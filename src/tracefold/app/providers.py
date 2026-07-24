from __future__ import annotations

from tracefold.app.provider_types import (
    AssetMarketProviders,
    IngestionProviders,
    NewsIntelProviders,
    WiredProviders,
)
from tracefold.platform.config.settings import Settings


def wire_providers(
    settings: Settings,
    *,
    start_collector: bool,
) -> WiredProviders:
    from tracefold.app import market_providers
    from tracefold.integrations.gmgn import providers as gmgn
    from tracefold.integrations.news_feeds import providers as news

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=market_providers.wire_asset_market(settings),
        news_intel=NewsIntelProviders(
            feed_client=news.news_feed_client(settings)
            if settings.news_intel.enabled and settings.workers.news_fetch.enabled
            else None,
        ),
    )


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "NewsIntelProviders",
    "WiredProviders",
    "wire_providers",
]
