from __future__ import annotations

from typing import get_type_hints

from gmgn_twitter_intel.domains.asset_market.types.market_tick import EnrichedEventCapture, MarketTick


def test_enriched_event_capture_requires_resolution_and_capture_reason() -> None:
    type_hints = get_type_hints(EnrichedEventCapture)

    assert type_hints["resolution_id"] is str
    assert type_hints["capture_reason"] is str


def test_market_tick_is_frozen_slots_dataclass() -> None:
    assert MarketTick.__dataclass_params__.frozen is True
    assert hasattr(MarketTick, "__slots__")
