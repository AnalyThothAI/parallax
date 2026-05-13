from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from agents import (
    Agent,
    AgentOutputSchema,
    AgentOutputSchemaBase,
    ModelBehaviorError,
    ModelRetrySettings,
    ModelSettings,
    RunConfig,
    Runner,
    retry_policies,
    set_tracing_export_api_key,
)
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from gmgn_twitter_intel.domains.pulse_lab.interfaces import BACKEND
from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import pulse_harness_hash
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    AnalystOpinion,
    CritiqueReport,
    DecisionRoute,
    FinalDecision,
    PulseDecisionPayload,
    StageName,
    StageRunAudit,
)
from gmgn_twitter_intel.integrations.openai_agents.pulse_stage_prompts import pulse_stage_prompt

WORKFLOW_NAME = "gmgn-twitter-intel.pulse_decision"
AGENT_NAME = "PulseDecisionPipeline"
PULSE_DECISION_PROMPT_VERSION = "pulse-decision-v1"
PULSE_DECISION_SCHEMA_VERSION = "pulse_decision_v1"


@dataclass(frozen=True)
class PulseDecisionAgentResult:
    final_decision: FinalDecision
    run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class _JsonFenceTolerantOutputSchema(AgentOutputSchemaBase):
    def __init__(self, output_type: type[Any]) -> None:
        self._schema = AgentOutputSchema(output_type)

    def is_plain_text(self) -> bool:
        return self._schema.is_plain_text()

    def name(self) -> str:
        return self._schema.name()

    def json_schema(self) -> dict[str, Any]:
        return self._schema.json_schema()

    def is_strict_json_schema(self) -> bool:
        return self._schema.is_strict_json_schema()

    def validate_json(self, json_str: str) -> Any:
        try:
            return self._schema.validate_json(json_str)
        except ModelBehaviorError:
            normalized = _strip_single_json_fence(json_str)
            if normalized == json_str:
                raise
            return self._schema.validate_json(normalized)


class OpenAIAgentsPulseDecisionClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        runner: Any | None = None,
        trace_enabled: bool = True,
        trace_api_key: str | None = None,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.pulse_agent_model or llm.model is required")
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        tracing_export_key = str(trace_api_key or "").strip()
        if not tracing_export_key and _is_openai_base_url(self.base_url):
            tracing_export_key = self.api_key
        self.trace_enabled = bool(trace_enabled and tracing_export_key)
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        if self.trace_enabled:
            set_tracing_export_api_key(tracing_export_key)
        self._runner = runner or Runner
        self._http_client: httpx.AsyncClient | None = None
        self._model = None if runner is not None else self._build_model()

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            harness=harness,
        )

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> PulseDecisionAgentResult:
        audit = self._request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            harness=harness,
        )
        analyst = await self._run_stage(
            stage="analyst",
            route=route,
            output_type=AnalystOpinion,
            input_json={"route": route, "context": context, "completeness": completeness},
            run_id=run_id,
            audit=audit,
        )
        analyst_output = AnalystOpinion.model_validate(analyst.response_json)
        critic = await self._run_stage(
            stage="critic",
            route=route,
            output_type=CritiqueReport,
            input_json={
                "route": route,
                "context": context,
                "completeness": completeness,
                "analyst": analyst_output.model_dump(mode="json"),
            },
            run_id=run_id,
            audit=audit,
        )
        critic_output = CritiqueReport.model_validate(critic.response_json)
        stage_audits: list[StageRunAudit] = [analyst, critic]
        if critic_output.should_abstain:
            final = FinalDecision(
                route=route,
                recommendation="abstain",
                confidence=critic_output.confidence_ceiling,
                abstain_reason="critic_veto",
                summary_zh=analyst_output.summary_zh,
                invalidation_conditions=list(critic_output.missing_fact_impacts),
                residual_risks=list(critic_output.weaknesses),
                evidence_event_ids=[],
            )
            PulseDecisionPayload(final_decision=final, stage_audits=tuple(stage_audits))
            return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))

        judge = await self._run_stage(
            stage="judge",
            route=route,
            output_type=FinalDecision,
            input_json={
                "route": route,
                "context": context,
                "completeness": completeness,
                "analyst": analyst_output.model_dump(mode="json"),
                "critic": critic_output.model_dump(mode="json"),
            },
            run_id=run_id,
            audit=audit,
        )
        final = FinalDecision.model_validate(judge.response_json)
        if final.confidence > critic_output.confidence_ceiling:
            final = final.model_copy(update={"confidence": critic_output.confidence_ceiling})
        stage_audits.append(judge)
        PulseDecisionPayload(final_decision=final, stage_audits=tuple(stage_audits))
        audit = {**audit, "output_hash": _sha256(final.model_dump(mode="json"))}
        return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))

    async def _run_stage(
        self,
        *,
        stage: StageName,
        route: DecisionRoute,
        output_type: type[Any],
        input_json: dict[str, Any],
        run_id: str,
        audit: dict[str, Any],
    ) -> StageRunAudit:
        prompt = pulse_stage_prompt(route=route, stage=stage)
        agent = Agent(
            name=_stage_agent_name(route=route, stage=stage),
            instructions=prompt,
            output_type=_JsonFenceTolerantOutputSchema(output_type),
            tools=[],
            model=self._model,
            model_settings=_model_settings(),
        )
        stage_input = json.dumps(input_json, ensure_ascii=False, sort_keys=True)
        started = int(time.time() * 1000)
        result = await self._runner.run(
            agent,
            stage_input,
            max_turns=1,
            run_config=RunConfig(
                workflow_name=self.workflow_name,
                trace_id=audit["sdk_trace_id"],
                group_id=_group_id(input_json.get("context")),
                trace_include_sensitive_data=self.trace_include_sensitive_data,
                tracing_disabled=not self.trace_enabled,
                trace_metadata={**audit["trace_metadata"], "stage": stage, "route": route},
            ),
        )
        output = output_type.model_validate(result.final_output)
        finished = int(time.time() * 1000)
        return StageRunAudit(
            stage=stage,
            route=route,
            attempt_index=0,
            input_json=input_json,
            prompt_text=prompt,
            response_json=output.model_dump(mode="json"),
            trace_metadata_json={**audit["trace_metadata"], "stage": stage, "route": route},
            usage_json={},
            latency_ms=max(0, finished - started),
            status="ok",
            error=None,
        )

    def _request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> dict[str, Any]:
        input_hash = _sha256({"context": context, "route": route, "completeness": completeness})
        harness_hash = pulse_harness_hash(harness)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": str(run_id or ""),
            "job_id": str(job.get("job_id") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "model": self.model,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": input_hash,
            "harness_version": str(harness.get("harness_version") or ""),
            "harness_hash": harness_hash,
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
            "workflow_name": self.workflow_name,
            "agent_name": AGENT_NAME,
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
            "harness_version": str(harness.get("harness_version") or ""),
            "harness_hash": harness_hash,
            "harness": harness,
        }

    def _build_model(self):
        self._http_client = httpx.AsyncClient(trust_env=False)
        return OpenAIResponsesModel(
            model=self.model,
            openai_client=AsyncOpenAI(
                api_key=str(self.api_key or ""),
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                max_retries=0,
                default_headers={"User-Agent": "gmgn-twitter-intel/0.1"},
                http_client=self._http_client,
            ),
        )

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


def _model_settings() -> ModelSettings:
    return ModelSettings(
        retry=ModelRetrySettings(
            max_retries=2,
            backoff={"initial_delay": 0.5, "max_delay": 4.0, "multiplier": 2.0, "jitter": True},
            policy=retry_policies.any(
                retry_policies.provider_suggested(),
                retry_policies.retry_after(),
                retry_policies.network_error(),
                retry_policies.http_status([408, 409, 429, 500, 502, 503, 504]),
            ),
        )
    )


def _stage_agent_name(*, route: DecisionRoute, stage: StageName) -> str:
    route_label = {"cex": "Cex", "meme": "Meme", "research_only": "ResearchOnly"}[route]
    stage_label = {"analyst": "Analyst", "critic": "Critic", "judge": "Judge", "research_only_gate": "Gate"}[stage]
    return f"{route_label}{stage_label}"


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip()
    return value.rstrip("/") if value else "https://api.openai.com/v1"


def _is_openai_base_url(base_url: str) -> bool:
    return _api_base(base_url) == "https://api.openai.com/v1"


def _trace_id(run_id: str) -> str:
    digest = hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:24]
    return f"trace_{digest}"


def _group_id(context: Any) -> str | None:
    if not isinstance(context, dict):
        return None
    candidate_id = _context_string(context, "candidate_id")
    if candidate_id:
        return candidate_id
    return _context_string(context, "subject_key")


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _strip_single_json_fence(value: str) -> str:
    text = str(value or "").strip()
    lines = text.splitlines()
    if len(lines) < 3:
        return value
    if lines[0].strip().lower() != "```json":
        return value
    if lines[-1].strip() != "```":
        return value
    return "\n".join(lines[1:-1]).strip()


__all__ = [
    "AGENT_NAME",
    "PULSE_DECISION_PROMPT_VERSION",
    "PULSE_DECISION_SCHEMA_VERSION",
    "WORKFLOW_NAME",
    "OpenAIAgentsPulseDecisionClient",
    "PulseDecisionAgentResult",
]
