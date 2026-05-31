from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from parallax.domains.news_intel.types.news_item_brief import (
    DataGap,
    NewsItemBriefInputPacket,
    NewsItemBriefPayload,
)
from parallax.platform.agent_hashing import json_sha256

_FORBIDDEN_EXECUTION_RE = re.compile(
    r"(?:建议|可以|应当|应该|立刻|马上|直接)(?:买入|卖出|加仓|减仓)|"
    r"(?:买入|卖出|加仓|减仓)(?:建议|计划|指令|点位)|"
    r"开仓|做多|做空|仓位|杠杆|目标价|止损|止盈|配仓|"
    r"\b(?:buy|sell|leverage|order\s+instructions?|position\s+(?:size|sizing)|"
    r"execution\s+permission|portfolio\s+(?:advice|allocation)|"
    r"stop[-\s]+loss|take[-\s]+profit|target\s+prices?)\b|"
    r"\b(?:go|enter|open)\s+(?:long|short)\b|"
    r"\b(?:long|short)\s+position\b",
    re.IGNORECASE,
)

_ACTION_AUDIT_KEYS = frozenset({"tool_calls", "tools", "handoffs"})
_NON_NATURAL_KEYS = frozenset(
    {
        "status",
        "direction",
        "decision_class",
        "strength",
        "evidence_refs",
        "symbol",
        "name",
        "resolution_status",
        "target_type",
        "target_id",
        "impact_direction",
        "severity",
    }
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
    packet: NewsItemBriefInputPacket,
    audit: Any,
) -> NewsItemBriefValidationResult:
    try:
        parsed = payload if isinstance(payload, NewsItemBriefPayload) else NewsItemBriefPayload.model_validate(payload)
    except ValidationError as exc:
        return _failed([_error("schema_invalid", _validation_message(exc))])

    errors: list[dict[str, str]] = []
    payload_dict = parsed.model_dump(mode="json")
    errors.extend(_unexpected_action_errors(audit))
    errors.extend(_unknown_evidence_ref_errors(payload_dict, packet=packet))
    if _contains_forbidden_execution_language(payload_dict):
        errors.append(_error("forbidden_execution_language", "natural-language output contains execution language"))
    errors.extend(_status_invariant_errors(parsed))
    payload_dict = _drop_unsupported_assets(payload_dict, packet=packet)
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


def _unknown_evidence_ref_errors(
    payload: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
) -> list[dict[str, str]]:
    allowed = set(packet.evidence_refs)
    refs = sorted({ref for ref in _walk_evidence_refs(payload) if ref not in allowed})
    return [_error("unknown_evidence_ref", ref) for ref in refs]


def _status_invariant_errors(payload: NewsItemBriefPayload) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if payload.status == "ready":
        if not payload.title_zh.strip():
            errors.append(_error("ready_invariant", "ready requires title_zh"))
        if not payload.summary_zh.strip():
            errors.append(_error("ready_invariant", "ready requires summary_zh"))
        if not payload.evidence_refs:
            errors.append(_error("ready_invariant", "ready requires top-level evidence_refs"))
        side_errors = [
            message
            for side_name, side in (("bull_view", payload.bull_view), ("bear_view", payload.bear_view))
            for message in _side_invariant_errors(side_name, side)
        ]
        errors.extend(_error("ready_invariant", message) for message in side_errors)
        has_side = _is_complete_side(payload.bull_view) or _is_complete_side(payload.bear_view)
        if payload.direction != "neutral" and not has_side:
            errors.append(
                _error(
                    "ready_invariant",
                    "ready requires at least one complete bull or bear side unless neutral",
                )
            )
    if payload.status == "insufficient" and not payload.data_gaps:
        errors.append(_error("insufficient_invariant", "insufficient requires data_gaps"))
    return errors


def _side_invariant_errors(side_name: str, side: Any) -> list[str]:
    if side.strength == "absent":
        return []
    errors: list[str] = []
    if not side.thesis_zh.strip():
        errors.append(f"{side_name} with strength requires thesis_zh")
    if not side.evidence_refs:
        errors.append(f"{side_name} with strength requires evidence_refs")
    return errors


def _is_complete_side(side: Any) -> bool:
    return side.strength != "absent" and bool(side.thesis_zh.strip()) and bool(side.evidence_refs)


def _drop_unsupported_assets(payload: dict[str, Any], *, packet: NewsItemBriefInputPacket) -> dict[str, Any]:
    supported = _source_backed_asset_labels(packet)
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
    normalized["data_gaps"] = gaps
    return normalized


def _source_backed_asset_labels(packet: NewsItemBriefInputPacket) -> set[str]:
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


def _walk_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "evidence_refs" and isinstance(child, list):
                refs.extend(str(item).strip() for item in child if str(item).strip())
                continue
            refs.extend(_walk_evidence_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_walk_evidence_refs(child))
    return refs


def _contains_forbidden_execution_language(value: Any, *, parent_key: str = "") -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _NON_NATURAL_KEYS:
                continue
            if _contains_forbidden_execution_language(child, parent_key=str(key)):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_execution_language(child, parent_key=parent_key) for child in value)
    if isinstance(value, str):
        return bool(_FORBIDDEN_EXECUTION_RE.search(value))
    return False


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
