from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.services.live_observation_policy import (
    should_persist_live_observation,
)
from gmgn_twitter_intel.domains.asset_market.types import MarketObservation, MarketTargetRef


def test_flat_market_live_observation_write_budget():
    target_count = 100
    fps = 5
    duration_seconds = 10 * 60
    raw_frame_count = target_count * fps * duration_seconds
    persisted_count = 0
    previous_by_target: dict[str, MarketObservation] = {}

    for second in range(duration_seconds):
        for frame in range(fps):
            now_ms = (second * 1000) + (frame * 200)
            for target_index in range(target_count):
                target_id = f"asset-{target_index}"
                jitter = 0.0001 if (second + frame + target_index) % 2 else -0.0001
                candidate = _observation(target_id=target_id, price_usd=1.0 + jitter, observed_at_ms=now_ms)
                decision = should_persist_live_observation(
                    previous=previous_by_target.get(target_id),
                    candidate=candidate,
                    now_ms=now_ms,
                    heartbeat_ms=60_000,
                    min_price_change_pct=0.005,
                    min_write_interval_ms=5_000,
                )
                if decision.should_persist:
                    persisted_count += 1
                    previous_by_target[target_id] = candidate

    assert raw_frame_count == 300_000
    assert persisted_count <= 1_500
    assert persisted_count / raw_frame_count <= 0.005


def _observation(*, target_id: str, price_usd: float, observed_at_ms: int) -> MarketObservation:
    return MarketObservation(
        target=MarketTargetRef(target_type="Asset", target_id=target_id),
        observed_at_ms=observed_at_ms,
        received_at_ms=observed_at_ms,
        source="decision_latest",
        provider="okx_dex_ws_price_info",
        pricefeed_id=None,
        price_usd=price_usd,
        price_quote=None,
        quote_symbol="USD",
        price_basis="usd",
        market_cap_usd=1_000_000.0,
        liquidity_usd=100_000.0,
        holders=1_000,
        volume_24h_usd=10_000.0,
        open_interest_usd=None,
        raw_payload_hash=None,
    )
