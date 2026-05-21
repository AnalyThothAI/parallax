from __future__ import annotations

from gmgn_twitter_intel.app.runtime.provider_wiring.types import MacrodataProviders
from gmgn_twitter_intel.integrations.macrodata import MacrodataQuoteProvider
from gmgn_twitter_intel.platform.config.settings import Settings


def wire_macrodata(settings: Settings) -> MacrodataProviders:
    if not settings.macrodata_enabled:
        return MacrodataProviders()
    return MacrodataProviders(
        stock_quote_provider=MacrodataQuoteProvider(
            timeout_seconds=settings.macrodata_quote_timeout_seconds,
            cache_ttl_seconds=settings.macrodata_quote_cache_ttl_seconds,
        )
    )


__all__ = ["wire_macrodata"]
