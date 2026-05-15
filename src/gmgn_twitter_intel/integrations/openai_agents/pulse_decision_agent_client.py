from __future__ import annotations

import hashlib
import inspect
import json
import time
from dataclasses import dataclass
from types import GetSetDescriptorType, MemberDescriptorType
from typing import Any, cast

from agents import (
    Agent,
    AgentOutputSchema,
    AgentOutputSchemaBase,
    ModelRetrySettings,
    ModelSettings,
    RunConfig,
    Runner,
    retry_policies,
)
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

from gmgn_twitter_intel.domains.pulse_lab.interfaces import BACKEND
from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import pulse_harness_hash
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    AnalystOpinion,
    CritiqueReport,
    DecisionRoute,
    FinalDecision,
    PulseDecisionPayload,
    PulseStageFailure,
    StageName,
    StageRunAudit,
    StageStatus,
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


class _JsonOutputSchema(AgentOutputSchemaBase):
    """Prompt-based JSON output: schema lives in instructions, not in strict response_format.

    Works across OpenAI / DeepSeek / qwen on the OpenAI-compatible Chat Completions surface
    because it relies on the model following the prompt, not on the provider honoring strict
    json_schema. Recovers JSON embedded in prose by extracting the first balanced object.
    """

    def __init__(self, output_type: type[Any]) -> None:
        self._schema = AgentOutputSchema(output_type, strict_json_schema=False)

    def is_plain_text(self) -> bool:
        return self._schema.is_plain_text()

    def name(self) -> str:
        return self._schema.name()

    def json_schema(self) -> dict[str, Any]:
        return self._schema.json_schema()

    def is_strict_json_schema(self) -> bool:
        return False

    def validate_json(self, json_str: str) -> Any:
        text = str(json_str or "")
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else text
        return self._schema.validate_json(candidate)


class OpenAIAgentsPulseDecisionClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        llm_gateway: Any,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        runner: Any | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.pulse_agent_model or llm.model is required")
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        self._llm_gateway = llm_gateway
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.trace_enabled = bool(trace_enabled and getattr(self._llm_gateway, "trace_export_enabled", False))
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self._runner = runner or Runner
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
        stage_audits: list[StageRunAudit] = []
        analyst = await self._run_stage(
            stage="analyst",
            route=route,
            output_type=AnalystOpinion,
            input_json={"route": route, "context": context, "completeness": completeness},
            run_id=run_id,
            audit=audit,
        )
        stage_audits.append(analyst)
        if analyst.status != "ok":
            raise PulseStageFailure(
                f"analyst stage {analyst.status}: {analyst.error}",
                audits=tuple(stage_audits),
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
        stage_audits.append(critic)
        if critic.status != "ok":
            raise PulseStageFailure(
                f"critic stage {critic.status}: {critic.error}",
                audits=tuple(stage_audits),
            )
        critic_output = CritiqueReport.model_validate(critic.response_json)
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
        stage_audits.append(judge)
        if judge.status != "ok":
            raise PulseStageFailure(
                f"judge stage {judge.status}: {judge.error}",
                audits=tuple(stage_audits),
            )
        final = FinalDecision.model_validate(judge.response_json)
        if final.confidence > critic_output.confidence_ceiling:
            final = final.model_copy(update={"confidence": critic_output.confidence_ceiling})
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
        prompt = pulse_stage_prompt(route=route, stage=stage, output_type=output_type)
        agent = Agent(
            name=_stage_agent_name(route=route, stage=stage),
            instructions=prompt,
            output_type=_JsonOutputSchema(output_type),
            tools=[],
            model=self._model,
            model_settings=_model_settings(),
        )
        stage_input = json.dumps(input_json, ensure_ascii=False, sort_keys=True)
        trace_metadata = {**audit["trace_metadata"], "stage": stage, "route": route}
        started = int(time.time() * 1000)
        raw_output: Any = None
        try:
            result = await self._llm_gateway.run_with_limits(
                "pulse_candidate",
                stage,
                self.timeout_seconds,
                lambda: self._runner.run(
                    agent,
                    stage_input,
                    max_turns=1,
                    run_config=RunConfig(
                        workflow_name=self.workflow_name,
                        trace_id=audit["sdk_trace_id"],
                        group_id=_group_id(input_json.get("context")),
                        trace_include_sensitive_data=self.trace_include_sensitive_data,
                        tracing_disabled=not self.trace_enabled,
                        trace_metadata=trace_metadata,
                    ),
                ),
            )
            raw_output = result.final_output
            usage = _extract_usage(result)
            output = output_type.model_validate(raw_output)
        except Exception as exc:
            finished = int(time.time() * 1000)
            status: StageStatus = "timeout" if isinstance(exc, TimeoutError) else "failed"
            return StageRunAudit(
                stage=stage,
                route=route,
                attempt_index=0,
                input_json=input_json,
                prompt_text=prompt,
                response_json={"raw_output": _truncate(raw_output)} if raw_output is not None else None,
                trace_metadata_json=trace_metadata,
                usage_json=_extract_usage(locals().get("result")),
                latency_ms=max(0, finished - started),
                started_at_ms=started,
                finished_at_ms=finished,
                status=status,
                error=f"{type(exc).__name__}: {exc}"[:1000],
            )
        finished = int(time.time() * 1000)
        return StageRunAudit(
            stage=stage,
            route=route,
            attempt_index=0,
            input_json=input_json,
            prompt_text=prompt,
            response_json=output.model_dump(mode="json"),
            trace_metadata_json=trace_metadata,
            usage_json=usage,
            latency_ms=max(0, finished - started),
            started_at_ms=started,
            finished_at_ms=finished,
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
        return OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=self._llm_gateway.openai_client(
                model=self.model,
                base_url=self.base_url,
                timeout_s=self.timeout_seconds,
            ),
        )

    async def aclose(self) -> None:
        return None


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
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


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


def _truncate(value: Any, *, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _extract_usage(result: Any) -> dict[str, Any]:
    for candidate in _usage_candidates(result):
        payload = _usage_payload(candidate)
        if payload:
            return payload
    return {}


def _usage_candidates(result: Any) -> list[Any]:
    if result is None:
        return []
    candidates = [
        getattr(result, "usage", None),
        getattr(getattr(result, "context_wrapper", None), "usage", None),
    ]
    for attr in ("raw_response", "response", "final_response"):
        response = getattr(result, attr, None)
        candidates.append(getattr(response, "usage", None))
        candidates.append(response)
    responses = getattr(result, "raw_responses", None) or getattr(result, "responses", None)
    if isinstance(responses, list | tuple):
        for response in responses:
            candidates.append(getattr(response, "usage", None))
            candidates.append(response)
    return candidates


def _usage_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        if isinstance(data, dict):
            return cast(dict[str, Any], _json_safe_usage(data))
    data = _json_safe_usage(value)
    if isinstance(data, dict):
        return data
    return {}


def _json_safe_usage(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 8:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_usage(item, depth=depth + 1) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_json_safe_usage(item, depth=depth + 1) for item in value if item is not None]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        return _json_safe_usage(data, depth=depth + 1)
    object_values = _public_object_values(value)
    if object_values:
        return {key: _json_safe_usage(item, depth=depth + 1) for key, item in object_values.items() if item is not None}
    return str(value)


def _public_object_values(value: Any) -> dict[str, Any]:
    if not hasattr(value, "__dict__") and not hasattr(value, "__slots__"):
        return {}
    data = {}
    if hasattr(value, "__dict__"):
        data.update(
            {str(key): item for key, item in vars(value).items() if not str(key).startswith("_") and item is not None}
        )
    slot_names = set(_public_slot_names(value))
    for name in slot_names:
        if name in data:
            continue
        try:
            item = getattr(value, name)
        except AttributeError:
            continue
        if item is not None:
            data[name] = item
    for name, item in inspect.getmembers_static(value):
        if name.startswith("_") or name in data:
            continue
        if isinstance(item, property | classmethod | staticmethod):
            continue
        if isinstance(item, GetSetDescriptorType | MemberDescriptorType):
            continue
        if item is None or callable(item):
            continue
        if isinstance(item, type):
            continue
        data[name] = item
    return data


def _public_slot_names(value: Any) -> tuple[str, ...]:
    names: list[str] = []
    for cls in type(value).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slot_items = (slots,)
        else:
            try:
                slot_items = tuple(slots)
            except TypeError:
                continue
        for name in slot_items:
            text = str(name)
            if text.startswith("_") or text in {"__dict__", "__weakref__"}:
                continue
            names.append(text)
    return tuple(names)


__all__ = [
    "AGENT_NAME",
    "PULSE_DECISION_PROMPT_VERSION",
    "PULSE_DECISION_SCHEMA_VERSION",
    "WORKFLOW_NAME",
    "OpenAIAgentsPulseDecisionClient",
    "PulseDecisionAgentResult",
    "_extract_usage",
]
