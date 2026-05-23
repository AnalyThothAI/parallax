from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.integrations.news_feeds.feed_client import FeedFetchResult
from gmgn_twitter_intel.integrations.news_feeds.provider_registry import (
    SUPPORTED_NEWS_PROVIDER_TYPES,
    NewsFeedProviderRegistry,
    RssLikeNewsFeedProvider,
    default_news_feed_provider_registry,
)


def test_registry_routes_rss_atom_json_feed_and_cryptopanic_to_expected_wrappers() -> None:
    rss_client = RecordingFeedClient(FeedFetchResult(status_code=200, entries=[{"id": "rss-1"}]))
    cryptopanic_client = RecordingFeedClient(FeedFetchResult(status_code=200, entries=[{"id": "panic-1"}]))
    registry = default_news_feed_provider_registry(
        rss_client=rss_client,
        cryptopanic_client=cryptopanic_client,
    )

    rss_wrapper = registry.provider_for("rss")
    assert registry.provider_for("atom") is rss_wrapper
    assert registry.provider_for("json_feed") is rss_wrapper
    assert registry.provider_for("cryptopanic") is not rss_wrapper

    for provider_type in ("rss", "atom", "json_feed"):
        registry.fetch(
            provider_type=provider_type,
            feed_url=f"https://example.com/{provider_type}.xml",
            etag="old-etag",
            last_modified="old-modified",
            source={"source_id": provider_type},
        )

    registry.fetch(
        provider_type="cryptopanic",
        feed_url="cryptopanic://posts?regions=en",
        etag="panic-cursor",
        last_modified=None,
        source={"source_id": "cryptopanic-en"},
    )

    assert [call["provider_type"] for call in rss_client.calls] == ["rss", "atom", "json_feed"]
    assert rss_client.calls[0]["etag"] == "old-etag"
    assert rss_client.calls[0]["last_modified"] == "old-modified"
    assert rss_client.calls[0]["source_id"] == "rss"
    assert cryptopanic_client.calls == [
        {
            "url": "cryptopanic://posts?regions=en",
            "etag": "panic-cursor",
            "last_modified": None,
            "provider_type": "cryptopanic",
            "source_id": "cryptopanic-en",
        }
    ]
    assert registry.supported_provider_types() == SUPPORTED_NEWS_PROVIDER_TYPES


def test_registry_unknown_provider_type_raises_compact_value_error() -> None:
    registry = default_news_feed_provider_registry(
        rss_client=RecordingFeedClient(FeedFetchResult(status_code=200)),
        cryptopanic_client=RecordingFeedClient(FeedFetchResult(status_code=200)),
    )

    with pytest.raises(ValueError) as exc_info:
        registry.fetch(provider_type="openbb", feed_url="https://example.com/feed")

    assert str(exc_info.value) == "unsupported news source provider: openbb"


def test_registry_close_attempts_all_providers_and_remains_retryable_on_error() -> None:
    failing_client = CloseFailingFeedClient()
    healthy_client = RecordingFeedClient(FeedFetchResult(status_code=200))
    registry = NewsFeedProviderRegistry()
    registry.register("bad", RssLikeNewsFeedProvider(failing_client))
    registry.register("good", RssLikeNewsFeedProvider(healthy_client))

    with pytest.raises(RuntimeError, match="close boom"):
        registry.close()

    assert failing_client.close_count == 1
    assert healthy_client.close_count == 1

    with pytest.raises(RuntimeError, match="close boom"):
        registry.close()

    assert failing_client.close_count == 2
    assert healthy_client.close_count == 2


class RecordingFeedClient:
    def __init__(self, result: FeedFetchResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []
        self.close_count = 0

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        provider_type: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> FeedFetchResult:
        self.calls.append(
            {
                "url": url,
                "etag": etag,
                "last_modified": last_modified,
                "provider_type": provider_type,
                "source_id": (source or {}).get("source_id"),
            }
        )
        return self.result

    def close(self) -> None:
        self.close_count += 1


class CloseFailingFeedClient:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1
        raise RuntimeError("close boom")
