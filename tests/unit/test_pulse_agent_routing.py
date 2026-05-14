from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.services.agent_routing import compute_completeness, route_decision_context
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION


def test_unresolved_token_target_routes_research_only_without_llm() -> None:
    snapshot = _snapshot(target_id=None, decision_latest=None)

    assert route_decision_context({"candidate_type": "token_target", "factor_snapshot": snapshot}) == "research_only"

    completeness = compute_completeness(snapshot, route="research_only")
    assert completeness.hard_blocked is True
    assert completeness.blockers == ("research_only_no_resolved_target",)


def test_missing_decision_latest_hard_blocks_token_target() -> None:
    snapshot = _snapshot(decision_latest={})

    route = route_decision_context({"candidate_type": "token_target", "factor_snapshot": snapshot})
    completeness = compute_completeness(snapshot, route=route)

    assert route == "meme"
    assert completeness.hard_blocked is True
    assert "decision_latest_missing" in completeness.blockers


def test_meme_dex_floor_unverified_hard_blocks() -> None:
    snapshot = _snapshot(
        target_market_type="dex",
        readiness={"missing_fields": ["holders", "liquidity_usd"], "stale_fields": []},
    )

    route = route_decision_context({"candidate_type": "token_target", "factor_snapshot": snapshot})
    completeness = compute_completeness(snapshot, route=route)

    assert route == "meme"
    assert completeness.hard_blocked is True
    assert completeness.missing_fields == ("holders", "liquidity_usd")
    assert "dex_floor_unverified" in completeness.blockers


def test_cex_complete_snapshot_routes_cex() -> None:
    snapshot = _snapshot(target_market_type="cex", decision_latest={"price_usd": 1.2, "venue_id": "binance"})

    route = route_decision_context({"candidate_type": "token_target", "factor_snapshot": snapshot})
    completeness = compute_completeness(snapshot, route=route)

    assert route == "cex"
    assert completeness.hard_blocked is False
    assert completeness.score == 1.0


def test_meme_complete_snapshot_routes_meme() -> None:
    snapshot = _snapshot(target_market_type="dex")

    route = route_decision_context({"candidate_type": "token_target", "factor_snapshot": snapshot})
    completeness = compute_completeness(snapshot, route=route)

    assert route == "meme"
    assert completeness.hard_blocked is False
    assert completeness.score == 1.0


def _snapshot(
    *,
    target_id: str | None = "asset:pepe",
    target_market_type: str | None = "dex",
    decision_latest: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    cohort_status: str = "ready",
) -> dict[str, object]:
    latest = (
        {
            "target_type": "Asset",
            "target_id": target_id,
            "price_usd": 0.01,
            "holders": 1000,
            "liquidity_usd": 100_000,
            "market_cap_usd": 1_000_000,
            "volume_24h_usd": 250_000,
            "source": "decision_latest",
        }
        if target_id
        else None
    )
    if decision_latest is not None:
        latest = decision_latest
    resolved_readiness = readiness or {"missing_fields": [], "stale_fields": []}
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {
            "target_type": "Asset" if target_id else None,
            "target_id": target_id,
            "target_market_type": target_market_type,
            "symbol": "PEPE" if target_id else None,
        },
        "market": {
            "event_anchor": None,
            "decision_latest": latest,
            "readiness": resolved_readiness,
        },
        "gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": _family(),
            "social_propagation": _family(),
            "semantic_catalyst": _family(),
            "timing_risk": _family(),
        },
        "normalization": {
            "status": "ranked",
            "cohort_status": cohort_status,
            "cohort": {"size": 12, "in_cohort": bool(target_id)},
            "factor_ranks": {},
            "alpha_rank": 0.7,
        },
        "composite": {"rank_score": 70, "recommended_decision": "high_alert"},
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_800_000},
    }


def _family() -> dict[str, object]:
    return {
        "raw_score": 70,
        "score": 70,
        "weight": 0.25,
        "data_health": "ready",
        "facts": {},
        "factors": {},
    }
