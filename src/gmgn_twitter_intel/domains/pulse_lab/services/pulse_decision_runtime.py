from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import (
    BACKEND,
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.pulse_lab.providers import (
    PulseAgentToolRuntime,
    PulseDecisionStageSpec,
)
from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import fetch_evidence_event_urls
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import pulse_runtime_hash
from gmgn_twitter_intel.domains.pulse_lab.services.prompt_loader import (
    load_decision_maker_prompt,
    load_investigator_prompt,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    DecisionRoute,
    FinalDecision,
    InvestigationReport,
    StageRunAudit,
)

_DEFAULT_INVESTIGATOR_BUDGETS: dict[str, int] = {"cex": 3, "meme": 5, "research_only": 3}


@dataclass(frozen=True, slots=True)
class PulseDecisionRuntimeService:
    db_pool: Any

    def tool_budget_for_route(self, *, route: DecisionRoute, budgets: dict[str, int] | None) -> int:
        configured = budgets or {}
        return int(configured.get(str(route), _DEFAULT_INVESTIGATOR_BUDGETS.get(str(route), 3)))

    def investigator_stage_spec(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
    ) -> PulseDecisionStageSpec:
        return PulseDecisionStageSpec(
            stage="investigator",
            prompt_text=load_investigator_prompt(route),
            input_payload={"route": route, "context": context, "completeness": completeness},
        )

    def decision_maker_stage_spec(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
        investigation: InvestigationReport,
    ) -> PulseDecisionStageSpec:
        return PulseDecisionStageSpec(
            stage="decision_maker",
            prompt_text=load_decision_maker_prompt(route),
            input_payload={
                "route": route,
                "context": context,
                "completeness": completeness,
                "investigation": investigation.model_dump(mode="json"),
            },
        )

    def validate_supporting_ids(
        self,
        investigation: InvestigationReport,
        *,
        tool_runtime: PulseAgentToolRuntime,
        context: dict[str, Any],
    ) -> None:
        allowed = _context_event_ids(context) | set(tool_runtime.contributed_event_ids)
        for view_name in ("bull_observation", "bear_observation"):
            view: BullBearView = getattr(investigation, view_name)
            if view.strength == "absent":
                continue
            unknown = [event_id for event_id in view.supporting_event_ids if event_id not in allowed]
            if unknown:
                preview = unknown[:5]
                suffix = "..." if len(unknown) > 5 else ""
                raise ValueError(
                    f"{view_name}.supporting_event_ids contains unknown event ids "
                    f"(not in tool contributions or context): {preview}{suffix}"
                )

    def validate_final_evidence_ids(
        self,
        final: FinalDecision,
        *,
        investigation: InvestigationReport,
        tool_runtime: PulseAgentToolRuntime,
        context: dict[str, Any],
    ) -> None:
        allowed = _allowed_final_evidence_ids(
            context=context,
            tool_runtime=tool_runtime,
            investigation=investigation,
        )
        fields = (
            ("evidence_event_ids", final.evidence_event_ids),
            ("bull_view.supporting_event_ids", final.bull_view.supporting_event_ids),
            ("bear_view.supporting_event_ids", final.bear_view.supporting_event_ids),
        )
        for field_name, values in fields:
            unknown = [event_id for event_id in values if event_id not in allowed]
            if unknown:
                preview = unknown[:5]
                suffix = "..." if len(unknown) > 5 else ""
                raise ValueError(
                    f"{field_name} contains unknown event ids "
                    f"(not in context, tool contributions, or Investigator output): {preview}{suffix}"
                )

    def enrich_evidence_urls(self, final: FinalDecision) -> FinalDecision:
        event_ids = _final_url_event_ids(final)
        if not event_ids:
            return final.model_copy(update={"evidence_event_urls": {}})
        urls = fetch_evidence_event_urls(self.db_pool, event_ids=event_ids)
        return final.model_copy(update={"evidence_event_urls": urls})

    def mark_step_failed(self, step: StageRunAudit, *, error: str) -> StageRunAudit:
        return step.model_copy(
            update={
                "status": "failed",
                "error": error[:1000],
                "response_json": step.response_json,
            }
        )

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        model: str,
        artifact_version_hash: str,
        workflow_name: str,
        agent_name: str,
    ) -> dict[str, Any]:
        input_hash = _sha256({"context": context, "route": route, "completeness": completeness})
        runtime_hash = pulse_runtime_hash(runtime_manifest)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": str(run_id or ""),
            "job_id": str(job.get("job_id") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "model": str(model or ""),
            "artifact_version_hash": artifact_version_hash,
            "input_hash": input_hash,
            "runtime_version": str(runtime_manifest.get("runtime_version") or ""),
            "runtime_hash": runtime_hash,
            "candidate_id": _context_string(context, "candidate_id"),
            "candidate_type": _context_string(context, "candidate_type"),
            "subject_key": _context_string(context, "subject_key"),
            "target_type": _context_string(context, "target_type"),
            "target_id": _context_string(context, "target_id"),
            "route": route,
            "completeness": completeness,
        }
        return {
            "backend": BACKEND,
            "sdk_trace_id": _trace_id(run_id),
            "workflow_name": str(workflow_name or ""),
            "agent_name": str(agent_name or ""),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "artifact_version_hash": artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
            "runtime_version": str(runtime_manifest.get("runtime_version") or ""),
            "runtime_hash": runtime_hash,
            "runtime_manifest": runtime_manifest,
        }

    def with_output_hash(self, audit: dict[str, Any], *, final: FinalDecision) -> dict[str, Any]:
        return {**audit, "output_hash": _sha256(final.model_dump(mode="json"))}


def _context_event_ids(context: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for key in ("evidence_event_ids", "source_event_ids"):
        values = context.get(key) if isinstance(context, dict) else None
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    allowed.add(value.strip())
    return allowed


def _allowed_final_evidence_ids(
    *,
    context: dict[str, Any],
    tool_runtime: PulseAgentToolRuntime,
    investigation: InvestigationReport,
) -> set[str]:
    allowed = _context_event_ids(context) | set(tool_runtime.contributed_event_ids)
    for view in (investigation.bull_observation, investigation.bear_observation):
        for value in view.supporting_event_ids:
            if isinstance(value, str) and value.strip():
                allowed.add(value.strip())
    return allowed


def _final_url_event_ids(final: FinalDecision) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in (
        *final.evidence_event_ids,
        *final.bull_view.supporting_event_ids,
        *final.bear_view.supporting_event_ids,
    ):
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _trace_id(run_id: str) -> str:
    digest = hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:24]
    return f"trace_{digest}"


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


__all__ = ["PulseDecisionRuntimeService"]
