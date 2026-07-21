from __future__ import annotations

import math
import re
from typing import Any

from parallax.domains.asset_market.providers import (
    CexTicker,
    DexTokenProfile,
    MarketCandle,
    MarketCapability,
    ProviderHealth,
)
from parallax.domains.cex_market_intel.providers import (
    CexFundingPremium,
    CexOiTicker24h,
    CexOpenInterestPoint,
)
from parallax.integrations.binance.usdm_futures_client import (
    BinanceUsdmFuturesClient,
    BinanceUsdmTicker24hr,
)
from parallax.integrations.binance.web3_token_client import BinanceWeb3TokenClient
from parallax.platform.config.settings import Settings

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class BinanceWeb3DexProfileProvider:
    def __init__(self, client: BinanceWeb3TokenClient) -> None:
        self._client = client

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        metadata = self._client.token_metadata(chain_id=chain_id, address=address)
        if metadata is None:
            return None
        return DexTokenProfile(
            chain_id=metadata.chain_id,
            address=_normalize_address(metadata.address),
            symbol=metadata.symbol,
            name=metadata.name,
            logo_url=metadata.logo_url,
            banner_url=None,
            website=metadata.website,
            twitter_username=metadata.twitter_username,
            telegram=metadata.telegram,
            gmgn_url=None,
            geckoterminal_url=None,
            description=metadata.description,
            raw=metadata.raw,
        )

    def close(self) -> None:
        self._client.close()


class BinanceUsdmFuturesMarketProvider:
    def __init__(self, client: BinanceUsdmFuturesClient) -> None:
        self._client = client

    def tickers(self, *, inst_type: str) -> list[CexTicker]:
        if str(inst_type or "").strip().upper() not in {"SWAP", "PERP", "PERPETUAL"}:
            return []
        tickers = self._client.ticker_24hr()
        rows = tickers if isinstance(tickers, list) else [tickers]
        return [_cex_ticker(row) for row in rows]

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        ticker = self._client.ticker_24hr(symbol=inst_id)
        if isinstance(ticker, list):
            return _cex_ticker(ticker[0]) if ticker else None
        return _cex_ticker(ticker)

    def candles(self, *, inst_id: str, bar: str, limit: int) -> list[MarketCandle]:
        return [
            MarketCandle(
                time_ms=candle.open_time_ms,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                volume_quote=candle.quote_volume,
                volume_usd=candle.quote_volume,
                confirmed=True,
                raw=candle.raw,
            )
            for candle in self._client.candles(symbol=inst_id, interval=bar, limit=limit)
        ]

    def close(self) -> None:
        self._client.close()


class BinanceUsdmFuturesOiProvider:
    def __init__(self, client: BinanceUsdmFuturesClient) -> None:
        self._client = client

    def list_24h_tickers(self, symbol: str | None = None) -> list[CexOiTicker24h]:
        payload = self._client.ticker_24hr(symbol=symbol)
        rows = payload if isinstance(payload, list) else [payload]
        return [_cex_oi_ticker(row) for row in rows]

    def list_funding_premium(self, symbol: str | None = None) -> list[CexFundingPremium]:
        payload = self._client.premium_index(symbol=symbol)
        rows = payload if isinstance(payload, list) else [payload]
        return [_cex_funding_premium(row) for row in rows]

    def list_open_interest_history(self, symbol: str, period: str, limit: int) -> list[CexOpenInterestPoint]:
        return [
            CexOpenInterestPoint(
                symbol=_row_symbol(row),
                open_interest_value=_optional_row_float(row, "open_interest_value"),
                observed_at_ms=_optional_row_positive_int(row, "time_ms"),
            )
            for row in self._client.open_interest_hist(symbol=symbol, period=period, limit=limit)
        ]

    def close(self) -> None:
        self._client.close()


def binance_web3_profile_market(settings: Settings) -> BinanceWeb3DexProfileProvider:
    return BinanceWeb3DexProfileProvider(
        BinanceWeb3TokenClient(
            base_url=settings.binance_web3_base_url,
            timeout_seconds=settings.binance_timeout_seconds,
        )
    )


def binance_usdm_futures_market(settings: Settings) -> BinanceUsdmFuturesMarketProvider:
    return BinanceUsdmFuturesMarketProvider(
        BinanceUsdmFuturesClient(
            base_url=settings.binance_usdm_futures_base_url,
            timeout_seconds=settings.binance_timeout_seconds,
        )
    )


def binance_usdm_futures_oi_market(settings: Settings) -> BinanceUsdmFuturesOiProvider:
    return BinanceUsdmFuturesOiProvider(
        BinanceUsdmFuturesClient(
            base_url=settings.binance_usdm_futures_base_url,
            timeout_seconds=settings.binance_timeout_seconds,
        )
    )


def binance_provider_health(settings: Settings) -> ProviderHealth:
    capabilities = (
        frozenset({MarketCapability.PROFILE_CEX, MarketCapability.PROFILE_DEX_EXACT, MarketCapability.QUOTE_CEX})
        if settings.binance_enabled
        else frozenset()
    )
    return ProviderHealth(provider="binance", capabilities=capabilities, configured=settings.binance_enabled)


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if EVM_ADDRESS_RE.match(text) else text


def _cex_ticker(ticker: BinanceUsdmTicker24hr) -> CexTicker:
    return CexTicker(
        inst_id=ticker.symbol,
        inst_type="SWAP",
        last_price=ticker.last_price,
        volume_24h=ticker.quote_volume_24h,
        open_interest=None,
        raw=ticker.raw,
    )


def _cex_oi_ticker(row: Any) -> CexOiTicker24h:
    return CexOiTicker24h(
        symbol=_row_symbol(row),
        quote_volume_24h=_optional_row_float(row, "quote_volume_24h"),
        price_change_pct_24h=_optional_row_float(row, "price_change_percent"),
        last_price=_optional_row_float(row, "last_price"),
    )


def _cex_funding_premium(row: Any) -> CexFundingPremium:
    return CexFundingPremium(
        symbol=_row_symbol(row),
        mark_price=_optional_row_float(row, "mark_price"),
        last_funding_rate=_optional_row_float(row, "last_funding_rate"),
    )


def _row_symbol(row: Any) -> str:
    text = str(_required_row_field(row, "symbol") or "").strip().upper()
    if not text:
        raise ValueError("binance_oi_provider_contract_required:symbol")
    return text


def _required_row_field(row: Any, field: str) -> Any:
    try:
        return getattr(row, field)
    except AttributeError as exc:
        raise ValueError(f"binance_oi_provider_contract_required:{field}") from exc


def _optional_row_float(row: Any, field: str) -> float | None:
    value = _required_row_field(row, field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"binance_oi_provider_contract_required:{field}")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"binance_oi_provider_contract_required:{field}")
    return parsed


def _optional_row_positive_int(row: Any, field: str) -> int | None:
    value = _required_row_field(row, field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"binance_oi_provider_contract_required:{field}")
    return int(value)


__all__ = [
    "BinanceUsdmFuturesMarketProvider",
    "BinanceUsdmFuturesOiProvider",
    "BinanceWeb3DexProfileProvider",
    "binance_provider_health",
    "binance_usdm_futures_market",
    "binance_usdm_futures_oi_market",
    "binance_web3_profile_market",
]
