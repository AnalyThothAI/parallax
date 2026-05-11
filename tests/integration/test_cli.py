import io
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import yaml

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.cli import build_parser, main
from gmgn_twitter_intel.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import SignalRepository
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.postgres_test_utils import test_postgres_dsn as postgres_test_dsn

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_event(
    event_id: str,
    received_at_ms: int | None = None,
    text: str = f"$PEPE Solana XDP mainnet base stablecoin {PEPE}",
) -> TwitterEvent:
    received_at_ms = received_at_ms if received_at_ms is not None else int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle="toly", name="toly", avatar=None, followers=100, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw=None,
    )


def seed_postgres(db_path: Path) -> None:
    conn = connect_postgres_test(db_path, read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        enrichment = EnrichmentRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=enrichment,
        )
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": PEPE,
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "1.0",
                    "s": "PEPE",
                },
            }
        )
        token_event = replace(
            make_event("event-1"),
            source=Source(
                provider="gmgn",
                transport="direct_ws",
                coverage="public_stream",
                channel="twitter_monitor_token",
            ),
            token_snapshot=snapshot,
        )
        ingest.ingest_event(token_event, is_watched=True)
        TokenRadarProjection(repos=repositories_for_connection(conn)).rebuild(
            window="5m",
            scope="all",
            now_ms=token_event.received_at_ms + 1,
            limit=20,
        )
    finally:
        conn.close()


def write_runtime_config(home: Path, *, db_path: Path, ws_token: str | None = None, llm: bool = False) -> Path:
    app_home = home / ".gmgn-twitter-intel"
    app_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "handles": ["toly", "traderpow"],
        "storage": {"postgres": {"dsn": postgres_test_dsn(), "password_file": None}},
    }
    if ws_token is not None:
        payload["ws_token"] = ws_token
    if llm:
        payload["llm"] = {"provider": "openai", "api_key": "sk-test", "model": "gpt-test"}
    path = app_home / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


class CliTests(unittest.TestCase):
    def test_audit_and_token_radar_projection_commands_are_registered(self):
        parser = build_parser()

        commands = [
            ["db", "audit"],
            ["db", "query-audit"],
            ["db", "query-audit", "--analyze"],
            ["asset-flow", "--window", "1h", "--limit", "5", "--scope", "all"],
            ["ops", "projection-status"],
            ["ops", "validate-projections", "--sample", "5"],
            ["ops", "sync-okx-cex-universe", "--inst-type", "SPOT"],
            ["ops", "run-token-discovery", "--limit", "5"],
            ["ops", "reprocess-token-intents", "--window", "24h", "--limit", "5", "--lookup-key", "symbol:SLOP"],
            ["ops", "rebuild-token-intents", "--window", "5m", "--limit", "5"],
            ["ops", "audit-token-intent", "--event-id", "event-1"],
            ["ops", "rebuild-token-radar", "--window", "1h"],
            ["ops", "audit-token-radar", "--window", "5m", "--scope", "all"],
            ["current-market", "--target-type", "Asset", "--target-id", f"asset:eip155:1:erc20:{PEPE}"],
        ]

        parsed = [parser.parse_args(command) for command in commands]

        self.assertEqual(parsed[0].db_command, "audit")
        self.assertEqual(parsed[1].db_command, "query-audit")
        self.assertFalse(parsed[1].analyze)
        self.assertTrue(parsed[2].analyze)
        self.assertEqual(parsed[3].command, "asset-flow")
        self.assertEqual(parsed[4].ops_command, "projection-status")
        self.assertEqual(parsed[5].ops_command, "validate-projections")
        self.assertEqual(parsed[5].sample, 5)
        self.assertEqual(parsed[6].ops_command, "sync-okx-cex-universe")
        self.assertEqual(parsed[7].ops_command, "run-token-discovery")
        self.assertEqual(parsed[7].limit, 5)
        self.assertEqual(parsed[8].ops_command, "reprocess-token-intents")
        self.assertEqual(parsed[8].window, "24h")
        self.assertEqual(parsed[8].lookup_key, ["symbol:SLOP"])
        self.assertEqual(parsed[9].ops_command, "rebuild-token-intents")
        self.assertEqual(parsed[9].window, "5m")
        self.assertEqual(parsed[10].ops_command, "audit-token-intent")
        self.assertEqual(parsed[11].ops_command, "rebuild-token-radar")
        self.assertEqual(parsed[12].ops_command, "audit-token-radar")
        self.assertEqual(parsed[13].command, "current-market")
        self.assertEqual(parsed[13].target_type, "Asset")

    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path, ws_token="secret", llm=True)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                exit_code = main(["config"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["handles"], ["toly", "traderpow"])
        self.assertEqual(payload["data"]["handle_count"], 2)
        self.assertTrue(payload["data"]["api"]["ws_token_configured"])
        self.assertTrue(payload["data"]["enrichment"]["llm_configured"])
        self.assertEqual(payload["data"]["enrichment"]["model"], "gpt-test")
        self.assertEqual(payload["data"]["enrichment"]["provider"], "openai")
        self.assertEqual(payload["data"]["store"]["engine"], "postgresql")
        self.assertIn("postgres_dsn", payload["data"]["store"])
        self.assertNotIn("embed" + "ding_dim", payload["data"]["store"])

    def test_config_redacts_notification_channel_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            app_home = home / ".gmgn-twitter-intel"
            app_home.mkdir(parents=True, exist_ok=True)
            (app_home / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "ws_token": "secret",
                        "handles": ["toly"],
                        "storage": {"postgres": {"dsn": postgres_test_dsn(), "password_file": None}},
                        "notifications": {
                            "channels": {
                                "pushdeer": {
                                    "enabled": True,
                                    "provider": "apprise",
                                    "url": "pushdeer://pushKey",
                                    "min_severity": "high",
                                },
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                exit_code = main(["config"], stdout=stdout)

        raw_output = stdout.getvalue()
        payload = json.loads(raw_output)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("pushdeer://pushKey", raw_output)
        self.assertTrue(payload["data"]["notifications"]["channels"]["pushdeer"]["url_configured"])
        self.assertEqual(payload["data"]["notifications"]["channels"]["pushdeer"]["provider"], "apprise")

    def test_recent_search_asset_flow_harness_and_alerts_use_postgres_runtime_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path)
            seed_postgres(db_path)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                recent_code = main(["recent", "--limit", "5"], stdout=stdout)
                search_code = main(["search", "--symbol", "PEPE", "--limit", "5"], stdout=stdout)
                asset_flow_code = main(
                    ["asset-flow", "--window", "5m", "--limit", "5", "--scope", "all"],
                    stdout=stdout,
                )
                current_market_code = main(
                    ["current-market", "--target-type", "Asset", "--target-id", f"asset:eip155:1:erc20:{PEPE}"],
                    stdout=stdout,
                )
                alerts_code = main(["account-alerts", "--window", "24h", "--limit", "5"], stdout=stdout)
                jobs_code = main(["enrichment-jobs", "--limit", "5"], stdout=stdout)
                social_events_code = main(["social-events", "--window", "1h", "--limit", "5"], stdout=stdout)
                seeds_code = main(["attention-seeds", "--window", "1h", "--limit", "5"], stdout=stdout)
                snapshots_code = main(["harness-snapshots", "--horizon", "6h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [
                recent_code,
                search_code,
                asset_flow_code,
                current_market_code,
                alerts_code,
                jobs_code,
                social_events_code,
                seeds_code,
                snapshots_code,
            ],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(lines[0]["data"]["events"][0]["event_id"], "event-1")
        self.assertEqual(lines[1]["data"]["items"][0]["event"]["event_id"], "event-1")
        self.assertEqual(lines[2]["data"]["scope"], "all")
        self.assertEqual(lines[2]["data"]["targets"][0]["target"]["symbol"], "PEPE")
        self.assertEqual(lines[2]["data"]["targets"][0]["attention"]["mentions_window"], 1)
        self.assertEqual(lines[3]["data"]["market_status"], "fresh")
        self.assertEqual(lines[3]["data"]["fields"]["price_usd"]["status"], "fresh")
        self.assertEqual(
            {item["alert_type"] for item in lines[4]["data"]["items"]},
            {"account_token"},
        )
        self.assertEqual(lines[5]["data"]["counts"]["pending"], 1)
        self.assertEqual(lines[6]["data"]["items"], [])
        self.assertEqual(lines[7]["data"]["items"], [])
        self.assertEqual(lines[8]["data"]["items"], [])

    def test_notification_deliveries_command_reads_delivery_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path)
            conn = connect_postgres_test(db_path, read_only=False)
            try:
                migrate(conn)
                notifications = NotificationRepository(conn)
                notification = notifications.insert_notification(
                    dedup_key="hot:pepe",
                    rule_id="hot_quality_token_5m",
                    severity="high",
                    title="PEPE heat",
                    body="heat score 88",
                    entity_type="token",
                    entity_key="token:eth:pepe",
                    symbol="PEPE",
                    source_table="token_flow",
                    source_id="token:eth:pepe",
                    occurrence_at_ms=1_700_000_060_000,
                    payload={"social_heat_score": 88},
                    channels=["in_app", "pushdeer"],
                )
                self.assertIsNotNone(notification)
                notifications.enqueue_delivery(
                    notification_id=notification["notification_id"],
                    channel_id="pushdeer",
                    provider="apprise",
                    max_attempts=5,
                    next_run_at_ms=1_700_000_060_000,
                )
            finally:
                conn.close()
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                exit_code = main(["notification-deliveries", "--limit", "5"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["items"][0]["channel_id"], "pushdeer")
        self.assertEqual(payload["data"]["items"][0]["status"], "pending")

    def test_db_audit_query_audit_and_token_radar_projection_ops_use_postgres_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path)
            conn = connect_postgres_test(db_path, read_only=False)
            try:
                migrate(conn)
            finally:
                conn.close()
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                db_audit_code = main(["db", "audit"], stdout=stdout)
                query_audit_code = main(["db", "query-audit"], stdout=stdout)
                projection_status_code = main(["ops", "projection-status"], stdout=stdout)
                validate_code = main(["ops", "validate-projections", "--sample", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([db_audit_code, query_audit_code, projection_status_code, validate_code], [0, 0, 0, 0])
        self.assertEqual(lines[0]["data"]["engine"], "postgresql")
        self.assertTrue(lines[0]["data"]["projection_schema"]["projection_offsets"])
        self.assertFalse(lines[1]["data"]["analyze"])
        self.assertIn("token_radar_latest", {item["name"] for item in lines[1]["data"]["queries"]})
        self.assertEqual(lines[2]["data"]["known_projections"][0]["projection_name"], "token-radar")
        self.assertEqual(lines[3]["data"]["sample"], 5)
        self.assertEqual(lines[3]["data"]["mismatch_count"], 0)

    def test_obsolete_runtime_commands_are_not_registered(self):
        parser_help = main(["embed"], stdout=io.StringIO())

        self.assertEqual(parser_help, 2)
        obsolete_commands = [
            ["narrative-flow"],
            ["account-narratives"],
            ["narrative-seeds"],
            ["narrative-token-flow", "--seed-id", "seed"],
            ["attention-frontier"],
            ["ops", "rebuild-narrative-links"],
            ["token-flow"],
            ["ops", "rebuild-attributions"],
            ["ops", "freeze-token-signals"],
            ["ops", "settle-token-signals"],
            ["token-signal-snapshots"],
            ["token-signal-outcomes"],
            ["token-signal-evaluations"],
            ["market-observations"],
            ["ops", "backfill-market-observations"],
            ["ops", "process-asset-resolution-jobs"],
            ["ops", "resolve-asset-symbol", "--symbol", "MIRROR"],
            ["ops", "asset-resolution-health"],
            ["ops", "audit-asset-attribution", "--event-id", "event-1"],
        ]
        for command in obsolete_commands:
            self.assertEqual(main(command, stdout=io.StringIO()), 2)

def test_recent_defaults_to_runtime_postgres_store_without_ws_token(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    db_path = app_home / "postgres_test_db"
    write_runtime_config(tmp_path, db_path=db_path)
    seed_postgres(db_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "event-1"


def test_harness_cli_reports_empty_read_models_without_error(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    db_path = app_home / "postgres_test_db"
    write_runtime_config(tmp_path, db_path=db_path)
    conn = connect_postgres_test(db_path, read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    codes = [
        main(["social-events", "--window", "1h", "--limit", "5"], stdout=stdout),
        main(["attention-seeds", "--window", "1h", "--limit", "5"], stdout=stdout),
        main(["harness-snapshots", "--horizon", "6h", "--limit", "5"], stdout=stdout),
        main(["harness-outcomes", "--horizon", "6h", "--limit", "5"], stdout=stdout),
        main(["harness-credits", "--horizon", "6h", "--limit", "5"], stdout=stdout),
        main(["harness-weights", "--horizon", "6h", "--limit", "5"], stdout=stdout),
        main(["harness-health"], stdout=stdout),
        main(["harness-score-buckets", "--horizon", "6h"], stdout=stdout),
        main(["ops", "backfill-harness-jobs", "--limit", "5"], stdout=stdout),
        main(["ops", "settle-harness", "--horizon", "6h", "--limit", "5", "--now-ms", "21601001"], stdout=stdout),
        main(["ops", "attribute-harness-credits", "--horizon", "6h", "--limit", "5"], stdout=stdout),
        main(["ops", "update-harness-weights", "--limit", "5"], stdout=stdout),
    ]

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert codes == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert [line["ok"] for line in lines] == [True, True, True, True, True, True, True, True, True, True, True, True]
    assert lines[0]["data"]["items"] == []
    assert lines[6]["data"]["snapshots_24h"] == 0
    assert lines[7]["data"]["items"][2]["bucket"] == "-0.4 to 0.4"
    assert lines[8]["data"]["jobs_enqueued"] == 0
    assert lines[9]["data"]["snapshots_scanned"] == 0
    assert lines[10]["data"]["credits_written"] == 0
    assert lines[11]["data"]["weights_updated"] == 0


def test_init_creates_runtime_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["init"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["created"] is True
    assert (tmp_path / ".gmgn-twitter-intel" / "config.yaml").is_file()


def test_run_sync_gmgn_directory_walks_all_pages_and_upserts():
    from gmgn_twitter_intel.app.surfaces.cli.main import _run_sync_gmgn_directory
    from gmgn_twitter_intel.integrations.gmgn.directory_client import GmgnDirectoryEntry

    class FakeClient:
        def __init__(self, entries):
            self._entries = entries
            self.calls: list[int] = []

        def iter_entries(self, *, max_pages):
            self.calls.append(max_pages)
            return iter(self._entries)

    class FakeRepo:
        def __init__(self):
            self.upserts: list[dict] = []
            self.commits = 0

            class _Conn:
                outer = self

                def commit(self_inner):
                    self_inner.outer.commits += 1

            self.conn = _Conn()

        def upsert_directory_entry(self, **kwargs):
            self.upserts.append(kwargs)

    entries = [
        GmgnDirectoryEntry(handle="cz", gmgn_user_id="X", user_tags=("kol",), platform_followers=100),
        GmgnDirectoryEntry(handle="elonmusk", gmgn_user_id="Y", user_tags=("founder",), platform_followers=200),
    ]
    client = FakeClient(entries)
    repo = FakeRepo()

    summary = _run_sync_gmgn_directory(
        client=client,
        repository=repo,
        now_ms=1_700_000_000_000,
        max_pages=42,
    )

    assert client.calls == [42]
    assert repo.commits == 1
    assert [u["handle"] for u in repo.upserts] == ["cz", "elonmusk"]
    assert all(u["observed_at_ms"] == 1_700_000_000_000 for u in repo.upserts)
    assert all(u["commit"] is False for u in repo.upserts)
    assert summary == {
        "upserted": 2,
        "first_handles": ["cz", "elonmusk"],
        "last_handles": ["cz", "elonmusk"],
        "observed_at_ms": 1_700_000_000_000,
    }


def test_cli_ops_sync_gmgn_directory_dispatches_to_runner(monkeypatch, tmp_path):
    import io
    import json

    import gmgn_twitter_intel.app.surfaces.cli.main as cli_module

    captured = {}

    def fake_runner(*, client, repository, now_ms, max_pages):
        captured["client"] = client
        captured["repository_type"] = type(repository).__name__
        captured["now_ms"] = now_ms
        captured["max_pages"] = max_pages
        return {"upserted": 7, "first_handles": [], "last_handles": [], "observed_at_ms": now_ms}

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    monkeypatch.setattr(cli_module, "_run_sync_gmgn_directory", fake_runner)
    monkeypatch.setattr(cli_module, "GmgnDirectoryClient", FakeClient)
    monkeypatch.setattr(cli_module, "_now_ms", lambda: 1_700_000_000_000)
    write_runtime_config(tmp_path, db_path=tmp_path / ".gmgn-twitter-intel" / "postgres_test_db")
    conn = connect_postgres_test(read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()
    monkeypatch.setenv("HOME", str(tmp_path))

    stdout = io.StringIO()
    code = cli_module.main(
        ["ops", "sync-gmgn-directory", "--max-pages", "3"],
        stdout=stdout,
    )

    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload == {
        "ok": True,
        "data": {
            "upserted": 7,
            "first_handles": [],
            "last_handles": [],
            "observed_at_ms": 1_700_000_000_000,
        },
    }
    assert captured["max_pages"] == 3
    assert captured["repository_type"] == "AccountQualityRepository"
    assert isinstance(captured["client"], FakeClient)


def test_cli_ops_sync_gmgn_directory_emits_error_on_directory_failure(monkeypatch, tmp_path):
    import io
    import json

    import gmgn_twitter_intel.app.surfaces.cli.main as cli_module
    from gmgn_twitter_intel.integrations.gmgn.directory_client import GmgnDirectoryError

    def boom(*, client, repository, now_ms, max_pages):
        raise GmgnDirectoryError("Cloudflare 403")

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(cli_module, "_run_sync_gmgn_directory", boom)
    monkeypatch.setattr(cli_module, "GmgnDirectoryClient", FakeClient)
    write_runtime_config(tmp_path, db_path=tmp_path / ".gmgn-twitter-intel" / "postgres_test_db")
    conn = connect_postgres_test(read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()
    monkeypatch.setenv("HOME", str(tmp_path))

    stdout = io.StringIO()
    code = cli_module.main(["ops", "sync-gmgn-directory"], stdout=stdout)

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "Cloudflare 403"}


if __name__ == "__main__":
    unittest.main()
