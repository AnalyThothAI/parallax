from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.services.live_observation_policy import (
    should_persist_live_observation,
)
from gmgn_twitter_intel.domains.asset_market.types import MarketObservation, MarketTargetRef


def test_first_seen_persists():
    decision = should_persist_live_observation(
        previous=None,
        candidate=_observation(price_usd=1.0, observed_at_ms=10_000),
        now_ms=10_000,
    )

    assert decision.should_persist is True
    assert decision.reason == "first_seen"


def test_flat_frame_inside_heartbeat_is_not_material():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000, holders=10),
        candidate=_observation(price_usd=1.0, observed_at_ms=30_000, holders=10),
        now_ms=30_000,
        heartbeat_ms=60_000,
        min_write_interval_ms=5_000,
    )

    assert decision.should_persist is False


def test_sub_threshold_price_change_is_not_material():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000),
        candidate=_observation(price_usd=1.0049, observed_at_ms=20_000),
        now_ms=20_000,
        min_price_change_pct=0.005,
        min_write_interval_ms=5_000,
    )

    assert decision.should_persist is False


def test_price_change_at_threshold_persists():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000),
        candidate=_observation(price_usd=1.005, observed_at_ms=20_000),
        now_ms=20_000,
        min_price_change_pct=0.005,
        min_write_interval_ms=5_000,
    )

    assert decision.should_persist is True
    assert decision.reason == "significant_price_change"


def test_heartbeat_persists_even_without_price_change():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000),
        candidate=_observation(price_usd=1.0, observed_at_ms=70_000),
        now_ms=70_000,
        heartbeat_ms=60_000,
    )

    assert decision.should_persist is True
    assert decision.reason == "heartbeat"


def test_missing_to_present_gate_field_persists():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000, holders=None),
        candidate=_observation(price_usd=1.0, observed_at_ms=11_000, holders=10),
        now_ms=11_000,
        min_write_interval_ms=5_000,
    )

    assert decision.should_persist is True
    assert decision.reason == "gate_field_change"


def test_provider_state_change_bypasses_debounce():
    decision = should_persist_live_observation(
        previous=_observation(price_usd=1.0, observed_at_ms=10_000),
        candidate=_observation(price_usd=1.0, observed_at_ms=11_000),
        now_ms=11_000,
        min_write_interval_ms=5_000,
        provider_state_changed=True,
    )

    assert decision.should_persist is True
    assert decision.reason == "provider_state_change"


def _observation(
    *,
    price_usd: float | None,
    observed_at_ms: int,
    holders: int | None = None,
) -> MarketObservation:
    return MarketObservation(
        target=MarketTargetRef(target_type="Asset", target_id="asset-1"),
        observed_at_ms=observed_at_ms,
        received_at_ms=observed_at_ms,
        source="decision_latest",
        provider="okx_dex_ws_price_info",
        pricefeed_id=None,
        price_usd=price_usd,
        price_quote=None,
        quote_symbol="USD",
        price_basis="usd" if price_usd is not None else "unavailable",
        market_cap_usd=None,
        liquidity_usd=None,
        holders=holders,
        volume_24h_usd=None,
        open_interest_usd=None,
        raw_payload_hash=None,
    )
