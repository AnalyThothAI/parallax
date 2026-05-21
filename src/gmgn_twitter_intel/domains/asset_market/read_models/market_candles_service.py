from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import MarketCandle


class MarketCandlesService:
    def __init__(self, *, cex_market: Any | None, dex_candle_market: Any | None) -> None:
        self.cex_market = cex_market
        self.dex_candle_market = dex_candle_market

    def enrich_market_candles(self, payload: dict[str, Any] | None, *, window: str) -> dict[str, Any]:
        base = dict(payload) if isinstance(payload, dict) else {"status": "missing"}
        bar, limit = _window_candle_query(window)
        target_type = _text(base.get("target_type"))
        if target_type == "CexToken":
            return self._enrich_cex_candles(base, bar=bar, limit=limit)
        if target_type == "Asset":
            return self._enrich_dex_candles(base, bar=bar, limit=limit)
        return _anchor_candles(base, status="missing_target", bar=bar, source=None)

    def _enrich_cex_candles(self, payload: dict[str, Any], *, bar: str, limit: int) -> dict[str, Any]:
        inst_id = _text(payload.get("native_market_id"))
        if not inst_id:
            return _anchor_candles(payload, status="missing_market_id", bar=bar, source="binance_cex_candles")
        candles = getattr(self.cex_market, "candles", None)
        if not candles:
            return _anchor_candles(payload, status="unsupported", bar=bar, source="binance_cex_candles")
        try:
            rows = candles(inst_id=inst_id, bar=bar, limit=limit)
        except Exception as exc:
            return _anchor_candles(
                payload,
                status="error",
                bar=bar,
                source="binance_cex_candles",
                error=type(exc).__name__,
            )
        return _ohlc_candles(payload, candles=rows, bar=bar, source="binance_cex_candles")

    def _enrich_dex_candles(self, payload: dict[str, Any], *, bar: str, limit: int) -> dict[str, Any]:
        chain_id = _text(payload.get("chain_id"))
        address = _text(payload.get("address"))
        if not chain_id or not address:
            return _anchor_candles(payload, status="missing_identity", bar=bar, source="gmgn_dex_candles")
        if self.dex_candle_market is None:
            return _anchor_candles(payload, status="unsupported", bar=bar, source="gmgn_dex_candles")
        try:
            rows = self.dex_candle_market.token_candles(chain_id=chain_id, address=address, bar=bar, limit=limit)
        except Exception as exc:
            return _anchor_candles(
                payload,
                status="error",
                bar=bar,
                source="gmgn_dex_candles",
                error=type(exc).__name__,
            )
        return _ohlc_candles(payload, candles=rows, bar=bar, source="gmgn_dex_candles")


def _ohlc_candles(
    payload: dict[str, Any],
    *,
    candles: list[MarketCandle],
    bar: str,
    source: str,
) -> dict[str, Any]:
    serialized = sorted(
        [_candle_payload(candle) for candle in candles if _has_ohlc(candle)],
        key=lambda candle: int(candle["time_ms"]),
    )
    if not serialized:
        return _anchor_candles(payload, status="empty", bar=bar, source=source)
    return {
        **payload,
        "price_series_type": "ohlc",
        "candle_status": "ready",
        "candle_source": source,
        "candle_bar": bar,
        "candles": serialized,
    }


def _anchor_candles(
    payload: dict[str, Any],
    *,
    status: str,
    bar: str,
    source: str | None,
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        **payload,
        "price_series_type": str(payload.get("price_series_type") or "anchor_line"),
        "candle_status": status,
        "candle_bar": bar,
        "candles": [],
    }
    if source:
        payload["candle_source"] = source
    if error:
        payload["candle_error"] = error
    return payload


def _candle_payload(candle: MarketCandle) -> dict[str, Any]:
    return {
        "time_ms": int(candle.time_ms),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "volume_quote": candle.volume_quote,
        "volume_usd": candle.volume_usd,
        "confirmed": candle.confirmed,
    }


def _has_ohlc(candle: MarketCandle) -> bool:
    return all(value is not None for value in (candle.open, candle.high, candle.low, candle.close))


def _window_candle_query(window: str) -> tuple[str, int]:
    if window == "5m":
        return "1m", 10
    if window == "1h":
        return "5m", 24
    if window == "4h":
        return "15m", 32
    return "1H", 48


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
