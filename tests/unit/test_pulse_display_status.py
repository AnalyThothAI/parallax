from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.pulse_lab.types import (
    BearCaseMemo,
    EvidenceClaim,
    FinalDecision,
    PulseEvidencePacket,
    SignalAnalystMemo,
    display_status_from_decision,
    is_public_display_status,
    run_outcome_from_failure,
)


def test_display_status_maps_public_decisions_only_when_publish_allowed() -> None:
    assert display_status_from_decision("trade_candidate", "complete", True) == "display_trade_candidate"
    assert display_status_from_decision("token_watch", "partial", True) == "display_token_watch"
    assert (
        display_status_from_decision("risk_rejected_high_info", "partial", True)
        == "display_risk_rejected_high_info"
    )

    assert display_status_from_decision("trade_candidate", "insufficient", True) == "hidden_insufficient_evidence"
    assert display_status_from_decision("trade_candidate", "complete", False) == "hidden_hold_publish"
    assert display_status_from_decision("abstain", "complete", True) == "hidden_abstain"
    assert display_status_from_decision("invalid", "invalid", True) == "hidden_invalid_output"
    assert is_public_display_status("hidden_source_quality") is False


def test_public_status_helper_only_accepts_display_prefixes() -> None:
    assert is_public_display_status("display_trade_candidate") is True
    assert is_public_display_status("display_token_watch") is True
    assert is_public_display_status("display_risk_rejected_high_info") is True
    assert is_public_display_status("hidden_abstain") is False


def test_run_outcome_from_failure_uses_recovered_state_machine_values() -> None:
    assert run_outcome_from_failure("unknown_evidence_id") == "invalid_unknown_evidence_ref"
    assert run_outcome_from_failure("schema_validation_failed") == "invalid_schema"
    assert run_outcome_from_failure("provider_rate_limited") == "provider_rate_limited"
    assert run_outcome_from_failure("mystery") == "unexpected_exception"


def test_evidence_packet_hash_is_stable_across_dict_key_order() -> None:
    packet_a = _packet(
        source_fingerprints={
            "factor_snapshot": {"b": 2, "a": 1},
            "market": {"provider": "binance_cex_rest", "pricefeed_id": "pf-1"},
        }
    ).sealed_copy()
    packet_b = _packet(
        source_fingerprints={
            "market": {"pricefeed_id": "pf-1", "provider": "binance_cex_rest"},
            "factor_snapshot": {"a": 1, "b": 2},
        }
    ).sealed_copy()

    assert packet_a.evidence_packet_hash == packet_b.evidence_packet_hash
    assert packet_a.evidence_packet_hash.startswith("sha256:")


def test_research_committee_memos_and_final_decision_serialize_round_trip() -> None:
    signal_memo = SignalAnalystMemo(
        bull_claims=(EvidenceClaim(claim="价格和社交流量同时活跃", evidence_refs=("event:event-1",), stance="bull"),),
        what_changed_zh="证据足够形成观察，但仍需关注流动性持续性。",
        allowed_evidence_ref_ids=("event:event-1", "metric:market:price_usd"),
    )
    restored_signal = SignalAnalystMemo.model_validate_json(signal_memo.model_dump_json())
    assert restored_signal == signal_memo

    bear_memo = BearCaseMemo(
        risk_claims=(),
        confidence_ceiling=0.7,
        missing_fact_impacts=(),
        allowed_evidence_ref_ids=("event:event-1",),
    )
    restored_bear = BearCaseMemo.model_validate_json(bear_memo.model_dump_json())
    assert restored_bear == bear_memo

    decision = _final_decision(supporting_evidence_refs=("event:event-1",))
    assert FinalDecision.model_validate_json(decision.model_dump_json()) == decision


def test_non_abstain_final_decision_requires_supporting_evidence_refs() -> None:
    with pytest.raises(ValueError, match="supporting_evidence_refs"):
        _final_decision(supporting_evidence_refs=())


def _packet(*, source_fingerprints: dict) -> PulseEvidencePacket:
    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        evidence_packet_hash="",
        schema_version="pulse_evidence_packet_v1",
        candidate_id="candidate-1",
        target_type="cex_symbol",
        target_id="BNB",
        symbol="BNB",
        window="1h",
        scope="all",
        snapshot_at_ms=1_800_000_000_000,
        source_event_ids=("event-1",),
        allowed_evidence_refs=(
            {
                "ref_id": "event:event-1",
                "ref_type": "event",
                "source_table": "events",
                "source_id": "event-1",
                "observed_at_ms": 1_800_000_000_000,
                "summary_zh": "官方账号提及 BNB。",
                "quality": "high",
            },
        ),
        social_evidence={"status": "complete", "event_refs": ("event:event-1",), "summary_zh": "社交流量充足"},
        market_evidence={
            "status": "partial",
            "route": "cex",
            "target_market_type": "cex",
            "price_usd": 600.0,
            "venue_ref": "okx",
            "instrument_ref": "pf-1",
            "observed_at_ms": 1_800_000_000_000,
            "freshness_status": "fresh",
            "source_provider": "binance_cex_rest",
            "pricefeed_id": "pf-1",
        },
        identity_evidence={"status": "complete", "identity_refs": (), "profile_refs": (), "summary_zh": "身份可识别"},
        quality_metrics={"ref_count": 1, "high_quality_ref_count": 1, "fresh_ref_count": 1},
        data_gaps=(),
        risk_flags=(),
        source_fingerprints=source_fingerprints,
        admission_context={"candidate_score": 0.82},
    )


def _final_decision(*, supporting_evidence_refs: tuple[str, ...]) -> FinalDecision:
    return FinalDecision(
        route="cex",
        recommendation="trade_candidate",
        confidence=0.72,
        summary_zh="证据支持进入观察列表。",
        narrative_archetype="资金关注",
        narrative_thesis_zh="社交流量与市场价格同步增强，身份与价格证据都在证据包内，当前足够支持交易候选观察。",
        bull_view={
            "strength": "moderate",
            "thesis_zh": "社交流量与价格证据同步。",
            "supporting_event_ids": ["event-1"],
        },
        bear_view={
            "strength": "moderate",
            "thesis_zh": "仍需观察成交延续性。",
            "supporting_event_ids": ["event-1"],
        },
        playbook={
            "has_playbook": True,
            "watch_signals": ["继续观察社交流量"],
            "exit_triggers": ["证据过期"],
            "monitoring_horizon": "1h",
        },
        evidence_event_ids=["event-1"],
        supporting_evidence_refs=supporting_evidence_refs,
        risk_evidence_refs=(),
        data_gap_refs=(),
    )
