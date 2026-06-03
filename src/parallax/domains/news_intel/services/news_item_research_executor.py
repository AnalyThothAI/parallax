from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from parallax.domains.news_intel.services.news_item_research_tools import (
    NewsResearchToolDefinition,
    build_news_research_tool_registry,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefBasePacket,
    NewsItemResearchPlan,
    NewsItemResearchToolCall,
    NewsResearchToolResult,
    news_research_tool_material_hash,
)

NEWS_RESEARCH_TOOL_RESULT_SCHEMA_VERSION = "news_research_tool_result_v1"
NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS = 3_000
NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS = 6_000
NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS = 5
NEWS_RESEARCH_EXECUTOR_MAX_ARCHIVE_SEARCHES = 2

ExecutionStatus = Literal["ok", "partial", "failed", "skipped"]

_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "provider_item_id",
        "raw_payload_json",
        "provider_article_key",
        "provider_article_keys",
        "feed_url",
        "sync_cursor",
        "credential",
        "credentials",
        "secret",
        "token",
        "password",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth_token",
    }
)
_SENSITIVE_KEY_PARTS = ("secret", "password", "api_key", "apikey", "credential")


class NewsResearchPlanExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExecutionStatus
    tool_results: list[NewsResearchToolResult] = Field(default_factory=list, max_length=5)
    error_codes: list[str] = Field(default_factory=list, max_length=20)
    material_chars: int = Field(default=0, ge=0)
    material_budget_chars: int = Field(default=NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS, ge=0)
    hard_material_budget_chars: int = Field(default=NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS, ge=0)
    truncated: bool = False
    skipped_call_count: int = Field(default=0, ge=0)
    executed_call_count: int = Field(default=0, ge=0)


def execute_news_research_plan(
    news_repo: Any,
    plan: NewsItemResearchPlan,
    *,
    base_packet: NewsItemBriefBasePacket | None = None,
    now_ms: int | None = None,
) -> NewsResearchPlanExecutionResult:
    generated_at_ms = _now_ms() if now_ms is None else int(now_ms)
    registry = build_news_research_tool_registry()
    tool_results: list[NewsResearchToolResult] = []
    error_codes: list[str] = []
    skipped_call_count = 0
    executed_call_count = 0
    material_chars = 0
    total_truncated = False
    archive_search_count = 0
    calls = list(plan.tool_calls)

    if plan.status == "skip":
        return NewsResearchPlanExecutionResult(
            status="skipped",
            tool_results=[],
            error_codes=[],
            material_chars=0,
            skipped_call_count=len(calls),
            executed_call_count=0,
        )

    for index, call in enumerate(calls):
        if len(tool_results) >= NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS:
            skipped_call_count += len(calls) - index
            _add_error(error_codes, "max_tool_calls_exceeded")
            break

        tool = registry.get(call.tool_name)
        if tool is None:
            skipped_call_count += 1
            _add_error(error_codes, "unknown_tool")
            tool_results.append(
                _failed_tool_result(
                    call=call,
                    query_version="unknown_tool_v1",
                    source_tables=[],
                    input_payload=_safe_input(call.input),
                    error_code="unknown_tool",
                    generated_at_ms=generated_at_ms,
                )
            )
            continue

        if call.tool_name == "search_news_archive":
            archive_search_count += 1
            if archive_search_count > NEWS_RESEARCH_EXECUTOR_MAX_ARCHIVE_SEARCHES:
                skipped_call_count += 1
                _add_error(error_codes, "max_archive_searches_exceeded")
                tool_results.append(
                    _failed_tool_result(
                        call=call,
                        query_version=tool.query_version,
                        source_tables=tool.source_tables,
                        input_payload=_clamp_input(tool=tool, call_input=call.input),
                        error_code="max_archive_searches_exceeded",
                        generated_at_ms=generated_at_ms,
                    )
                )
                continue

        clamped_input = _clamp_input(tool=tool, call_input=call.input)
        if tool.requires_allowed_context_target:
            allowed_error = _allowed_target_error(clamped_input, base_packet=base_packet)
            if allowed_error is not None:
                skipped_call_count += 1
                _add_error(error_codes, allowed_error)
                tool_results.append(
                    _failed_tool_result(
                        call=call,
                        query_version=tool.query_version,
                        source_tables=tool.source_tables,
                        input_payload=clamped_input,
                        error_code=allowed_error,
                        generated_at_ms=generated_at_ms,
                    )
                )
                continue

        started_ms = _now_ms()
        try:
            rows = getattr(news_repo, tool.handler_name)(**clamped_input)
            executed_call_count += 1
        except Exception:
            skipped_call_count += 1
            _add_error(error_codes, "repo_exception")
            tool_results.append(
                _failed_tool_result(
                    call=call,
                    query_version=tool.query_version,
                    source_tables=tool.source_tables,
                    input_payload=clamped_input,
                    error_code="repo_exception",
                    generated_at_ms=generated_at_ms,
                    latency_ms=max(0, _now_ms() - started_ms),
                )
            )
            continue

        result, row_chars = _successful_tool_result(
            call=call,
            tool=tool,
            input_payload=clamped_input,
            rows=rows,
            generated_at_ms=generated_at_ms,
            latency_ms=max(0, _now_ms() - started_ms),
            remaining_chars=max(0, NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS - material_chars),
        )
        material_chars += row_chars
        if result.truncated:
            total_truncated = True
        tool_results.append(result)

    status = _execution_status(tool_results=tool_results, error_codes=error_codes)
    return NewsResearchPlanExecutionResult(
        status=status,
        tool_results=tool_results,
        error_codes=error_codes,
        material_chars=material_chars,
        truncated=total_truncated or material_chars > NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS,
        skipped_call_count=skipped_call_count,
        executed_call_count=executed_call_count,
    )


def _successful_tool_result(
    *,
    call: NewsItemResearchToolCall,
    tool: NewsResearchToolDefinition,
    input_payload: dict[str, Any],
    rows: Any,
    generated_at_ms: int,
    latency_ms: int,
    remaining_chars: int,
) -> tuple[NewsResearchToolResult, int]:
    redaction_notes: list[str] = []
    clean_rows = _redacted_rows(rows, redaction_notes=redaction_notes)
    clean_rows = _label_symbol_fallback_rows(tool=tool, input_payload=input_payload, rows=clean_rows)
    compact_rows, truncated, row_chars = _compact_rows(
        clean_rows,
        max_rows=tool.max_rows,
        max_chars=min(tool.max_chars, max(0, remaining_chars)),
    )
    status = "empty" if not compact_rows else "truncated" if truncated else "ok"
    result = NewsResearchToolResult(
        tool_call_id=call.tool_call_id,
        tool_name=call.tool_name,
        status=status,
        schema_version=NEWS_RESEARCH_TOOL_RESULT_SCHEMA_VERSION,
        query_version=tool.query_version,
        source_tables=tool.source_tables,
        input=input_payload,
        rows=compact_rows,
        row_count=len(compact_rows),
        truncated=truncated,
        skipped_reason="",
        result_hash="",
        generated_at_ms=generated_at_ms,
        latency_ms=latency_ms,
        redaction_notes=redaction_notes[:20],
        evidence_refs=_evidence_refs(compact_rows),
    )
    return result.model_copy(update={"result_hash": news_research_tool_material_hash(result)}), row_chars


def _failed_tool_result(
    *,
    call: NewsItemResearchToolCall,
    query_version: str,
    source_tables: list[str],
    input_payload: dict[str, Any],
    error_code: str,
    generated_at_ms: int,
    latency_ms: int = 0,
) -> NewsResearchToolResult:
    result = NewsResearchToolResult(
        tool_call_id=call.tool_call_id,
        tool_name=call.tool_name,
        status="failed",
        schema_version=NEWS_RESEARCH_TOOL_RESULT_SCHEMA_VERSION,
        query_version=query_version,
        source_tables=source_tables,
        input=input_payload,
        rows=[],
        row_count=0,
        truncated=False,
        skipped_reason=error_code,
        result_hash="",
        generated_at_ms=generated_at_ms,
        latency_ms=latency_ms,
        redaction_notes=[],
        evidence_refs=[],
    )
    return result.model_copy(update={"result_hash": news_research_tool_material_hash(result)})


def _clamp_input(*, tool: NewsResearchToolDefinition, call_input: Mapping[str, Any]) -> dict[str, Any]:
    if tool.name == "search_news_archive":
        return {
            "query_terms": _bounded_strings(call_input.get("query_terms"), max_items=5),
            "symbols": _bounded_strings(call_input.get("symbols"), max_items=5),
            "window_hours": _bounded_int(call_input.get("window_hours"), default=168, max_value=168),
            "limit": _bounded_int(call_input.get("limit"), default=8, max_value=8),
        }
    if tool.name == "get_target_news_context":
        return {
            "target_refs": _bounded_target_refs(call_input.get("target_refs"), max_items=5),
            "symbol_fallbacks": _bounded_strings(call_input.get("symbol_fallbacks"), max_items=3),
            "window_hours": _bounded_int(call_input.get("window_hours"), default=72, max_value=168),
            "limit": _bounded_int(call_input.get("limit"), default=12, max_value=12),
        }
    if tool.name == "get_fact_context":
        return {"limit": _bounded_int(call_input.get("limit"), default=20, max_value=20)}
    if tool.name == "get_observation_history":
        return {"limit": _bounded_int(call_input.get("limit"), default=25, max_value=25)}
    return {}


def _allowed_target_error(
    input_payload: Mapping[str, Any],
    *,
    base_packet: NewsItemBriefBasePacket | None,
) -> str | None:
    target_refs = input_payload.get("target_refs")
    if not target_refs:
        return None
    if base_packet is None:
        return "target_ref_not_allowed"
    allowed = {(target.target_type, target.target_id) for target in base_packet.allowed_context_targets}
    for ref in target_refs:
        if (str(ref.get("target_type") or ""), str(ref.get("target_id") or "")) not in allowed:
            return "target_ref_not_allowed"
    return None


def _bounded_int(value: Any, *, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(max_value, parsed))


def _bounded_strings(value: Any, *, max_items: int) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _bounded_target_refs(value: Any, *, max_items: int) -> list[dict[str, str]]:
    if not isinstance(value, list | tuple):
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        target_type = str(item.get("target_type") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        if not target_type or not target_id or (target_type, target_id) in seen:
            continue
        seen.add((target_type, target_id))
        refs.append({"target_type": target_type, "target_id": target_id})
        if len(refs) >= max_items:
            break
    return refs


def _redacted_rows(rows: Any, *, redaction_notes: list[str]) -> list[dict[str, Any]]:
    if not isinstance(rows, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        redacted = _redact_mapping(row, path="", redaction_notes=redaction_notes)
        if redacted:
            result.append(redacted)
    return result


def _redact_mapping(value: Mapping[str, Any], *, path: str, redaction_notes: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in value.items():
        key_text = str(key)
        child_path = f"{path}.{key_text}" if path else key_text
        if _is_sensitive_key(key_text):
            _note_redaction(redaction_notes, child_path)
            continue
        redacted_child = _redact_value(child, path=child_path, redaction_notes=redaction_notes)
        if redacted_child is not None:
            result[key_text] = redacted_child
    return result


def _redact_value(value: Any, *, path: str, redaction_notes: list[str]) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value, path=path, redaction_notes=redaction_notes)
    if isinstance(value, list):
        clean_items = [_redact_value(item, path=path, redaction_notes=redaction_notes) for item in value]
        return [item for item in clean_items if item is not None]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _SENSITIVE_EXACT_KEYS or any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _note_redaction(redaction_notes: list[str], path: str) -> None:
    note = f"redacted:{path}"
    if note not in redaction_notes:
        redaction_notes.append(note)


def _label_symbol_fallback_rows(
    *,
    tool: NewsResearchToolDefinition,
    input_payload: Mapping[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if tool.name != "get_target_news_context" or not input_payload.get("symbol_fallbacks"):
        return rows
    for row in rows:
        if row.get("target_id") or row.get("target_ref"):
            continue
        if row.get("result_basis") in {None, ""}:
            row["result_basis"] = "symbol_heuristic"
    return rows


def _compact_rows(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    compact: list[dict[str, Any]] = []
    used_chars = 0
    truncated = len(rows) > max_rows
    for row in rows[:max_rows]:
        row_chars = _json_len(row)
        if used_chars + row_chars > max_chars:
            truncated = True
            break
        compact.append(row)
        used_chars += row_chars
    return compact, truncated, used_chars


def _json_len(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _evidence_refs(rows: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for row in rows:
        for key in ("evidence_ref", "evidence_refs"):
            value = row.get(key)
            if isinstance(value, str) and value.strip() and value not in refs:
                refs.append(value)
            elif isinstance(value, list):
                refs.extend(str(item) for item in value if str(item or "").strip() and str(item) not in refs)
    return refs[:80]


def _safe_input(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _execution_status(*, tool_results: list[NewsResearchToolResult], error_codes: list[str]) -> ExecutionStatus:
    if not tool_results:
        return "failed" if error_codes else "skipped"
    failed_count = sum(1 for result in tool_results if result.status == "failed")
    if failed_count == len(tool_results):
        return "failed"
    if failed_count or error_codes:
        return "partial"
    return "ok"


def _add_error(error_codes: list[str], error_code: str) -> None:
    if error_code not in error_codes:
        error_codes.append(error_code)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS",
    "NEWS_RESEARCH_EXECUTOR_MAX_ARCHIVE_SEARCHES",
    "NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS",
    "NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS",
    "NewsResearchPlanExecutionResult",
    "execute_news_research_plan",
]
