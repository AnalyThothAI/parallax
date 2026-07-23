from __future__ import annotations

from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    IngestionProviders,
    NewsIntelProviders,
    WiredProviders,
)
from parallax.platform.config.settings import Settings


def wire_providers(
    settings: Settings,
    *,
    start_collector: bool,
) -> WiredProviders:
    from parallax.app.runtime.provider_wiring import (
        asset_market,
        gmgn,
        news,
    )

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=asset_market.wire_asset_market(settings),
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
