from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from parallax.app.runtime.queue_health import (
    fetch_queue_table_health,
    fill_worker_queue_healths,
)
from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.app.runtime.worker_status import manifest_worker_statuses


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
        if "GROUP BY final_reason_bucket" in sql:
            return _Rows(
                [
                    {"final_reason_bucket": "llm_provider_522", "count": 3},
                    {"final_reason_bucket": "stale_window_ttl", "count": 1},
                ]
            )
        if "FROM worker_queue_terminal_events" in sql:
            return _Rows([{"terminal_count": 5, "unresolved_terminal_count": 4}])
        if "GROUP BY status" in sql:
            return _Rows(
                [
                    {"status": "pending", "count": 2},
                    {"status": "running", "count": 1},
                    {"status": "dead", "count": 2},
                ]
            )
        if "FROM notification_deliveries" in sql:
            return _Rows(
                [
                    {
                        "total_count": 16,
                        "active_count": 3,
                        "due_count": 2,
                        "running_count": 1,
                        "failed_count": 0,
                        "blocked_count": 0,
                        "source_terminal_count": 2,
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
        self.params: list[object] = []

    def execute(self, sql: str, params: object = ()) -> _Rows:
        self.sql.append(sql)
        self.params.append(params)
        if "GROUP BY final_reason_bucket" in sql:
            return _Rows([])
        if "FROM worker_queue_terminal_events" in sql:
            return _Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
        if "FROM token_radar_dirty_targets" in sql or "FROM news_projection_dirty_targets" in sql:
            return _Rows(
                [
                    {
                        "total_count": 4,
                        "active_count": 4,
                        "due_count": 2,
                        "running_count": 1,
                        "failed_count": 1,
                        "blocked_count": 0,
                        "source_terminal_count": 0,
                        "oldest_due_at_ms": 850,
                        "oldest_running_at_ms": 980,
                        "max_attempt_count": 5,
                    }
                ]
            )
        raise AssertionError(sql)


def test_fetch_status_queue_health_uses_terminal_projection_for_terminal_backlog() -> None:
    conn = _QueueHealthConn()
    health = fetch_queue_table_health(conn, "notification_deliveries", now_ms=1_000)

    assert health["available"] is True
    assert health["kind"] == "status_queue"
    assert health["status"] == "blocked"
    assert health["counts_by_status"] == {"pending": 2, "running": 1, "dead": 2}
    assert health["queue_depth"] == 3
    assert health["source_terminal_count"] == 2
    assert health["terminal_count"] == 5
    assert health["unresolved_terminal_count"] == 4
    assert health["reason_buckets"] == {"llm_provider_522": 3, "stale_window_ttl": 1}
    assert health["due_count"] == 2
    assert health["running_count"] == 1
    assert health["blocked_count"] == 6
    assert health["oldest_due_age_ms"] == 100
    assert health["oldest_running_age_ms"] == 50
    assert health["max_attempt_count"] == 3
    assert any("AS source_terminal_count" in sql and "'dead'" in sql for sql in conn.sql)


def test_source_terminal_status_blocks_queue_health_even_if_terminal_projection_is_missing() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "GROUP BY final_reason_bucket" in sql:
                return _Rows([])
            if "FROM worker_queue_terminal_events" in sql:
                return _Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
            if "GROUP BY status" in sql:
                return _Rows([{"status": "dead", "count": 2}])
            if "FROM notification_deliveries" in sql:
                return _Rows(
                    [
                        {
                            "total_count": 2,
                            "active_count": 0,
                            "due_count": 0,
                            "running_count": 0,
                            "failed_count": 0,
                            "blocked_count": 0,
                            "source_terminal_count": 2,
                            "oldest_due_at_ms": None,
                            "oldest_running_at_ms": None,
                            "max_attempt_count": 5,
                        }
                    ]
                )
            raise AssertionError(sql)

    health = fetch_queue_table_health(Conn(), "notification_deliveries", now_ms=1_000)

    assert health["available"] is True
    assert health["counts_by_status"] == {"dead": 2}
    assert health["source_terminal_count"] == 2
    assert health["terminal_count"] == 0
    assert health["blocked_count"] == 2
    assert health["status"] == "blocked"


def test_fetch_dirty_target_health_counts_due_leased_and_failed_rows() -> None:
    conn = _DirtyTargetConn()
    health = fetch_queue_table_health(conn, "token_radar_dirty_targets", now_ms=1_000)

    assert health["available"] is True
    assert health["kind"] == "dirty_target"
    assert health["status"] == "degraded"
    assert health["counts_by_status"] == {}
    assert health["queue_depth"] == 4
    assert health["terminal_count"] == 0
    assert health["unresolved_terminal_count"] == 0
    assert health["due_count"] == 2
    assert health["running_count"] == 1
    assert health["failed_count"] == 1
    assert health["oldest_due_age_ms"] == 150
    assert health["oldest_running_age_ms"] == 20
    assert health["max_attempt_count"] == 5
    assert any("WHERE (" in sql for sql in conn.sql)


def test_fetch_shared_dirty_target_health_filters_by_worker_projection_name() -> None:
    conn = _DirtyTargetConn()

    health = fetch_queue_table_health(
        conn,
        "news_projection_dirty_targets",
        now_ms=1_000,
        worker_name="news_item_brief",
    )

    assert health["available"] is True
    assert any("AND projection_name = %(worker_filter_value)s" in sql for sql in conn.sql)
    assert any(params.get("worker_filter_value") == "brief_input" for params in conn.params if isinstance(params, dict))


def test_fill_worker_queue_healths_attaches_all_manifest_queue_tables() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "GROUP BY final_reason_bucket" in sql:
                return _Rows([])
            if "FROM worker_queue_terminal_events" in sql:
                return _Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
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
                        "source_terminal_count": 0,
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

    assert workers["token_radar_projection"]["queue_depth"] == 2
    assert "token_radar_dirty_targets" in workers["token_radar_projection"]["queue_health"]["tables"]
    assert workers["notification_delivery"]["queue_depth"] == 1
    assert set(workers["notification_delivery"]["queue_health"]["tables"]) == {"notification_deliveries"}
    assert workers["event_anchor_backfill"]["queue_depth"] == 1
    assert set(workers["event_anchor_backfill"]["queue_health"]["tables"]) == {"event_anchor_backfill_jobs"}


def test_fill_worker_queue_healths_reuses_short_ttl_cache_without_db_query() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "GROUP BY final_reason_bucket" in sql:
                return _Rows([])
            if "FROM worker_queue_terminal_events" in sql:
                return _Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
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
                        "source_terminal_count": 0,
                        "oldest_due_at_ms": 900,
                        "oldest_running_at_ms": None,
                        "max_attempt_count": 0,
                    }
                ]
            )

    class ConnectionContext:
        enter_count = 0

        def __enter__(self) -> Conn:
            type(self).enter_count += 1
            return Conn()

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    runtime = SimpleNamespace(db=SimpleNamespace(api_pool=SimpleNamespace(connection=ConnectionContext)))
    first_workers = manifest_worker_statuses({manifest.name: {} for manifest in all_worker_manifests()})
    second_workers = manifest_worker_statuses({manifest.name: {} for manifest in all_worker_manifests()})

    fill_worker_queue_healths(first_workers, runtime, now_ms=1_000)
    first_workers["token_radar_projection"]["queue_health"]["tables"]["token_radar_dirty_targets"]["queue_depth"] = 999
    fill_worker_queue_healths(second_workers, runtime, now_ms=1_500)

    assert ConnectionContext.enter_count == 1
    assert second_workers["token_radar_projection"]["queue_depth"] == 2
    assert (
        second_workers["token_radar_projection"]["queue_health"]["tables"]["token_radar_dirty_targets"]["queue_depth"]
        == 1
    )


def test_unregistered_manifest_queue_table_reports_manifest_mismatch() -> None:
    health = fetch_queue_table_health(_DirtyTargetConn(), "unknown_manifest_queue", now_ms=1_000)

    assert health["available"] is False
    assert health["status"] == "unavailable"
    assert health["error_code"] == "manifest_mismatch"


def test_terminal_evidence_query_failure_is_adapter_error() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "FROM worker_queue_terminal_events" in sql:
                raise RuntimeError("terminal table missing")
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

    health = fetch_queue_table_health(Conn(), "notification_deliveries", now_ms=1_000)

    assert health["available"] is False
    assert health["kind"] == "status_queue"
    assert health["error_code"] == "adapter_query_failure"
    assert health["adapter_error_kind"] == "RuntimeError"


def test_missing_required_queue_metric_reports_adapter_error_instead_of_idle_queue() -> None:
    class Conn:
        def execute(self, sql: str, params: object = ()) -> _Rows:
            if "GROUP BY final_reason_bucket" in sql:
                return _Rows([])
            if "FROM token_radar_dirty_targets" in sql:
                return _Rows(
                    [
                        {
                            "total_count": 1,
                            # active_count is deliberately absent: missing metrics are contract damage.
                            "due_count": 0,
                            "running_count": 0,
                            "failed_count": 0,
                            "blocked_count": 0,
                            "source_terminal_count": 0,
                            "oldest_due_at_ms": None,
                            "oldest_running_at_ms": None,
                            "max_attempt_count": 0,
                        }
                    ]
                )
            if "FROM worker_queue_terminal_events" in sql:
                return _Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
            raise AssertionError(sql)

    health = fetch_queue_table_health(Conn(), "token_radar_dirty_targets", now_ms=1_000)

    assert health["available"] is False
    assert health["status"] == "unavailable"
    assert health["error_code"] == "adapter_query_failure"
    assert health["adapter_error_kind"] == "KeyError"


def test_fill_worker_queue_healths_requires_api_pool_connection_contract() -> None:
    runtime = SimpleNamespace(db=SimpleNamespace(api_pool=SimpleNamespace()))
    workers = manifest_worker_statuses({manifest.name: {} for manifest in all_worker_manifests()})

    try:
        fill_worker_queue_healths(workers, runtime, now_ms=1_000)
    except AttributeError as exc:
        assert "connection" in str(exc)
    else:  # pragma: no cover - RED guard expectation
        raise AssertionError("queue health must not hide missing api_pool.connection as unavailable queue state")


def test_connection_context_enter_failure_is_reported_on_manifest_workers() -> None:
    class ConnectionContext:
        def __enter__(self) -> object:
            raise ConnectionError("cannot enter")

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    runtime = SimpleNamespace(db=SimpleNamespace(api_pool=SimpleNamespace(connection=ConnectionContext)))
    workers = manifest_worker_statuses({manifest.name: {} for manifest in all_worker_manifests()})

    fill_worker_queue_healths(workers, runtime, now_ms=1_000)

    health = workers["notification_delivery"]["queue_health"]
    assert health["status"] == "unavailable"
    assert health["unavailable_table_count"] == 1
    assert {table_health["error_code"] for table_health in health["tables"].values()} == {
        "connection_context_enter_failure"
    }
