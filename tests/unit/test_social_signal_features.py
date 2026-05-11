from __future__ import annotations

import math

import pytest

from gmgn_twitter_intel.domains.token_intel.scoring.social_signal_features import (
    author_entropy,
    public_followup_author_count,
    source_weighted_effective_authors,
    time_to_nth_independent_author_ms,
)


def test_source_weighted_effective_authors_penalizes_repeated_single_author_spam() -> None:
    repeated_single_author = [
        {"author_handle": "alice", "received_at_ms": 1_000},
        {"author_handle": "alice", "received_at_ms": 1_010},
        {"author_handle": "alice", "received_at_ms": 1_020},
    ]
    independent_authors = [
        {"author_handle": "alice", "received_at_ms": 1_000},
        {"author_handle": "bob", "received_at_ms": 1_010},
        {"author_handle": "carol", "received_at_ms": 1_020},
    ]

    assert source_weighted_effective_authors(repeated_single_author) == pytest.approx(1.0)
    assert source_weighted_effective_authors(independent_authors) > source_weighted_effective_authors(
        repeated_single_author
    )


def test_source_weighted_effective_authors_uses_source_weight_by_author() -> None:
    balanced_authors = [
        {"author_handle": "alice", "_source_weight": 1.0},
        {"author_handle": "bob", "_source_weight": 1.0},
        {"author_handle": "carol", "_source_weight": 1.0},
    ]
    skewed_authors = [
        {"author_handle": "alice", "_source_weight": 1.0},
        {"author_handle": "bob", "_source_weight": 0.05},
        {"author_handle": "carol", "_source_weight": 0.05},
    ]
    repeated_single_author = [
        {"author_handle": "alice", "_source_weight": 1.0},
        {"author_handle": "alice", "_source_weight": 0.05},
        {"author_handle": "alice", "_source_weight": 0.05},
    ]

    balanced_score = source_weighted_effective_authors(balanced_authors)
    skewed_score = source_weighted_effective_authors(skewed_authors)

    assert balanced_score == pytest.approx(3.0)
    assert skewed_score < balanced_score
    assert skewed_score < 1.25
    assert source_weighted_effective_authors(repeated_single_author) == pytest.approx(1.0)


def test_time_to_nth_independent_author_ms_returns_elapsed_from_first_event() -> None:
    rows = [
        {"author_handle": "alice", "received_at_ms": 1_000},
        {"author_handle": "alice", "received_at_ms": 1_250},
        {"author_handle": "bob", "received_at_ms": 1_700},
        {"author_handle": "carol", "received_at_ms": 2_100},
    ]

    assert time_to_nth_independent_author_ms(rows, 2) == 700
    assert time_to_nth_independent_author_ms(rows, 3) == 1_100
    assert time_to_nth_independent_author_ms(rows, 4) is None


def test_time_to_nth_independent_author_ms_starts_at_first_valid_distinct_author() -> None:
    rows = [
        {"received_at_ms": 500},
        {"author_handle": "", "received_at_ms": 700},
        {"author_handle": "alice", "received_at_ms": 1_000},
        {"author_handle": "bob", "received_at_ms": 1_400},
    ]

    assert time_to_nth_independent_author_ms(rows, 2) == 400


def test_public_followup_author_count_counts_non_watched_authors_after_watched_seed() -> None:
    rows = [
        {"author_handle": "seed", "received_at_ms": 1_000, "is_watched": True},
        {"author_handle": "bob", "received_at_ms": 1_010, "is_watched": False},
        {"author_handle": "bob", "received_at_ms": 1_020, "is_watched": False},
        {"author_handle": "carol", "received_at_ms": 1_030, "is_watched": False},
        {"author_handle": "watched-followup", "received_at_ms": 1_040, "is_watched": True},
    ]

    assert public_followup_author_count(rows) == 2


def test_public_followup_author_count_excludes_watched_seed_authors_from_public_followup() -> None:
    rows = [
        {"author_handle": "alice", "received_at_ms": 1_000, "is_watched": True},
        {"author_handle": "alice", "received_at_ms": 1_010, "is_watched": False},
        {"author_handle": "bob", "received_at_ms": 1_020, "is_watched": False},
        {"author_handle": "carol", "received_at_ms": 1_030, "is_watched": False},
    ]

    assert public_followup_author_count(rows) == 2


def test_public_followup_author_count_returns_zero_without_watched_seed() -> None:
    rows = [
        {"author_handle": "alice", "received_at_ms": 1_000, "is_watched": False},
        {"author_handle": "bob", "received_at_ms": 1_010, "is_watched": False},
    ]

    assert public_followup_author_count(rows) == 0


def test_author_entropy_is_high_for_balanced_authors_and_low_for_dominant_author() -> None:
    balanced = [
        {"author_handle": "alice"},
        {"author_handle": "bob"},
        {"author_handle": "carol"},
        {"author_handle": "dina"},
    ]
    dominated = [
        {"author_handle": "alice"},
        {"author_handle": "alice"},
        {"author_handle": "alice"},
        {"author_handle": "alice"},
    ]

    assert author_entropy(balanced) > 0.95
    assert author_entropy(dominated) == pytest.approx(0.0)


def test_author_entropy_returns_raw_shannon_entropy() -> None:
    balanced = [
        {"author_handle": "alice"},
        {"author_handle": "bob"},
        {"author_handle": "carol"},
    ]

    assert author_entropy(balanced) == pytest.approx(math.log(3))
    assert author_entropy(balanced) > 1.0
