from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_agent_cost_guard import (
    decide_pulse_agent_cost,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_source_quality import PulseSourceQualityDecision
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext

LANE_MODELS = {
    "pulse.signal_analyst": "qwen3.6",
    "pulse.bear_case": "qwen3.6",
    "pulse.risk_portfolio_judge": "deepseek-v4-flash",
}


def test_cost_guard_hard_block_finalizes_without_public_judge() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=False, hard_blocked=True, blocked_reason="blocked_market_contract"),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        lane_models=LANE_MODELS,
        terminal_fingerprint_found=False,
        provider_cooldown_until_ms=None,
        now_ms=1_000,
    )

    assert decision.action == "no_llm_finalize"
    assert decision.reason == "deterministic_evidence_block"
    assert decision.public_eligible is False
    assert decision.public_judge_allowed is False
    assert decision.stage_plan.run_risk_portfolio_judge is False


def test_cost_guard_source_quality_hidden_uses_research_only() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=False, reasons=("single_author_source",)),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        lane_models=LANE_MODELS,
        terminal_fingerprint_found=False,
        provider_cooldown_until_ms=None,
        now_ms=1_000,
    )

    assert decision.action == "research_only"
    assert decision.reason == "source_quality_hidden"
    assert decision.public_eligible is False
    assert decision.research_allowed is True
    assert decision.public_judge_allowed is False
    assert decision.stage_plan.signal_model == "qwen3.6"
    assert decision.stage_plan.bear_model == "qwen3.6"
    assert decision.stage_plan.judge_model is None


def test_cost_guard_public_trade_candidate_uses_research_and_public_judge() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        lane_models=LANE_MODELS,
        terminal_fingerprint_found=False,
        provider_cooldown_until_ms=None,
        now_ms=1_000,
    )

    assert decision.action == "research_with_public_judge"
    assert decision.reason == "public_judge"
    assert decision.public_eligible is True
    assert decision.research_allowed is True
    assert decision.public_judge_allowed is True
    assert decision.stage_plan.run_signal_analyst is True
    assert decision.stage_plan.run_bear_case is True
    assert decision.stage_plan.run_risk_portfolio_judge is True
    assert decision.stage_plan.judge_model == "deepseek-v4-flash"


def test_cost_guard_duplicate_fingerprint_reuses_terminal_run() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("token_watch", "watch"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        lane_models=LANE_MODELS,
        terminal_fingerprint_found=True,
        provider_cooldown_until_ms=None,
        now_ms=1_000,
    )

    assert decision.action == "reuse_terminal_run"
    assert decision.reason == "duplicate_fingerprint"
    assert decision.fingerprint.candidate_id == "candidate-1"
    assert decision.fingerprint.trigger_signature == "trigger-a"
    assert decision.fingerprint.timeline_signature == "timeline-a"
    assert decision.public_judge_allowed is False


def test_cost_guard_provider_cooldown_suppresses_model_work() -> None:
    decision = decide_pulse_agent_cost(
        context=_context(),
        evidence_gate=_evidence_gate(public_allowed=True),
        gate=_gate("trade_candidate", "trade_candidate"),
        source_quality=_source_quality(public_allowed=True),
        runtime_hash="runtime-a",
        evidence_packet_hash="packet-a",
        lane_models=LANE_MODELS,
        terminal_fingerprint_found=False,
        provider_cooldown_until_ms=60_000,
        now_ms=1_000,
    )

    assert decision.action == "provider_cooldown"
    assert decision.reason == "provider_cooldown_active"
    assert decision.cooldown_until_ms == 60_000
    assert decision.research_allowed is False
    assert decision.public_judge_allowed is False
    assert decision.stage_plan.run_signal_analyst is False
    assert decision.stage_plan.run_risk_portfolio_judge is False


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
