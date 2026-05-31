from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from macrodata.core.errors import MacrodataError  # type: ignore[import-untyped]
from macrodata.providers.yahoo import YahooPriceProvider  # type: ignore[import-untyped]


class MacrodataQuoteProvider:
    def __init__(self, *, timeout_seconds: float, cache_ttl_seconds: float) -> None:
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._provider = YahooPriceProvider(timeout_sec=self.timeout_seconds)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def quote(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        now = time.monotonic()
        cached = self._cache.get(normalized_symbol)
        if cached is not None and cached[0] > now:
            return dict(cached[1])
        quote = self._quote(normalized_symbol)
        if self.cache_ttl_seconds > 0:
            self._cache[normalized_symbol] = (now + self.cache_ttl_seconds, quote)
        return dict(quote)

    def _quote(self, symbol: str) -> dict[str, Any]:
        end = datetime.now(UTC).date() + timedelta(days=1)
        start = end - timedelta(days=14)
        try:
            observations = self._provider.get_range(symbol, start=start.isoformat(), end=end.isoformat())
        except MacrodataError as exc:
            return _unavailable_quote(symbol=symbol, error=exc.code)
        if not observations:
            return _unavailable_quote(symbol=symbol, error="no_data")
        latest = observations[-1]
        previous = observations[-2] if len(observations) >= 2 else None
        price = float(latest.value)
        reference_close_price = float(previous.value) if previous is not None else None
        change_pct = None
        if reference_close_price:
            change_pct = (price - reference_close_price) / reference_close_price
        return {
            "status": "ready",
            "price": price,
            "reference_close_price": reference_close_price,
            "change_pct": change_pct,
            "asof": latest.observed_at,
            "provider": latest.provider,
            "provider_symbol": latest.dataset,
            "latency_class": latest.latency_class,
            "freshness_class": latest.latency_class,
            "error": None,
        }


def _unavailable_quote(*, symbol: str, error: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "price": None,
        "reference_close_price": None,
        "change_pct": None,
        "asof": None,
        "provider": "yahoo",
        "provider_symbol": symbol,
        "latency_class": "daily",
        "freshness_class": "daily",
        "error": error,
    }
