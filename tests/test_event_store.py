import tempfile
import unittest
from pathlib import Path

from gmgn_twitter_cli.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_cli.store.sqlite import EventStore


def make_event(event_id: str, handle: str, received_at_ms: int = 1000) -> TwitterEvent:
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
        tweet_id="tweet-1",
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=handle, name=handle, avatar=None, followers=None, tags=[]),
        content=Content(text="hello", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[handle],
        raw={"i": event_id},
    )


class EventStoreTests(unittest.TestCase):
    def test_observed_and_matched_events_are_separate_idempotent_streams(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir) / "events.sqlite3")
            first_observed = store.insert_observed_event(make_event("event-1", "toly", 1000))
            duplicate_observed = store.insert_observed_event(make_event("event-1", "toly", 1000))
            first_matched = store.insert_matched_event(make_event("event-1", "toly", 1000))
            duplicate_matched = store.insert_matched_event(make_event("event-1", "toly", 1000))
            store.insert_observed_event(make_event("event-2", "elonmusk", 2000))
            store.insert_matched_event(make_event("event-2", "elonmusk", 2000))

            recent = store.recent_events(limit=10)
            counts = store.event_counts()
            store.close()

        self.assertTrue(first_observed)
        self.assertFalse(duplicate_observed)
        self.assertTrue(first_matched)
        self.assertFalse(duplicate_matched)
        self.assertEqual(counts, {"observed_events": 2, "matched_events": 2})
        self.assertEqual([event["event_id"] for event in recent], ["event-2", "event-1"])

    def test_recent_events_replays_only_matched_events_and_can_filter_by_handles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir) / "events.sqlite3")
            store.insert_observed_event(make_event("event-1", "toly", 1000))
            store.insert_observed_event(make_event("event-2", "elonmusk", 2000))
            store.insert_matched_event(make_event("event-1", "toly", 1000))

            all_recent = store.recent_events(limit=10)
            filtered = store.recent_events(limit=10, handles={"toly"})
            store.close()

        self.assertEqual([event["author"]["handle"] for event in all_recent], ["toly"])
        self.assertEqual([event["author"]["handle"] for event in filtered], ["toly"])

    def test_backfill_matches_promotes_existing_observed_events_for_new_handles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir) / "events.sqlite3")
            store.insert_observed_event(make_event("event-1", "toly", 1000))
            store.insert_observed_event(make_event("event-2", "elonmusk", 2000))

            backfilled = store.backfill_matches(handles={"elonmusk"})
            recent = store.recent_events(limit=10)
            counts = store.event_counts()
            store.close()

        self.assertEqual(backfilled, 1)
        self.assertEqual(counts, {"observed_events": 2, "matched_events": 1})
        self.assertEqual([event["author"]["handle"] for event in recent], ["elonmusk"])

    def test_store_schema_does_not_keep_legacy_events_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir) / "events.sqlite3")
            table_names = store.table_names()
            store.close()

        self.assertEqual(table_names, ["matched_events", "observed_events"])

    def test_store_drops_legacy_events_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "events.sqlite3"
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute("create table events (event_id text primary key)")
            conn.commit()
            conn.close()

            store = EventStore(db_path)
            table_names = store.table_names()
            store.close()

        self.assertEqual(table_names, ["matched_events", "observed_events"])


if __name__ == "__main__":
    unittest.main()
