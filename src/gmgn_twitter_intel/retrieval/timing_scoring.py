from __future__ import annotations

from typing import Any

from .scoring_common import contribution, safe_float, safe_int, score_payload


def timing_score(features: dict[str, Any]) -> dict[str, Any]:
    social_signal_start_ms = _optional_int(features.get("social_signal_start_ms"))
    price_change_since_social_pct = features.get("price_change_since_social_pct")
    price_change = safe_float(price_change_since_social_pct) if price_change_since_social_pct is not None else None
    price_change_before_raw = features.get("price_change_before_social_pct")
    price_change_before = safe_float(price_change_before_raw) if price_change_before_raw is not None else None
    market_observation_status = str(features.get("market_observation_status") or "ready")
    heat_score = safe_int(features.get("social_heat_score"))

    reasons: list[str] = []
    risks: list[str] = []
    contributions: list[dict[str, Any]] = []
    status = "insufficient_history"
    score = 45.0
    chase_risk = False

    if social_signal_start_ms is None:
        risks.append("missing_social_start")
    elif market_observation_status in {"pending", "running"}:
        status = "market_pending"
        risks.append("market_observation_pending")
        score = 50.0 if heat_score >= 70 else 40.0
    elif market_observation_status in {
        "provider_not_configured",
        "provider_not_found",
        "provider_error",
        "rate_limited",
        "dead",
    }:
        status = "market_unavailable"
        risks.append(market_observation_status)
        score = 38.0
    elif (price_change_before or 0.0) >= 0.15:
        status = "price_leads_social"
        chase_risk = True
        risks.append("chase_risk")
        score = 35.0
    elif price_change is None:
        status = "insufficient_history"
        risks.append("insufficient_history")
        score = 50.0 if heat_score >= 70 else 40.0
    elif price_change < 0:
        status = "social_fades"
        risks.append("social_fades")
        score = 42.0
    elif price_change >= 0.08:
        status = "social_confirms_price"
        reasons.append("social_and_price_confirm")
        score = 70.0
    else:
        status = "social_leads_price"
        reasons.append("social_before_price_move")
        score = 82.0

    contributions.append(contribution("timing.status", score, status))
    return score_payload(
        score_version="timing_v2",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=[],
        extra={
            "status": status,
            "social_signal_start_ms": social_signal_start_ms,
            "price_change_since_social_pct": price_change,
            "price_change_before_social_pct": price_change_before,
            "market_observation_status": market_observation_status,
            "chase_risk": chase_risk,
        },
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return safe_int(value)
