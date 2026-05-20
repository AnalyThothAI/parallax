from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult

PULSE_EDGE_EVENTS = (
    "pulse_version_bumped",
    "pulse_status_changed",
    "score_band_crossed",
    "hard_risk_added",
    "recommended_decision_changed",
    "watched_confirmation_appeared",
    "independent_author_bucket_changed",
    "trigger_evidence_changed",
    "timeline_evidence_changed",
)


def build_pulse_edge_state(
    *,
    candidate_id: str,
    candidate_type: str,
    target_type: str | None,
    target_id: str | None,
    window: str,
    scope: str,
    trigger_signature: str,
    timeline_signature: str,
    factor_snapshot: dict[str, Any],
    gate: PulseGateResult,
    pulse_version: str,
    gate_version: str,
) -> dict[str, Any]:
    social_heat = _mapping(_nested(factor_snapshot, "families", "social_heat", "facts"))
    social_propagation = _mapping(_nested(factor_snapshot, "families", "social_propagation", "facts"))
    hard_risks = _stable_strings([*gate.hard_risks, *_list(_nested(factor_snapshot, "gates", "blocked_reasons"))])
    rank_score = _int(_nested(factor_snapshot, "composite", "rank_score"))
    return {
        "candidate_id": str(candidate_id),
        "candidate_type": str(candidate_type),
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "pulse_version": str(pulse_version),
        "gate_version": str(gate_version),
        "pulse_status": gate.pulse_status,
        "verdict": gate.verdict,
        "score_band": gate.score_band,
        "candidate_score_bucket": _score_bucket(gate.candidate_score),
        "rank_score_bucket": _score_bucket(rank_score),
        "recommended_decision": _clean(_nested(factor_snapshot, "composite", "recommended_decision")),
        "watched_confirmation": _int(social_heat.get("watched_mentions")) > 0,
        "independent_author_count_bucket": _count_bucket(
            max(_int(social_heat.get("unique_authors")), _int(social_propagation.get("independent_authors")))
        ),
        "hard_risks": hard_risks,
        "trigger_signature": trigger_signature,
        "timeline_signature": timeline_signature,
    }


def diff_pulse_edge_events(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    before = _mapping(previous)
    after = _mapping(current)
    if not before:
        return ["pulse_status_changed"]

    events: list[str] = []
    if before.get("pulse_version") != after.get("pulse_version") or before.get("gate_version") != after.get(
        "gate_version"
    ):
        events.append("pulse_version_bumped")
    if before.get("pulse_status") != after.get("pulse_status"):
        events.append("pulse_status_changed")
    if before.get("score_band") != after.get("score_band"):
        events.append("score_band_crossed")
    if set(_list(after.get("hard_risks"))) - set(_list(before.get("hard_risks"))):
        events.append("hard_risk_added")
    if before.get("recommended_decision") != after.get("recommended_decision"):
        events.append("recommended_decision_changed")
    if not bool(before.get("watched_confirmation")) and bool(after.get("watched_confirmation")):
        events.append("watched_confirmation_appeared")
    if before.get("independent_author_count_bucket") != after.get("independent_author_count_bucket"):
        events.append("independent_author_bucket_changed")
    if before.get("trigger_signature") != after.get("trigger_signature"):
        events.append("trigger_evidence_changed")
    if before.get("timeline_signature") != after.get("timeline_signature"):
        events.append("timeline_evidence_changed")
    return events


def pulse_edge_signature(state: dict[str, Any]) -> str:
    payload = {
        "candidate_id": state.get("candidate_id"),
        "candidate_type": state.get("candidate_type"),
        "target_type": state.get("target_type"),
        "target_id": state.get("target_id"),
        "window": state.get("window"),
        "scope": state.get("scope"),
        "pulse_version": state.get("pulse_version"),
        "gate_version": state.get("gate_version"),
        "pulse_status": state.get("pulse_status"),
        "score_band": state.get("score_band"),
        "candidate_score_bucket": state.get("candidate_score_bucket"),
        "rank_score_bucket": state.get("rank_score_bucket"),
        "recommended_decision": state.get("recommended_decision"),
        "watched_confirmation": bool(state.get("watched_confirmation")),
        "independent_author_count_bucket": state.get("independent_author_count_bucket"),
        "hard_risks": _stable_strings(state.get("hard_risks")),
        "trigger_signature": state.get("trigger_signature"),
        "timeline_signature": state.get("timeline_signature"),
    }
    return _stable_hash(payload)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _score_bucket(value: Any) -> str:
    score = max(0, min(100, _int(value)))
    lower = (score // 10) * 10
    if lower >= 100:
        return "100"
    return f"{lower}-{lower + 9}"


def _count_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 2:
        return "1-2"
    if value <= 5:
        return "3-5"
    if value <= 10:
        return "6-10"
    return "11+"


def _stable_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values if isinstance(values, list | tuple | set) else []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["PULSE_EDGE_EVENTS", "build_pulse_edge_state", "diff_pulse_edge_events", "pulse_edge_signature"]
