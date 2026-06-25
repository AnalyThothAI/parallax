from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import FinalDecision

_SCORE_BAND_BY_DECISION: dict[str, str] = {
    "high_conviction": "high_conviction",
    "trade_candidate": "watch",
    "watchlist": "watch",
    "ignore": "blocked",
    "abstain": "blocked",
}


def candidate_fields_from_decision(decision: FinalDecision, *, stage_count: int) -> dict[str, Any]:
    parsed_stage_count = _required_nonnegative_int(stage_count, "pulse_decision_stage_count_required")
    return {
        "decision_route": decision.route,
        "decision_recommendation": decision.recommendation,
        "decision_confidence": decision.confidence,
        "decision_abstain_reason": decision.abstain_reason,
        "decision_stage_count": parsed_stage_count,
        "decision_json": decision.model_dump(mode="json"),
        "score_band": _SCORE_BAND_BY_DECISION[decision.recommendation],
    }


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error_code)
    return int(value)


__all__ = ["candidate_fields_from_decision"]
