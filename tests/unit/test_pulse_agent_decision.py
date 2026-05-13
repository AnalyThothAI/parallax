from __future__ import annotations

import pytest
from pydantic import ValidationError

from gmgn_twitter_intel.domains.pulse_lab.services.decision_mapping import candidate_fields_from_decision
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision


def test_final_decision_requires_abstain_reason() -> None:
    with pytest.raises(ValidationError, match="abstain_reason"):
        FinalDecision(
            route="research_only",
            recommendation="abstain",
            confidence=0,
            abstain_reason=None,
            summary_zh="身份未解析。",
            invalidation_conditions=[],
            residual_risks=["无 target，不能形成资产判断。"],
            evidence_event_ids=[],
        )


def test_final_decision_rejects_execution_language() -> None:
    with pytest.raises(ValueError, match="trading execution"):
        FinalDecision(
            route="meme",
            recommendation="trade_candidate",
            confidence=0.72,
            abstain_reason=None,
            summary_zh="可以买入并设置止损。",
            invalidation_conditions=["流动性跌破 floor。"],
            residual_risks=["单一 KOL 驱动。"],
            evidence_event_ids=["event-1"],
        )


def test_high_conviction_maps_to_candidate_decision_fields() -> None:
    decision = FinalDecision(
        route="meme",
        recommendation="high_conviction",
        confidence=0.81,
        abstain_reason=None,
        summary_zh="社交与市场事实共振。",
        invalidation_conditions=["cohort 转弱。"],
        residual_risks=["流动性薄。"],
        evidence_event_ids=["event-1"],
    )

    fields = candidate_fields_from_decision(decision, stage_count=3)

    assert fields == {
        "decision_route": "meme",
        "decision_recommendation": "high_conviction",
        "decision_confidence": 0.81,
        "decision_abstain_reason": None,
        "decision_stage_count": 3,
        "decision_json": decision.model_dump(mode="json"),
        "score_band": "high_conviction",
    }


def test_watchlist_maps_to_candidate_decision_fields() -> None:
    decision = FinalDecision(
        route="cex",
        recommendation="watchlist",
        confidence=0.49,
        abstain_reason=None,
        summary_zh="事件值得观察，但证据不足。",
        invalidation_conditions=["成交量回落。"],
        residual_risks=["缺少 OI 确认。"],
        evidence_event_ids=["event-2"],
    )

    fields = candidate_fields_from_decision(decision, stage_count=2)

    assert fields["decision_route"] == "cex"
    assert fields["decision_recommendation"] == "watchlist"
    assert fields["decision_confidence"] == 0.49
    assert fields["decision_stage_count"] == 2
    assert fields["score_band"] == "watch"
