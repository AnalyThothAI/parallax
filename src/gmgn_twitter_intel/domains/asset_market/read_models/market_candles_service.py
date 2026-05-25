from __future__ import annotations

from typing import Any


class MarketCandlesService:
    def enrich_market_candles(self, payload: dict[str, Any] | None, *, window: str) -> dict[str, Any]:
        base = dict(payload) if isinstance(payload, dict) else {"status": "missing"}
        bar, _ = _window_candle_query(window)
        target_type = _text(base.get("target_type"))
        if target_type == "CexToken":
            return _cex_anchor_candles(base, bar=bar)
        if target_type == "Asset":
            return _dex_anchor_candles(base, bar=bar)
        return _anchor_candles(base, status="missing_target", bar=bar, source=None)


def _cex_anchor_candles(payload: dict[str, Any], *, bar: str) -> dict[str, Any]:
    if not _text(payload.get("native_market_id")):
        return _anchor_candles(payload, status="missing_market_id", bar=bar, source=None)
    return _anchor_candles(payload, status="unsupported", bar=bar, source=None)


def _dex_anchor_candles(payload: dict[str, Any], *, bar: str) -> dict[str, Any]:
    if not _text(payload.get("chain_id")) or not _text(payload.get("address")):
        return _anchor_candles(payload, status="missing_identity", bar=bar, source=None)
    return _anchor_candles(payload, status="unsupported", bar=bar, source=None)


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
