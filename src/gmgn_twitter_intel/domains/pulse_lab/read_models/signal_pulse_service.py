from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION

SUMMARY_STATUSES = (
    "trade_candidate",
    "token_watch",
    "theme_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
)
DISPLAY_STATUSES = {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}


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


def _summary(aggregate: dict[str, Any]) -> dict[str, int]:
    raw_summary = _dict(aggregate.get("summary"))
    counts = {status: 0 for status in SUMMARY_STATUSES}
    for status in SUMMARY_STATUSES:
        if status in counts:
            counts[status] = int(raw_summary.get(status) or 0)
    return counts


def _is_displayable(row: dict[str, Any]) -> bool:
    return (
        row.get("pulse_status") in DISPLAY_STATUSES
        and row.get("verdict") != "blocked_low_information"
        and _valid_factor_snapshot(row.get("factor_snapshot_json"))
    )


def pulse_item_from_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _dict(row.get("factor_snapshot_json"))
    gate = _dict(row.get("gate_json"))
    agent_recommendation = _dict(row.get("agent_recommendation_json"))
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
        "agent_recommendation": agent_recommendation,
        "gate": gate,
        "fact_card": {
            "market_cap_usd": _factor_raw(factor_snapshot, "market_quality", "market_cap_usd"),
            "liquidity_usd": _factor_raw(factor_snapshot, "market_quality", "liquidity_usd"),
            "holders": _factor_raw(factor_snapshot, "market_quality", "holders"),
            "volume_24h_usd": _factor_raw(factor_snapshot, "market_quality", "volume_24h_usd"),
            "market_status": _factor_raw(factor_snapshot, "market_quality", "market_status"),
            "mentions_1h": _factor_raw(factor_snapshot, "social_attention", "mentions_1h"),
            "unique_authors": _factor_raw(factor_snapshot, "social_quality", "independent_authors")
            or _factor_raw(factor_snapshot, "social_attention", "unique_authors"),
            "watched_mentions": _factor_raw(factor_snapshot, "social_attention", "watched_mentions"),
            "eligible_for_high_alert": gate.get("eligible_for_high_alert"),
            "blocked_reasons": _list(gate.get("blocked_reasons")),
        },
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


def _valid_factor_snapshot(value: Any) -> bool:
    snapshot = _dict(value)
    return (
        bool(snapshot)
        and snapshot.get("schema_version") == TOKEN_FACTOR_SNAPSHOT_VERSION
        and isinstance(snapshot.get("subject"), dict)
        and isinstance(snapshot.get("families"), dict)
        and isinstance(snapshot.get("hard_gates"), dict)
    )


def _factor_raw(snapshot: dict[str, Any], family: str, key: str) -> Any:
    families = _dict(snapshot.get("families"))
    family_payload = _dict(families.get(family))
    facts = _dict(family_payload.get("facts"))
    return facts.get(key)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
