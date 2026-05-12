from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_FACTOR_FAMILIES,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_diagnostics import factor_distribution_report


def test_factor_distribution_report_flags_low_rank_score_diversity() -> None:
    rows = [_row(rank_score=80 if index % 2 else 90) for index in range(21)]

    report = factor_distribution_report(rows)

    assert report["ok"] is False
    assert report["row_count"] == 21
    assert report["rank_score_unique_count"] == 2
    assert any(item["code"] == "rank_score_low_diversity" for item in report["violations"])


def test_factor_distribution_report_flags_family_100_saturation() -> None:
    rows = [
        _row(
            rank_score=index,
            family_scores={
                "social_heat": 100 if index < 6 else 40,
                "social_propagation": 50,
                "semantic_catalyst": 50,
                "timing_risk": 50,
            },
        )
        for index in range(20)
    ]

    report = factor_distribution_report(rows)

    assert report["ok"] is False
    assert report["family_saturation_100_share"]["social_heat"] == 0.3
    assert any(
        item["code"] == "family_score_100_saturation" and item["family"] == "social_heat"
        for item in report["violations"]
    )


def test_factor_distribution_report_accepts_v3_family_keys() -> None:
    report = factor_distribution_report([_row()])

    assert report["ok"] is True
    assert not any(item["code"] == "unexpected_factor_family_keys" for item in report["violations"])


def test_factor_distribution_report_flags_old_v2_family_keys_and_hard_gates() -> None:
    snapshot = _snapshot(rank_score=55)
    snapshot["families"]["attention_heat"] = _family(80)
    snapshot["families"]["diffusion_quality"] = _family(80)
    snapshot["families"]["semantic_quality"] = _family(80)
    snapshot["families"]["timing_response"] = _family(80)
    snapshot["hard_gates"] = {"eligible_for_high_alert": True}

    report = factor_distribution_report([{"factor_snapshot_json": snapshot}])

    assert report["ok"] is False
    old_family_violation = next(
        item for item in report["violations"] if item["code"] == "unexpected_factor_family_keys"
    )
    assert old_family_violation["families"] == [
        "attention_heat",
        "diffusion_quality",
        "semantic_quality",
        "timing_response",
    ]
    assert any(item["code"] == "hard_gates_present" for item in report["violations"])


def test_factor_distribution_report_flags_old_v1ish_family_keys() -> None:
    snapshot = _snapshot(rank_score=55)
    snapshot["families"]["market_quality"] = _family(80)
    snapshot["families"]["social_attention"] = _family(80)

    report = factor_distribution_report([{"factor_snapshot_json": snapshot}])

    assert report["ok"] is False
    old_family_violation = next(
        item for item in report["violations"] if item["code"] == "unexpected_factor_family_keys"
    )
    assert old_family_violation["families"] == ["market_quality", "social_attention"]


def test_factor_distribution_report_counts_gates_and_data_health() -> None:
    rows = [
        _row(gate_reasons=["market_stale", "thin_author_set"], data_health={"market": "partial", "alpha": "ready"}),
        _row(gate_reasons=["market_stale"], data_health={"market": "ready", "alpha": "missing"}),
    ]

    report = factor_distribution_report(rows)

    assert report["ok"] is True
    assert report["gate_block_counts"] == {"market_stale": 2, "thin_author_set": 1}
    assert report["data_health_counts"] == {
        "alpha": {"missing": 1, "ready": 1},
        "identity": {"ready": 2},
        "market": {"partial": 1, "ready": 1},
        "social": {"ready": 2},
    }


def _row(
    *,
    rank_score: float = 55,
    family_scores: dict[str, float] | None = None,
    gate_reasons: list[str] | None = None,
    data_health: dict[str, str] | None = None,
) -> dict:
    return {
        "factor_snapshot_json": _snapshot(
            rank_score=rank_score,
            family_scores=family_scores,
            gate_reasons=gate_reasons,
            data_health=data_health,
        )
    }


def _snapshot(
    *,
    rank_score: float,
    family_scores: dict[str, float] | None = None,
    gate_reasons: list[str] | None = None,
    data_health: dict[str, str] | None = None,
) -> dict:
    family_scores = family_scores or {family: 50 for family in TOKEN_RADAR_FACTOR_FAMILIES}
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {"target_type": "Asset", "target_id": "asset:pepe"},
        "gates": {
            "eligible_for_high_alert": not gate_reasons,
            "blocked_reasons": gate_reasons or [],
        },
        "data_health": {
            "identity": "ready",
            "market": "ready",
            "social": "ready",
            "alpha": "ready",
            **(data_health or {}),
        },
        "families": {family: _family(score) for family, score in family_scores.items()},
        "normalization": {"status": "ready"},
        "composite": {"rank_score": rank_score, "recommended_decision": "watch"},
    }


def _family(score: float) -> dict:
    return {"score": score, "data_health": "ready", "facts": {}, "factors": {}}
