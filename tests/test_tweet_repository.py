import tempfile
import unittest
from pathlib import Path

from gmgn_twitter_cli.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_cli.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_cli.storage.tweet_repository import TweetRepository


def make_event(
    event_id: str,
    handle: str,
    received_at_ms: int = 1000,
    text: str = "hello",
    tweet_id: str | None = None,
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
        tweet_id=tweet_id or event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=handle, name=handle, avatar=None, followers=None, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[handle],
        raw={"i": event_id},
    )


class TweetRepositoryTests(unittest.TestCase):
    def test_events_are_stored_once_and_matched_by_flag_not_copy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = TweetRepository(build_lancedb_client(Path(tmpdir) / "twitter_intel.lancedb", embedding_dim=8))
            first_event = repo.insert_event(make_event("event-1", "toly", 1000))
            duplicate_event = repo.insert_event(make_event("event-1", "toly", 1000))
            first_match = repo.mark_event_matched(make_event("event-1", "toly", 1000))
            duplicate_match = repo.mark_event_matched(make_event("event-1", "toly", 1000))
            repo.insert_event(make_event("event-2", "elonmusk", 2000))
            repo.mark_event_matched(make_event("event-2", "elonmusk", 2000))

            recent = repo.recent_events(limit=10)
            counts = repo.event_counts()
            repo.close()

        self.assertTrue(first_event)
        self.assertFalse(duplicate_event)
        self.assertTrue(first_match)
        self.assertFalse(duplicate_match)
        self.assertEqual(counts, {"twitter_events": 2, "matched_twitter_events": 2, "tweet_entities": 0})
        self.assertEqual([event["event_id"] for event in recent], ["event-2", "event-1"])

    def test_recent_events_replays_only_matched_events_and_can_filter_by_handles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = TweetRepository(build_lancedb_client(Path(tmpdir) / "twitter_intel.lancedb", embedding_dim=8))
            repo.insert_event(make_event("event-1", "toly", 1000))
            repo.insert_event(make_event("event-2", "elonmusk", 2000))
            repo.mark_event_matched(make_event("event-1", "toly", 1000))

            all_recent = repo.recent_events(limit=10)
            filtered = repo.recent_events(limit=10, handles={"toly"})
            empty = repo.recent_events(limit=10, handles={"elonmusk"})
            repo.close()

        self.assertEqual([event["author"]["handle"] for event in all_recent], ["toly"])
        self.assertEqual([event["author"]["handle"] for event in filtered], ["toly"])
        self.assertEqual(empty, [])

    def test_store_schema_is_lancedb_first_without_sqlite_compat_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = TweetRepository(build_lancedb_client(Path(tmpdir) / "twitter_intel.lancedb", embedding_dim=8))
            table_names = repo.table_names()
            repo.close()

        self.assertEqual(
            table_names,
            [
                "llm_claims",
                "llm_entities",
                "llm_relations",
                "llm_runs",
                "raw_frames",
                "token_registry",
                "token_social_windows",
                "tweet_entities",
                "twitter_events",
            ],
        )

    def test_insert_event_rejects_duplicate_logical_tweet_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = TweetRepository(build_lancedb_client(Path(tmpdir) / "twitter_intel.lancedb", embedding_dim=8))

            first = repo.insert_event(make_event("event-1", "toly", 1000, tweet_id="tweet-1"))
            duplicate = repo.insert_event(make_event("event-2", "toly", 2000, tweet_id="tweet-1"))
            counts = repo.event_counts()
            repo.close()

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual(counts["twitter_events"], 1)

    def test_insert_event_extracts_entities_and_filters_recent_events_by_ca(self):
        ca = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
        event = make_event("event-1", "toly", 1000, text=f"$PEPE is moving {ca}")
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = TweetRepository(build_lancedb_client(Path(tmpdir) / "twitter_intel.lancedb", embedding_dim=8))
            repo.insert_event(event)
            repo.mark_event_matched(event)

            recent = repo.recent_events(limit=10, ca=ca, chain="eth")
            counts = repo.event_counts()
            repo.close()

        self.assertEqual([item["event_id"] for item in recent], ["event-1"])
        self.assertEqual(recent[0]["token_resolution_status"], "resolved")
        self.assertEqual(recent[0]["cashtags"], ["PEPE"])
        self.assertEqual(counts["tweet_entities"], 2)


if __name__ == "__main__":
    unittest.main()
