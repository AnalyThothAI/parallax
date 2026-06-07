from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker, _source_fetch_since_ms
from parallax.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from parallax.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from parallax.domains.token_intel.interfaces import TokenIdentityLookupResult

NOW_MS = 1_779_000_000_000


def test_news_fetch_worker_fetches_outside_db_session_and_writes_items() -> None:
    source = {
        "source_id": "example-rss",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
        "etag": "old-etag",
        "last_modified": "old-modified",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            etag="new-etag",
            last_modified="new-modified",
            observations=[
                NewsProviderObservation(
                    source_item_key="guid-1",
                    canonical_url="https://example.com/news/story",
                    title="SOL ETF approved",
                    summary="Issuer confirms launch.",
                    body_text="Issuer confirms launch.",
                    language="en",
                    published_at_ms=NOW_MS,
                    raw_payload={
                        "id": "guid-1",
                        "link": "https://example.com/news/story?utm_source=rss",
                        "title": "SOL ETF approved",
                        "summary": "Issuer confirms launch.",
                        "source_domain": "example.com",
                    },
                    provider_signal={"source": "provider", "provider": "opennews", "status": "ready"},
                    provider_token_impacts=[{"symbol": "SOL", "score": 70, "signal": "long"}],
                )
            ],
        ),
    )
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, feed_client=feed, wake_bus=wake_bus, sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.failed == 0
    assert db.max_open_sessions == 1
    assert feed.calls == [
        {
            "source_id": "example-rss",
            "provider_type": "rss",
            "feed_url": "https://example.com/rss.xml",
            "cache": NewsSourceHttpCache(etag="old-etag", last_modified="old-modified"),
            "since_ms": None,
            "cursor": {},
            "limit": 10,
        }
    ]
    assert db.repo.reconciled_sources == [source]
    assert db.repo.provider_items[0]["source_item_key"] == "guid-1"
    assert db.repo.provider_items[0]["canonical_url"] == "https://example.com/news/story"
    assert db.repo.news_items[0]["title"] == "SOL ETF approved"
    assert db.repo.news_items[0]["provider_signal"] == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
    }
    assert db.repo.news_items[0]["provider_token_impacts"] == [{"symbol": "SOL", "score": 70, "signal": "long"}]
    assert db.repo.news_items[0]["canonical_identity"].canonical_item_key.startswith("canonical-url:")
    assert db.repo.cache_updates == [
        {
            "source_id": "example-rss",
            "etag": "new-etag",
            "last_modified": "new-modified",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert db.repo.finished_runs[0]["status"] == "success"
    assert db.repo.finished_runs[0]["fetched_count"] == 1
    assert db.repo.finished_runs[0]["inserted_count"] == 1
    assert wake_bus.notifications == [{"source_id": "example-rss", "count": 1}]


def test_news_fetch_worker_treats_not_modified_as_success_without_wake() -> None:
    source = {
        "source_id": "example-rss",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(db, NewsProviderFetchResult(status_code=304, not_modified=True, observations=[]))
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, feed_client=feed, wake_bus=wake_bus, sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 0
    assert db.repo.provider_items == []
    assert db.repo.news_items == []
    assert db.repo.finished_runs[0]["status"] == "success"
    assert db.repo.finished_runs[0]["fetched_count"] == 0
    assert wake_bus.notifications == []


def test_news_fetch_worker_passes_source_sync_cursor_and_updates_after_success() -> None:
    source = {
        "source_id": "opennews-realtime",
        "provider_type": "opennews",
        "feed_url": "opennews://subscribe",
        "source_domain": "6551.io",
        "source_name": "OpenNews",
    }
    db = FakeDB(FakeNewsRepository([source]))
    db.repo.sync_cursors["opennews-realtime"] = {"high_watermark_ms": NOW_MS - 60_000, "overlap_ms": 600_000}
    next_cursor = {
        "high_watermark_ms": NOW_MS - 1_000,
        "overlap_ms": 600_000,
        "pages_scanned": 2,
        "rest_received": 4,
        "oldest_seen_ms": NOW_MS - 120_000,
        "stop_reason": "empty_page",
    }
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            next_cursor=next_cursor,
            observations=[
                NewsProviderObservation(
                    source_item_key="2367422",
                    canonical_url="https://example.com/news/2367422",
                    title="BTC headline",
                    summary="OpenNews summary.",
                    body_text="OpenNews body.",
                    language="en",
                    published_at_ms=NOW_MS - 1_000,
                    raw_payload={"id": "2367422", "title": "BTC headline"},
                )
            ],
        ),
    )
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 0
    assert feed.calls[0]["since_ms"] == NOW_MS - 660_000
    assert feed.calls[0]["cursor"] == {"high_watermark_ms": NOW_MS - 60_000, "overlap_ms": 600_000}
    assert db.repo.sync_updates == [
        {
            "source_id": "opennews-realtime",
            "next_cursor": next_cursor,
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert db.repo.events.index("update_source_sync_state") < db.repo.events.index("finish_fetch_run")


def test_news_fetch_worker_does_not_bound_opennews_since_ms_to_brief_window_without_cursor() -> None:
    source = {
        "source_id": "opennews-realtime",
        "provider_type": "opennews",
        "feed_url": "opennews://subscribe",
        "source_domain": "6551.io",
        "source_name": "OpenNews",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(db, NewsProviderFetchResult(status_code=200, observations=[]))
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 0
    assert feed.calls[0]["since_ms"] is None


def test_opennews_fetch_since_uses_cursor_overlap_not_agent_brief_age() -> None:
    since_ms = _source_fetch_since_ms(
        source={
            "provider_type": "opennews",
            "fetch_policy_json": {"rest_overlap_ms": 900_000},
        },
        source_cursor={"high_watermark_ms": 10_000_000},
        now_ms=20_000_000,
    )

    assert since_ms == 9_100_000


def test_opennews_first_fetch_since_uses_optional_fetch_policy_catchup_only() -> None:
    assert (
        _source_fetch_since_ms(
            source={"provider_type": "opennews", "fetch_policy_json": {"max_initial_fetch_age_ms": 3_600_000}},
            source_cursor={},
            now_ms=20_000_000,
        )
        == 16_400_000
    )
    assert (
        _source_fetch_since_ms(
            source={"provider_type": "opennews", "fetch_policy_json": {}},
            source_cursor={},
            now_ms=20_000_000,
        )
        is None
    )


def test_news_fetch_worker_enqueues_dirty_targets_for_all_affected_news_items() -> None:
    source = {
        "source_id": "example-rss",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }
    db = FakeDB(FakeNewsRepository([source]))
    db.repo.news_results = [
        {
            "news_item_id": "news-new",
            "status": "updated",
            "affected_news_item_ids": ["news-old", "news-new"],
        }
    ]
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            observations=[
                NewsProviderObservation(
                    source_item_key="guid-1",
                    canonical_url="https://example.com/news/story",
                    title="Updated story",
                    summary="Summary",
                    body_text="Body",
                    language="en",
                    published_at_ms=NOW_MS,
                    raw_payload={"id": "guid-1", "title": "Updated story"},
                )
            ],
        ),
    )
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    worker.run_once_sync(now_ms=NOW_MS)

    news_item_written = next(batch for batch in db.dirty.enqueued if batch["reason"] == "news_item_written")
    assert news_item_written["rows"] == [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-old"},
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-new"},
    ]


def test_news_fetch_worker_does_not_enqueue_brief_input_for_provider_signal_update() -> None:
    source = {
        "source_id": "opennews-news",
        "provider_type": "opennews",
        "feed_url": "https://opennews.test/news",
        "source_domain": "opennews.test",
        "source_name": "OpenNews",
    }
    db = FakeDB(FakeNewsRepository([source]))
    db.repo.news_results = [
        {
            "news_item_id": "news-eligible",
            "status": "updated",
            "affected_news_item_ids": ["news-eligible"],
        }
    ]
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            observations=[
                NewsProviderObservation(
                    source_item_key="opennews-eligible",
                    canonical_url="https://opennews.test/eligible",
                    title="Eligible provider signal",
                    summary="Summary",
                    body_text="Body",
                    language="en",
                    published_at_ms=NOW_MS,
                    raw_payload={"id": "opennews-eligible", "title": "Eligible provider signal"},
                    provider_signal={"source": "provider", "provider": "opennews", "status": "ready", "score": 85},
                )
            ],
        ),
    )
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    worker.run_once_sync(now_ms=NOW_MS)

    news_item_written_rows = [
        row for batch in db.dirty.enqueued if batch["reason"] == "news_item_written" for row in batch["rows"]
    ]
    assert {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "news-eligible",
    } in news_item_written_rows
    assert all(row["projection_name"] != "brief_input" for row in news_item_written_rows)


def test_news_fetch_worker_passes_cryptopanic_source_context_to_feed_client() -> None:
    source = {
        "source_id": "cryptopanic-en",
        "provider_type": "cryptopanic",
        "feed_url": "cryptopanic://posts?regions=en&kind=news&max_items=50",
        "source_domain": "cryptopanic.com",
        "source_name": "CryptoPanic",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            observations=[
                NewsProviderObservation(
                    source_item_key="cryptopanic:32675220",
                    canonical_url="https://coincu.com/mastercard-acquires-bvnk/",
                    title="Mastercard Acquires BVNK",
                    summary="Crypto payments deal explained.",
                    body_text="Crypto payments deal explained.",
                    language="en",
                    published_at_ms=NOW_MS,
                    raw_payload={
                        "id": "cryptopanic:32675220",
                        "link": "https://coincu.com/mastercard-acquires-bvnk/",
                        "title": "Mastercard Acquires BVNK",
                        "summary": "Crypto payments deal explained.",
                        "source_domain": "cryptopanic.com",
                    },
                )
            ],
        ),
    )
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert feed.calls == [
        {
            "source_id": "cryptopanic-en",
            "provider_type": "cryptopanic",
            "feed_url": "cryptopanic://posts?regions=en&kind=news&max_items=50",
            "cache": NewsSourceHttpCache(etag=None, last_modified=None),
            "since_ms": None,
            "cursor": {},
            "limit": 10,
        }
    ]
    assert db.repo.provider_items[0]["source_item_key"] == "cryptopanic:32675220"


def test_news_item_process_worker_extracts_mentions_candidates_and_wakes() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {
            "event_types": ["exchange_listing"],
            "domains": ["coinbase.com"],
            "targets": [{"target_type": "CexToken", "target_id": "cex:BTC"}],
        },
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    wake_bus = FakeItemProcessWakeBus()
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=wake_bus,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.failed == 0
    assert db.max_open_sessions == 1
    assert db.repo.release_calls == [NOW_MS]
    assert db.repo.claim_calls == [
        {
            "limit": 10,
            "lease_owner": "news_item_process",
            "lease_ms": 120_000,
            "now_ms": NOW_MS,
        }
    ]
    assert db.repo.entities["news-1"][0].entity_type == "symbol"
    assert db.repo.mentions["news-1"][0].resolution_status == "known_symbol"
    assert db.repo.fact_candidates["news-1"][0].validation_status == "accepted"
    assert db.repo.content_classifications == [
        {
            "news_item_id": "news-1",
            "content_class": "exchange_listing",
            "content_tags": ["exchange_listing"],
            "classification_payload": {
                "policy_version": "news_content_classification_v1",
                "matched_rules": ["fact_event_type:exchange_listing"],
            },
            "now_ms": NOW_MS,
        }
    ]
    assert db.repo.market_scope_story_updates[0]["news_item_id"] == "news-1"
    assert db.repo.market_scope_story_updates[0]["market_scope"].primary == "crypto"
    assert db.repo.market_scope_story_updates[0]["story_identity"].story_key
    assert db.repo.processed_items == [
        {
            "news_item_id": "news-1",
            "processed_at_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 1,
        }
    ]
    assert db.repo.retryable_items == []
    assert db.repo.terminal_failed_items == []
    assert wake_bus.notifications == [{"count": 1}]
    assert "direct_commit" not in db.conn.events
    assert "tx:release_expired_processing_items" in db.conn.events
    assert "tx:claim_unprocessed_items" in db.conn.events
    assert "tx:mark_item_processed" in db.conn.events


def test_news_item_process_worker_passes_authority_scope_to_fact_candidates() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {"event_types": ["exchange_delisting"], "domains": ["coinbase.com"]},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    candidate = db.repo.fact_candidates["news-1"][0]
    assert candidate.event_type == "exchange_listing"
    assert candidate.validation_status == "attention"
    assert "event_type_out_of_authority_scope" in candidate.rejection_reasons


def test_news_item_process_provider_only_non_crypto_high_score_row_enqueues_page_and_brief() -> None:
    item = {
        "news_item_id": "news-spacex",
        "source_id": "opennews-realtime",
        "provider_type": "opennews",
        "source_role": "observed_source",
        "source_domain": "6551.io",
        "source_name": "OpenNews",
        "coverage_tags_json": ["equities"],
        "authority_scope_json": {},
        "title": "SpaceX share sale values company above $350 billion",
        "summary": "Samsung chip demand and private company valuation remain in focus.",
        "body_text": "",
        "published_at_ms": NOW_MS - 1_000,
        "provider_signal_json": {
            "source": "provider",
            "provider": "opennews",
            "status": "ready",
            "direction": "bullish",
            "score": 92,
        },
        "provider_token_impacts_json": [{"symbol": "SPCX", "score": 92, "signal": "long", "grade": "A"}],
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert db.repo.entities["news-spacex"] == []
    assert db.repo.mentions["news-spacex"] == []
    assert db.repo.market_scope_story_updates[0]["market_scope"].primary == "private_company"
    assert db.repo.agent_admission_updates[0]["admission"].status == "eligible"
    assert db.dirty.enqueued == [
        {
            "rows": [{"projection_name": "page", "target_kind": "news_item", "target_id": "news-spacex"}],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "brief_input",
                    "target_kind": "news_item",
                    "target_id": "news-spacex",
                    "priority": 8,
                }
            ],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]


def test_news_item_process_admitted_crypto_row_enqueues_page_and_brief_with_story_key() -> None:
    item = {
        "news_item_id": "news-zec",
        "source_id": "opennews-realtime",
        "provider_type": "opennews",
        "provider_article_keys_json": ["opennews:2367422"],
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "source_name": "Coinbase",
        "coverage_tags_json": ["crypto"],
        "authority_scope_json": {
            "event_types": ["exchange_listing"],
            "domains": ["coinbase.com"],
            "targets": [{"target_type": "CexToken", "target_id": "cex:ZEC"}],
        },
        "title": "Coinbase lists $ZEC for trading",
        "summary": "Zcash trading starts today on Coinbase.",
        "body_text": "",
        "published_at_ms": NOW_MS - 1_000,
        "provider_signal_json": {
            "source": "provider",
            "provider": "opennews",
            "status": "ready",
            "direction": "bullish",
            "score": 72,
        },
        "provider_token_impacts_json": [{"symbol": "ZEC", "score": 72, "signal": "long", "grade": "B"}],
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert db.repo.entities["news-zec"][0].normalized_value == "ZEC"
    assert db.repo.mentions["news-zec"][0].observed_symbol == "ZEC"
    assert db.repo.market_scope_story_updates[0]["market_scope"].primary == "crypto"
    assert db.repo.market_scope_story_updates[0]["story_identity"].story_key == "news-story:opennews-article:2367422"
    assert db.repo.agent_admission_updates[0]["admission"].status == "score_below_threshold"
    assert db.dirty.enqueued == [
        {
            "rows": [{"projection_name": "page", "target_kind": "news_item", "target_id": "news-zec"}],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]


def test_news_item_process_worker_marks_retryable_failure_with_next_due_at_ms() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(
            batch_size=10,
            statement_timeout_seconds=30,
            retry_delay_ms=45_000,
            max_attempts=3,
            lease_ms=120_000,
        ),
        db=db,
        telemetry=object(),
        identity_lookup=ExplodingIdentityLookup(RuntimeError("extract failed")),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 1
    assert db.repo.release_calls == [NOW_MS]
    assert db.repo.claim_calls == [
        {
            "limit": 10,
            "lease_owner": "news_item_process",
            "lease_ms": 120_000,
            "now_ms": NOW_MS,
        }
    ]
    assert db.repo.retryable_items == [
        {
            "news_item_id": "news-1",
            "error": "extract failed",
            "next_due_at_ms": NOW_MS + 45_000,
            "now_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 1,
        }
    ]
    assert db.repo.terminal_failed_items == []


def test_news_item_process_worker_uses_failure_time_for_retry_delay() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    failure_time_ms = NOW_MS + 120_000
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(
            batch_size=10,
            statement_timeout_seconds=30,
            retry_delay_ms=45_000,
            max_attempts=3,
            lease_ms=120_000,
        ),
        db=db,
        telemetry=object(),
        identity_lookup=ExplodingIdentityLookup(RuntimeError("slow failure")),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: failure_time_ms,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert db.repo.retryable_items == [
        {
            "news_item_id": "news-1",
            "error": "slow failure",
            "next_due_at_ms": failure_time_ms + 45_000,
            "now_ms": failure_time_ms,
            "lease_owner": "news_item_process",
            "processing_attempts": 1,
        }
    ]


def test_news_item_process_worker_marks_terminal_failure_on_last_allowed_attempt() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 3,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(
            batch_size=10,
            statement_timeout_seconds=30,
            retry_delay_ms=45_000,
            max_attempts=3,
            lease_ms=120_000,
        ),
        db=db,
        telemetry=object(),
        identity_lookup=ExplodingIdentityLookup(RuntimeError("final failure")),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 1
    assert db.repo.retryable_items == []
    assert db.repo.terminal_failed_items == [
        {
            "news_item_id": "news-1",
            "error": "final failure",
            "now_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 3,
        }
    ]


def test_news_item_process_worker_releases_expired_processing_before_skipping_empty_claim() -> None:
    db = FakeItemProcessDB(FakeItemProcessRepository([]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(
            batch_size=10,
            statement_timeout_seconds=30,
            retry_delay_ms=45_000,
            max_attempts=3,
            lease_ms=120_000,
        ),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.skipped == 1
    assert result.notes == {"reason": "no_unprocessed_items"}
    assert db.repo.release_calls == [NOW_MS]
    assert db.repo.claim_calls == [
        {
            "limit": 10,
            "lease_owner": "news_item_process",
            "lease_ms": 120_000,
            "now_ms": NOW_MS,
        }
    ]
    assert "direct_commit" not in db.conn.events
    assert db.conn.events == [
        "begin",
        "tx:release_expired_processing_items",
        "tx:claim_unprocessed_items",
        "commit",
    ]


def test_news_item_process_worker_treats_stale_processed_claim_as_no_op() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 2,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item], processed_rowcount=0))
    wake_bus = FakeItemProcessWakeBus()
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=wake_bus,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 0
    assert result.notes == {"claimed": 1, "stale_claims": 1}
    assert db.repo.processed_items == [
        {
            "news_item_id": "news-1",
            "processed_at_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 2,
        }
    ]
    assert wake_bus.notifications == []


def test_news_item_process_worker_treats_stale_retryable_claim_as_no_op() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 2,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item], retryable_rowcount=0))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=ExplodingIdentityLookup(RuntimeError("late retry")),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 0
    assert result.notes == {"claimed": 1, "stale_claims": 1}
    assert db.repo.retryable_items == [
        {
            "news_item_id": "news-1",
            "error": "late retry",
            "next_due_at_ms": NOW_MS + 60_000,
            "now_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 2,
        }
    ]


def test_news_item_process_worker_treats_stale_terminal_claim_as_no_op() -> None:
    item = {
        "news_item_id": "news-1",
        "source_id": "source-1",
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "authority_scope_json": {},
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
        "processing_attempts": 3,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item], terminal_rowcount=0))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30, max_attempts=3),
        db=db,
        telemetry=object(),
        identity_lookup=ExplodingIdentityLookup(RuntimeError("late terminal")),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 0
    assert result.notes == {"claimed": 1, "stale_claims": 1}
    assert db.repo.terminal_failed_items == [
        {
            "news_item_id": "news-1",
            "error": "late terminal",
            "now_ms": NOW_MS,
            "lease_owner": "news_item_process",
            "processing_attempts": 3,
        }
    ]


def test_news_item_process_rejects_unsupported_market_scope_shape_before_persistence() -> None:
    item = {
        **_crypto_process_item(),
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    with patch(
        "parallax.domains.news_intel.runtime.news_item_process_worker.classify_news_market_scope",
        return_value=object(),
    ):
        result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 1
    assert db.repo.market_scope_story_updates == []
    assert db.repo.retryable_items[0]["news_item_id"] == "news-zec"
    assert "market scope payload" in str(db.repo.retryable_items[0]["error"])


def test_news_item_process_rejects_unsupported_story_identity_shape_before_persistence() -> None:
    item = {
        **_crypto_process_item(),
        "processing_attempts": 1,
        "processing_lease_owner": "news_item_process",
    }
    db = FakeItemProcessDB(FakeItemProcessRepository([item]))
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        identity_lookup=FakeItemProcessLookup(db),
        wake_bus=FakeItemProcessWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    with patch(
        "parallax.domains.news_intel.runtime.news_item_process_worker.build_news_story_identity",
        return_value=object(),
    ):
        result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.failed == 1
    assert db.repo.market_scope_story_updates == []
    assert db.repo.retryable_items[0]["news_item_id"] == "news-zec"
    assert "story identity payload" in str(db.repo.retryable_items[0]["error"])


def test_news_page_projection_worker_replaces_rows_without_emitting_wake() -> None:
    repo = FakePageProjectionRepository()
    db = FakeProjectionDB("news_page_projection", repo)
    wake_bus = FakeWakeBus()
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert db.sessions == ["news_page_projection"]
    assert repo.story_load_news_item_ids == ["news-1"]
    assert repo.replaced_story_news_item_ids == ["news-1"]
    assert repo.replaced_story_keys == []
    assert repo.replaced_story_rows[0]["news_item_id"] == "news-1"
    assert repo.replaced_story_rows[0]["lifecycle_status"] == "attention"
    assert repo.replaced_story_rows[0]["agent_status"] == "ready"
    assert repo.replaced_story_rows[0]["agent_brief"]["agent_run_id"] == "run-1"
    assert wake_bus.notifications == []


def test_news_page_projection_worker_projects_same_story_once() -> None:
    story_key = "news-story:subject:jpmorgan-citi-tokenized-deposit:t412000"
    repo = FakePageProjectionRepository(
        story_payloads=[
            _page_projection_payload(
                item={
                    "news_item_id": "news-1",
                    "story_key": story_key,
                    "title": "JPMorgan and Citi test tokenized deposits",
                    "analysis_admission_status": "admitted",
                    "analysis_admission_reason": "tokenized_deposit_subject",
                },
                story={
                    "story_key": story_key,
                    "representative_news_item_id": "news-1",
                    "member_news_item_ids": ["news-1", "news-2"],
                    "member_count": 2,
                    "source_domains": ["bloomberg.com", "reuters.com"],
                },
                member_items=[{"news_item_id": "news-1"}, {"news_item_id": "news-2"}],
            )
        ]
    )
    db = FakeProjectionDB(
        "news_page_projection",
        repo,
        claimed=[
            _claimed_page_target("news-1"),
            _claimed_page_target("news-2"),
        ],
    )
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert repo.story_load_news_item_ids == ["news-1", "news-2"]
    assert repo.replaced_story_keys == [story_key]
    assert len(repo.replaced_story_rows) == 1
    assert repo.replaced_story_rows[0]["story_key"] == story_key
    assert result.notes["story_groups_projected"] == 1
    assert result.notes["story_member_items"] == 2
    assert result.notes["projected"] == 1


def test_news_page_projection_worker_reports_deleted_story_member_rows() -> None:
    story_key = "news-story:subject:spacex-valuation:t412000"
    repo = FakePageProjectionRepository(
        story_payloads=[
            _page_projection_payload(
                item={
                    "news_item_id": "news-1",
                    "story_key": story_key,
                    "title": "SpaceX tender offer values company higher",
                    "analysis_admission_status": "page_only",
                    "analysis_admission_reason": "private_company_equity_context",
                },
                story={
                    "story_key": story_key,
                    "representative_news_item_id": "news-1",
                    "member_news_item_ids": ["news-1", "news-2"],
                    "member_count": 2,
                    "source_domains": ["bloomberg.com", "wsj.com"],
                },
                member_items=[{"news_item_id": "news-1"}, {"news_item_id": "news-2"}],
            )
        ],
        replace_result={"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 2},
    )
    db = FakeProjectionDB("news_page_projection", repo, claimed=[_claimed_page_target("news-1")])
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert repo.replaced_story_keys == [story_key]
    assert result.notes["deleted"] == 2
    assert result.notes["projected"] == 1


def test_news_page_projection_worker_reports_unchanged_story_projection() -> None:
    story_key = "news-story:subject:jpmorgan-citi-tokenized-deposit:t412000"
    repo = FakePageProjectionRepository(
        story_payloads=[
            _page_projection_payload(
                item={
                    "news_item_id": "news-1",
                    "story_key": story_key,
                    "title": "JPMorgan and Citi test tokenized deposits",
                    "analysis_admission_status": "admitted",
                    "analysis_admission_reason": "tokenized_deposit_subject",
                },
                story={
                    "story_key": story_key,
                    "representative_news_item_id": "news-1",
                    "member_news_item_ids": ["news-1", "news-2"],
                    "member_count": 2,
                    "source_domains": ["bloomberg.com", "reuters.com"],
                },
                member_items=[{"news_item_id": "news-1"}, {"news_item_id": "news-2"}],
            )
        ],
        replace_result={"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0},
    )
    db = FakeProjectionDB("news_page_projection", repo, claimed=[_claimed_page_target("news-1")])
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.notes["unchanged"] == 1
    assert result.notes["projected"] == 1


def test_news_page_projection_worker_replaces_story_targets_when_payloads_empty() -> None:
    repo = FakePageProjectionRepository(
        story_payloads=[],
        replace_result={"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 1},
    )
    db = FakeProjectionDB("news_page_projection", repo, claimed=[_claimed_page_target("news-non-representative")])
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert repo.story_load_news_item_ids == ["news-non-representative"]
    assert repo.replaced_story_news_item_ids == ["news-non-representative"]
    assert repo.replaced_story_keys == []
    assert repo.replaced_story_rows == []
    assert result.notes["deleted"] == 1


def _worker(
    *,
    db: FakeDB,
    feed_client: FakeNewsSourceProvider,
    wake_bus: FakeWakeBus,
    sources: list[dict[str, object]],
) -> NewsFetchWorker:
    return NewsFetchWorker(
        name="news_fetch",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        feed_client=feed_client,
        news_settings=SimpleNamespace(sources=tuple(sources)),
        wake_bus=wake_bus,
    )


def _crypto_process_item() -> dict[str, object]:
    return {
        "news_item_id": "news-zec",
        "source_id": "opennews-realtime",
        "provider_type": "opennews",
        "provider_article_keys_json": ["opennews:2367422"],
        "source_role": "official_exchange",
        "source_domain": "coinbase.com",
        "source_name": "Coinbase",
        "coverage_tags_json": ["crypto"],
        "authority_scope_json": {
            "event_types": ["exchange_listing"],
            "domains": ["coinbase.com"],
            "targets": [{"target_type": "CexToken", "target_id": "cex:ZEC"}],
        },
        "title": "Coinbase lists $ZEC for trading",
        "summary": "Zcash trading starts today on Coinbase.",
        "body_text": "",
        "published_at_ms": NOW_MS - 1_000,
        "provider_signal_json": {
            "source": "provider",
            "provider": "opennews",
            "status": "ready",
            "direction": "bullish",
            "score": 72,
        },
        "provider_token_impacts_json": [{"symbol": "ZEC", "score": 72, "signal": "long", "grade": "B"}],
    }


def _claimed_page_target(news_item_id: str) -> dict[str, object]:
    return {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": news_item_id,
        "window": "",
        "payload_hash": f"hash-{news_item_id}",
        "lease_owner": "news_page_projection",
        "attempt_count": 1,
    }


def _page_projection_payload(
    *,
    item: dict[str, object] | None = None,
    story: dict[str, object] | None = None,
    member_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload_item = {
        "news_item_id": "news-1",
        "title": "Coinbase lists NEWX",
        "summary": "",
        "source_id": "example-rss",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/a",
        "published_at_ms": 1000,
        "lifecycle_status": "processed",
    }
    payload_item.update(item or {})
    return {
        "item": payload_item,
        "token_mentions": [
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
            }
        ],
        "fact_candidates": [],
        "current_brief": {
            "agent_run_id": "run-1",
            "status": "ready",
            "direction": "bullish",
            "decision_class": "watch",
            "brief_json": {"summary_zh": "测试摘要", "bull_view": {"strength": "moderate"}},
            "input_hash": "input-1",
            "artifact_version_hash": "artifact-1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "computed_at_ms": NOW_MS - 1,
        },
        "story": story,
        "member_items": member_items or [dict(payload_item)],
    }


class FakeDB:
    def __init__(self, repo: FakeNewsRepository) -> None:
        self.repo = repo
        self.conn = FakeConn()
        self.dirty = FakeProjectionDirtyTargetRepository()
        self.open_sessions = 0
        self.max_open_sessions = 0

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == "news_fetch"
        assert statement_timeout_seconds == 30
        assert self.open_sessions == 0
        self.open_sessions += 1
        self.max_open_sessions = max(self.max_open_sessions, self.open_sessions)
        try:
            yield SimpleNamespace(news=self.repo, news_projection_dirty_targets=self.dirty, conn=self.conn)
        finally:
            self.open_sessions -= 1


class FakeItemProcessDB:
    def __init__(self, repo: FakeItemProcessRepository) -> None:
        self.repo = repo
        self.conn = FakeConn()
        self.repo.conn = self.conn
        self.dirty = FakeProjectionDirtyTargetRepository()
        self.open_sessions = 0
        self.max_open_sessions = 0

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == "news_item_process"
        assert statement_timeout_seconds == 30
        assert self.open_sessions == 0
        self.open_sessions += 1
        self.max_open_sessions = max(self.max_open_sessions, self.open_sessions)
        try:
            yield SimpleNamespace(news=self.repo, news_projection_dirty_targets=self.dirty, conn=self.conn)
        finally:
            self.open_sessions -= 1


class FakeProjectionDB:
    def __init__(self, expected_name: str, repo: object, claimed: list[dict[str, object]] | None = None) -> None:
        self.expected_name = expected_name
        self.repo = repo
        self.conn = FakeConn()
        if claimed is None and expected_name == "news_page_projection":
            claimed = [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "window": "",
                    "payload_hash": "hash-1",
                    "lease_owner": expected_name,
                    "attempt_count": 1,
                }
            ]
        claimed = claimed or []
        self.dirty = FakeProjectionDirtyTargetRepository(claimed)
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == self.expected_name
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(news=self.repo, news_projection_dirty_targets=self.dirty, conn=self.conn)


class FakeConn:
    def __init__(self) -> None:
        self.events: list[str] = []
        self._transaction_depth = 0

    def record(self, event: str) -> None:
        prefix = "tx" if self._transaction_depth else "autocommit"
        self.events.append(f"{prefix}:{event}")

    def commit(self) -> None:
        self.events.append("direct_commit")

    @contextmanager
    def transaction(self):
        self.events.append("begin")
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")
        finally:
            self._transaction_depth -= 1


class FakeProjectionDirtyTargetRepository:
    def __init__(self, claimed=None) -> None:
        self.claimed = claimed or []
        self.enqueued: list[dict[str, object]] = []

    def claim_due(self, **payload):
        return [dict(row) for row in self.claimed]

    def enqueue_targets(self, rows, *, reason: str, now_ms: int, commit: bool = True):
        self.enqueued.append({"rows": list(rows), "reason": reason, "now_ms": now_ms, "commit": commit})
        return len(rows)

    def mark_done(self, rows, *, now_ms: int, commit: bool = True):
        return len(rows)

    def mark_error(
        self,
        rows,
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ):
        del count_attempt
        return len(rows)


class FakeNewsSourceProvider:
    provider_type = "fake"

    def __init__(self, db: FakeDB, result: NewsProviderFetchResult) -> None:
        self.db = db
        self.result = result
        self.calls: list[dict[str, object]] = []

    def fetch(
        self,
        source: NewsSourceSnapshot,
        *,
        since_ms: int | None = None,
        cursor: dict[str, object] | None = None,
        cache: NewsSourceHttpCache | None = None,
        limit: int | None = None,
    ) -> NewsProviderFetchResult:
        assert self.db.open_sessions == 0
        self.calls.append(
            {
                "source_id": source.source_id,
                "provider_type": source.provider_type,
                "feed_url": source.feed_url,
                "cache": cache,
                "since_ms": since_ms,
                "cursor": dict(cursor or {}),
                "limit": limit,
            }
        )
        return self.result


class FakeWakeBus:
    def __init__(self) -> None:
        self.notifications: list[dict[str, int | str]] = []

    def notify_news_item_written(self, *, source_id: str, count: int) -> None:
        self.notifications.append({"source_id": source_id, "count": count})


class FakeItemProcessWakeBus:
    def __init__(self) -> None:
        self.notifications: list[dict[str, int]] = []

    def notify_news_item_processed(self, *, count: int) -> None:
        self.notifications.append({"count": count})


class FakeItemProcessLookup:
    def __init__(self, db: FakeItemProcessDB) -> None:
        self.db = db

    def resolve_address(self, *, chain_id: str | None, address: str):
        raise AssertionError("address lookup should not be called for this fixture")

    def resolve_symbol(self, *, symbol: str):
        assert self.db.open_sessions == 0
        return TokenIdentityLookupResult(
            resolution_status="EXACT",
            target_type="CexToken",
            target_id=f"cex:{symbol}",
            display_symbol=symbol,
            display_name="Bitcoin",
            reason_codes=["CONFIRMED_CEX_TOKEN"],
            candidate_targets=[],
        )


class FakeNewsRepository:
    def __init__(self, due_sources: list[dict[str, object]]) -> None:
        self.due_sources = due_sources
        self.reconciled_sources: list[dict[str, object]] = []
        self.fetch_runs: list[dict[str, object]] = []
        self.provider_items: list[dict[str, object]] = []
        self.news_items: list[dict[str, object]] = []
        self.finished_runs: list[dict[str, object]] = []
        self.cache_updates: list[dict[str, object]] = []
        self.news_results: list[dict[str, object]] = []
        self.sync_cursors: dict[str, dict[str, object]] = {}
        self.sync_updates: list[dict[str, object]] = []
        self.events: list[str] = []

    def reconcile_configured_sources(self, sources, *, now_ms: int, commit: bool = True):
        self.reconciled_sources = list(sources)
        return []

    def claim_due_sources(self, *, now_ms: int, limit: int, commit: bool = True):
        return self.due_sources[:limit]

    def list_news_item_ids_for_sources(self, *, source_ids):
        return []

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True):
        fetch_run_id = f"run-{source_id}"
        self.fetch_runs.append({"source_id": source_id, "started_at_ms": started_at_ms})
        return fetch_run_id

    def source_sync_cursor(self, source_id: str):
        return dict(self.sync_cursors.get(source_id, {}))

    def update_source_sync_state(self, source_id: str, next_cursor: dict[str, object], *, now_ms: int, commit: bool):
        self.sync_updates.append(
            {"source_id": source_id, "next_cursor": dict(next_cursor), "now_ms": now_ms, "commit": commit}
        )
        self.events.append("update_source_sync_state")

    def update_source_http_cache(
        self,
        *,
        source_id: str,
        etag: str | None,
        last_modified: str | None,
        now_ms: int,
        commit: bool = True,
    ):
        self.cache_updates.append(
            {"source_id": source_id, "etag": etag, "last_modified": last_modified, "now_ms": now_ms, "commit": commit}
        )

    def upsert_provider_item(self, **payload):
        self.provider_items.append(payload)
        provider_article_id = str(payload["raw_payload"].get("id") or "")
        return {
            "provider_item_id": f"provider-{len(self.provider_items)}",
            "provider_article_id": provider_article_id,
            "provider_article_key": f"rss:{provider_article_id}" if provider_article_id else "",
            "status": "inserted",
        }

    def upsert_canonical_news_item(self, **payload):
        self.news_items.append(payload)
        if self.news_results:
            return dict(self.news_results.pop(0))
        return {"news_item_id": f"news-{len(self.news_items)}", "status": "inserted"}

    def finish_fetch_run(self, **payload):
        self.events.append("finish_fetch_run")
        self.finished_runs.append(payload)
        return payload


class FakeItemProcessRepository:
    def __init__(
        self,
        items: list[dict[str, object]],
        *,
        processed_rowcount: int = 1,
        retryable_rowcount: int = 1,
        terminal_rowcount: int = 1,
    ) -> None:
        self.items = items
        self.conn: FakeConn | None = None
        self.claim_calls: list[dict[str, int | str]] = []
        self.release_calls: list[int] = []
        self.entities: dict[str, list[object]] = {}
        self.mentions: dict[str, list[object]] = {}
        self.fact_candidates: dict[str, list[object]] = {}
        self.content_classifications: list[dict[str, object]] = []
        self.market_scope_story_updates: list[dict[str, object]] = []
        self.agent_admission_updates: list[dict[str, object]] = []
        self.processed_items: list[dict[str, int | str]] = []
        self.retryable_items: list[dict[str, int | str]] = []
        self.terminal_failed_items: list[dict[str, int | str]] = []
        self.processed_rowcount = processed_rowcount
        self.retryable_rowcount = retryable_rowcount
        self.terminal_rowcount = terminal_rowcount

    def release_expired_processing_items(self, *, now_ms: int, commit: bool = True) -> int:
        assert self.conn is not None
        self.conn.record("release_expired_processing_items")
        self.release_calls.append(now_ms)
        return 0

    def claim_unprocessed_items(self, *, limit: int, lease_owner: str, lease_ms: int, now_ms: int, commit: bool = True):
        assert self.conn is not None
        self.conn.record("claim_unprocessed_items")
        self.claim_calls.append(
            {
                "limit": limit,
                "lease_owner": lease_owner,
                "lease_ms": lease_ms,
                "now_ms": now_ms,
            }
        )
        return self.items[:limit]

    def replace_item_entities(self, news_item_id: str, entities: list[object], *, commit: bool = True) -> None:
        assert self.conn is not None
        self.conn.record("replace_item_entities")
        self.entities[news_item_id] = entities

    def replace_token_mentions(self, news_item_id: str, mentions: list[object], *, commit: bool = True) -> None:
        assert self.conn is not None
        self.conn.record("replace_token_mentions")
        self.mentions[news_item_id] = mentions

    def replace_fact_candidates(self, news_item_id: str, candidates: list[object], *, commit: bool = True) -> None:
        assert self.conn is not None
        self.conn.record("replace_fact_candidates")
        self.fact_candidates[news_item_id] = candidates

    def update_item_content_classification(
        self,
        *,
        news_item_id: str,
        content_class: str,
        content_tags: list[str],
        classification_payload: dict[str, object],
        now_ms: int,
        commit: bool = True,
    ) -> None:
        assert self.conn is not None
        self.conn.record("update_item_content_classification")
        self.content_classifications.append(
            {
                "news_item_id": news_item_id,
                "content_class": content_class,
                "content_tags": content_tags,
                "classification_payload": classification_payload,
                "now_ms": now_ms,
            }
        )

    def update_item_market_scope_and_story_identity(
        self,
        *,
        news_item_id: str,
        market_scope: object,
        story_identity: object,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.market_scope_story_updates.append(
            {
                "news_item_id": news_item_id,
                "market_scope": market_scope,
                "story_identity": story_identity,
                "now_ms": now_ms,
                "commit": commit,
            }
        )

    def load_agent_admission_contexts(self, *, news_item_ids: list[str], now_ms: int) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for news_item_id in news_item_ids:
            item = next((dict(row) for row in self.items if str(row.get("news_item_id")) == news_item_id), None)
            if item is None:
                continue
            result.append(
                {
                    "item": item,
                    "entities": [],
                    "token_mentions": [],
                    "fact_candidates": [],
                    "exact_duplicate": {},
                    "similar_story": {},
                    "material_delta": {"has_delta": False, "reasons": [], "evidence": {}},
                }
            )
        return result

    def update_item_agent_admission(
        self,
        *,
        news_item_id: str,
        admission: object,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        assert self.conn is not None
        self.conn.record("update_item_agent_admission")
        self.agent_admission_updates.append(
            {
                "news_item_id": news_item_id,
                "admission": admission,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return 1

    def mark_item_processed(
        self,
        news_item_id: str,
        processed_at_ms: int,
        *,
        lease_owner: str,
        processing_attempts: int,
        commit: bool = True,
    ) -> int:
        assert self.conn is not None
        self.conn.record("mark_item_processed")
        self.processed_items.append(
            {
                "news_item_id": news_item_id,
                "processed_at_ms": processed_at_ms,
                "lease_owner": lease_owner,
                "processing_attempts": processing_attempts,
            }
        )
        return self.processed_rowcount

    def mark_item_process_retryable(
        self,
        news_item_id: str,
        error: str,
        next_due_at_ms: int,
        now_ms: int,
        *,
        lease_owner: str,
        processing_attempts: int,
        commit: bool = True,
    ) -> int:
        assert self.conn is not None
        self.conn.record("mark_item_process_retryable")
        self.retryable_items.append(
            {
                "news_item_id": news_item_id,
                "error": error,
                "next_due_at_ms": next_due_at_ms,
                "now_ms": now_ms,
                "lease_owner": lease_owner,
                "processing_attempts": processing_attempts,
            }
        )
        return self.retryable_rowcount

    def mark_item_process_terminal_failed(
        self,
        news_item_id: str,
        error: str,
        now_ms: int,
        *,
        lease_owner: str,
        processing_attempts: int,
        commit: bool = True,
    ) -> int:
        assert self.conn is not None
        self.conn.record("mark_item_process_terminal_failed")
        self.terminal_failed_items.append(
            {
                "news_item_id": news_item_id,
                "error": error,
                "now_ms": now_ms,
                "lease_owner": lease_owner,
                "processing_attempts": processing_attempts,
            }
        )
        return self.terminal_rowcount


class ExplodingIdentityLookup:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def resolve_address(self, *, chain_id: str | None, address: str):
        raise AssertionError("address lookup should not be called for this fixture")

    def resolve_symbol(self, *, symbol: str):
        raise self.error


class FakePageProjectionRepository:
    def __init__(
        self,
        *,
        story_payloads: list[dict[str, object]] | None = None,
        replace_result: dict[str, int] | None = None,
    ) -> None:
        self.replaced_news_item_ids: list[str] = []
        self.replaced_rows: list[dict[str, object]] = []
        self.story_payloads = [_page_projection_payload()] if story_payloads is None else story_payloads
        self.story_load_news_item_ids: list[str] = []
        self.replaced_story_news_item_ids: list[str] = []
        self.replaced_story_keys: list[str] = []
        self.replaced_story_rows: list[dict[str, object]] = []
        self.replace_result = replace_result

    def load_items_for_page_projection(self, *, news_item_ids):
        assert list(news_item_ids) == ["news-1"]
        return self.story_payloads

    def load_story_projection_payloads_for_items(self, *, news_item_ids):
        self.story_load_news_item_ids = list(news_item_ids)
        return self.story_payloads

    def replace_page_rows_for_items(self, *, news_item_ids, rows, commit: bool = True):
        self.replaced_news_item_ids = list(news_item_ids)
        self.replaced_rows = [dict(row) for row in rows]

    def replace_page_rows_for_story_targets(self, *, news_item_ids, story_keys, rows, commit: bool = True):
        self.replaced_story_news_item_ids = list(news_item_ids)
        self.replaced_story_keys = list(story_keys)
        self.replaced_story_rows = [dict(row) for row in rows]
        if self.replace_result is not None:
            return dict(self.replace_result)
        return {"inserted": len(rows), "updated": 0, "unchanged": 0, "deleted": 0}
