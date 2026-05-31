from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.domains.token_intel.read_models.token_target_stage_builder import build_token_target_stages


def test_stage_builder_splits_seed_ignition_expansion_and_chase():
    rows = [
        row("event-1", "alice", 1_000, watched=True, price="1.00"),
        row("event-2", "bob", 2_000, price="1.05"),
        row("event-3", "carol", 3_000, price="1.10"),
        row("event-4", "dave", 4_000, price="1.15"),
        row("event-5", "erin", 5_000, price="1.80"),
    ]

    result = build_token_target_stages(rows)

    assert [stage["phase"] for stage in result.stages] == ["seed", "ignition", "expansion", "chase"]
    assert result.stages[0]["representative_event_ids"] == ["event-1"]
    assert result.stages[-1]["price"]["delta_pct"] == pytest.approx(0.565217, rel=0.0001)
    assert result.stages[-1]["price"]["observation_ids"] == ["tick:event-5"]
    assert result.annotations["event-1"]["author_role"] == "watched"
    assert result.annotations["event-2"]["author_role"] == "early_amplifier"
    assert result.annotations["event-5"]["price_delta_from_previous_post_pct"] == pytest.approx(0.565217, rel=0.0001)


def test_stage_builder_marks_concentrated_repeater_flow():
    rows = [
        row("event-1", "alice", 1_000, price="1.00"),
        row("event-2", "alice", 2_000, price="1.01"),
        row("event-3", "alice", 3_000, price="1.02"),
    ]

    result = build_token_target_stages(rows)

    assert [stage["phase"] for stage in result.stages] == ["seed", "ignition", "concentration"]
    assert result.stages[-1]["people"]["top_author_share"] == 1.0
    assert result.annotations["event-3"]["author_role"] == "repeater"


def row(event_id: str, handle: str, received_at_ms: int, *, watched: bool = False, price: str = "1.00") -> dict:
    return {
        "event_id": event_id,
        "author_handle": handle,
        "is_watched": watched,
        "received_at_ms": received_at_ms,
        "market_tick_id": f"tick:{event_id}",
        "market_tick_provider": "okx_dex_price",
        "pricefeed_id": "pricefeed:test",
        "price_usd": Decimal(price),
        "price_quote": None,
        "price_quote_symbol": None,
        "quote_symbol": "USDT",
        "market_tick_observed_at_ms": received_at_ms,
        "market_tick_lag_ms": 0,
        "market_capture_method": "tier1_ws",
    }
