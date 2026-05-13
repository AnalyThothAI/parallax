from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.domains.asset_market.types import (
    MarketContext,
    MarketObservation,
    MarketReadiness,
    MarketTargetRef,
    market_context_to_dict,
    market_observation_from_row,
    market_observation_to_dict,
)


def test_market_observation_serialization_preserves_none_fields() -> None:
    observation = MarketObservation(
        target=MarketTargetRef(target_type="Asset", target_id="asset-1"),
        observed_at_ms=1_770_000_000_000,
        received_at_ms=None,
        source="event_anchor",
        provider=None,
        pricefeed_id=None,
        price_usd=None,
        price_quote=None,
        quote_symbol=None,
        price_basis=None,
        market_cap_usd=None,
        liquidity_usd=None,
        holders=None,
        volume_24h_usd=None,
        open_interest_usd=None,
        raw_payload_hash=None,
    )

    payload = market_observation_to_dict(observation)

    assert payload["target_type"] == "Asset"
    assert payload["target_id"] == "asset-1"
    assert payload["price_usd"] is None
    assert payload["market_cap_usd"] is None
    assert payload["holders"] is None
    assert payload["price_basis"] is None


def test_market_context_serialization_keeps_absent_observations_null() -> None:
    context = MarketContext(
        event_anchor=None,
        decision_latest=None,
        readiness=MarketReadiness(
            anchor_status="missing",
            latest_status="missing",
            dex_floor_status="missing_fields",
            missing_fields=("price_usd", "holders"),
            stale_fields=("decision_latest",),
        ),
    )

    payload = market_context_to_dict(context)

    assert payload == {
        "event_anchor": None,
        "decision_latest": None,
        "readiness": {
            "anchor_status": "missing",
            "latest_status": "missing",
            "dex_floor_status": "missing_fields",
            "missing_fields": ["price_usd", "holders"],
            "stale_fields": ["decision_latest"],
        },
    }


def test_market_observation_from_row_uses_subject_columns_and_does_not_synthesize_prices() -> None:
    observation = market_observation_from_row(
        {
            "subject_type": "Asset",
            "subject_id": "asset-1",
            "observed_at_ms": 1_770_000_000_000,
            "created_at_ms": 1_770_000_000_100,
            "observation_kind": "decision_latest",
            "provider": "okx_dex_ws",
            "pricefeed_id": "pf-1",
            "price_usd": Decimal("1.25"),
            "price_quote": None,
            "quote_symbol": "USD",
            "price_basis": "last",
            "market_cap_usd": None,
            "liquidity_usd": Decimal("250000.5"),
            "holders": None,
            "volume_24h_usd": None,
            "open_interest_usd": None,
        }
    )

    assert observation.target == MarketTargetRef(target_type="Asset", target_id="asset-1")
    assert observation.received_at_ms == 1_770_000_000_100
    assert observation.source == "decision_latest"
    assert observation.price_usd == 1.25
    assert observation.price_quote is None
    assert observation.market_cap_usd is None
    assert observation.liquidity_usd == 250000.5
    assert observation.holders is None
