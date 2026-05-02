import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gmgn_twitter_intel.cli import main
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_event(
    event_id: str,
    received_at_ms: int | None = None,
    text: str = f"$PEPE mainnet base stablecoin {PEPE}",
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
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            watch_keywords=("mainnet",),
        )
        ingest.ingest_event(make_event("event-1"), is_watched=True)
    finally:
        conn.close()


class CliTests(unittest.TestCase):
    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            original_env = {
                "GMGN_TWITTER_HOME": str(Path(tmpdir) / "app-home"),
                "WS_TOKEN": "secret",
                "MONITOR_HANDLES": " @Toly, traderpow,toly ",
                "WATCH_KEYWORDS": "mainnet,listing",
            }
            with patch.dict("os.environ", original_env, clear=False):
                exit_code = main(["config"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["handles"], ["toly", "traderpow"])
        self.assertEqual(payload["data"]["handle_count"], 2)
        self.assertEqual(payload["data"]["watch_keywords"], ["mainnet", "listing"])
        self.assertTrue(payload["data"]["api"]["ws_token_configured"])
        self.assertTrue(payload["data"]["store"]["sqlite_path"].endswith("twitter_intel.sqlite3"))
        self.assertNotIn("embed" + "ding_dim", payload["data"]["store"])

    def test_recent_search_token_flow_keyword_flow_and_alerts_use_sqlite_runtime_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "twitter_intel.sqlite3"
            seed_sqlite(db_path)
            stdout = io.StringIO()
            env = {
                "SQLITE_PATH": str(db_path),
                "MONITOR_HANDLES": "toly",
                "WATCH_KEYWORDS": "mainnet",
            }
            with patch.dict(os.environ, env, clear=False):
                recent_code = main(["recent", "--limit", "5"], stdout=stdout)
                search_code = main(["search", "--symbol", "PEPE", "--limit", "5"], stdout=stdout)
                token_flow_code = main(["token-flow", "--window", "5m", "--limit", "5"], stdout=stdout)
                keyword_flow_code = main(["keyword-flow", "--window", "5m", "--limit", "5"], stdout=stdout)
                alerts_code = main(["account-alerts", "--window", "24h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([recent_code, search_code, token_flow_code, keyword_flow_code, alerts_code], [0, 0, 0, 0, 0])
        self.assertEqual(lines[0]["data"]["events"][0]["event_id"], "event-1")
        self.assertEqual(lines[1]["data"]["items"][0]["event"]["event_id"], "event-1")
        self.assertEqual(lines[2]["data"]["items"][0]["mention_count"], 1)
        self.assertEqual(lines[3]["data"]["items"][0]["keyword"], "mainnet")
        self.assertEqual(
            {item["alert_type"] for item in lines[4]["data"]["items"]},
            {"account_token", "account_keyword"},
        )

    def test_obsolete_runtime_commands_are_not_registered(self):
        parser_help = main(["embed"], stdout=io.StringIO())

        self.assertEqual(parser_help, 2)

    def test_ops_rebuild_windows_reconstructs_materialized_signal_windows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "twitter_intel.sqlite3"
            seed_sqlite(db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                conn.execute("DELETE FROM token_windows")
                conn.execute("DELETE FROM keyword_windows")
                conn.commit()
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch.dict(os.environ, {"SQLITE_PATH": str(db_path)}, clear=False):
                rebuild_code = main(["ops", "rebuild-windows", "--window", "5m"], stdout=stdout)
                flow_code = main(["token-flow", "--window", "5m", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([rebuild_code, flow_code], [0, 0])
        self.assertGreater(lines[0]["data"]["rebuilt"], 0)
        self.assertEqual(lines[1]["data"]["items"][0]["mention_count"], 1)


def test_recent_defaults_to_runtime_sqlite_store_without_ws_token(tmp_path, monkeypatch):
    app_home = tmp_path / "app-home"
    db_path = app_home / "twitter_intel.sqlite3"
    seed_sqlite(db_path)
    monkeypatch.setenv("GMGN_TWITTER_HOME", str(app_home))
    monkeypatch.delenv("WS_TOKEN", raising=False)
    monkeypatch.setenv("MONITOR_HANDLES", "toly")
    monkeypatch.setenv("WATCH_KEYWORDS", "mainnet")
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "event-1"


if __name__ == "__main__":
    unittest.main()
