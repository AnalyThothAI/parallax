from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NarrativeAdmissionDecision:
    target_type: str
    target_id: str
    window: str
    scope: str
    schema_version: str
    status: str
    reason: str
    priority: int
    last_radar_rank: int | None = None
    last_rank_score: float | None = None
    source_event_ids: tuple[str, ...] = ()
    source_max_received_at_ms: int | None = None
    projection_computed_at_ms: int | None = None


class NarrativeAdmissionService:
    def __init__(
        self,
        *,
        hot_rank_limit: int,
        min_rank_score: int,
    ) -> None:
        self.hot_rank_limit = _required_positive_int(
            hot_rank_limit,
            error_code="narrative_admission_hot_rank_limit_required",
        )
        self.min_rank_score = _required_nonnegative_int(
            min_rank_score,
            error_code="narrative_admission_min_rank_score_required",
        )

    def reconcile_from_radar_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        existing_admissions: list[dict[str, Any]],
        window: str,
        scope: str,
        schema_version: str,
        now_ms: int,
    ) -> list[NarrativeAdmissionDecision]:
        decisions: dict[tuple[str, str], NarrativeAdmissionDecision] = {}
        for row in rows:
            target_type = _clean(row.get("target_type"))
            target_id = _clean(row.get("target_id"))
            if not target_type or not target_id:
                continue
            rank = _int(row.get("rank"))
            score = _float(row.get("rank_score"))
            reason = _admission_reason(
                rank=rank,
                score=score,
                hot_rank_limit=self.hot_rank_limit,
                min_score=self.min_rank_score,
            )
            if reason is None:
                continue
            priority = _priority(rank=rank, score=score)
            source_event_ids = tuple(str(event_id) for event_id in row.get("source_event_ids") or [])
            source_max_received_at_ms = _int(row.get("source_max_received_at_ms"))
            if source_max_received_at_ms is None:
                source_max_received_at_ms = _int(row.get("computed_at_ms"))
            decisions[(target_type, target_id)] = NarrativeAdmissionDecision(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
                status="admitted",
                reason=reason,
                priority=priority,
                last_radar_rank=rank,
                last_rank_score=score,
                source_event_ids=source_event_ids,
                source_max_received_at_ms=source_max_received_at_ms,
                projection_computed_at_ms=_int(row.get("computed_at_ms")),
            )

        return sorted(decisions.values(), key=lambda item: (-item.priority, item.target_type, item.target_id))


def _admission_reason(*, rank: int | None, score: float | None, hot_rank_limit: int, min_score: int) -> str | None:
    if rank is not None and rank <= hot_rank_limit:
        return "hot_rank"
    if score is not None and score >= min_score:
        return "rank_score"
    return None


def _priority(*, rank: int | None, score: float | None) -> int:
    rank_component = max(0, 10_000 - int(rank or 10_000))
    score_component = int(score or 0) * 100
    return rank_component + score_component


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_nonnegative_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value < 0:
        raise ValueError(error_code)
    return int(value)
