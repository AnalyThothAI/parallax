from __future__ import annotations

from typing import Any

MESSAGE_PRICE_FRESH_MS = 5 * 60 * 1000


def message_price_payload(row: dict[str, Any]) -> dict[str, Any]:
    observation_id = row.get("price_observation_id")
    if not observation_id:
        return {
            "status": "pending_observation",
            "provider": None,
            "pricefeed_id": row.get("pricefeed_id"),
            "price_usd": None,
            "price_quote": None,
            "quote_symbol": row.get("quote_symbol"),
            "observed_at_ms": None,
            "observation_lag_ms": None,
            "observation_id": None,
            "observation_kind": None,
        }
    lag = row.get("price_observation_lag_ms")
    status = "stale" if lag is not None and int(lag) > MESSAGE_PRICE_FRESH_MS else "ready"
    return {
        "status": status,
        "provider": row.get("price_provider"),
        "pricefeed_id": row.get("pricefeed_id"),
        "price_usd": _number(row.get("price_usd")),
        "price_quote": _number(row.get("price_quote")),
        "quote_symbol": row.get("price_quote_symbol") or row.get("quote_symbol"),
        "observed_at_ms": row.get("price_observed_at_ms"),
        "observation_lag_ms": lag,
        "observation_id": observation_id,
        "observation_kind": row.get("price_observation_kind"),
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
