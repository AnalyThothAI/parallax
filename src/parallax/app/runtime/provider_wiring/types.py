from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from parallax.domains.asset_market.providers import (
    CexMarketProvider,
    DexMarketStreamProvider,
    DexProfileSource,
    DexTokenDiscoveryProvider,
    DexTokenQuoteProvider,
    ProviderHealth,
)
from parallax.domains.ingestion.providers import UpstreamClientProtocol
from parallax.domains.news_intel.providers import NewsItemBriefProvider, NewsSourceProvider
from parallax.domains.pulse_lab.providers import PulseDecisionProvider

UpstreamClientFactory = Callable[[Callable[..., Any]], UpstreamClientProtocol | None]


@dataclass(frozen=True, slots=True)
class IngestionProviders:
    upstream_client_factory: UpstreamClientFactory | None = None


@dataclass(frozen=True, slots=True)
class AssetMarketProviders:
    cex_market: CexMarketProvider | None = None
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    dex_quote_market: DexTokenQuoteProvider | None = None
    dex_candle_market: object | None = None
    dex_profile_sources: tuple[DexProfileSource, ...] = ()
    stream_dex_market: DexMarketStreamProvider | None = None
    discovery_chain_ids: tuple[str, ...] = ()
    provider_health: tuple[ProviderHealth, ...] = ()


@dataclass(frozen=True, slots=True)
class OkxProviderBundle:
    dex_discovery_market: DexTokenDiscoveryProvider | None
    dex_quote_market: DexTokenQuoteProvider | None
    stream_dex_market: DexMarketStreamProvider | None
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class PulseLabProviders:
    decision_provider: PulseDecisionProvider | None = None


@dataclass(frozen=True, slots=True)
class NarrativeIntelProviders:
    narrative_provider: Any | None = None


@dataclass(frozen=True, slots=True)
class NewsIntelProviders:
    feed_client: NewsSourceProvider | None = None
    brief_provider: NewsItemBriefProvider | None = None


@dataclass(frozen=True, slots=True)
class MacrodataProviders:
    stock_quote_provider: object | None = None


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    narrative_intel: NarrativeIntelProviders
    news_intel: NewsIntelProviders
    pulse_lab: PulseLabProviders
    macrodata: MacrodataProviders
    agent_execution_gateway: object | None = None


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "MacrodataProviders",
    "NarrativeIntelProviders",
    "NewsIntelProviders",
    "OkxProviderBundle",
    "PulseLabProviders",
    "UpstreamClientFactory",
    "WiredProviders",
]
