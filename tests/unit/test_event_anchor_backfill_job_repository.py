from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.repositories.event_anchor_backfill_job_repository import (
    EventAnchorBackfillJobRepository,
)
from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture


def test_enqueue_for_pending_capture_writes_control_plane_job() -> None:
    conn = _ScriptedConnection([])
    capture = _pending_capture()

    EventAnchorBackfillJobRepository(conn).enqueue_for_capture(capture, active_window_ms=300_000)

    sql = conn.sql[-1]
    assert "INSERT INTO event_anchor_backfill_jobs" in sql
    assert "ON CONFLICT(event_id, intent_id) DO NOTHING" in sql
    assert conn.params[-1]["event_id"] == "event-1"
    assert conn.params[-1]["status"] == "pending"
    assert conn.params[-1]["active_until_ms"] == capture.created_at_ms + 300_000


def test_enqueue_ignores_non_pending_captures() -> None:
    conn = _ScriptedConnection([])
    capture = _pending_capture(capture_method="tier3_inline", capture_reason="fresh_tick", tick_id="tick-1")

    EventAnchorBackfillJobRepository(conn).enqueue_for_capture(capture, active_window_ms=300_000)

    assert conn.sql == []


def test_list_due_reads_jobs_not_enriched_event_rows() -> None:
    conn = _ScriptedConnection([[{"event_id": "event-1", "intent_id": "intent-1"}]])

    rows = EventAnchorBackfillJobRepository(conn).list_due(limit=25, now_ms=1_700_000_001_000, min_age_ms=250)

    assert rows == [{"event_id": "event-1", "intent_id": "intent-1"}]
    sql = conn.sql[-1]
    assert "FROM event_anchor_backfill_jobs" in sql
    assert "FROM enriched_events" not in sql
    assert "status = 'pending'" in sql
    assert "next_run_at_ms <= %(now_ms)s" in sql
    assert "created_at_ms <= %(ready_before_ms)s" in sql


def test_reschedule_increments_attempts_and_keeps_job_pending() -> None:
    conn = _ScriptedConnection([])

    EventAnchorBackfillJobRepository(conn).reschedule(
        event_id="event-1",
        intent_id="intent-1",
        reason="rate_limited",
        now_ms=1_700_000_001_000,
        next_run_at_ms=1_700_000_011_000,
    )

    sql = conn.sql[-1]
    assert "UPDATE event_anchor_backfill_jobs" in sql
    assert "attempt_count = attempt_count + 1" in sql
    assert "status = 'pending'" in sql
    assert conn.params[-1]["reason"] == "rate_limited"


def test_mark_ready_jobs_done_reconciles_control_state_from_ready_facts() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 4

    marked = EventAnchorBackfillJobRepository(conn).mark_ready_jobs_done(limit=25, now_ms=1_700_000_001_000)

    sql = conn.sql[-1]
    assert marked == 4
    assert "JOIN enriched_events anchors" in sql
    assert "anchors.capture_method <> 'unavailable'" in sql
    assert "jobs.status <> 'done'" in sql
    assert "SET status = 'done'" in sql


class _ScriptedConnection:
    def __init__(self, results: list[dict[str, Any] | list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        return result


def _pending_capture(
    *,
    capture_method: str = "unavailable",
    capture_reason: str = "pending_backfill",
    tick_id: str | None = None,
) -> EnrichedEventCapture:
    return EnrichedEventCapture(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        target_type="chain_token",
        target_id="solana:abc",
        t_event_ms=1_700_000_000_000,
        tick_observed_at_ms=None if tick_id is None else 1_700_000_000_100,
        tick_id=tick_id,
        tick_lag_ms=None if tick_id is None else 100,
        capture_method=capture_method,  # type: ignore[arg-type]
        capture_reason=capture_reason,
        created_at_ms=1_700_000_000_200,
    )
