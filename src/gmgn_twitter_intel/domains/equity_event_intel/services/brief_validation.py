from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gmgn_twitter_intel.domains.equity_event_intel.types import EquityEventBriefInputPacket, EquityEventBriefPayload
from gmgn_twitter_intel.platform.agent_hashing import json_sha256

_FORBIDDEN_EXECUTION_RE = re.compile(
    r"(?:买入|卖出).{0,8}(?:股票|证券|合约|期权|期货|仓位|头寸)|"
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
        "ticker",
        "company_name",
        "impact_direction",
        "severity",
    }
)


class EquityEventBriefValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publishable: bool
    status: str
    payload: dict[str, Any] | None = None
    errors: list[dict[str, str]] = Field(default_factory=list)
    output_hash: str | None = None


def validate_equity_event_brief_output(
    *,
    payload: Any,
    packet: EquityEventBriefInputPacket,
    audit: Any,
) -> EquityEventBriefValidationResult:
    try:
        parsed = (
            payload if isinstance(payload, EquityEventBriefPayload) else EquityEventBriefPayload.model_validate(payload)
        )
    except ValidationError as exc:
        return _failed([_error("schema_invalid", _validation_message(exc))])

    payload_dict = parsed.model_dump(mode="json")
    errors: list[dict[str, str]] = []
    errors.extend(_unexpected_action_errors(audit))
    errors.extend(_unknown_evidence_ref_errors(payload_dict, packet=packet))
    if _contains_forbidden_execution_language(payload_dict):
        errors.append(_error("forbidden_execution_language", "natural-language output contains execution language"))
    errors.extend(_status_invariant_errors(parsed))
    errors.extend(_uncited_material_claim_errors(parsed))

    if errors:
        return _failed(errors)
    return EquityEventBriefValidationResult(
        publishable=True,
        status=parsed.status,
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
    packet: EquityEventBriefInputPacket,
) -> list[dict[str, str]]:
    allowed = set(packet.evidence_refs)
    refs = sorted({ref for ref in _walk_evidence_refs(payload) if ref not in allowed})
    return [_error("unknown_evidence_ref", ref) for ref in refs]


def _status_invariant_errors(payload: EquityEventBriefPayload) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if payload.status == "ready":
        if not payload.summary_zh.strip():
            errors.append(_error("ready_invariant", "ready requires summary_zh"))
        if not payload.event_read_zh.strip():
            errors.append(_error("ready_invariant", "ready requires event_read_zh"))
        if not payload.evidence_refs:
            errors.append(_error("ready_invariant", "ready requires top-level evidence_refs"))
        for side_name, side in (("bull_view", payload.bull_view), ("bear_view", payload.bear_view)):
            if side.strength == "absent":
                continue
            if not side.thesis_zh.strip():
                errors.append(_error("ready_invariant", f"{side_name} with strength requires thesis_zh"))
            if not side.evidence_refs:
                errors.append(_error("ready_invariant", f"{side_name} with strength requires evidence_refs"))
    if payload.status == "insufficient" and not payload.data_gaps:
        errors.append(_error("insufficient_invariant", "insufficient requires data_gaps"))
    return errors


def _uncited_material_claim_errors(payload: EquityEventBriefPayload) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if payload.status != "ready":
        return errors
    if _material_text(payload.summary_zh) and not payload.evidence_refs:
        errors.append(_error("uncited_material_claim", "summary_zh requires evidence_refs"))
    if _material_text(payload.event_read_zh) and not payload.evidence_refs:
        errors.append(_error("uncited_material_claim", "event_read_zh requires evidence_refs"))
    for side_name, side in (("bull_view", payload.bull_view), ("bear_view", payload.bear_view)):
        if _material_text(side.thesis_zh) and side.strength != "absent" and not side.evidence_refs:
            errors.append(_error("uncited_material_claim", f"{side_name}.thesis_zh requires evidence_refs"))
    for index, impact in enumerate(payload.company_impacts):
        if _material_text(impact.reason_zh) and not impact.evidence_refs:
            errors.append(
                _error("uncited_material_claim", f"company_impacts[{index}].reason_zh requires evidence_refs")
            )
    return errors


def _material_text(value: str) -> bool:
    return bool(value.strip())


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


def _contains_forbidden_execution_language(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _NON_NATURAL_KEYS:
                continue
            if _contains_forbidden_execution_language(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_execution_language(child) for child in value)
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
    if isinstance(value, Mapping | list | tuple | set):
        return bool(value)
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


def _failed(errors: list[dict[str, str]]) -> EquityEventBriefValidationResult:
    return EquityEventBriefValidationResult(publishable=False, status="failed", payload=None, errors=errors)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": str(message)[:500]}


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())[:500]


__all__ = ["EquityEventBriefValidationResult", "validate_equity_event_brief_output"]
