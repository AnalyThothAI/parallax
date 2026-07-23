from __future__ import annotations

import pytest

from parallax.domains.token_intel.scoring.factor_snapshot import (
    DEX_HIGH_ALERT_FLOORS,
    FACTOR_FAMILIES,
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    build_token_factor_snapshot,
)
from parallax.domains.token_intel.scoring.factor_snapshot_contract import require_token_factor_snapshot


def test_scoring_package_exports_factor_snapshot_contract() -> None:
    from parallax.domains.token_intel import scoring

    assert TOKEN_FACTOR_SNAPSHOT_VERSION == "token_factor_snapshot_v4_transparent_factors"
    assert FACTOR_FAMILIES == (
        "social_heat",
        "social_propagation",
        "timing_risk",
    )
    assert scoring.TOKEN_FACTOR_SNAPSHOT_VERSION == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert scoring.FACTOR_FAMILIES == FACTOR_FAMILIES
    assert scoring.DEX_HIGH_ALERT_FLOORS == DEX_HIGH_ALERT_FLOORS
    assert scoring.build_token_factor_snapshot is build_token_factor_snapshot


def test_factor_snapshot_outputs_v4_transparent_factor_shape() -> None:
    snapshot = _strong_dex_snapshot(attention={"latest_seen_ms": 1_778_000_012_345})

    assert set(snapshot) == {
        "schema_version",
        "subject",
        "market",
        "gates",
        "data_health",
        "families",
        "normalization",
        "composite",
        "provenance",
    }
    assert "hard_gates" not in snapshot
    assert snapshot["schema_version"] == "token_factor_snapshot_v4_transparent_factors"
    assert snapshot["subject"] == {
        "target_type": "Asset",
        "target_id": "asset:solana:token:STRONG",
        "symbol": "STRONG",
        "target_market_type": "dex",
        "chain": "solana",
        "address": "STRONG",
        "pricefeed_id": "pf-strong",
    }
    assert set(snapshot["families"]) == {
        "social_heat",
        "social_propagation",
        "timing_risk",
    }
    assert not {
        "attention_heat",
        "diffusion_quality",
        "timing_response",
    } & set(snapshot["families"])
    assert snapshot["families"]["social_heat"]["facts"]["latest_seen_ms"] == 1_778_000_012_345
    heat_factors = snapshot["families"]["social_heat"]["factors"]
    assert set(heat_factors) >= {
        "attention_surprise",
        "source_weighted_mentions",
        "attention_acceleration",
        "watched_seed_strength",
    }
    assert "mentions_4h" not in heat_factors
    assert "mentions_24h" not in heat_factors
    assert snapshot["normalization"] == {
        "status": "pending_cross_section",
        "cohort_status": "pending_cross_section",
        "cohort": {},
        "factor_ranks": {family: None for family in FACTOR_FAMILIES},
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


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda subject: subject.pop("chain"), r"factor_snapshot\.subject\.chain is required"),
        (
            lambda subject: subject.__setitem__("chain_id", "solana"),
            r"factor_snapshot\.subject\.chain_id is not allowed",
        ),
    ],
)
def test_factor_snapshot_subject_requires_one_exact_identity_contract(mutate, error: str) -> None:
    snapshot = _strong_dex_snapshot()
    mutate(snapshot["subject"])

    with pytest.raises(ValueError, match=error):
        require_token_factor_snapshot(snapshot)


@pytest.mark.parametrize(
    ("block", "mutation", "error"),
    [
        ("gates", lambda value: value.pop("risk_reasons"), r"factor_snapshot\.gates\.risk_reasons is required"),
        (
            "gates",
            lambda value: value.__setitem__("eligible_for_watch", True),
            r"factor_snapshot\.gates\.eligible_for_watch is not allowed",
        ),
        (
            "composite",
            lambda value: value.pop("raw_alpha_score"),
            r"factor_snapshot\.composite\.raw_alpha_score is required",
        ),
        (
            "composite",
            lambda value: value.__setitem__("score", 50),
            r"factor_snapshot\.composite\.score is not allowed",
        ),
        (
            "normalization",
            lambda value: value.pop("cohort_status"),
            r"factor_snapshot\.normalization\.cohort_status is required",
        ),
    ],
)
def test_factor_snapshot_fixed_blocks_require_exact_contract(block: str, mutation, error: str) -> None:
    snapshot = _strong_dex_snapshot()
    mutation(snapshot[block])

    with pytest.raises(ValueError, match=error):
        require_token_factor_snapshot(snapshot)


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
        market=_dex_market({"pricefeed_id": "pf-quiet"}),
        timing={"social_signal_start_ms": 1_778_000_001_000},
        source_event_ids=["event-1"],
        computed_at_ms=1_778_000_002_000,
    )

    assert "identity" not in snapshot["families"]
    assert "market_quality" not in snapshot["families"]
    assert snapshot["data_health"]["identity"] == "ready"
    assert snapshot["data_health"]["market"] == "ready"
    assert snapshot["families"]["timing_risk"]["facts"]["social_signal_start_ms"] == 1_778_000_001_000
    assert snapshot["families"]["timing_risk"]["weight"] == 0
    assert "social_signal_start_ms" not in snapshot["families"]["timing_risk"]["factors"]
    assert snapshot["data_health"]["alpha"] == "missing"
    assert "alpha_data_missing" in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["max_decision"] == "discard"
    assert snapshot["composite"]["raw_alpha_score"] == 0
    assert snapshot["composite"]["recommended_decision"] == "discard"


def test_social_heat_formula_constants_match_spec() -> None:
    snapshot = _strong_dex_snapshot(
        attention={
            "weighted_mentions": 3.0,
            "watched_mentions": 2,
            "attention_acceleration": 2.0,
            "robust_z": 1.0,
            "z_score": None,
            "new_burst_score": 4.0,
        }
    )

    factors = snapshot["families"]["social_heat"]["factors"]
    assert factors["source_weighted_mentions"]["score"] == pytest.approx(_log_points(3.0, scale=3))
    assert factors["watched_seed_strength"]["score"] == pytest.approx(_log_points(2, scale=2))
    assert factors["attention_acceleration"]["score"] == pytest.approx(_log_points(2.0, scale=2))
    assert factors["attention_acceleration"]["confidence"] == pytest.approx(0.9)
    assert factors["attention_surprise"]["score"] == pytest.approx(47.5)
    assert factors["attention_surprise"]["confidence"] == pytest.approx(0.95)

    fallback = _strong_dex_snapshot(
        attention={"robust_z": None, "z_ewma": None, "z_score": None, "new_burst_score": 2.0}
    )
    fallback_surprise = fallback["families"]["social_heat"]["factors"]["attention_surprise"]
    assert fallback_surprise["score"] == pytest.approx(80.0)
    assert fallback_surprise["confidence"] == pytest.approx(0.95)


def test_social_factor_facts_preserve_auditable_inputs() -> None:
    snapshot = _strong_dex_snapshot(
        attention={
            "mentions_window": 6,
            "previous_mentions": 2,
            "mention_delta": 4,
            "mention_delta_pct": 2.0,
            "stream_share": 0.12,
            "z_score": 1.5,
            "z_ewma": 1.2,
            "robust_z": 1.0,
            "new_burst_score": 3.0,
            "baseline_status": "ready",
            "baseline_sample_count": 6,
            "baseline_nonzero_sample_count": 4,
            "zero_slot_count": 2,
        },
        social_quality={
            "informative_post_count": 8,
            "new_authors": 3,
            "watched_author_count": 1,
            "reproduction_rate": 0.75,
        },
    )

    heat_facts = snapshot["families"]["social_heat"]["facts"]
    assert heat_facts["mentions_window"] == 6
    assert heat_facts["previous_mentions"] == 2
    assert heat_facts["mention_delta"] == 4
    assert heat_facts["mention_delta_pct"] == 2.0
    assert heat_facts["stream_share"] == 0.12
    assert heat_facts["z_score"] == 1.5
    assert heat_facts["z_ewma"] == 1.2
    assert heat_facts["robust_z"] == 1.0
    assert heat_facts["new_burst_score"] == 3.0
    assert heat_facts["baseline_status"] == "ready"
    assert heat_facts["baseline_sample_count"] == 6
    assert heat_facts["baseline_nonzero_sample_count"] == 4
    assert heat_facts["zero_slot_count"] == 2

    propagation_facts = snapshot["families"]["social_propagation"]["facts"]
    assert propagation_facts["informative_post_count"] == 8
    assert propagation_facts["effective_authors"] == 6.0
    assert propagation_facts["new_authors"] == 3
    assert propagation_facts["watched_author_count"] == 1
    assert propagation_facts["reproduction_rate"] == 0.75


def test_social_propagation_formula_constants_and_speed_match_spec() -> None:
    snapshot = _strong_dex_snapshot(
        social_quality={
            "independent_authors": 4,
            "source_weighted_effective_authors": 5.0,
            "time_to_second_author_ms": 30 * 60_000,
            "time_to_third_author_ms": 45 * 60_000,
            "public_followup_author_count": 2,
        }
    )

    factors = snapshot["families"]["social_propagation"]["factors"]
    assert factors["independent_authors"]["score"] == pytest.approx(_log_points(4, scale=4))
    assert factors["source_weighted_effective_authors"]["score"] == pytest.approx(100.0)
    assert factors["watched_to_public_followup"]["score"] == pytest.approx(_log_points(2, scale=2))
    expected_second = 100 - 30 / 60 * 60
    expected_third = 100 - 45 / 60 * 40
    assert factors["propagation_speed"]["score"] == pytest.approx(expected_second * 0.65 + expected_third * 0.35)

    missing_second = _strong_dex_snapshot(
        social_quality={"time_to_second_author_ms": None, "time_to_third_author_ms": 45_000}
    )
    assert missing_second["families"]["social_propagation"]["factors"]["propagation_speed"]["raw_value"] is None
    assert missing_second["families"]["social_propagation"]["factors"]["propagation_speed"]["score"] == 0


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
    assert "dex_floor_below" in snapshot["gates"]["blocked_reasons"]
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "holders_below_high_alert_floor",
        "liquidity_below_high_alert_floor",
        "market_cap_below_high_alert_floor",
    }
    assert snapshot["gates"]["max_decision"] == "watch"
    assert snapshot["composite"]["recommended_decision"] == "watch"


def test_fresh_dex_market_missing_floor_inputs_is_not_market_ready() -> None:
    snapshot = _strong_dex_snapshot(
        market={
            "market_status": "fresh",
            "holders": None,
            "liquidity_usd": None,
            "market_cap_usd": None,
        }
    )

    assert snapshot["data_health"]["market"] == "partial"
    assert "market_metadata_missing" in snapshot["gates"]["risk_reasons"]
    assert "dex_floor_missing" in snapshot["gates"]["blocked_reasons"]
    assert "holders_unverified" in snapshot["gates"]["blocked_reasons"]
    assert "liquidity_usd_unverified" in snapshot["gates"]["blocked_reasons"]
    assert "market_cap_usd_unverified" in snapshot["gates"]["blocked_reasons"]
    assert "holders_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "liquidity_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "market_cap_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert snapshot["gates"]["max_decision"] == "watch"
    assert snapshot["composite"]["recommended_decision"] == "watch"


def test_dex_missing_market_fields_block_high_alert() -> None:
    snapshot = _strong_dex_snapshot(
        market={
            "holders": None,
            "liquidity_usd": None,
            "market_cap_usd": None,
        }
    )

    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert "dex_floor_missing" in snapshot["gates"]["blocked_reasons"]
    assert set(snapshot["gates"]["blocked_reasons"]) >= {
        "holders_unverified",
        "liquidity_usd_unverified",
        "market_cap_usd_unverified",
    }
    assert snapshot["gates"]["max_decision"] == "watch"
    assert snapshot["composite"]["recommended_decision"] == "watch"


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
    risky = _strong_dex_snapshot(
        attention={"watched_mentions": 0},
        social_quality={
            "duplicate_text_share": 0.75,
            "top_author_share": 0.80,
            "independent_authors": 1,
            "source_weighted_effective_authors": 1.0,
        },
    )

    clean_factors = clean["families"]["social_propagation"]["factors"]
    risky_factors = risky["families"]["social_propagation"]["factors"]
    assert risky_factors["independent_authors"]["score"] < clean_factors["independent_authors"]["score"]
    assert clean_factors["duplicate_text_share_penalty"]["score"] == 0
    assert clean_factors["top_author_concentration_penalty"]["score"] == 0
    assert risky_factors["duplicate_text_share_penalty"]["score"] < 0
    assert risky_factors["top_author_concentration_penalty"]["score"] < 0
    assert "duplicate_text_share_high" in risky["gates"]["blocked_reasons"]
    assert "author_concentration_high" in risky["gates"]["risk_reasons"]
    assert risky["families"]["social_propagation"]["score"] < clean["families"]["social_propagation"]["score"]


def test_independent_source_gate_uses_two_author_floor_and_credible_reason_name() -> None:
    watched_single_author = _strong_dex_snapshot(
        attention={"unique_authors": 1, "watched_mentions": 1},
        social_quality={"independent_authors": 1, "source_weighted_effective_authors": 1.0},
    )
    assert "insufficient_independent_social_sources" not in watched_single_author["gates"]["blocked_reasons"]

    public_single_author = _strong_dex_snapshot(
        attention={"unique_authors": 1, "watched_mentions": 0},
        social_quality={"independent_authors": 1, "source_weighted_effective_authors": 1.0},
    )
    assert "insufficient_independent_social_sources" in public_single_author["gates"]["blocked_reasons"]
    assert "insufficient_credible_social_sources" in public_single_author["gates"]["blocked_reasons"]
    assert "thin_credible_author_set" in public_single_author["gates"]["risk_reasons"]
    assert "thin_credible_source_set" not in public_single_author["gates"]["risk_reasons"]


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


def test_ready_market_with_strong_social_remains_eligible_for_high_alert() -> None:
    snapshot = _strong_dex_snapshot()

    assert snapshot["composite"]["raw_alpha_score"] >= 70
    assert snapshot["data_health"]["market"] == "ready"
    assert snapshot["gates"]["eligible_for_high_alert"] is True
    assert snapshot["gates"]["max_decision"] == "high_alert"
    assert snapshot["composite"]["recommended_decision"] == "high_alert"
    assert not {
        "market_anchor_missing",
        "market_latest_missing",
        "market_latest_stale",
        "dex_floor_missing",
        "dex_floor_below",
    } & set(snapshot["gates"]["blocked_reasons"])


def test_high_raw_alpha_with_missing_market_anchor_caps_high_alert_to_watch() -> None:
    market = _dex_market()
    market["event_anchor"] = None
    market["readiness"]["anchor_status"] = "missing"
    snapshot = _strong_dex_snapshot(market=market)

    assert snapshot["composite"]["raw_alpha_score"] >= 70
    assert snapshot["data_health"]["market"] == "missing"
    assert "market_anchor_missing" in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert snapshot["gates"]["max_decision"] == "watch"
    assert snapshot["composite"]["recommended_decision"] == "watch"


@pytest.mark.parametrize(
    ("latest_status", "reason"),
    [
        ("missing", "market_latest_missing"),
        ("stale", "market_latest_stale"),
    ],
)
def test_high_raw_alpha_with_degraded_latest_market_caps_high_alert_to_watch(
    latest_status: str,
    reason: str,
) -> None:
    market = _market_with_latest_status(latest_status)
    snapshot = _strong_dex_snapshot(market=market)

    assert snapshot["composite"]["raw_alpha_score"] >= 70
    assert snapshot["data_health"]["market"] == "partial"
    assert reason in snapshot["gates"]["blocked_reasons"]
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert snapshot["gates"]["max_decision"] == "watch"
    assert snapshot["composite"]["recommended_decision"] == "watch"


def test_unresolved_identity_and_stale_market_gate_high_alert() -> None:
    snapshot = _strong_dex_snapshot(
        target={"target_type": "source_seed", "target_id": "source_seed:event-1"},
        market={"market_status": "stale"},
    )

    assert snapshot["data_health"]["identity"] == "missing"
    assert snapshot["data_health"]["market"] == "partial"
    assert snapshot["gates"]["eligible_for_high_alert"] is False
    assert set(snapshot["gates"]["blocked_reasons"]) >= {"identity_unresolved", "market_latest_stale"}
    assert snapshot["gates"]["max_decision"] == "discard"
    assert snapshot["composite"]["recommended_decision"] == "discard"


def test_eligible_raw_alpha_35_recommends_watch() -> None:
    snapshot = _strong_dex_snapshot(
        attention={
            "mentions_1h": 0,
            "mentions_4h": 0,
            "mentions_24h": 0,
            "weighted_mentions": None,
            "unique_authors": 3,
            "watched_mentions": 0,
            "attention_acceleration": None,
            "new_burst_score": None,
            "robust_z": None,
        },
        social_quality={
            "informative_post_count": 2,
            "mentions": 0,
            "independent_authors": 3,
            "effective_authors": None,
            "source_weighted_effective_authors": None,
            "time_to_second_author_ms": None,
            "time_to_third_author_ms": None,
            "public_followup_author_count": 0,
            "author_entropy": None,
        },
        timing={
            "price_change_before_social_pct": None,
            "price_change_since_social_pct": None,
        },
    )

    assert snapshot["gates"]["eligible_for_high_alert"] is True
    assert snapshot["gates"]["max_decision"] == "high_alert"
    assert 35 <= snapshot["composite"]["raw_alpha_score"] < 70
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
        market=_dex_market(),
        timing={},
        source_event_ids=["event-empty"],
        computed_at_ms=1_778_000_000_000,
    )

    assert snapshot["families"]["social_heat"]["data_health"] == "missing"
    assert snapshot["families"]["social_propagation"]["data_health"] == "missing"
    assert snapshot["families"]["social_heat"]["facts"]["mentions_1h"] == 0
    assert snapshot["families"]["social_propagation"]["facts"]["independent_authors"] == 0
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
        timing={"social_signal_start_ms": float("inf")},
    )

    assert snapshot["families"]["social_heat"]["facts"]["mentions_1h"] == 0
    assert snapshot["families"]["social_propagation"]["factors"]["duplicate_text_share_penalty"]["raw_value"] is None
    concentration_penalty = snapshot["families"]["social_propagation"]["factors"]["top_author_concentration_penalty"]
    assert concentration_penalty["raw_value"] is None
    assert snapshot["families"]["timing_risk"]["facts"]["social_signal_start_ms"] is None
    assert "market_metadata_missing" in snapshot["gates"]["risk_reasons"]
    assert "dex_floor_missing" in snapshot["gates"]["blocked_reasons"]
    assert "market_cap_usd_unverified" in snapshot["gates"]["blocked_reasons"]
    assert "holders_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "liquidity_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]
    assert "market_cap_below_high_alert_floor" not in snapshot["gates"]["blocked_reasons"]


@pytest.mark.parametrize("computed_at_ms", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_computed_at_ms_normalizes_to_zero(computed_at_ms: float) -> None:
    snapshot = _strong_dex_snapshot(computed_at_ms=computed_at_ms)

    assert snapshot["provenance"]["computed_at_ms"] == 0


def test_timing_risk_is_zero_weight_negative_only_and_reports_chase_or_late_risks() -> None:
    snapshot = _strong_dex_snapshot(
        timing={
            "price_change_before_social_pct": 0.30,
            "price_change_since_social_pct": 0.60,
        }
    )

    timing = snapshot["families"]["timing_risk"]
    assert timing["weight"] == 0
    assert timing["score"] == 0
    assert snapshot["composite"]["raw_alpha_score"] == _strong_dex_snapshot(timing={})["composite"]["raw_alpha_score"]
    assert timing["factors"]["pre_social_chase_risk"]["score"] == pytest.approx(-100.0)
    assert timing["factors"]["post_social_late_risk"]["score"] == pytest.approx(-100.0)
    assert "timing_chase_risk" in snapshot["gates"]["risk_reasons"]
    assert "timing_late_risk" in snapshot["gates"]["risk_reasons"]


def test_timing_risk_uses_material_decision_latest_status() -> None:
    snapshot = _strong_dex_snapshot(
        timing={"price_change_since_social_pct": 0.50},
    )

    timing = snapshot["families"]["timing_risk"]
    assert timing["data_health"] == "ready"
    assert timing["weight"] == 0
    assert timing["score"] == 0
    assert timing["facts"]["price_change_status"] == "live"
    assert timing["facts"]["price_change_since_social_pct"] == 0.50
    assert "post_social_late_risk" in timing["factors"]


def _all_factor_keys(snapshot: dict[str, object]) -> set[str]:
    families = snapshot["families"]
    assert isinstance(families, dict)
    return {key for family in families.values() if isinstance(family, dict) for key in (family.get("factors") or {})}


def _log_points(value: float, *, scale: float) -> float:
    import math

    return min(100.0, math.log1p(max(0.0, value)) / math.log1p(scale) * 100.0)


def _dex_market(overrides: dict[str, object] | None = None) -> dict[str, object]:
    event_anchor = {
        "target_type": "Asset",
        "target_id": "asset:solana:token:STRONG",
        "observed_at_ms": 1_778_000_000_000,
        "received_at_ms": 1_778_000_000_000,
        "source": "event_anchor",
        "provider": "gmgn_dex_quote",
        "pricefeed_id": "pf-strong",
        "price_usd": 1.0,
        "price_quote": None,
        "quote_symbol": "USD",
        "price_basis": "usd",
        "market_cap_usd": None,
        "liquidity_usd": None,
        "holders": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
    }
    decision_latest = {
        **event_anchor,
        "source": "decision_latest",
        "observed_at_ms": 1_778_000_030_000,
        "received_at_ms": 1_778_000_030_000,
        "price_usd": 1.03,
        "market_cap_usd": 500_000.0,
        "liquidity_usd": 150_000.0,
        "holders": 1_500,
    }
    status = "live"
    payload = dict(overrides or {})
    if payload:
        status_value = payload.pop("market_status", None)
        if status_value == "stale":
            status = "stale"
        elif status_value is None and "market_status" in (overrides or {}):
            return {
                "event_anchor": None,
                "decision_latest": None,
                "readiness": {
                    "anchor_status": "missing",
                    "latest_status": "missing",
                    "dex_floor_status": "missing_fields",
                    "missing_fields": ["holders", "liquidity_usd", "market_cap_usd"],
                    "stale_fields": [],
                },
            }
        for key in (
            "holders",
            "liquidity_usd",
            "market_cap_usd",
            "volume_24h_usd",
            "open_interest_usd",
            "pricefeed_id",
        ):
            if key in payload:
                decision_latest[key] = payload[key]
    missing_fields = [key for key in ("holders", "liquidity_usd", "market_cap_usd") if decision_latest.get(key) is None]
    return {
        "event_anchor": event_anchor,
        "decision_latest": decision_latest,
        "readiness": {
            "anchor_status": "ready",
            "latest_status": status,
            "dex_floor_status": "missing_fields" if missing_fields else "ready",
            "missing_fields": missing_fields,
            "stale_fields": ["decision_latest"] if status == "stale" else [],
        },
    }


def _market_with_latest_status(latest_status: str) -> dict[str, object]:
    market = _dex_market()
    market["readiness"]["latest_status"] = latest_status
    if latest_status == "missing":
        market["decision_latest"] = None
        market["readiness"]["dex_floor_status"] = "missing_fields"
        market["readiness"]["missing_fields"] = ["holders", "liquidity_usd", "market_cap_usd"]
        market["readiness"]["stale_fields"] = []
    elif latest_status == "stale":
        market["readiness"]["stale_fields"] = ["decision_latest"]
    return market


def _cex_market(overrides: dict[str, object] | None = None) -> dict[str, object]:
    market = _dex_market({})
    latest = dict(market["decision_latest"])
    latest.update(
        {
            "target_type": "CexToken",
            "target_id": "cex_token:BLEND",
            "provider": "binance_cex",
            "pricefeed_id": "pf-blend",
            "volume_24h_usd": 45_000_000.0,
            "open_interest_usd": 8_000_000.0,
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
        }
    )
    if overrides:
        status_value = overrides.get("market_status")
        if status_value == "stale":
            market["readiness"]["latest_status"] = "stale"
            market["readiness"]["stale_fields"] = ["decision_latest"]
        for key in ("volume_24h_usd", "open_interest_usd", "pricefeed_id"):
            if key in overrides:
                latest[key] = overrides[key]
    market["decision_latest"] = latest
    market["readiness"]["dex_floor_status"] = "ready"
    market["readiness"]["missing_fields"] = []
    return market


def _strong_dex_snapshot(
    *,
    target: dict[str, object] | None = None,
    attention: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    social_quality: dict[str, object] | None = None,
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
        "mentions_5m": 6,
        "mentions_1h": 12,
        "mentions_4h": 18,
        "mentions_24h": 32,
        "weighted_mentions": 8.5,
        "unique_authors": 8,
        "watched_mentions": 2,
        "attention_acceleration": 2.0,
        "new_burst_score": 3.0,
        "robust_z": 4.0,
    }
    if attention is not None:
        base_attention.update(attention)
    base_market = market if market is not None and _is_full_market_payload(market) else _dex_market(market)
    base_social_quality: dict[str, object] = {
        "duplicate_text_share": 0.0,
        "top_author_share": 0.20,
        "informative_post_count": 8,
        "mentions": 12,
        "independent_authors": 8,
        "effective_authors": 6.0,
        "source_weighted_effective_authors": 6.0,
        "time_to_second_author_ms": 60_000,
        "time_to_third_author_ms": 180_000,
        "public_followup_author_count": 5,
        "author_entropy": 1.4,
    }
    if social_quality is not None:
        base_social_quality.update(social_quality)
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
        market=base_market,
        timing=base_timing,
        source_event_ids=["event-strong-1", "event-strong-2", "event-strong-1"],
        computed_at_ms=computed_at_ms,
    )


def _is_full_market_payload(market: dict[str, object]) -> bool:
    return {"event_anchor", "decision_latest", "readiness"} <= set(market)


def _strong_cex_snapshot(
    *,
    market: dict[str, object] | None = None,
) -> dict[str, object]:
    base_market = _cex_market(market)
    return build_token_factor_snapshot(
        target={
            "target_type": "CexToken",
            "target_id": "cex_token:BLEND",
            "symbol": "BLEND",
            "pricefeed_id": "pf-blend",
        },
        attention={
            "mentions_5m": 4,
            "mentions_1h": 7,
            "mentions_4h": 7,
            "mentions_24h": 9,
            "weighted_mentions": 4.5,
            "unique_authors": 5,
            "watched_mentions": 1,
            "attention_acceleration": 1.0,
            "new_burst_score": 1.0,
        },
        social_quality={
            "duplicate_text_share": 0.0,
            "top_author_share": 0.25,
            "informative_post_count": 5,
            "mentions": 7,
            "independent_authors": 5,
            "effective_authors": 4.0,
            "source_weighted_effective_authors": 4.0,
            "time_to_second_author_ms": 45_000,
            "time_to_third_author_ms": 90_000,
            "public_followup_author_count": 4,
            "author_entropy": 1.2,
        },
        market=base_market,
        timing={"price_change_before_social_pct": 0.02, "price_change_since_social_pct": 0.01},
        source_event_ids=["event-1"],
        computed_at_ms=1_778_000_000_000,
    )
