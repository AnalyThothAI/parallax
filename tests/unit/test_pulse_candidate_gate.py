from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import (
    gate_pulse_candidate_from_factor_snapshot,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION


def _snapshot(
    *,
    rank_score: int = 73,
    eligible: bool = True,
    blocked_reasons: list[str] | None = None,
    target_type: str | None = "Asset",
    target_id: str | None = "asset-1",
    symbol: str | None = "TEST",
    risk_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {
            "target_type": target_type,
            "target_id": target_id,
            "target_market_type": "dex" if target_id else None,
            "symbol": symbol,
        },
        "market": {
            "market_status": "anchored" if target_id else "missing",
            "price_change_status": "live_not_persisted" if target_id else "missing_anchor",
            "provider": "okx" if target_id else None,
            "anchor_price_usd": 0.42 if target_id else None,
            "social_signal_start_ms": 1_700_000_000_000,
            "event_price_readiness": {"status": "ready" if target_id else "missing"},
        },
        "gates": {
            "eligible_for_high_alert": eligible,
            "blocked_reasons": blocked_reasons or [],
            "risk_reasons": risk_reasons or [],
            "max_decision": "high_alert" if eligible else "watch",
        },
        "data_health": {
            "identity": "ready" if target_id else "missing",
            "market": "ready" if target_id else "no_resolved_target",
            "social": "ready",
            "alpha": "ready",
        },
        "families": {
            "social_heat": _family(
                raw_score=rank_score,
                score=rank_score,
                weight=0.35,
                facts={"mentions_1h": 8, "unique_authors": 4, "watched_mentions": 1},
                factors={},
            ),
            "social_propagation": _family(
                raw_score=rank_score,
                score=rank_score,
                weight=0.3,
                facts={"independent_authors": 4},
                factors={
                    "independent_authors": {
                        "family": "social_propagation",
                        "key": "independent_authors",
                        "risk_flags": risk_reasons or [],
                    },
                },
            ),
            "semantic_catalyst": _family(
                raw_score=rank_score,
                score=rank_score,
                weight=0.25,
                facts={"phase": "ignition"},
                factors={},
            ),
            "timing_risk": _family(
                raw_score=rank_score,
                score=rank_score,
                weight=0.1,
                facts={"price_change_status": "ready"},
                factors={},
            ),
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "family_scores": {
                "social_heat": rank_score,
                "social_propagation": rank_score,
                "semantic_catalyst": rank_score,
                "timing_risk": rank_score,
            },
            "rank_score": rank_score,
            "recommended_decision": "high_alert" if rank_score >= 70 else "watch",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_800_000},
    }


def _family(
    *,
    raw_score: int,
    score: int,
    weight: float,
    facts: dict[str, object],
    factors: dict[str, object],
) -> dict[str, object]:
    return {
        "raw_score": raw_score,
        "score": score,
        "weight": weight,
        "data_health": "ready",
        "facts": facts,
        "factors": factors,
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
def test_blocked_reasons_from_gates_reject_high_info(blocked_reasons: list[str]) -> None:
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


def test_alpha_risk_flags_are_recorded_without_runtime_context() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=80,
            eligible=True,
            risk_reasons=["duplicate_text_share_high"],
        )
    )

    assert result.pulse_status == "trade_candidate"
    assert result.risk_reasons == ["duplicate_text_share_high"]
    assert result.hard_risks == []


def test_source_seed_or_no_target_snapshot_is_blocked() -> None:
    result = gate_pulse_candidate_from_factor_snapshot(
        factor_snapshot=_snapshot(
            rank_score=80,
            eligible=True,
            blocked_reasons=["identity_unresolved"],
            target_type=None,
            target_id=None,
            symbol=None,
        )
    )

    assert result.pulse_status == "risk_rejected_high_info"
    assert "identity_unresolved" in result.blocked_reasons
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


def test_rejects_factor_snapshot_with_legacy_hard_gates() -> None:
    snapshot = _snapshot(rank_score=80)
    snapshot["hard_gates"] = {"eligible_for_high_alert": True, "blocked_reasons": []}

    with pytest.raises(ValueError, match="hard_gates"):
        gate_pulse_candidate_from_factor_snapshot(factor_snapshot=snapshot)


def test_rejects_factor_snapshot_missing_v3_keys() -> None:
    snapshot = _snapshot(rank_score=80)
    snapshot.pop("data_health")

    with pytest.raises(ValueError, match="data_health"):
        gate_pulse_candidate_from_factor_snapshot(factor_snapshot=snapshot)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda snapshot: snapshot["families"].__setitem__("market_quality", {"facts": {}}), "market_quality"),
        (lambda snapshot: snapshot.pop("normalization"), "normalization"),
        (lambda snapshot: snapshot.pop("provenance"), "provenance"),
        (lambda snapshot: snapshot.__setitem__("legacy_score", {"score": 100}), "legacy_score"),
    ],
)
def test_rejects_malformed_v3_snapshot_shape(mutate, match: str) -> None:
    snapshot = _snapshot(rank_score=80)
    mutate(snapshot)

    with pytest.raises(ValueError, match=match):
        gate_pulse_candidate_from_factor_snapshot(factor_snapshot=snapshot)


def test_legacy_gate_runtime_arguments_are_not_supported() -> None:
    with pytest.raises(TypeError):
        gate_pulse_candidate_from_factor_snapshot(
            thesis={},
            radar_score={},
            market_context={},
            timeline_context={},
        )
