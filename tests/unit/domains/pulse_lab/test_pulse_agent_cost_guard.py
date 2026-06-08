from __future__ import annotations

from parallax.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from parallax.domains.pulse_lab.services.pulse_agent_cost_guard import (
    decide_pulse_agent_cost,
)
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.pulse_source_quality import PulseSourceQualityDecision
from parallax.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext


def test_cost_guard_hard_block_uses_deterministic_finalize() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=False, hard_blocked=True, blocked_reason="blocked_market_contract"),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        now_ms=1_000,
    )

    assert decision.action == "deterministic_finalize"
    assert decision.reason == "deterministic_evidence_block"
    assert decision.public_eligible is False
    assert decision.decision_allowed is False
    assert "stage_plan" not in decision.to_json()
    assert "stage_plan_hash" not in decision.fingerprint.to_json()
    assert "analysis_allowed" not in decision.to_json()
    assert "public_judge_allowed" not in decision.to_json()


def test_cost_guard_source_quality_hidden_skips_decision() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=False, reasons=("single_author_source",)),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        now_ms=1_000,
    )

    assert decision.action == "skip_decision"
    assert decision.reason == "source_quality_hidden"
    assert decision.public_eligible is False
    assert decision.decision_allowed is False
    assert "stage_plan" not in decision.to_json()


def test_cost_guard_public_trade_candidate_runs_single_decision() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        now_ms=1_000,
    )

    assert decision.action == "run_decision"
    assert decision.reason == "public_decision"
    assert decision.public_eligible is True
    assert decision.decision_allowed is True
    assert "stage_plan" not in decision.to_json()


def test_cost_guard_public_token_watch_runs_current_decision() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("token_watch", "watch"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        now_ms=1_000,
    )

    assert decision.action == "run_decision"
    assert decision.reason == "public_decision"
    assert decision.fingerprint.candidate_id == "candidate-1"
    assert decision.fingerprint.trigger_signature == "trigger-a"
    assert decision.fingerprint.timeline_signature == "timeline-a"
    assert decision.decision_allowed is True


def _context() -> PulseCandidateContext:
    return PulseCandidateContext(
        candidate_id="candidate-1",
        candidate_type="token",
        subject_key="token:sol:abc",
        window="1h",
        scope="all",
        trigger_signature="trigger-a",
        timeline_signature="timeline-a",
        priority=90,
        target_type="meme",
        target_id="abc",
        symbol="ABC",
        factor_snapshot={},
        selected_posts=[],
        post_clusters=[],
        gate_result=None,
        edge_state=None,
        edge_events=(),
        source_event_ids=[],
        evidence_event_ids=[],
    )


def _evidence_gate(
    *,
    public_allowed: bool,
    hard_blocked: bool = False,
    blocked_reason: str | None = None,
) -> EvidenceCompletenessGateResult:
    return EvidenceCompletenessGateResult(
        evidence_status="complete" if public_allowed else "insufficient",
        hard_blocked=hard_blocked,
        blocked_reason=blocked_reason,
        max_decision_status="trade_candidate" if public_allowed else "abstain",
        required_ref_ids=("event:1", "metric:1") if public_allowed else tuple(),
        missing_ref_types=tuple() if public_allowed else ("metric",),
        data_gaps=tuple(),
        public_allowed=public_allowed,
        display_status="display_trade_candidate" if public_allowed else "hidden_abstain",
    )


def _gate(pulse_status: str, max_recommendation: str) -> PulseGateResult:
    return PulseGateResult(
        pulse_status=pulse_status,
        verdict=pulse_status,
        candidate_score=82.0,
        score_band="high_conviction" if pulse_status == "trade_candidate" else "watch",
        gate_reasons=["factor_snapshot_trade_gate_passed"],
        risk_reasons=[],
        hard_risks=[],
        max_recommendation=max_recommendation,
        eligible_for_high_alert=True,
        blocked_reasons=[],
    )


def _source_quality(
    *,
    public_allowed: bool,
    reasons: tuple[str, ...] = tuple(),
) -> PulseSourceQualityDecision:
    return PulseSourceQualityDecision(
        public_allowed=public_allowed,
        reasons=reasons,
        metrics={"effective_author_count": 3.0},
    )
