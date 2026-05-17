from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    IngestionProviders,
    MarketlaneProviders,
    PulseLabProviders,
    SocialEnrichmentProviders,
    WatchlistIntelProviders,
    WiredProviders,
)
from gmgn_twitter_intel.platform.config.settings import Settings


def wire_providers(
    settings: Settings,
    *,
    start_collector: bool,
    llm_gateway: object | None = None,
    db_pool: Any | None = None,
) -> WiredProviders:
    from gmgn_twitter_intel.app.runtime.provider_wiring import asset_market, gmgn, marketlane, openai

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=asset_market.wire_asset_market(settings),
        social_enrichment=SocialEnrichmentProviders(
            event_enrichment=openai.openai_social_event_provider(settings, llm_gateway=llm_gateway)
            if settings.llm_configured
            else None,
        ),
        pulse_lab=PulseLabProviders(
            decision_provider=openai.openai_pulse_decision_provider(
                settings,
                llm_gateway=llm_gateway,
                db_pool=db_pool,
            )
            if settings.workers.pulse_candidate.enabled and settings.pulse_agent_configured
            else None,
        ),
        watchlist_intel=WatchlistIntelProviders(
            summary_provider=openai.openai_watchlist_summary_provider(settings, llm_gateway=llm_gateway)
            if settings.workers.handle_summary.enabled and settings.watchlist_handle_summary_configured
            else None,
        ),
        marketlane=marketlane.wire_marketlane(settings),
    )


def wire_asset_market_providers(settings: Settings, *, start_collector: bool) -> AssetMarketProviders:
    from gmgn_twitter_intel.app.runtime.provider_wiring import asset_market

    return asset_market.wire_asset_market_providers(settings, start_collector=start_collector)


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "MarketlaneProviders",
    "PulseLabProviders",
    "SocialEnrichmentProviders",
    "WatchlistIntelProviders",
    "WiredProviders",
    "wire_asset_market_providers",
    "wire_providers",
]
