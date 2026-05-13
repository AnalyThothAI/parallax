from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import is_token_factor_snapshot

SUMMARY_STATUSES = (
    "trade_candidate",
    "token_watch",
    "theme_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
)
DISPLAY_STATUSES = {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}
ALPHA_FAMILIES = ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk")


class SignalPulseService:
    def __init__(self, *, pulse: Any, harness: Any | None = None):
        self.pulse_repository = pulse
        self.harness = harness

    def pulse(
        self,
        *,
        window: str,
        scope: str,
        status: str | None,
        handle: str | None,
        q: str | None,
        limit: int,
        cursor: str | None,
        agent_worker_running: bool,
    ) -> dict[str, Any]:
        page = self.pulse_repository.list_candidates(
            window=window,
            scope=scope,
            status=status,
            limit=limit,
            cursor=cursor,
            q=q,
            handle=handle,
            displayable_only=True,
        )
        page_rows = [row for row in _rows(page) if _is_displayable(row)]
        aggregate = self.pulse_repository.pulse_summary(window=window, scope=scope, q=q, handle=handle)
        candidate_count = int(aggregate.get("candidate_count") or 0)
        result_health = {
            "pulse_ready": candidate_count > 0,
            "agent_worker_running": bool(agent_worker_running),
            "candidate_count": candidate_count,
            "blocked_low_information_count": int(aggregate.get("blocked_low_information_count") or 0),
            "dead_job_count": int(aggregate.get("dead_job_count") or 0),
            "market_ready_rate": float(aggregate.get("market_ready_rate") or 0.0),
            "settlement_coverage": self._settlement_coverage(),
        }
        return {
            "query": {
                "window": window,
                "scope": scope,
                "status": status,
                "handle": handle,
                "q": q,
            },
            "health": result_health,
            "summary": _summary(aggregate),
            "items": [pulse_item_from_row(row) for row in page_rows],
            "returned_count": len(page_rows),
            "has_more": page.get("next_cursor") is not None,
            "next_cursor": page.get("next_cursor"),
        }

    def candidate(self, *, candidate_id: str) -> dict[str, Any] | None:
        row = self.pulse_repository.candidate_by_id(candidate_id)
        if row is None:
            return None
        if not _is_displayable(row):
            return None
        return pulse_item_from_row(row)

    def _settlement_coverage(self) -> float | None:
        if self.harness is None:
            return 0.0
        try:
            health = self.harness.health()
        except Exception:
            return 0.0
        coverage = health.get("settlement_coverage")
        if coverage is None:
            return None
        return float(coverage)


def _rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in page.get("items", []) if isinstance(row, dict)]


def _summary(aggregate: dict[str, Any]) -> dict[str, Any]:
    raw_summary = _dict(aggregate.get("summary"))
    counts: dict[str, Any] = {status: 0 for status in SUMMARY_STATUSES}
    for status in SUMMARY_STATUSES:
        if status in counts:
            counts[status] = int(raw_summary.get(status) or 0)
    counts["decision_route_counts"] = _int_dict(aggregate.get("decision_route_counts"))
    counts["decision_recommendation_counts"] = _int_dict(aggregate.get("decision_recommendation_counts"))
    counts["decision_abstain_reason_counts"] = _int_dict(aggregate.get("decision_abstain_reason_counts"))
    counts["decision_error_count"] = int(aggregate.get("decision_error_count") or 0)
    return counts


def _is_displayable(row: dict[str, Any]) -> bool:
    return (
        row.get("pulse_status") in DISPLAY_STATUSES
        and row.get("verdict") != "blocked_low_information"
        and row.get("decision_recommendation") != "abstain"
        and _valid_factor_snapshot(row.get("factor_snapshot_json"))
    )


def pulse_item_from_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _dict(row.get("factor_snapshot_json"))
    gate = _dict(factor_snapshot.get("gates"))
    return {
        "candidate_id": row.get("candidate_id"),
        "candidate_type": row.get("candidate_type"),
        "subject_key": row.get("subject_key"),
        "subject": _dict(factor_snapshot.get("subject")),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "symbol": row.get("symbol"),
        "window": row.get("window"),
        "scope": row.get("scope"),
        "pulse_status": row.get("pulse_status"),
        "verdict": row.get("verdict"),
        "social_phase": row.get("social_phase"),
        "narrative_type": row.get("narrative_type"),
        "candidate_score": row.get("candidate_score"),
        "score_band": row.get("score_band"),
        "gate_reasons": _list(row.get("gate_reasons_json")),
        "risk_reasons": _list(row.get("risk_reasons_json")),
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "factor_snapshot": factor_snapshot,
        "decision": _decision(row),
        "gate": gate,
        "fact_card": _fact_card(row=row, factor_snapshot=factor_snapshot, gate=gate),
        "agent_run_id": row.get("agent_run_id"),
        "pulse_version": row.get("pulse_version"),
        "gate_version": row.get("gate_version"),
        "prompt_version": row.get("prompt_version"),
        "schema_version": row.get("schema_version"),
        "created_at_ms": row.get("created_at_ms"),
        "updated_at_ms": row.get("updated_at_ms"),
        "playbooks": [],
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_dict(value: Any) -> dict[str, int]:
    payload = _dict(value)
    return {str(key): int(count or 0) for key, count in payload.items()}


def _decision(row: dict[str, Any]) -> dict[str, Any]:
    decision = _dict(row.get("decision_json"))
    return {
        "route": row.get("decision_route") or decision.get("route"),
        "recommendation": row.get("decision_recommendation") or decision.get("recommendation"),
        "confidence": row.get("decision_confidence"),
        "abstain_reason": row.get("decision_abstain_reason") or decision.get("abstain_reason"),
        "stage_count": int(row.get("decision_stage_count") or 0),
        "summary_zh": decision.get("summary_zh") or "",
        "invalidation_conditions": _string_list(decision.get("invalidation_conditions")),
        "residual_risks": _string_list(decision.get("residual_risks")),
        "evidence_event_ids": _string_list(decision.get("evidence_event_ids")),
    }


def _valid_factor_snapshot(value: Any) -> bool:
    return is_token_factor_snapshot(value)


def _fact_card(*, row: dict[str, Any], factor_snapshot: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    subject = _dict(factor_snapshot.get("subject"))
    data_health = _dict(factor_snapshot.get("data_health"))
    composite = _dict(factor_snapshot.get("composite"))
    attention_facts = _family_facts(factor_snapshot, "social_heat")
    diffusion_facts = _family_facts(factor_snapshot, "social_propagation")
    return {
        "rank_score": composite.get("rank_score"),
        "recommended_decision": composite.get("recommended_decision"),
        "target_market_type": subject.get("target_market_type"),
        "data_health": data_health,
        "alpha_family_scores": _alpha_family_scores(factor_snapshot),
        "market_status": data_health.get("market"),
        "mentions_1h": attention_facts.get("mentions_1h"),
        "unique_authors": diffusion_facts.get("independent_authors") or attention_facts.get("unique_authors"),
        "watched_mentions": attention_facts.get("watched_mentions"),
        "eligible_for_high_alert": gate.get("eligible_for_high_alert"),
        "blocked_reasons": _list(gate.get("blocked_reasons")),
        **_row_market_facts(row),
    }


def _alpha_family_scores(snapshot: dict[str, Any]) -> dict[str, Any]:
    composite_scores = _dict(_dict(snapshot.get("composite")).get("family_scores"))
    if composite_scores:
        return {family: composite_scores.get(family) for family in ALPHA_FAMILIES}
    families = _dict(snapshot.get("families"))
    return {family: _dict(families.get(family)).get("score") for family in ALPHA_FAMILIES}


def _family_facts(snapshot: dict[str, Any], family: str) -> dict[str, Any]:
    families = _dict(snapshot.get("families"))
    family_payload = _dict(families.get(family))
    return _dict(family_payload.get("facts"))


_MISSING = object()


def _row_market_facts(row: dict[str, Any]) -> dict[str, Any]:
    anchor = _dict(row.get("anchor_price"))
    facts: dict[str, Any] = {}
    for key in ("price_usd", "market_cap_usd", "liquidity_usd", "holders", "volume_24h_usd"):
        value = anchor.get(key, _MISSING)
        if value is _MISSING and key in row:
            value = row.get(key)
        if value is not _MISSING:
            facts[key] = value
    return facts


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
