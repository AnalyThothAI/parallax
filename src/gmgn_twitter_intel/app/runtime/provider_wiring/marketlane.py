from __future__ import annotations

from gmgn_twitter_intel.app.runtime.provider_wiring.types import MarketlaneProviders
from gmgn_twitter_intel.integrations.marketlane import MarketlaneQuoteProvider
from gmgn_twitter_intel.platform.config.settings import Settings


def wire_marketlane(settings: Settings) -> MarketlaneProviders:
    if not settings.marketlane_enabled:
        return MarketlaneProviders()
    return MarketlaneProviders(
        stock_quote_provider=MarketlaneQuoteProvider(
            timeout_seconds=settings.marketlane_quote_timeout_seconds,
            cache_ttl_seconds=settings.marketlane_quote_cache_ttl_seconds,
        )
    )


__all__ = ["wire_marketlane"]
