from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.pulse_lab.services.recommendation_clipper import clip_recommendation
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    TradePlaybook,
)


def test_trade_candidate_clipped_to_watchlist_when_evidence_gate_is_partial() -> None:
    decision = _decision("trade_candidate", confidence=0.74)
    pulse_gate = SimpleNamespace(pulse_status="trade_candidate", max_recommendation="trade_candidate")
    evidence_gate = SimpleNamespace(
        evidence_status="partial",
        max_decision_status="token_watch",
        public_allowed=True,
        required_ref_ids=("gate:pulse:evidence_partial",),
    )

    clipped = clip_recommendation(decision, gate=pulse_gate, evidence_gate=evidence_gate)

    assert clipped.recommendation == "watchlist"
    assert clipped.confidence == 0.74


def test_insufficient_evidence_gate_clips_to_abstain() -> None:
    decision = _decision("trade_candidate", confidence=0.74)
    pulse_gate = SimpleNamespace(pulse_status="trade_candidate", max_recommendation="trade_candidate")
    evidence_gate = SimpleNamespace(
        evidence_status="insufficient",
        max_decision_status="abstain",
        public_allowed=False,
        blocked_reason="blocked_social_contract",
        required_ref_ids=("gate:pulse:blocked_social_contract",),
    )

    clipped = clip_recommendation(decision, gate=pulse_gate, evidence_gate=evidence_gate)

    assert clipped.recommendation == "abstain"
    assert clipped.confidence == 0.0
    assert clipped.abstain_reason == "blocked_social_contract"
    assert clipped.playbook.has_playbook is False


def test_existing_pulse_gate_risk_rejection_still_clips_to_ignore() -> None:
    decision = _decision("trade_candidate", confidence=0.74)
    pulse_gate = SimpleNamespace(pulse_status="risk_rejected_high_info", max_recommendation="research")

    clipped = clip_recommendation(decision, gate=pulse_gate)

    assert clipped.recommendation == "ignore"
    assert clipped.confidence == 0.49
    assert "risk_rejected_high_info" in clipped.residual_risks


def _decision(recommendation: str, *, confidence: float) -> FinalDecision:
    return FinalDecision(
        route="cex",
        recommendation=recommendation,
        confidence=confidence,
        abstain_reason="insufficient evidence" if recommendation == "abstain" else None,
        summary_zh="测试摘要",
        narrative_archetype="催化",
        narrative_thesis_zh="这是一个用于测试推荐裁剪的中文论述，长度足够满足模型校验要求。",
        bull_view=BullBearView(
            strength="moderate",
            thesis_zh="多头证据足够用于测试",
            supporting_event_ids=["event-1"],
        ),
        bear_view=BullBearView(
            strength="moderate",
            thesis_zh="空头风险足够用于测试",
            supporting_event_ids=["event-1"],
        ),
        playbook=TradePlaybook(
            has_playbook=True,
            watch_signals=["成交量继续放大"],
            exit_triggers=["证据失效"],
            monitoring_horizon="1h",
        ),
        evidence_event_ids=["event-1"],
        supporting_evidence_refs=("event:event-1",),
    )
