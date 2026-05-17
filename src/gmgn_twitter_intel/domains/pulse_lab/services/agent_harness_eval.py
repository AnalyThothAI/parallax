"""Deterministic eval grader v2 for the two-stage Pulse Agent Desk.

v2 hard cut (plan 2026-05-16 Task 10):

* v1 grader rules (final_route_mismatch / critic_confidence_ceiling /
  hard_blocked_run_entered_llm_stages / etc.) are DELETED. The v1 case
  schema referenced ``analyst``/``critic``/``judge`` stages and
  ``critic.response_json.confidence_ceiling``; those keys no longer exist
  in v2 cases.
* New rules (R1..R5) target the v2 schema (Investigator + DecisionMaker
  stages, narrative + bull/bear/playbook fields). See Task 10 spec §10.1.
* Defensive dispatch (reviewer G.1): if a case is recognised as a v1
  shape (missing v2 narrative/bull/bear/playbook keys *or* stage_audits
  containing analyst/critic/judge), the grader returns
  ``status='legacy_skipped'`` with no violations rather than panicking
  with a KeyError. v1 cases coexist via the bumped ``harness_hash``
  (manifest stages changed in Task 6), so they never reach v2
  expectations and ``legacy_skipped`` documents intent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import (
    PULSE_DETERMINISTIC_GRADER_VERSION,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
)

# v2 rule identifiers (kept stable for eval_results.details_json.violations).
_RULE_STAGES_PRESENT = "stages_present"
_RULE_TOOL_CALLS_PRESENT = "tool_calls_present"
_RULE_EVIDENCE_SUBSET = "evidence_subset"
_RULE_HIGH_CONVICTION_CONSTRAINT = "high_conviction_constraint"
_RULE_PLAYBOOK_CONSISTENT = "playbook_consistent"
_RULE_FAILED_RUN_RECORDED = "failed_run_recorded"

_V2_RULES = (
    _RULE_STAGES_PRESENT,
    _RULE_TOOL_CALLS_PRESENT,
    _RULE_EVIDENCE_SUBSET,
    _RULE_HIGH_CONVICTION_CONSTRAINT,
    _RULE_PLAYBOOK_CONSISTENT,
)

# Stage names from the v1 (analyst/critic/judge) era. The presence of any
# of these in stage_audits OR the absence of v2-only keys on the final
# decision triggers the legacy_skipped dispatch.
_LEGACY_STAGE_NAMES = frozenset({"analyst", "critic", "judge"})
_V2_FINAL_KEYS = ("narrative_archetype", "narrative_thesis_zh", "bull_view", "bear_view", "playbook")


def build_pulse_deterministic_eval_case(
    *,
    run_id: str,
    harness_hash: str,
    context: dict[str, Any],
    route: DecisionRoute,
    completeness: dict[str, Any],
    final_decision: FinalDecision,
    stage_audits: tuple[StageRunAudit, ...],
) -> dict[str, Any]:
    final_json = final_decision.model_dump(mode="json")
    stage_json = [stage.model_dump(mode="json") for stage in stage_audits]
    return {
        "eval_case_id": _stable_id("pulse-eval-case", run_id, PULSE_DETERMINISTIC_GRADER_VERSION),
        "source_run_id": run_id,
        "harness_hash": harness_hash,
        "eval_type": "deterministic",
        "route": route,
        "recommendation": final_decision.recommendation,
        "input_json": {
            "context": context,
            "completeness": completeness,
            "stage_audits": stage_json,
        },
        "expected_json": {
            "final_decision": final_json,
            "stage_count": len(stage_audits),
        },
        "rubric_json": {
            "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
            "checks": list(_V2_RULES),
        },
    }


def build_pulse_failed_eval_case(
    *,
    run_id: str,
    harness_hash: str,
    context: dict[str, Any],
    route: DecisionRoute,
    completeness: dict[str, Any],
    stage_audits: tuple[StageRunAudit, ...],
    failure_reason: str,
) -> dict[str, Any]:
    return {
        "eval_case_id": _stable_id(
            "pulse-failed-eval-case",
            run_id,
            failure_reason,
            PULSE_DETERMINISTIC_GRADER_VERSION,
        ),
        "source_run_id": run_id,
        "harness_hash": harness_hash,
        "eval_type": "deterministic",
        "route": route,
        "recommendation": "abstain",
        "input_json": {
            "context": context,
            "completeness": completeness,
            "stage_audits": [stage.model_dump(mode="json") for stage in stage_audits],
            "failure_reason": failure_reason,
        },
        "expected_json": {"status": "fail", "failure_reason": failure_reason},
        "rubric_json": {
            "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
            "checks": [_RULE_FAILED_RUN_RECORDED],
        },
    }


def grade_pulse_deterministic_eval_case(case: dict[str, Any]) -> dict[str, Any]:
    """Grade a v2 eval case against rules R1..R5.

    v1-shaped cases are detected up-front and returned as
    ``status='legacy_skipped'`` (reviewer G.1) so the grader can run
    safely against historical eval_cases rows without raising.
    """

    input_json = _mapping(case.get("input_json"))
    expected_json = _mapping(case.get("expected_json"))
    completeness = _mapping(input_json.get("completeness"))
    final = _mapping(expected_json.get("final_decision"))
    stages = _list(input_json.get("stage_audits"))

    if expected_json.get("status") == "fail":
        return _grade_failed_run_case(case, input_json=input_json, expected_json=expected_json, stages=stages)

    if _is_legacy_case(final=final, stages=stages):
        return _result(
            case,
            status="legacy_skipped",
            violations=[],
            stage_names=[str(_mapping(stage).get("stage") or "") for stage in stages],
            notes="v1 schema not graded by v2 grader",
        )

    violations: list[str] = []
    hard_blocked = bool(completeness.get("hard_blocked") is True)

    # R1: stages_present — investigator + decision_maker both ok unless hard_blocked.
    stage_status_by_name: dict[str, str] = {}
    for stage in stages:
        payload = _mapping(stage)
        stage_status_by_name[str(payload.get("stage") or "")] = str(payload.get("status") or "")
    if not hard_blocked and (
        stage_status_by_name.get("investigator") != "ok"
        or stage_status_by_name.get("decision_maker") != "ok"
    ):
        violations.append(_RULE_STAGES_PRESENT)

    # R2: tool_calls_present — investigator step has >= 1 tool_calls unless hard_blocked.
    if not hard_blocked:
        investigator = _find_stage(stages, "investigator")
        tool_calls = _list(_mapping(_mapping(investigator).get("input_json")).get("tool_calls"))
        if not tool_calls:
            violations.append(_RULE_TOOL_CALLS_PRESENT)

    # R3: evidence_subset — final.evidence_event_ids ⊂ union of investigator + context sources.
    evidence_event_ids = {str(value) for value in _list(final.get("evidence_event_ids")) if value}
    if evidence_event_ids:
        allowed = _collect_allowed_evidence_ids(stages, _mapping(input_json.get("context")))
        if not evidence_event_ids.issubset(allowed):
            violations.append(_RULE_EVIDENCE_SUBSET)

    # R4: high_conviction_constraint — bull/bear strength >= moderate AND evidence >= 3.
    if final.get("recommendation") == "high_conviction":
        bull_strength = str(_mapping(final.get("bull_view")).get("strength") or "")
        bear_strength = str(_mapping(final.get("bear_view")).get("strength") or "")
        if (
            bull_strength not in {"moderate", "strong"}
            or bear_strength not in {"moderate", "strong"}
            or len(evidence_event_ids) < 3
        ):
            violations.append(_RULE_HIGH_CONVICTION_CONSTRAINT)

    # R5: playbook_consistent — abstain → has_playbook=false AND watch_signals/exit_triggers empty.
    if final.get("recommendation") == "abstain":
        playbook = _mapping(final.get("playbook"))
        if playbook.get("has_playbook") is not False or (
            _list(playbook.get("watch_signals")) or _list(playbook.get("exit_triggers"))
        ):
            violations.append(_RULE_PLAYBOOK_CONSISTENT)

    # De-duplicate while preserving first-seen order (R4/R5 can add the same code twice).
    violations = list(dict.fromkeys(violations))
    status = "fail" if violations else "pass"
    return _result(
        case,
        status=status,
        violations=violations,
        stage_names=list(stage_status_by_name.keys()),
    )


def _grade_failed_run_case(
    case: dict[str, Any],
    *,
    input_json: dict[str, Any],
    expected_json: dict[str, Any],
    stages: list[Any],
) -> dict[str, Any]:
    expected_reason = str(expected_json.get("failure_reason") or "")
    observed_reason = str(input_json.get("failure_reason") or "")
    violations = []
    if not expected_reason or observed_reason != expected_reason:
        violations.append(_RULE_FAILED_RUN_RECORDED)
    return _result(
        case,
        status="fail" if violations else "pass",
        violations=violations,
        stage_names=[str(_mapping(stage).get("stage") or "") for stage in stages],
    )


def _is_legacy_case(*, final: dict[str, Any], stages: list[Any]) -> bool:
    """True if the case predates the v2 schema and must be skipped (G.1)."""
    # Stage_audits referencing analyst/critic/judge are unambiguous v1.
    for stage in stages:
        payload = _mapping(stage)
        if str(payload.get("stage") or "") in _LEGACY_STAGE_NAMES:
            return True
    # Missing every v2-only final-decision key indicates pre-Task-3 case shape.
    return not any(key in final for key in _V2_FINAL_KEYS)


def _find_stage(stages: list[Any], stage_name: str) -> Any | None:
    for stage in stages:
        payload = _mapping(stage)
        if str(payload.get("stage") or "") == stage_name:
            return payload
    return None


def _collect_allowed_evidence_ids(stages: list[Any], context: dict[str, Any]) -> set[str]:
    """Union of investigator-reported supporting event ids + context-provided ids.

    Defensive: any of the source lists may be missing or None in older
    cases; treat such absences as empty contributions instead of raising.
    """

    allowed: set[str] = set()
    investigator = _find_stage(stages, "investigator")
    response = _mapping(_mapping(investigator).get("response_json"))
    for key in ("bull_observation", "bear_observation"):
        observation = _mapping(response.get(key))
        for value in _list(observation.get("supporting_event_ids")):
            if value:
                allowed.add(str(value))
    for key in ("evidence_event_ids", "source_event_ids"):
        for value in _list(context.get(key)):
            if value:
                allowed.add(str(value))
    return allowed


def _result(
    case: dict[str, Any],
    *,
    status: str,
    violations: list[str],
    stage_names: list[str],
    notes: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "violations": violations,
        "checked_stage_names": stage_names,
    }
    if notes is not None:
        details["notes"] = notes
    return {
        "eval_result_id": _stable_id(
            "pulse-eval-result",
            str(case.get("eval_case_id") or ""),
            str(case.get("harness_hash") or ""),
            PULSE_DETERMINISTIC_GRADER_VERSION,
        ),
        "eval_case_id": str(case.get("eval_case_id") or ""),
        "harness_hash": str(case.get("harness_hash") or ""),
        "status": status,
        "score": 1.0 if status == "pass" else 0.0,
        "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
        "details_json": details,
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_id(*parts: str) -> str:
    payload = json.dumps([str(part) for part in parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "build_pulse_deterministic_eval_case",
    "build_pulse_failed_eval_case",
    "grade_pulse_deterministic_eval_case",
]
