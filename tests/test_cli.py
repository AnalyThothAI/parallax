import io
import json
import tempfile
import unittest
from pathlib import Path

from gmgn_twitter_cli.cli import main
from gmgn_twitter_cli.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_cli.store.sqlite import EventStore


def make_event(event_id: str) -> TwitterEvent:
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
        timestamp=1,
        received_at_ms=1000,
        author=Author(handle="toly", name="toly", avatar=None, followers=None, tags=[]),
        content=Content(text="hello", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw=None,
    )


class CliTests(unittest.TestCase):
    def test_recent_prints_json_envelope_from_sqlite_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "events.sqlite3"
            store = EventStore(db_path)
            store.insert_observed_event(make_event("event-1"))
            store.insert_matched_event(make_event("event-1"))
            store.close()
            stdout = io.StringIO()

            exit_code = main(["recent", "--db", str(db_path), "--limit", "5"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["events"][0]["event_id"], "event-1")


def test_recent_defaults_to_runtime_event_store(tmp_path, monkeypatch):
    state_home = tmp_path / "state"
    db_path = state_home / "gmgn-twitter-cli" / "events.sqlite3"
    store = EventStore(db_path)
    store.insert_observed_event(make_event("configured-event"))
    store.insert_matched_event(make_event("configured-event"))
    store.close()
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("WS_TOKEN", "secret")
    monkeypatch.setenv("MONITOR_HANDLES", "toly")
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "configured-event"


if __name__ == "__main__":
    unittest.main()
