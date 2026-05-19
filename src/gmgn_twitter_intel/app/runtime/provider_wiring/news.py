from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.providers import NewsFeedProvider
from gmgn_twitter_intel.integrations.news_feeds.feed_client import FeedClient
from gmgn_twitter_intel.platform.config.settings import Settings


def news_feed_client(settings: Settings) -> NewsFeedProvider:
    return FeedClient()


__all__ = ["news_feed_client"]
