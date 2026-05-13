from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision

_SCORE_BAND_BY_DECISION: dict[str, str] = {
    "high_conviction": "high_conviction",
    "trade_candidate": "watch",
    "watchlist": "watch",
    "ignore": "blocked",
    "abstain": "blocked",
}


def candidate_fields_from_decision(decision: FinalDecision, *, stage_count: int) -> dict[str, Any]:
    bounded_stage_count = max(0, int(stage_count))
    return {
        "decision_route": decision.route,
        "decision_recommendation": decision.recommendation,
        "decision_confidence": decision.confidence,
        "decision_abstain_reason": decision.abstain_reason,
        "decision_stage_count": bounded_stage_count,
        "decision_json": decision.model_dump(mode="json"),
        "score_band": _SCORE_BAND_BY_DECISION[decision.recommendation],
    }


__all__ = ["candidate_fields_from_decision"]
