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
        recent_failure_count: int,
        failure_circuit_per_hour: int,
        timeline_debounce_seconds: int,
        last_processed_at_ms: int | None = None,
        now_ms: int | None = None,
    ) -> PulseAdmissionDecision:
        failure_threshold = _required_positive_int(
            failure_circuit_per_hour,
            "pulse_failure_circuit_per_hour_required",
        )
        timeline_debounce = _required_nonnegative_int(
            timeline_debounce_seconds,
            "pulse_timeline_debounce_seconds_required",
        )
        previous = _mapping(previous_state)
        events = tuple(str(event) for event in edge_events if str(event or "").strip())
        active_reason = _active_job_suppression_reason(existing_job)
        if active_reason is not None:
            return PulseAdmissionDecision("suppress", active_reason, events)
        if not events:
            return PulseAdmissionDecision("suppress", "unchanged", events)
        if recent_failure_count >= failure_threshold and not _is_escalation(events):
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
        if _is_debounced_timeline_only(
            events,
            last_processed_at_ms=last_processed_at_ms,
            now_ms=now_ms,
            timeline_debounce_seconds=timeline_debounce,
        ):
            return PulseAdmissionDecision("suppress", "timeline_debounce", events)
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
        attempt_count, max_attempts = _failed_job_attempt_contract(job)
        if attempt_count < max_attempts:
            return "retryable_failed_job"
    return None


def _failed_job_attempt_contract(job: dict[str, Any]) -> tuple[int, int]:
    try:
        attempt_count = int(job["attempt_count"])
        max_attempts = int(job["max_attempts"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("pulse_existing_failed_job_attempt_contract_required") from exc
    if attempt_count < 0 or max_attempts < 1:
        raise RuntimeError("pulse_existing_failed_job_attempt_contract_required")
    return attempt_count, max_attempts


def _is_escalation(edge_events: tuple[str, ...]) -> bool:
    return bool(set(edge_events) & ESCALATION_EDGE_EVENTS)


def _has_material_evidence_change(edge_events: tuple[str, ...]) -> bool:
    return bool(set(edge_events) & MATERIAL_EVIDENCE_EDGE_EVENTS)


def _is_debounced_timeline_only(
    edge_events: tuple[str, ...],
    *,
    last_processed_at_ms: int | None,
    now_ms: int | None,
    timeline_debounce_seconds: int,
) -> bool:
    if set(edge_events) != {"timeline_evidence_changed"}:
        return False
    if last_processed_at_ms is None or now_ms is None:
        return False
    debounce_seconds = _required_nonnegative_int(
        timeline_debounce_seconds,
        "pulse_timeline_debounce_seconds_required",
    )
    return int(now_ms) - int(last_processed_at_ms) < debounce_seconds * 1000


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error_code)
    return int(value)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = [
    "ESCALATION_EDGE_EVENTS",
    "MATERIAL_EVIDENCE_EDGE_EVENTS",
    "PulseAdmissionDecision",
    "PulseAdmissionPolicy",
]
