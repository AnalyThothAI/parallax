from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from agents import Agent, RunConfig, Runner, set_tracing_export_api_key
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from .pulse_contract import (
    AGENT_NAME,
    BACKEND,
    PULSE_THESIS_PROMPT_VERSION,
    PULSE_THESIS_SCHEMA_VERSION,
    WORKFLOW_NAME,
)
from .pulse_thesis import (
    PulseThesisPayload,
    pulse_thesis_agent_input,
    pulse_thesis_agent_instructions,
    validate_pulse_thesis_payload,
)


class PulseThesisClientProtocol(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]: ...

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisAgentResult: ...


@dataclass(frozen=True)
class PulseThesisAgentResult:
    payload: PulseThesisPayload
    agent_run_audit: dict[str, Any]


class OpenAIAgentsPulseThesisClient:
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
        max_turns: int = 3,
    ):
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
        self.max_turns = max(1, min(3, int(max_turns)))
        self._runner = runner or Runner
        self._http_client: httpx.AsyncClient | None = None
        self._model = None if runner is not None else self._build_model()

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]:
        _, audit, _ = self._request_context(context=context, run_id=run_id, job=job)
        return audit

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisAgentResult:
        input_payload, audit, input_source_event_ids = self._request_context(
            context=context,
            run_id=run_id,
            job=job,
        )
        agent = Agent(
            name=AGENT_NAME,
            instructions=pulse_thesis_agent_instructions(),
            output_type=PulseThesisPayload,
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
                group_id=_group_id(context),
                trace_include_sensitive_data=self.trace_include_sensitive_data,
                tracing_disabled=not self.trace_enabled,
                trace_metadata=audit["trace_metadata"],
            ),
        )
        payload = validate_pulse_thesis_payload(
            result.final_output,
            input_source_event_ids=set(input_source_event_ids),
        )
        output_json = payload.model_dump(mode="json")
        audit = {**audit, "output_hash": _sha256(output_json)}
        return PulseThesisAgentResult(payload=payload, agent_run_audit=audit)

    def _request_context(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> tuple[str, dict[str, Any], list[str]]:
        input_payload = pulse_thesis_agent_input(context)
        input_hash = _sha256(input_payload)
        input_source_event_ids = _input_source_event_ids(context)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": str(run_id or ""),
            "job_id": str(job.get("job_id") or ""),
            "job_type": str(job.get("job_type") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
            "prompt_version": PULSE_THESIS_PROMPT_VERSION,
            "schema_version": PULSE_THESIS_SCHEMA_VERSION,
            "model": self.model,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": input_hash,
            "candidate_id": _context_string(context, "candidate_id"),
            "candidate_type": _context_string(context, "candidate_type"),
            "subject_key": _context_string(context, "subject_key"),
            "target_type": _context_string(context, "target_type"),
            "target_id": _context_string(context, "target_id"),
        }
        audit = {
            "backend": BACKEND,
            "sdk_trace_id": _trace_id(run_id),
            "workflow_name": self.workflow_name,
            "agent_name": AGENT_NAME,
            "prompt_version": PULSE_THESIS_PROMPT_VERSION,
            "schema_version": PULSE_THESIS_SCHEMA_VERSION,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
            "input_source_event_ids": input_source_event_ids,
        }
        return input_payload, audit, input_source_event_ids

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


def _input_source_event_ids(context: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(_iter_list(context.get("source_event_ids")))
    values.extend(_iter_list(context.get("evidence_event_ids")))
    for post in _iter_mapping_items(context.get("selected_posts")):
        values.append(post.get("event_id"))
    for cluster in _iter_mapping_items(context.get("post_clusters")):
        values.extend(_iter_list(cluster.get("event_ids")))
    for segment in _iter_mapping_items(context.get("stage_segments")):
        values.extend(_iter_list(segment.get("representative_event_ids")))
    return _stable_unique_strings(values)


def _iter_list(value: Any) -> list[Any]:
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _iter_mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict)]


def _stable_unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _context_string(context: dict[str, Any], key: str) -> str:
    return str(context.get(key) or "").strip()


def _group_id(context: dict[str, Any]) -> str:
    return _context_string(context, "candidate_id") or _context_string(context, "subject_key")


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
