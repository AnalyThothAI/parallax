from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import PULSE_DETERMINISTIC_GRADER_VERSION
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
    contains_trading_execution_instruction,
)


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
            "checks": [
                "final_route_matches_runtime_route",
                "critic_confidence_ceiling_not_exceeded",
                "non_abstain_has_evidence_or_residual_risk",
                "hard_blocked_runs_skip_llm_asset_stages",
                "source_seed_stays_research_only",
                "trading_execution_language_absent",
            ],
        },
    }


def grade_pulse_deterministic_eval_case(case: dict[str, Any]) -> dict[str, Any]:
    input_json = _mapping(case.get("input_json"))
    expected_json = _mapping(case.get("expected_json"))
    context = _mapping(input_json.get("context"))
    completeness = _mapping(input_json.get("completeness"))
    final = _mapping(expected_json.get("final_decision"))
    stages = _list(input_json.get("stage_audits"))
    violations: list[str] = []

    route = str(case.get("route") or "")
    if final.get("route") != route:
        violations.append("final_route_mismatch")
    if final.get("recommendation") != case.get("recommendation"):
        violations.append("final_recommendation_mismatch")

    stage_names = [str(_mapping(stage).get("stage") or "") for stage in stages]
    if completeness.get("hard_blocked") is True:
        if stage_names != ["research_only_gate"]:
            violations.append("hard_blocked_run_entered_llm_stages")
        if final.get("recommendation") != "abstain":
            violations.append("hard_blocked_run_not_abstain")

    if str(context.get("candidate_type") or "") == "source_seed" and final.get("route") != "research_only":
        violations.append("source_seed_asset_route")

    if final.get("recommendation") != "abstain":
        evidence_ids = _list(final.get("evidence_event_ids"))
        residual_risks = _list(final.get("residual_risks"))
        if not evidence_ids and not residual_risks:
            violations.append("non_abstain_missing_evidence_or_residual_risk")

    ceiling = _critic_confidence_ceiling(stages)
    confidence = _float(final.get("confidence"))
    if ceiling is not None and confidence is not None and confidence > ceiling + 1e-9:
        violations.append("critic_confidence_ceiling_exceeded")

    if _contains_execution_language(final) or any(
        _contains_execution_language(_mapping(stage).get("response_json")) for stage in stages
    ):
        violations.append("trading_execution_language_present")

    if any(str(_mapping(stage).get("status") or "") in {"failed", "timeout"} for stage in stages):
        violations.append("stage_failed_or_timed_out")

    status = "fail" if violations else "pass"
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
        "score": 0.0 if violations else 1.0,
        "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
        "details_json": {
            "violations": violations,
            "checked_stage_names": stage_names,
        },
    }


def _critic_confidence_ceiling(stages: list[Any]) -> float | None:
    for stage in stages:
        payload = _mapping(stage)
        if payload.get("stage") != "critic":
            continue
        response = _mapping(payload.get("response_json"))
        return _float(response.get("confidence_ceiling"))
    return None


def _contains_execution_language(value: Any) -> bool:
    if isinstance(value, str):
        return contains_trading_execution_instruction(value)
    if isinstance(value, dict):
        return any(_contains_execution_language(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_execution_language(item) for item in value)
    return False


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_id(*parts: str) -> str:
    payload = json.dumps([str(part) for part in parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "build_pulse_deterministic_eval_case",
    "grade_pulse_deterministic_eval_case",
]
