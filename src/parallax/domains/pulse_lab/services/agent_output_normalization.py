from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import BearCaseMemo, FinalDecision, SignalAnalystMemo


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

    ref_result = _canonicalize_evidence_refs(payload, output_type=output_type, evidence_packet=evidence_packet)
    if ref_result:
        trace_metadata["evidence_ref_canonicalization"] = ref_result

    if output_type is FinalDecision:
        event_id_repairs = _normalize_final_event_ids(payload, evidence_packet=evidence_packet)
        if event_id_repairs:
            trace_metadata["event_id_normalization"] = {"repairs": event_id_repairs}
        supporting_ref_repairs = _synthesize_missing_supporting_refs(payload, evidence_packet=evidence_packet)
        if supporting_ref_repairs:
            trace_metadata.setdefault("schema_normalization", {}).setdefault("repairs", []).extend(
                supporting_ref_repairs
            )

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


def _canonicalize_evidence_refs(
    payload: dict[str, Any],
    *,
    output_type: type[Any],
    evidence_packet: Any,
) -> dict[str, Any]:
    allowed = _allowed_ref_index(evidence_packet)
    if not allowed.by_id:
        return {}

    corrections: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for path, container, index in _iter_ref_lists(payload, output_type=output_type):
        value = _string_value(container[index])
        if not value or value.startswith("missing:") or value in allowed.by_id:
            continue

        resolution = _resolve_ref(value, allowed)
        if resolution.corrected_ref_id:
            container[index] = resolution.corrected_ref_id
            corrections.append(
                {
                    "path": f"{path}[{index}]",
                    "from": value,
                    "to": resolution.corrected_ref_id,
                    "ref_type": resolution.ref_type,
                    "reason": resolution.reason,
                }
            )
            continue
        if _should_convert_to_missing_ref(payload, path=path, value=value, output_type=output_type):
            replacement = _missing_ref(value)
            container[index] = replacement
            corrections.append(
                {
                    "path": f"{path}[{index}]",
                    "from": value,
                    "to": replacement,
                    "ref_type": resolution.ref_type,
                    "reason": "data_gap_missing_placeholder",
                }
            )
            continue

        rejections.append(
            {
                "path": f"{path}[{index}]",
                "value": value,
                "reason": resolution.reason,
                "candidate_ref_ids": resolution.candidate_ref_ids,
            }
        )
    if output_type in {SignalAnalystMemo, BearCaseMemo}:
        corrections.extend(_remove_unknown_declared_allowed_refs(payload, allowed))

    result: dict[str, Any] = {}
    if corrections:
        result["corrections"] = corrections
    if rejections:
        result["rejections"] = rejections
    return result


@dataclass(frozen=True, slots=True)
class _AllowedRefIndex:
    by_id: dict[str, str]
    by_type: dict[str, tuple[str, ...]]
    by_body: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _RefResolution:
    corrected_ref_id: str | None
    ref_type: str
    reason: str
    candidate_ref_ids: list[str]


def _allowed_ref_index(evidence_packet: Any) -> _AllowedRefIndex:
    refs = _allowed_refs(evidence_packet)
    by_id: dict[str, str] = {}
    by_type: dict[str, list[str]] = {}
    by_body: dict[str, list[str]] = {}
    for ref in refs:
        ref_id = _ref_value(ref, "ref_id")
        if not ref_id:
            continue
        ref_type = _ref_value(ref, "ref_type") or _ref_type(ref_id)
        by_id[ref_id] = ref_type
        by_type.setdefault(ref_type, []).append(ref_id)
        by_body.setdefault(_ref_body(ref_id), []).append(ref_id)
    return _AllowedRefIndex(
        by_id=by_id,
        by_type={key: tuple(sorted(values)) for key, values in by_type.items()},
        by_body={key: tuple(sorted(values)) for key, values in by_body.items() if key},
    )


def _resolve_ref(value: str, allowed: _AllowedRefIndex) -> _RefResolution:
    ref_type = _ref_type(value)
    event_alias = _event_ref_alias(value)
    if event_alias and event_alias in allowed.by_id:
        return _RefResolution(
            corrected_ref_id=event_alias,
            ref_type=ref_type,
            reason="event_source_alias",
            candidate_ref_ids=[event_alias],
        )
    if value.startswith("event:") and value.removeprefix("event:") in allowed.by_id:
        stripped = value.removeprefix("event:")
        return _RefResolution(
            corrected_ref_id=stripped,
            ref_type=ref_type,
            reason="event_prefix_alias",
            candidate_ref_ids=[stripped],
        )
    same_body = [ref_id for ref_id in allowed.by_body.get(_ref_body(value), ()) if allowed.by_id[ref_id] != ref_type]
    if same_body:
        return _RefResolution(
            corrected_ref_id=None,
            ref_type=ref_type,
            reason="cross_type_candidate",
            candidate_ref_ids=same_body,
        )

    candidates = [
        ref_id
        for ref_id in allowed.by_type.get(ref_type, ())
        if _bounded_levenshtein_distance(value, ref_id, max_distance=1) == 1
    ]
    if len(candidates) == 1:
        return _RefResolution(
            corrected_ref_id=candidates[0],
            ref_type=ref_type,
            reason="unique_same_type_edit_distance_1",
            candidate_ref_ids=candidates,
        )
    if len(candidates) > 1:
        return _RefResolution(
            corrected_ref_id=None,
            ref_type=ref_type,
            reason="ambiguous_same_type_edit_distance_1",
            candidate_ref_ids=sorted(candidates),
        )
    return _RefResolution(
        corrected_ref_id=None,
        ref_type=ref_type,
        reason="outside_packet",
        candidate_ref_ids=[],
    )


def _event_ref_alias(value: str) -> str | None:
    if not value or value.startswith("event:"):
        return None
    if value.startswith("gmgn:"):
        return f"event:{value}"
    return None


def _should_convert_to_missing_ref(
    payload: dict[str, Any],
    *,
    path: str,
    value: str,
    output_type: type[Any],
) -> bool:
    if output_type is FinalDecision:
        return path == "data_gap_refs"
    if output_type not in {SignalAnalystMemo, BearCaseMemo}:
        return False
    if output_type is BearCaseMemo and path.startswith("missing_fact_impacts["):
        return True
    ref_type = _ref_type(value)
    if ref_type.endswith("_evidence"):
        return True
    claim = _claim_for_ref_path(payload, path)
    stance = _string_value(claim.get("stance")) if claim else ""
    return stance in {"gap", "risk"}


def _claim_for_ref_path(payload: dict[str, Any], path: str) -> dict[str, Any] | None:
    match = re.match(r"^(bull_claims|risk_claims|missing_fact_impacts)\[(\d+)\]\.evidence_refs$", path)
    if not match:
        return None
    claims = payload.get(match.group(1))
    index = int(match.group(2))
    if not isinstance(claims, list) or index >= len(claims):
        return None
    claim = claims[index]
    return claim if isinstance(claim, dict) else None


def _iter_ref_lists(payload: dict[str, Any], *, output_type: type[Any]) -> list[tuple[str, list[Any], int]]:
    refs: list[tuple[str, list[Any], int]] = []
    if output_type is FinalDecision:
        for field_name in ("supporting_evidence_refs", "risk_evidence_refs", "data_gap_refs"):
            values = payload.get(field_name)
            if isinstance(values, list):
                refs.extend((field_name, values, index) for index in range(len(values)))
        return refs

    group_names: tuple[str, ...]
    if output_type is SignalAnalystMemo:
        group_names = ("bull_claims",)
    elif output_type is BearCaseMemo:
        group_names = ("risk_claims", "missing_fact_impacts")
    else:
        group_names = ()
    for group_name in group_names:
        claims = payload.get(group_name)
        if not isinstance(claims, list):
            continue
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                continue
            evidence_refs = claim.get("evidence_refs")
            if isinstance(evidence_refs, list):
                path = f"{group_name}[{claim_index}].evidence_refs"
                refs.extend((path, evidence_refs, index) for index in range(len(evidence_refs)))
    return refs


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
    if output_type not in {SignalAnalystMemo, BearCaseMemo, FinalDecision}:
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


def _missing_ref(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value.strip().lower()).strip("_")
    return f"missing:{slug or 'evidence'}"


def _remove_unknown_declared_allowed_refs(payload: dict[str, Any], allowed: _AllowedRefIndex) -> list[dict[str, Any]]:
    values = payload.get("allowed_evidence_ref_ids")
    if not isinstance(values, list):
        return []
    filtered = sorted({value for item in values if (value := _string_value(item)) and value in allowed.by_id})
    if filtered == values:
        return []
    payload["allowed_evidence_ref_ids"] = filtered
    return [
        {
            "path": "allowed_evidence_ref_ids",
            "action": "removed_unknown_declared_refs",
            "from_count": len(values),
            "to_count": len(filtered),
        }
    ]


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


def _synthesize_missing_supporting_refs(payload: dict[str, Any], *, evidence_packet: Any) -> list[dict[str, Any]]:
    recommendation = _string_value(payload.get("recommendation"))
    if recommendation in {"", "abstain"}:
        return []
    values = payload.get("supporting_evidence_refs")
    if isinstance(values, list | tuple) and any(_string_value(value) for value in values):
        return []
    refs = _supporting_refs_from_event_ids(payload, evidence_packet=evidence_packet)
    if not refs:
        refs = _fallback_supporting_refs(evidence_packet)
    if not refs:
        return []
    payload["supporting_evidence_refs"] = list(refs)
    return [
        {
            "path": "supporting_evidence_refs",
            "action": "inserted_from_allowed_evidence_refs",
            "count": len(refs),
        }
    ]


def _supporting_refs_from_event_ids(payload: dict[str, Any], *, evidence_packet: Any) -> tuple[str, ...]:
    values = payload.get("evidence_event_ids")
    if not isinstance(values, list | tuple):
        return ()
    event_ref_by_source = _event_ref_by_source_event_id(evidence_packet)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        source_id = _string_value(value).removeprefix("event:")
        ref_id = event_ref_by_source.get(source_id)
        if ref_id and ref_id not in seen:
            seen.add(ref_id)
            result.append(ref_id)
    return tuple(result[:3])


def _event_ref_by_source_event_id(evidence_packet: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for ref in _allowed_refs(evidence_packet):
        ref_id = _ref_value(ref, "ref_id")
        if not ref_id.startswith("event:"):
            continue
        source_id = _ref_value(ref, "source_id") or ref_id.removeprefix("event:")
        result[source_id] = ref_id
        result[ref_id.removeprefix("event:")] = ref_id
    return result


def _fallback_supporting_refs(evidence_packet: Any) -> tuple[str, ...]:
    by_type: dict[str, list[str]] = {}
    for ref in _allowed_refs(evidence_packet):
        ref_id = _ref_value(ref, "ref_id")
        if not ref_id:
            continue
        by_type.setdefault(_ref_value(ref, "ref_type") or _ref_type(ref_id), []).append(ref_id)
    result: list[str] = []
    seen: set[str] = set()
    for ref_type in ("event", "market", "metric", "identity", "profile"):
        for ref_id in by_type.get(ref_type, ()):
            if ref_id not in seen:
                seen.add(ref_id)
                result.append(ref_id)
            if len(result) >= 3:
                return tuple(result)
    return tuple(result)


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


def _ref_type(ref_id: str) -> str:
    if ":" not in ref_id:
        return ""
    return ref_id.split(":", 1)[0]


def _ref_body(ref_id: str) -> str:
    if ":" not in ref_id:
        return ""
    return ref_id.split(":", 1)[1]


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _bounded_levenshtein_distance(left: str, right: str, *, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            cell = min(insert_cost, delete_cost, replace_cost)
            current.append(cell)
            row_min = min(row_min, cell)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


__all__ = ["PulseStageOutputNormalization", "normalize_pulse_stage_output"]
