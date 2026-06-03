from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from parallax.domains.news_intel.types.news_item_brief import (
    DataGap,
    NewsItemBriefBasePacket,
    NewsItemBriefPayload,
)
from parallax.platform.agent_hashing import json_sha256

_ACTION_AUDIT_KEYS = frozenset({"tool_calls", "tools", "handoffs"})
_HOST_EVIDENCE_AUDIT_CONTAINERS = frozenset({"request_json", "research_execution", "research_plan", "tool_results"})


class NewsItemBriefValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publishable: bool
    status: str
    payload: dict[str, Any] | None = None
    errors: list[dict[str, str]] = Field(default_factory=list)
    output_hash: str | None = None


def validate_news_item_brief_output(
    *,
    payload: Any,
    packet: NewsItemBriefBasePacket,
    audit: Any,
) -> NewsItemBriefValidationResult:
    try:
        parsed = payload if isinstance(payload, NewsItemBriefPayload) else NewsItemBriefPayload.model_validate(payload)
    except ValidationError as exc:
        return _failed([_error("schema_invalid", _validation_message(exc))])

    errors: list[dict[str, str]] = []
    payload_dict = parsed.model_dump(mode="json")
    errors.extend(_unexpected_action_errors(audit))
    if parsed.confirmation_state == "multi_source_confirmed" and not _has_independent_source_confirmation(
        packet=packet,
        audit=audit,
    ):
        errors.append(_error("unsupported_confirmation_state", "multi_source_confirmed"))
    payload_dict = _drop_unsupported_assets(payload_dict, packet=packet, audit=audit)
    try:
        normalized = NewsItemBriefPayload.model_validate(payload_dict)
    except ValidationError as exc:
        errors.append(_error("schema_invalid", _validation_message(exc)))

    if errors:
        return _failed(errors)
    payload_dict = normalized.model_dump(mode="json")
    return NewsItemBriefValidationResult(
        publishable=True,
        status=normalized.status,
        payload=payload_dict,
        errors=[],
        output_hash=json_sha256(payload_dict),
    )


def _unexpected_action_errors(audit: Any) -> list[dict[str, str]]:
    audit_dict = _as_dict(audit)
    errors: list[dict[str, str]] = []
    for key, value in _walk_action_audit_items(audit_dict):
        if key in _ACTION_AUDIT_KEYS and _non_empty(value):
            errors.append(_error("unexpected_agent_action", key))
    return _dedupe_errors(errors)


def _has_independent_source_confirmation(*, packet: NewsItemBriefBasePacket, audit: Any) -> bool:
    source_domains = {
        _norm(domain)
        for domain in (packet.provider_signal_evidence.source_domains if packet.provider_signal_evidence else [])
        if _norm(domain)
    }
    if len(source_domains) > 1:
        return True
    for result in _tool_results(audit):
        if str(result.get("tool_name") or "") != "get_observation_history":
            continue
        domains = {
            _norm(row.get("source_domain"))
            for row in _result_rows(result)
            if _norm(row.get("source_domain")) and not _is_heuristic_row(row)
        }
        if len(domains) > 1:
            return True
    return False


def _drop_unsupported_assets(
    payload: dict[str, Any],
    *,
    packet: NewsItemBriefBasePacket,
    audit: Any,
) -> dict[str, Any]:
    supported = _source_backed_asset_labels(packet) | _exact_tool_asset_labels(audit)
    kept_assets: list[dict[str, Any]] = []
    dropped_symbols: list[str] = []
    for asset in payload.get("affected_assets") or []:
        labels = {
            _norm(asset.get("symbol")),
            _norm(asset.get("name")),
            _norm(asset.get("target_id")),
        }
        if any(label and label in supported for label in labels):
            kept_assets.append(asset)
            continue
        dropped_symbols.append(str(asset.get("symbol") or asset.get("name") or "unknown"))
    if not dropped_symbols:
        return payload
    normalized = dict(payload)
    normalized["affected_assets"] = kept_assets
    gaps = list(normalized.get("data_gaps") or [])
    gaps.extend(
        [
            DataGap(
                description_zh=f"模型提到的资产 {symbol} 未在输入 token、fact 或新闻文本中找到来源支撑。",
                severity="medium",
            ).model_dump(mode="json")
            for symbol in sorted(set(dropped_symbols))
        ]
    )
    normalized["data_gaps"] = gaps[:12]
    return normalized


def _exact_tool_asset_labels(audit: Any) -> set[str]:
    labels: set[str] = set()
    for result in _tool_results(audit):
        for row in _result_rows(result):
            if not _is_exact_tool_asset_row(row):
                continue
            labels.update(
                _norm(value)
                for value in (
                    row.get("symbol"),
                    row.get("display_symbol"),
                    row.get("target_id"),
                )
                if value
            )
            for target in _json_list(row.get("affected_targets")):
                if isinstance(target, Mapping):
                    labels.update(_norm(value) for value in target.values() if isinstance(value, str))
    return {label for label in labels if label}


def _is_exact_tool_asset_row(row: Mapping[str, Any]) -> bool:
    if _is_heuristic_row(row):
        return False
    matching_basis = _norm(row.get("matching_basis") or row.get("result_basis"))
    if matching_basis == "exact_target":
        return _confidence_is_exact(row.get("match_confidence"))
    if matching_basis == "fact_candidate":
        return True
    return bool(_json_list(row.get("affected_targets")))


def _is_heuristic_row(row: Mapping[str, Any]) -> bool:
    basis_values = {
        _norm(row.get("matching_basis")),
        _norm(row.get("result_basis")),
        _norm(row.get("match_confidence")),
    }
    return bool(basis_values & {"symbol_heuristic", "market_subject_heuristic", "heuristic"})


def _confidence_is_exact(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, int | float):
        return float(value) >= 0.8
    return _norm(value) in {"exact", "strong", "high", "known_symbol", "unique_by_context"}


def _tool_results(audit: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    audit_dict = _as_dict(audit)
    results.extend(_json_object_list(audit_dict.get("tool_results")))
    results.extend(_json_object_list(_as_dict(audit_dict.get("research_execution")).get("tool_results")))
    request_json = _as_dict(audit_dict.get("request_json"))
    results.extend(_json_object_list(request_json.get("tool_results")))
    results.extend(_json_object_list(_as_dict(request_json.get("research_execution")).get("tool_results")))
    trace_metadata = _as_dict(audit_dict.get("trace_metadata"))
    results.extend(_json_object_list(trace_metadata.get("tool_results")))
    results.extend(_json_object_list(_as_dict(trace_metadata.get("request_json")).get("tool_results")))
    for key, value in _walk_mapping_items(audit_dict):
        if key != "tool_results":
            continue
        results.extend(_json_object_list(value))
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for index, result in enumerate(results):
        key = (str(result.get("tool_call_id") or index), str(result.get("tool_name") or ""))
        deduped.setdefault(key, result)
    return list(deduped.values())


def _result_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _json_object_list(result.get("rows"))
    if rows:
        return rows
    payload = result.get("payload")
    if isinstance(payload, Mapping):
        nested_rows = _json_object_list(payload.get("rows"))
        if nested_rows:
            return nested_rows
        for key in ("top_items", "latest_items"):
            nested_rows.extend(_json_object_list(payload.get(key)))
        return nested_rows
    return []


def _source_backed_asset_labels(packet: NewsItemBriefBasePacket) -> set[str]:
    labels: set[str] = set()
    text_fields = [
        packet.news_item.title,
        packet.news_item.summary,
        packet.news_item.body_excerpt,
    ]
    labels.update(_norm(token) for field in text_fields for token in re.findall(r"[A-Za-z0-9]{2,20}", field or ""))
    for token in packet.token_lanes:
        labels.update(
            {
                _norm(token.observed_symbol),
                _norm(token.display_symbol),
                _norm(token.display_name),
                _norm(token.target_id),
            }
        )
    for fact in packet.fact_lanes:
        labels.update(_norm(token) for token in re.findall(r"[A-Za-z0-9]{2,20}", fact.claim or ""))
        for target in fact.affected_targets:
            labels.update(_norm(value) for value in target.values() if isinstance(value, str))
    return {label for label in labels if label}


def _walk_mapping_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            items.append((str(key), child))
            items.extend(_walk_mapping_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_walk_mapping_items(child))
    return items


def _walk_action_audit_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key)
            items.append((normalized_key, child))
            if normalized_key in _HOST_EVIDENCE_AUDIT_CONTAINERS:
                continue
            items.extend(_walk_action_audit_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_walk_action_audit_items(child))
    return items


def _json_object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, BaseModel):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, Mapping):
            rows.append({str(key): child for key, child in item.items()})
    return rows


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): child for key, child in value.items()}
    return {}


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if value == "":
        return False
    if isinstance(value, list | tuple | set | dict):
        return len(value) > 0
    return True


def _dedupe_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for error in errors:
        key = (error["code"], error["message"])
        if key in seen:
            continue
        seen.add(key)
        result.append(error)
    return result


def _failed(errors: list[dict[str, str]]) -> NewsItemBriefValidationResult:
    return NewsItemBriefValidationResult(
        publishable=False,
        status="failed",
        payload=None,
        errors=_dedupe_errors(errors),
        output_hash=None,
    )


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _validation_message(exc: ValidationError) -> str:
    messages = [str(error.get("loc", "")) + ": " + str(error.get("msg", "")) for error in exc.errors()]
    return "; ".join(messages)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = ["NewsItemBriefValidationResult", "validate_news_item_brief_output"]
