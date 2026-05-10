from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot import (
    DEX_HIGH_ALERT_FLOORS,
    FACTOR_FAMILIES,
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    build_token_factor_snapshot,
)


def test_scoring_package_exports_factor_snapshot_contract() -> None:
    from gmgn_twitter_intel.domains.token_intel import scoring

    assert scoring.TOKEN_FACTOR_SNAPSHOT_VERSION == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert scoring.FACTOR_FAMILIES == FACTOR_FAMILIES
    assert scoring.DEX_HIGH_ALERT_FLOORS == DEX_HIGH_ALERT_FLOORS
    assert scoring.build_token_factor_snapshot is build_token_factor_snapshot


def test_dex_asset_below_market_floors_blocks_high_alert() -> None:
    snapshot = build_token_factor_snapshot(
        target={
            "target_type": "Asset",
            "target_id": "asset:bsc:0x1",
            "symbol": "BOV",
            "chain": "56",
            "address": "0x1",
        },
        attention={
            "mentions_1h": 3,
            "mentions_4h": 3,
            "mentions_24h": 3,
            "unique_authors": 2,
            "watched_mentions": 0,
        },
        social_quality={
            "duplicate_text_share": 0.0,
            "informative_post_count": 1,
            "mentions": 3,
            "independent_authors": 2,
        },
        social_semantics={
            "direction_counts": {"bullish": 1},
            "impact_mean": 0.2,
            "novelty_mean": 0.1,
            "confidence_mean": 0.6,
        },
        market={
            "market_status": "fresh",
            "market_cap_usd": 12087.0,
            "liquidity_usd": 6553.0,
            "holders": 46,
            "price_change_since_social_pct": -0.1338,
            "price_change_before_social_pct": None,
        },
        timing={
            "price_change_before_social_pct": None,
            "price_change_since_social_pct": -0.1338,
        },
        source_event_ids=["event-1", "event-2", "event-3", "event-2"],
        computed_at_ms=1_778_000_000_000,
    )

    assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["hard_gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
        "insufficient_independent_social_sources",
    }
    assert snapshot["families"]["market_quality"]["factors"]["holders"]["raw_value"] == 46
    assert snapshot["provenance"]["source_event_ids"] == ["event-1", "event-2", "event-3"]
    for family in FACTOR_FAMILIES:
        assert snapshot["families"][family]["data_health"] in {"ready", "partial", "missing"}
    assert isinstance(snapshot["families"]["identity"]["data_health"], str)
    assert isinstance(snapshot["families"]["market_quality"]["data_health"], str)


def test_cex_token_does_not_apply_dex_holder_liquidity_floors() -> None:
    snapshot = build_token_factor_snapshot(
        target={"target_type": "CexToken", "target_id": "cex_token:BLEND", "symbol": "BLEND"},
        attention={
            "mentions_1h": 7,
            "mentions_4h": 7,
            "mentions_24h": 9,
            "unique_authors": 5,
            "watched_mentions": 1,
        },
        social_quality={
            "duplicate_text_share": 0.0,
            "informative_post_count": 5,
            "mentions": 7,
            "independent_authors": 5,
        },
        social_semantics={
            "direction_counts": {"bullish": 3, "neutral": 2},
            "impact_mean": 0.5,
            "novelty_mean": 0.3,
            "confidence_mean": 0.8,
        },
        market={
            "market_status": "fresh",
            "volume_24h_usd": 45_000_000.0,
            "open_interest_usd": None,
            "native_market_id": "OKX:BLEND-USDT",
        },
        timing={"price_change_before_social_pct": 0.02, "price_change_since_social_pct": 0.01},
        source_event_ids=["event-1"],
        computed_at_ms=1_778_000_000_000,
    )

    assert "holders_below_high_alert_floor" not in snapshot["hard_gates"]["blocked_reasons"]
    assert "liquidity_below_high_alert_floor" not in snapshot["hard_gates"]["blocked_reasons"]
    assert "market_cap_below_high_alert_floor" not in snapshot["hard_gates"]["blocked_reasons"]
    assert snapshot["families"]["market_quality"]["target_market_type"] == "cex"


def test_duplicate_social_text_blocks_high_alert() -> None:
    snapshot = build_token_factor_snapshot(
        target={
            "target_type": "Asset",
            "target_id": "asset:solana:token:X",
            "symbol": "X",
            "chain": "solana",
            "address": "X",
        },
        attention={
            "mentions_1h": 5,
            "mentions_4h": 5,
            "mentions_24h": 5,
            "unique_authors": 5,
            "watched_mentions": 0,
        },
        social_quality={
            "duplicate_text_share": 0.75,
            "informative_post_count": 1,
            "mentions": 5,
            "independent_authors": 5,
        },
        social_semantics={
            "direction_counts": {},
            "impact_mean": None,
            "novelty_mean": None,
            "confidence_mean": None,
        },
        market={
            "market_status": "fresh",
            "market_cap_usd": 200_000.0,
            "liquidity_usd": 80_000.0,
            "holders": 500,
        },
        timing={"price_change_before_social_pct": 0.0, "price_change_since_social_pct": 0.0},
        source_event_ids=["event-1", "event-2"],
        computed_at_ms=1_778_000_000_000,
    )

    assert "duplicate_text_share_high" in snapshot["hard_gates"]["blocked_reasons"]
