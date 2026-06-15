from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from parallax.domains.asset_market.providers import (
    CexMarketProvider,
    DexMarketStreamProvider,
    DexProfileSource,
    DexTokenCandleProvider,
    DexTokenDiscoveryProvider,
    DexTokenQuoteProvider,
    ProviderHealth,
)
from parallax.domains.cex_market_intel.providers import CexOiMarketProvider, CoinglassDerivativesProvider
from parallax.domains.ingestion.providers import UpstreamClientProtocol
from parallax.domains.news_intel.providers import NewsItemBriefProvider, NewsSourceProvider
from parallax.domains.pulse_lab.providers import PulseDecisionProvider

UpstreamClientFactory = Callable[[Callable[[str], Awaitable[None]]], UpstreamClientProtocol | None]


class _SyncClosable(Protocol):
    def close(self) -> None: ...


class _AsyncClosable(Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class IngestionProviders:
    upstream_client_factory: UpstreamClientFactory | None = None

    async def aclose(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class AssetMarketProviders:
    cex_market: CexMarketProvider | None = None
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    dex_quote_market: DexTokenQuoteProvider | None = None
    dex_candle_market: DexTokenCandleProvider | None = None
    dex_profile_sources: tuple[DexProfileSource, ...] = ()
    stream_dex_market: DexMarketStreamProvider | None = None
    discovery_chain_ids: tuple[str, ...] = ()
    provider_health: tuple[ProviderHealth, ...] = ()

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        _close_sync_provider(errors, seen, self.cex_market)
        _close_sync_provider(errors, seen, self.dex_discovery_market)
        _close_sync_provider(errors, seen, self.dex_quote_market)
        _close_sync_provider(errors, seen, self.dex_candle_market)
        for source in self.dex_profile_sources:
            _close_sync_provider(errors, seen, source.market)
        await _close_async_provider(errors, seen, self.stream_dex_market)
        if errors:
            raise ExceptionGroup("asset_market_provider_cleanup_failed", errors)


@dataclass(frozen=True, slots=True)
class CexMarketIntelProviders:
    oi_market: CexOiMarketProvider | None = None
    coinglass_derivatives: CoinglassDerivativesProvider | None = None

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        _close_sync_provider(errors, seen, self.oi_market)
        if errors:
            raise ExceptionGroup("cex_market_intel_provider_cleanup_failed", errors)


@dataclass(frozen=True, slots=True)
class OkxProviderBundle:
    dex_discovery_market: DexTokenDiscoveryProvider | None
    dex_quote_market: DexTokenQuoteProvider | None
    stream_dex_market: DexMarketStreamProvider | None
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class PulseLabProviders:
    decision_provider: PulseDecisionProvider | None = None

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        await _close_async_provider(errors, seen, self.decision_provider)
        if errors:
            raise ExceptionGroup("pulse_lab_provider_cleanup_failed", errors)


@dataclass(frozen=True, slots=True)
class NewsIntelProviders:
    feed_client: NewsSourceProvider | None = None
    brief_provider: NewsItemBriefProvider | None = None

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        _close_sync_provider(errors, seen, self.feed_client)
        await _close_async_provider(errors, seen, self.brief_provider)
        if errors:
            raise ExceptionGroup("news_intel_provider_cleanup_failed", errors)


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    cex_market_intel: CexMarketIntelProviders
    news_intel: NewsIntelProviders
    pulse_lab: PulseLabProviders
    agent_execution_gateway: object | None = None

    async def aclose(self) -> None:
        errors: list[Exception] = []
        for providers in (
            self.ingestion,
            self.asset_market,
            self.cex_market_intel,
            self.news_intel,
            self.pulse_lab,
        ):
            try:
                await providers.aclose()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("wired_provider_cleanup_failed", errors)


def _close_sync_provider(errors: list[Exception], seen: set[int], provider: _SyncClosable | None) -> None:
    if provider is None:
        return
    object_id = id(provider)
    if object_id in seen:
        return
    seen.add(object_id)
    try:
        provider.close()
    except Exception as exc:
        errors.append(exc)


async def _close_async_provider(errors: list[Exception], seen: set[int], provider: _AsyncClosable | None) -> None:
    if provider is None:
        return
    object_id = id(provider)
    if object_id in seen:
        return
    seen.add(object_id)
    try:
        await provider.aclose()
    except Exception as exc:
        errors.append(exc)


__all__ = [
    "AssetMarketProviders",
    "CexMarketIntelProviders",
    "IngestionProviders",
    "NewsIntelProviders",
    "OkxProviderBundle",
    "PulseLabProviders",
    "UpstreamClientFactory",
    "WiredProviders",
]
