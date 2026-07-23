from __future__ import annotations

import pytest

from parallax.domains.token_intel.scoring.cross_section_normalizer import (
    NORMALIZER_VERSION,
    rank_factors_within_cohort,
    rank_within_cohort,
    weighted_rank_score,
)


def test_rank_returns_percentiles_for_cohort_members():
    scores = {chr(97 + index): float(index + 1) for index in range(10)}
    cohort = set(scores)
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == 0.10
    assert ranks["c"] == 0.30
    assert ranks["b"] == 0.20
    assert ranks["j"] == 1.00


def test_rank_returns_none_for_non_cohort_members():
    scores = {chr(97 + index): float(index + 1) for index in range(10)}
    scores["btc"] = 100.0
    cohort = set(scores) - {"btc"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] is not None
    assert ranks["b"] is not None
    assert ranks["btc"] is None


def test_rank_handles_ties_with_average_method():
    scores = {"a": 10.0, "b": 10.0, **{chr(99 + index): float(index + 30) for index in range(8)}}
    cohort = set(scores)
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == ranks["b"]
    assert ranks["a"] == 0.15
    assert ranks["j"] == 1.0


def test_rank_with_single_cohort_member_returns_no_signal():
    scores = {"only_one": 42.0, "outsider": 0.0}
    cohort = {"only_one"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["only_one"] is None
    assert ranks["outsider"] is None


def test_rank_skips_none_scores_inside_cohort():
    scores = {"a": 10.0, "b": None, **{chr(99 + index): float(index + 30) for index in range(9)}}
    cohort = set(scores)
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["a"] == 0.1
    assert ranks["b"] is None
    assert ranks["k"] == 1.0


def test_empty_cohort_returns_none_for_all():
    scores = {"a": 1.0, "b": 2.0}
    ranks = rank_within_cohort(scores=scores, cohort=set())
    assert ranks == {"a": None, "b": None}


def test_normalizer_version_is_set():
    assert NORMALIZER_VERSION == "cross_section_v2_factor_ranks"


def test_rank_factors_within_cohort_ranks_each_factor_independently():
    factor_scores = {
        f"asset:{index}": {"social_heat": float(index), "social_propagation": float(100 - index)} for index in range(10)
    }
    factor_scores["asset:b"] = {"social_heat": 30.0, "social_propagation": None}
    factor_scores["asset:d"] = {"social_heat": 100.0, "social_propagation": 100.0}
    cohort = {f"asset:{index}" for index in range(10)}

    ranks = rank_factors_within_cohort(factor_scores=factor_scores, cohort=cohort)

    assert ranks["asset:0"]["social_heat"] == 0.1
    assert ranks["asset:9"]["social_heat"] == 1.0
    assert ranks["asset:0"]["social_propagation"] == 1.0
    assert ranks["asset:b"]["social_propagation"] is None
    assert ranks["asset:d"] == {"social_heat": None, "social_propagation": None}


def test_weighted_rank_score_renormalizes_over_available_factor_ranks():
    rank = weighted_rank_score(
        factor_ranks={"social_heat": 0.5, "social_propagation": None, "timing_risk": 1.0},
        weights={"social_heat": 0.55, "social_propagation": 0.45, "timing_risk": 0.10},
    )

    assert rank == pytest.approx(0.576923)


def test_weighted_rank_score_ignores_zero_weight_factors():
    rank = weighted_rank_score(
        factor_ranks={"social_heat": 0.5, "social_propagation": 0.5, "timing_risk": 1.0},
        weights={"social_heat": 0.45, "social_propagation": 0.40, "timing_risk": 0.0},
    )

    assert rank == 0.5


def test_weighted_rank_score_returns_none_when_no_factors_are_ranked():
    assert weighted_rank_score({"social_heat": None}, {"social_heat": 1.0}) is None
