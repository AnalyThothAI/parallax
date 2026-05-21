from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.news_intel.providers import NewsFeedProvider
from gmgn_twitter_intel.integrations.news_feeds.cryptopanic_client import CryptopanicFeedClient
from gmgn_twitter_intel.integrations.news_feeds.feed_client import FeedClient, FeedFetchResult
from gmgn_twitter_intel.platform.config.settings import Settings


def news_feed_client(settings: Settings) -> NewsFeedProvider:
    del settings
    return CompositeNewsFeedClient(rss_client=FeedClient(), cryptopanic_client=CryptopanicFeedClient())


class CompositeNewsFeedClient:
    def __init__(self, *, rss_client: FeedClient, cryptopanic_client: CryptopanicFeedClient) -> None:
        self._rss_client = rss_client
        self._cryptopanic_client = cryptopanic_client

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        provider_type: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> FeedFetchResult:
        if provider_type == "cryptopanic" or str(url).startswith("cryptopanic://"):
            return self._cryptopanic_client.fetch(
                url,
                etag=etag,
                last_modified=last_modified,
                provider_type=provider_type,
                source=source,
            )
        return self._rss_client.fetch(
            url,
            etag=etag,
            last_modified=last_modified,
            provider_type=provider_type,
            source=source,
        )

    def close(self) -> None:
        self._rss_client.close()
        self._cryptopanic_client.close()


__all__ = ["CompositeNewsFeedClient", "news_feed_client"]
