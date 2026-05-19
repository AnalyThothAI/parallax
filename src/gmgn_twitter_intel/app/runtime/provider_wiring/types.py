from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    CexMarketProvider,
    DexMarketStreamProvider,
    DexProfileSource,
    DexTokenDiscoveryProvider,
    DexTokenQuoteProvider,
    ProviderHealth,
)
from gmgn_twitter_intel.domains.ingestion.providers import UpstreamClientProtocol
from gmgn_twitter_intel.domains.news_intel.providers import NewsFeedProvider
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionProvider
from gmgn_twitter_intel.domains.social_enrichment.providers import SocialEventEnrichmentProvider

UpstreamClientFactory = Callable[[Callable[..., Any]], UpstreamClientProtocol | None]


@dataclass(frozen=True, slots=True)
class IngestionProviders:
    upstream_client_factory: UpstreamClientFactory | None = None


@dataclass(frozen=True, slots=True)
class AssetMarketProviders:
    sync_cex_market: CexMarketProvider | None = None
    message_cex_market: CexMarketProvider | None = None
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    dex_quote_market: DexTokenQuoteProvider | None = None
    dex_candle_market: object | None = None
    dex_profile_sources: tuple[DexProfileSource, ...] = ()
    stream_dex_market: DexMarketStreamProvider | None = None
    discovery_chain_ids: tuple[str, ...] = ()
    provider_health: tuple[ProviderHealth, ...] = ()


@dataclass(frozen=True, slots=True)
class OkxProviderBundle:
    sync_cex_market: CexMarketProvider | None
    message_cex_market: CexMarketProvider | None
    dex_discovery_market: DexTokenDiscoveryProvider | None
    dex_quote_market: DexTokenQuoteProvider | None
    stream_dex_market: DexMarketStreamProvider | None
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class SocialEnrichmentProviders:
    event_enrichment: SocialEventEnrichmentProvider | None = None


@dataclass(frozen=True, slots=True)
class PulseLabProviders:
    decision_provider: PulseDecisionProvider | None = None


@dataclass(frozen=True, slots=True)
class NarrativeIntelProviders:
    narrative_provider: Any | None = None


@dataclass(frozen=True, slots=True)
class NewsIntelProviders:
    feed_client: NewsFeedProvider | None = None


@dataclass(frozen=True, slots=True)
class WatchlistIntelProviders:
    summary_provider: object | None = None


@dataclass(frozen=True, slots=True)
class MarketlaneProviders:
    stock_quote_provider: object | None = None


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    social_enrichment: SocialEnrichmentProviders
    narrative_intel: NarrativeIntelProviders
    news_intel: NewsIntelProviders
    pulse_lab: PulseLabProviders
    watchlist_intel: WatchlistIntelProviders
    marketlane: MarketlaneProviders
    agent_execution_gateway: object | None = None


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "MarketlaneProviders",
    "NarrativeIntelProviders",
    "NewsIntelProviders",
    "OkxProviderBundle",
    "PulseLabProviders",
    "SocialEnrichmentProviders",
    "UpstreamClientFactory",
    "WatchlistIntelProviders",
    "WiredProviders",
]
