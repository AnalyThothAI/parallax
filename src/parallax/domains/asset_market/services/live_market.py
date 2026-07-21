from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

LIVE_MARKET_STALE_AFTER_MS = 300_000


@dataclass(frozen=True, slots=True)
class LiveMarketSnapshot:
    target_type: str
    target_id: str
    price_usd: float | None
    price_quote: float | None
    quote_symbol: str | None
    price_basis: str
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    volume_24h_usd: float | None
    open_interest_usd: float | None
    observed_at_ms: int
    received_at_ms: int
    provider: str | None
    pricefeed_id: str | None


def live_market_snapshot(
    row: Mapping[str, Any] | None,
    *,
    target_type: str,
    target_id: str,
    now_ms: int,
) -> dict[str, Any]:
    if row is None:
        return _missing_snapshot(target_type=target_type, target_id=target_id)
    snapshot = _snapshot_from_current(row, target_type=target_type, target_id=target_id)
    age_ms = max(0, int(now_ms) - snapshot.received_at_ms)
    return {
        "target_type": snapshot.target_type,
        "target_id": snapshot.target_id,
        "status": "stale" if age_ms > LIVE_MARKET_STALE_AFTER_MS else "live",
        "price_usd": snapshot.price_usd,
        "price_quote": snapshot.price_quote,
        "quote_symbol": snapshot.quote_symbol,
        "price_basis": snapshot.price_basis,
        "market_cap_usd": snapshot.market_cap_usd,
        "liquidity_usd": snapshot.liquidity_usd,
        "holders": snapshot.holders,
        "volume_24h_usd": snapshot.volume_24h_usd,
        "open_interest_usd": snapshot.open_interest_usd,
        "observed_at_ms": snapshot.observed_at_ms,
        "received_at_ms": snapshot.received_at_ms,
        "age_ms": age_ms,
        "provider": snapshot.provider,
    }


def live_market_update_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot_from_current(
        row,
        target_type=str(row["product_target_type"]),
        target_id=str(row["product_target_id"]),
    )
    return {
        "type": "live_market_update",
        "provider": snapshot.provider,
        "target_type": snapshot.target_type,
        "target_id": snapshot.target_id,
        "observed_at_ms": snapshot.observed_at_ms,
        "market": {
            "decision_latest": {
                "target_type": snapshot.target_type,
                "target_id": snapshot.target_id,
                "observed_at_ms": snapshot.observed_at_ms,
                "received_at_ms": snapshot.received_at_ms,
                "source": "decision_latest",
                "provider": snapshot.provider,
                "pricefeed_id": snapshot.pricefeed_id,
                "price_usd": snapshot.price_usd,
                "price_quote": snapshot.price_quote,
                "quote_symbol": snapshot.quote_symbol,
                "price_basis": snapshot.price_basis,
                "market_cap_usd": snapshot.market_cap_usd,
                "liquidity_usd": snapshot.liquidity_usd,
                "holders": snapshot.holders,
                "volume_24h_usd": snapshot.volume_24h_usd,
                "open_interest_usd": snapshot.open_interest_usd,
            }
        },
    }


def _snapshot_from_current(
    row: Mapping[str, Any],
    *,
    target_type: str,
    target_id: str,
) -> LiveMarketSnapshot:
    market_target_type = str(row["target_type"])
    price_usd = _float(row.get("price_usd"))
    quote_symbol = "USDT" if market_target_type == "cex_symbol" else None
    price_basis = "quote_as_usd" if quote_symbol else ("usd" if price_usd is not None else "unavailable")
    return LiveMarketSnapshot(
        target_type=target_type,
        target_id=str(target_id),
        price_usd=price_usd,
        price_quote=price_usd if quote_symbol else None,
        quote_symbol=quote_symbol,
        price_basis=price_basis,
        market_cap_usd=_float(row.get("market_cap_usd")),
        liquidity_usd=_float(row.get("liquidity_usd")),
        holders=_int(row.get("holders")),
        volume_24h_usd=_float(row.get("volume_24h_usd")),
        open_interest_usd=_float(row.get("open_interest_usd")),
        observed_at_ms=int(row["tick_observed_at_ms"]),
        received_at_ms=int(row["updated_at_ms"]),
        provider=str(row.get("source_provider") or "") or None,
        pricefeed_id=str(row.get("pricefeed_id") or "") or None,
    )


def _missing_snapshot(*, target_type: str, target_id: str) -> dict[str, Any]:
    return {
        "target_type": str(target_type),
        "target_id": str(target_id),
        "status": "missing",
        "price_usd": None,
        "price_quote": None,
        "quote_symbol": None,
        "price_basis": "unavailable",
        "market_cap_usd": None,
        "liquidity_usd": None,
        "holders": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "observed_at_ms": None,
        "received_at_ms": None,
        "age_ms": None,
        "provider": None,
    }


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        try:
            return float(value)
        except (OverflowError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
