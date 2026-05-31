from __future__ import annotations

import hashlib
import json
from typing import Any

from parallax.domains.pulse_lab.interfaces import (
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
    PULSE_GATE_VERSION,
)

PULSE_AGENT_RUNTIME_VERSION = "pulse-research-committee-runtime-v1"
PULSE_AGENT_STRATEGY = "signal_pulse_decision"
PULSE_DETERMINISTIC_GRADER_VERSION = "pulse-deterministic-eval-v3"
PULSE_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"
PULSE_EVIDENCE_PACKET_SCHEMA_VERSION = "pulse-evidence-packet-v1"
PULSE_FAILURE_TAXONOMY_CODES = (
    "invalid_schema",
    "invalid_unknown_evidence_ref",
    "invalid_unsupported_claim",
    "timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "unexpected_exception",
)

_DEFAULT_STAGE_NAMES = ("signal_analyst", "bear_case", "risk_portfolio_judge")
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_ref_subset",
    "deterministic_completeness_gate",
)


def build_pulse_runtime_manifest(
    *,
    provider: str,
    model: str,
    artifact_version_hash: str,
    timeout_seconds: float,
    stage_names: tuple[str, ...] | list[str] | None = None,
    safety_net_enabled: bool = False,
    validators_enabled: tuple[str, ...] | list[str] | None = None,
    failure_taxonomy_version: str = PULSE_FAILURE_TAXONOMY_VERSION,
    evidence_packet_schema_version: str = PULSE_EVIDENCE_PACKET_SCHEMA_VERSION,
) -> dict[str, Any]:
    stages = _stable_strings(stage_names) or list(_DEFAULT_STAGE_NAMES)
    return {
        "runtime_version": PULSE_AGENT_RUNTIME_VERSION,
        "strategy": PULSE_AGENT_STRATEGY,
        "runtime": {
            "framework": "litellm",
            "orchestration": "sequential_stage_runner",
            "stages": stages,
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
            "evidence_packet_schema_version": str(
                evidence_packet_schema_version or PULSE_EVIDENCE_PACKET_SCHEMA_VERSION
            ),
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


def pulse_runtime_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _stable_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list | tuple | set) else []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


__all__ = [
    "PULSE_AGENT_RUNTIME_VERSION",
    "PULSE_AGENT_STRATEGY",
    "PULSE_DETERMINISTIC_GRADER_VERSION",
    "PULSE_FAILURE_TAXONOMY_CODES",
    "PULSE_FAILURE_TAXONOMY_VERSION",
    "build_pulse_runtime_manifest",
    "pulse_runtime_hash",
]
