from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_manifest import worker_queue_health_tables


@dataclass(frozen=True, slots=True)
class StatusQueueSpec:
    table: str
    due_column: str = "next_run_at_ms"
    active_statuses: tuple[str, ...] = ("pending", "failed", "running", "dead")
    due_statuses: tuple[str, ...] = ("pending", "failed")
    running_statuses: tuple[str, ...] = ("running",)
    failed_statuses: tuple[str, ...] = ("failed",)
    blocked_statuses: tuple[str, ...] = ("dead",)
    lease_column: str | None = None
    running_age_column: str = "updated_at_ms"


STATUS_QUEUE_SPECS: dict[str, StatusQueueSpec] = {
    "enrichment_jobs": StatusQueueSpec(table="enrichment_jobs"),
    "pulse_agent_jobs": StatusQueueSpec(table="pulse_agent_jobs"),
    "notification_deliveries": StatusQueueSpec(table="notification_deliveries"),
    "watchlist_handle_summary_jobs": StatusQueueSpec(
        table="watchlist_handle_summary_jobs",
        lease_column="lease_expires_at_ms",
    ),
    "event_anchor_backfill_jobs": StatusQueueSpec(
        table="event_anchor_backfill_jobs",
        active_statuses=("pending", "failed", "expired"),
        due_statuses=("pending",),
        running_statuses=(),
        failed_statuses=("failed",),
        blocked_statuses=("failed", "expired"),
    ),
    "token_mention_semantics": StatusQueueSpec(
        table="token_mention_semantics",
        due_column="next_retry_at_ms",
        active_statuses=("queued", "retryable_error", "stale", "semantic_unavailable"),
        due_statuses=("queued", "retryable_error", "stale"),
        running_statuses=(),
        failed_statuses=("retryable_error", "stale"),
        blocked_statuses=("semantic_unavailable",),
        lease_column="leased_until_ms",
        running_age_column="claimed_at_ms",
    ),
}

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def fill_worker_queue_healths(
    workers: dict[str, dict[str, Any]],
    runtime: object,
    *,
    now_ms: int | None = None,
) -> None:
    db = getattr(runtime, "db", None)
    api_pool = getattr(db, "api_pool", None)
    connection = getattr(api_pool, "connection", None)
    if not callable(connection):
        return
    resolved_now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    try:
        with connection() as conn:
            for worker_name, tables in worker_queue_health_tables().items():
                table_health = {
                    table: fetch_queue_table_health(conn, table, now_ms=resolved_now_ms) for table in tables
                }
                health = aggregate_queue_health(table_health)
                workers.setdefault(worker_name, {})["queue_health"] = health
                workers[worker_name]["queue_depth"] = health["queue_depth"]
    except Exception:
        return


def fetch_queue_table_health(conn: Any, table: str, *, now_ms: int) -> dict[str, Any]:
    _validate_identifier(table)
    spec = STATUS_QUEUE_SPECS.get(table)
    if spec is not None:
        return _status_queue_health(conn, spec, now_ms=now_ms)
    return _dirty_target_queue_health(conn, table, now_ms=now_ms)


def aggregate_queue_health(tables: dict[str, dict[str, Any]]) -> dict[str, Any]:
    queue_depth = _sum_field(tables, "queue_depth")
    due_count = _sum_field(tables, "due_count")
    running_count = _sum_field(tables, "running_count")
    failed_count = _sum_field(tables, "failed_count")
    blocked_count = _sum_field(tables, "blocked_count")
    unavailable_count = sum(1 for health in tables.values() if not health.get("available"))
    status = _aggregate_status(tables.values())
    return {
        "status": status,
        "reason": _aggregate_reason(status, unavailable_count=unavailable_count, blocked_count=blocked_count),
        "table_count": len(tables),
        "unavailable_table_count": unavailable_count,
        "queue_depth": queue_depth,
        "due_count": due_count,
        "running_count": running_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "oldest_due_age_ms": _max_age(tables, "oldest_due_age_ms"),
        "oldest_running_age_ms": _max_age(tables, "oldest_running_age_ms"),
        "max_attempt_count": _max_int(health.get("max_attempt_count") for health in tables.values()),
        "tables": tables,
    }


def empty_queue_health() -> dict[str, Any]:
    return {
        "status": "not_configured",
        "reason": "worker_has_no_manifest_queue",
        "table_count": 0,
        "unavailable_table_count": 0,
        "queue_depth": None,
        "due_count": 0,
        "running_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "oldest_due_age_ms": None,
        "oldest_running_age_ms": None,
        "max_attempt_count": None,
        "tables": {},
    }


def _status_queue_health(conn: Any, spec: StatusQueueSpec, *, now_ms: int) -> dict[str, Any]:
    table = _validate_identifier(spec.table)
    try:
        counts = _status_counts(conn, table)
        metrics = _status_metrics(conn, spec, now_ms=now_ms)
    except Exception as exc:
        return _unavailable_health(table, "status_queue", exc)
    return _table_health(
        table=table,
        kind="status_queue",
        counts_by_status=counts,
        metrics=metrics,
        now_ms=now_ms,
    )


def _dirty_target_queue_health(conn: Any, table: str, *, now_ms: int) -> dict[str, Any]:
    table = _validate_identifier(table)
    try:
        row = conn.execute(
            f"""
            SELECT
              COUNT(*) AS total_count,
              COUNT(*) AS active_count,
              COUNT(*) FILTER (
                WHERE due_at_ms <= %(now_ms)s
                  AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ) AS due_count,
              COUNT(*) FILTER (WHERE leased_until_ms > %(now_ms)s) AS running_count,
              COUNT(*) FILTER (WHERE last_error IS NOT NULL AND last_error <> '') AS failed_count,
              0 AS blocked_count,
              MIN(due_at_ms) FILTER (
                WHERE due_at_ms <= %(now_ms)s
                  AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ) AS oldest_due_at_ms,
              MIN(updated_at_ms) FILTER (WHERE leased_until_ms > %(now_ms)s) AS oldest_running_at_ms,
              MAX(attempt_count) AS max_attempt_count
            FROM {table}
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
    except Exception as exc:
        return _unavailable_health(table, "dirty_target", exc)
    return _table_health(
        table=table,
        kind="dirty_target",
        counts_by_status={},
        metrics=_row_dict(row),
        now_ms=now_ms,
    )


def _status_counts(conn: Any, table: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status").fetchall()
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        status = _row_get(row, "status", 0)
        count = _row_get(row, "count", 1)
        if status is None:
            status = f"unknown_{index}"
        counts[str(status)] = int(count or 0)
    return counts


def _status_metrics(conn: Any, spec: StatusQueueSpec, *, now_ms: int) -> dict[str, Any]:
    table = _validate_identifier(spec.table)
    due_column = _validate_identifier(spec.due_column)
    running_age_column = _validate_identifier(spec.running_age_column)
    due_released = _lease_released_sql(spec.lease_column, now_ms_placeholder="%(now_ms)s")
    running_filter = _status_filter("status", spec.running_statuses)
    if spec.lease_column is not None:
        lease_column = _validate_identifier(spec.lease_column)
        lease_running = f"{lease_column} > %(now_ms)s"
        running_filter = f"({running_filter} OR {lease_running})" if running_filter else lease_running
    if not running_filter:
        running_filter = "FALSE"
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS total_count,
          COUNT(*) FILTER (WHERE {_status_filter("status", spec.active_statuses)}) AS active_count,
          COUNT(*) FILTER (
            WHERE {_status_filter("status", spec.due_statuses)}
              AND {due_column} <= %(now_ms)s
              AND {due_released}
          ) AS due_count,
          COUNT(*) FILTER (WHERE {running_filter}) AS running_count,
          COUNT(*) FILTER (WHERE {_status_filter("status", spec.failed_statuses)}) AS failed_count,
          COUNT(*) FILTER (WHERE {_status_filter("status", spec.blocked_statuses)}) AS blocked_count,
          MIN({due_column}) FILTER (
            WHERE {_status_filter("status", spec.due_statuses)}
              AND {due_column} <= %(now_ms)s
              AND {due_released}
          ) AS oldest_due_at_ms,
          MIN({running_age_column}) FILTER (WHERE {running_filter}) AS oldest_running_at_ms,
          MAX(attempt_count) AS max_attempt_count
        FROM {table}
        """,
        {"now_ms": int(now_ms)},
    ).fetchone()
    return _row_dict(row)


def _table_health(
    *,
    table: str,
    kind: str,
    counts_by_status: dict[str, int],
    metrics: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    queue_depth = _int_metric(metrics, "active_count")
    due_count = _int_metric(metrics, "due_count")
    running_count = _int_metric(metrics, "running_count")
    failed_count = _int_metric(metrics, "failed_count")
    blocked_count = _int_metric(metrics, "blocked_count")
    status = _health_status(
        queue_depth=queue_depth,
        due_count=due_count,
        running_count=running_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
    )
    return {
        "table": table,
        "kind": kind,
        "available": True,
        "status": status,
        "reason": _health_reason(
            status=status,
            due_count=due_count,
            failed_count=failed_count,
            blocked_count=blocked_count,
        ),
        "counts_by_status": counts_by_status,
        "total_count": _int_metric(metrics, "total_count"),
        "queue_depth": queue_depth,
        "due_count": due_count,
        "running_count": running_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "oldest_due_age_ms": _age_ms(now_ms, metrics.get("oldest_due_at_ms")),
        "oldest_running_age_ms": _age_ms(now_ms, metrics.get("oldest_running_at_ms")),
        "max_attempt_count": _optional_int(metrics.get("max_attempt_count")),
    }


def _unavailable_health(table: str, kind: str, exc: Exception) -> dict[str, Any]:
    return {
        "table": table,
        "kind": kind,
        "available": False,
        "status": "unavailable",
        "reason": type(exc).__name__,
        "counts_by_status": {},
        "total_count": None,
        "queue_depth": None,
        "due_count": 0,
        "running_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "oldest_due_age_ms": None,
        "oldest_running_age_ms": None,
        "max_attempt_count": None,
    }


def _health_status(
    *,
    queue_depth: int,
    due_count: int,
    running_count: int,
    failed_count: int,
    blocked_count: int,
) -> str:
    if blocked_count > 0:
        return "blocked"
    if failed_count > 0:
        return "degraded"
    if due_count > 0 or running_count > 0 or queue_depth > 0:
        return "ok"
    return "idle"


def _health_reason(*, status: str, due_count: int, failed_count: int, blocked_count: int) -> str:
    if status == "blocked" and blocked_count > 0:
        return "blocked_work_present"
    if status == "degraded" and failed_count > 0:
        return "retryable_failures_present"
    if due_count > 0:
        return "due_work_present"
    if status == "idle":
        return "no_active_work"
    return "fresh_work"


def _aggregate_status(healths: Any) -> str:
    statuses = [str(health.get("status")) for health in healths]
    for status in ("unavailable", "blocked", "degraded", "ok"):
        if status in statuses:
            return status
    return "idle"


def _aggregate_reason(status: str, *, unavailable_count: int, blocked_count: int) -> str:
    if status == "unavailable" and unavailable_count > 0:
        return "queue_table_unavailable"
    if status == "blocked" and blocked_count > 0:
        return "blocked_work_present"
    if status == "degraded":
        return "retryable_failures_present"
    if status == "idle":
        return "no_active_work"
    return "fresh_work"


def _status_filter(column: str, values: tuple[str, ...]) -> str:
    column = _validate_identifier(column)
    if not values:
        return "FALSE"
    return f"{column} IN ({', '.join(_quote_literal(value) for value in values)})"


def _lease_released_sql(lease_column: str | None, *, now_ms_placeholder: str) -> str:
    if lease_column is None:
        return "TRUE"
    column = _validate_identifier(lease_column)
    return f"({column} IS NULL OR {column} <= {now_ms_placeholder})"


def _quote_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _validate_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"unsafe SQL identifier: {value}")
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return {}


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return row[index]


def _int_metric(metrics: dict[str, Any], key: str) -> int:
    return int(metrics.get(key) or 0)


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _age_ms(now_ms: int, started_at_ms: Any) -> int | None:
    if started_at_ms is None:
        return None
    return max(0, int(now_ms) - int(started_at_ms))


def _sum_field(tables: dict[str, dict[str, Any]], field: str) -> int:
    return sum(int(health.get(field) or 0) for health in tables.values() if health.get("available"))


def _max_age(tables: dict[str, dict[str, Any]], field: str) -> int | None:
    return _max_int(health.get(field) for health in tables.values())


def _max_int(values: Any) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return max(integers) if integers else None
