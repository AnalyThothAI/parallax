from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import EvidenceDebateMemo, FinalDecision


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

    ref_result = _canonicalize_evidence_refs(payload, output_type=output_type, evidence_packet=evidence_packet)
    if ref_result:
        trace_metadata["evidence_ref_canonicalization"] = ref_result

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

        rejections.append(
            {
                "path": f"{path}[{index}]",
                "value": value,
                "reason": resolution.reason,
                "candidate_ref_ids": resolution.candidate_ref_ids,
            }
        )

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


def _iter_ref_lists(payload: dict[str, Any], *, output_type: type[Any]) -> list[tuple[str, list[Any], int]]:
    refs: list[tuple[str, list[Any], int]] = []
    if output_type is FinalDecision:
        for field_name in ("supporting_evidence_refs", "risk_evidence_refs", "data_gap_refs"):
            values = payload.get(field_name)
            if isinstance(values, list):
                refs.extend((field_name, values, index) for index in range(len(values)))
        return refs

    if output_type is EvidenceDebateMemo:
        for group_name in ("bull_claims", "bear_claims", "rebuttal_claims", "data_gap_claims"):
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
        values = payload.get("allowed_evidence_ref_ids")
        if isinstance(values, list):
            refs.extend(("allowed_evidence_ref_ids", values, index) for index in range(len(values)))
    return refs


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
