from __future__ import annotations

from copy import deepcopy

from gmgn_twitter_intel.domains.pulse_lab.services.agent_output_normalization import normalize_pulse_stage_output
from gmgn_twitter_intel.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerifier
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import EvidenceDebateMemo, FinalDecision


def test_exact_allowed_refs_pass_without_repairs() -> None:
    raw = _trade_candidate_raw(supporting_refs=["event:event-1"])

    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=raw,
        evidence_packet=_packet(refs=["event:event-1"]),
    )

    assert result.payload == raw
    assert result.trace_metadata == {}
    assert FinalDecision.model_validate(result.payload).supporting_evidence_refs == ("event:event-1",)


def test_unique_same_type_typo_is_canonicalized() -> None:
    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=_trade_candidate_raw(supporting_refs=["event:event-l"]),
        evidence_packet=_packet(refs=["event:event-1"]),
    )

    decision = FinalDecision.model_validate(result.payload)

    assert decision.supporting_evidence_refs == ("event:event-1",)
    assert result.trace_metadata["evidence_ref_canonicalization"]["corrections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "from": "event:event-l",
            "to": "event:event-1",
            "ref_type": "event",
            "reason": "unique_same_type_edit_distance_1",
        }
    ]


def test_ambiguous_same_type_typo_is_rejected_without_repair() -> None:
    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=_trade_candidate_raw(supporting_refs=["event:event-0"]),
        evidence_packet=_packet(refs=["event:event-1", "event:event-2"]),
    )

    decision = FinalDecision.model_validate(result.payload)
    verification = ClaimEvidenceVerifier().verify(_packet_object(["event:event-1", "event:event-2"]), _memo(), decision)

    assert decision.supporting_evidence_refs == ("event:event-0",)
    assert verification.valid is False
    assert verification.unknown_ref_ids == ("event:event-0",)
    assert result.trace_metadata["evidence_ref_canonicalization"]["rejections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "value": "event:event-0",
            "reason": "ambiguous_same_type_edit_distance_1",
            "candidate_ref_ids": ["event:event-1", "event:event-2"],
        }
    ]


def test_cross_type_typo_is_rejected_without_repair() -> None:
    result = normalize_pulse_stage_output(
        output_type=FinalDecision,
        raw_output=_trade_candidate_raw(supporting_refs=["event:market:price_usd"]),
        evidence_packet=_packet(refs=["metric:market:price_usd"]),
    )

    decision = FinalDecision.model_validate(result.payload)
    verification = ClaimEvidenceVerifier().verify(_packet_object(["metric:market:price_usd"]), _memo(), decision)

    assert decision.supporting_evidence_refs == ("event:market:price_usd",)
    assert verification.valid is False
    assert verification.unknown_ref_ids == ("event:market:price_usd",)
    assert result.trace_metadata["evidence_ref_canonicalization"]["rejections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "value": "event:market:price_usd",
            "reason": "cross_type_candidate",
            "candidate_ref_ids": ["metric:market:price_usd"],
        }
    ]


def test_outside_packet_ref_is_rejected_without_repair() -> None:
    result = normalize_pulse_stage_output(
        output_type=EvidenceDebateMemo,
        raw_output={
            "bull_claims": [
                {"claim": "社交证据支持扩散观察", "evidence_refs": ["event:event-999"], "stance": "bull"}
            ],
            "bear_claims": [],
            "rebuttal_claims": [],
            "data_gap_claims": [],
            "summary_zh": "证据显示讨论在扩散，但需要继续观察。",
            "allowed_evidence_ref_ids": ["event:event-1"],
        },
        evidence_packet=_packet(refs=["event:event-1"]),
    )

    memo = EvidenceDebateMemo.model_validate(result.payload)

    assert memo.bull_claims[0].evidence_refs == ("event:event-999",)
    assert result.trace_metadata["evidence_ref_canonicalization"]["rejections"] == [
        {
            "path": "bull_claims[0].evidence_refs[0]",
            "value": "event:event-999",
            "reason": "outside_packet",
            "candidate_ref_ids": [],
        }
    ]


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
        evidence_packet=_packet(refs=["event:event-1"]),
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
        evidence_packet=_packet(refs=["gate:pulse:blocked_market_contract"]),
    )

    decision = FinalDecision.model_validate(result.payload)

    assert decision.recommendation == "abstain"
    assert decision.playbook.has_playbook is False
    assert decision.playbook.watch_signals == []
    assert decision.playbook.exit_triggers == []
    assert result.trace_metadata["schema_normalization"]["repairs"] == [
        {"path": "playbook", "action": "inserted_empty", "reason": "abstain_missing_playbook"}
    ]


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


def _packet_object(refs: list[str]) -> object:
    return type("Packet", (), {"allowed_evidence_refs": _packet(refs=refs)["allowed_evidence_refs"]})()


def _memo() -> EvidenceDebateMemo:
    return EvidenceDebateMemo(
        bull_claims=(),
        bear_claims=(),
        rebuttal_claims=(),
        data_gap_claims=(),
        summary_zh="证据摘要足以进行一致性校验。",
        allowed_evidence_ref_ids=(),
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
        "supporting_evidence_refs": deepcopy(supporting_refs),
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
        "summary_zh": "证据不足，转为 research_only。",
        "narrative_archetype": "",
        "narrative_thesis_zh": "证据不足以形成资产判断，本轮只记录缺口并等待后续事实进入证据包。",
        "bull_view": {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []},
        "evidence_event_ids": [],
        "supporting_evidence_refs": [],
        "risk_evidence_refs": [],
        "data_gap_refs": ["gate:pulse:blocked_market_contract"],
        "invalidation_conditions": [],
        "residual_risks": ["证据不足"],
    }
