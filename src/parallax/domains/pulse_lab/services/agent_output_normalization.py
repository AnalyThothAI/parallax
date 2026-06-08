from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import FinalDecision


@dataclass(frozen=True, slots=True)
class PulseStageOutputNormalization:
    payload: Any
    trace_metadata: dict[str, Any]


def normalize_pulse_stage_output(
    *,
    output_type: type[Any],
    raw_output: Any,
    evidence_packet: Any,
) -> PulseStageOutputNormalization:
    if not isinstance(raw_output, dict):
        return PulseStageOutputNormalization(payload=raw_output, trace_metadata={})

    payload = deepcopy(raw_output)
    trace_metadata: dict[str, Any] = {}

    if output_type is FinalDecision:
        schema_repairs = _normalize_final_decision_schema(payload)
        if schema_repairs:
            trace_metadata["schema_normalization"] = {"repairs": schema_repairs}

    policy_repairs = _normalize_policy_text(payload, output_type=output_type)
    if policy_repairs:
        trace_metadata["policy_text_normalization"] = {"repairs": policy_repairs}

    if output_type is FinalDecision:
        event_id_repairs = _normalize_final_event_ids(payload, evidence_packet=evidence_packet)
        if event_id_repairs:
            trace_metadata["event_id_normalization"] = {"repairs": event_id_repairs}

    return PulseStageOutputNormalization(payload=payload, trace_metadata=trace_metadata)


def _normalize_final_decision_schema(payload: dict[str, Any]) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    recommendation = _string_value(payload.get("recommendation"))

    playbook = payload.get("playbook")
    if recommendation == "abstain" and not isinstance(playbook, dict):
        payload["playbook"] = {
            "has_playbook": False,
            "watch_signals": [],
            "exit_triggers": [],
            "monitoring_horizon": "1h",
        }
        return [{"path": "playbook", "action": "inserted_empty", "reason": "abstain_missing_playbook"}]

    if not isinstance(playbook, dict) or playbook.get("has_playbook") is not False:
        return repairs

    for field_name in ("watch_signals", "exit_triggers"):
        values = playbook.get(field_name)
        if isinstance(values, list | tuple) and values:
            playbook[field_name] = []
            repairs.append(
                {
                    "path": f"playbook.{field_name}",
                    "action": "cleared",
                    "reason": "playbook_has_playbook_false",
                }
            )
    return repairs


_EXECUTION_TEXT_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile("买入"), "买盘"),
    (re.compile("卖出"), "卖压"),
    (re.compile("开仓"), "交易动作"),
    (re.compile("做多"), "看多表达"),
    (re.compile("做空"), "看空表达"),
    (re.compile("仓位"), "敞口"),
    (re.compile("杠杆"), "借贷放大"),
    (re.compile("目标价"), "价格区间"),
    (re.compile("止损"), "风险退出"),
    (re.compile("止盈"), "收益退出"),
    (re.compile(r"\bbuy\b", re.IGNORECASE), "demand"),
    (re.compile(r"\bsell\b", re.IGNORECASE), "supply"),
    (re.compile(r"\bleverage\b", re.IGNORECASE), "borrowed exposure"),
    (re.compile(r"\bposition\s+sizing?\b", re.IGNORECASE), "exposure sizing"),
    (re.compile(r"\bstop[-\s]+loss\b", re.IGNORECASE), "risk exit"),
    (re.compile(r"\btake[-\s]+profit\b", re.IGNORECASE), "profit exit"),
    (re.compile(r"\btarget\s+price\b", re.IGNORECASE), "price range"),
    (re.compile(r"\b(?:go|enter|open)\s+(?:long|short)\b", re.IGNORECASE), "directional expression"),
    (re.compile(r"\b(?:long|short)\s+position\b", re.IGNORECASE), "directional exposure"),
)

_REFISH_KEYS = {
    "evidence_refs",
    "allowed_evidence_ref_ids",
    "supporting_evidence_refs",
    "risk_evidence_refs",
    "data_gap_refs",
    "evidence_event_ids",
    "supporting_event_ids",
    "evidence_event_urls",
}


def _normalize_policy_text(payload: dict[str, Any], *, output_type: type[Any]) -> list[dict[str, Any]]:
    if output_type is not FinalDecision:
        return []
    repairs: list[dict[str, Any]] = []

    def visit(value: Any, path: str, parent_key: str | None = None) -> Any:
        if parent_key in _REFISH_KEYS:
            return value
        if isinstance(value, str):
            cleaned = _neutralize_execution_language(value)
            if cleaned != value:
                repairs.append({"path": path, "action": "neutralized_execution_language"})
            return cleaned
        if isinstance(value, list):
            for index, item in enumerate(value):
                value[index] = visit(item, f"{path}[{index}]", parent_key=None)
            return value
        if isinstance(value, dict):
            for key, item in list(value.items()):
                value[key] = visit(item, f"{path}.{key}" if path else str(key), parent_key=str(key))
            return value
        return value

    visit(payload, "")
    return repairs


def _neutralize_execution_language(value: str) -> str:
    result = value
    for pattern, replacement in _EXECUTION_TEXT_REPLACEMENTS:
        result = pattern.sub(replacement, result)
    return result


def _normalize_final_event_ids(payload: dict[str, Any], *, evidence_packet: Any) -> list[dict[str, Any]]:
    values = payload.get("evidence_event_ids")
    if not isinstance(values, list):
        return []
    allowed = _allowed_event_ids(evidence_packet)
    if not allowed:
        return []
    repairs: list[dict[str, Any]] = []
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        value = _string_value(item)
        if not value:
            continue
        corrected = value
        if corrected.startswith("event:"):
            corrected = corrected.removeprefix("event:")
        if corrected not in allowed:
            repairs.append(
                {
                    "path": f"evidence_event_ids[{index}]",
                    "from": value,
                    "action": "dropped_unknown_event_id",
                }
            )
            continue
        if corrected != value:
            repairs.append(
                {
                    "path": f"evidence_event_ids[{index}]",
                    "from": value,
                    "to": corrected,
                    "action": "event_ref_to_source_event_id",
                }
            )
        if corrected not in seen:
            seen.add(corrected)
            normalized.append(corrected)
    if normalized != values:
        payload["evidence_event_ids"] = normalized
    return repairs


def _allowed_event_ids(evidence_packet: Any) -> set[str]:
    result: set[str] = set()
    packet = evidence_packet if isinstance(evidence_packet, dict) else {}
    source_ids = packet.get("source_event_ids") if isinstance(packet, dict) else None
    if isinstance(source_ids, list | tuple):
        result.update(_string_value(value) for value in source_ids if _string_value(value))
    for ref in _allowed_refs(evidence_packet):
        ref_id = _ref_value(ref, "ref_id")
        source_id = _ref_value(ref, "source_id")
        if source_id and _ref_value(ref, "ref_type") == "event":
            result.add(source_id)
        if ref_id.startswith("event:"):
            result.add(ref_id.removeprefix("event:"))
    return result


def _allowed_refs(evidence_packet: Any) -> tuple[Any, ...]:
    refs = evidence_packet.get("allowed_evidence_refs") if isinstance(evidence_packet, dict) else None
    if refs is None:
        refs = getattr(evidence_packet, "allowed_evidence_refs", ())
    return tuple(refs) if isinstance(refs, list | tuple) else ()


def _ref_value(ref: Any, key: str) -> str:
    value = ref.get(key) if isinstance(ref, dict) else getattr(ref, key, None)
    return _string_value(value)


def _string_value(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["PulseStageOutputNormalization", "normalize_pulse_stage_output"]
