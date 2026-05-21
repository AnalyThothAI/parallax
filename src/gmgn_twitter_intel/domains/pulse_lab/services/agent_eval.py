"""Deterministic evidence-first eval grader for Signal Pulse."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import (
    PULSE_DETERMINISTIC_GRADER_VERSION,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
)

_RULE_EVIDENCE_PACKET_EXISTS = "evidence_packet_exists"
_RULE_STAGE_CONTRACT = "stage_contract"
_RULE_DECISION_REFS_SUBSET_PACKET_REFS = "decision_refs_subset_packet_refs"
_RULE_RECOMMENDATION_CEILING_RESPECTED = "recommendation_ceiling_respected"
_RULE_PLAYBOOK_CONSISTENT = "playbook_consistent"
_RULE_FAILED_RUN_RECORDED = "failed_run_recorded"

_RULES = (
    _RULE_EVIDENCE_PACKET_EXISTS,
    _RULE_STAGE_CONTRACT,
    _RULE_DECISION_REFS_SUBSET_PACKET_REFS,
    _RULE_RECOMMENDATION_CEILING_RESPECTED,
    _RULE_PLAYBOOK_CONSISTENT,
)

_NON_BLOCKED_REQUIRED_STAGES = ("signal_analyst", "bear_case", "risk_portfolio_judge")
_EVIDENCE_REQUIRED_STAGES = ("evidence_pack", "evidence_completeness_gate")
_RECOMMENDATION_RANK = {
    "abstain": 0,
    "ignore": 1,
    "watchlist": 2,
    "token_watch": 2,
    "risk_rejected_high_info": 1,
    "trade_candidate": 3,
    "high_conviction": 4,
}


def build_pulse_deterministic_eval_case(
    *,
    run_id: str,
    runtime_hash: str,
    context: dict[str, Any],
    route: DecisionRoute,
    completeness: dict[str, Any],
    final_decision: FinalDecision,
    stage_audits: tuple[StageRunAudit, ...],
) -> dict[str, Any]:
    return {
        "eval_case_id": _stable_id("pulse-eval-case", run_id, PULSE_DETERMINISTIC_GRADER_VERSION),
        "source_run_id": run_id,
        "runtime_hash": runtime_hash,
        "eval_type": "deterministic",
        "route": route,
        "recommendation": final_decision.recommendation,
        "input_json": {
            "context": context,
            "completeness": completeness,
            "stage_audits": [stage.model_dump(mode="json") for stage in stage_audits],
        },
        "expected_json": {
            "final_decision": final_decision.model_dump(mode="json"),
            "stage_count": len(stage_audits),
        },
        "rubric_json": {
            "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
            "checks": list(_RULES),
        },
    }


def build_pulse_failed_eval_case(
    *,
    run_id: str,
    runtime_hash: str,
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
        "runtime_hash": runtime_hash,
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
    input_json = _mapping(case.get("input_json"))
    expected_json = _mapping(case.get("expected_json"))
    stages = _list(input_json.get("stage_audits"))
    if expected_json.get("status") == "fail":
        return _grade_failed_run_case(case, input_json=input_json, expected_json=expected_json, stages=stages)

    context = _mapping(input_json.get("context"))
    completeness = _mapping(input_json.get("completeness"))
    final = _mapping(expected_json.get("final_decision"))
    packet = _mapping(context.get("evidence_packet"))
    allowed_refs = _allowed_ref_ids(packet)
    violations: list[str] = []

    if not packet.get("evidence_packet_hash") or not allowed_refs:
        violations.append(_RULE_EVIDENCE_PACKET_EXISTS)

    hard_blocked = bool(completeness.get("hard_blocked") is True)
    stage_status_by_name = _stage_status_by_name(stages)
    for stage_name in _EVIDENCE_REQUIRED_STAGES:
        if stage_status_by_name.get(stage_name) != "ok":
            violations.append(_RULE_STAGE_CONTRACT)
            break
    if not hard_blocked:
        for stage_name in _required_non_blocked_stages(context):
            if stage_status_by_name.get(stage_name) != "ok":
                violations.append(_RULE_STAGE_CONTRACT)
                break

    final_refs = _final_refs(final)
    unknown_refs = sorted(ref_id for ref_id in final_refs if ref_id not in allowed_refs)
    if unknown_refs:
        violations.append(_RULE_DECISION_REFS_SUBSET_PACKET_REFS)
    if final.get("recommendation") != "abstain" and not _list(final.get("supporting_evidence_refs")):
        violations.append(_RULE_DECISION_REFS_SUBSET_PACKET_REFS)

    max_decision_status = str(completeness.get("max_decision_status") or "")
    if max_decision_status and _rank(str(final.get("recommendation") or "")) > _rank(max_decision_status):
        violations.append(_RULE_RECOMMENDATION_CEILING_RESPECTED)

    playbook = _mapping(final.get("playbook"))
    if final.get("recommendation") == "abstain" and (
        playbook.get("has_playbook") is not False
        or _list(playbook.get("watch_signals"))
        or _list(playbook.get("exit_triggers"))
    ):
        violations.append(_RULE_PLAYBOOK_CONSISTENT)

    violations = list(dict.fromkeys(violations))
    return _result(
        case,
        status="fail" if violations else "pass",
        violations=violations,
        stage_names=list(stage_status_by_name.keys()),
        unknown_refs=unknown_refs,
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


def _stage_status_by_name(stages: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for stage in stages:
        payload = _mapping(stage)
        result[str(payload.get("stage") or "")] = str(payload.get("status") or "")
    return result


def _required_non_blocked_stages(context: dict[str, Any]) -> tuple[str, ...]:
    cost_guard = _mapping(context.get("cost_guard"))
    decision = _mapping(cost_guard.get("decision"))
    if str(decision.get("action") or "") == "reuse_terminal_run":
        return tuple()
    stage_plan = _mapping(cost_guard.get("stage_plan"))
    if not stage_plan:
        return _NON_BLOCKED_REQUIRED_STAGES
    stages: list[str] = []
    if bool(stage_plan.get("run_signal_analyst")):
        stages.append("signal_analyst")
    if bool(stage_plan.get("run_bear_case")):
        stages.append("bear_case")
    if bool(stage_plan.get("run_risk_portfolio_judge")):
        stages.append("risk_portfolio_judge")
    return tuple(stages)


def _allowed_ref_ids(packet: dict[str, Any]) -> set[str]:
    refs = _list(packet.get("allowed_evidence_refs"))
    result: set[str] = set()
    for ref in refs:
        ref_id = str(_mapping(ref).get("ref_id") or "").strip()
        if ref_id:
            result.add(ref_id)
    return result


def _final_refs(final: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in ("supporting_evidence_refs", "risk_evidence_refs", "data_gap_refs"):
        for value in _list(final.get(key)):
            ref_id = str(value or "").strip()
            if not ref_id:
                continue
            if key == "data_gap_refs" and ref_id.startswith("missing:"):
                continue
            result.add(ref_id)
    return result


def _rank(value: str) -> int:
    return _RECOMMENDATION_RANK.get(value, -1)


def _result(
    case: dict[str, Any],
    *,
    status: str,
    violations: list[str],
    stage_names: list[str],
    unknown_refs: list[str] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "violations": violations,
        "checked_stage_names": stage_names,
    }
    if unknown_refs is not None:
        details["unknown_refs"] = unknown_refs
    return {
        "eval_result_id": _stable_id(
            "pulse-eval-result",
            str(case.get("eval_case_id") or ""),
            str(case.get("runtime_hash") or ""),
            PULSE_DETERMINISTIC_GRADER_VERSION,
        ),
        "eval_case_id": str(case.get("eval_case_id") or ""),
        "runtime_hash": str(case.get("runtime_hash") or ""),
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
