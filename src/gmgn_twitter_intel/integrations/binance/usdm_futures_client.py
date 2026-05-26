from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

PROVIDER = "binance"
FEED_TYPE = "cex_swap"
QUOTE_SYMBOL = "USDT"

_EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
_TICKER_24HR_PATH = "/fapi/v1/ticker/24hr"
_PREMIUM_INDEX_PATH = "/fapi/v1/premiumIndex"
_OPEN_INTEREST_HIST_PATH = "/futures/data/openInterestHist"
_TICKER_PRICE_PATH = "/fapi/v1/ticker/price"
_KLINES_PATH = "/fapi/v1/klines"


class BinanceUsdmFuturesClientError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BinanceUsdmRoute:
    provider: str
    feed_type: str
    quote_symbol: str
    native_market_id: str
    base_symbol: str
    multiplier: float | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BinanceUsdmTicker24hr:
    symbol: str
    last_price: float | None
    price_change_percent: float | None
    volume_24h: float | None
    quote_volume_24h: float | None
    open_time_ms: int | None
    close_time_ms: int | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BinanceUsdmPremiumIndex:
    symbol: str
    mark_price: float | None
    index_price: float | None
    last_funding_rate: float | None
    next_funding_time_ms: int | None
    time_ms: int | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BinanceUsdmOpenInterestHist:
    symbol: str
    period: str
    open_interest: float | None
    open_interest_value: float | None
    time_ms: int | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BinanceUsdmTicker:
    symbol: str
    price: float | None
    time_ms: int | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BinanceUsdmCandle:
    symbol: str
    interval: str
    open_time_ms: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    close_time_ms: int | None
    quote_volume: float | None
    trade_count: int | None
    taker_buy_base_volume: float | None
    taker_buy_quote_volume: float | None
    raw: list[Any]


class BinanceUsdmFuturesClient:
    def __init__(
        self,
        *,
        base_url: str = "https://fapi.binance.com",
        timeout_seconds: float = 15.0,
        http_client: Any | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "gmgn-twitter-intel/1.0"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def exchange_info(self) -> dict[str, Any]:
        payload = self._get_json(_EXCHANGE_INFO_PATH)
        if not isinstance(payload, dict):
            raise BinanceUsdmFuturesClientError("Binance exchangeInfo returned invalid payload")
        return payload

    def usdt_perpetual_routes(self) -> list[BinanceUsdmRoute]:
        symbols = self.exchange_info().get("symbols")
        if not isinstance(symbols, list):
            return []
        routes = [_route_from_exchange_symbol(row) for row in symbols if isinstance(row, dict)]
        return sorted((route for route in routes if route is not None), key=lambda route: route.native_market_id)

    def ticker_24hr(self, symbol: str | None = None) -> BinanceUsdmTicker24hr | list[BinanceUsdmTicker24hr]:
        payload = self._get_json(_TICKER_24HR_PATH, params=_optional_symbol_params(symbol))
        if isinstance(payload, list):
            return [_ticker_24hr_from_row(row) for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return _ticker_24hr_from_row(payload)
        raise BinanceUsdmFuturesClientError("Binance ticker/24hr returned invalid payload")

    def premium_index(
        self,
        symbol: str | None = None,
    ) -> BinanceUsdmPremiumIndex | list[BinanceUsdmPremiumIndex]:
        payload = self._get_json(_PREMIUM_INDEX_PATH, params=_optional_symbol_params(symbol))
        if isinstance(payload, list):
            return [_premium_index_from_row(row) for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return _premium_index_from_row(payload)
        raise BinanceUsdmFuturesClientError("Binance premiumIndex returned invalid payload")

    def open_interest_hist(self, symbol: str, period: str, limit: int) -> list[BinanceUsdmOpenInterestHist]:
        normalized_period = _period(period)
        params = {
            "symbol": _symbol(symbol),
            "period": normalized_period,
            "limit": str(_limit(limit, maximum=500)),
        }
        payload = self._get_json(_OPEN_INTEREST_HIST_PATH, params=params)
        if not isinstance(payload, list):
            raise BinanceUsdmFuturesClientError("Binance openInterestHist returned invalid payload")
        return [_open_interest_hist_from_row(row, period=normalized_period) for row in payload if isinstance(row, dict)]

    def ticker(self, symbol: str) -> BinanceUsdmTicker:
        payload = self._get_json(_TICKER_PRICE_PATH, params={"symbol": _symbol(symbol)})
        if not isinstance(payload, dict):
            raise BinanceUsdmFuturesClientError("Binance ticker/price returned invalid payload")
        return _ticker_from_row(payload)

    def candles(self, symbol: str, interval: str, limit: int) -> list[BinanceUsdmCandle]:
        normalized_symbol = _symbol(symbol)
        normalized_interval = _interval(interval)
        params = {
            "symbol": normalized_symbol,
            "interval": normalized_interval,
            "limit": str(_limit(limit, maximum=1500)),
        }
        payload = self._get_json(_KLINES_PATH, params=params)
        if not isinstance(payload, list):
            raise BinanceUsdmFuturesClientError("Binance klines returned invalid payload")
        candles: list[BinanceUsdmCandle] = []
        for row in payload:
            candle = _candle_from_row(row, symbol=normalized_symbol, interval=normalized_interval)
            if candle is not None:
                candles.append(candle)
        return candles

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        response = self._client.get(path, params=params)
        if response.status_code >= 400:
            raise BinanceUsdmFuturesClientError(f"Binance {path} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise BinanceUsdmFuturesClientError(f"Binance {path} returned non-json response") from exc


def _route_from_exchange_symbol(row: dict[str, Any]) -> BinanceUsdmRoute | None:
    status = _text(row.get("status"))
    contract_type = _text(row.get("contractType"))
    quote = _text(row.get("quoteAsset"))
    symbol = _text(row.get("symbol"))
    base = _text(row.get("baseAsset"))
    if status != "TRADING" or contract_type != "PERPETUAL" or quote != QUOTE_SYMBOL:
        return None
    if not symbol or not base:
        return None
    return BinanceUsdmRoute(
        provider=PROVIDER,
        feed_type=FEED_TYPE,
        quote_symbol=QUOTE_SYMBOL,
        native_market_id=symbol,
        base_symbol=base,
        multiplier=_float(row.get("contractSize") or row.get("multiplier")),
        raw=dict(row),
    )


def _ticker_24hr_from_row(row: dict[str, Any]) -> BinanceUsdmTicker24hr:
    return BinanceUsdmTicker24hr(
        symbol=_symbol(row.get("symbol")),
        last_price=_float(row.get("lastPrice")),
        price_change_percent=_float(row.get("priceChangePercent")),
        volume_24h=_float(row.get("volume")),
        quote_volume_24h=_float(row.get("quoteVolume")),
        open_time_ms=_int(row.get("openTime")),
        close_time_ms=_int(row.get("closeTime")),
        raw=dict(row),
    )


def _premium_index_from_row(row: dict[str, Any]) -> BinanceUsdmPremiumIndex:
    return BinanceUsdmPremiumIndex(
        symbol=_symbol(row.get("symbol")),
        mark_price=_float(row.get("markPrice")),
        index_price=_float(row.get("indexPrice")),
        last_funding_rate=_float(row.get("lastFundingRate")),
        next_funding_time_ms=_int(row.get("nextFundingTime")),
        time_ms=_int(row.get("time")),
        raw=dict(row),
    )


def _open_interest_hist_from_row(row: dict[str, Any], *, period: str) -> BinanceUsdmOpenInterestHist:
    return BinanceUsdmOpenInterestHist(
        symbol=_symbol(row.get("symbol")),
        period=period,
        open_interest=_float(row.get("sumOpenInterest")),
        open_interest_value=_float(row.get("sumOpenInterestValue")),
        time_ms=_int(row.get("timestamp")),
        raw=dict(row),
    )


def _ticker_from_row(row: dict[str, Any]) -> BinanceUsdmTicker:
    return BinanceUsdmTicker(
        symbol=_symbol(row.get("symbol")),
        price=_float(row.get("price")),
        time_ms=_int(row.get("time")),
        raw=dict(row),
    )


def _candle_from_row(row: Any, *, symbol: str, interval: str) -> BinanceUsdmCandle | None:
    if not isinstance(row, (list, tuple)) or len(row) < 11:
        return None
    open_time_ms = _int(row[0])
    if open_time_ms is None:
        return None
    return BinanceUsdmCandle(
        symbol=symbol,
        interval=interval,
        open_time_ms=open_time_ms,
        open=_float(row[1]),
        high=_float(row[2]),
        low=_float(row[3]),
        close=_float(row[4]),
        volume=_float(row[5]),
        close_time_ms=_int(row[6]),
        quote_volume=_float(row[7]),
        trade_count=_int(row[8]),
        taker_buy_base_volume=_float(row[9]),
        taker_buy_quote_volume=_float(row[10]),
        raw=list(row),
    )


def _optional_symbol_params(symbol: str | None) -> dict[str, str] | None:
    return {"symbol": _symbol(symbol)} if symbol is not None else None


def _symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise BinanceUsdmFuturesClientError("Binance symbol is required")
    return text


def _period(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise BinanceUsdmFuturesClientError("Binance open-interest period is required")
    return text


def _interval(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise BinanceUsdmFuturesClientError("Binance candle interval is required")
    return text


def _limit(value: Any, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 100
    return max(1, min(maximum, parsed))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
