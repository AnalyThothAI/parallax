from __future__ import annotations

from gmgn_twitter_intel.app.runtime.provider_wiring import wire_asset_market_providers, wire_providers
from gmgn_twitter_intel.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    IngestionProviders,
    MacrodataProviders,
    NarrativeIntelProviders,
    NewsIntelProviders,
    PulseLabProviders,
    UpstreamClientFactory,
    WiredProviders,
)

__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "MacrodataProviders",
    "NarrativeIntelProviders",
    "NewsIntelProviders",
    "PulseLabProviders",
    "UpstreamClientFactory",
    "WiredProviders",
    "wire_asset_market_providers",
    "wire_providers",
]
