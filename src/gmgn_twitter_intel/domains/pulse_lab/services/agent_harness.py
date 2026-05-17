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


def build_pulse_harness_manifest(
    *,
    provider: str,
    model: str,
    artifact_version_hash: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    return {
        "harness_version": PULSE_AGENT_HARNESS_VERSION,
        "strategy": PULSE_AGENT_STRATEGY,
        "runtime": {
            "framework": "openai-agents-python",
            "orchestration": "sequential_stage_runner",
            "stages": ["investigator", "decision_maker"],
            "max_turns_per_stage": {"investigator": 5, "decision_maker": 3},
            "tools_enabled": True,
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
    }


def pulse_harness_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


__all__ = [
    "PULSE_AGENT_HARNESS_VERSION",
    "PULSE_AGENT_STRATEGY",
    "PULSE_DETERMINISTIC_GRADER_VERSION",
    "build_pulse_harness_manifest",
    "pulse_harness_hash",
]
