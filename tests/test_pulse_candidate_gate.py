from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import (
    gate_pulse_candidate_from_factor_snapshot,
)


def _snapshot(
    *,
    rank_score: int = 73,
    eligible: bool = True,
    blocked_reasons: list[str] | None = None,
    target_type: str | None = "Asset",
    target_id: str | None = "asset-1",
    symbol: str | None = "TEST",
    market_risks: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "token_factor_snapshot_v1",
        "subject": {
            "target_type": target_type,
            "target_id": target_id,
            "symbol": symbol,
        },
        "families": {
            "identity": {
                "facts": {"target_type": target_type, "target_id": target_id, "symbol": symbol},
                "factors": {
                    "target_id": {
                        "family": "identity",
                        "key": "target_id",
                        "risk_flags": [],
                        "hard_gate": None,
                    }
                },
            },
            "market_quality": {
                "facts": {"holders": 500, "liquidity_usd": 50_000},
                "factors": {
                    "holders": {
                        "family": "market_quality",
                        "key": "holders",
                        "risk_flags": market_risks or [],
                        "hard_gate": "block_high_alert" if market_risks else None,
                    },
                    "liquidity_usd": {
                        "family": "market_quality",
                        "key": "liquidity_usd",
                        "risk_flags": [],
                        "hard_gate": None,
                    },
                },
            },
        },
        "hard_gates": {
            "eligible_for_high_alert": eligible,
            "blocked_reasons": blocked_reasons or [],
        },
        "composite": {
            "rank_score": rank_score,
            "recommended_decision": "high_alert" if rank_score >= 70 else "watch",
        },
        "provenance": {"source_event_ids": ["event-1"]},
    }


def test_trade_candidate_when_snapshot_eligible_and_score_at_least_72() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(factor_snapshot=_snapshot(rank_score=72))

    assert result.pulse_status == "trade_candidate"
    assert result.candidate_score == 72
    assert result.score_band == "watch"
    assert result.max_recommendation == "trade_candidate"
    assert result.eligible_for_high_alert is True
    assert result.blocked_reasons == []
    assert result.to_json()["max_recommendation"] == "trade_candidate"


def test_token_watch_when_snapshot_eligible_and_score_at_least_45() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(factor_snapshot=_snapshot(rank_score=45))

    assert result.pulse_status == "token_watch"
    assert result.candidate_score == 45
    assert result.score_band == "speculative"
    assert result.max_recommendation == "watch"


def test_low_score_eligible_snapshot_is_blocked_low_information() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(factor_snapshot=_snapshot(rank_score=29))

    assert result.pulse_status == "blocked_low_information"
    assert result.score_band == "blocked"
    assert result.max_recommendation == "ignore"


@pytest.mark.parametrize(
    "blocked_reasons",
    [
        ["liquidity_below_high_alert_floor"],
        ["holders_below_high_alert_floor"],
        ["liquidity_below_high_alert_floor", "holders_below_high_alert_floor"],
    ],
)
def test_blocked_reasons_from_hard_gates_reject_high_info(blocked_reasons: list[str]) -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(rank_score=35, eligible=False, blocked_reasons=blocked_reasons)
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert result.gate_reasons == blocked_reasons
    assert result.blocked_reasons == blocked_reasons
    assert result.hard_risks == blocked_reasons
    assert result.max_recommendation == "research"


def test_blocked_snapshot_below_30_is_low_information() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=20,
            eligible=False,
            blocked_reasons=["insufficient_independent_social_sources"],
        )
    )

    assert result.pulse_status == "blocked_low_information"
    assert result.score_band == "blocked"
    assert result.max_recommendation == "ignore"


def test_factor_risk_flags_are_recorded_without_runtime_context() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=80,
            eligible=True,
            market_risks=["liquidity_below_high_alert_floor"],
        )
    )

    assert result.pulse_status == "trade_candidate"
    assert result.risk_reasons == ["liquidity_below_high_alert_floor"]
    assert result.hard_risks == ["liquidity_below_high_alert_floor"]


def test_source_seed_or_no_target_snapshot_is_blocked() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=80,
            eligible=True,
            target_type=None,
            target_id=None,
            symbol=None,
        )
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert "missing_token_target" in result.blocked_reasons
    assert result.max_recommendation == "research"


def test_to_json_contains_gate_contract_for_agent_validation() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=50,
            eligible=False,
            blocked_reasons=["market_freshness_missing"],
        )
    )

    assert result.to_json() == {
        "pulse_status": "risk_rejected_high_info",
        "verdict": "risk_rejected_high_info",
        "candidate_score": 50.0,
        "score_band": "blocked",
        "gate_reasons": ["market_freshness_missing"],
        "risk_reasons": ["market_freshness_missing"],
        "hard_risks": ["market_freshness_missing"],
        "max_recommendation": "research",
        "eligible_for_high_alert": False,
        "blocked_reasons": ["market_freshness_missing"],
    }


def test_legacy_gate_runtime_arguments_are_not_supported() -> None:
    with pytest.raises(TypeError):
        gate_pulse_candidate_from_factor_snapshot(
            thesis={},
            radar_score={},
            market_context={},
            timeline_context={},
        )
