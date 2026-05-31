from __future__ import annotations

from typing import Any

DEFAULT_PRICE_FRESH_MS = 5 * 60 * 1000
DEFAULT_MARKET_METADATA_FRESH_MS = 5 * 60 * 1000
RESOLUTION_MARKET_FRESH_MS = 24 * 60 * 60 * 1000

PROVIDER_OKX_DEX_SEARCH = "okx_dex_search"
PROVIDER_OKX_DEX_PRICE = "okx_dex_price"
PROVIDER_OKX_DEX_WS_PRICE_INFO = "okx_dex_ws_price_info"
PROVIDER_BINANCE_CEX = "binance_cex"

PRICE_CAPABLE_PROVIDERS = frozenset(
    {
        PROVIDER_OKX_DEX_SEARCH,
        PROVIDER_OKX_DEX_PRICE,
        PROVIDER_OKX_DEX_WS_PRICE_INFO,
        PROVIDER_BINANCE_CEX,
    }
)
DEX_METADATA_CAPABLE_PROVIDERS = frozenset(
    {
        PROVIDER_OKX_DEX_SEARCH,
        PROVIDER_OKX_DEX_WS_PRICE_INFO,
    }
)
CEX_MARKET_CAPABLE_PROVIDERS = frozenset({PROVIDER_BINANCE_CEX})
VOLUME_24H_CAPABLE_PROVIDERS = frozenset(
    {
        PROVIDER_BINANCE_CEX,
        PROVIDER_OKX_DEX_SEARCH,
        PROVIDER_OKX_DEX_WS_PRICE_INFO,
    }
)


def field_status(*, value: Any, observed_at_ms: int | None, now_ms: int, fresh_ms: int) -> str:
    if value is None or observed_at_ms is None:
        return "missing"
    age_ms = max(0, int(now_ms) - int(observed_at_ms))
    return "fresh" if age_ms <= int(fresh_ms) else "stale"


def field_fact(
    *,
    value: Any,
    observed_at_ms: int | None,
    now_ms: int,
    provider: str | None,
    observation_id: str | None,
    fresh_ms: int,
) -> dict[str, Any]:
    age_ms = max(0, int(now_ms) - int(observed_at_ms)) if observed_at_ms is not None else None
    return {
        "value": _json_number(value),
        "status": field_status(value=value, observed_at_ms=observed_at_ms, now_ms=now_ms, fresh_ms=fresh_ms),
        "observed_at_ms": int(observed_at_ms) if observed_at_ms is not None else None,
        "age_ms": age_ms,
        "provider": provider,
        "source_observation_id": observation_id,
    }


def aggregate_market_status(*, target_type: str, fields: dict[str, dict[str, Any]]) -> str:
    required = (
        ("price_usd",)
        if target_type == "CexToken"
        else (
            "price_usd",
            "market_cap_usd",
            "liquidity_usd",
            "holders",
        )
    )
    statuses = [str(fields.get(key, {}).get("status") or "missing") for key in required]
    if all(status == "fresh" for status in statuses):
        return "fresh"
    if any(status == "fresh" for status in statuses):
        return "partial"
    if any(status == "stale" for status in statuses):
        return "stale"
    return "missing"


def _json_number(value: Any) -> Any:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    return int(numeric) if numeric.is_integer() else numeric
