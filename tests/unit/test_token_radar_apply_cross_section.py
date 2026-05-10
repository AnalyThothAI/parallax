"""Deterministic unit tests for TokenRadarProjection._apply_cross_section.

The cross-section pass is otherwise only covered by the live-PG idempotency
test. These tests construct synthetic projected rows and verify the
classify-rank-rewrite-strip flow without requiring a database.
"""

from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.scoring.cross_section_normalizer import NORMALIZER_VERSION
from gmgn_twitter_intel.domains.token_intel.scoring.factor_cohort import COHORT_DEFINITION_VERSION
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection


def _row(
    *,
    target_id: str,
    symbol: str,
    opportunity_score: float | None = 50.0,
    high_conf: int = 1,
    kol_count: int = 0,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "target_json": {"symbol": symbol},
        "score_json": {
            "opportunity": {"score": opportunity_score, "score_version": "social_opportunity_v4"},
        },
        "_cohort_high_conf_count": high_conf,
        "_cohort_kol_count": kol_count,
    }


def test_cross_section_ranks_cohort_members_and_excludes_stablecoins():
    rows = [
        _row(target_id="asset:pepe", symbol="PEPE", opportunity_score=30.0),
        _row(target_id="asset:wif", symbol="WIF", opportunity_score=70.0),
        _row(target_id="asset:bonk", symbol="BONK", opportunity_score=50.0),
        _row(target_id="cex_token:USDT", symbol="USDT", opportunity_score=99.0),
        _row(target_id="cex_token:USDC", symbol="USDC", opportunity_score=99.0),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)

    by_id = {r["target_id"]: r["score_json"] for r in result}

    assert by_id["asset:wif"]["cross_section_rank"] == 1.0
    assert by_id["asset:bonk"]["cross_section_rank"] == 2 / 3
    assert by_id["asset:pepe"]["cross_section_rank"] == 1 / 3

    assert by_id["cex_token:USDT"]["cross_section_rank"] is None
    assert by_id["cex_token:USDC"]["cross_section_rank"] is None
    assert by_id["cex_token:USDT"]["cohort"]["in_cohort"] is False
    assert by_id["cex_token:USDC"]["cohort"]["in_cohort"] is False


def test_cross_section_writes_cohort_metadata_with_versions():
    rows = [_row(target_id="asset:pepe", symbol="PEPE", high_conf=3, kol_count=1)]

    result = TokenRadarProjection._apply_cross_section(rows)

    cohort = result[0]["score_json"]["cohort"]
    assert cohort["in_cohort"] is True
    assert cohort["size"] == 1
    assert cohort["definition_version"] == COHORT_DEFINITION_VERSION
    assert cohort["normalizer_version"] == NORMALIZER_VERSION
    assert cohort["high_confidence_mentions"] == 3
    assert cohort["kol_mentions"] == 1
    assert cohort["symbol"] == "PEPE"
    assert cohort["first_seen_global_24h"] is False


def test_cross_section_strips_internal_cohort_fields():
    rows = [_row(target_id="asset:pepe", symbol="PEPE")]

    result = TokenRadarProjection._apply_cross_section(rows)

    assert "_cohort_high_conf_count" not in result[0]
    assert "_cohort_kol_count" not in result[0]


def test_cross_section_leaves_attention_lane_rows_with_no_target_id_alone():
    """Rows with empty/missing target_id (attention lane) should still get
    score_json.cross_section_rank=None and cohort metadata, just without
    being added to the cohort itself."""
    rows = [
        _row(target_id="asset:pepe", symbol="PEPE"),
        {
            "target_id": None,
            "target_json": None,
            "score_json": {"opportunity": {"score": 40.0}},
            "_cohort_high_conf_count": 0,
            "_cohort_kol_count": 0,
        },
    ]

    result = TokenRadarProjection._apply_cross_section(rows)

    attention_row = result[1]["score_json"]
    assert attention_row["cross_section_rank"] is None
    assert attention_row["cohort"]["in_cohort"] is False
    assert attention_row["cohort"]["size"] == 1


def test_cross_section_skips_non_qualifying_tokens_from_cohort():
    """Token with no high-conf mentions, no KOL mentions, no first-seen-global
    should be excluded from cohort even though it has an opportunity score."""
    rows = [
        _row(target_id="asset:noise", symbol="NOISE", high_conf=0, kol_count=0),
        _row(target_id="asset:real", symbol="REAL", high_conf=2, kol_count=0),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["score_json"] for r in result}

    assert by_id["asset:noise"]["cohort"]["in_cohort"] is False
    assert by_id["asset:noise"]["cross_section_rank"] is None
    assert by_id["asset:real"]["cohort"]["in_cohort"] is True
    assert by_id["asset:real"]["cross_section_rank"] == 1.0


def test_cross_section_handles_none_opportunity_score():
    rows = [
        _row(target_id="asset:has_score", symbol="HAS", opportunity_score=42.0),
        _row(target_id="asset:no_score", symbol="NONE", opportunity_score=None),
    ]

    result = TokenRadarProjection._apply_cross_section(rows)
    by_id = {r["target_id"]: r["score_json"] for r in result}

    assert by_id["asset:has_score"]["cross_section_rank"] == 1.0
    assert by_id["asset:no_score"]["cross_section_rank"] is None
    assert by_id["asset:no_score"]["cohort"]["in_cohort"] is True
