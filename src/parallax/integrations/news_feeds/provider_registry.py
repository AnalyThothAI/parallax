from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from parallax.integrations.news_feeds.cryptopanic_client import CryptopanicFeedClient
from parallax.integrations.news_feeds.feed_client import FeedClient, FeedFetchResult
from parallax.integrations.news_feeds.opennews_client import OpenNewsFeedClient


class NewsFeedClient(Protocol):
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        provider_type: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> FeedFetchResult: ...

    def close(self) -> None: ...


class RegistryNewsFeedProvider(Protocol):
    def fetch(
        self,
        *,
        feed_url: str,
        provider_type: str,
        etag: str | None = None,
        last_modified: str | None = None,
        source: Mapping[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult: ...

    def close(self) -> None: ...


class OpenNewsClient(Protocol):
    def fetch(
        self,
        url: str,
        *,
        source: dict[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult: ...

    def close(self) -> None: ...


class RssLikeNewsFeedProvider:
    def __init__(self, client: NewsFeedClient) -> None:
        self._client = client

    def fetch(
        self,
        *,
        feed_url: str,
        provider_type: str,
        etag: str | None = None,
        last_modified: str | None = None,
        source: Mapping[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        del cursor, since_ms, limit
        return self._client.fetch(
            feed_url,
            etag=etag,
            last_modified=last_modified,
            provider_type=provider_type,
            source=dict(source or {}),
        )

    def close(self) -> None:
        self._client.close()


class OpenNewsNewsFeedProvider:
    def __init__(self, client: OpenNewsClient) -> None:
        self._client = client

    def fetch(
        self,
        *,
        feed_url: str,
        provider_type: str,
        etag: str | None = None,
        last_modified: str | None = None,
        source: Mapping[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        del provider_type, etag, last_modified
        return self._client.fetch(
            feed_url,
            source=dict(source or {}),
            cursor=dict(cursor or {}),
            since_ms=since_ms,
            limit=limit,
        )

    def close(self) -> None:
        self._client.close()


class NewsFeedProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, RegistryNewsFeedProvider] = {}
        self._closed = False

    def register(self, provider_type: str, provider: RegistryNewsFeedProvider) -> None:
        self._providers[str(provider_type)] = provider

    def provider_for(self, provider_type: str) -> RegistryNewsFeedProvider:
        try:
            return self._providers[str(provider_type)]
        except KeyError as exc:
            raise ValueError(f"unsupported news source provider: {provider_type}") from exc

    def fetch(
        self,
        *,
        provider_type: str,
        feed_url: str,
        etag: str | None = None,
        last_modified: str | None = None,
        source: Mapping[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        provider = self.provider_for(provider_type)
        return provider.fetch(
            feed_url=feed_url,
            provider_type=provider_type,
            etag=etag,
            last_modified=last_modified,
            source=source,
            cursor=cursor,
            since_ms=since_ms,
            limit=limit,
        )

    def close(self) -> None:
        if self._closed:
            return
        seen: set[int] = set()
        first_error: Exception | None = None
        for provider in self._providers.values():
            provider_id = id(provider)
            if provider_id in seen:
                continue
            seen.add(provider_id)
            try:
                provider.close()
            except Exception as exc:  # pragma: no cover - defensive close path.
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error
        self._closed = True


def default_news_feed_provider_registry(
    *,
    rss_client: NewsFeedClient | None = None,
    cryptopanic_client: NewsFeedClient | None = None,
    opennews_client: OpenNewsClient | None = None,
) -> NewsFeedProviderRegistry:
    rss_provider = RssLikeNewsFeedProvider(rss_client or FeedClient())
    cryptopanic_provider = RssLikeNewsFeedProvider(cryptopanic_client or CryptopanicFeedClient())
    opennews_provider = OpenNewsNewsFeedProvider(opennews_client or OpenNewsFeedClient())
    registry = NewsFeedProviderRegistry()
    for provider_type in ("rss", "atom", "json_feed"):
        registry.register(provider_type, rss_provider)
    registry.register("cryptopanic", cryptopanic_provider)
    registry.register("opennews", opennews_provider)
    return registry


__all__ = [
    "NewsFeedProviderRegistry",
    "OpenNewsNewsFeedProvider",
    "RegistryNewsFeedProvider",
    "RssLikeNewsFeedProvider",
    "default_news_feed_provider_registry",
]
