from __future__ import annotations

import asyncio
import time
from typing import Any


class MarketlaneQuoteProvider:
    def __init__(self, *, timeout_seconds: float, cache_ttl_seconds: float) -> None:
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._client: Any | None = None
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def quote(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        now = time.monotonic()
        cached = self._cache.get(normalized_symbol)
        if cached is not None and cached[0] > now:
            return dict(cached[1])
        payload = await asyncio.wait_for(
            self._client_instance().quote(normalized_symbol),
            timeout=self.timeout_seconds,
        )
        quote = _normalize_marketlane_quote(payload)
        if self.cache_ttl_seconds > 0:
            self._cache[normalized_symbol] = (now + self.cache_ttl_seconds, quote)
        return dict(quote)

    def _client_instance(self) -> Any:
        if self._client is None:
            from marketlane.client import AsyncMarketlaneClient  # type: ignore[import-untyped]

            self._client = AsyncMarketlaneClient()
        return self._client


def _normalize_marketlane_quote(payload: dict[str, Any]) -> dict[str, Any]:
    price = _float_or_none(payload.get("price"))
    reference_close_price = _float_or_none(payload.get("reference_close_price"))
    change_pct = None
    if price is not None and reference_close_price:
        change_pct = (price - reference_close_price) / reference_close_price
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    status = "ready" if price is not None else "unavailable"
    return {
        "status": status,
        "price": price,
        "reference_close_price": reference_close_price,
        "change_pct": change_pct,
        "asof": _str_or_none(payload.get("asof")),
        "provider": _str_or_none(payload.get("provider")),
        "provider_symbol": _str_or_none(payload.get("provider_symbol")),
        "latency_class": _str_or_none(payload.get("latency_class") or meta.get("freshness_class")),
        "freshness_class": _str_or_none(meta.get("freshness_class") or payload.get("latency_class")),
        "error": None if status == "ready" else "missing_price",
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
