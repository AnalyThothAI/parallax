from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from agents import Agent, RunConfig, Runner, set_tracing_export_api_key
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

BACKEND = "openai_agents_sdk"
WORKFLOW_NAME = "gmgn-twitter-intel.watchlist_handle_summary"
AGENT_NAME = "WatchlistHandleSummaryAgent"
PROMPT_VERSION = "watchlist-handle-summary-v1"
SCHEMA_VERSION = "watchlist_handle_summary_v1"


class WatchlistTopicPayload(BaseModel):
    title: str
    description: str
    event_count: int = Field(ge=0)
    top_event_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class WatchlistHandleSummaryPayload(BaseModel):
    summary_zh: str
    topics: list[WatchlistTopicPayload] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)


class OpenAIAgentsWatchlistSummaryClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        runner: Any | None = None,
        trace_enabled: bool = True,
        trace_api_key: str | None = None,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("watchlist_handle_summary_model is required")
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

    def request_audit(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        _, audit = self._request_context(handle=handle, events=events, run_id=run_id, job=job, context=context)
        return audit

    async def summarize_handle(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        input_payload, audit = self._request_context(
            handle=handle,
            events=events,
            run_id=run_id,
            job=job,
            context=context,
        )
        agent = Agent(
            name=AGENT_NAME,
            instructions=_instructions(),
            output_type=WatchlistHandleSummaryPayload,
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
                group_id=handle,
                trace_include_sensitive_data=self.trace_include_sensitive_data,
                tracing_disabled=not self.trace_enabled,
                trace_metadata=audit["trace_metadata"],
            ),
        )
        payload = result.final_output
        if not isinstance(payload, WatchlistHandleSummaryPayload):
            payload = WatchlistHandleSummaryPayload.model_validate(payload)
        output_json = payload.model_dump(mode="json")
        return {
            **output_json,
            "agent_run_audit": {**audit, "output_hash": _sha256(output_json)},
        }

    async def aclose(self) -> None:
        return None

    def _request_context(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        input_json = {
            "handle": handle,
            "context": context,
            "events": [_event_payload(item) for item in events],
        }
        input_payload = json.dumps(input_json, ensure_ascii=False, sort_keys=True)
        input_hash = _sha256(input_json)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": run_id,
            "handle": handle,
            "job_handle": str(job.get("handle") or ""),
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


def _instructions() -> str:
    return (
        "You summarize a watched crypto Twitter account's recent structured signal events for a Chinese trader UI. "
        "Write concise Simplified Chinese. Identify 1-5 recurring topics, catalysts, or narrative changes. "
        "Use only provided events. Do not invent prices, market caps, or facts absent from input. "
        "Return topics as title, description, event_count, top_event_ids, symbols, and confidence. Keep titles short."
    )


def _event_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item.get("event_id"),
        "received_at_ms": item.get("received_at_ms"),
        "event_type": item.get("event_type"),
        "subject": item.get("subject"),
        "summary_zh": item.get("summary_zh"),
        "anchor_terms": item.get("anchor_terms") or [],
        "token_candidates": item.get("token_candidates") or [],
        "cashtags": item.get("cashtags") or [],
        "hashtags": item.get("hashtags") or [],
        "text": item.get("event_text") or "",
    }


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


__all__ = ["OpenAIAgentsWatchlistSummaryClient"]
