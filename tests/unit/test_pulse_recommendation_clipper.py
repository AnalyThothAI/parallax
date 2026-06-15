from __future__ import annotations

from types import SimpleNamespace

import pytest

from parallax.domains.pulse_lab.services.evidence_completeness_gate import EvidenceCompletenessGateResult
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.recommendation_clipper import clip_recommendation
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    TradePlaybook,
)


def test_trade_candidate_clipped_to_watchlist_when_evidence_gate_is_partial() -> None:
    decision = _decision("trade_candidate", confidence=0.74)
    pulse_gate = _pulse_gate(pulse_status="trade_candidate", max_recommendation="trade_candidate")
    evidence_gate = _evidence_gate(
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
    pulse_gate = _pulse_gate(pulse_status="trade_candidate", max_recommendation="trade_candidate")
    evidence_gate = _evidence_gate(
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
    pulse_gate = _pulse_gate(pulse_status="risk_rejected_high_info", max_recommendation="research")
    evidence_gate = _evidence_gate()

    clipped = clip_recommendation(decision, gate=pulse_gate, evidence_gate=evidence_gate)

    assert clipped.recommendation == "ignore"
    assert clipped.confidence == 0.49
    assert "risk_rejected_high_info" in clipped.residual_risks


def test_recommendation_clipper_requires_existing_playbook_horizon_without_1h_fallback() -> None:
    payload = _decision("trade_candidate", confidence=0.74).model_dump(mode="json")
    payload["playbook"] = {"has_playbook": True}
    pulse_gate = _pulse_gate(pulse_status="risk_rejected_high_info", max_recommendation="research")

    class MalformedDecision:
        recommendation = "trade_candidate"

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return payload

    with pytest.raises(TypeError, match="pulse_recommendation_clipper_playbook_horizon_required"):
        clip_recommendation(MalformedDecision(), gate=pulse_gate, evidence_gate=_evidence_gate())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("gate", "pulse_recommendation_clipper_gate_contract_required"),
        ("evidence_gate", "pulse_recommendation_clipper_evidence_gate_contract_required"),
    ],
)
def test_recommendation_clipper_requires_formal_gate_inputs_without_reflection(field: str, match: str) -> None:
    inputs = {
        "decision": _decision("trade_candidate", confidence=0.74),
        "gate": _pulse_gate(),
        "evidence_gate": _evidence_gate(),
    }
    inputs[field] = SimpleNamespace(
        pulse_status="trade_candidate",
        max_recommendation="trade_candidate",
        evidence_status="complete",
        public_allowed=True,
        max_decision_status="trade_candidate",
    )

    with pytest.raises(TypeError, match=match):
        clip_recommendation(**inputs)


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


def _pulse_gate(
    *,
    pulse_status: str = "trade_candidate",
    max_recommendation: str = "trade_candidate",
) -> PulseGateResult:
    return PulseGateResult(
        pulse_status=pulse_status,
        verdict=pulse_status,
        candidate_score=80.0,
        score_band="high_conviction",
        gate_reasons=["positive_signal"],
        risk_reasons=[],
        hard_risks=[],
        max_recommendation=max_recommendation,
        eligible_for_high_alert=True,
        blocked_reasons=[],
    )


def _evidence_gate(
    *,
    evidence_status: str = "complete",
    max_decision_status: str = "trade_candidate",
    public_allowed: bool = True,
    blocked_reason: str | None = None,
    required_ref_ids: tuple[str, ...] = (),
) -> EvidenceCompletenessGateResult:
    return EvidenceCompletenessGateResult(
        evidence_status=evidence_status,
        hard_blocked=max_decision_status == "abstain",
        blocked_reason=blocked_reason,
        max_decision_status=max_decision_status,
        required_ref_ids=required_ref_ids,
        missing_ref_types=(),
        data_gaps=(),
        public_allowed=public_allowed,
        display_status="display_trade_candidate" if public_allowed else "hidden_insufficient_evidence",
    )
