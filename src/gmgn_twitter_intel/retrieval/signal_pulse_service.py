from __future__ import annotations

from typing import Any

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
            "items": [_item(row) for row in page_rows],
            "returned_count": len(page_rows),
            "has_more": page.get("next_cursor") is not None,
            "next_cursor": page.get("next_cursor"),
        }

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
    return row.get("pulse_status") in DISPLAY_STATUSES and row.get("verdict") != "blocked_low_information"


def _item(row: dict[str, Any]) -> dict[str, Any]:
    thesis = _dict(row.get("thesis_json"))
    return {
        "candidate_id": row.get("candidate_id"),
        "candidate_type": row.get("candidate_type"),
        "subject_key": row.get("subject_key"),
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
        "summary_zh": _text(thesis.get("summary_zh")),
        "why_now_zh": _text(thesis.get("why_now_zh")),
        "bull_case_zh": _list(thesis.get("bull_case_zh")),
        "bear_case_zh": _list(thesis.get("bear_case_zh")),
        "confirmation_triggers_zh": _list(thesis.get("confirmation_triggers_zh")),
        "invalidation_triggers_zh": _list(thesis.get("invalidation_triggers_zh")),
        "top_risks": _list(thesis.get("top_risks")),
        "gate_reasons": _list(row.get("gate_reasons_json")),
        "risk_reasons": _list(row.get("risk_reasons_json")),
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "radar_score_json": _dict(row.get("radar_score_json")),
        "market_context_json": _dict(row.get("market_context_json")),
        "thesis_json": thesis,
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


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
