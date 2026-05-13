from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class MarketTargetRef:
    target_type: str
    target_id: str


@dataclass(frozen=True, slots=True)
class MarketObservation:
    target: MarketTargetRef
    observed_at_ms: int
    received_at_ms: int | None
    source: str
    provider: str | None
    pricefeed_id: str | None
    price_usd: float | None
    price_quote: float | None
    quote_symbol: str | None
    price_basis: str | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    volume_24h_usd: float | None
    open_interest_usd: float | None
    raw_payload_hash: str | None


@dataclass(frozen=True, slots=True)
class MarketReadiness:
    anchor_status: str
    latest_status: str
    dex_floor_status: str
    missing_fields: Sequence[str]
    stale_fields: Sequence[str]


@dataclass(frozen=True, slots=True)
class MarketContext:
    event_anchor: MarketObservation | None
    decision_latest: MarketObservation | None
    readiness: MarketReadiness


def market_observation_to_dict(observation: MarketObservation) -> dict[str, Any]:
    return {
        "target_type": observation.target.target_type,
        "target_id": observation.target.target_id,
        "observed_at_ms": observation.observed_at_ms,
        "received_at_ms": observation.received_at_ms,
        "source": observation.source,
        "provider": observation.provider,
        "pricefeed_id": observation.pricefeed_id,
        "price_usd": observation.price_usd,
        "price_quote": observation.price_quote,
        "quote_symbol": observation.quote_symbol,
        "price_basis": observation.price_basis,
        "market_cap_usd": observation.market_cap_usd,
        "liquidity_usd": observation.liquidity_usd,
        "holders": observation.holders,
        "volume_24h_usd": observation.volume_24h_usd,
        "open_interest_usd": observation.open_interest_usd,
        "raw_payload_hash": observation.raw_payload_hash,
    }


def market_context_to_dict(context: MarketContext) -> dict[str, Any]:
    return {
        "event_anchor": (
            market_observation_to_dict(context.event_anchor) if context.event_anchor is not None else None
        ),
        "decision_latest": (
            market_observation_to_dict(context.decision_latest) if context.decision_latest is not None else None
        ),
        "readiness": {
            "anchor_status": context.readiness.anchor_status,
            "latest_status": context.readiness.latest_status,
            "dex_floor_status": context.readiness.dex_floor_status,
            "missing_fields": list(context.readiness.missing_fields),
            "stale_fields": list(context.readiness.stale_fields),
        },
    }


def market_observation_from_row(row: Mapping[str, Any]) -> MarketObservation:
    return MarketObservation(
        target=MarketTargetRef(
            target_type=str(row.get("target_type") or row.get("subject_type") or ""),
            target_id=str(row.get("target_id") or row.get("subject_id") or ""),
        ),
        observed_at_ms=int(row["observed_at_ms"]),
        received_at_ms=_optional_int(row.get("received_at_ms", row.get("created_at_ms"))),
        source=str(row.get("source") or row.get("observation_kind") or ""),
        provider=_optional_str(row.get("provider")),
        pricefeed_id=_optional_str(row.get("pricefeed_id")),
        price_usd=_optional_float(row.get("price_usd")),
        price_quote=_optional_float(row.get("price_quote")),
        quote_symbol=_optional_str(row.get("quote_symbol")),
        price_basis=_optional_str(row.get("price_basis")),
        market_cap_usd=_optional_float(row.get("market_cap_usd")),
        liquidity_usd=_optional_float(row.get("liquidity_usd")),
        holders=_optional_int(row.get("holders")),
        volume_24h_usd=_optional_float(row.get("volume_24h_usd")),
        open_interest_usd=_optional_float(row.get("open_interest_usd")),
        raw_payload_hash=_row_payload_hash(row),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _row_payload_hash(row: Mapping[str, Any]) -> str | None:
    direct = row.get("raw_payload_hash")
    if direct is not None:
        return str(direct)
    raw_payload = row.get("raw_payload_json")
    if isinstance(raw_payload, Mapping):
        value = raw_payload.get("raw_payload_hash")
        return str(value) if value is not None else None
    return None
