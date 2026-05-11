from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot import (
    DEX_HIGH_ALERT_FLOORS,
    FACTOR_FAMILIES,
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    build_token_factor_snapshot,
)


def test_scoring_package_exports_factor_snapshot_contract() -> None:
    from gmgn_twitter_intel.domains.token_intel import scoring

    assert TOKEN_FACTOR_SNAPSHOT_VERSION == "token_factor_snapshot_v2_alpha_gated"
    assert FACTOR_FAMILIES == (
        "attention_heat",
        "diffusion_quality",
        "semantic_quality",
        "timing_response",
    )
    assert scoring.TOKEN_FACTOR_SNAPSHOT_VERSION == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert scoring.FACTOR_FAMILIES == FACTOR_FAMILIES
    assert scoring.DEX_HIGH_ALERT_FLOORS == DEX_HIGH_ALERT_FLOORS
    assert scoring.build_token_factor_snapshot is build_token_factor_snapshot


def test_factor_snapshot_outputs_v2_alpha_gated_shape() -> None:
    snapshot = _strong_dex_snapshot(attention={"latest_seen_ms": 1_778_000_012_345})

    assert set(snapshot) == {
        "schema_version",
        "subject",
        "gates",
        "data_health",
        "families",
        "normalization",
        "composite",
        "provenance",
    }
    assert "hard_gates" not in snapshot
    assert snapshot["schema_version"] == "token_factor_snapshot_v2_alpha_gated"
    assert snapshot["subject"] == {
        "target_type": "Asset",
        "target_id": "asset:solana:token:STRONG",
        "symbol": "STRONG",
        "target_market_type": "dex",
        "chain": "solana",
        "address": "STRONG",
        "pricefeed_id": "pf-strong",
    }
    assert set(snapshot["families"]) == set(FACTOR_FAMILIES)
    assert snapshot["families"]["attention_heat"]["facts"]["latest_seen_ms"] == 1_778_000_012_345
    assert snapshot["normalization"] == {
        "status": "pending_cross_section",
        "cohort": {},
        "factor_ranks": {},
        "alpha_rank": None,
    }
    assert snapshot["provenance"]["source_event_ids"] == ["event-strong-1", "event-strong-2"]
    for family in FACTOR_FAMILIES:
        assert set(snapshot["families"][family]) == {
            "raw_score",
            "score",
            "weight",
            "data_health",
            "facts",
            "factors",
        }
        assert snapshot["families"][family]["data_health"] in {"ready", "partial", "missing"}


def test_identity_market_and_social_start_presence_do_not_score_as_alpha() -> None:
    snapshot = build_token_factor_snapshot(
        target={
            "target_type": "Asset",
            "target_id": "asset:solana:token:QUIET",
            "symbol": "QUIET",
            "chain": "solana",
            "address": "QUIET",
            "pricefeed_id": "pf-quiet",
        },
        attention={},
        social_quality={},
        social_semantics={},
        market={
            "market_status": "fresh",
            "market_cap_usd": 500_000.0,
            "liquidity_usd": 150_000.0,
            "holders": 1_500,
            "native_market_id": "raydium:quiet-sol",
            "pricefeed_id": "pf-quiet",
        },
        timing={"social_signal_start_ms": 1_778_000_001_000},
        source_event_ids=["event-1"],
        computed_at_ms=1_778_000_002_000,
    )

    assert "identity" not in snapshot["families"]
    assert "market_quality" not in snapshot["families"]
    assert snapshot["data_health"]["identity"] == "ready"
    assert snapshot["data_health"]["market"] == "ready"
    assert snapshot["families"]["timing_response"]["facts"]["social_signal_start_ms"] == 1_778_000_001_000
    assert "social_signal_start_ms" not in snapshot["families"]["timing_response"]["factors"]
    assert snapshot["data_health"]["alpha"] == "missing"
    assert "alpha_data_missing" in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["max_decision"] == "discard"
    assert snapshot["composite"]["raw_alpha_score"] == 0
    assert snapshot["composite"]["recommended_decision"] == "discard"


def test_dex_market_floors_gate_high_alert_without_market_alpha_family() -> None:
    snapshot = _strong_dex_snapshot(
        market={
            "holders": 46,
            "liquidity_usd": 6_553.0,
            "market_cap_usd": 12_087.0,
        }
    )

    assert "market_quality" not in snapshot["families"]
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }
    assert snapshot["composite"]["recommended_decision"] != "high_alert"


def test_fresh_dex_market_missing_floor_inputs_is_not_market_ready() -> None:
    snapshot = _strong_dex_snapshot(
        market={
            "market_status": "fresh",
            "holders": None,
            "liquidity_usd": None,
            "market_cap_usd": None,
        }
    )

    assert snapshot["data_health"]["market"] == "missing"
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert snapshot["composite"]["recommended_decision"] != "high_alert"


def test_cex_token_does_not_apply_dex_holder_liquidity_floors_or_native_market_alpha() -> None:
    snapshot = _strong_cex_snapshot(
        market={
            "market_status": "fresh",
            "volume_24h_usd": 45_000_000.0,
            "open_interest_usd": 8_000_000.0,
            "native_market_id": "OKX:BLEND-USDT",
        }
    )

    assert snapshot["subject"]["target_market_type"] == "cex"
    assert "holders_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "liquidity_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "market_cap_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "market_quality" not in snapshot["families"]
    assert "native_market_id" not in _all_factor_keys(snapshot)


def test_duplicate_and_top_author_concentration_are_penalties_not_clean_rewards() -> None:
    clean = _strong_dex_snapshot(social_quality={"duplicate_text_share": 0.0, "top_author_share": 0.20})
    risky = _strong_dex_snapshot(social_quality={"duplicate_text_share": 0.75, "top_author_share": 0.80})

    clean_factors = clean["families"]["diffusion_quality"]["factors"]
    risky_factors = risky["families"]["diffusion_quality"]["factors"]
    assert clean_factors["duplicate_text_share_penalty"]["score"] == 0
    assert clean_factors["top_author_concentration_penalty"]["score"] == 0
    assert risky_factors["duplicate_text_share_penalty"]["score"] < 0
    assert risky_factors["top_author_concentration_penalty"]["score"] < 0
    assert "duplicate_text_share_high" in risky["gates"]["blocked_reasons"]
    assert "author_concentration_high" in risky["gates"]["risk_reasons"]
    assert risky["families"]["diffusion_quality"]["score"] < clean["families"]["diffusion_quality"]["score"]


def test_high_raw_alpha_with_unresolved_identity_is_capped_to_discard() -> None:
    snapshot = _strong_dex_snapshot(
        target={"target_type": "source_seed", "target_id": "source_seed:event-1"},
    )

    assert snapshot["composite"]["raw_alpha_score"] >= 70
    assert snapshot["data_health"]["identity"] == "missing"
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert "identity_unresolved" in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["max_decision"] == "discard"
    assert snapshot["composite"]["recommended_decision"] == "discard"


@pytest.mark.parametrize(
    ("market_status", "reason", "market_health"),
    [
        ("stale", "market_freshness_stale", "partial"),
        (None, "market_freshness_missing", "missing"),
    ],
)
def test_high_raw_alpha_with_unfresh_market_is_capped_to_discard(
    market_status: object,
    reason: str,
    market_health: str,
) -> None:
    snapshot = _strong_dex_snapshot(market={"market_status": market_status})

    assert snapshot["composite"]["raw_alpha_score"] >= 70
    assert snapshot["data_health"]["market"] == market_health
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert reason in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["max_decision"] == "discard"
    assert snapshot["composite"]["recommended_decision"] == "discard"


def test_unresolved_identity_and_stale_market_gate_high_alert() -> None:
    snapshot = _strong_dex_snapshot(
        target={"target_type": "source_seed", "target_id": "source_seed:event-1"},
        market={"market_status": "stale"},
    )

    assert snapshot["data_health"]["identity"] == "missing"
    assert snapshot["data_health"]["market"] == "partial"
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "identity_unresolved",
        "market_freshness_stale",
    }
    assert snapshot["composite"]["recommended_decision"] != "high_alert"


def test_eligible_raw_alpha_35_recommends_watch() -> None:
    snapshot = _strong_dex_snapshot(
        attention={
            "mentions_1h": 0,
            "mentions_4h": 0,
            "mentions_24h": 0,
            "unique_authors": 3,
            "watched_mentions": 1,
        },
        social_quality={
            "informative_post_count": 2,
            "mentions": 0,
            "independent_authors": 3,
            "effective_authors": None,
        },
        social_semantics={
            "direction_counts": {},
            "impact_mean": None,
            "novelty_mean": None,
            "confidence_mean": None,
        },
        timing={
            "price_change_before_social_pct": None,
            "price_change_since_social_pct": None,
        },
    )

    assert snapshot["gates"]["eligible_for_high_alert"] is True
    assert snapshot["gates"]["max_decision"] == "high_alert"
    assert snapshot["composite"]["raw_alpha_score"] == 35
    assert snapshot["composite"]["recommended_decision"] == "watch"


def test_empty_attention_and_social_quality_are_missing_not_ready() -> None:
    snapshot = build_token_factor_snapshot(
        target={
            "target_type": "Asset",
            "target_id": "asset:solana:token:EMPTY",
            "symbol": "EMPTY",
            "chain": "solana",
            "address": "EMPTY",
        },
        attention={},
        social_quality={},
        social_semantics={},
        market={
            "market_status": "fresh",
            "market_cap_usd": 500_000.0,
            "liquidity_usd": 150_000.0,
            "holders": 1_500,
        },
        timing={},
        source_event_ids=["event-empty"],
        computed_at_ms=1_778_000_000_000,
    )

    assert snapshot["families"]["attention_heat"]["data_health"] == "missing"
    assert snapshot["families"]["diffusion_quality"]["data_health"] == "missing"
    assert snapshot["families"]["attention_heat"]["facts"]["mentions_1h"] == 0
    assert snapshot["families"]["diffusion_quality"]["facts"]["independent_authors"] == 0
    assert snapshot["data_health"]["social"] == "missing"
    assert snapshot["data_health"]["alpha"] == "missing"
    assert "alpha_data_missing" in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["max_decision"] == "discard"


def test_whitespace_identity_normalizes_to_missing() -> None:
    snapshot = _strong_dex_snapshot(target={"target_type": "   ", "target_id": "\t\n"})

    assert snapshot["subject"]["target_type"] is None
    assert snapshot["subject"]["target_id"] is None
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert "identity_unresolved" in snapshot["gates"]["blocked_reasons"]


def test_non_finite_numeric_inputs_are_treated_as_missing_or_zero() -> None:
    snapshot = _strong_dex_snapshot(
        attention={"mentions_1h": float("inf")},
        market={
            "holders": float("inf"),
            "liquidity_usd": float("inf"),
            "market_cap_usd": float("-inf"),
        },
        social_quality={
            "duplicate_text_share": float("nan"),
            "top_author_share": float("inf"),
            "effective_authors": float("nan"),
        },
        social_semantics={"direction_counts": {"bullish": float("inf")}},
        timing={"social_signal_start_ms": float("inf")},
    )

    assert snapshot["families"]["attention_heat"]["facts"]["mentions_1h"] == 0
    assert snapshot["families"]["semantic_quality"]["facts"]["direction_counts"]["bullish"] == 0
    assert snapshot["families"]["diffusion_quality"]["factors"]["duplicate_text_share_penalty"]["raw_value"] is None
    assert snapshot["families"]["diffusion_quality"]["factors"]["top_author_concentration_penalty"]["raw_value"] is None
    assert snapshot["families"]["timing_response"]["facts"]["social_signal_start_ms"] is None
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }


@pytest.mark.parametrize("computed_at_ms", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_computed_at_ms_normalizes_to_zero(computed_at_ms: float) -> None:
    snapshot = _strong_dex_snapshot(computed_at_ms=computed_at_ms)

    assert snapshot["provenance"]["computed_at_ms"] == 0


def _all_factor_keys(snapshot: dict[str, object]) -> set[str]:
    families = snapshot["families"]
    assert isinstance(families, dict)
    return {key for family in families.values() if isinstance(family, dict) for key in (family.get("factors") or {})}


def _strong_dex_snapshot(
    *,
    target: dict[str, object] | None = None,
    attention: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    social_quality: dict[str, object] | None = None,
    social_semantics: dict[str, object] | None = None,
    timing: dict[str, object] | None = None,
    computed_at_ms: object = 1_778_000_000_000,
) -> dict[str, object]:
    base_target: dict[str, object] = {
        "target_type": "Asset",
        "target_id": "asset:solana:token:STRONG",
        "symbol": "STRONG",
        "chain": "solana",
        "address": "STRONG",
        "pricefeed_id": "pf-strong",
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
        "top_author_share": 0.20,
        "informative_post_count": 8,
        "mentions": 12,
        "independent_authors": 8,
        "effective_authors": 6.0,
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
        source_event_ids=["event-strong-1", "event-strong-2", "event-strong-1"],
        computed_at_ms=computed_at_ms,
    )


def _strong_cex_snapshot(
    *,
    market: dict[str, object] | None = None,
) -> dict[str, object]:
    base_market: dict[str, object] = {
        "market_status": "fresh",
        "native_market_id": "OKX:BLEND-USDT",
    }
    if market is not None:
        base_market.update(market)
    return build_token_factor_snapshot(
        target={
            "target_type": "CexToken",
            "target_id": "cex_token:BLEND",
            "symbol": "BLEND",
            "pricefeed_id": "pf-blend",
        },
        attention={
            "mentions_1h": 7,
            "mentions_4h": 7,
            "mentions_24h": 9,
            "unique_authors": 5,
            "watched_mentions": 1,
        },
        social_quality={
            "duplicate_text_share": 0.0,
            "top_author_share": 0.25,
            "informative_post_count": 5,
            "mentions": 7,
            "independent_authors": 5,
            "effective_authors": 4.0,
        },
        social_semantics={
            "direction_counts": {"bullish": 3, "neutral": 2},
            "impact_mean": 0.5,
            "novelty_mean": 0.3,
            "confidence_mean": 0.8,
        },
        market=base_market,
        timing={"price_change_before_social_pct": 0.02, "price_change_since_social_pct": 0.01},
        source_event_ids=["event-1"],
        computed_at_ms=1_778_000_000_000,
    )
