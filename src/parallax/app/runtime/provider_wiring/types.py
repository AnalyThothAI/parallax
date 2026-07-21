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
from parallax.domains.ingestion.providers import UpstreamClientProtocol
from parallax.domains.news_intel.providers import NewsSourceProvider, NewsStoryBriefProvider

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
class OkxProviderBundle:
    dex_discovery_market: DexTokenDiscoveryProvider | None
    dex_quote_market: DexTokenQuoteProvider | None
    stream_dex_market: DexMarketStreamProvider | None
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class NewsIntelProviders:
    feed_client: NewsSourceProvider | None = None
    story_brief_provider: NewsStoryBriefProvider | None = None

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        _close_sync_provider(errors, seen, self.feed_client)
        await _close_async_provider(errors, seen, self.story_brief_provider)
        if errors:
            raise ExceptionGroup("news_intel_provider_cleanup_failed", errors)


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    news_intel: NewsIntelProviders

    async def aclose(self) -> None:
        errors: list[Exception] = []
        for providers in (
            self.ingestion,
            self.asset_market,
            self.news_intel,
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
    "IngestionProviders",
    "NewsIntelProviders",
    "OkxProviderBundle",
    "UpstreamClientFactory",
    "WiredProviders",
]
