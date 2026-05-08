from __future__ import annotations

import pytest

from gmgn_twitter_intel.pipeline.pulse_candidate_gate import PulseGateThresholds, gate_pulse_candidate
from gmgn_twitter_intel.pipeline.pulse_contract import PULSE_THESIS_SCHEMA_VERSION


def _thesis(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": PULSE_THESIS_SCHEMA_VERSION,
        "candidate_type": "token_target",
        "subject_key": "target:CexToken:cex-token:PEPE",
        "target_type": "CexToken",
        "target_id": "cex-token:PEPE",
        "symbol": "PEPE",
        "verdict": "trade_candidate",
        "social_phase": "ignition",
        "narrative_type": "direct_token",
        "summary_zh": "PEPE 社交热度显著上升，独立作者扩散正在增加。",
        "why_now_zh": "5m heat 突破阈值，且 watched source 出现直接证据。",
        "bull_case_zh": ["新增独立作者继续扩散"],
        "bear_case_zh": ["后续只剩重复文案"],
        "confirmation_triggers_zh": ["更多独立作者参与讨论"],
        "invalidation_triggers_zh": ["扩散停止且重复文案占比升高"],
        "top_risks": ["public_stream_coverage"],
        "evidence_event_ids": ["event-1", "event-2"],
        "source_event_ids": ["event-1", "event-2"],
        "confidence": 0.72,
    }
    payload.update(overrides)
    return payload


def _radar(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "heat": {"score": 86, "reasons": ["abnormal_attention"]},
        "quality": {"score": 76},
        "propagation": {"score": 74, "phase": "ignition"},
        "tradeability": {"score": 84, "market_status": "fresh", "market_fresh": True},
        "timing": {"score": 58, "chase_risk": False, "price_change_before_social_pct": 0.0},
        "opportunity": {"decision": "driver", "risks": []},
        "price": {"market_status": "fresh", "price_change_before_social_pct": 0.0},
    }
    payload.update(overrides)
    return payload


def test_all_trade_candidate_requirements_pass() -> None:
    result = gate_pulse_candidate(thesis=_thesis(), radar_score=_radar(), historical_credit=0.6)

    assert result.pulse_status == "trade_candidate"
    assert result.score_band in {"high_conviction", "watch"}
    assert result.hard_risks == []
    assert "trade_gate_passed" in result.gate_reasons


def test_heat_alone_with_unresolved_identity_does_not_trade() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(
            candidate_type="source_seed",
            subject_key="source:unknown",
            target_type=None,
            target_id=None,
            symbol=None,
            verdict="theme_watch",
            social_phase="ignition",
            top_risks=["unresolved token identity"],
            confidence=0.8,
        ),
        radar_score=_radar(heat={"score": 91}, quality={"score": 35}, propagation={"score": 30}),
    )

    assert result.pulse_status in {"blocked_low_information", "risk_rejected_high_info"}
    assert result.pulse_status != "trade_candidate"
    assert "identity_ambiguous" in result.risk_reasons


def test_heat_with_price_lead_chase_risk_is_rejected() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score=_radar(
            timing={"score": 52, "chase_risk": False, "price_change_before_social_pct": 0.16},
            price={"market_status": "fresh", "price_change_before_social_pct": 0.16},
        ),
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert result.score_band == "blocked"
    assert "chase_risk" in result.risk_reasons
    assert "chase_risk" in result.hard_risks


@pytest.mark.parametrize("market_context", [{"market_status": "stale"}, {}])
def test_missing_or_non_fresh_market_never_trades_and_records_risk(market_context: dict[str, object]) -> None:
    radar = _radar(price={}, tradeability={"score": 84})
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score=radar,
        market_context=market_context,
    )

    assert result.pulse_status != "trade_candidate"
    assert result.pulse_status in {"risk_rejected_high_info", "token_watch"}
    assert set(result.risk_reasons) & {"market_stale", "market_missing"}


def test_source_seed_cannot_trade_and_becomes_theme_watch() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(
            candidate_type="source_seed",
            subject_key="source:toly",
            target_type=None,
            target_id=None,
            symbol=None,
            verdict="theme_watch",
            social_phase="expansion",
            narrative_type="ecosystem_spillover",
            confidence=0.77,
        ),
        radar_score=_radar(),
        market_context={"market_status": "fresh"},
    )

    assert result.pulse_status == "theme_watch"
    assert result.pulse_status != "trade_candidate"


def test_low_information_duplicate_public_only_context_is_blocked() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(verdict="token_watch", social_phase="seed", confidence=0.5),
        radar_score=_radar(
            heat={"score": 42, "risks": ["public_stream_coverage"]},
            quality={"score": 35},
            propagation={"score": 30, "risks": ["public_only_unconfirmed"]},
            opportunity={"decision": "watch"},
        ),
        timeline_context={
            "windows": {"1h": {"duplicate_text_share": 0.62, "authors": 1, "mentions": 2}},
            "timeline_signature": "timeline:duplicate-public-only",
            "risk_flags": ["duplicate_text"],
        },
    )

    assert result.pulse_status == "blocked_low_information"
    assert result.score_band == "blocked"
    assert "duplicate_text_cluster" in result.risk_reasons
    assert "public_only_unconfirmed" in result.risk_reasons


def test_high_scoring_duplicate_public_only_context_is_blocked_low_information() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(confidence=0.9),
        radar_score=_radar(
            heat={"score": 92, "risks": ["public_stream_coverage"]},
            quality={"score": 88},
            propagation={"score": 86, "phase": "ignition"},
            tradeability={"score": 91, "market_status": "fresh", "market_fresh": True},
            timing={"score": 70, "chase_risk": False, "price_change_before_social_pct": 0.0},
            opportunity={"decision": "driver", "risks": []},
        ),
        timeline_context={
            "windows": {"1h": {"duplicate_text_share": 0.74, "authors": 1, "mentions": 2}},
            "timeline_signature": "timeline:duplicate-public-only-high-score",
            "risk_flags": ["duplicate_text"],
        },
    )

    assert result.pulse_status == "blocked_low_information"
    assert result.pulse_status != "trade_candidate"
    assert "duplicate_text_cluster" in result.risk_reasons
    assert "public_only_unconfirmed" in result.risk_reasons


def test_low_information_with_chase_risk_is_rejected_high_info() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(verdict="token_watch", social_phase="seed", confidence=0.5),
        radar_score=_radar(
            heat={"score": 42, "risks": ["public_stream_coverage"]},
            quality={"score": 35},
            propagation={"score": 30, "risks": ["public_only_unconfirmed"]},
            timing={"score": 45, "chase_risk": True, "price_change_before_social_pct": 0.16},
            price={"market_status": "fresh", "price_change_before_social_pct": 0.16},
            opportunity={"decision": "watch"},
        ),
        timeline_context={
            "windows": {"1h": {"duplicate_text_share": 0.68, "authors": 1, "mentions": 2}},
            "timeline_signature": "timeline:low-info-chase",
            "risk_flags": ["duplicate_text"],
        },
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert "chase_risk" in result.risk_reasons
    assert "chase_risk" in result.hard_risks


def test_stage_price_chase_risk_alias_rejects_real_timeline_shape() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score=_radar(),
        timeline_context={
            "timeline_signature": "timeline:real-stage-risk",
            "windows": {"1h": {"duplicate_text_share": 0.0, "authors": 4, "mentions": 6}},
            "stage_segments": [
                {
                    "phase": "chase",
                    "summary_facts": {
                        "posts": 4,
                        "authors": 3,
                        "risks": ["price_chase_risk"],
                    },
                }
            ],
        },
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert "chase_risk" in result.risk_reasons
    assert "chase_risk" in result.hard_risks


def test_strong_low_information_with_hard_risk_prefers_high_info_rejection() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(confidence=0.86),
        radar_score=_radar(
            heat={"score": 88, "risks": ["public_stream_coverage"]},
            quality={"score": 80},
            propagation={"score": 78, "risks": ["public_only_unconfirmed"]},
            tradeability={"score": 84, "market_status": "fresh", "hard_risks": ["lookahead_risk"]},
            timing={"score": 62, "chase_risk": False, "price_change_before_social_pct": 0.0},
            opportunity={"decision": "driver"},
        ),
        timeline_context={
            "timeline_signature": "timeline:strong-low-info-hard-risk",
            "windows": {"1h": {"duplicate_text_share": 0.7, "authors": 1, "mentions": 2}},
        },
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert result.pulse_status != "blocked_low_information"
    assert "lookahead_risk" in result.hard_risks
    assert "public_only_unconfirmed" in result.risk_reasons


def test_flat_radar_fresh_market_status_allows_trade() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score={
            "heat": 86,
            "quality": 76,
            "propagation": 74,
            "tradeability": 84,
            "timing": 58,
            "decision": "driver",
            "market_status": "fresh",
        },
    )

    assert result.pulse_status == "trade_candidate"
    assert result.hard_risks == []


def test_missing_market_cap_alias_is_hard_risk() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score=_radar(tradeability={"score": 84, "market_status": "fresh", "risks": ["missing_market_cap"]}),
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert "missing_market_cap" in result.risk_reasons
    assert "missing_market_cap" in result.hard_risks


def test_stage_missing_message_price_is_recorded_as_non_hard_risk() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(),
        radar_score=_radar(),
        timeline_context={
            "timeline_signature": "timeline:missing-message-price",
            "windows": {"1h": {"duplicate_text_share": 0.0, "authors": 4, "mentions": 6}},
            "stage_segments": [
                {
                    "phase": "ignition",
                    "summary_facts": {
                        "posts": 3,
                        "authors": 2,
                        "risks": ["missing_message_price"],
                    },
                }
            ],
        },
    )

    assert result.pulse_status == "trade_candidate"
    assert "missing_message_price" in result.risk_reasons
    assert "missing_message_price" not in result.hard_risks


def test_useful_token_target_below_trade_thresholds_becomes_token_watch() -> None:
    result = gate_pulse_candidate(
        thesis=_thesis(verdict="token_watch", confidence=0.69),
        radar_score=_radar(quality={"score": 55}, propagation={"score": 54}, opportunity={"decision": "watch"}),
        market_context={"market_status": "fresh"},
    )

    assert result.pulse_status == "token_watch"
    assert result.score_band in {"watch", "speculative"}
    assert "trade_gate_incomplete" in result.gate_reasons


def test_trade_gate_thresholds_are_configurable_for_heat_70() -> None:
    radar = _radar(
        heat={"score": 70},
        quality={"score": 60},
        propagation={"score": 60, "phase": "ignition"},
        tradeability={"score": 66, "market_status": "fresh", "market_fresh": True},
        timing={"score": 45, "chase_risk": False, "price_change_before_social_pct": 0.0},
        opportunity={"decision": "driver", "risks": []},
    )

    default_result = gate_pulse_candidate(thesis=_thesis(confidence=0.61), radar_score=radar)
    configured_result = gate_pulse_candidate(
        thesis=_thesis(confidence=0.61),
        radar_score=radar,
        thresholds=PulseGateThresholds(
            trade_heat_min=70,
            trade_quality_min=58,
            trade_propagation_min=58,
            tradeability_min=65,
            timing_min=45,
            confidence_min=0.6,
        ),
    )

    assert default_result.pulse_status == "token_watch"
    assert configured_result.pulse_status == "trade_candidate"
    assert "trade_gate_passed" in configured_result.gate_reasons


def test_candidate_score_and_band_are_deterministic_and_bounded() -> None:
    kwargs = {
        "thesis": _thesis(confidence=0.68),
        "radar_score": {
            "heat": 70,
            "quality": 61,
            "propagation": 58,
            "tradeability": 72,
            "timing": 50,
            "decision": "watch",
            "market_status": "fresh",
        },
        "historical_credit": 0.75,
    }

    first = gate_pulse_candidate(**kwargs)
    second = gate_pulse_candidate(**kwargs)

    assert first == second
    assert 0 <= first.candidate_score <= 100
    assert first.score_band in {"high_conviction", "watch", "speculative", "blocked"}


def test_gate_uses_thesis_validation_for_forbidden_text_and_invalid_target_rules() -> None:
    with pytest.raises(ValueError, match="execution instruction"):
        gate_pulse_candidate(thesis=_thesis(summary_zh="可以考虑买入 PEPE。"), radar_score=_radar())

    with pytest.raises(ValueError, match="token_target requires"):
        gate_pulse_candidate(
            thesis=_thesis(verdict="token_watch", target_type=None, target_id=None),
            radar_score=_radar(),
        )
