from __future__ import annotations

from parallax.app.runtime.provider_wiring import wire_asset_market_providers, wire_providers
from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    CexMarketIntelProviders,
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
    "CexMarketIntelProviders",
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
