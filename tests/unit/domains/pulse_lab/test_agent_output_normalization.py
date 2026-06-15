from __future__ import annotations

import pytest

from parallax.domains.pulse_lab.services.agent_output_normalization import normalize_pulse_stage_output
from parallax.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerifier
from parallax.domains.pulse_lab.types.agent_decision import FinalDecision
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket


def test_exact_allowed_refs_pass_without_repairs() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:event-1"])

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:event-1"]),
    )

    assert result.payload == raw
    assert result.trace_metadata == {}
    assert FinalDecision.model_validate(result.payload).supporting_evidence_refs == ("event:event-1",)


def test_normalization_requires_formal_evidence_packet_without_dict_compatibility() -> None:
    with pytest.raises(TypeError, match="pulse_stage_output_normalization_packet_contract_required"):
        normalize_pulse_stage_output(
            output_type=FinalDecision,
            raw_output=_trade_candidate_raw(supporting_refs=["event:event-1"]),
            evidence_packet=_packet(refs=["event:event-1"]),
        )


def test_unknown_final_ref_is_not_repaired() -> None:
    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=_trade_candidate_raw(supporting_refs=["event:event-l"]),
        evidence_packet=_packet_model(refs=["event:event-1"]),
    )
    decision = FinalDecision.model_validate(result.payload)
    verification = ClaimEvidenceVerifier().verify(_packet_model(refs=["event:event-1"]), decision)

    assert decision.supporting_evidence_refs == ("event:event-l",)
    assert verification.valid is False
    assert verification.unknown_ref_ids == ("event:event-l",)
    assert "evidence_ref_canonicalization" not in result.trace_metadata


def test_playbook_false_clears_signal_lists() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:event-1"])
    raw["playbook"] = {
        "has_playbook": False,
        "watch_signals": ["继续观察链上流动性"],
        "exit_triggers": ["叙事降温"],
        "monitoring_horizon": "4h",
    }

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:event-1"]),
    )
    decision = FinalDecision.model_validate(result.payload)

    assert decision.playbook.watch_signals == []
    assert decision.playbook.exit_triggers == []
    assert result.trace_metadata["schema_normalization"]["repairs"] == [
        {"path": "playbook.watch_signals", "action": "cleared", "reason": "playbook_has_playbook_false"},
        {"path": "playbook.exit_triggers", "action": "cleared", "reason": "playbook_has_playbook_false"},
    ]


def test_abstain_without_playbook_gets_empty_structural_playbook() -> None:
    raw = _abstain_raw()
    raw.pop("playbook", None)

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["gate:pulse:blocked_market_contract"]),
    )
    decision = FinalDecision.model_validate(result.payload)

    assert decision.recommendation == "abstain"
    assert decision.playbook.has_playbook is False
    assert result.trace_metadata["schema_normalization"]["repairs"] == [
        {"path": "playbook", "action": "inserted_empty", "reason": "abstain_missing_playbook"}
    ]


def test_data_gap_pseudo_ref_is_not_rewritten_to_missing_ref() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:event-1"])
    raw["data_gap_refs"] = ["market:holders_distribution"]

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:event-1"]),
    )
    decision = FinalDecision.model_validate(result.payload)
    verification = ClaimEvidenceVerifier().verify(_packet_model(refs=["event:event-1"]), decision)

    assert decision.data_gap_refs == ("market:holders_distribution",)
    assert verification.valid is False
    assert verification.unknown_ref_ids == ("market:holders_distribution",)
    assert "evidence_ref_canonicalization" not in result.trace_metadata


def test_final_decision_unknown_event_ids_are_dropped_without_invalidating_decision() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:gmgn:twitter_monitor_basic:event-1"])
    raw["evidence_event_ids"] = [
        "event:gmgn:twitter_monitor_basic:event-1",
        "gmgn:twitter_monitor_basic:invented",
    ]

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:gmgn:twitter_monitor_basic:event-1"]),
    )
    decision = FinalDecision.model_validate(result.payload)

    assert decision.evidence_event_ids == ["gmgn:twitter_monitor_basic:event-1"]
    repairs = result.trace_metadata["event_id_normalization"]["repairs"]
    assert repairs[0]["action"] == "event_ref_to_source_event_id"
    assert repairs[1]["action"] == "dropped_unknown_event_id"


def test_final_decision_event_ids_do_not_substitute_for_missing_supporting_refs() -> None:
    raw = _trade_candidate_raw(supporting_refs=[])
    raw["evidence_event_ids"] = ["gmgn:twitter_monitor_basic:event-1"]

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:gmgn:twitter_monitor_basic:event-1"]),
    )

    assert result.payload["supporting_evidence_refs"] == []
    with pytest.raises(ValueError, match="non-abstain decisions require supporting_evidence_refs"):
        FinalDecision.model_validate(result.payload)


def test_execution_language_in_final_text_is_neutralized_before_schema_validation() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:event-1"])
    raw["summary_zh"] = "摘要提到买入语义，但这里只做证据观察。"
    raw["bull_view"]["thesis_zh"] = "自动监测文本提到大额买入。"

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet_model(refs=["event:event-1"]),
    )
    decision = FinalDecision.model_validate(result.payload)

    assert "买入" not in decision.summary_zh
    assert "买入" not in decision.bull_view.thesis_zh
    assert result.trace_metadata["policy_text_normalization"]["repairs"]


def _packet(*, refs: list[str]) -> dict:
    return {
        "allowed_evidence_refs": [
            {
                "ref_id": ref_id,
                "ref_type": ref_id.split(":", 1)[0],
                "source_table": "events",
                "source_id": ref_id.rsplit(":", 1)[-1],
                "observed_at_ms": 1,
                "summary_zh": "证据摘要",
                "quality": "high",
            }
            for ref_id in refs
        ]
    }


def _packet_model(*, refs: list[str]) -> PulseEvidencePacket:
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
        allowed_evidence_refs=_packet(refs=refs)["allowed_evidence_refs"],
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


def _trade_candidate_raw(*, supporting_refs: list[str]) -> dict:
    return {
        "route": "meme",
        "recommendation": "trade_candidate",
        "confidence": 0.63,
        "abstain_reason": None,
        "summary_zh": "社交与市场证据形成观察。",
        "narrative_archetype": "memetic",
        "narrative_thesis_zh": "社交扩散与市场反馈形成同步观察，但仍需要继续监控证据质量和后续确认。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "社交流量与市场反馈同步增强。",
            "supporting_event_ids": ["event-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "流动性仍然偏薄，需要观察延续性。",
            "supporting_event_ids": ["event-1"],
        },
        "playbook": {
            "has_playbook": True,
            "watch_signals": ["社交流量继续扩散"],
            "exit_triggers": ["证据热度回落"],
            "monitoring_horizon": "4h",
        },
        "evidence_event_ids": ["event-1"],
        "supporting_evidence_refs": supporting_refs,
        "risk_evidence_refs": [],
        "data_gap_refs": [],
        "invalidation_conditions": [],
        "residual_risks": [],
    }


def _abstain_raw() -> dict:
    return {
        "route": "research_only",
        "recommendation": "abstain",
        "confidence": 0.0,
        "abstain_reason": "证据不足以形成判断",
        "summary_zh": "证据缺失。",
        "narrative_archetype": "",
        "narrative_thesis_zh": "窗口期内未观察到稳定叙事或对立证据，缺乏足够输入支撑可执行的判断，应转入 research_only",
        "bull_view": {"strength": "absent"},
        "bear_view": {"strength": "absent"},
        "playbook": {"has_playbook": False, "monitoring_horizon": "1h"},
        "evidence_event_ids": [],
        "supporting_evidence_refs": [],
        "risk_evidence_refs": [],
        "data_gap_refs": ["gate:pulse:blocked_market_contract"],
        "invalidation_conditions": [],
        "residual_risks": [],
    }
