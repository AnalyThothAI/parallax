from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision, TradePlaybook

_RECOMMENDATION_RANK = {
    "abstain": 0,
    "ignore": 1,
    "watchlist": 2,
    "trade_candidate": 3,
    "high_conviction": 4,
}


def clip_recommendation(decision: FinalDecision, *, gate: Any) -> FinalDecision:
    """Apply deterministic gate ceilings before public write/eval."""

    pulse_status = str(getattr(gate, "pulse_status", "") or "")
    max_recommendation = str(getattr(gate, "max_recommendation", "") or "")
    if pulse_status == "risk_rejected_high_info":
        return _clip_to_ignore(decision, reason="risk_rejected_high_info")
    if max_recommendation and _rank(decision.recommendation) > _rank(max_recommendation):
        if max_recommendation == "ignore":
            return _clip_to_ignore(decision, reason="gate_recommendation_ceiling")
        if max_recommendation == "watchlist":
            return _replace_recommendation(decision, recommendation="watchlist")
    return decision


def _clip_to_ignore(decision: FinalDecision, *, reason: str) -> FinalDecision:
    payload = decision.model_dump(mode="json")
    residual_risks = list(payload.get("residual_risks") or [])
    if reason not in residual_risks:
        residual_risks.append(reason)
    payload.update(
        {
            "recommendation": "ignore",
            "confidence": min(float(payload.get("confidence") or 0.0), 0.49),
            "abstain_reason": None,
            "playbook": TradePlaybook(
                has_playbook=False,
                watch_signals=[],
                exit_triggers=[],
                monitoring_horizon=payload.get("playbook", {}).get("monitoring_horizon") or "1h",
            ).model_dump(mode="json"),
            "residual_risks": residual_risks,
        }
    )
    return FinalDecision.model_validate(payload)


def _replace_recommendation(decision: FinalDecision, *, recommendation: str) -> FinalDecision:
    payload = decision.model_dump(mode="json")
    payload["recommendation"] = recommendation
    if recommendation in {"ignore", "abstain"}:
        payload["playbook"] = TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon=payload.get("playbook", {}).get("monitoring_horizon") or "1h",
        ).model_dump(mode="json")
    return FinalDecision.model_validate(payload)


def _rank(value: str) -> int:
    return _RECOMMENDATION_RANK.get(str(value or ""), -1)


__all__ = ["clip_recommendation"]
