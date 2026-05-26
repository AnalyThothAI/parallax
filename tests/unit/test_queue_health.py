from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.queue_health import (
    fetch_queue_table_health,
    fill_worker_queue_healths,
)
from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests
from gmgn_twitter_intel.app.runtime.worker_status import manifest_worker_statuses


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _QueueHealthConn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: object = ()) -> _Rows:
        self.sql.append(sql)
        if "GROUP BY status" in sql:
            return _Rows(
                [
                    {"status": "pending", "count": 2},
                    {"status": "running", "count": 1},
                    {"status": "dead", "count": 4},
                    {"status": "done", "count": 9},
                ]
            )
        if "FROM pulse_agent_jobs" in sql:
            return _Rows(
                [
                    {
                        "total_count": 16,
                        "active_count": 7,
                        "due_count": 2,
                        "running_count": 1,
                        "failed_count": 0,
                        "blocked_count": 4,
                        "oldest_due_at_ms": 900,
                        "oldest_running_at_ms": 950,
                        "max_attempt_count": 3,
                    }
                ]
            )
        raise AssertionError(sql)


class _DirtyTargetConn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: object = ()) -> _Rows:
        self.sql.append(sql)
        if "FROM token_radar_dirty_targets" in sql:
            return _Rows(
                [
                    {
                        "total_count": 4,
                        "active_count": 4,
                        "due_count": 2,
                        "running_count": 1,
                        "failed_count": 1,
                        "blocked_count": 0,
                        "oldest_due_at_ms": 850,
                        "oldest_running_at_ms": 980,
                        "max_attempt_count": 5,
                    }
                ]
            )
        raise AssertionError(sql)


def test_fetch_status_queue_health_counts_due_running_dead_and_ignores_success_depth() -> None:
    health = fetch_queue_table_health(_QueueHealthConn(), "pulse_agent_jobs", now_ms=1_000)

    assert health["available"] is True
    assert health["kind"] == "status_queue"
    assert health["status"] == "blocked"
    assert health["counts_by_status"] == {"pending": 2, "running": 1, "dead": 4, "done": 9}
    assert health["queue_depth"] == 7
    assert health["due_count"] == 2
    assert health["running_count"] == 1
    assert health["blocked_count"] == 4
    assert health["oldest_due_age_ms"] == 100
    assert health["oldest_running_age_ms"] == 50
    assert health["max_attempt_count"] == 3


def test_fetch_dirty_target_health_counts_due_leased_and_failed_rows() -> None:
    health = fetch_queue_table_health(_DirtyTargetConn(), "token_radar_dirty_targets", now_ms=1_000)

    assert health["available"] is True
    assert health["kind"] == "dirty_target"
    assert health["status"] == "degraded"
    assert health["counts_by_status"] == {}
    assert health["queue_depth"] == 4
    assert health["due_count"] == 2
    assert health["running_count"] == 1
    assert health["failed_count"] == 1
    assert health["oldest_due_age_ms"] == 150
    assert health["oldest_running_age_ms"] == 20
    assert health["max_attempt_count"] == 5


def test_fill_worker_queue_healths_attaches_all_manifest_queue_tables() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "GROUP BY status" in sql:
                return _Rows([{"status": "pending", "count": 1}])
            return _Rows(
                [
                    {
                        "total_count": 1,
                        "active_count": 1,
                        "due_count": 1,
                        "running_count": 0,
                        "failed_count": 0,
                        "blocked_count": 0,
                        "oldest_due_at_ms": 900,
                        "oldest_running_at_ms": None,
                        "max_attempt_count": 0,
                    }
                ]
            )

    class ConnectionContext:
        def __enter__(self) -> Conn:
            return Conn()

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    runtime = SimpleNamespace(db=SimpleNamespace(api_pool=SimpleNamespace(connection=ConnectionContext)))
    workers = manifest_worker_statuses({manifest.name: {} for manifest in all_worker_manifests()})

    fill_worker_queue_healths(workers, runtime, now_ms=1_000)

    assert workers["token_radar_projection"]["queue_depth"] == 1
    assert "token_radar_dirty_targets" in workers["token_radar_projection"]["queue_health"]["tables"]
    assert workers["pulse_candidate"]["queue_depth"] == 2
    assert set(workers["pulse_candidate"]["queue_health"]["tables"]) == {
        "pulse_agent_jobs",
        "pulse_trigger_dirty_targets",
    }
    assert workers["event_anchor_backfill"]["queue_depth"] == 1
    assert set(workers["event_anchor_backfill"]["queue_health"]["tables"]) == {
        "event_anchor_backfill_jobs"
    }
