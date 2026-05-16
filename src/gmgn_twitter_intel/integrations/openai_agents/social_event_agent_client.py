from __future__ import annotations

import hashlib
import json
from typing import Any

from agents import Agent, ModelRetrySettings, ModelSettings, RunConfig, Runner, retry_policies
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

from gmgn_twitter_intel.domains.social_enrichment.types.social_event_extraction import (
    AGENT_NAME,
    BACKEND,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    WORKFLOW_NAME,
    SocialEventPayload,
    payload_from_output,
    social_event_agent_input,
    social_event_agent_instructions,
    social_event_extraction_from_payload,
)
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import InstructorSafetyNet


class OpenAIAgentsSocialEventClient:
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
        safety_net: InstructorSafetyNet | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ):
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.model is required")
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        self._llm_gateway = llm_gateway
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.trace_enabled = bool(trace_enabled and getattr(self._llm_gateway, "trace_export_enabled", False))
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self.max_turns = max(1, min(2, int(max_turns)))
        self._runner = runner or Runner
        self._safety_net = safety_net
        self._model = None if runner is not None else self._build_model()

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    def request_audit(self, *, event: dict, entities: list[dict], run_id: str, job: dict) -> dict[str, Any]:
        _, audit = self._request_context(event=event, entities=entities, run_id=run_id, job=job)
        return audit

    async def enrich_event(self, *, event: dict, entities: list[dict], run_id: str, job: dict):
        input_payload, audit = self._request_context(event=event, entities=entities, run_id=run_id, job=job)
        agent = Agent(
            name=AGENT_NAME,
            instructions=social_event_agent_instructions(),
            output_type=SocialEventPayload,
            tools=[],
            model=self._model,
            model_settings=_model_settings(),
        )
        run_config = RunConfig(
            workflow_name=self.workflow_name,
            trace_id=audit["sdk_trace_id"],
            group_id=str(event.get("event_id") or ""),
            trace_include_sensitive_data=self.trace_include_sensitive_data,
            tracing_disabled=not self.trace_enabled,
            trace_metadata=audit["trace_metadata"],
        )
        audit_extra: dict[str, Any] = {
            "safety_net_used": False,
            "safety_net_retries": 0,
            "parse_mode": "strict",
        }
        if self._safety_net is not None:
            final_output, audit_extra = await self._llm_gateway.run_with_limits(
                "enrichment",
                "social_event",
                self.timeout_seconds,
                lambda: self._safety_net.run_with_safety_net(
                    agent=agent,
                    input_payload=input_payload,
                    run_config=run_config,
                    pydantic_output_type=SocialEventPayload,
                ),
            )
        else:
            result = await self._llm_gateway.run_with_limits(
                "enrichment",
                "social_event",
                self.timeout_seconds,
                lambda: self._runner.run(
                    agent,
                    input_payload,
                    max_turns=self.max_turns,
                    run_config=run_config,
                ),
            )
            final_output = result.final_output
        payload = payload_from_output(final_output)
        output_json = payload.model_dump(mode="json")
        # PR 1: safety_net audit lives in trace_metadata jsonb until PR 2 promotes columns.
        audit = {
            **audit,
            "output_hash": _sha256(output_json),
            "trace_metadata": {**audit["trace_metadata"], **audit_extra},
        }
        return social_event_extraction_from_payload(
            payload,
            event_text=_event_text(event),
            agent_run_audit=audit,
        )

    def _request_context(
        self,
        *,
        event: dict,
        entities: list[dict],
        run_id: str,
        job: dict,
    ) -> tuple[str, dict[str, Any]]:
        input_payload = social_event_agent_input(event=event, entities=entities)
        input_hash = _sha256(input_payload)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": run_id,
            "event_id": str(event.get("event_id") or ""),
            "job_id": str(job.get("job_id") or ""),
            "job_type": str(job.get("job_type") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "model": self.model,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": input_hash,
        }
        audit = {
            "backend": BACKEND,
            "sdk_trace_id": _trace_id(run_id),
            "workflow_name": self.workflow_name,
            "agent_name": AGENT_NAME,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
        }
        return input_payload, audit

    def _build_model(self):
        return OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=self._llm_gateway.openai_client(
                model=self.model,
                base_url=self.base_url,
                timeout_s=self.timeout_seconds,
            ),
        )


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
        ),
        # qwen3.6 reasoning variant - disable thinking to keep grammar enforced.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def _event_text(event: dict) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


def _trace_id(run_id: str) -> str:
    return "trace_" + hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:32]


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()
