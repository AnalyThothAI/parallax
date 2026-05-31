from __future__ import annotations

from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.pulse_edge_events import (
    build_pulse_edge_state,
    diff_pulse_edge_events,
    pulse_edge_signature,
)


def test_first_observation_emits_status_edge_and_stable_state() -> None:
    state = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )

    assert state["candidate_type"] == "token_target"
    assert state["pulse_status"] == "trade_candidate"
    assert state["score_band"] == "high_conviction"
    assert state["recommended_decision"] == "high_alert"
    assert state["watched_confirmation"] is True
    assert diff_pulse_edge_events({}, state) == ["pulse_status_changed"]
    assert pulse_edge_signature(state).startswith("sha256:")


def test_diff_reports_only_material_state_edges() -> None:
    previous = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger-a",
        timeline_signature="sha256:timeline-a",
        factor_snapshot=_snapshot(rank_score=61, watched_mentions=0, recommended_decision="watch"),
        gate=_gate(status="token_watch", score_band="watch"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )
    current = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger-b",
        timeline_signature="sha256:timeline-b",
        factor_snapshot=_snapshot(
            rank_score=88,
            watched_mentions=2,
            recommended_decision="high_alert",
            hard_risks=["crowded_trade"],
        ),
        gate=_gate(status="trade_candidate", score_band="high_conviction", hard_risks=["crowded_trade"]),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )

    assert diff_pulse_edge_events(previous, current) == [
        "pulse_status_changed",
        "score_band_crossed",
        "hard_risk_added",
        "recommended_decision_changed",
        "watched_confirmation_appeared",
        "trigger_evidence_changed",
        "timeline_evidence_changed",
    ]
    assert pulse_edge_signature(previous) != pulse_edge_signature(current)


def test_diff_reports_material_evidence_signature_changes() -> None:
    previous = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger-a",
        timeline_signature="sha256:timeline-a",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )
    current = {
        **previous,
        "trigger_signature": "sha256:trigger-b",
        "timeline_signature": "sha256:timeline-b",
    }

    assert diff_pulse_edge_events(previous, current) == [
        "trigger_evidence_changed",
        "timeline_evidence_changed",
    ]


def test_diff_reports_independent_author_bucket_change() -> None:
    previous = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1, independent_authors=2),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )
    current = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1, independent_authors=6),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )

    assert diff_pulse_edge_events(previous, current) == ["independent_author_bucket_changed"]


def test_diff_reports_unchanged_signatures_as_no_events() -> None:
    previous = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )

    assert diff_pulse_edge_events(previous, dict(previous)) == []


def test_diff_reports_pulse_version_bump_without_other_state_changes() -> None:
    previous = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v1",
        gate_version="gate-v1",
    )
    current = build_pulse_edge_state(
        candidate_id="pulse-1",
        candidate_type="token_target",
        target_type="Asset",
        target_id="asset:pepe",
        window="1h",
        scope="all",
        trigger_signature="sha256:trigger",
        timeline_signature="sha256:timeline",
        factor_snapshot=_snapshot(rank_score=82, watched_mentions=1),
        gate=_gate(status="trade_candidate", score_band="high_conviction"),
        pulse_version="pulse-v2",
        gate_version="gate-v1",
    )

    assert diff_pulse_edge_events(previous, current) == ["pulse_version_bumped"]
    assert pulse_edge_signature(previous) != pulse_edge_signature(current)


def _gate(*, status: str, score_band: str, hard_risks: list[str] | None = None) -> PulseGateResult:
    return PulseGateResult(
        pulse_status=status,
        verdict=status,
        candidate_score=88.0,
        score_band=score_band,
        gate_reasons=["factor_snapshot_watch_gate_passed"],
        risk_reasons=hard_risks or [],
        hard_risks=hard_risks or [],
        max_recommendation="trade_candidate" if status == "trade_candidate" else "watch",
        eligible_for_high_alert=not hard_risks,
        blocked_reasons=[],
    )


def _snapshot(
    *,
    rank_score: int,
    watched_mentions: int,
    recommended_decision: str = "high_alert",
    hard_risks: list[str] | None = None,
    independent_authors: int = 4,
) -> dict:
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "target_market_type": "dex",
            "symbol": "PEPE",
        },
        "market": {"decision_latest": {}, "readiness": {"missing_fields": [], "stale_fields": []}},
        "gates": {
            "eligible_for_high_alert": not hard_risks,
            "blocked_reasons": hard_risks or [],
            "risk_reasons": hard_risks or [],
            "max_decision": recommended_decision,
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": {
                "score": rank_score,
                "facts": {"watched_mentions": watched_mentions, "unique_authors": 4},
            },
            "social_propagation": {"score": 70, "facts": {"independent_authors": independent_authors}},
            "semantic_catalyst": {"score": 70, "facts": {}},
            "timing_risk": {"score": 60, "facts": {}},
        },
        "normalization": {"status": "ready"},
        "composite": {"rank_score": rank_score, "recommended_decision": recommended_decision},
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
    }
