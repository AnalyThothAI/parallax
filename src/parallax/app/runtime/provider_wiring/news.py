from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.domains.news_intel.providers import NewsSourceProvider
from parallax.domains.news_intel.services.feed_item_normalizer import normalize_feed_entry
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from parallax.integrations.news_feeds.cryptopanic_client import CryptopanicFeedClient
from parallax.integrations.news_feeds.feed_client import FeedClient
from parallax.integrations.news_feeds.opennews_client import OpenNewsFeedClient
from parallax.integrations.news_feeds.provider_registry import (
    NewsFeedProviderRegistry,
    default_news_feed_provider_registry,
)
from parallax.platform.config.settings import Settings


def news_feed_client(settings: Settings) -> NewsSourceProvider:
    opennews_settings = settings.news_intel.opennews
    registry = default_news_feed_provider_registry(
        rss_client=FeedClient(),
        cryptopanic_client=CryptopanicFeedClient(),
        opennews_client=OpenNewsFeedClient(
            token=opennews_settings.api_token,
            api_base_url=opennews_settings.api_base_url,
        ),
    )
    return RegistryBackedNewsSourceProvider(registry=registry)


class RegistryBackedNewsSourceProvider:
    provider_type = "registry"

    def __init__(self, *, registry: NewsFeedProviderRegistry) -> None:
        self._registry = registry

    def fetch(
        self,
        source: NewsSourceSnapshot,
        *,
        since_ms: int | None = None,
        cursor: Mapping[str, Any] | None = None,
        cache: NewsSourceHttpCache | None = None,
        limit: int | None = None,
    ) -> NewsProviderFetchResult:
        feed_result = self._registry.fetch(
            provider_type=source.provider_type,
            feed_url=source.feed_url,
            etag=cache.etag if cache else None,
            last_modified=cache.last_modified if cache else None,
            source=source.raw,
            cursor=cursor or {},
            since_ms=since_ms,
            limit=limit,
        )
        observations = [_observation_from_entry(source, entry) for entry in feed_result.entries]
        return NewsProviderFetchResult(
            status_code=feed_result.status_code,
            observations=[observation for observation in observations if observation is not None],
            etag=feed_result.etag,
            last_modified=feed_result.last_modified,
            not_modified=feed_result.not_modified,
            next_cursor=dict(feed_result.next_cursor or {}),
            provider_diagnostics=_provider_diagnostics(feed_result),
        )

    def close(self) -> None:
        self._registry.close()


def _observation_from_entry(
    source: NewsSourceSnapshot,
    entry: Mapping[str, Any],
) -> NewsProviderObservation | None:
    normalized = normalize_feed_entry(source.source_domain, entry, fetched_at_ms=source.now_ms)
    if normalized is None:
        return None
    return NewsProviderObservation(
        source_item_key=normalized.source_item_key,
        canonical_url=normalized.canonical_url,
        title=normalized.title,
        summary=normalized.summary,
        body_text=normalized.body_text,
        language=normalized.language,
        published_at_ms=normalized.published_at_ms,
        raw_payload=normalized.raw_payload,
        original_source_url=_optional_str(entry.get("original_url")),
        original_source_domain=_optional_str(entry.get("source_domain")),
        provider_signal=_optional_mapping(entry.get("provider_signal")),
        provider_token_impacts=_optional_mapping_list(entry.get("provider_token_impacts")),
    )


def _provider_diagnostics(feed_result: Any) -> dict[str, Any]:
    feed = getattr(feed_result, "feed", None)
    if isinstance(feed, Mapping) and feed:
        return {"feed": dict(feed)}
    return {}


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _optional_mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


__all__ = [
    "RegistryBackedNewsSourceProvider",
    "news_feed_client",
]
