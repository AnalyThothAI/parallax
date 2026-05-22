from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker import NewsStoryProjectionWorker
from gmgn_twitter_intel.domains.news_intel.types.source_provider import (
    NewsProviderContextObservation,
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import TokenIdentityLookupResult

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
                    canonical_url="https://example.com/story",
                    title="SOL ETF approved",
                    summary="Issuer confirms launch.",
                    body_text="Issuer confirms launch.",
                    language="en",
                    published_at_ms=NOW_MS,
                    raw_payload={
                        "id": "guid-1",
                        "link": "https://example.com/story?utm_source=rss",
                        "title": "SOL ETF approved",
                        "summary": "Issuer confirms launch.",
                        "source_domain": "example.com",
                    },
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
            "limit": 10,
        }
    ]
    assert db.repo.reconciled_sources == [source]
    assert db.repo.provider_items[0]["source_item_key"] == "guid-1"
    assert db.repo.provider_items[0]["canonical_url"] == "https://example.com/story"
    assert db.repo.news_items[0]["title"] == "SOL ETF approved"
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


def test_news_fetch_worker_persists_context_observations() -> None:
    source = {
        "source_id": "example-rss",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            observations=[
                NewsProviderObservation(
                    source_item_key="guid-1",
                    canonical_url="https://example.com/story",
                    title="SOL ETF approved",
                    summary="Issuer confirms launch.",
                    body_text="Primary body stays primary.",
                    language="en",
                    published_at_ms=NOW_MS - 10,
                    raw_payload={"id": "guid-1", "title": "SOL ETF approved"},
                ),
                NewsProviderObservation(
                    source_item_key="guid-2",
                    canonical_url="https://example.com/second-story",
                    title="BTC ETF launches",
                    summary="Second issuer confirms launch.",
                    body_text="Second primary body.",
                    language="en",
                    published_at_ms=NOW_MS - 8,
                    raw_payload={"id": "guid-2", "title": "BTC ETF launches"},
                )
            ],
            context_observations=[
                NewsProviderContextObservation(
                    context_item_id="ctx-1",
                    parent_source_item_key="guid-2",
                    context_type="reply",
                    author="analyst",
                    canonical_url="https://example.social/post/1",
                    body_text="Context should live outside news_items.body_text.",
                    published_at_ms=NOW_MS - 5,
                    engagement={"likes": 42},
                    raw_payload={"id": "ctx-1", "kind": "reply"},
                ),
                NewsProviderContextObservation(
                    context_item_id="ctx-unresolved",
                    parent_source_item_key="missing-guid",
                    context_type="reply",
                    author=None,
                    canonical_url="https://example.social/post/unresolved",
                    body_text="Context without a parent should still be stored.",
                    published_at_ms=None,
                    engagement=None,
                    raw_payload={"id": "ctx-unresolved", "kind": "reply"},
                )
            ],
        ),
    )
    worker = _worker(db=db, feed_client=feed, wake_bus=FakeWakeBus(), sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert db.repo.news_items[0]["body_text"] == "Primary body stays primary."
    assert db.repo.context_items == [
        {
            "context_item_id": "ctx-1",
            "source_id": "example-rss",
            "parent_news_item_id": "news-2",
            "provider_item_id": None,
            "context_type": "reply",
            "author": "analyst",
            "canonical_url": "https://example.social/post/1",
            "body_text": "Context should live outside news_items.body_text.",
            "published_at_ms": NOW_MS - 5,
            "engagement_json": {"likes": 42},
            "raw_payload_json": {"id": "ctx-1", "kind": "reply"},
            "created_at_ms": NOW_MS,
            "commit": False,
        },
        {
            "context_item_id": "ctx-unresolved",
            "source_id": "example-rss",
            "parent_news_item_id": None,
            "provider_item_id": None,
            "context_type": "reply",
            "author": None,
            "canonical_url": "https://example.social/post/unresolved",
            "body_text": "Context without a parent should still be stored.",
            "published_at_ms": None,
            "engagement_json": {},
            "raw_payload_json": {"id": "ctx-unresolved", "kind": "reply"},
            "created_at_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_news_fetch_worker_persists_context_only_observations_without_processing_items() -> None:
    source = {
        "source_id": "example-rss",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }
    db = FakeDB(FakeNewsRepository([source]))
    feed = FakeNewsSourceProvider(
        db,
        NewsProviderFetchResult(
            status_code=200,
            observations=[],
            context_observations=[
                NewsProviderContextObservation(
                    context_item_id="ctx-only",
                    parent_source_item_key="missing-guid",
                    context_type="reply",
                    author="analyst",
                    canonical_url=None,
                    body_text="Context-only update.",
                    published_at_ms=None,
                    engagement=None,
                    raw_payload={"id": "ctx-only"},
                )
            ],
        ),
    )
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, feed_client=feed, wake_bus=wake_bus, sources=[source])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert db.repo.news_items == []
    assert db.repo.context_items == [
        {
            "context_item_id": "ctx-only",
            "source_id": "example-rss",
            "parent_news_item_id": None,
            "provider_item_id": None,
            "context_type": "reply",
            "author": "analyst",
            "canonical_url": None,
            "body_text": "Context-only update.",
            "published_at_ms": None,
            "engagement_json": {},
            "raw_payload_json": {"id": "ctx-only"},
            "created_at_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert db.repo.finished_runs[0]["fetched_count"] == 0
    assert db.repo.finished_runs[0]["inserted_count"] == 0
    assert wake_bus.notifications == []


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
            "limit": 10,
        }
    ]
    assert db.repo.provider_items[0]["source_item_key"] == "cryptopanic:32675220"


def test_news_item_process_worker_extracts_mentions_candidates_and_wakes() -> None:
    item = {
        "news_item_id": "news-1",
        "source_role": "official_exchange",
        "title": "Coinbase lists $BTC for trading",
        "summary": "Trading starts today",
        "body_text": "",
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
    assert db.repo.list_calls == [{"limit": 10, "now_ms": NOW_MS}]
    assert db.repo.entities["news-1"][0].entity_type == "symbol"
    assert db.repo.mentions["news-1"][0].resolution_status == "known_symbol"
    assert db.repo.fact_candidates["news-1"][0].validation_status == "accepted"
    assert db.repo.processed_items == [{"news_item_id": "news-1", "processed_at_ms": NOW_MS}]
    assert db.repo.failed_items == []
    assert wake_bus.notifications == [{"count": 1}]


def test_news_story_projection_worker_assigns_items_in_worker_session_and_notifies() -> None:
    repo = FakeStoryProjectionRepository()
    db = FakeProjectionDB("news_story_projection", repo)
    wake_bus = FakeWakeBus()
    worker = NewsStoryProjectionWorker(
        name="news_story_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert db.sessions == ["news_story_projection"]
    assert repo.created_stories[0]["item"]["news_item_id"] == "news-1"
    assert repo.story_members[0]["relation"] == "representative"
    assert wake_bus.notifications == [{"channel": "news_story_updated", "count": 1}]


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
    assert repo.replaced_news_item_ids == ["news-1"]
    assert repo.replaced_rows[0]["news_item_id"] == "news-1"
    assert repo.replaced_rows[0]["lifecycle_status"] == "attention"
    assert repo.replaced_rows[0]["agent_status"] == "ready"
    assert repo.replaced_rows[0]["agent_brief_json"]["agent_run_id"] == "run-1"
    assert wake_bus.notifications == []


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


class FakeDB:
    def __init__(self, repo: FakeNewsRepository) -> None:
        self.repo = repo
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
            yield SimpleNamespace(news=self.repo)
        finally:
            self.open_sessions -= 1


class FakeItemProcessDB:
    def __init__(self, repo: FakeItemProcessRepository) -> None:
        self.repo = repo
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
            yield SimpleNamespace(news=self.repo)
        finally:
            self.open_sessions -= 1


class FakeProjectionDB:
    def __init__(self, expected_name: str, repo: object) -> None:
        self.expected_name = expected_name
        self.repo = repo
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == self.expected_name
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(news=self.repo)


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
        assert since_ms is None
        assert cursor == {}
        self.calls.append(
            {
                "source_id": source.source_id,
                "provider_type": source.provider_type,
                "feed_url": source.feed_url,
                "cache": cache,
                "limit": limit,
            }
        )
        return self.result


class FakeWakeBus:
    def __init__(self) -> None:
        self.notifications: list[dict[str, int | str]] = []

    def notify_news_item_written(self, *, source_id: str, count: int) -> None:
        self.notifications.append({"source_id": source_id, "count": count})

    def notify_news_story_updated(self, *, count: int) -> None:
        self.notifications.append({"channel": "news_story_updated", "count": count})


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
        self.context_items: list[dict[str, object]] = []
        self.finished_runs: list[dict[str, object]] = []
        self.cache_updates: list[dict[str, object]] = []

    def reconcile_configured_sources(self, sources, *, now_ms: int):
        self.reconciled_sources = list(sources)
        return []

    def claim_due_sources(self, *, now_ms: int, limit: int):
        return self.due_sources[:limit]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int):
        fetch_run_id = f"run-{source_id}"
        self.fetch_runs.append({"source_id": source_id, "started_at_ms": started_at_ms})
        return fetch_run_id

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
        return {"provider_item_id": f"provider-{len(self.provider_items)}", "status": "inserted"}

    def upsert_news_item(self, **payload):
        self.news_items.append(payload)
        return {"news_item_id": f"news-{len(self.news_items)}", "status": "inserted"}

    def upsert_news_context_item(self, **payload):
        self.context_items.append(payload)
        return payload

    def finish_fetch_run(self, **payload):
        self.finished_runs.append(payload)
        return payload


class FakeItemProcessRepository:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items
        self.list_calls: list[dict[str, int]] = []
        self.entities: dict[str, list[object]] = {}
        self.mentions: dict[str, list[object]] = {}
        self.fact_candidates: dict[str, list[object]] = {}
        self.processed_items: list[dict[str, int | str]] = []
        self.failed_items: list[dict[str, int | str]] = []

    def list_unprocessed_items(self, *, limit: int, now_ms: int):
        self.list_calls.append({"limit": limit, "now_ms": now_ms})
        return self.items[:limit]

    def replace_item_entities(self, news_item_id: str, entities: list[object]) -> None:
        self.entities[news_item_id] = entities

    def replace_token_mentions(self, news_item_id: str, mentions: list[object]) -> None:
        self.mentions[news_item_id] = mentions

    def replace_fact_candidates(self, news_item_id: str, candidates: list[object]) -> None:
        self.fact_candidates[news_item_id] = candidates

    def mark_item_processed(self, news_item_id: str, processed_at_ms: int) -> None:
        self.processed_items.append({"news_item_id": news_item_id, "processed_at_ms": processed_at_ms})

    def mark_item_process_failed(self, news_item_id: str, error: str, now_ms: int) -> None:
        self.failed_items.append({"news_item_id": news_item_id, "error": error, "now_ms": now_ms})


class FakeStoryProjectionRepository:
    def __init__(self) -> None:
        self.created_stories: list[dict[str, object]] = []
        self.refreshed_stories: list[dict[str, object]] = []
        self.story_members: list[dict[str, object]] = []

    def list_items_missing_story(self, *, limit: int):
        assert limit == 10
        return [
            {
                "news_item_id": "news-1",
                "canonical_url": "https://example.test/a",
                "content_hash": "hash-1",
                "title_fingerprint": "coinbase lists newx",
                "published_at_ms": 1000,
                "token_targets": ["symbol:NEWX"],
            }
        ]

    def find_story_candidates_for_item(self, item):
        assert item["news_item_id"] == "news-1"
        return []

    def create_story_from_item(self, **payload):
        self.created_stories.append(payload)

    def refresh_story_from_member(self, **payload):
        self.refreshed_stories.append(payload)

    def add_story_member(self, **payload):
        self.story_members.append(payload)


class FakePageProjectionRepository:
    def __init__(self) -> None:
        self.replaced_news_item_ids: list[str] = []
        self.replaced_rows: list[dict[str, object]] = []

    def list_items_for_page_projection(self, *, limit: int):
        assert limit == 10
        return [
            {
                "item": {
                    "news_item_id": "news-1",
                    "title": "Coinbase lists NEWX",
                    "summary": "",
                    "source_id": "example-rss",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/a",
                    "published_at_ms": 1000,
                    "lifecycle_status": "processed",
                },
                "story": None,
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
            }
        ]

    def replace_page_rows_for_items(self, *, news_item_ids, rows):
        self.replaced_news_item_ids = list(news_item_ids)
        self.replaced_rows = [dict(row) for row in rows]
