from __future__ import annotations

import time
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_freshness_health import PulseFreshnessHealthService
from gmgn_twitter_intel.domains.token_intel.interfaces import is_token_factor_snapshot

PUBLIC_SUMMARY_STATUSES = (
    "trade_candidate",
    "token_watch",
    "risk_rejected_high_info",
)
PUBLIC_DISPLAY_STATUSES = {
    "display_trade_candidate",
    "display_token_watch",
    "display_risk_rejected_high_info",
}
ALPHA_FAMILIES = ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk")


class SignalPulseService:
    def __init__(self, *, pulse_read: Any, pulse_runs: Any):
        self.pulse_read_repository = pulse_read
        self.pulse_runs_repository = pulse_runs

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
        page = self.pulse_read_repository.list_candidates(
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
        aggregate = self.pulse_read_repository.pulse_summary(window=window, scope=scope, q=q, handle=handle)
        candidate_count = int(aggregate.get("candidate_count") or 0)
        freshness_health = _freshness_health(self.pulse_read_repository, window=window, scope=scope)
        public_candidate_count = _first_int(
            aggregate.get("public_candidate_count"),
            aggregate.get("displayable_count"),
            freshness_health.get("public_candidates_4h"),
            candidate_count,
        )
        result_health = {
            "pulse_ready": public_candidate_count > 0,
            "public_ready": public_candidate_count > 0,
            "agent_worker_running": bool(agent_worker_running),
            "candidate_count": candidate_count,
            "public_candidate_count": public_candidate_count,
            "blocked_low_information_count": int(aggregate.get("blocked_low_information_count") or 0),
            "dead_job_count": int(aggregate.get("dead_job_count") or 0),
            "market_ready_rate": float(aggregate.get("market_ready_rate") or 0.0),
            **_health_passthrough(aggregate),
            **freshness_health,
        }
        result_health["pulse_ready"] = public_candidate_count > 0
        result_health["public_ready"] = public_candidate_count > 0
        result_health["public_candidate_count"] = public_candidate_count
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
        row = self.pulse_read_repository.candidate_by_id(candidate_id)
        if row is None:
            return None
        if not _is_displayable(row):
            return None
        item = pulse_item_from_row(row)
        item["stages"] = self._stages_for(row.get("agent_run_id"))
        return item

    def _stages_for(self, run_id: Any) -> dict[str, Any]:
        empty: dict[str, dict[str, Any] | None] = {
            "evidence_pack": None,
            "evidence_completeness_gate": None,
            "evidence_debate": None,
            "claim_verifier": None,
            "decision_maker": None,
            "recommendation_clipper": None,
            "deterministic_eval": None,
            "write_gate": None,
        }
        if not run_id:
            return empty
        try:
            steps = self.pulse_runs_repository.list_agent_run_steps(str(run_id))
        except Exception:
            return empty
        by_stage: dict[str, dict[str, Any]] = {}
        for step in steps:
            stage = step.get("stage")
            if stage not in empty:
                continue
            prior = by_stage.get(stage)
            if prior is None or _is_better_step(step, prior):
                by_stage[stage] = step
        result = dict(empty)
        for stage, step in by_stage.items():
            result[stage] = _stage_payload(step)
        return result


def _rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in page.get("items", []) if isinstance(row, dict)]


def _summary(aggregate: dict[str, Any]) -> dict[str, Any]:
    raw_summary = _dict(aggregate.get("summary"))
    counts: dict[str, Any] = {status: 0 for status in PUBLIC_SUMMARY_STATUSES}
    for status in PUBLIC_SUMMARY_STATUSES:
        if status in counts:
            counts[status] = int(raw_summary.get(status) or 0)
    counts["decision_route_counts"] = _int_dict(aggregate.get("decision_route_counts"))
    counts["decision_recommendation_counts"] = _int_dict(aggregate.get("decision_recommendation_counts"))
    counts["decision_abstain_reason_counts"] = _int_dict(aggregate.get("decision_abstain_reason_counts"))
    counts["decision_error_count"] = int(aggregate.get("decision_error_count") or 0)
    return counts


def _health_passthrough(aggregate: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "window",
        "scope",
        "since_hours",
        "publish_status",
        "reasons",
        "latest_packet_created_at_ms",
        "latest_agent_run_finished_at_ms",
        "latest_public_candidate_updated_at_ms",
        "latest_hidden_hold_candidate_updated_at_ms",
        "due_jobs",
        "claimed_jobs",
        "failed_jobs_4h",
        "agent_runs_4h",
        "agent_failed_4h",
        "agent_failure_rate_4h",
        "unknown_ref_failures_4h",
        "unknown_ref_failure_rate_4h",
        "unsupported_claim_failures_4h",
        "unsupported_claim_failure_rate_4h",
        "hidden_abstain_4h",
        "hidden_hold_publish_4h",
        "hidden_insufficient_evidence_4h",
        "public_candidates_4h",
    }
    return {key: aggregate[key] for key in keys if key in aggregate}


def _freshness_health(repository: Any, *, window: str, scope: str) -> dict[str, Any]:
    conn = getattr(repository, "conn", None)
    if conn is None:
        return {}
    try:
        return PulseFreshnessHealthService(conn).health(
            window=window,
            scope=scope,
            now_ms=int(time.time() * 1000),
            since_hours=4,
        )
    except Exception:
        return {
            "window": window,
            "scope": scope,
            "since_hours": 4,
            "publish_status": "degraded",
            "reasons": ["pulse_health_query_failed"],
        }


def _is_displayable(row: dict[str, Any]) -> bool:
    return (
        row.get("display_status") in PUBLIC_DISPLAY_STATUSES
        and bool(row.get("evidence_packet_hash"))
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
        "evidence_status": row.get("evidence_status"),
        "decision_status": row.get("decision_status"),
        "display_status": row.get("display_status"),
        "evidence_packet_hash": row.get("evidence_packet_hash"),
        "verdict": row.get("verdict"),
        "social_phase": row.get("social_phase"),
        "candidate_score": row.get("candidate_score"),
        "score_band": row.get("score_band"),
        "gate_reasons": _list(row.get("gate_reasons_json")),
        "risk_reasons": _list(row.get("risk_reasons_json")),
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "factor_snapshot": factor_snapshot,
        "decision": _decision(row),
        "gate": gate,
        "claim_verification": _dict(row.get("claim_verification_json")),
        "evidence_gate": _dict(row.get("evidence_gate_json")),
        "fact_card": _fact_card(factor_snapshot=factor_snapshot, gate=gate),
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


def _first_int(*values: Any) -> int:
    for value in values:
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


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
        "supporting_evidence_refs": _string_list(decision.get("supporting_evidence_refs")),
        "risk_evidence_refs": _string_list(decision.get("risk_evidence_refs")),
        "data_gap_refs": _string_list(decision.get("data_gap_refs")),
        "narrative_archetype": decision.get("narrative_archetype") or "",
        "narrative_thesis_zh": decision.get("narrative_thesis_zh") or "",
        "bull_view": _bull_bear_view(decision.get("bull_view")),
        "bear_view": _bull_bear_view(decision.get("bear_view")),
        "playbook": _playbook(decision.get("playbook")),
        "evidence_event_urls": _string_string_map(decision.get("evidence_event_urls")),
    }


def _bull_bear_view(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    strength = value.get("strength")
    if strength not in ("absent", "weak", "moderate", "strong"):
        return None
    return {
        "strength": strength,
        "thesis_zh": str(value.get("thesis_zh") or ""),
        "supporting_event_ids": _string_list(value.get("supporting_event_ids")),
    }


def _playbook(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    horizon = value.get("monitoring_horizon")
    if horizon not in ("1h", "4h", "24h"):
        return None
    return {
        "has_playbook": bool(value.get("has_playbook")),
        "watch_signals": _string_list(value.get("watch_signals")),
        "exit_triggers": _string_list(value.get("exit_triggers")),
        "monitoring_horizon": horizon,
    }


def _string_string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def _valid_factor_snapshot(value: Any) -> bool:
    return is_token_factor_snapshot(value)


def _fact_card(*, factor_snapshot: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
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
        **_market_facts(factor_snapshot),
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


def _market_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    market = _dict(snapshot.get("market"))
    anchor = _dict(market.get("event_anchor"))
    latest = _dict(market.get("decision_latest"))
    facts: dict[str, Any] = {}
    for key in ("price_usd", "market_cap_usd", "liquidity_usd", "holders", "volume_24h_usd"):
        value = latest.get(key, _MISSING)
        if value is _MISSING or value is None:
            value = anchor.get(key, _MISSING)
        if value is not _MISSING and value is not None:
            facts[key] = value
    return facts


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _is_better_step(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    candidate_ok = candidate.get("status") == "ok"
    existing_ok = existing.get("status") == "ok"
    if candidate_ok != existing_ok:
        return candidate_ok
    return int(candidate.get("attempt_index") or 0) >= int(existing.get("attempt_index") or 0)


def _stage_payload(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": step.get("stage"),
        "route": step.get("route"),
        "status": step.get("status"),
        "model": step.get("model"),
        "started_at_ms": step.get("started_at_ms"),
        "finished_at_ms": step.get("finished_at_ms"),
        "latency_ms": step.get("latency_ms"),
        "attempt_index": step.get("attempt_index"),
        "response": _dict(step.get("response_json")) or step.get("response_json"),
        "error": step.get("error"),
    }
