import io
import json
import tempfile
import time
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.app.surfaces.cli.parser import build_parser
from parallax.cli import main
from parallax.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from parallax.domains.evidence.services.ingest_service import IngestService
from parallax.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from parallax.platform.config.settings import default_workers_yaml
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.postgres_test_utils import test_postgres_dsn as postgres_test_dsn

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


class FakeWorkerSettings(SimpleNamespace):
    def model_copy(self, *, update: dict[str, object] | None = None):
        data = vars(self).copy()
        data.update(update or {})
        return type(self)(**data)


class FakeAssetMarketProviders(SimpleNamespace):
    async def aclose(self):
        return None


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
        repos = repositories_for_connection(
            conn,
            pulse_job_running_timeout_ms=300_000,
            notification_delivery_running_timeout_ms=300_000,
            notification_delivery_stale_running_terminalization_batch_size=100,
        )
        ingest = IngestService(
            evidence=repos.evidence,
            entities=repos.entities,
            signals=repos.signals,
            registry=repos.registry,
            identity_evidence=repos.identity_evidence,
            token_intent_lookup=repos.token_intent_lookup,
            token_evidence=repos.token_evidence,
            token_intents=repos.token_intents,
            intent_resolutions=repos.intent_resolutions,
            discovery=repos.discovery,
            market_ticks=repos.market_ticks,
            market_tick_current_dirty_targets=repos.market_tick_current_dirty_targets,
            enriched_events=repos.enriched_events,
            event_anchor_jobs=repos.event_anchor_jobs,
            token_radar_source_dirty_events=repos.token_radar_source_dirty_events,
            event_anchor_active_window_ms=300_000,
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
        now_ms = token_event.received_at_ms + 1
        repos.token_radar_dirty_targets.enqueue_recent_resolved_targets(
            since_ms=max(0, token_event.received_at_ms - 5 * 60 * 1000),
            now_ms=now_ms,
            limit=20,
            reason="test_seed",
            commit=True,
        )
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=now_ms,
            limit=20,
            rank_limit=20,
            lease_owner="test_cli_seed",
        )
    finally:
        conn.close()


def write_runtime_config(home: Path, *, db_path: Path, ws_token: str | None = None, llm: bool = False) -> Path:
    app_home = home / ".parallax"
    app_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "handles": ["toly", "traderpow"],
        "storage": {"postgres": {"dsn": postgres_test_dsn(), "password_file": None}},
    }
    if ws_token is not None:
        payload["ws_token"] = ws_token
    payload["gmgn"] = {"api_key": "gmgn-test", "openapi_base_url": "https://openapi.gmgn.ai"}
    workers_payload = yaml.safe_load(default_workers_yaml())
    if llm:
        payload["llm"] = {"provider": "litellm", "api_key": "sk-test"}
        workers_payload["agent_runtime"]["defaults"]["model"] = "gpt-test"
    path = app_home / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    (app_home / "workers.yaml").write_text(yaml.safe_dump(workers_payload, sort_keys=False), encoding="utf-8")
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
            ["ops", "worker-status"],
            ["ops", "validate-projections", "--sample", "5"],
            ["ops", "sync-binance-usdt-perp-universe", "--dry-run"],
            ["ops", "sync-binance-usdt-perp-universe", "--execute"],
            ["ops", "sync-binance-cex-profiles"],
            ["ops", "run-resolution-refresh", "--limit", "5"],
            ["ops", "refresh-asset-profiles", "--limit", "5"],
            ["ops", "mirror-token-images", "--limit", "5"],
            ["ops", "repair-token-profile-images", "--limit", "5"],
            ["ops", "reprocess-token-intents", "--window", "24h", "--limit", "5", "--lookup-key", "symbol:SLOP"],
            ["ops", "rebuild-token-intents", "--window", "5m", "--limit", "5"],
            ["ops", "audit-token-intent", "--event-id", "event-1"],
            ["ops", "rebuild-token-radar", "--window", "1h"],
            ["ops", "audit-token-radar", "--window", "5m", "--scope", "all"],
            ["ops", "factor-diagnostics", "--window", "1h", "--scope", "all", "--limit", "200"],
            [
                "ops",
                "settle-token-factors",
                "--window",
                "1h",
                "--scope",
                "all",
                "--horizon",
                "1h",
                "--limit",
                "1000",
                "--now-ms",
                "1700000000000",
            ],
            ["ops", "sync-us-equity-symbols"],
            ["ops", "rebuild-token-profiles", "--limit", "5"],
            ["ops", "rebuild-market-tick-current", "--dry-run"],
            ["ops", "enqueue-token-radar-dirty-targets", "--source", "events", "--since-ms", "0", "--dry-run"],
            [
                "ops",
                "enqueue-token-radar-dirty-targets",
                "--source",
                "market-current",
                "--since-ms",
                "0",
                "--execute",
            ],
            ["ops", "enqueue-token-capture-tier-rank-set", "--execute"],
        ]

        parsed = [parser.parse_args(command) for command in commands]

        self.assertEqual(parsed[0].db_command, "audit")
        self.assertEqual(parsed[1].db_command, "query-audit")
        self.assertFalse(parsed[1].analyze)
        self.assertTrue(parsed[2].analyze)
        self.assertEqual(parsed[3].command, "asset-flow")
        self.assertEqual(parsed[4].ops_command, "projection-status")
        self.assertEqual(parsed[5].ops_command, "worker-status")
        self.assertEqual(parsed[6].ops_command, "validate-projections")
        self.assertEqual(parsed[6].sample, 5)
        self.assertEqual(parsed[7].ops_command, "sync-binance-usdt-perp-universe")
        self.assertTrue(parsed[7].dry_run)
        self.assertEqual(parsed[8].ops_command, "sync-binance-usdt-perp-universe")
        self.assertTrue(parsed[8].execute)
        self.assertEqual(parsed[9].ops_command, "sync-binance-cex-profiles")
        self.assertEqual(parsed[10].ops_command, "run-resolution-refresh")
        self.assertEqual(parsed[10].limit, 5)
        self.assertEqual(parsed[11].ops_command, "refresh-asset-profiles")
        self.assertEqual(parsed[11].limit, 5)
        self.assertEqual(parsed[12].ops_command, "mirror-token-images")
        self.assertEqual(parsed[12].limit, 5)
        self.assertEqual(parsed[13].ops_command, "repair-token-profile-images")
        self.assertEqual(parsed[13].limit, 5)
        self.assertEqual(parsed[14].ops_command, "reprocess-token-intents")
        self.assertEqual(parsed[14].window, "24h")
        self.assertEqual(parsed[14].lookup_key, ["symbol:SLOP"])
        self.assertEqual(parsed[15].ops_command, "rebuild-token-intents")
        self.assertEqual(parsed[15].window, "5m")
        self.assertEqual(parsed[16].ops_command, "audit-token-intent")
        self.assertEqual(parsed[17].ops_command, "rebuild-token-radar")
        self.assertEqual(parsed[18].ops_command, "audit-token-radar")
        self.assertEqual(parsed[19].ops_command, "factor-diagnostics")
        self.assertEqual(parsed[19].limit, 200)
        self.assertEqual(parsed[20].ops_command, "settle-token-factors")
        self.assertEqual(parsed[20].now_ms, 1_700_000_000_000)
        self.assertEqual(parsed[21].ops_command, "sync-us-equity-symbols")
        self.assertEqual(parsed[22].ops_command, "rebuild-token-profiles")
        self.assertEqual(parsed[22].limit, 5)
        self.assertEqual(parsed[23].ops_command, "rebuild-market-tick-current")
        self.assertTrue(parsed[23].dry_run)
        self.assertEqual(parsed[24].ops_command, "enqueue-token-radar-dirty-targets")
        self.assertEqual(parsed[24].source, "events")
        self.assertEqual(parsed[24].since_ms, 0)
        self.assertEqual(parsed[24].limit, 5000)
        self.assertTrue(parsed[24].dry_run)
        self.assertEqual(parsed[25].ops_command, "enqueue-token-radar-dirty-targets")
        self.assertEqual(parsed[25].source, "market-current")
        self.assertTrue(parsed[25].execute)
        self.assertEqual(parsed[26].ops_command, "enqueue-token-capture-tier-rank-set")
        self.assertEqual(parsed[26].window, "24h")
        self.assertTrue(parsed[26].execute)

    def test_cli_ops_rebuild_narrative_intel_is_not_registered(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["ops", "rebuild-narrative-intel", "--window", "1h"])

    def test_cli_ops_cex_binance_hard_cut_cleanup_is_not_registered(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["ops", "cex-binance-hard-cut-cleanup", "--dry-run"])

    def test_cli_ops_cleanup_news_brief_input_is_not_registered(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["ops", "cleanup-news-brief-input", "--dry-run"])

    def test_cli_ops_mirror_token_images_has_no_source_limit_option(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["ops", "mirror-token-images", "--source-limit", "9"])

    def test_cli_ops_repair_token_profile_images_rejects_non_positive_limit(self):
        parser = build_parser()

        for limit in ("0", "-1"):
            with self.subTest(limit=limit), self.assertRaises(SystemExit):
                parser.parse_args(["ops", "repair-token-profile-images", "--limit", limit])

    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".parallax" / "postgres_test_db"
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
        self.assertEqual(
            payload["data"]["config_path"],
            str(home / ".parallax" / "config.yaml"),
        )
        self.assertTrue(payload["data"]["agent_execution"]["llm_configured"])
        self.assertEqual(payload["data"]["agent_execution"]["model"], "gpt-test")
        self.assertEqual(payload["data"]["agent_execution"]["provider"], "litellm")
        self.assertEqual(
            payload["data"]["providers"]["gmgn"],
            {
                "configured": True,
                "openapi_base_url": "https://openapi.gmgn.ai",
                "timeout_seconds": 5.0,
                "token_info_cache_ttl_seconds": 60,
            },
        )
        self.assertNotIn("gmgn-test", stdout.getvalue())
        self.assertEqual(payload["data"]["store"]["engine"], "postgresql")
        self.assertIn("postgres_dsn", payload["data"]["store"])
        self.assertNotIn("embed" + "ding_dim", payload["data"]["store"])
        self.assertEqual(
            payload["data"]["workers_config_path"],
            str(home / ".parallax" / "workers.yaml"),
        )
        self.assertEqual(payload["data"]["workers"]["collector"]["mode"], "continuous")
        self.assertTrue(payload["data"]["workers"]["collector"]["enabled"])
        self.assertEqual(payload["data"]["workers"]["pulse_candidate"]["batch_size"], 10)

    def test_config_redacts_notification_channel_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            app_home = home / ".parallax"
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
            (app_home / "workers.yaml").write_text(default_workers_yaml(), encoding="utf-8")
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                exit_code = main(["config"], stdout=stdout)

        raw_output = stdout.getvalue()
        payload = json.loads(raw_output)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("pushdeer://pushKey", raw_output)
        self.assertTrue(payload["data"]["notifications"]["channels"]["pushdeer"]["url_configured"])
        self.assertEqual(payload["data"]["notifications"]["channels"]["pushdeer"]["provider"], "apprise")

    def test_recent_search_asset_flow_and_alerts_use_postgres_runtime_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".parallax" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path)
            seed_postgres(db_path)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                recent_code = main(["recent", "--limit", "5"], stdout=stdout)
                search_code = main(["search", "$PEPE", "--limit", "5"], stdout=stdout)
                asset_flow_code = main(
                    ["asset-flow", "--window", "5m", "--limit", "5", "--scope", "all"],
                    stdout=stdout,
                )
                alerts_code = main(["account-alerts", "--window", "24h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [
                recent_code,
                search_code,
                asset_flow_code,
                alerts_code,
            ],
            [0, 0, 0, 0],
        )
        self.assertEqual(lines[0]["data"]["events"][0]["event_id"], "event-1")
        self.assertEqual(lines[1]["data"]["items"][0]["event"]["event_id"], "event-1")
        self.assertEqual(lines[2]["data"]["scope"], "all")
        self.assertEqual(lines[2]["data"]["targets"][0]["target"]["symbol"], "PEPE")
        self.assertEqual(lines[2]["data"]["targets"][0]["attention"]["mentions_5m"], 1)
        self.assertEqual(
            {item["alert_type"] for item in lines[3]["data"]["items"]},
            {"account_token"},
        )

    def test_notification_deliveries_command_reads_delivery_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".parallax" / "postgres_test_db"
            write_runtime_config(home, db_path=db_path)
            conn = connect_postgres_test(db_path, read_only=False)
            try:
                migrate(conn)
                notifications = NotificationRepository(
                    conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100
                )
                notification = notifications.insert_notification(
                    dedup_key="news:pepe",
                    rule_id="news_high_signal",
                    severity="high",
                    title="PEPE news",
                    body="agent news driver",
                    entity_type="token",
                    entity_key="token:eth:pepe",
                    symbol="PEPE",
                    source_table="news_items",
                    source_id="token:eth:pepe",
                    occurrence_at_ms=1_700_000_060_000,
                    payload={"decision_class": "driver"},
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
            db_path = home / ".parallax" / "postgres_test_db"
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
            ["ops", "prune-token-radar", "--dry-run"],
            ["ops", "backfill-token-radar-first-seen"],
        ]
        for command in obsolete_commands:
            self.assertEqual(main(command, stdout=io.StringIO()), 2)


def test_recent_defaults_to_runtime_postgres_store_without_ws_token(tmp_path, monkeypatch):
    app_home = tmp_path / ".parallax"
    db_path = app_home / "postgres_test_db"
    write_runtime_config(tmp_path, db_path=db_path)
    seed_postgres(db_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "event-1"


def test_rebuild_token_radar_one_shot_acquires_projection_advisory_lock(monkeypatch):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    events: list[tuple] = []
    configured_lock_key = 909090

    class FakeLock:
        def release(self):
            events.append(("release",))

    class FakeDB:
        api_pool = None
        worker_pool = None
        wake_pool = None

        def wake_emitter(self):
            return object()

        def wake_listener(self, worker_name, wakes_on):
            events.append(("wake_listener", worker_name, tuple(wakes_on)))
            return object()

        def acquire_advisory_lock_connection(self, worker_name, key):
            events.append(("acquire", worker_name, key))
            return FakeLock()

        async def aclose(self):
            return None

    class FakeWorker:
        SINGLE_WRITER_KEY = 2026051501

        def __init__(self, **kwargs):
            self.settings = kwargs["settings"]
            events.append(("worker_init", kwargs["name"]))

        def _advisory_lock_key(self):
            settings_key = getattr(self.settings, "advisory_lock_key", None)
            if settings_key is not None:
                return int(settings_key)
            return self.SINGLE_WRITER_KEY

        def rebuild_once(self, **kwargs):
            events.append(("rebuild", kwargs))
            return {"rows_written": 1}

        async def aclose(self):
            events.append(("worker_close",))

    db = FakeDB()
    settings = SimpleNamespace(
        workers=SimpleNamespace(
            token_radar_projection=FakeWorkerSettings(
                advisory_lock_key=configured_lock_key,
                batch_size=100,
                wakes_on=("market_tick_written",),
            ),
            narrative_admission=SimpleNamespace(enabled=True),
        )
    )
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", staticmethod(lambda settings, telemetry: db))
    monkeypatch.setattr(ops_module, "TokenRadarProjectionWorker", FakeWorker)

    result = ops_module._run_token_radar_projection_worker_once(
        settings,
        windows=("1h",),
        scopes=("all",),
        limit=5,
        now_ms=1_700_000_000_000,
    )

    assert result == {"rows_written": 1}
    assert ("acquire", "token_radar_projection", configured_lock_key) in events
    assert ("acquire", "token_radar_projection", FakeWorker.SINGLE_WRITER_KEY) not in events
    assert events.index(("acquire", "token_radar_projection", configured_lock_key)) < events.index(
        (
            "rebuild",
            {
                "now_ms": 1_700_000_000_000,
                "windows": ("1h",),
                "scopes": ("all",),
                "limit": 5,
            },
        )
    )
    assert events.index(("release",)) < events.index(("worker_close",))


def test_rebuild_token_radar_one_shot_skips_when_live_worker_holds_lock(monkeypatch):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    events: list[tuple] = []
    configured_lock_key = 909090

    class FakeDB:
        api_pool = None
        worker_pool = None
        wake_pool = None

        def wake_emitter(self):
            return object()

        def wake_listener(self, worker_name, wakes_on):
            events.append(("wake_listener", worker_name, tuple(wakes_on)))
            return object()

        def acquire_advisory_lock_connection(self, worker_name, key):
            events.append(("acquire", worker_name, key))
            raise RuntimeError("advisory_lock_unavailable")

        async def aclose(self):
            return None

    class FakeWorker:
        SINGLE_WRITER_KEY = 2026051501

        def __init__(self, **kwargs):
            self.settings = kwargs["settings"]
            events.append(("worker_init", kwargs["name"]))

        def _advisory_lock_key(self):
            return configured_lock_key

        def rebuild_once(self, **kwargs):
            events.append(("rebuild", kwargs))
            return {"rows_written": 1}

        async def aclose(self):
            events.append(("worker_close",))

    db = FakeDB()
    settings = SimpleNamespace(
        workers=SimpleNamespace(
            token_radar_projection=FakeWorkerSettings(
                advisory_lock_key=configured_lock_key,
                batch_size=100,
                wakes_on=("market_tick_written",),
            ),
            narrative_admission=SimpleNamespace(enabled=True),
        )
    )
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", staticmethod(lambda settings, telemetry: db))
    monkeypatch.setattr(ops_module, "TokenRadarProjectionWorker", FakeWorker)

    result = ops_module._run_token_radar_projection_worker_once(
        settings,
        windows=("1h",),
        scopes=("all",),
        limit=5,
        now_ms=1_700_000_000_000,
    )

    assert result["status"] == "skipped"
    assert result["notes"] == {
        "reason": "advisory_lock_unavailable",
        "worker_name": "token_radar_projection",
        "lock_key": configured_lock_key,
    }
    assert ("acquire", "token_radar_projection", configured_lock_key) in events
    assert not any(event[0] == "rebuild" for event in events)
    assert events[-1] == ("worker_close",)


def test_init_creates_runtime_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["init"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["created"] is True
    assert (tmp_path / ".parallax" / "config.yaml").is_file()


def test_run_sync_gmgn_directory_walks_all_pages_and_upserts():
    from parallax.app.surfaces.cli.commands.ops import _run_sync_gmgn_directory
    from parallax.integrations.gmgn.directory_client import GmgnDirectoryEntry

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

                @contextmanager
                def transaction(self_inner):
                    yield
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

    from parallax.app.surfaces.cli.commands import ops as ops_module

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

    monkeypatch.setattr(ops_module, "_run_sync_gmgn_directory", fake_runner)
    monkeypatch.setattr(ops_module, "GmgnDirectoryClient", FakeClient)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    conn = connect_postgres_test(read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()
    monkeypatch.setenv("HOME", str(tmp_path))

    stdout = io.StringIO()
    code = main(
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


def test_cli_ops_factor_diagnostics_reads_latest_token_radar_current_rows(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.domains.token_intel.interfaces import (
        TOKEN_FACTOR_SNAPSHOT_VERSION,
        TOKEN_RADAR_FACTOR_FAMILIES,
        TOKEN_RADAR_PROJECTION_VERSION,
    )

    captured = {}

    class FakeTokenRadar:
        def latest_current_rows(self, **kwargs):
            captured.update(kwargs)
            return [
                {
                    "factor_snapshot_json": {
                        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                        "families": {
                            family: {"score": 50, "data_health": "ready", "facts": {}, "factors": {}}
                            for family in TOKEN_RADAR_FACTOR_FAMILIES
                        },
                        "gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
                        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
                        "normalization": {},
                        "composite": {"rank_score": 50, "recommended_decision": "watch"},
                    }
                }
            ]

    class FakeRepos:
        token_radar = FakeTokenRadar()

    @contextmanager
    def fake_repositories(_settings):
        yield FakeRepos()

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "factor-diagnostics", "--window", "1h", "--scope", "all", "--limit", "7"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured == {
        "window": "1h",
        "scope": "all",
        "venue": "all",
        "limit": 7,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
    }
    assert payload["ok"] is True
    assert payload["data"]["row_count"] == 1


def test_cli_ops_cleanup_news_intel_hard_cut_is_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-intel-hard-cut"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-intel-hard-cut", "--execute"])


def test_cli_ops_settle_token_factors_dispatches_to_service_with_hidden_now_ms(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured = {}

    class FakeRepos:
        pass

    @contextmanager
    def fake_repositories(_settings):
        yield FakeRepos()

    def fake_settle_token_factor_scores(**kwargs):
        captured.update(kwargs)
        return {"settled_count": 3, "generated_at_ms": kwargs["generated_at_ms"]}

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "settle_token_factor_scores", fake_settle_token_factor_scores)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "settle-token-factors",
            "--window",
            "1h",
            "--scope",
            "all",
            "--horizon",
            "1h",
            "--limit",
            "9",
            "--now-ms",
            "1700000000123",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["repos"].__class__ is FakeRepos
    assert captured["window"] == "1h"
    assert captured["scope"] == "all"
    assert captured["horizon"] == "1h"
    assert captured["limit"] == 9
    assert captured["generated_at_ms"] == 1_700_000_000_123
    assert payload == {"ok": True, "data": {"settled_count": 3, "generated_at_ms": 1_700_000_000_123}}


def test_cli_ops_settle_token_factors_respects_zero_hidden_now_ms(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured = {}

    class FakeRepos:
        pass

    @contextmanager
    def fake_repositories(_settings):
        yield FakeRepos()

    def fake_settle_token_factor_scores(**kwargs):
        captured.update(kwargs)
        return {"generated_at_ms": kwargs["generated_at_ms"]}

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "settle_token_factor_scores", fake_settle_token_factor_scores)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 9_999)
    stdout = io.StringIO()

    code = main(
        ["ops", "settle-token-factors", "--window", "1h", "--scope", "all", "--horizon", "1h", "--now-ms", "0"],
        stdout=stdout,
    )

    assert code == 0
    assert captured["generated_at_ms"] == 0
    assert json.loads(stdout.getvalue())["data"]["generated_at_ms"] == 0


def test_cli_ops_refresh_asset_profiles_emits_skipped_without_profile_provider(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured = {}

    @contextmanager
    def fake_repositories(_settings):
        raise AssertionError("refresh-asset-profiles must not hold an outer repository session")

    class FakeDB:
        api_pool = SimpleNamespace(close=lambda: None)
        worker_pool = SimpleNamespace(close=lambda: None)
        wake_pool = SimpleNamespace(close=lambda: None)

        async def aclose(self):
            return None

    def fake_wire_asset_market_providers(settings, *, start_collector):
        captured["start_collector"] = start_collector
        return FakeAssetMarketProviders(dex_profile_sources=())

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db", llm=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fake_wire_asset_market_providers)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(
        ["ops", "refresh-asset-profiles", "--limit", "3"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["start_collector"] is True
    assert payload == {
        "ok": True,
        "data": {
            "providers": [],
            "selected": 0,
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "targets_enqueued": 0,
            "rows_written": 0,
            "ready": 0,
            "missing": 0,
            "error": 0,
            "provider_blocked": 0,
            "skipped": 1,
            "sources": {},
            "started_at_ms": 1_700_000_000_000,
            "finished_at_ms": 1_700_000_000_000,
        },
    }


def test_cli_ops_run_resolution_refresh_uses_worker_without_outer_repository_session(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured = {}

    @contextmanager
    def fake_repositories(_settings):
        raise AssertionError("run-resolution-refresh must not hold an outer repository session")

    class FakeDB:
        def __init__(self) -> None:
            self.repos = SimpleNamespace(discovery=FakeDiscovery())
            self.api_pool = SimpleNamespace(close=lambda: None)
            self.worker_pool = SimpleNamespace(close=lambda: None)
            self.wake_pool = SimpleNamespace(close=lambda: None)

        def worker_session(self, name):
            captured.setdefault("session_names", []).append(name)
            return FakeSession(self.repos)

        def wake_emitter(self):
            return object()

        async def aclose(self):
            return None

    class FakeSession:
        def __init__(self, repos):
            self.repos = repos

        def __enter__(self):
            return self.repos

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeDiscovery:
        def claim_due_lookup_keys(self, **kwargs):
            captured["claim_due_lookup_kwargs"] = kwargs
            return []

        def counts(self):
            return {"found": 0}

    def fake_wire_asset_market_providers(settings, *, start_collector):
        captured["start_collector"] = start_collector
        return FakeAssetMarketProviders(
            dex_discovery_market=object(),
            dex_quote_market=None,
            discovery_chain_ids=("solana",),
        )

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fake_wire_asset_market_providers)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(["ops", "run-resolution-refresh", "--limit", "3"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["start_collector"] is True
    assert captured["session_names"] == ["resolution_refresh", "resolution_refresh"]
    assert captured["claim_due_lookup_kwargs"]["limit"] == 3
    assert payload["data"]["lookups_selected"] == 0


def test_cli_ops_rebuild_token_profiles_is_db_only_and_closes_db(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured: dict[str, object] = {}
    closed: list[str] = []

    @contextmanager
    def fake_repositories(_settings):
        raise AssertionError("rebuild-token-profiles must not hold an outer repository session")

    class FakePool:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    class FakeDB:
        api_pool = FakePool("api")
        worker_pool = FakePool("worker")
        tool_pool = FakePool("tool")
        wake_pool = FakePool("wake")

        async def aclose(self):
            self.api_pool.close()
            self.worker_pool.close()
            self.tool_pool.close()
            self.wake_pool.close()

    class FakeWorker:
        def __init__(self, *, name, settings, db, telemetry):
            captured["worker"] = (name, settings.batch_size, db, telemetry)

        async def run_once(self, *, now_ms):
            captured["now_ms"] = now_ms
            return SimpleNamespace(
                notes={
                    "result": {
                        "selected": 0,
                        "ready": 0,
                        "missing": 0,
                        "unsupported": 0,
                        "error": 0,
                        "with_logo": 0,
                        "source_provider": {},
                        "started_at_ms": now_ms,
                        "finished_at_ms": now_ms,
                    }
                }
            )

        async def aclose(self):
            captured["closed_worker"] = True

    def fail_wire_asset_market_providers(*_args, **_kwargs):
        raise AssertionError("rebuild-token-profiles must not wire asset providers")

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db", llm=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fail_wire_asset_market_providers)
    monkeypatch.setattr(ops_module, "TokenProfileCurrentWorker", FakeWorker)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(["ops", "rebuild-token-profiles", "--limit", "3"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["worker"][0] == "token_profile_current"
    assert captured["worker"][1] == 3
    assert captured["closed_worker"] is True
    assert closed == ["api", "worker", "tool", "wake"]
    assert payload["data"]["unsupported"] == 0


def test_cli_ops_mirror_token_images_is_db_only_and_closes_db(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured: dict[str, object] = {}
    closed: list[str] = []

    @contextmanager
    def fake_repositories(_settings):
        raise AssertionError("mirror-token-images must not hold an outer repository session")

    class FakePool:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    class FakeDB:
        api_pool = FakePool("api")
        worker_pool = FakePool("worker")
        tool_pool = FakePool("tool")
        wake_pool = FakePool("wake")

        async def aclose(self):
            self.api_pool.close()
            self.worker_pool.close()
            self.tool_pool.close()
            self.wake_pool.close()

    class FakeWorker:
        def __init__(self, *, name, settings, db, telemetry, app_home):
            captured["worker"] = (name, settings.batch_size, db, telemetry, app_home)

        async def run_once(self, *, now_ms):
            captured["now_ms"] = now_ms
            return SimpleNamespace(
                notes={
                    "result": {
                        "selected": 9,
                        "pending_upserted": 8,
                        "ready_existing": 1,
                        "claimed": 3,
                        "mirrored": 2,
                        "error": 1,
                        "unsupported": 0,
                        "started_at_ms": now_ms,
                        "finished_at_ms": now_ms,
                    }
                }
            )

        async def aclose(self):
            captured["closed_worker"] = True

    def fail_wire_asset_market_providers(*_args, **_kwargs):
        raise AssertionError("mirror-token-images must not wire asset providers")

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db", llm=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fail_wire_asset_market_providers)
    monkeypatch.setattr(ops_module, "TokenImageMirrorWorker", FakeWorker)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(["ops", "mirror-token-images", "--limit", "3"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["worker"][0] == "token_image_mirror"
    assert captured["worker"][1] == 3
    assert captured["closed_worker"] is True
    assert closed == ["api", "worker", "tool", "wake"]
    assert payload["data"]["mirrored"] == 2


def test_cli_ops_repair_token_profile_images_enqueues_profiles_then_runs_worker(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    captured: dict[str, object] = {"events": []}
    closed: list[str] = []

    @contextmanager
    def fake_repositories(_settings):
        raise AssertionError("repair-token-profile-images must not hold an outer repository session")

    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "target_type": "Asset",
                    "target_id": "asset:gmgn",
                    "source_watermark_ms": 1_699_999_999_000,
                },
                {
                    "target_type": "CexToken",
                    "target_id": "cex_token:BTC",
                    "source_watermark_ms": 1_700_000_000_000,
                },
            ]

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            captured["events"].append("select")
            return FakeCursor()

    class FakeTransaction:
        def __enter__(self):
            captured["events"].append("transaction_start")

        def __exit__(self, exc_type, exc, tb):
            captured["events"].append("transaction_commit")
            return False

    class FakeProfileDirtyTargets:
        def enqueue_targets(self, targets, *, reason, now_ms, commit):
            captured["events"].append("enqueue_profiles")
            captured["enqueued"] = {
                "targets": list(targets),
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
            return {"targets": len(captured["enqueued"]["targets"])}

    class FailingImageSourceDirtyTargets:
        def enqueue_targets(self, *_args, **_kwargs):
            raise AssertionError("repair-token-profile-images must not enqueue image source dirty targets")

    class FakeRepos:
        conn = FakeConn()
        token_profile_current_dirty_targets = FakeProfileDirtyTargets()
        token_image_source_dirty_targets = FailingImageSourceDirtyTargets()

        def transaction(self):
            return FakeTransaction()

    class FakePool:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    class FakeDB:
        api_pool = FakePool("api")
        worker_pool = FakePool("worker")
        tool_pool = FakePool("tool")
        wake_pool = FakePool("wake")

        @contextmanager
        def worker_session(self, name):
            captured["worker_session_name"] = name
            yield FakeRepos()

        async def aclose(self):
            self.api_pool.close()
            self.worker_pool.close()
            self.tool_pool.close()
            self.wake_pool.close()

    class FakeWorker:
        def __init__(self, *, name, settings, db, telemetry):
            captured["events"].append("worker_init")
            captured["worker"] = (name, settings.batch_size, db, telemetry)

        async def run_once(self, *, now_ms):
            captured["events"].append("worker_run")
            captured["worker_now_ms"] = now_ms
            return SimpleNamespace(notes={"result": {"selected": 2, "ready": 2, "with_logo": 1}})

        async def aclose(self):
            captured["events"].append("worker_close")

    def fail_wire_asset_market_providers(*_args, **_kwargs):
        raise AssertionError("repair-token-profile-images must not wire asset providers")

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db", llm=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fail_wire_asset_market_providers)
    monkeypatch.setattr(ops_module, "TokenProfileCurrentWorker", FakeWorker)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(["ops", "repair-token-profile-images", "--limit", "3"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert captured["worker_session_name"] == "token_profile_image_repair"
    assert "FROM token_profile_current" in captured["sql"]
    assert "status = 'ready'" in captured["sql"]
    assert "quality_flags_json ? 'logo_mirror_pending'" in captured["sql"]
    assert "quality_flags_json ? 'source_not_admitted'" in captured["sql"]
    assert "quality_flags_json ? 'logo_mirror_unsupported'" in captured["sql"]
    assert "quality_flags_json ? 'logo_mirror_failed'" in captured["sql"]
    assert captured["params"] == (3,)
    assert captured["enqueued"] == {
        "targets": [
            {
                "target_type": "Asset",
                "target_id": "asset:gmgn",
                "source_watermark_ms": 1_699_999_999_000,
                "priority": 25,
            },
            {
                "target_type": "CexToken",
                "target_id": "cex_token:BTC",
                "source_watermark_ms": 1_700_000_000_000,
                "priority": 25,
            },
        ],
        "reason": "token_profile_image_repair",
        "now_ms": 1_700_000_000_000,
        "commit": False,
    }
    assert captured["worker"][0] == "token_profile_current"
    assert captured["worker"][1] == 3
    assert captured["events"] == [
        "transaction_start",
        "select",
        "enqueue_profiles",
        "transaction_commit",
        "worker_init",
        "worker_run",
        "worker_close",
    ]
    assert closed == ["api", "worker", "tool", "wake"]
    assert payload["data"] == {
        "selected_targets": 2,
        "profile_targets_enqueued": 2,
        "profile_rebuild": {"selected": 2, "ready": 2, "with_logo": 1},
    }


def test_cli_ops_repair_token_profile_images_closes_db_when_worker_close_fails(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    closed: list[str] = []

    class FakeCursor:
        def fetchall(self):
            return []

    class FakeConn:
        def execute(self, *_args, **_kwargs):
            return FakeCursor()

    class FakeTransaction:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeProfileDirtyTargets:
        def enqueue_targets(self, targets, *, reason, now_ms, commit):
            return {"targets": len(list(targets))}

    class FakeRepos:
        conn = FakeConn()
        token_profile_current_dirty_targets = FakeProfileDirtyTargets()

        def transaction(self):
            return FakeTransaction()

    class FakePool:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    class FakeDB:
        api_pool = FakePool("api")
        worker_pool = FakePool("worker")
        tool_pool = FakePool("tool")
        wake_pool = FakePool("wake")

        @contextmanager
        def worker_session(self, _name):
            yield FakeRepos()

        async def aclose(self):
            self.api_pool.close()
            self.worker_pool.close()
            self.tool_pool.close()
            self.wake_pool.close()

    class FakeWorker:
        def __init__(self, *, name, settings, db, telemetry):
            pass

        async def run_once(self, *, now_ms):
            return SimpleNamespace(notes={"result": {}})

        async def aclose(self):
            raise RuntimeError("worker close failed")

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db", llm=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "TokenProfileCurrentWorker", FakeWorker)

    with pytest.raises(RuntimeError, match="worker close failed"):
        ops_module._run_token_profile_image_repair_once(
            ops_module.load_settings(require_ws_token=False),
            limit=3,
            now_ms=1_700_000_000_000,
        )

    assert closed == ["api", "worker", "tool", "wake"]


def test_cli_ops_refresh_asset_profiles_closes_db_when_provider_wiring_fails(monkeypatch, tmp_path):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    closed: list[str] = []

    class FakePool:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    class FakeDB:
        def __init__(self) -> None:
            self.api_pool = FakePool("api")
            self.worker_pool = FakePool("worker")
            self.wake_pool = FakePool("wake")

        async def aclose(self):
            self.api_pool.close()
            self.worker_pool.close()
            self.wake_pool.close()

    def fake_wire_asset_market_providers(settings, *, start_collector):
        raise RuntimeError("provider wiring failed")

    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", lambda settings, *, telemetry: FakeDB())
    monkeypatch.setattr(ops_module, "wire_asset_market_providers", fake_wire_asset_market_providers)

    try:
        main(["ops", "refresh-asset-profiles"], stdout=io.StringIO())
    except RuntimeError as exc:
        assert str(exc) == "provider wiring failed"
    else:
        raise AssertionError("provider wiring failure should propagate")

    assert closed == ["api", "worker", "wake"]


def test_cli_ops_sync_gmgn_directory_emits_error_on_directory_failure(monkeypatch, tmp_path):
    import io
    import json

    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.integrations.gmgn.directory_client import GmgnDirectoryError

    def boom(*, client, repository, now_ms, max_pages):
        raise GmgnDirectoryError("Cloudflare 403")

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(ops_module, "_run_sync_gmgn_directory", boom)
    monkeypatch.setattr(ops_module, "GmgnDirectoryClient", FakeClient)
    write_runtime_config(tmp_path, db_path=tmp_path / ".parallax" / "postgres_test_db")
    conn = connect_postgres_test(read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()
    monkeypatch.setenv("HOME", str(tmp_path))

    stdout = io.StringIO()
    code = main(["ops", "sync-gmgn-directory"], stdout=stdout)

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "Cloudflare 403"}


if __name__ == "__main__":
    unittest.main()
