from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from parallax.domains.news_intel.services.news_item_brief_entity_support import (
    NewsBriefValidationPacket,
    validate_affected_entity_support,
)
from parallax.domains.news_intel.types.news_item_brief import (
    DataGap,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
)
from parallax.domains.news_intel.types.news_story_brief import NewsStoryBriefInputPacket
from parallax.platform.agent_hashing import json_sha256

_ACTION_AUDIT_KEYS = frozenset({"tool_calls", "tools", "handoffs"})
_TRADING_INSTRUCTION_PATTERNS = (
    re.compile(r"(?:建议|推荐|可以|应当|应该|适合).{0,16}(?:买入|卖出|开仓|平仓|做多|做空|加仓|减仓|止损|止盈|杠杆)"),
    re.compile(r"(?:买入|卖出|开仓|平仓|做多|做空).{0,12}(?:止损|止盈|杠杆|仓位)"),
    re.compile(r"\b(?:long|short|buy|sell)\s+(?:this|it)\b", re.I),
    re.compile(r"\b(?:long|short|buy|sell)\s+[A-Z0-9]{2,10}\b"),
    re.compile(r"\b(?:open|close)\s+(?:a\s+)?(?:long|short|position|trade|order)\b", re.I),
    re.compile(r"\bposition\s+size\b", re.I),
    re.compile(r"\btarget\s+price\b", re.I),
    re.compile(r"\bstop[-\s]?loss\b", re.I),
    re.compile(r"\btake[-\s]?profit\b", re.I),
    re.compile(r"\b(?:use\s+a\s+)?\d+x\s+leverage(?:\s+order)?\b", re.I),
    re.compile(r"\bleverage\s+order\b", re.I),
)


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
    packet: NewsBriefValidationPacket,
    audit: Any,
) -> NewsItemBriefValidationResult:
    try:
        parsed = payload if isinstance(payload, NewsItemBriefPayload) else NewsItemBriefPayload.model_validate(payload)
    except ValidationError as exc:
        return _failed([_error("schema_invalid", _validation_message(exc))])

    errors: list[dict[str, str]] = []
    payload_dict = parsed.model_dump(mode="json")
    errors.extend(_unexpected_action_errors(audit))
    payload_dict = _drop_unsupported_market_impacts(payload_dict, packet=packet)
    errors.extend(_evidence_ref_errors(payload_dict, packet=packet))
    errors.extend(_ready_evidence_errors(payload_dict, packet=packet))
    errors.extend(_ready_publishable_text_errors(payload_dict))
    errors.extend(_ready_market_structure_errors(payload_dict, packet=packet))
    errors.extend(_unsupported_entity_errors(payload_dict, packet=packet))
    errors.extend(_trading_instruction_errors(payload_dict))
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
    for key, value in _walk_mapping_items(audit_dict):
        if key in _ACTION_AUDIT_KEYS and _non_empty(value):
            errors.append(_error("unexpected_agent_action", key))
    return _dedupe_errors(errors)


def _evidence_ref_errors(payload: dict[str, Any], *, packet: NewsBriefValidationPacket) -> list[dict[str, str]]:
    allowed = set(packet.evidence_refs)
    return [
        _error("unknown_evidence_ref", ref) for ref in sorted(_evidence_refs_in_payload(payload)) if ref not in allowed
    ]


def _ready_evidence_errors(payload: dict[str, Any], *, packet: NewsBriefValidationPacket) -> list[dict[str, str]]:
    if payload.get("status") != "ready":
        return []
    allowed = set(packet.evidence_refs)
    if any(ref in allowed for ref in _evidence_refs_in_payload(payload)):
        return []
    return [_error("missing_ready_evidence_ref", "ready output requires at least one valid evidence ref")]


def _ready_publishable_text_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    if payload.get("status") != "ready":
        return []
    summary = payload.get("summary_zh")
    if isinstance(summary, str) and summary.strip():
        return []
    return [_error("missing_publishable_text", "ready output requires summary_zh")]


def _ready_market_structure_errors(
    payload: dict[str, Any],
    *,
    packet: NewsBriefValidationPacket,
) -> list[dict[str, str]]:
    if payload.get("status") != "ready":
        return []
    if payload.get("decision_class") not in {"driver", "watch"}:
        return []
    errors: list[dict[str, str]] = []
    if not _non_empty(payload.get("market_domains")):
        errors.append(_error("missing_market_domains", "ready driver/watch output requires market_domains"))
    paths = [path for path in payload.get("transmission_paths") or [] if isinstance(path, Mapping)]
    if not paths:
        errors.append(
            _error("missing_transmission_path", "ready driver/watch output requires a source-backed transmission path")
        )
        return errors
    allowed = set(packet.evidence_refs)
    if not any(ref in allowed for path in paths for ref in _refs_from_mapping(path)):
        errors.append(
            _error(
                "missing_transmission_path_evidence",
                "ready driver/watch transmission path requires at least one valid evidence ref",
            )
        )
    return errors


def _drop_unsupported_market_impacts(payload: dict[str, Any], *, packet: NewsBriefValidationPacket) -> dict[str, Any]:
    supported = _source_backed_market_labels(packet)
    kept_impacts: list[dict[str, Any]] = []
    dropped_labels: list[str] = []
    for impact in payload.get("market_impacts") or []:
        if not isinstance(impact, Mapping):
            continue
        labels = {
            _norm(impact.get("label")),
            _norm(impact.get("target_id")),
        }
        if any(label and label in supported for label in labels):
            kept_impacts.append(dict(impact))
            continue
        dropped_labels.append(str(impact.get("label") or "unknown"))
    if not dropped_labels:
        return payload
    normalized = dict(payload)
    normalized["market_impacts"] = kept_impacts
    gaps = list(normalized.get("data_gaps") or [])
    gaps.extend(
        [
            DataGap(
                description_zh=f"模型提到的市场影响对象 {label} 未在输入 entity、fact 或新闻文本中找到来源支撑。",
                severity="medium",
            ).model_dump(mode="json")
            for label in sorted(set(dropped_labels))
        ]
    )
    normalized["data_gaps"] = gaps[:12]
    return normalized


def _source_backed_market_labels(packet: NewsBriefValidationPacket) -> set[str]:
    labels: set[str] = set()
    news_item = _packet_news_item(packet)
    text_fields = [
        news_item.title,
        news_item.summary,
        news_item.body_excerpt,
    ]
    labels.update(_norm(token) for field in text_fields for token in re.findall(r"[A-Za-z0-9]{2,20}", field or ""))
    for entity in packet.entity_lanes:
        labels.update(
            {
                _norm(entity.observed_label),
                _norm(entity.display_symbol),
                _norm(entity.display_name),
                _norm(entity.target_id),
            }
        )
    for fact in packet.fact_lanes:
        labels.update(_norm(token) for token in re.findall(r"[A-Za-z0-9]{2,20}", fact.claim or ""))
        for target in fact.affected_targets:
            labels.update(_norm(value) for value in target.values() if isinstance(value, str))
    return {label for label in labels if label}


def _unsupported_entity_errors(payload: dict[str, Any], *, packet: NewsBriefValidationPacket) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for entity in payload.get("affected_entities") or []:
        if not isinstance(entity, Mapping):
            continue
        decision = validate_affected_entity_support(entity, packet=packet, payload=payload)
        if decision.supported:
            continue
        errors.append(_error("unsupported_entity", str(entity.get("label") or entity.get("symbol") or "unknown")))
    return errors


def _packet_news_item(packet: NewsBriefValidationPacket) -> NewsItemBriefNewsItem:
    if isinstance(packet, NewsItemBriefInputPacket):
        return packet.news_item
    if isinstance(packet, NewsStoryBriefInputPacket):
        return packet.representative_item
    raise TypeError("news_brief_validation_packet_invalid")


def _trading_instruction_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    for text in _strings_in_payload(payload):
        if any(pattern.search(text) for pattern in _TRADING_INSTRUCTION_PATTERNS):
            return [_error("trading_instruction", "output contains prescriptive trading or execution language")]
    return []


def _evidence_refs_in_payload(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "evidence_refs" and isinstance(child, list):
                refs.update(str(ref) for ref in child if str(ref or ""))
            else:
                refs.update(_evidence_refs_in_payload(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_evidence_refs_in_payload(child))
    return refs


def _refs_from_mapping(value: Mapping[str, Any]) -> set[str]:
    refs = value.get("evidence_refs")
    if not isinstance(refs, list):
        return set()
    return {str(ref) for ref in refs if str(ref or "")}


def _strings_in_payload(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        texts: list[str] = []
        for child in value.values():
            texts.extend(_strings_in_payload(child))
        return texts
    if isinstance(value, list):
        list_texts: list[str] = []
        for child in value:
            list_texts.extend(_strings_in_payload(child))
        return list_texts
    return []


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
