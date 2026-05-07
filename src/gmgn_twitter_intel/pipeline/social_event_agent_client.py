from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

import httpx
from agents import Agent, RunConfig, Runner, set_tracing_export_api_key
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from .social_event_extraction import (
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


class EnrichmentClientProtocol(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    async def enrich_event(self, *, event: dict, entities: list[dict], run_id: str, job: dict): ...


class OpenAIAgentsSocialEventClient:
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
        max_turns: int = 1,
    ):
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.model is required")
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
        self.max_turns = max(1, min(2, int(max_turns)))
        self._runner = runner or Runner
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
        )
        result = await self._runner.run(
            agent,
            input_payload,
            max_turns=self.max_turns,
            run_config=RunConfig(
                workflow_name=self.workflow_name,
                trace_id=audit["sdk_trace_id"],
                group_id=str(event.get("event_id") or ""),
                trace_include_sensitive_data=self.trace_include_sensitive_data,
                tracing_disabled=not self.trace_enabled,
                trace_metadata=audit["trace_metadata"],
            ),
        )
        payload = payload_from_output(result.final_output)
        output_json = payload.model_dump(mode="json")
        audit = {**audit, "output_hash": _sha256(output_json)}
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
        return OpenAIResponsesModel(
            model=self.model,
            openai_client=AsyncOpenAI(
                api_key=str(self.api_key or ""),
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                max_retries=0,
                default_headers={"User-Agent": "gmgn-twitter-intel/0.1"},
                http_client=httpx.AsyncClient(trust_env=False),
            ),
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


def _is_openai_base_url(base_url: str) -> bool:
    value = str(base_url or "").strip().lower()
    return value.startswith("https://api.openai.com/")


def _trace_id(run_id: str) -> str:
    return "trace_" + hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:32]


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()
