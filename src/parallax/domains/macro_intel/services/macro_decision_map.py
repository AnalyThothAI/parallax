from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from parallax.domains.macro_intel.services.macro_cross_asset_rules import market_session_offset
from parallax.domains.macro_intel.services.macro_evidence import numeric_series

LaneDirection = Literal["tailwind", "neutral", "headwind", "insufficient_evidence"]
LaneTrend = Literal["strengthening", "stable", "weakening", "insufficient_evidence"]
LaneConfidence = Literal["high", "medium", "low", "insufficient_evidence"]
_ChangeMode = Literal["return_pct", "difference"]

_DIRECTION_ZH = {
    "tailwind": "顺风",
    "neutral": "中性",
    "headwind": "逆风",
    "insufficient_evidence": "证据不足",
}
_TREND_ZH = {
    "strengthening": "增强",
    "stable": "基本不变",
    "weakening": "减弱",
    "insufficient_evidence": "缺少可比历史",
}
_SHOCK_LABELS = {
    "growth": "增长降温",
    "inflation": "通胀压力",
    "policy_real_rates": "实际利率收紧",
    "term_premium_supply": "期限溢价与供给压力",
    "liquidity_funding": "流动性与融资压力",
    "credit": "信用收紧",
}


@dataclass(frozen=True, slots=True)
class _LaneSpec:
    lane_id: str
    label: str
    anchor: str
    anchor_mode: _ChangeMode
    threshold: float
    confirmation: str
    confirmation_mode: _ChangeMode
    confirmation_threshold: float
    confirmation_inverted: bool = False


_LANES = (
    _LaneSpec(
        "us_equities",
        "美国股票",
        "asset:spy",
        "return_pct",
        0.75,
        "asset:qqq",
        "return_pct",
        0.75,
    ),
    _LaneSpec(
        "long_duration_treasuries",
        "长期美债",
        "asset:tlt",
        "return_pct",
        0.75,
        "rates:dgs10",
        "difference",
        0.10,
        True,
    ),
    _LaneSpec(
        "credit",
        "信用",
        "asset:hyg",
        "return_pct",
        0.50,
        "credit:hy_oas",
        "difference",
        15.0,
        True,
    ),
    _LaneSpec(
        "usd",
        "美元",
        "fx:dxy",
        "return_pct",
        0.50,
        "rates:dgs10",
        "difference",
        0.10,
    ),
    _LaneSpec(
        "gold",
        "黄金",
        "asset:gld",
        "return_pct",
        0.75,
        "rates:real_10y",
        "difference",
        0.10,
        True,
    ),
    _LaneSpec(
        "oil",
        "原油",
        "asset:uso",
        "return_pct",
        1.0,
        "inflation:10y_breakeven",
        "difference",
        0.10,
    ),
    _LaneSpec(
        "crypto",
        "加密资产",
        "crypto:btc",
        "return_pct",
        2.0,
        "crypto:eth",
        "return_pct",
        2.0,
    ),
    _LaneSpec(
        "market_volatility",
        "市场波动率",
        "vol:vix",
        "difference",
        1.0,
        "vol:vix3m",
        "difference",
        1.0,
    ),
)


def build_macro_decision_map(
    observations: Sequence[Mapping[str, Any]],
    *,
    market_cutoff: date,
    dominant_shock: Mapping[str, Any],
    official_catalysts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    comparison_session = market_session_offset(market_cutoff, sessions=5)
    lanes = [
        _build_lane(
            observations,
            spec=spec,
            current_session=market_cutoff,
            comparison_session=comparison_session,
        )
        for spec in _LANES
    ]
    shock_summary = _shock_summary(dominant_shock, lanes)
    return {
        "shock_summary": shock_summary,
        "risk_lanes": lanes,
        "key_changes": _key_changes(lanes),
        "nearest_catalyst": dict(official_catalysts[0]) if official_catalysts else None,
        "core_invalidation": _core_invalidation(shock_summary, lanes),
    }


def _build_lane(
    observations: Sequence[Mapping[str, Any]],
    *,
    spec: _LaneSpec,
    current_session: date,
    comparison_session: date,
) -> dict[str, Any]:
    current = _window_change(
        observations,
        concept_key=spec.anchor,
        cutoff=current_session,
        mode=spec.anchor_mode,
    )
    comparison = _window_change(
        observations,
        concept_key=spec.anchor,
        cutoff=comparison_session,
        mode=spec.anchor_mode,
    )
    confirmation = _window_change(
        observations,
        concept_key=spec.confirmation,
        cutoff=current_session,
        mode=spec.confirmation_mode,
    )
    current_signal = _signal(current.get("value"), threshold=spec.threshold)
    comparison_signal = _signal(comparison.get("value"), threshold=spec.threshold)
    confirmation_signal = _signal(
        confirmation.get("value"),
        threshold=spec.confirmation_threshold,
    )
    if confirmation_signal is not None and spec.confirmation_inverted:
        confirmation_signal *= -1

    direction = _direction(current_signal)
    trend = _trend(
        current_signal,
        comparison_signal,
        current_value=current.get("value"),
        comparison_value=comparison.get("value"),
        threshold=spec.threshold,
    )
    confidence = _confidence(current_signal, confirmation_signal)
    contradiction = (
        {
            "code": f"{spec.lane_id}_confirmation_conflicts",
            "evidence_refs": [spec.confirmation],
        }
        if current_signal not in {None, 0}
        and confirmation_signal not in {None, 0}
        and current_signal != confirmation_signal
        else None
    )
    evidence_refs = [spec.anchor]
    if confirmation.get("status") == "available":
        evidence_refs.append(spec.confirmation)
    degradation_reason = _degradation_reason(current, comparison, confirmation)
    invalidation_refs = list(dict.fromkeys((spec.anchor, spec.confirmation)))
    return {
        "lane_id": spec.lane_id,
        "direction": direction,
        "trend": trend,
        "confidence": confidence,
        "summary": _lane_summary(spec.label, direction=direction, trend=trend),
        "drivers": (
            [
                {
                    "code": f"{spec.lane_id}_{direction}",
                    "evidence_refs": [spec.anchor],
                }
            ]
            if direction != "insufficient_evidence"
            else []
        ),
        "contradiction": contradiction,
        "invalidation": (
            {
                "code": (
                    f"{spec.lane_id}_breaks_neutral_range"
                    if direction == "neutral"
                    else f"{spec.lane_id}_direction_reverses"
                ),
                "evidence_refs": invalidation_refs,
            }
            if direction != "insufficient_evidence"
            else None
        ),
        "evidence_refs": evidence_refs,
        "degradation_reason": degradation_reason,
        "current_session": current_session,
        "comparison_session": comparison_session,
        "sparkline_concept_key": spec.anchor,
    }


def _window_change(
    observations: Sequence[Mapping[str, Any]],
    *,
    concept_key: str,
    cutoff: date,
    mode: _ChangeMode,
) -> dict[str, Any]:
    base_session = market_session_offset(cutoff, sessions=20)
    points = numeric_series(observations, concept_key, cutoff=cutoff)
    by_date = {point["observed_at"]: point for point in points}
    latest = by_date.get(cutoff)
    base = by_date.get(base_session)
    if latest is None:
        return {"status": "unavailable", "reason": "missing_at_cutoff", "value": None}
    if base is None:
        return {"status": "unavailable", "reason": "insufficient_20_session_history", "value": None}
    latest_value = float(latest["value"])
    base_value = float(base["value"])
    if mode == "return_pct":
        if base_value == 0:
            return {"status": "unavailable", "reason": "zero_window_base", "value": None}
        value = ((latest_value / base_value) - 1.0) * 100.0
    else:
        value = latest_value - base_value
    return {
        "status": "available",
        "reason": None,
        "value": round(value, 6),
        "sample_start": base_session,
        "sample_end": cutoff,
    }


def _signal(value: Any, *, threshold: float) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    numeric = float(value)
    if numeric > threshold:
        return 1
    if numeric < -threshold:
        return -1
    return 0


def _direction(signal: int | None) -> LaneDirection:
    if signal is None:
        return "insufficient_evidence"
    if signal > 0:
        return "tailwind"
    if signal < 0:
        return "headwind"
    return "neutral"


def _trend(
    current_signal: int | None,
    comparison_signal: int | None,
    *,
    current_value: Any,
    comparison_value: Any,
    threshold: float,
) -> LaneTrend:
    if current_signal is None or comparison_signal is None:
        return "insufficient_evidence"
    if current_signal == 0:
        return "stable" if comparison_signal == 0 else "weakening"
    if comparison_signal == 0 or current_signal != comparison_signal:
        return "strengthening"
    current_magnitude = abs(float(current_value))
    comparison_magnitude = abs(float(comparison_value))
    material_delta = threshold / 2.0
    if current_magnitude > comparison_magnitude + material_delta:
        return "strengthening"
    if current_magnitude + material_delta < comparison_magnitude:
        return "weakening"
    return "stable"


def _confidence(current_signal: int | None, confirmation_signal: int | None) -> LaneConfidence:
    if current_signal is None:
        return "insufficient_evidence"
    if confirmation_signal is None:
        return "medium"
    if current_signal == confirmation_signal:
        return "high"
    if current_signal == 0 or confirmation_signal == 0:
        return "medium"
    return "low"


def _degradation_reason(
    current: Mapping[str, Any],
    comparison: Mapping[str, Any],
    confirmation: Mapping[str, Any],
) -> str | None:
    if current.get("status") != "available":
        return str(current.get("reason") or "anchor_unavailable")
    if comparison.get("status") != "available":
        return f"comparison_{comparison.get('reason') or 'unavailable'}"
    if confirmation.get("status") != "available":
        return f"confirmation_{confirmation.get('reason') or 'unavailable'}"
    return None


def _lane_summary(label: str, *, direction: LaneDirection, trend: LaneTrend) -> str:
    if direction == "insufficient_evidence":
        return f"{label}：关键证据不足，暂不判断。"
    return f"{label}：{_DIRECTION_ZH[direction]}，较五个已完成交易日前{_TREND_ZH[trend]}。"


def _shock_summary(
    dominant_shock: Mapping[str, Any],
    lanes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate = str(dominant_shock.get("candidate") or "") or None
    available_lanes = [lane for lane in lanes if lane.get("direction") != "insufficient_evidence"]
    if candidate is not None:
        state = "dominant"
    elif len(available_lanes) >= 6:
        state = "no_dominant_shock"
    else:
        state = "insufficient_evidence"

    status = str(dominant_shock.get("status") or "")
    confidence: LaneConfidence
    if state == "insufficient_evidence":
        confidence = "insufficient_evidence"
    elif state == "no_dominant_shock":
        confidence = "medium"
    elif status == "confirmed":
        confidence = "high"
    elif status == "provisional":
        confidence = "medium"
    else:
        confidence = "low"

    lane_trends = [str(lane.get("trend") or "") for lane in available_lanes]
    if state == "insufficient_evidence":
        trend: LaneTrend = "insufficient_evidence"
    elif lane_trends.count("strengthening") >= 2:
        trend = "strengthening"
    elif lane_trends.count("weakening") >= 2:
        trend = "weakening"
    else:
        trend = "stable"

    primary_trigger = dominant_shock.get("primary_trigger")
    drivers = [dict(primary_trigger)] if isinstance(primary_trigger, Mapping) else []
    confirmations = _mapping_items(dominant_shock.get("cross_domain_confirmations"))
    contradictions = _mapping_items(dominant_shock.get("critical_contradictions"))
    evidence_refs = [str(ref) for ref in dominant_shock.get("hit_evidence", ()) if isinstance(ref, str) and ref]
    return {
        "state": state,
        "candidate": candidate,
        "summary": _shock_text(state, candidate),
        "confidence": confidence,
        "trend": trend,
        "drivers": drivers,
        "confirmations": confirmations,
        "contradictions": contradictions,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
    }


def _shock_text(state: str, candidate: str | None) -> str:
    if state == "dominant" and candidate is not None:
        return f"当前主导冲击：{_SHOCK_LABELS.get(candidate, candidate)}。"
    if state == "no_dominant_shock":
        return "当前没有单一主导冲击，跨资产信号仍然分散。"
    return "关键证据不足，暂时无法判断主导冲击。"


def _key_changes(lanes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    priority = {"strengthening": 0, "weakening": 1}
    candidates = [
        (index, lane)
        for index, lane in enumerate(lanes)
        if str(lane.get("trend") or "") in priority and str(lane.get("direction") or "") != "insufficient_evidence"
    ]
    candidates.sort(
        key=lambda pair: (
            priority[str(pair[1]["trend"])],
            0 if pair[1].get("confidence") == "high" else 1,
            pair[0],
        )
    )
    return [
        {
            "rank": rank,
            "lane_id": str(lane["lane_id"]),
            "code": f"{lane['lane_id']}_{lane['trend']}",
            "summary": str(lane["summary"]),
            "evidence_refs": list(lane.get("evidence_refs") or ()),
        }
        for rank, (_index, lane) in enumerate(candidates[:3], start=1)
    ]


def _core_invalidation(
    shock_summary: Mapping[str, Any],
    lanes: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    state = str(shock_summary.get("state") or "")
    if state == "insufficient_evidence":
        return None
    if state == "dominant":
        refs = list(shock_summary.get("evidence_refs") or ())
        return {"code": "dominant_shock_trigger_reverses", "evidence_refs": refs}
    refs = [
        str(lane.get("sparkline_concept_key") or "")
        for lane in lanes
        if lane.get("direction") != "insufficient_evidence"
    ][:3]
    return {"code": "cross_asset_consensus_emerges", "evidence_refs": refs}


def _mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


__all__ = ["build_macro_decision_map"]
