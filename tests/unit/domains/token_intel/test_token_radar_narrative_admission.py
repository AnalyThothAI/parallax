from __future__ import annotations

import pytest

from parallax.domains.token_intel.read_models.token_radar_narrative_admission import (
    narrative_admission_from_current_row,
)


def test_hot_rank_is_admitted_from_current_radar_row() -> None:
    admission = narrative_admission_from_current_row(
        _current_row(rank=50, rank_score=1.0),
        window="1h",
    )

    assert admission == {
        "status": "admitted",
        "reason": "hot_rank",
        "is_current": True,
        "computed_at_ms": 1_778_000_000_000,
        "currentness": {"display_status": "current", "reason": "hot_rank"},
        "coverage": {"source_mentions": 3, "independent_authors": 2},
        "data_gaps": [],
    }


def test_rank_score_admits_row_outside_hot_rank_frontier() -> None:
    admission = narrative_admission_from_current_row(
        _current_row(rank=51, rank_score=30.0),
        window="1h",
    )

    assert admission["status"] == "admitted"
    assert admission["reason"] == "rank_score"
    assert admission["currentness"] == {"display_status": "current", "reason": "rank_score"}


def test_row_below_both_thresholds_is_suppressed_out_of_frontier() -> None:
    admission = narrative_admission_from_current_row(
        _current_row(rank=51, rank_score=29.99),
        window="1h",
    )

    assert admission["status"] == "suppressed"
    assert admission["is_current"] is False
    assert admission["currentness"] == {
        "display_status": "out_of_frontier",
        "reason": "out_of_frontier",
    }
    assert admission["coverage"] == {"source_mentions": 3, "independent_authors": 2}
    assert admission["data_gaps"] == [{"reason": "out_of_frontier"}]


def test_missing_current_row_is_explicitly_not_ready() -> None:
    admission = narrative_admission_from_current_row(None, window="1h")

    assert admission == {
        "status": "missing",
        "reason": "no_current_admission",
        "is_current": False,
        "computed_at_ms": None,
        "currentness": {"display_status": "not_ready", "reason": "no_current_admission"},
        "coverage": {"source_mentions": 0, "independent_authors": 0},
        "data_gaps": [{"reason": "no_current_admission"}],
    }


def test_non_1h_window_is_explicitly_unsupported_without_reading_row_shape() -> None:
    admission = narrative_admission_from_current_row({"malformed": True}, window="24h")

    assert admission["status"] == "missing"
    assert admission["currentness"] == {
        "display_status": "unsupported_window",
        "reason": "narrative_not_supported_for_window",
    }
    assert admission["coverage"] == {"source_mentions": 0, "independent_authors": 0}


def test_malformed_present_current_row_fails_instead_of_becoming_missing() -> None:
    row = _current_row(rank=1, rank_score=55.0)
    row["factor_snapshot_json"]["families"]["social_propagation"]["facts"].pop("independent_authors")

    with pytest.raises(
        ValueError,
        match=(
            r"token_radar_narrative_admission_current_row_invalid:"
            r"factor_snapshot_json\.families\.social_propagation\.facts\.independent_authors"
        ),
    ):
        narrative_admission_from_current_row(row, window="1h")


def _current_row(*, rank: int, rank_score: float) -> dict:
    return {
        "rank": rank,
        "rank_score": rank_score,
        "computed_at_ms": 1_778_000_000_000,
        "source_event_ids_json": ["event-1", "event-2", "event-3"],
        "factor_snapshot_json": {
            "families": {
                "social_propagation": {
                    "facts": {"independent_authors": 2},
                }
            },
            "provenance": {"source_event_ids": ["wrong-source"]},
        },
    }
