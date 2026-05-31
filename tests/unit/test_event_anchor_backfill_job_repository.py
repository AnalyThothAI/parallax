from __future__ import annotations

import inspect
from typing import Any

from parallax.domains.asset_market.repositories.event_anchor_backfill_job_repository import (
    EventAnchorBackfillJobRepository,
)
from parallax.domains.asset_market.types import EnrichedEventCapture


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


def test_event_anchor_claim_due_moves_pending_to_running() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "event_id": "event-1",
                    "intent_id": "intent-1",
                    "status": "running",
                    "attempt_count": 1,
                    "lease_owner": "worker-a",
                    "leased_until_ms": 1_700_000_061_000,
                }
            ]
        ]
    )

    rows = EventAnchorBackfillJobRepository(conn).claim_due(
        limit=25,
        now_ms=1_700_000_001_000,
        min_age_ms=250,
        lease_owner="worker-a",
        lease_ms=60_000,
    )

    assert rows == [
        {
            "event_id": "event-1",
            "intent_id": "intent-1",
            "status": "running",
            "attempt_count": 1,
            "lease_owner": "worker-a",
            "leased_until_ms": 1_700_000_061_000,
        }
    ]
    sql = conn.sql[-1]
    assert "WITH due AS" in sql
    assert "UPDATE event_anchor_backfill_jobs AS jobs" in sql
    assert "SET status = 'running'" in sql
    assert "attempt_count = attempt_count + 1" in sql
    assert "lease_owner = %(lease_owner)s" in sql
    assert "leased_until_ms = %(leased_until_ms)s" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "FROM event_anchor_backfill_jobs" in sql
    assert "FROM enriched_events" not in sql
    assert "status = 'pending'" in sql
    assert "next_run_at_ms <= %(now_ms)s" in sql
    assert "created_at_ms <= %(ready_before_ms)s" in sql
    assert conn.params[-1]["lease_owner"] == "worker-a"
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_061_000


def test_event_anchor_mark_done_requires_lease_owner_and_attempt() -> None:
    conn = _ScriptedConnection(
        [
            None,
            {"event_id": "event-1", "intent_id": "intent-1"},
        ]
    )

    wrong_owner = EventAnchorBackfillJobRepository(conn).mark_done(
        event_id="event-1",
        intent_id="intent-1",
        now_ms=1_700_000_001_000,
        lease_owner="worker-b",
        attempt_count=1,
    )
    matching_owner = EventAnchorBackfillJobRepository(conn).mark_done(
        event_id="event-1",
        intent_id="intent-1",
        now_ms=1_700_000_001_000,
        lease_owner="worker-a",
        attempt_count=1,
    )

    assert wrong_owner is False
    assert matching_owner is True
    sql = conn.sql[-1]
    assert "status = 'done'" in sql
    assert "lease_owner = NULL" in sql
    assert "leased_until_ms = NULL" in sql
    assert "status = 'running'" in sql
    assert "lease_owner = %(lease_owner)s" in sql
    assert "attempt_count = %(attempt_count)s" in sql
    assert conn.params[-1]["lease_owner"] == "worker-a"
    assert conn.params[-1]["attempt_count"] == 1


def test_reschedule_uses_claim_guard_without_incrementing_attempts() -> None:
    conn = _ScriptedConnection([{"event_id": "event-1", "intent_id": "intent-1"}])

    rescheduled = EventAnchorBackfillJobRepository(conn).reschedule(
        event_id="event-1",
        intent_id="intent-1",
        reason="rate_limited",
        now_ms=1_700_000_001_000,
        next_run_at_ms=1_700_000_011_000,
        lease_owner="worker-a",
        attempt_count=1,
    )

    assert rescheduled is True
    sql = conn.sql[-1]
    assert "UPDATE event_anchor_backfill_jobs" in sql
    assert "attempt_count = attempt_count + 1" not in sql
    assert "status = 'pending'" in sql
    assert "lease_owner = NULL" in sql
    assert "leased_until_ms = NULL" in sql
    assert "status = 'running'" in sql
    assert "lease_owner = %(lease_owner)s" in sql
    assert "attempt_count = %(attempt_count)s" in sql
    assert conn.params[-1]["reason"] == "rate_limited"


def test_mark_terminal_writes_operator_terminal_evidence() -> None:
    conn = _ScriptedConnection(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "status": "failed",
                "attempt_count": 3,
                "created_at_ms": 1_700_000_000_000,
                "updated_at_ms": 1_700_000_001_000,
            },
            None,
            {"terminal_generation": 1},
            {"terminal_id": "terminal-1"},
        ]
    )

    marked = EventAnchorBackfillJobRepository(conn).mark_terminal(
        event_id="event-1",
        intent_id="intent-1",
        status="failed",
        reason="provider_no_quote",
        now_ms=1_700_000_001_000,
        lease_owner="worker-a",
        attempt_count=3,
    )

    assert marked is True
    assert "RETURNING *" in conn.sql[0]
    assert "status = 'running'" in conn.sql[0]
    assert "lease_owner = %(lease_owner)s" in conn.sql[0]
    assert "attempt_count = %(attempt_count)s" in conn.sql[0]
    assert "lease_owner = NULL" in conn.sql[0]
    assert "leased_until_ms = NULL" in conn.sql[0]
    insert_index = next(
        index for index, sql in enumerate(conn.sql) if "INSERT INTO worker_queue_terminal_events" in sql
    )
    assert conn.params[insert_index]["worker_name"] == "event_anchor_backfill"
    assert conn.params[insert_index]["source_table"] == "event_anchor_backfill_jobs"
    assert conn.params[insert_index]["target_key"] == "event-1:intent-1"


def test_repository_has_no_runtime_ready_fact_reconciliation_method() -> None:
    source = inspect.getsource(EventAnchorBackfillJobRepository)

    assert not hasattr(EventAnchorBackfillJobRepository, "mark_ready_jobs_done")
    assert "JOIN enriched_events anchors" not in source


def test_reconcile_ready_historical_jobs_dry_run_reports_bounded_explain_without_update() -> None:
    conn = _ScriptedConnection(
        [
            [{"QUERY PLAN": "Limit  (cost=0.00..1.00 rows=10 width=64)"}],
            {"count": 2},
            {"count": 2},
        ]
    )

    result = EventAnchorBackfillJobRepository(conn).reconcile_ready_historical_jobs(
        limit=10,
        now_ms=1_700_000_010_000,
        execute=False,
    )

    assert result == {
        "mode": "dry_run",
        "execute": False,
        "limit": 10,
        "ready_pending_count": 2,
        "updated_count": 0,
        "remaining_ready_pending_count": 2,
        "explain": ["Limit  (cost=0.00..1.00 rows=10 width=64)"],
        "updated": [],
    }
    assert any("EXPLAIN (FORMAT TEXT)" in sql for sql in conn.sql)
    assert all("job.status = 'pending'" in sql for sql in conn.sql if "event_anchor_backfill_jobs job" in sql)
    assert not any("UPDATE event_anchor_backfill_jobs job" in sql for sql in conn.sql)


def test_reconcile_ready_historical_jobs_execute_marks_bounded_rows_done() -> None:
    conn = _ScriptedConnection(
        [
            [{"QUERY PLAN": "Index Scan using idx_event_anchor_backfill_jobs_pending_created"}],
            {"count": 2},
            [
                {"event_id": "event-1", "intent_id": "intent-1"},
                {"event_id": "event-2", "intent_id": "intent-2"},
            ],
            {"count": 0},
        ]
    )

    result = EventAnchorBackfillJobRepository(conn).reconcile_ready_historical_jobs(
        limit=10,
        now_ms=1_700_000_010_000,
        execute=True,
    )

    assert result["mode"] == "execute"
    assert result["ready_pending_count"] == 2
    assert result["updated_count"] == 2
    assert result["remaining_ready_pending_count"] == 0
    update_index = next(index for index, sql in enumerate(conn.sql) if "UPDATE event_anchor_backfill_jobs job" in sql)
    assert "historical_ready_reconcile" in conn.sql[update_index]
    assert conn.params[update_index]["now_ms"] == 1_700_000_010_000


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

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        result = self.results.pop(0)
        assert isinstance(result, dict) or result is None
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
