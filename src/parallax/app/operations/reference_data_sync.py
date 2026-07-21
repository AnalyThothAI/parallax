from __future__ import annotations

import time
from typing import Any

from parallax.app.runtime.repository_session import repositories
from parallax.domains.asset_market.services.asset_market_sync import (
    BinanceUsdtPerpRoute,
    sync_binance_usdt_perp_routes,
)
from parallax.domains.asset_market.services.cex_token_profile_sync import sync_cex_token_profiles
from parallax.domains.asset_market.services.us_equity_symbol_sync import (
    NasdaqTraderSymbolClient,
    sync_us_equity_symbols,
)
from parallax.integrations.binance.cex_profile_client import BinanceCexProfileClient
from parallax.integrations.binance.usdm_futures_client import BinanceUsdmFuturesClient, BinanceUsdmRoute
from parallax.platform.config.settings import Settings


def sync_binance_usdt_perp_universe(
    settings: Settings,
    *,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    """Fetch Binance routes, close the transport, then update reference facts."""
    client = BinanceUsdmFuturesClient(
        base_url=settings.providers.binance.usdm_futures_base_url,
        timeout_seconds=settings.providers.binance.timeout_seconds,
    )
    try:
        routes = [_to_domain_route(route) for route in client.usdt_perpetual_routes()]
    finally:
        client.close()
    with repositories(settings) as repos:
        return sync_binance_usdt_perp_routes(
            repos=repos,
            routes=routes,
            observed_at_ms=_now_ms(),
            dry_run=bool(dry_run),
            execute=bool(execute),
        )


def sync_binance_cex_profiles_once(settings: Settings) -> dict[str, Any]:
    """Fetch Binance profile observations before opening a DB transaction."""
    client = BinanceCexProfileClient(
        base_url=settings.providers.binance.cex_profile_base_url,
        timeout_seconds=settings.providers.binance.timeout_seconds,
    )
    try:
        profiles = client.token_profiles()
    finally:
        client.close()
    with repositories(settings) as repos:
        return sync_cex_token_profiles(
            repos=repos,
            profiles=profiles,
            observed_at_ms=_now_ms(),
        )


def sync_us_equity_symbols_once(settings: Settings) -> dict[str, Any]:
    """Fetch Nasdaq Trader symbols before opening a DB transaction."""
    client = NasdaqTraderSymbolClient(timeout_seconds=settings.providers.okx.timeout_seconds)
    try:
        symbols = client.symbols()
    finally:
        client.close()
    with repositories(settings) as repos:
        return sync_us_equity_symbols(
            repos=repos,
            symbols=symbols,
            observed_at_ms=_now_ms(),
        )


def _to_domain_route(route: BinanceUsdmRoute) -> BinanceUsdtPerpRoute:
    if not isinstance(route, BinanceUsdmRoute):
        raise RuntimeError("binance_usdm_route_contract_required")
    return BinanceUsdtPerpRoute(
        native_market_id=route.native_market_id,
        base_symbol=route.base_symbol,
        quote_symbol=route.quote_symbol,
        multiplier=route.multiplier,
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "sync_binance_cex_profiles_once",
    "sync_binance_usdt_perp_universe",
    "sync_us_equity_symbols_once",
]
