from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.retrieval.mindshare_service import MindshareService
from gmgn_twitter_intel.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_intel.storage.social_repository import SocialRepository
from gmgn_twitter_intel.storage.tweet_repository import TweetRepository

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
DOGE = "0xba2ae424d960c26247dd6c32edc70b295c744c43"


def make_event(event_id: str, text: str, handle: str, followers: int, received_at_ms: int) -> TwitterEvent:
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
        author=Author(handle=handle, name=handle, avatar=None, followers=followers, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[handle],
        raw=None,
    )


def seed_repo(tmp_path):
    repo = TweetRepository(build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8))
    for event in [
        make_event("pepe-1", f"$PEPE first {PEPE} #launch", "alice", 1000, 3_600_000),
        make_event("pepe-2", f"$PEPE second {PEPE} #launch", "bob", 100, 3_500_000),
        make_event("doge-1", f"$DOGE other {DOGE}", "carol", 10, 3_400_000),
        make_event("tokenless", "whale rumor no ca", "dan", 9999, 3_300_000),
        make_event("pepe-prev", f"$PEPE old {PEPE}", "alice", 1000, 50_000),
    ]:
        repo.insert_event(event)
        repo.mark_event_matched(event)
    return repo


def test_mindshare_by_ca_excludes_tokenless_tweets_and_computes_metrics(tmp_path):
    repo = seed_repo(tmp_path)
    service = MindshareService(repo, SocialRepository(repo.client))

    result = service.mindshare(ca=PEPE, chain="eth", window="1h", now_ms=3_700_000)

    assert result["ok"]
    assert result["data"]["mention_count"] == 2
    assert result["data"]["unique_authors"] == 2
    assert result["data"]["share_of_voice"] == 0.666667
    assert result["data"]["velocity"] == 1.0
    assert "public_stream_coverage" in result["data"]["quality_flags"]
    assert result["data"]["top_authors"][0]["handle"] == "alice"
    repo.close()


def test_mindshare_symbol_returns_ambiguity_candidates(tmp_path):
    repo = seed_repo(tmp_path)
    other = "0x6982508145454ce325ddbe47a25d4ec3d2311934"
    event = make_event("pepe-other", f"$PEPE other ca {other}", "eve", 10, 3_600_000)
    repo.insert_event(event)
    repo.mark_event_matched(event)
    service = MindshareService(repo, SocialRepository(repo.client))

    result = service.mindshare(symbol="PEPE", window="1h", now_ms=3_700_000)

    assert not result["ok"]
    assert result["error"] == "ambiguous_symbol"
    assert len(result["candidates"]) == 2
    repo.close()
