from __future__ import annotations

from typing import Any

from .scoring_common import contribution, safe_float, safe_int, score_payload


def timing_score(features: dict[str, Any]) -> dict[str, Any]:
    social_start_ms = _optional_int(features.get("social_start_ms"))
    first_price_move_ms = _optional_int(features.get("first_price_move_ms"))
    price_change_window_pct = features.get("price_change_window_pct")
    price_change = safe_float(price_change_window_pct) if price_change_window_pct is not None else None
    price_change_before = safe_float(features.get("price_change_before_social_pct"))
    heat_score = safe_int(features.get("social_heat_score"))

    reasons: list[str] = []
    risks: list[str] = []
    contributions: list[dict[str, Any]] = []
    status = "insufficient_data"
    score = 45.0
    chase_risk = False

    if social_start_ms is None:
        risks.append("missing_social_start")
    elif first_price_move_ms is None or price_change is None:
        status = "insufficient_data"
        risks.append("missing_price_history")
        score = 50.0 if heat_score >= 70 else 40.0
    elif first_price_move_ms < social_start_ms and (price_change_before >= 0.15 or price_change >= 0.35):
        status = "price_leads_social"
        chase_risk = True
        risks.append("chase_risk")
        score = 35.0
    elif social_start_ms <= first_price_move_ms and abs(price_change) <= 0.08:
        status = "social_leads_price"
        reasons.append("social_before_price_move")
        score = 82.0
    elif price_change >= 0.08:
        status = "social_confirms_price"
        reasons.append("social_and_price_confirm")
        score = 70.0
    elif price_change < 0:
        status = "social_fades"
        risks.append("social_fades")
        score = 42.0

    contributions.append(contribution("timing.status", score, status))
    return score_payload(
        score_version="timing_v1",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=[],
        extra={
            "status": status,
            "social_start_ms": social_start_ms,
            "first_price_move_ms": first_price_move_ms,
            "price_change_window_pct": price_change,
            "price_change_before_social_pct": price_change_before,
            "chase_risk": chase_risk,
        },
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return safe_int(value)
