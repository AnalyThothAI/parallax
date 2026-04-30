from pathlib import Path

from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.embedding import HashEmbeddingBackend, embed_pending_tweets
from gmgn_twitter_intel.retrieval.search_service import SearchService
from gmgn_twitter_intel.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_intel.storage.tweet_repository import TweetRepository


def make_event(event_id: str, text: str, received_at_ms: int = 1000) -> TwitterEvent:
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


def build_repo(tmp_path: Path) -> TweetRepository:
    repo = TweetRepository(build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=16))
    for event in [
        make_event("event-ca", "$PEPE exact ca 0x6982508145454ce325ddbe47a25d4ec3d2311933", 3000),
        make_event("event-tokenless", "whale buy listing rumor gaining traction", 2000),
        make_event("event-other", "quiet timeline", 1000),
    ]:
        repo.insert_event(event)
        repo.mark_event_matched(event)
    return repo


def test_search_exact_ca_ranks_above_semantic_matches(tmp_path):
    repo = build_repo(tmp_path)
    embed_pending_tweets(repo, HashEmbeddingBackend(dimension=16), limit=10)

    results = SearchService(repo, HashEmbeddingBackend(dimension=16)).search(
        "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        limit=5,
    )

    assert results.ok
    assert results.query == {
        "kind": "ca",
        "text": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "scope": "all",
        "ca": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
        "chain": "eth",
    }
    assert results.items[0]["event"]["event_id"] == "event-ca"
    assert results.items[0]["match_type"] == "exact_ca"
    repo.close()


def test_search_returns_tokenless_tweets_for_semantic_text(tmp_path):
    repo = build_repo(tmp_path)
    embed_pending_tweets(repo, HashEmbeddingBackend(dimension=16), limit=10)

    results = SearchService(repo, HashEmbeddingBackend(dimension=16)).search("whale listing rumor", limit=5)

    assert results.ok
    assert results.query == {"kind": "text", "text": "whale listing rumor", "scope": "all"}
    assert results.items[0]["event"]["event_id"] == "event-tokenless"
    assert results.items[0]["event"]["token_resolution_status"] == "no_token"
    repo.close()


def test_search_defaults_to_all_events_and_can_scope_to_matched_only(tmp_path):
    repo = TweetRepository(build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=16))
    repo.insert_event(make_event("public-ca", "$PEPE 0x6982508145454ce325ddbe47a25d4ec3d2311933", 3000))

    all_results = SearchService(repo, HashEmbeddingBackend(dimension=16)).search(
        "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        limit=5,
    )
    matched_results = SearchService(repo, HashEmbeddingBackend(dimension=16)).search(
        "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        limit=5,
        scope="matched",
    )

    assert all_results.items[0]["event"]["event_id"] == "public-ca"
    assert all_results.query["scope"] == "all"
    assert matched_results.items == []
    assert matched_results.query["scope"] == "matched"
    repo.close()


def test_embedding_processor_only_updates_pending_rows(tmp_path):
    repo = build_repo(tmp_path)

    processed = embed_pending_tweets(repo, HashEmbeddingBackend(dimension=16), limit=10)
    pending_after = repo.client.count_where("twitter_events", where="embedding_status = 'pending'")

    assert processed == 2
    assert pending_after == 0
    repo.close()
