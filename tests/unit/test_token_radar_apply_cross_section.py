"""Deterministic unit tests for TokenRadarProjection._apply_cross_section.

The cross-section pass is otherwise only covered by the live-PG idempotency
test. These tests construct synthetic projected rows and verify the
classify-rank-normalize-strip flow without requiring a database.
"""

from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.token_intel.scoring.cross_section_normalizer import NORMALIZER_VERSION
from gmgn_twitter_intel.domains.token_intel.scoring.factor_cohort import COHORT_DEFINITION_VERSION
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection


def _row(
    *,
    target_id: str,
    symbol: str,
    rank_score: float | None = 50.0,
    family_scores: dict[str, float | None] | None = None,
    high_conf: int = 2,
    kol_count: int = 0,
    first_seen_global_24h: bool = False,
    public_followup_authors: int = 0,
) -> dict[str, Any]:
    resolved_family_scores = family_scores or {
        "social_heat": rank_score,
        "social_propagation": rank_score,
        "semantic_catalyst": rank_score,
        "timing_risk": rank_score,
    }
    return {
        "target_id": target_id,
        "decision": "watch",
        "target_json": {"symbol": symbol},
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {"target_id": target_id},
            "market": _market(),
            "gates": {"max_decision": "high_alert", "blocked_reasons": []},
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "composite": {
                "raw_alpha_score": rank_score,
                "rank_score": rank_score,
                "recommended_decision": "watch",
                "family_scores": resolved_family_scores,
            },
            "families": {
                "social_heat": _family(resolved_family_scores["social_heat"], 0.45),
                "social_propagation": _family(resolved_family_scores["social_propagation"], 0.40),
                "semantic_catalyst": _family(resolved_family_scores["semantic_catalyst"], 0.15),
                "timing_risk": _family(resolved_family_scores["timing_risk"], 0.0),
            },
            "normalization": {"status": "pending_cross_section", "cohort": {}, "factor_ranks": {}, "alpha_rank": None},
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
        },
        "score_json": {},
        "_cohort_high_conf_count": high_conf,
        "_cohort_kol_count": kol_count,
        "_cohort_first_seen_global_24h": first_seen_global_24h,
        "_cohort_public_followup_count": public_followup_authors,
    }


def _family(score: float | None, weight: float) -> dict[str, Any]:
    resolved_score = 0.0 if score is None else score
    return {
        "raw_score": resolved_score,
        "score": resolved_score,
        "weight": weight,
        "data_health": "ready",
        "facts": {},
        "factors": {},
    }


def _market(status: str = "anchored") -> dict[str, Any]:
    if status == "missing":
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
    return {
        "event_anchor": {
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "observed_at_ms": 1_700_000_000_000,
            "received_at_ms": 1_700_000_000_000,
            "source": "event_anchor",
            "provider": "okx",
            "pricefeed_id": "pf",
            "price_usd": 0.42,
            "price_quote": None,
            "quote_symbol": "USD",
            "price_basis": "usd",
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
            "volume_24h_usd": None,
            "open_interest_usd": None,
            "raw_payload_hash": None,
        },
        "decision_latest": {
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "observed_at_ms": 1_700_000_030_000,
            "received_at_ms": 1_700_000_030_000,
            "source": "decision_latest",
            "provider": "okx",
            "pricefeed_id": "pf",
            "price_usd": 0.44,
            "price_quote": None,
            "quote_symbol": "USD",
            "price_basis": "usd",
            "market_cap_usd": 500_000.0,
            "liquidity_usd": 150_000.0,
            "holders": 1_500,
            "volume_24h_usd": None,
            "open_interest_usd": None,
            "raw_payload_hash": None,
        },
        "readiness": {
            "anchor_status": "ready",
            "latest_status": "live" if status != "stale" else "stale",
            "dex_floor_status": "ready",
            "missing_fields": [],
            "stale_fields": [] if status != "stale" else ["decision_latest"],
        },
    }


def test_cross_section_ranks_cohort_members_and_excludes_stablecoins():
    rows = [
        _row(target_id="asset:pepe", symbol="PEPE", rank_score=30.0),
        _row(target_id="asset:wif", symbol="WIF", rank_score=70.0),
        _row(target_id="asset:bonk", symbol="BONK", rank_score=50.0),
        _row(target_id="cex_token:USDT", symbol="USDT", rank_score=99.0),
        _row(target_id="cex_token:USDC", symbol="USDC", rank_score=99.0),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)

    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}

    assert by_id["asset:wif"]["alpha_rank"] is None
    assert by_id["asset:bonk"]["alpha_rank"] is None
    assert by_id["asset:pepe"]["alpha_rank"] is None
    assert by_id["asset:wif"]["cohort_status"] == "insufficient"

    assert by_id["cex_token:USDT"]["alpha_rank"] is None
    assert by_id["cex_token:USDC"]["alpha_rank"] is None
    assert by_id["cex_token:USDT"]["cohort"]["in_cohort"] is False
    assert by_id["cex_token:USDC"]["cohort"]["in_cohort"] is False


def test_small_or_all_tied_cohort_returns_no_signal():
    small_rows = [_row(target_id=f"asset:small-{index}", symbol=f"SMALL{index}") for index in range(9)]
    tied_rows = [_row(target_id=f"asset:tied-{index}", symbol=f"TIED{index}") for index in range(10)]

    small_result = TokenRadarProjection._apply_cross_section(small_rows)
    tied_result = TokenRadarProjection._apply_cross_section(tied_rows)

    assert {row["factor_snapshot_json"]["normalization"]["status"] for row in small_result} == {"no_signal"}
    assert {row["factor_snapshot_json"]["normalization"]["cohort_status"] for row in small_result} == {"insufficient"}
    assert {row["factor_snapshot_json"]["normalization"]["status"] for row in tied_result} == {"no_signal"}
    assert {row["factor_snapshot_json"]["normalization"]["cohort_status"] for row in tied_result} == {"all_tied"}
    assert all(row["factor_snapshot_json"]["normalization"]["alpha_rank"] is None for row in tied_result)


def test_cross_section_writes_cohort_metadata_with_versions():
    rows = [_row(target_id="asset:pepe", symbol="PEPE", high_conf=3, kol_count=1, public_followup_authors=2)]

    result = TokenRadarProjection._apply_cross_section(rows)

    cohort = result[0]["factor_snapshot_json"]["normalization"]["cohort"]
    assert cohort["in_cohort"] is True
    assert cohort["size"] == 1
    assert cohort["definition_version"] == COHORT_DEFINITION_VERSION
    assert cohort["normalizer_version"] == NORMALIZER_VERSION
    assert cohort["high_confidence_mentions"] == 3
    assert cohort["kol_mentions"] == 1
    assert cohort["public_followup_authors"] == 2
    assert cohort["symbol"] == "PEPE"
    assert cohort["first_seen_global_24h"] is False


def test_cross_section_strips_internal_cohort_fields():
    rows = [_row(target_id="asset:pepe", symbol="PEPE")]

    result = TokenRadarProjection._apply_cross_section(rows)

    assert "_cohort_high_conf_count" not in result[0]
    assert "_cohort_kol_count" not in result[0]
    assert "_cohort_first_seen_global_24h" not in result[0]
    assert "_cohort_public_followup_count" not in result[0]


def test_cross_section_includes_first_seen_only_tokens_in_cohort():
    rows = [
        _row(
            target_id="asset:new",
            symbol="NEW",
            high_conf=0,
            kol_count=0,
            first_seen_global_24h=True,
        )
    ]

    result = TokenRadarProjection._apply_cross_section(rows)

    cohort = result[0]["factor_snapshot_json"]["normalization"]["cohort"]
    assert cohort["in_cohort"] is True
    assert cohort["first_seen_global_24h"] is True
    assert cohort["high_confidence_mentions"] == 0
    assert cohort["kol_mentions"] == 0


def test_cross_section_keeps_public_followup_metadata_out_of_active_cohort_condition():
    rows = [
        _row(
            target_id="asset:public",
            symbol="PUBLIC",
            high_conf=0,
            kol_count=0,
            first_seen_global_24h=False,
            public_followup_authors=4,
        ),
        _row(target_id="asset:real", symbol="REAL", high_conf=2, kol_count=0),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}

    assert by_id["asset:public"]["cohort"]["in_cohort"] is False
    assert by_id["asset:public"]["cohort"]["public_followup_authors"] == 4
    assert by_id["asset:public"]["alpha_rank"] is None


def test_cross_section_leaves_attention_lane_rows_with_no_target_id_alone():
    """Rows with empty/missing target_id (attention lane) should still get
    factor_snapshot.normalization.cross_section_rank=None and cohort metadata, just without
    being added to the cohort itself."""
    rows = [
        _row(target_id="asset:pepe", symbol="PEPE"),
        {
            "target_id": None,
            "target_json": None,
            "factor_snapshot_json": {
                "schema_version": "token_factor_snapshot_v3_social_attention",
                "subject": {"target_id": None},
                "market": _market(status="missing"),
                "gates": {"max_decision": "high_alert", "blocked_reasons": []},
                "data_health": {"identity": "missing", "market": "missing", "social": "ready", "alpha": "ready"},
                "composite": {
                    "raw_alpha_score": 40.0,
                    "rank_score": 40.0,
                    "recommended_decision": "watch",
                    "family_scores": {
                        "social_heat": 40.0,
                        "social_propagation": 40.0,
                        "semantic_catalyst": 40.0,
                        "timing_risk": 40.0,
                    },
                },
                "families": {
                    "social_heat": _family(40.0, 0.45),
                    "social_propagation": _family(40.0, 0.40),
                    "semantic_catalyst": _family(40.0, 0.15),
                    "timing_risk": _family(40.0, 0.0),
                },
                "normalization": {
                    "status": "pending_cross_section",
                    "cohort": {},
                    "factor_ranks": {},
                    "alpha_rank": None,
                },
                "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
            },
            "score_json": {},
            "_cohort_high_conf_count": 0,
            "_cohort_kol_count": 0,
            "_cohort_public_followup_count": 0,
        },
    ]

    result = TokenRadarProjection._apply_cross_section(rows)

    attention_row = result[1]["factor_snapshot_json"]["normalization"]
    assert attention_row["alpha_rank"] is None
    assert attention_row["cohort"]["in_cohort"] is False
    assert attention_row["cohort"]["size"] == 1


def test_cross_section_skips_non_qualifying_tokens_from_cohort():
    """Token with no high-conf mentions, no KOL mentions, no first-seen-global
    should be excluded from cohort even though it has a rank score."""
    rows = [
        _row(target_id="asset:noise", symbol="NOISE", high_conf=0, kol_count=0),
        _row(target_id="asset:real", symbol="REAL", high_conf=2, kol_count=0),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}

    assert by_id["asset:noise"]["cohort"]["in_cohort"] is False
    assert by_id["asset:noise"]["alpha_rank"] is None
    assert by_id["asset:real"]["cohort"]["in_cohort"] is True
    assert by_id["asset:real"]["alpha_rank"] is None
    assert by_id["asset:real"]["cohort_status"] == "insufficient"


def test_cross_section_uses_family_scores_when_composite_rank_score_is_missing():
    rows = [
        _row(target_id="asset:has_score", symbol="HAS", rank_score=42.0),
        _row(target_id="asset:no_score", symbol="NONE", rank_score=None),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}

    assert by_id["asset:has_score"]["alpha_rank"] is None
    assert by_id["asset:no_score"]["alpha_rank"] is None
    assert by_id["asset:has_score"]["cohort_status"] == "insufficient"
    assert by_id["asset:no_score"]["cohort"]["in_cohort"] is True


def test_cross_section_updates_family_scores_composite_and_decision_from_factor_ranks():
    rows = [
        _row(target_id="asset:hot", symbol="HOT", rank_score=90.0, high_conf=2),
        _row(target_id="asset:cold", symbol="COLD", rank_score=10.0, high_conf=2),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    hot = next(r for r in result if r["target_id"] == "asset:hot")
    cold = next(r for r in result if r["target_id"] == "asset:cold")

    assert hot["factor_snapshot_json"]["normalization"]["status"] == "no_signal"
    assert hot["factor_snapshot_json"]["normalization"]["cohort_status"] == "insufficient"
    assert hot["factor_snapshot_json"]["families"]["social_heat"]["score"] == 90.0
    assert hot["factor_snapshot_json"]["composite"]["rank_score"] == 90
    assert hot["factor_snapshot_json"]["composite"]["recommended_decision"] == "high_alert"
    assert hot["decision"] == "high_alert"
    assert cold["factor_snapshot_json"]["families"]["social_heat"]["score"] == 10.0
    assert cold["factor_snapshot_json"]["composite"]["rank_score"] == 10
    assert cold["factor_snapshot_json"]["composite"]["recommended_decision"] == "discard"
    assert cold["decision"] == "discard"


def test_cross_section_zero_weight_timing_risk_cannot_dominate_alpha_rank():
    rows = [
        _row(
            target_id="asset:social",
            symbol="SOCIAL",
            rank_score=50.0,
            family_scores={
                "social_heat": 100.0,
                "social_propagation": 100.0,
                "semantic_catalyst": 100.0,
                "timing_risk": 0.0,
            },
        ),
        _row(
            target_id="asset:timing",
            symbol="TIMING",
            rank_score=50.0,
            family_scores={
                "social_heat": 0.0,
                "social_propagation": 0.0,
                "semantic_catalyst": 0.0,
                "timing_risk": 100.0,
            },
        ),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}

    assert by_id["asset:social"]["alpha_rank"] is None
    assert by_id["asset:timing"]["alpha_rank"] is None
    assert by_id["asset:social"]["cohort_status"] == "insufficient"


def test_cross_section_rejects_snapshot_with_legacy_hard_gates():
    row = _row(target_id="asset:legacy", symbol="OLD")
    row["factor_snapshot_json"]["hard_gates"] = {"eligible_for_high_alert": True}

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.hard_gates is not allowed"):
        TokenRadarProjection._apply_cross_section([row])
