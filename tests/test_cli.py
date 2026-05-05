import io
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from threading import RLock
from unittest.mock import patch

import yaml

from gmgn_twitter_intel.cli import main
from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.market_observation_repository import MarketObservationRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository

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


def seed_sqlite(db_path: Path) -> None:
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        enrichment = EnrichmentRepository(conn)
        tokens = TokenRepository(conn)
        observations = MarketObservationRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
            market_observations=observations,
            write_lock=RLock(),
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
    finally:
        conn.close()


def write_runtime_config(home: Path, *, db_path: Path, ws_token: str | None = None, llm: bool = False) -> Path:
    app_home = home / ".gmgn-twitter-intel"
    app_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "handles": ["toly", "traderpow"],
        "storage": {"sqlite_path": str(db_path)},
    }
    if ws_token is not None:
        payload["ws_token"] = ws_token
    if llm:
        payload["llm"] = {"provider": "openai", "api_key": "sk-test", "model": "gpt-test"}
    path = app_home / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


class CliTests(unittest.TestCase):
    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
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
        self.assertTrue(payload["data"]["store"]["sqlite_path"].endswith("twitter_intel.sqlite3"))
        self.assertNotIn("embed" + "ding_dim", payload["data"]["store"])

    def test_recent_search_token_flow_harness_and_alerts_use_sqlite_runtime_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            seed_sqlite(db_path)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                recent_code = main(["recent", "--limit", "5"], stdout=stdout)
                search_code = main(["search", "--symbol", "PEPE", "--limit", "5"], stdout=stdout)
                token_flow_code = main(
                    ["token-flow", "--window", "5m", "--limit", "5", "--scope", "all"],
                    stdout=stdout,
                )
                freeze_code = main(
                    ["ops", "freeze-token-signals", "--window", "5m", "--limit", "5", "--scope", "all"],
                    stdout=stdout,
                )
                token_signal_snapshots_code = main(
                    ["token-signal-snapshots", "--window", "5m", "--limit", "5", "--scope", "all"],
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
                token_flow_code,
                freeze_code,
                token_signal_snapshots_code,
                alerts_code,
                jobs_code,
                social_events_code,
                seeds_code,
                snapshots_code,
            ],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(lines[0]["data"]["events"][0]["event_id"], "event-1")
        self.assertEqual(lines[1]["data"]["items"][0]["event"]["event_id"], "event-1")
        self.assertEqual(lines[2]["data"]["scope"], "all")
        self.assertEqual(lines[3]["data"]["snapshots_written"], 1)
        self.assertEqual(lines[4]["data"]["items"][0]["score_versions"]["opportunity"], "social_opportunity_v2")
        self.assertEqual(lines[2]["data"]["items"][0]["flow"]["mentions"], 1)
        self.assertEqual(lines[2]["data"]["items"][0]["opportunity"]["decision"], "watch")
        self.assertEqual(
            {item["alert_type"] for item in lines[5]["data"]["items"]},
            {"account_token"},
        )
        self.assertEqual(lines[6]["data"]["counts"]["pending"], 1)
        self.assertEqual(lines[7]["data"]["items"], [])
        self.assertEqual(lines[8]["data"]["items"], [])
        self.assertEqual(lines[9]["data"]["items"], [])

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
        ]
        for command in obsolete_commands:
            self.assertEqual(main(command, stdout=io.StringIO()), 2)

    def test_token_signal_settlement_cli_commands_return_empty_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                settle_code = main(
                    ["ops", "settle-token-signals", "--horizon", "6h", "--limit", "5"],
                    stdout=stdout,
                )
                outcomes_code = main(["token-signal-outcomes", "--horizon", "6h", "--limit", "5"], stdout=stdout)
                evaluations_code = main(
                    ["token-signal-evaluations", "--horizon", "6h", "--window", "5m", "--scope", "all"],
                    stdout=stdout,
                )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([settle_code, outcomes_code, evaluations_code], [0, 0, 0])
        self.assertEqual(lines[0]["data"]["snapshots_scanned"], 0)
        self.assertEqual(lines[1]["data"]["items"], [])
        self.assertEqual(lines[2]["data"]["buckets"][0]["snapshot_count"], 0)

    def test_ops_rebuild_attributions_materializes_existing_symbol_mentions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                migrate(conn)
                evidence = EvidenceRepository(conn)
                entities = EntityRepository(conn)
                signals = SignalRepository(conn)
                enrichment = EnrichmentRepository(conn)
                tokens = TokenRepository(conn)
                ingest = IngestService(
                    evidence=evidence,
                    entities=entities,
                    signals=signals,
                    enrichment=enrichment,
                    tokens=tokens,
                    write_lock=RLock(),
                )
                base_ms = int(time.time() * 1000) - 10_000
                ingest.ingest_event(
                    make_event("event-dog-symbol", received_at_ms=base_ms, text="$DOG early"),
                    is_watched=True,
                )
                snapshot = parse_gmgn_token_payload(
                    {
                        "tt": "ca",
                        "t": {
                            "a": PEPE,
                            "c": "eth",
                            "mc": "60490.341996",
                            "p": "1.0",
                            "s": "DOG",
                            "liquidity": "250000",
                            "holder_count": 10000,
                            "pool": {"pool_address": "pool-dog"},
                        },
                    }
                )
                ingest.ingest_event(
                    replace(
                        make_event("event-dog-token", received_at_ms=base_ms + 1_000, text="$DOG payload"),
                        source=Source(
                            provider="gmgn",
                            transport="direct_ws",
                            coverage="public_stream",
                            channel="twitter_monitor_token",
                        ),
                        token_snapshot=snapshot,
                    ),
                    is_watched=False,
                )
                conn.execute("DELETE FROM event_token_attributions")
                conn.commit()
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                rebuild_code = main(["ops", "rebuild-attributions", "--symbol", "DOG"], stdout=stdout)
                flow_code = main(["token-flow", "--window", "24h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([rebuild_code, flow_code], [0, 0])
        self.assertEqual(lines[0]["data"]["symbol"], "DOG")
        self.assertEqual(lines[0]["data"]["direct_mentions_scanned"], 1)
        self.assertEqual(lines[0]["data"]["symbol_mentions_scanned"], 1)
        self.assertEqual(lines[1]["data"]["items"][0]["flow"]["mentions"], 2)
        self.assertEqual(lines[1]["data"]["items"][0]["flow"]["symbol_mentions"], 1)

    def test_market_observations_cli_lists_counts_and_backfills_missing_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                migrate(conn)
                evidence = EvidenceRepository(conn)
                entities = EntityRepository(conn)
                signals = SignalRepository(conn)
                enrichment = EnrichmentRepository(conn)
                tokens = TokenRepository(conn)
                ingest = IngestService(
                    evidence=evidence,
                    entities=entities,
                    signals=signals,
                    enrichment=enrichment,
                    tokens=tokens,
                    write_lock=RLock(),
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
                ingest.ingest_event(
                    replace(
                        make_event("event-market-backfill"),
                        source=Source(
                            provider="gmgn",
                            transport="direct_ws",
                            coverage="public_stream",
                            channel="twitter_monitor_token",
                        ),
                        token_snapshot=snapshot,
                    ),
                    is_watched=True,
                )
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                before_code = main(["market-observations", "--status", "pending", "--limit", "5"], stdout=stdout)
                backfill_code = main(["ops", "backfill-market-observations", "--limit", "5"], stdout=stdout)
                after_code = main(["market-observations", "--status", "pending", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([before_code, backfill_code, after_code], [0, 0, 0])
        self.assertEqual(lines[0]["data"]["items"], [])
        self.assertEqual(lines[1]["data"]["rows_scanned"], 1)
        self.assertEqual(lines[1]["data"]["observations_enqueued"], 1)
        self.assertEqual(lines[2]["data"]["counts"]["pending"], 1)
        self.assertEqual(lines[2]["data"]["items"][0]["event_id"], "event-market-backfill")

def test_recent_defaults_to_runtime_sqlite_store_without_ws_token(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    db_path = app_home / "twitter_intel.sqlite3"
    write_runtime_config(tmp_path, db_path=db_path)
    seed_sqlite(db_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "event-1"


def test_harness_cli_reports_empty_read_models_without_error(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    db_path = app_home / "twitter_intel.sqlite3"
    write_runtime_config(tmp_path, db_path=db_path)
    conn = connect_sqlite(db_path, read_only=False)
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


if __name__ == "__main__":
    unittest.main()
