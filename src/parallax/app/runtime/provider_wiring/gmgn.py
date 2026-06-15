from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from parallax.app.runtime.provider_wiring.types import UpstreamClientFactory
from parallax.domains.asset_market.providers import (
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
    DexTokenQuote,
    DexTokenQuoteRequest,
    MarketCandle,
    MarketCapability,
    ProviderHealth,
)
from parallax.domains.ingestion.providers import UpstreamClientProtocol
from parallax.integrations.gmgn.direct_ws import DirectGmgnWebSocketClient
from parallax.integrations.gmgn.openapi_client import (
    GmgnOpenApiClient,
    GmgnOpenApiProviderUnavailableError,
    GmgnTokenInfoLookup,
)
from parallax.integrations.gmgn.openapi_gateway import GmgnOpenApiGateway
from parallax.platform.config.settings import Settings

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class GmgnDexMarketProvider:
    def __init__(self, gateway: GmgnOpenApiGateway) -> None:
        self._gateway = gateway

    def token_quotes(self, tokens: list[DexTokenQuoteRequest]) -> list[DexTokenQuote]:
        observed_at_ms = int(time.time() * 1000)
        quotes: list[DexTokenQuote] = []
        for token in tokens:
            lookup = self._lookup_token_info(chain_id=token.chain_id, address=token.address)
            info = lookup.info
            if info is None:
                continue
            raw = {**info.raw, "cache_status": lookup.cache_status, "source_provider": "gmgn_dex_quote"}
            raw_price_payload = raw.get("price")
            price_payload: dict[str, Any] = raw_price_payload if isinstance(raw_price_payload, dict) else {}
            quotes.append(
                DexTokenQuote(
                    chain_id=info.chain,
                    address=_normalize_address(info.address),
                    observed_at_ms=observed_at_ms,
                    price_usd=info.price,
                    raw=raw,
                    market_cap_usd=info.market_cap,
                    liquidity_usd=info.liquidity,
                    volume_24h_usd=_number_from_mapping(
                        {**price_payload, **info.raw},
                        "volume_24h_usd",
                        "volume24hUsd",
                        "volume_24h",
                    ),
                    holders=info.holder_count,
                )
            )
        return quotes

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int) -> list[MarketCandle]:
        try:
            candles = self._gateway.token_kline(chain=chain_id, address=address, resolution=bar, limit=limit)
        except GmgnOpenApiProviderUnavailableError as exc:
            raise DexProviderTemporarilyUnavailable(str(exc)) from exc
        return [
            MarketCandle(
                time_ms=candle.time_ms,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                volume_quote=None,
                volume_usd=candle.volume_usd,
                confirmed=None,
                raw=candle.raw,
            )
            for candle in candles
        ]

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        info = self._lookup_token_info(chain_id=chain_id, address=address).info
        if info is None:
            return None
        return DexTokenProfile(
            chain_id=info.chain,
            address=_normalize_address(info.address),
            symbol=info.symbol,
            name=info.name,
            logo_url=info.icon_url,
            banner_url=info.banner_url,
            website=info.website,
            twitter_username=info.twitter_username,
            telegram=info.telegram,
            gmgn_url=info.gmgn_url,
            geckoterminal_url=info.geckoterminal_url,
            description=info.description,
            raw=info.raw,
        )

    def _lookup_token_info(self, *, chain_id: str, address: str) -> GmgnTokenInfoLookup:
        try:
            return self._gateway.lookup_token_info(chain=chain_id, address=address)
        except GmgnOpenApiProviderUnavailableError as exc:
            raise DexProviderTemporarilyUnavailable(str(exc)) from exc

    def close(self) -> None:
        self._gateway.close()


def gmgn_dex_market(settings: Settings) -> GmgnDexMarketProvider:
    return GmgnDexMarketProvider(
        GmgnOpenApiGateway(
            GmgnOpenApiClient(
                api_key=settings.gmgn_api_key or "",
                base_url=settings.gmgn_openapi_base_url,
                timeout_seconds=settings.gmgn_timeout_seconds,
            ),
            token_info_cache_ttl_seconds=settings.gmgn_token_info_cache_ttl_seconds,
        )
    )


def gmgn_provider_health(settings: Settings) -> ProviderHealth:
    capabilities = (
        frozenset(
            {
                MarketCapability.QUOTE_DEX_EXACT,
                MarketCapability.PROFILE_DEX_EXACT,
                MarketCapability.CANDLES_DEX_EXACT,
            }
        )
        if settings.gmgn_configured
        else frozenset()
    )
    return ProviderHealth(provider="gmgn", capabilities=capabilities, configured=settings.gmgn_configured)


def gmgn_upstream_factory(settings: Settings) -> UpstreamClientFactory:
    def factory(on_frame: Callable[[str], Awaitable[None]]) -> UpstreamClientProtocol:
        return DirectGmgnWebSocketClient(
            app_version=settings.upstream_app_version,
            channels=list(settings.upstream_channels),
            chains=list(settings.upstream_chains),
            proxy=settings.upstream_proxy,
            reconnect_delay=settings.upstream_reconnect_delay,
            heartbeat_interval=settings.upstream_heartbeat_interval,
            idle_timeout=settings.upstream_idle_timeout,
            on_frame=on_frame,
        )

    return factory


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if EVM_ADDRESS_RE.match(text) else text


def _number_from_mapping(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


__all__ = [
    "GmgnDexMarketProvider",
    "gmgn_dex_market",
    "gmgn_provider_health",
    "gmgn_upstream_factory",
]
