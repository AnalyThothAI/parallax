import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gmgn_twitter_cli.cli import main
from gmgn_twitter_cli.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_cli.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_cli.storage.tweet_repository import TweetRepository


def make_event(
    event_id: str,
    received_at_ms: int = 1000,
    text: str = "hello 0x6982508145454ce325ddbe47a25d4ec3d2311933",
) -> TwitterEvent:
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
        author=Author(handle="toly", name="toly", avatar=None, followers=None, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw=None,
    )


class CliTests(unittest.TestCase):
    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            original_env = {
                "XDG_STATE_HOME": str(Path(tmpdir) / "state"),
                "WS_TOKEN": "secret",
                "MONITOR_HANDLES": " @Toly, traderpow,toly ",
                "EMBEDDING_DIM": "8",
            }
            with patch.dict("os.environ", original_env, clear=False):
                exit_code = main(["config"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["handles"], ["toly", "traderpow"])
        self.assertEqual(payload["data"]["handle_count"], 2)
        self.assertEqual(payload["data"]["store"]["embedding_dim"], 8)
        self.assertTrue(payload["data"]["api"]["ws_token_configured"])

    def test_recent_prints_json_envelope_from_lancedb_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "twitter_intel.lancedb"
            repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
            event = make_event("event-1", received_at_ms=int(time.time() * 1000))
            repo.insert_event(event)
            repo.mark_event_matched(event)
            repo.close()
            stdout = io.StringIO()

            exit_code = main(
                [
                    "recent",
                    "--store",
                    str(store_path),
                    "--ca",
                    "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "--limit",
                    "5",
                ],
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["events"][0]["event_id"], "event-1")

    def test_mindshare_prints_token_metrics_from_lancedb_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "twitter_intel.lancedb"
            repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
            event = make_event("event-1", received_at_ms=int(time.time() * 1000))
            repo.insert_event(event)
            repo.mark_event_matched(event)
            repo.close()
            stdout = io.StringIO()

            exit_code = main(
                [
                    "mindshare",
                    "--store",
                    str(store_path),
                    "--ca",
                    "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "--chain",
                    "eth",
                    "--window",
                    "24h",
                ],
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["mention_count"], 1)

    def test_ops_reprocess_entities_reports_processed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "twitter_intel.lancedb"
            repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
            event = make_event("event-1", received_at_ms=int(time.time() * 1000))
            repo.insert_event(event)
            repo.mark_event_matched(event)
            repo.close()
            stdout = io.StringIO()

            exit_code = main(["ops", "reprocess-entities", "--store", str(store_path), "--limit", "10"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["processed"], 1)

    def test_embed_infers_existing_store_embedding_dimension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "twitter_intel.lancedb"
            repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
            event = make_event("event-1", received_at_ms=int(time.time() * 1000))
            repo.insert_event(event)
            repo.mark_event_matched(event)
            repo.close()
            stdout = io.StringIO()

            exit_code = main(["embed", "--store", str(store_path), "--limit", "10"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["processed"], 1)

    def test_search_accepts_explicit_symbol_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "twitter_intel.lancedb"
            repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
            event = make_event(
                "event-1",
                received_at_ms=int(time.time() * 1000),
                text="$PEPE 0x6982508145454ce325ddbe47a25d4ec3d2311933",
            )
            repo.insert_event(event)
            repo.mark_event_matched(event)
            repo.close()
            stdout = io.StringIO()

            exit_code = main(["search", "--store", str(store_path), "--symbol", "PEPE"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["query"]["kind"], "symbol")
        self.assertEqual(payload["data"]["query"]["symbol"], "PEPE")
        self.assertEqual(payload["data"]["items"][0]["event"]["event_id"], "event-1")


def test_recent_defaults_to_runtime_event_store(tmp_path, monkeypatch):
    state_home = tmp_path / "state"
    store_path = state_home / "gmgn-twitter-cli" / "twitter_intel.lancedb"
    repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=8))
    repo.insert_event(make_event("configured-event"))
    repo.mark_event_matched(make_event("configured-event"))
    repo.close()
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("WS_TOKEN", "secret")
    monkeypatch.setenv("MONITOR_HANDLES", "toly")
    monkeypatch.setenv("EMBEDDING_DIM", "8")
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "configured-event"


if __name__ == "__main__":
    unittest.main()
