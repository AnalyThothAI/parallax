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


def test_strong_dex_asset_with_stale_market_blocks_high_alert() -> None:
    snapshot = _strong_dex_snapshot(market={"market_status": "stale"})

    assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
    assert "market_freshness_stale" in snapshot["hard_gates"]["blocked_reasons"]


def test_strong_dex_asset_with_missing_market_status_blocks_high_alert() -> None:
    snapshot = _strong_dex_snapshot(market={"market_status": None})

    assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
    assert "market_freshness_missing" in snapshot["hard_gates"]["blocked_reasons"]


def test_unresolved_identity_blocks_high_alert() -> None:
    snapshot_without_type = _strong_dex_snapshot(target={"target_type": None})
    snapshot_without_id = _strong_dex_snapshot(target={"target_id": None})
    snapshot_for_source_seed = _strong_dex_snapshot(
        target={"target_type": "source_seed", "target_id": "source_seed:event-1"}
    )

    assert snapshot_without_type["hard_gates"]["eligible_for_high_alert"] is False
    assert "identity_unresolved" in snapshot_without_type["hard_gates"]["blocked_reasons"]
    assert snapshot_without_id["hard_gates"]["eligible_for_high_alert"] is False
    assert "identity_unresolved" in snapshot_without_id["hard_gates"]["blocked_reasons"]
    assert snapshot_for_source_seed["hard_gates"]["eligible_for_high_alert"] is False
    assert "identity_unresolved" in snapshot_for_source_seed["hard_gates"]["blocked_reasons"]


def test_dex_asset_missing_market_floors_blocks_high_alert() -> None:
    snapshot = _strong_dex_snapshot(
        market={
            "holders": None,
            "liquidity_usd": None,
            "market_cap_usd": None,
        }
    )

    assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["hard_gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }
    assert snapshot["composite"]["recommended_decision"] != "high_alert"
    assert snapshot["families"]["market_quality"]["factors"]["holders"]["data_health"] == "missing"
    assert snapshot["families"]["market_quality"]["factors"]["holders"]["score"] == 0


def test_non_finite_numeric_inputs_are_treated_as_missing_or_zero() -> None:
    snapshot = _strong_dex_snapshot(
        attention={"mentions_1h": float("inf")},
        market={
            "holders": float("inf"),
            "liquidity_usd": float("inf"),
            "market_cap_usd": float("-inf"),
        },
        social_quality={"duplicate_text_share": float("nan")},
        social_semantics={"direction_counts": {"bullish": float("inf")}},
        timing={"social_signal_start_ms": float("inf")},
    )

    assert snapshot["families"]["social_attention"]["facts"]["mentions_1h"] == 0
    assert snapshot["families"]["social_semantics"]["facts"]["direction_counts"]["bullish"] == 0
    assert snapshot["families"]["social_quality"]["factors"]["duplicate_text_share"]["raw_value"] is None
    assert snapshot["families"]["social_quality"]["factors"]["duplicate_text_share"]["data_health"] == "missing"
    assert snapshot["families"]["market_quality"]["factors"]["holders"]["raw_value"] is None
    assert snapshot["families"]["market_quality"]["factors"]["holders"]["data_health"] == "missing"
    assert snapshot["families"]["market_quality"]["factors"]["liquidity_usd"]["raw_value"] is None
    assert snapshot["families"]["market_quality"]["factors"]["market_cap_usd"]["raw_value"] is None
    assert snapshot["families"]["timing"]["facts"]["social_signal_start_ms"] is None
    assert snapshot["families"]["timing"]["factors"]["social_signal_start_ms"]["data_health"] == "missing"
    assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["hard_gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }


def _strong_dex_snapshot(
    *,
    target: dict[str, object] | None = None,
    attention: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    social_quality: dict[str, object] | None = None,
    social_semantics: dict[str, object] | None = None,
    timing: dict[str, object] | None = None,
) -> dict[str, object]:
    base_target: dict[str, object] = {
        "target_type": "Asset",
        "target_id": "asset:solana:token:STRONG",
        "symbol": "STRONG",
        "chain": "solana",
        "address": "STRONG",
    }
    if target is not None:
        base_target.update(target)
    base_attention: dict[str, object] = {
        "mentions_1h": 12,
        "mentions_4h": 18,
        "mentions_24h": 32,
        "unique_authors": 8,
        "watched_mentions": 2,
    }
    if attention is not None:
        base_attention.update(attention)
    base_market: dict[str, object] = {
        "market_status": "fresh",
        "market_cap_usd": 500_000.0,
        "liquidity_usd": 150_000.0,
        "holders": 1_500,
    }
    if market is not None:
        base_market.update(market)
    base_social_quality: dict[str, object] = {
        "duplicate_text_share": 0.0,
        "informative_post_count": 8,
        "mentions": 12,
        "independent_authors": 8,
    }
    if social_quality is not None:
        base_social_quality.update(social_quality)
    base_social_semantics: dict[str, object] = {
        "direction_counts": {"bullish": 5, "neutral": 2},
        "impact_mean": 0.7,
        "novelty_mean": 0.5,
        "confidence_mean": 0.9,
    }
    if social_semantics is not None:
        base_social_semantics.update(social_semantics)
    base_timing: dict[str, object] = {
        "price_change_before_social_pct": 0.01,
        "price_change_since_social_pct": 0.03,
    }
    if timing is not None:
        base_timing.update(timing)
    return build_token_factor_snapshot(
        target=base_target,
        attention=base_attention,
        social_quality=base_social_quality,
        social_semantics=base_social_semantics,
        market=base_market,
        timing=base_timing,
        source_event_ids=["event-strong-1", "event-strong-2"],
        computed_at_ms=1_778_000_000_000,
    )
