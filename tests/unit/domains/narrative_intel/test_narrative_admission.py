import pytest

from parallax.domains.narrative_intel.services.narrative_admission import (
    NarrativeAdmissionService,
)


def row(target_id: str | None, *, rank: int, score: int, computed_at_ms: int = 10_000):
    return {
        "target_type": "chain_token" if target_id else None,
        "target_id": target_id,
        "rank": rank,
        "rank_score": score,
        "computed_at_ms": computed_at_ms,
        "source_max_received_at_ms": computed_at_ms - 1_000,
        "source_event_ids": [f"event-{target_id}"] if target_id else [],
    }


def test_admission_selects_current_frontier_only():
    service = NarrativeAdmissionService(hot_rank_limit=2, min_rank_score=50)
    decisions = service.reconcile_from_radar_rows(
        [
            row("hot-1", rank=1, score=10),
            row("hot-2", rank=2, score=10),
            row("high-score", rank=8, score=72),
            row("cold", rank=9, score=12),
            row(None, rank=1, score=99),
        ],
        existing_admissions=[
            {"target_type": "chain_token", "target_id": "carry", "last_seen_at_ms": 8_000, "status": "admitted"},
            {"target_type": "chain_token", "target_id": "expired", "last_seen_at_ms": 1_000, "status": "admitted"},
        ],
        window="24h",
        scope="matched",
        schema_version="narrative_intel_v1",
        now_ms=10_000,
    )

    admitted_ids = {decision.target_id for decision in decisions if decision.status == "admitted"}

    assert admitted_ids == {"hot-1", "hot-2", "high-score"}
    assert {decision.status for decision in decisions} == {"admitted"}


def test_raw_rows_without_targets_do_not_create_admissions():
    service = NarrativeAdmissionService(hot_rank_limit=10, min_rank_score=0)
    decisions = service.reconcile_from_radar_rows(
        [row(None, rank=1, score=99)],
        existing_admissions=[],
        window="24h",
        scope="matched",
        schema_version="narrative_intel_v1",
        now_ms=10_000,
    )

    assert decisions == []


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        ({"hot_rank_limit": 0, "min_rank_score": 30}, "narrative_admission_hot_rank_limit_required"),
        ({"hot_rank_limit": True, "min_rank_score": 30}, "narrative_admission_hot_rank_limit_required"),
        ({"hot_rank_limit": "10", "min_rank_score": 30}, "narrative_admission_hot_rank_limit_required"),
        ({"hot_rank_limit": 10, "min_rank_score": -1}, "narrative_admission_min_rank_score_required"),
        ({"hot_rank_limit": 10, "min_rank_score": True}, "narrative_admission_min_rank_score_required"),
        ({"hot_rank_limit": 10, "min_rank_score": "30"}, "narrative_admission_min_rank_score_required"),
    ],
)
def test_admission_service_requires_formal_thresholds_without_runtime_repairs(kwargs, error_code):
    with pytest.raises(ValueError, match=error_code):
        NarrativeAdmissionService(**kwargs)


@pytest.mark.parametrize("watermark", [None, 0, -1, True, "9000"])
def test_admission_rejects_missing_or_malformed_source_watermark(watermark):
    service = NarrativeAdmissionService(hot_rank_limit=10, min_rank_score=0)
    candidate = row("bad-watermark", rank=1, score=99, computed_at_ms=10_000)
    if watermark is None:
        candidate.pop("source_max_received_at_ms")
    else:
        candidate["source_max_received_at_ms"] = watermark

    with pytest.raises(ValueError, match="narrative_admission_source_watermark_required"):
        service.reconcile_from_radar_rows(
            [candidate],
            existing_admissions=[],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
            now_ms=10_000,
        )
