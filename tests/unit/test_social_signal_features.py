from __future__ import annotations

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


def test_public_followup_author_count_counts_non_watched_authors_after_watched_seed() -> None:
    rows = [
        {"author_handle": "seed", "received_at_ms": 1_000, "is_watched": True},
        {"author_handle": "bob", "received_at_ms": 1_010, "is_watched": False},
        {"author_handle": "bob", "received_at_ms": 1_020, "is_watched": False},
        {"author_handle": "carol", "received_at_ms": 1_030, "is_watched": False},
        {"author_handle": "watched-followup", "received_at_ms": 1_040, "is_watched": True},
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
