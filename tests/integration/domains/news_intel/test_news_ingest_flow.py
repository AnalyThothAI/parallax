from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.news_intel.queries.news_page_query import NewsPageQuery
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker import NewsStoryProjectionWorker
from gmgn_twitter_intel.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import TokenIdentityLookupResult
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_news_workers_ingest_process_project_and_query_visible_news(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        source = {
            "source_id": "binance-announcements",
            "provider_type": "rss",
            "feed_url": "https://www.binance.com/en/support/announcement/rss",
            "source_domain": "binance.com",
            "source_name": "Binance Announcements",
            "source_role": "official_exchange",
            "trust_tier": "high",
            "authority_scope": {
                "event_types": ["exchange_listing"],
                "domains": ["binance.com"],
                "targets": [{"target_type": "CexToken", "target_id": "cex:BTC"}],
            },
            "refresh_interval_seconds": 300,
        }
        db = _SingleConnectionWorkerDB(conn)
        wake_bus = _FakeWakeBus()
        feed_client = _FakeFeedClient(
            NewsProviderFetchResult(
                status_code=200,
                observations=[
                    NewsProviderObservation(
                        source_item_key="binance-guid-1",
                        canonical_url="https://www.binance.com/en/support/announcement/btc-listing",
                        title="Binance lists $BTC for spot trading",
                        summary="Trading opens today for the BTC/USDT pair.",
                        body_text="Trading opens today for the BTC/USDT pair.",
                        language="en",
                        published_at_ms=NOW_MS,
                        raw_payload={
                            "id": "binance-guid-1",
                            "link": "https://www.binance.com/en/support/announcement/btc-listing?utm_source=rss",
                            "title": "Binance lists $BTC for spot trading",
                            "summary": "Trading opens today for the BTC/USDT pair.",
                            "language": "en",
                        },
                    )
                ],
                etag="etag-1",
                last_modified="Tue, 19 May 2026 00:00:00 GMT",
            )
        )

        fetch = NewsFetchWorker(
            name="news_fetch",
            settings=_worker_settings(batch_size=10),
            db=db,
            telemetry=object(),
            news_settings=SimpleNamespace(sources=(source,)),
            wake_bus=wake_bus,
            feed_client=feed_client,
        )
        process = NewsItemProcessWorker(
            name="news_item_process",
            settings=_worker_settings(batch_size=10),
            db=db,
            telemetry=object(),
            identity_lookup=_FakeIdentityLookup(),
            wake_bus=wake_bus,
        )
        story = NewsStoryProjectionWorker(
            name="news_story_projection",
            settings=_worker_settings(batch_size=10),
            db=db,
            telemetry=object(),
            wake_bus=wake_bus,
        )
        page = NewsPageProjectionWorker(
            name="news_page_projection",
            settings=_worker_settings(batch_size=10),
            db=db,
            telemetry=object(),
            wake_bus=wake_bus,
        )

        fetch_result = fetch.run_once_sync(now_ms=NOW_MS)
        process_result = process.run_once_sync(now_ms=NOW_MS + 1)
        story_result = story.run_once_sync(now_ms=NOW_MS + 2)
        page_result = page.run_once_sync(now_ms=NOW_MS + 3)
        query = NewsPageQuery(repository=NewsRepository(conn))
        page_data = query.list_news(limit=10)
        item_detail = query.get_item(news_item_id=page_data["items"][0]["news_item_id"])
        story_detail = query.get_story(story_id=page_data["items"][0]["story_id"])
    finally:
        conn.close()

    assert fetch_result.processed == 1
    assert process_result.processed == 1
    assert story_result.processed == 1
    assert page_result.processed == 1
    assert feed_client.calls == [
        {
            "source_id": "binance-announcements",
            "provider_type": "rss",
            "feed_url": "https://www.binance.com/en/support/announcement/rss",
            "since_ms": None,
            "cursor": {},
            "etag": None,
            "last_modified": None,
            "limit": 10,
        }
    ]
    assert wake_bus.notifications == [
        {"channel": "news_item_written", "source_id": "binance-announcements", "count": 1},
        {"channel": "news_item_processed", "count": 1},
        {"channel": "news_story_updated", "count": 1},
    ]

    row = page_data["items"][0]
    assert row["headline"] == "Binance lists $BTC for spot trading"
    assert row["canonical_url"] == "https://www.binance.com/en/support/announcement/btc-listing"
    assert row["lifecycle_status"] == "accepted"
    assert row["story_id"]
    assert row["source"]["source_role"] == "official_exchange"
    assert row["token_lanes"][0]["resolution_status"] == "known_symbol"
    assert row["token_lanes"][0]["target_type"] == "CexToken"
    assert row["fact_lanes"][0]["event_type"] == "exchange_listing"
    assert row["fact_lanes"][0]["status"] == "accepted"
    assert item_detail is not None
    assert item_detail["source"]["source_role"] == "official_exchange"
    assert item_detail["provider_item"]["source_item_key"] == "binance-guid-1"
    assert item_detail["fetch_run"]["status"] == "success"
    assert item_detail["story_members"][0]["story_id"] == row["story_id"]
    assert story_detail is not None
    assert story_detail["token_mentions"][0]["target_type"] == "CexToken"
    assert story_detail["fact_candidates"][0]["event_type"] == "exchange_listing"


def _worker_settings(*, batch_size: int) -> SimpleNamespace:
    return SimpleNamespace(batch_size=batch_size, statement_timeout_seconds=30)


class _SingleConnectionWorkerDB:
    def __init__(self, conn) -> None:
        self.conn = conn

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name in {"news_fetch", "news_item_process", "news_story_projection", "news_page_projection"}
        assert statement_timeout_seconds == 30
        yield repositories_for_connection(self.conn)


class _FakeFeedClient:
    def __init__(self, result: NewsProviderFetchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def fetch(
        self,
        source: NewsSourceSnapshot,
        *,
        since_ms: int | None,
        cursor: Mapping[str, Any],
        cache: NewsSourceHttpCache,
        limit: int | None,
    ) -> NewsProviderFetchResult:
        self.calls.append(
            {
                "source_id": source.source_id,
                "provider_type": source.provider_type,
                "feed_url": source.feed_url,
                "since_ms": since_ms,
                "cursor": dict(cursor),
                "etag": cache.etag,
                "last_modified": cache.last_modified,
                "limit": limit,
            }
        )
        return self.result


class _FakeIdentityLookup:
    def resolve_address(self, *, chain_id: str | None, address: str) -> TokenIdentityLookupResult:
        raise AssertionError("address lookup should not be used by the fixture")

    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult:
        return TokenIdentityLookupResult(
            resolution_status="EXACT",
            target_type="CexToken",
            target_id=f"cex:{symbol}",
            display_symbol=symbol,
            display_name=symbol,
            reason_codes=["CONFIRMED_CEX_TOKEN"],
            candidate_targets=[{"target_type": "CexToken", "target_id": f"cex:{symbol}"}],
        )


class _FakeWakeBus:
    def __init__(self) -> None:
        self.notifications: list[dict[str, object]] = []

    def notify_news_item_written(self, *, source_id: str, count: int) -> None:
        self.notifications.append({"channel": "news_item_written", "source_id": source_id, "count": count})

    def notify_news_item_processed(self, *, count: int) -> None:
        self.notifications.append({"channel": "news_item_processed", "count": count})

    def notify_news_story_updated(self, *, count: int) -> None:
        self.notifications.append({"channel": "news_story_updated", "count": count})
