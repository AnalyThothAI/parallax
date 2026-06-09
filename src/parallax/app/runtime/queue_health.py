from __future__ import annotations

import re
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from parallax.app.runtime.worker_manifest import worker_queue_health_tables


@dataclass(frozen=True, slots=True)
class StatusQueueSpec:
    table: str
    due_column: str = "next_run_at_ms"
    active_statuses: tuple[str, ...] = ("pending", "failed", "running")
    due_statuses: tuple[str, ...] = ("pending", "failed")
    running_statuses: tuple[str, ...] = ("running",)
    failed_statuses: tuple[str, ...] = ("failed",)
    blocked_statuses: tuple[str, ...] = ()
    terminal_statuses: tuple[str, ...] = ("dead",)
    lease_column: str | None = None
    running_age_column: str = "updated_at_ms"


@dataclass(frozen=True, slots=True)
class QueueHealthAdapterSpec:
    table: str
    kind: str
    status_queue: StatusQueueSpec | None = None


STATUS_QUEUE_SPECS: dict[str, StatusQueueSpec] = {
    "pulse_agent_jobs": StatusQueueSpec(table="pulse_agent_jobs"),
    "notification_deliveries": StatusQueueSpec(table="notification_deliveries"),
    "event_anchor_backfill_jobs": StatusQueueSpec(
        table="event_anchor_backfill_jobs",
        active_statuses=("pending",),
        due_statuses=("pending",),
        running_statuses=(),
        failed_statuses=(),
        blocked_statuses=(),
        terminal_statuses=("failed", "expired"),
    ),
}

QUEUE_HEALTH_ADAPTER_SPECS: dict[str, QueueHealthAdapterSpec] = {
    "asset_profile_refresh_targets": QueueHealthAdapterSpec(table="asset_profile_refresh_targets", kind="dirty_target"),
    "event_anchor_backfill_jobs": QueueHealthAdapterSpec(
        table="event_anchor_backfill_jobs",
        kind="status_queue",
        status_queue=STATUS_QUEUE_SPECS["event_anchor_backfill_jobs"],
    ),
    "market_tick_current_dirty_targets": QueueHealthAdapterSpec(
        table="market_tick_current_dirty_targets", kind="dirty_target"
    ),
    "macro_projection_dirty_targets": QueueHealthAdapterSpec(
        table="macro_projection_dirty_targets", kind="dirty_target"
    ),
    "narrative_admission_dirty_targets": QueueHealthAdapterSpec(
        table="narrative_admission_dirty_targets", kind="dirty_target"
    ),
    "news_projection_dirty_targets": QueueHealthAdapterSpec(table="news_projection_dirty_targets", kind="dirty_target"),
    "notification_deliveries": QueueHealthAdapterSpec(
        table="notification_deliveries",
        kind="status_queue",
        status_queue=STATUS_QUEUE_SPECS["notification_deliveries"],
    ),
    "pulse_agent_jobs": QueueHealthAdapterSpec(
        table="pulse_agent_jobs", kind="status_queue", status_queue=STATUS_QUEUE_SPECS["pulse_agent_jobs"]
    ),
    "pulse_trigger_dirty_targets": QueueHealthAdapterSpec(table="pulse_trigger_dirty_targets", kind="dirty_target"),
    "token_capture_tier_dirty_targets": QueueHealthAdapterSpec(
        table="token_capture_tier_dirty_targets", kind="dirty_target"
    ),
    "token_discovery_dirty_lookup_keys": QueueHealthAdapterSpec(
        table="token_discovery_dirty_lookup_keys", kind="dirty_target"
    ),
    "token_image_source_dirty_targets": QueueHealthAdapterSpec(
        table="token_image_source_dirty_targets", kind="dirty_target"
    ),
    "token_profile_current_dirty_targets": QueueHealthAdapterSpec(
        table="token_profile_current_dirty_targets", kind="dirty_target"
    ),
    "token_radar_source_dirty_events": QueueHealthAdapterSpec(
        table="token_radar_source_dirty_events", kind="dirty_target"
    ),
    "token_radar_dirty_targets": QueueHealthAdapterSpec(table="token_radar_dirty_targets", kind="dirty_target"),
}

DIRTY_TARGET_WORKER_FILTERS: dict[tuple[str, str], tuple[str, str]] = {
    ("news_projection_dirty_targets", "news_item_brief"): ("projection_name", "brief_input"),
    ("news_projection_dirty_targets", "news_page_projection"): ("projection_name", "page"),
    ("news_projection_dirty_targets", "news_source_quality_projection"): ("projection_name", "source_quality"),
}

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
CONTRACT_FAILURE_ERROR_CODES = frozenset(
    {
        "adapter_query_failure",
        "connection_context_enter_failure",
        "manifest_mismatch",
        "missing_connection",
        "queue_table_unavailable",
    }
)
QUEUE_HEALTH_CACHE_TTL_MS = 5_000


def queue_health_adapter_specs() -> dict[str, QueueHealthAdapterSpec]:
    return dict(QUEUE_HEALTH_ADAPTER_SPECS)


def fill_worker_queue_healths(
    workers: dict[str, dict[str, Any]],
    runtime: object,
    *,
    now_ms: int | None = None,
) -> None:
    db = getattr(runtime, "db", None)
    api_pool = getattr(db, "api_pool", None)
    connection = getattr(api_pool, "connection", None)
    worker_tables = worker_queue_health_tables()
    resolved_now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    if _fill_cached_worker_queue_healths(workers, runtime, worker_tables, now_ms=resolved_now_ms):
        return
    if not callable(connection):
        _fill_unavailable_worker_queue_healths(
            workers,
            worker_tables,
            error_code="missing_connection",
            exc=None,
        )
        return
    try:
        with connection() as conn:
            for worker_name, tables in worker_tables.items():
                table_health = {
                    table: fetch_queue_table_health(
                        conn,
                        table,
                        now_ms=resolved_now_ms,
                        worker_name=worker_name,
                    )
                    for table in tables
                }
                health = aggregate_queue_health(table_health)
                workers.setdefault(worker_name, {})["queue_health"] = health
                workers[worker_name]["queue_depth"] = health["queue_depth"]
            _store_worker_queue_health_cache(workers, runtime, worker_tables, now_ms=resolved_now_ms)
    except Exception as exc:
        _fill_unavailable_worker_queue_healths(
            workers,
            worker_tables,
            error_code="connection_context_enter_failure",
            exc=exc,
        )


def fetch_queue_table_health(
    conn: Any,
    table: str,
    *,
    now_ms: int,
    worker_name: str | None = None,
) -> dict[str, Any]:
    _validate_identifier(table)
    spec = QUEUE_HEALTH_ADAPTER_SPECS.get(table)
    if spec is None:
        return _unavailable_health(
            table,
            "unknown",
            error_code="manifest_mismatch",
            exc=None,
        )
    if spec.kind == "status_queue" and spec.status_queue is not None:
        return _status_queue_health(conn, spec.status_queue, now_ms=now_ms, worker_name=worker_name)
    if spec.kind == "dirty_target":
        return _dirty_target_queue_health(conn, spec.table, now_ms=now_ms, worker_name=worker_name)
    if spec.kind == "terminal_projection":
        return _terminal_projection_queue_health(conn, spec.table, now_ms=now_ms, worker_name=worker_name)
    return _unavailable_health(
        spec.table,
        spec.kind,
        error_code="manifest_mismatch",
        exc=ValueError(f"unknown queue health adapter kind: {spec.kind}"),
    )


def aggregate_queue_health(tables: dict[str, dict[str, Any]]) -> dict[str, Any]:
    queue_depth = _sum_field(tables, "queue_depth")
    due_count = _sum_field(tables, "due_count")
    running_count = _sum_field(tables, "running_count")
    failed_count = _sum_field(tables, "failed_count")
    blocked_count = _sum_field(tables, "blocked_count")
    terminal_count = _sum_field(tables, "terminal_count")
    unresolved_terminal_count = _sum_field(tables, "unresolved_terminal_count")
    reason_buckets = _sum_reason_buckets(tables)
    unavailable_count = sum(1 for health in tables.values() if not health.get("available"))
    contract_failure_count = sum(
        1 for health in tables.values() if health.get("error_code") in CONTRACT_FAILURE_ERROR_CODES
    )
    adapter_error_count = sum(1 for health in tables.values() if health.get("error_code") == "adapter_query_failure")
    manifest_mismatch_count = sum(1 for health in tables.values() if health.get("error_code") == "manifest_mismatch")
    status = _aggregate_status(tables.values())
    return {
        "status": status,
        "reason": _aggregate_reason(
            status,
            unavailable_count=unavailable_count,
            blocked_count=blocked_count,
            adapter_error_count=adapter_error_count,
            manifest_mismatch_count=manifest_mismatch_count,
        ),
        "table_count": len(tables),
        "unavailable_table_count": unavailable_count,
        "contract_failure_count": contract_failure_count,
        "adapter_error_count": adapter_error_count,
        "manifest_mismatch_count": manifest_mismatch_count,
        "queue_depth": queue_depth,
        "due_count": due_count,
        "running_count": running_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "terminal_count": terminal_count,
        "unresolved_terminal_count": unresolved_terminal_count,
        "reason_buckets": reason_buckets,
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
        "contract_failure_count": 0,
        "adapter_error_count": 0,
        "manifest_mismatch_count": 0,
        "queue_depth": None,
        "due_count": 0,
        "running_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "terminal_count": 0,
        "unresolved_terminal_count": 0,
        "reason_buckets": {},
        "oldest_due_age_ms": None,
        "oldest_running_age_ms": None,
        "max_attempt_count": None,
        "tables": {},
    }


def _status_queue_health(
    conn: Any,
    spec: StatusQueueSpec,
    *,
    now_ms: int,
    worker_name: str | None,
) -> dict[str, Any]:
    table = _validate_identifier(spec.table)
    try:
        counts = _status_counts(conn, spec)
        metrics = _status_metrics(conn, spec, now_ms=now_ms)
        terminal_metrics = _terminal_projection_metrics(conn, table, worker_name=worker_name)
    except Exception as exc:
        return _unavailable_health(
            table,
            "status_queue",
            error_code=_query_error_code(exc),
            exc=exc,
        )
    return _table_health(
        table=table,
        kind="status_queue",
        counts_by_status=counts,
        metrics=metrics,
        terminal_metrics=terminal_metrics,
        now_ms=now_ms,
    )


def _dirty_target_queue_health(
    conn: Any,
    table: str,
    *,
    now_ms: int,
    worker_name: str | None,
) -> dict[str, Any]:
    table = _validate_identifier(table)
    try:
        worker_filter, worker_params = _dirty_target_worker_filter(table, worker_name)
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
            WHERE (
                due_at_ms <= %(now_ms)s
                OR leased_until_ms > %(now_ms)s
                OR (last_error IS NOT NULL AND last_error <> '')
              )
              {worker_filter}
            """,
            {"now_ms": int(now_ms), **worker_params},
        ).fetchone()
        terminal_metrics = _terminal_projection_metrics(conn, table, worker_name=worker_name)
    except Exception as exc:
        return _unavailable_health(
            table,
            "dirty_target",
            error_code=_query_error_code(exc),
            exc=exc,
        )
    return _table_health(
        table=table,
        kind="dirty_target",
        counts_by_status={},
        metrics=_row_dict(row),
        terminal_metrics=terminal_metrics,
        now_ms=now_ms,
    )


def _terminal_projection_queue_health(
    conn: Any,
    table: str,
    *,
    now_ms: int,
    worker_name: str | None,
) -> dict[str, Any]:
    table = _validate_identifier(table)
    try:
        terminal_metrics = _terminal_projection_metrics(conn, table, worker_name=worker_name)
    except Exception as exc:
        return _unavailable_health(
            table,
            "terminal_projection",
            error_code=_query_error_code(exc),
            exc=exc,
        )
    return _table_health(
        table=table,
        kind="terminal_projection",
        counts_by_status={},
        metrics={
            "total_count": terminal_metrics.get("terminal_count"),
            "active_count": 0,
            "due_count": 0,
            "running_count": 0,
            "failed_count": 0,
            "blocked_count": 0,
        },
        terminal_metrics=terminal_metrics,
        now_ms=now_ms,
    )


def _status_counts(conn: Any, spec: StatusQueueSpec) -> dict[str, int]:
    table = _validate_identifier(spec.table)
    statuses = _status_metric_statuses(spec)
    if not statuses:
        return {}
    rows = conn.execute(
        f"""
        SELECT status, COUNT(*) AS count
        FROM {table}
        WHERE {_status_filter("status", statuses)}
        GROUP BY status
        """
    ).fetchall()
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
    statuses = _status_metric_statuses(spec)
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
        WHERE {_status_filter("status", statuses)}
        """,
        {"now_ms": int(now_ms)},
    ).fetchone()
    return _row_dict(row)


def _terminal_projection_metrics(
    conn: Any,
    source_table: str,
    *,
    worker_name: str | None,
) -> dict[str, Any]:
    source_table = _validate_identifier(source_table)
    params: dict[str, Any] = {"source_table": source_table}
    worker_filter = ""
    if worker_name is not None:
        params["worker_name"] = worker_name
        worker_filter = "AND worker_name = %(worker_name)s"
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS terminal_count,
          COUNT(*) FILTER (WHERE operator_action IS NULL) AS unresolved_terminal_count
        FROM worker_queue_terminal_events
        WHERE source_table = %(source_table)s
          {worker_filter}
        """,
        params,
    ).fetchone()
    metrics = _row_dict(row)
    bucket_rows = conn.execute(
        f"""
        SELECT final_reason_bucket, COUNT(*) AS count
        FROM worker_queue_terminal_events
        WHERE source_table = %(source_table)s
          AND operator_action IS NULL
          {worker_filter}
        GROUP BY final_reason_bucket
        ORDER BY count DESC, final_reason_bucket ASC
        """,
        params,
    ).fetchall()
    metrics["reason_buckets"] = {
        str(_row_get(bucket_row, "final_reason_bucket", 0) or "other"): int(_row_get(bucket_row, "count", 1) or 0)
        for bucket_row in bucket_rows
    }
    return metrics


def _table_health(
    *,
    table: str,
    kind: str,
    counts_by_status: dict[str, int],
    metrics: dict[str, Any],
    terminal_metrics: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    queue_depth = _int_metric(metrics, "active_count")
    due_count = _int_metric(metrics, "due_count")
    running_count = _int_metric(metrics, "running_count")
    failed_count = _int_metric(metrics, "failed_count")
    active_blocked_count = _int_metric(metrics, "blocked_count")
    source_terminal_count = _int_metric(metrics, "source_terminal_count")
    unresolved_terminal_count = _int_metric(terminal_metrics, "unresolved_terminal_count")
    terminal_count = _int_metric(terminal_metrics, "terminal_count")
    blocked_count = active_blocked_count + unresolved_terminal_count
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
        "error_code": None,
        "adapter_error_kind": None,
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
        "active_blocked_count": active_blocked_count,
        "source_terminal_count": source_terminal_count,
        "terminal_count": terminal_count,
        "unresolved_terminal_count": unresolved_terminal_count,
        "reason_buckets": dict(terminal_metrics.get("reason_buckets") or {}),
        "oldest_due_age_ms": _age_ms(now_ms, metrics.get("oldest_due_at_ms")),
        "oldest_running_age_ms": _age_ms(now_ms, metrics.get("oldest_running_at_ms")),
        "max_attempt_count": _optional_int(metrics.get("max_attempt_count")),
    }


def _unavailable_health(
    table: str,
    kind: str,
    *,
    error_code: str,
    exc: Exception | None,
) -> dict[str, Any]:
    return {
        "table": table,
        "kind": kind,
        "available": False,
        "status": "unavailable",
        "reason": error_code,
        "error_code": error_code,
        "adapter_error_kind": type(exc).__name__ if exc is not None else None,
        "adapter_error": str(exc) if exc is not None else None,
        "counts_by_status": {},
        "total_count": None,
        "queue_depth": None,
        "due_count": 0,
        "running_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "active_blocked_count": 0,
        "terminal_count": 0,
        "unresolved_terminal_count": 0,
        "reason_buckets": {},
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


def _aggregate_reason(
    status: str,
    *,
    unavailable_count: int,
    blocked_count: int,
    adapter_error_count: int,
    manifest_mismatch_count: int,
) -> str:
    if status == "unavailable" and unavailable_count > 0:
        if manifest_mismatch_count > 0:
            return "manifest_mismatch"
        if adapter_error_count > 0:
            return "adapter_query_failure"
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


def _status_metric_statuses(spec: StatusQueueSpec) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *spec.active_statuses,
                *spec.due_statuses,
                *spec.running_statuses,
                *spec.failed_statuses,
                *spec.blocked_statuses,
            )
        )
    )


def _dirty_target_worker_filter(table: str, worker_name: str | None) -> tuple[str, dict[str, Any]]:
    if worker_name is None:
        return "", {}
    filter_spec = DIRTY_TARGET_WORKER_FILTERS.get((table, worker_name))
    if filter_spec is None:
        return "", {}
    column, value = filter_spec
    return f"AND {_validate_identifier(column)} = %(worker_filter_value)s", {"worker_filter_value": value}


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


def _sum_reason_buckets(tables: dict[str, dict[str, Any]]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for health in tables.values():
        if not health.get("available"):
            continue
        for bucket, count in dict(health.get("reason_buckets") or {}).items():
            buckets[str(bucket)] = buckets.get(str(bucket), 0) + int(count or 0)
    return dict(sorted(buckets.items(), key=lambda item: (-item[1], item[0])))


def _max_age(tables: dict[str, dict[str, Any]], field: str) -> int | None:
    return _max_int(health.get(field) for health in tables.values())


def _max_int(values: Any) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return max(integers) if integers else None


def _fill_cached_worker_queue_healths(
    workers: dict[str, dict[str, Any]],
    runtime: object,
    worker_tables: dict[str, tuple[str, ...]],
    *,
    now_ms: int,
) -> bool:
    cache = getattr(runtime, "_queue_health_cache", None)
    if not isinstance(cache, dict):
        return False
    if int(now_ms) - int(cache.get("cached_at_ms") or 0) > QUEUE_HEALTH_CACHE_TTL_MS:
        return False
    if cache.get("worker_tables") != worker_tables:
        return False
    cached_workers = cache.get("workers")
    if not isinstance(cached_workers, dict):
        return False
    for worker_name, health in cached_workers.items():
        if not isinstance(health, dict):
            continue
        workers.setdefault(worker_name, {})["queue_health"] = deepcopy(health)
        workers[worker_name]["queue_depth"] = health.get("queue_depth")
    return True


def _store_worker_queue_health_cache(
    workers: dict[str, dict[str, Any]],
    runtime: object,
    worker_tables: dict[str, tuple[str, ...]],
    *,
    now_ms: int,
) -> None:
    try:
        runtime._queue_health_cache = {
            "cached_at_ms": int(now_ms),
            "worker_tables": worker_tables,
            "workers": {
                worker_name: deepcopy(status.get("queue_health") or {})
                for worker_name, status in workers.items()
                if status.get("queue_health")
            },
        }
    except Exception:
        return


def _fill_unavailable_worker_queue_healths(
    workers: dict[str, dict[str, Any]],
    worker_tables: dict[str, tuple[str, ...]],
    *,
    error_code: str,
    exc: Exception | None,
) -> None:
    for worker_name, tables in worker_tables.items():
        table_health = {
            table: _unavailable_health(
                table,
                QUEUE_HEALTH_ADAPTER_SPECS.get(table, QueueHealthAdapterSpec(table=table, kind="unknown")).kind,
                error_code=error_code,
                exc=exc,
            )
            for table in tables
        }
        health = aggregate_queue_health(table_health)
        workers.setdefault(worker_name, {})["queue_health"] = health
        workers[worker_name]["queue_depth"] = health["queue_depth"]


def _query_error_code(exc: Exception) -> str:
    error_type = type(exc).__name__.lower()
    if "undefinedtable" in error_type or "undefined_table" in error_type:
        return "queue_table_unavailable"
    return "adapter_query_failure"
