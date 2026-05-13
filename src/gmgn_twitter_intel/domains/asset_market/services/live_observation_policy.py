from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gmgn_twitter_intel.domains.asset_market.types.market_observation import MarketObservation

_GATE_FIELDS = (
    "holders",
    "liquidity_usd",
    "market_cap_usd",
    "volume_24h_usd",
    "open_interest_usd",
)


@dataclass(frozen=True, slots=True)
class LiveObservationPersistDecision:
    should_persist: bool
    reason: Literal[
        "first_seen",
        "heartbeat",
        "significant_price_change",
        "gate_field_change",
        "provider_state_change",
        "debounced",
        "not_material",
    ]


def should_persist_live_observation(
    *,
    previous: MarketObservation | None,
    candidate: MarketObservation,
    now_ms: int,
    heartbeat_ms: int = 60_000,
    min_price_change_pct: float = 0.005,
    min_write_interval_ms: int = 5_000,
    provider_state_changed: bool = False,
    dex_floor_fields_changed: bool = False,
) -> LiveObservationPersistDecision:
    if previous is None:
        return LiveObservationPersistDecision(True, "first_seen")
    if provider_state_changed:
        return LiveObservationPersistDecision(True, "provider_state_change")
    if dex_floor_fields_changed or _gate_field_presence_changed(previous, candidate):
        return LiveObservationPersistDecision(True, "gate_field_change")

    elapsed_ms = max(0, int(now_ms) - int(previous.observed_at_ms))
    if elapsed_ms < min_write_interval_ms:
        return LiveObservationPersistDecision(False, "debounced")
    if elapsed_ms >= heartbeat_ms:
        return LiveObservationPersistDecision(True, "heartbeat")
    if _price_change_pct(previous, candidate) + 1e-12 >= min_price_change_pct:
        return LiveObservationPersistDecision(True, "significant_price_change")
    return LiveObservationPersistDecision(False, "not_material")


def _gate_field_presence_changed(previous: MarketObservation, candidate: MarketObservation) -> bool:
    return any((getattr(previous, field) is None) != (getattr(candidate, field) is None) for field in _GATE_FIELDS)


def _price_change_pct(previous: MarketObservation, candidate: MarketObservation) -> float:
    if previous.price_usd is None or candidate.price_usd is None:
        return 0.0
    previous_price = float(previous.price_usd)
    if previous_price <= 0:
        return 0.0
    return abs(float(candidate.price_usd) - previous_price) / previous_price
