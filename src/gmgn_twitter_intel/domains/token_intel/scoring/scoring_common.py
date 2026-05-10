from __future__ import annotations

import math
from typing import Any


def score_payload(
    *,
    score_version: str,
    score: float,
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    contributions: list[dict[str, Any]] | None = None,
    risk_caps: list[dict[str, Any]] | None = None,
    data_health: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capped_score = apply_risk_caps(clamp_score(score), risk_caps or [])
    payload: dict[str, Any] = {
        "score": capped_score,
        "score_version": score_version,
        "reasons": _dedupe(reasons or []),
        "risks": _dedupe(risks or []),
        "contributions": contributions or [],
        "risk_caps": risk_caps or [],
        "data_health": data_health or {},
    }
    if extra:
        payload.update(extra)
    return payload


def apply_risk_caps(score: int, risk_caps: list[dict[str, Any]]) -> int:
    capped = score
    for cap in risk_caps:
        if cap.get("cap") is not None:
            capped = min(capped, int(cap["cap"]))
    return clamp_score(capped)


def contribution(feature: str, value: float, reason: str) -> dict[str, Any]:
    return {"feature": feature, "value": round(float(value), 4), "reason": reason}


def cap(risk: str, value: int) -> dict[str, Any]:
    return {"risk": risk, "cap": int(value)}


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def log_points(value: float, *, scale: float, max_points: float) -> float:
    if value <= 0:
        return 0.0
    return min(max_points, math.log1p(value) / math.log1p(scale) * max_points)


def ratio_points(value: float, *, max_ratio: float, max_points: float) -> float:
    if value <= 0 or max_ratio <= 0:
        return 0.0
    return min(max_points, value / max_ratio * max_points)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
