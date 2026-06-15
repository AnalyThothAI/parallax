from __future__ import annotations

from types import SimpleNamespace
from typing import Literal

import pytest

from parallax.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerifier
from parallax.domains.pulse_lab.types.agent_decision import FinalDecision
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket


def test_unknown_ref_blocks_publish() -> None:
    packet = _packet()
    decision = _decision("trade_candidate", supporting_refs=("event:event-1", "metric:market:unknown"))

    result = _verify(packet, decision)

    assert result.valid is False
    assert result.unknown_ref_ids == ("metric:market:unknown",)
    assert result.display_status_if_failed == "hidden_invalid_output"


def test_event_id_only_final_decision_fails_schema_before_verifier() -> None:
    with pytest.raises(ValueError, match="supporting_evidence_refs"):
        _decision("trade_candidate", supporting_refs=(), evidence_event_ids=("event-1",))


def test_event_id_string_is_not_accepted_as_complete_evidence_ref() -> None:
    packet = _packet()
    decision = _decision("trade_candidate", supporting_refs=("event-1",))

    result = _verify(packet, decision)

    assert result.valid is False
    assert result.unknown_ref_ids == ("event-1",)


def test_complete_refs_allow_public_display() -> None:
    packet = _packet()
    decision = _decision("trade_candidate", supporting_refs=("event:event-1", "metric:market:price_usd"))

    result = _verify(packet, decision)

    assert result.valid is True
    assert result.unknown_ref_ids == ()
    assert result.decision_status == "trade_candidate"
    assert result.display_status_if_failed is None


def test_abstain_can_use_gate_gap_ref_without_supporting_refs() -> None:
    packet = _packet()
    decision = _decision("abstain", supporting_refs=(), data_gap_refs=("gate:pulse:blocked_market_contract",))

    result = _verify(packet, decision)

    assert result.valid is True
    assert result.decision_status == "abstain"


def test_verifier_requires_formal_packet_and_final_decision_without_reflection() -> None:
    packet = _packet()
    decision = _decision("trade_candidate", supporting_refs=("event:event-1",))
    loose_packet = SimpleNamespace(allowed_evidence_refs=[{"ref_id": "event:event-1"}])
    loose_decision = SimpleNamespace(
        recommendation="trade_candidate",
        supporting_evidence_refs=("event:event-1",),
        risk_evidence_refs=(),
        data_gap_refs=(),
        evidence_event_ids=[],
    )

    with pytest.raises(TypeError, match="pulse_claim_verifier_packet_contract_required"):
        ClaimEvidenceVerifier().verify(loose_packet, decision)
    with pytest.raises(TypeError, match="pulse_claim_verifier_final_decision_contract_required"):
        ClaimEvidenceVerifier().verify(packet, loose_decision)


def _packet() -> PulseEvidencePacket:
    refs = [
        {"ref_id": "event:event-1", "ref_type": "event"},
        {"ref_id": "metric:market:price_usd", "ref_type": "metric"},
        {"ref_id": "identity:token", "ref_type": "identity"},
        {"ref_id": "gate:pulse:blocked_market_contract", "ref_type": "gate"},
    ]
    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        run_id="run-1",
        evidence_packet_hash="sha256:packet",
        schema_version="pulse_evidence_packet_v1",
        candidate_id="candidate-1",
        target_type="chain_token",
        target_id="TEST",
        symbol="TEST",
        window="1h",
        scope="default",
        snapshot_at_ms=1,
        source_event_ids=("event-1",),
        allowed_evidence_refs=[
            {
                **ref,
                "source_table": "test",
                "source_id": str(ref["ref_id"]),
                "observed_at_ms": 1,
                "summary_zh": str(ref["ref_id"]),
                "quality": "high",
            }
            for ref in refs
        ],
        social_evidence={"status": "complete", "event_refs": ("event:event-1",)},
        market_evidence={
            "status": "complete",
            "route": "meme",
            "target_market_type": "dex",
            "price_usd": 1.0,
            "liquidity_usd": 1000.0,
            "instrument_ref": "pair:solana:test",
            "freshness_status": "fresh",
        },
        identity_evidence={"status": "complete", "identity_refs": ("identity:token",)},
        quality_metrics={"ref_count": len(refs), "high_quality_ref_count": len(refs), "fresh_ref_count": len(refs)},
    )


def _verify(
    packet: PulseEvidencePacket,
    decision: FinalDecision,
):
    return ClaimEvidenceVerifier().verify(packet, decision)


def _decision(
    recommendation: Literal["trade_candidate", "abstain"],
    *,
    supporting_refs: tuple[str, ...],
    risk_refs: tuple[str, ...] = (),
    data_gap_refs: tuple[str, ...] = (),
    evidence_event_ids: tuple[str, ...] = (),
) -> FinalDecision:
    abstain = recommendation == "abstain"
    return FinalDecision(
        route="research_only" if abstain else "meme",
        recommendation=recommendation,
        confidence=0.0 if abstain else 0.63,
        abstain_reason="证据不足以形成判断" if abstain else None,
        summary_zh="证据状态已经归一化。",
        narrative_archetype="" if abstain else "social_market_sync",
        narrative_thesis_zh="社交讨论与市场反馈在同一窗口内出现同步变化，但仍需要继续观察证据质量与后续确认。",
        bull_view=(
            {"strength": "absent"}
            if abstain
            else {
                "strength": "moderate",
                "thesis_zh": "社交流量与市场反馈同步增强。",
                "supporting_event_ids": ["event-1"],
            }
        ),
        bear_view=(
            {"strength": "absent"}
            if abstain
            else {
                "strength": "weak",
                "thesis_zh": "流动性仍然偏薄，需要观察延续性。",
                "supporting_event_ids": ["event-1"],
            }
        ),
        playbook=(
            {"has_playbook": False, "monitoring_horizon": "1h"}
            if abstain
            else {
                "has_playbook": True,
                "watch_signals": ["社交流量继续扩散"],
                "exit_triggers": ["证据热度回落"],
                "monitoring_horizon": "4h",
            }
        ),
        supporting_evidence_refs=supporting_refs,
        risk_evidence_refs=risk_refs,
        data_gap_refs=data_gap_refs,
        evidence_event_ids=list(evidence_event_ids),
    )
