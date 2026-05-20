from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ESCALATION_EDGE_EVENTS = frozenset({"pulse_status_changed", "recommended_decision_changed"})
MATERIAL_EVIDENCE_EDGE_EVENTS = frozenset(
    {"independent_author_bucket_changed", "trigger_evidence_changed", "timeline_evidence_changed"}
)


@dataclass(frozen=True, slots=True)
class PulseAdmissionDecision:
    action: Literal["suppress", "enqueue_agent"]
    reason: str
    edge_events: tuple[str, ...]


class PulseAdmissionPolicy:
    def classify(
        self,
        *,
        previous_state: dict[str, Any] | None,
        current_state: dict[str, Any],
        existing_job: dict[str, Any] | None,
        edge_events: list[str] | tuple[str, ...],
        pending_score_band: str | None,
        pending_score_band_count: int,
        recent_failure_count: int = 0,
    ) -> PulseAdmissionDecision:
        previous = _mapping(previous_state)
        events = tuple(str(event) for event in edge_events if str(event or "").strip())
        active_reason = _active_job_suppression_reason(existing_job)
        if active_reason is not None:
            return PulseAdmissionDecision("suppress", active_reason, events)
        if not events:
            return PulseAdmissionDecision("suppress", "unchanged", events)
        if recent_failure_count >= 3 and not _is_escalation(events):
            return PulseAdmissionDecision("suppress", "failure_circuit_open", events)
        if events == ("score_band_crossed",):
            score_band = _clean(current_state.get("score_band"))
            if score_band and pending_score_band == score_band and int(pending_score_band_count or 0) >= 1:
                return PulseAdmissionDecision("enqueue_agent", "score_band_confirmed", events)
            return PulseAdmissionDecision("suppress", "score_band_pending", events)
        if not previous:
            return PulseAdmissionDecision("enqueue_agent", "material_edge", events)
        if _is_escalation(events):
            return PulseAdmissionDecision("enqueue_agent", "escalation", events)
        if "hard_risk_added" in events:
            return PulseAdmissionDecision("enqueue_agent", "hard_risk_added", events)
        if _has_material_evidence_change(events):
            return PulseAdmissionDecision("enqueue_agent", "material_evidence_changed", events)
        return PulseAdmissionDecision("enqueue_agent", "material_edge", events)


def _active_job_suppression_reason(job: dict[str, Any] | None) -> str | None:
    if not job:
        return None
    status = _clean(job.get("status"))
    if status in {"pending", "running"}:
        return "active_job"
    if status == "failed":
        attempt_count = _int(job.get("attempt_count"))
        max_attempts = _int(job.get("max_attempts")) or 3
        if attempt_count < max_attempts:
            return "retryable_failed_job"
    return None


def _is_escalation(edge_events: tuple[str, ...]) -> bool:
    return bool(set(edge_events) & ESCALATION_EDGE_EVENTS)


def _has_material_evidence_change(edge_events: tuple[str, ...]) -> bool:
    return bool(set(edge_events) & MATERIAL_EVIDENCE_EDGE_EVENTS)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "ESCALATION_EDGE_EVENTS",
    "MATERIAL_EVIDENCE_EDGE_EVENTS",
    "PulseAdmissionDecision",
    "PulseAdmissionPolicy",
]
