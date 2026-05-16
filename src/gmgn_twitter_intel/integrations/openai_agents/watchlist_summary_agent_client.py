from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import jsonref
from agents import Agent, ModelRetrySettings, ModelSettings, RunConfig, Runner, retry_policies
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from pydantic import BaseModel, Field

from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import InstructorSafetyNet

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


class _WatchlistOutputSchema(AgentOutputSchemaBase):
    """Strict + jsonref-flattened wrapper around WatchlistHandleSummaryPayload.

    Same shape as pulse_decision_agent_client._JsonOutputSchema. Kept inline here
    until PR 3 moves the shared helper into integrations/openai_agents/_shared.py.
    """

    def __init__(self) -> None:
        self._output_type = WatchlistHandleSummaryPayload
        self._schema = AgentOutputSchema(WatchlistHandleSummaryPayload, strict_json_schema=True)
        raw = self._schema.json_schema()
        self._flat = jsonref.replace_refs(raw, proxies=False, lazy_load=False)

    @property
    def output_type(self) -> type[BaseModel]:
        return self._output_type

    def is_plain_text(self) -> bool:
        return self._schema.is_plain_text()

    def name(self) -> str:
        return self._schema.name()

    def json_schema(self) -> dict[str, Any]:
        return self._flat

    def is_strict_json_schema(self) -> bool:
        return True

    def validate_json(self, json_str: str) -> Any:
        text = str(json_str or "")
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else text
        return self._schema.validate_json(candidate)


class OpenAIAgentsWatchlistSummaryClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        llm_gateway: Any,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("watchlist_handle_summary_model is required")
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
            output_type=_WatchlistOutputSchema(),
            tools=[],
            model=self._model,
            model_settings=_model_settings(),
        )
        run_config = RunConfig(
            workflow_name=self.workflow_name,
            trace_id=audit["sdk_trace_id"],
            group_id=handle,
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
                "handle_summary",
                "summary",
                self.timeout_seconds,
                lambda: self._safety_net.run_with_safety_net(
                    agent=agent,
                    input_payload=input_payload,
                    run_config=run_config,
                    pydantic_output_type=WatchlistHandleSummaryPayload,
                ),
            )
        else:
            result = await self._llm_gateway.run_with_limits(
                "handle_summary",
                "summary",
                self.timeout_seconds,
                lambda: self._runner.run(
                    agent,
                    input_payload,
                    max_turns=self.max_turns,
                    run_config=run_config,
                ),
            )
            final_output = result.final_output
        payload = _coerce_summary_payload(final_output)
        output_json = payload.model_dump(mode="json")
        return {
            **output_json,
            "agent_run_audit": {**audit, "output_hash": _sha256(output_json), **audit_extra},
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
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        include_usage=True,
    )


def _instructions() -> str:
    return (
        "You summarize a watched crypto Twitter account's recent structured signal events for a Chinese trader UI. "
        "Write concise Simplified Chinese. Identify 1-5 recurring topics, catalysts, or narrative changes. "
        "Use only provided events. Do not invent prices, market caps, or facts absent from input. "
        "Return one valid JSON object only. Do not return Markdown, bullets, code fences, or prose outside JSON. "
        'Schema: {"summary_zh": string, "topics": [{"title": string, "description": string, '
        '"event_count": integer, "top_event_ids": string[], "symbols": string[], "confidence": number}], '
        '"residual_risks": string[]}. Keep titles short.'
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


def _coerce_summary_payload(value: Any) -> WatchlistHandleSummaryPayload:
    if isinstance(value, WatchlistHandleSummaryPayload):
        return value
    if isinstance(value, dict):
        if "summary_zh" not in value and _looks_like_topic(value):
            value = _payload_from_topics([value])
        return WatchlistHandleSummaryPayload.model_validate(value)
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return WatchlistHandleSummaryPayload.model_validate(_payload_from_topics(value))
    if isinstance(value, str):
        text = value.strip()
        parsed = _parse_json_object(text)
        if parsed is not None:
            if "summary_zh" not in parsed and _looks_like_topic(parsed):
                parsed = _payload_from_topics([parsed])
            return WatchlistHandleSummaryPayload.model_validate(parsed)
        parsed_list = _parse_json_list(text)
        if parsed_list is not None:
            return WatchlistHandleSummaryPayload.model_validate(_payload_from_topics(parsed_list))
        markdown_payload = _parse_markdown_summary(text)
        if markdown_payload is not None:
            return WatchlistHandleSummaryPayload.model_validate(markdown_payload)
    return WatchlistHandleSummaryPayload.model_validate(value)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = _raw_decode_json_object(candidate)
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_json_list(text: str) -> list[dict[str, Any]] | None:
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = _raw_decode_json_list(candidate)
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            return parsed
    return None


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    return candidates


def _raw_decode_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _raw_decode_json_list(text: str) -> list[dict[str, Any]] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", text):
        try:
            parsed, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            return parsed
    return None


def _looks_like_topic(value: dict[str, Any]) -> bool:
    return bool(value.get("title") and value.get("description"))


def _payload_from_topics(topics: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_topics = [_normalize_topic_dict(topic) for topic in topics if _looks_like_topic(topic)]
    summary_parts = [f"{topic['title']}：{topic['description']}" for topic in normalized_topics[:3]]
    return {
        "summary_zh": "；".join(summary_parts),
        "topics": normalized_topics[:5],
        "residual_risks": [],
    }


def _normalize_topic_dict(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(topic.get("title") or "").strip(),
        "description": str(topic.get("description") or "").strip(),
        "event_count": int(topic.get("event_count") or 1),
        "top_event_ids": [str(item) for item in topic.get("top_event_ids") or []],
        "symbols": [str(item).strip().strip("$#") for item in topic.get("symbols") or [] if str(item).strip()],
        "confidence": _coerce_confidence(topic.get("confidence")),
    }


def _parse_markdown_summary(text: str) -> dict[str, Any] | None:
    blocks = _markdown_topic_blocks(text)
    topics = [_parse_markdown_topic(block) for block in blocks]
    topics = [topic for topic in topics if topic is not None]
    if not topics:
        return None
    summary_parts = [f"{topic['title']}：{topic['description']}" for topic in topics[:3]]
    return {
        "summary_zh": "；".join(summary_parts),
        "topics": topics[:5],
        "residual_risks": [],
    }


def _markdown_topic_blocks(text: str) -> list[str]:
    matches = list(re.finditer(r"(?m)^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*\d+[.、]\s*", text))
    if not matches:
        return []
    blocks: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(text[match.start() : end].strip())
    return blocks


def _parse_markdown_topic(block: str) -> dict[str, Any] | None:
    title_match = re.search(r"^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*\d+[.、]\s*(.+?)(?:\*\*)?\s*$", block, re.MULTILINE)
    if not title_match:
        return None
    title = _clean_markdown(title_match.group(1))
    description = _field_value(block, "描述") or _first_body_line(block)
    if not title or not description:
        return None
    return {
        "title": title[:80],
        "description": description[:240],
        "event_count": _int_field(block, "事件数") or 1,
        "top_event_ids": _list_field(block, "Top Event IDs") or _list_field(block, "事件 IDs"),
        "symbols": _list_field(block, "关联标的") or _list_field(block, "symbols"),
        "confidence": _confidence_field(block, "置信度"),
    }


def _field_value(block: str, label: str) -> str:
    pattern = rf"(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*[：:]\s*(.+)"
    match = re.search(pattern, block, flags=re.IGNORECASE)
    return _clean_markdown(match.group(1)) if match else ""


def _first_body_line(block: str) -> str:
    lines = block.splitlines()[1:]
    field_pattern = r"^(描述|事件数|Top Event IDs|事件 IDs|关联标的|symbols|置信度)[：:]"
    for line in lines:
        cleaned = _clean_markdown(line)
        if cleaned and not re.match(field_pattern, cleaned, re.I):
            return cleaned
    return ""


def _int_field(block: str, label: str) -> int | None:
    value = _field_value(block, label)
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _list_field(block: str, label: str) -> list[str]:
    value = _field_value(block, label)
    if not value or value.lower() in {"none", "null", "无", "n/a"}:
        return []
    parts = re.split(r"[,，、\s]+", value)
    return [part.strip().strip("`$#") for part in parts if part.strip().strip("`$#")]


def _confidence_field(block: str, label: str) -> float:
    value = _field_value(block, label)
    if not value:
        return 0.5
    match = re.search(r"0(?:\.\d+)?|1(?:\.0+)?|\d{1,3}%", value)
    if match:
        raw = match.group(0)
        return max(0.0, min(1.0, float(raw.rstrip("%")) / (100.0 if raw.endswith("%") else 1.0)))
    lowered = value.lower()
    if any(token in lowered for token in ("高", "high")):
        return 0.85
    if any(token in lowered for token in ("低", "low")):
        return 0.35
    return 0.6


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _clean_markdown(value: str) -> str:
    cleaned = re.sub(r"^\s*[-*]\s*", "", value.strip())
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    return cleaned.strip(" \t\r\n-*：:")


def _trace_id(run_id: str) -> str:
    return "trace_" + hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:32]


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


__all__ = ["OpenAIAgentsWatchlistSummaryClient"]
