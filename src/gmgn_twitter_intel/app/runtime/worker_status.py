from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES

QUEUE_DEPTH_STATUSES = ("pending", "failed", "running")
WORKER_QUEUE_TABLES = {
    "enrichment": "enrichment_jobs",
    "handle_summary": "watchlist_handle_summary_jobs",
    "notification_delivery": "notification_deliveries",
}


def workers_status_payload(runtime: object) -> dict[str, dict[str, Any]]:
    workers = runtime.scheduler.status_payload()
    collector_status = runtime.collector.status.to_dict()
    workers.setdefault("collector", {})
    workers["collector"] = {
        **workers["collector"],
        "details": collector_status,
    }
    return workers


def canonical_workers_status_payload(runtime: object) -> dict[str, dict[str, Any]]:
    workers = canonical_worker_statuses(workers_status_payload(runtime))
    fill_worker_queue_depths(workers, runtime)
    return workers


def canonical_worker_statuses(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    workers = {name: dict(status) for name, status in payload.items()}
    for name in CANONICAL_WORKER_NAMES:
        workers.setdefault(name, empty_worker_status())
    for status in workers.values():
        for key, value in empty_worker_status().items():
            status.setdefault(key, value)
    return workers


def empty_worker_status() -> dict[str, Any]:
    return {
        "enabled": False,
        "running": False,
        "last_started_at_ms": None,
        "last_finished_at_ms": None,
        "last_result": None,
        "last_error": None,
        "iteration_duration_p99_ms": None,
        "queue_depth": None,
        "pool_wait_ms_p99": None,
        "details": {},
    }


def fill_worker_queue_depths(workers: dict[str, dict[str, Any]], runtime: object) -> None:
    db = getattr(runtime, "db", None)
    api_pool = getattr(db, "api_pool", None)
    connection = getattr(api_pool, "connection", None)
    if connection is None:
        return
    try:
        with connection() as conn:
            for worker_name, table in WORKER_QUEUE_TABLES.items():
                status_counts = _queue_status_counts(conn, table)
                if status_counts is not None:
                    workers.setdefault(worker_name, empty_worker_status())["queue_depth"] = sum(
                        status_counts.get(status, 0) for status in QUEUE_DEPTH_STATUSES
                    )
    except Exception:
        return


def _queue_status_counts(conn: object, table: str) -> dict[str, int] | None:
    try:
        rows = conn.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status").fetchall()
    except Exception:
        return None
    counts: dict[str, int] = {}
    for row in rows:
        status = row["status"] if isinstance(row, dict) else row[0]
        count = row["count"] if isinstance(row, dict) else row[1]
        counts[str(status)] = int(count or 0)
    return counts
