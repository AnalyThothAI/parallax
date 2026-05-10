from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.scoring.cross_section_normalizer import (
    NORMALIZER_VERSION,
    rank_within_cohort,
)


def test_rank_returns_percentiles_for_cohort_members():
    scores = {"a": 10.0, "b": 50.0, "c": 30.0, "d": 90.0}
    cohort = {"a", "b", "c", "d"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == 0.25
    assert ranks["c"] == 0.50
    assert ranks["b"] == 0.75
    assert ranks["d"] == 1.00


def test_rank_returns_none_for_non_cohort_members():
    scores = {"a": 10.0, "b": 50.0, "btc": 100.0}
    cohort = {"a", "b"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] is not None
    assert ranks["b"] is not None
    assert ranks["btc"] is None


def test_rank_handles_ties_with_average_method():
    scores = {"a": 10.0, "b": 10.0, "c": 30.0}
    cohort = {"a", "b", "c"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == ranks["b"]
    assert ranks["a"] == 0.5
    assert ranks["c"] == 1.0


def test_rank_with_single_cohort_member_returns_one():
    scores = {"only_one": 42.0, "outsider": 0.0}
    cohort = {"only_one"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["only_one"] == 1.0
    assert ranks["outsider"] is None


def test_rank_skips_none_scores_inside_cohort():
    scores = {"a": 10.0, "b": None, "c": 30.0}
    cohort = {"a", "b", "c"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["a"] == 0.5
    assert ranks["b"] is None
    assert ranks["c"] == 1.0


def test_empty_cohort_returns_none_for_all():
    scores = {"a": 1.0, "b": 2.0}
    ranks = rank_within_cohort(scores=scores, cohort=set())
    assert ranks == {"a": None, "b": None}


def test_normalizer_version_is_set():
    assert NORMALIZER_VERSION == "cross_section_v1"
