from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import (
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
    PULSE_GATE_VERSION,
)

PULSE_AGENT_HARNESS_VERSION = "pulse-decision-harness-v1"
PULSE_AGENT_STRATEGY = "signal_pulse_decision"
PULSE_DETERMINISTIC_GRADER_VERSION = "pulse-deterministic-harness-v2"
PULSE_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"
PULSE_FAILURE_TAXONOMY_CODES = (
    "unknown_evidence_id",
    "schema_validation_failed",
    "tool_budget_exceeded",
    "timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "stale_running_timeout",
    "unexpected_exception",
)

_DEFAULT_STAGE_NAMES = ("investigator", "decision_maker")
_DEFAULT_MAX_TURNS_PER_STAGE = {"investigator": 5, "decision_maker": 3}
_DEFAULT_TOOL_NAMES_BY_STAGE = {
    "investigator": (
        "get_target_recent_tweets",
        "get_target_price_action",
        "get_official_token_profile",
    ),
    "decision_maker": ("get_target_recent_tweets",),
}
_DEFAULT_ROUTE_TOOL_BUDGETS = {"cex": 3, "meme": 5, "research_only": 3}
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_id_subset",
    "deterministic_completeness_gate",
)


def build_pulse_harness_manifest(
    *,
    provider: str,
    model: str,
    artifact_version_hash: str,
    timeout_seconds: float,
    stage_names: tuple[str, ...] | list[str] | None = None,
    max_turns_per_stage: dict[str, Any] | None = None,
    tool_names_by_stage: dict[str, Any] | None = None,
    route_tool_budgets: dict[str, Any] | None = None,
    safety_net_enabled: bool = False,
    validators_enabled: tuple[str, ...] | list[str] | None = None,
    failure_taxonomy_version: str = PULSE_FAILURE_TAXONOMY_VERSION,
) -> dict[str, Any]:
    stages = _stable_strings(stage_names) or list(_DEFAULT_STAGE_NAMES)
    return {
        "harness_version": PULSE_AGENT_HARNESS_VERSION,
        "strategy": PULSE_AGENT_STRATEGY,
        "runtime": {
            "framework": "openai-agents-python",
            "orchestration": "sequential_stage_runner",
            "stages": stages,
            "max_turns_per_stage": _int_mapping(
                max_turns_per_stage,
                default=_DEFAULT_MAX_TURNS_PER_STAGE,
                keys=stages,
            ),
            "tool_names_by_stage": _tool_names_by_stage(tool_names_by_stage, stages=stages),
            "route_tool_budgets": _int_mapping(route_tool_budgets, default=_DEFAULT_ROUTE_TOOL_BUDGETS),
            "safety_net_enabled": bool(safety_net_enabled),
            "timeout_seconds": float(timeout_seconds),
        },
        "model": {
            "provider": str(provider or ""),
            "model": str(model or ""),
            "artifact_version_hash": str(artifact_version_hash or ""),
        },
        "contracts": {
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "decision_routes": ["cex", "meme", "research_only"],
            "decision_recommendations": [
                "high_conviction",
                "trade_candidate",
                "watchlist",
                "ignore",
                "abstain",
            ],
            "validators_enabled": _stable_strings(validators_enabled) or list(_DEFAULT_VALIDATORS_ENABLED),
            "tool_contract": {
                "stage": "investigator",
                "budget_owner": "harness",
                "evidence_ids_must_resolve_to_context": True,
            },
        },
        "gate_policy": {
            "gate_version": PULSE_GATE_VERSION,
            "pre_llm_completeness_gate": True,
            "cex_min_score": 0.8,
            "meme_min_score": 0.6,
            "hard_blockers": [
                "research_only_no_resolved_target",
                "decision_latest_missing",
                "dex_floor_unverified",
                "cohort_insufficient",
                "cohort_all_tied",
                "cohort_no_signal",
                "data_completeness_below_hard_gate",
            ],
        },
        "eval_metadata": {
            "deterministic_grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
            "closed_loop": "trace_to_eval_case_to_eval_result",
        },
        "failure_taxonomy": {
            "version": str(failure_taxonomy_version or PULSE_FAILURE_TAXONOMY_VERSION),
            "codes": list(PULSE_FAILURE_TAXONOMY_CODES),
        },
    }


def pulse_harness_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _tool_names_by_stage(value: dict[str, Any] | None, *, stages: list[str]) -> dict[str, list[str]]:
    source = value if isinstance(value, dict) else _DEFAULT_TOOL_NAMES_BY_STAGE
    return {stage: _stable_strings(source.get(stage)) for stage in stages}


def _int_mapping(
    value: dict[str, Any] | None,
    *,
    default: dict[str, int],
    keys: list[str] | None = None,
) -> dict[str, int]:
    source = value if isinstance(value, dict) else default
    selected = keys if keys is not None else sorted(set(default) | {str(key) for key in source})
    result: dict[str, int] = {}
    for key in selected:
        result[str(key)] = max(0, _int(source.get(key, default.get(str(key), 0))))
    return result


def _stable_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list | tuple | set) else []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "PULSE_AGENT_HARNESS_VERSION",
    "PULSE_AGENT_STRATEGY",
    "PULSE_DETERMINISTIC_GRADER_VERSION",
    "PULSE_FAILURE_TAXONOMY_CODES",
    "PULSE_FAILURE_TAXONOMY_VERSION",
    "build_pulse_harness_manifest",
    "pulse_harness_hash",
]
