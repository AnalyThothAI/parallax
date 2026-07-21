from __future__ import annotations

from typing import Any

from parallax.app.operations.queue_health import fetch_queue_table_health


class Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class DirtyQueueConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[object] = []

    def execute(self, sql: str, params: object = ()) -> Rows:
        self.sql.append(sql)
        self.params.append(params)
        if "GROUP BY final_reason_bucket" in sql:
            return Rows([])
        if "FROM worker_queue_terminal_events" in sql:
            return Rows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
        return Rows(
            [
                {
                    "total_count": 4,
                    "active_count": 4,
                    "due_count": 2,
                    "running_count": 1,
                    "failed_count": 1,
                    "source_terminal_count": 0,
                    "oldest_due_at_ms": 850,
                    "oldest_running_at_ms": 980,
                    "max_attempt_count": 5,
                }
            ]
        )


def test_dirty_target_health_is_an_on_demand_ops_query() -> None:
    conn = DirtyQueueConnection()

    health = fetch_queue_table_health(conn, "token_radar_dirty_targets", now_ms=1_000)

    assert health["available"] is True
    assert health["status"] == "degraded"
    assert health["queue_depth"] == 4
    assert health["due_count"] == 2
    assert health["oldest_due_age_ms"] == 150


def test_shared_news_queue_uses_the_current_worker_discriminator() -> None:
    conn = DirtyQueueConnection()

    fetch_queue_table_health(
        conn,
        "news_projection_dirty_targets",
        now_ms=1_000,
        worker_name="news_story_brief",
    )

    assert any("projection_name = %(worker_filter_value)s" in sql for sql in conn.sql)
    assert any(params.get("worker_filter_value") == "story_brief" for params in conn.params if isinstance(params, dict))


def test_unknown_queue_is_rejected_without_sql() -> None:
    conn = DirtyQueueConnection()

    health = fetch_queue_table_health(conn, "unknown_queue", now_ms=1_000)

    assert health["available"] is False
    assert health["error_code"] == "unknown_queue_table"
    assert conn.sql == []


def test_malformed_queue_rows_fail_closed() -> None:
    class Connection(DirtyQueueConnection):
        def execute(self, sql: str, params: object = ()) -> Rows:
            if "FROM token_radar_dirty_targets" in sql:
                return Rows([{"total_count": 1}])
            return super().execute(sql, params)

    health = fetch_queue_table_health(Connection(), "token_radar_dirty_targets", now_ms=1_000)

    assert health["available"] is False
    assert health["error_code"] == "queue_query_failed"
