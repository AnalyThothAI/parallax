from __future__ import annotations

import json
import re
from typing import Any

from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_runtime import (
    build_handle_summary_stage,
)
from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import HANDLE_SUMMARY_PAYLOAD_TYPE


class OpenAIAgentsWatchlistSummaryClient:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        agent_gateway: Any,
        max_turns: int = 1,
    ) -> None:
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("watchlist_handle_summary_model is required")
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway
        self.max_turns = max(1, min(2, int(max_turns)))

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
        stage = build_handle_summary_stage(
            model=self.model,
            handle=handle,
            events=events,
            run_id=run_id,
            job=job,
            context=context,
            max_turns=self.max_turns,
        )
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def summarize_handle(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        stage = build_handle_summary_stage(
            model=self.model,
            handle=handle,
            events=events,
            run_id=run_id,
            job=job,
            context=context,
            max_turns=self.max_turns,
        )
        execution = await self._agent_gateway.execute(stage)
        payload = _coerce_summary_payload(execution.final_output)
        output_json = payload.model_dump(mode="json")
        return {
            **output_json,
            "agent_run_audit": execution.audit.model_dump(mode="json"),
        }

    async def aclose(self) -> None:
        return None


def _coerce_summary_payload(value: Any) -> Any:
    if isinstance(value, HANDLE_SUMMARY_PAYLOAD_TYPE):
        return value
    if isinstance(value, dict):
        if "summary_zh" not in value and _looks_like_topic(value):
            value = _payload_from_topics([value])
        return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(value)
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(_payload_from_topics(value))
    if isinstance(value, str):
        text = value.strip()
        parsed = _parse_json_object(text)
        if parsed is not None:
            if "summary_zh" not in parsed and _looks_like_topic(parsed):
                parsed = _payload_from_topics([parsed])
            return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(parsed)
        parsed_list = _parse_json_list(text)
        if parsed_list is not None:
            return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(_payload_from_topics(parsed_list))
        markdown_payload = _parse_markdown_summary(text)
        if markdown_payload is not None:
            return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(markdown_payload)
    return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(value)


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


__all__ = ["OpenAIAgentsWatchlistSummaryClient"]
