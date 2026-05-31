from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.pulse_lab.services.pulse_freshness_health import PulseFreshnessHealthService
from parallax.domains.pulse_lab.services.write_gate import PulseWriteGate
from parallax.domains.pulse_lab.types.agent_decision import BullBearView, FinalDecision, TradePlaybook


def test_write_gate_does_not_hide_current_valid_candidate_due_to_aggregate_hold_health() -> None:
    decision = _trade_candidate_decision()

    result = PulseWriteGate().evaluate(
        final_decision=decision,
        eval_result={"status": "pass"},
        gate=SimpleNamespace(pulse_status="trade_candidate"),
        evidence_gate=SimpleNamespace(evidence_status="complete", public_allowed=True),
        claim_verification=SimpleNamespace(valid=True, decision_status="trade_candidate"),
        health_status={"publish_status": "hold_publish", "reasons": ["agent_failure_rate_hold"]},
    )

    assert result.public_write_allowed is True
    assert result.display_status == "display_trade_candidate"
    assert result.reason is None


def test_freshness_health_degrades_instead_of_hold_when_some_recent_runs_succeeded() -> None:
    status, reasons = PulseFreshnessHealthService(conn=object())._classify(
        clocks={
            "latest_packet_created_at_ms": 1_000,
            "latest_public_candidate_updated_at_ms": 500,
        },
        jobs={"dead_jobs": 0},
        runs={
            "agent_runs_4h": 10,
            "agent_failed_4h": 8,
            "agent_failure_rate_4h": 0.8,
            "unknown_ref_failure_rate_4h": 0.0,
            "unsupported_claim_failure_rate_4h": 0.0,
        },
        now_ms=1_500,
    )

    assert status == "degraded"
    assert "agent_failure_rate_high" in reasons
    assert "agent_failure_rate_hold" not in reasons


def test_freshness_health_holds_when_all_recent_runs_failed() -> None:
    status, reasons = PulseFreshnessHealthService(conn=object())._classify(
        clocks={
            "latest_packet_created_at_ms": 1_000,
            "latest_public_candidate_updated_at_ms": 500,
        },
        jobs={"dead_jobs": 0},
        runs={
            "agent_runs_4h": 10,
            "agent_failed_4h": 10,
            "agent_failure_rate_4h": 1.0,
            "unknown_ref_failure_rate_4h": 0.0,
            "unsupported_claim_failure_rate_4h": 0.0,
        },
        now_ms=1_500,
    )

    assert status == "hold_publish"
    assert "agent_failure_rate_hold" in reasons


def _trade_candidate_decision() -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="trade_candidate",
        confidence=0.7,
        abstain_reason=None,
        summary_zh="社交与市场证据形成可展示观察。",
        narrative_archetype="memetic",
        narrative_thesis_zh="社交扩散与市场反馈同步增强，但仍需要继续跟踪证据质量和后续确认。",
        bull_view=BullBearView(
            strength="moderate",
            thesis_zh="社交流量与市场反馈同步增强。",
            supporting_event_ids=["event-1"],
        ),
        bear_view=BullBearView(
            strength="weak",
            thesis_zh="流动性仍然偏薄，需要观察延续性。",
            supporting_event_ids=["event-1"],
        ),
        playbook=TradePlaybook(
            has_playbook=True,
            watch_signals=["社交流量继续扩散"],
            exit_triggers=["证据热度回落"],
            monitoring_horizon="4h",
        ),
        evidence_event_ids=["event-1"],
        supporting_evidence_refs=("event:event-1",),
        risk_evidence_refs=(),
        data_gap_refs=(),
        invalidation_conditions=[],
        residual_risks=[],
    )
