from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_manifest import (
    manifest_by_name,
    manifests_by_lane,
    worker_queue_depth_tables,
)

QUEUE_DEPTH_STATUSES = ("pending", "failed", "running")


@dataclass(frozen=True, slots=True)
class WorkerLaneStatus:
    lane: str
    enabled_workers: int
    running_workers: int
    failed_workers: int
    soft_timed_out_workers: int
    hard_timed_out_workers: int
    oldest_active_run_once_age_ms: int | None
    iteration_duration_p99_ms: float | None
    queue_depth: int | None


def workers_status_payload(runtime: object) -> dict[str, Any]:
    workers = manifest_worker_statuses(_runtime_worker_statuses(runtime))
    fill_worker_queue_depths(workers, runtime)
    return {
        "workers": workers,
        "worker_lanes": worker_lane_statuses(workers),
    }


def _runtime_worker_statuses(runtime: object) -> dict[str, dict[str, Any]]:
    workers = runtime.scheduler.status_payload()
    if "collector" in manifest_by_name():
        collector_status = runtime.collector.status.to_dict()
        workers.setdefault("collector", {})
        workers["collector"] = {
            **workers["collector"],
            "details": collector_status,
        }
    return workers


def canonical_workers_status_payload(runtime: object) -> dict[str, dict[str, Any]]:
    return workers_status_payload(runtime)["workers"]


def manifest_worker_statuses(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    manifests = manifest_by_name()
    unknown_workers = set(payload) - set(manifests)
    if unknown_workers:
        raise ValueError(f"Unknown worker status entries: {', '.join(sorted(unknown_workers))}")
    workers = {name: dict(status) for name, status in payload.items()}
    for name in manifests:
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
        "active_run_once_started_at_ms": None,
        "active_run_once_age_ms": None,
        "active_run_once_soft_timed_out_at_ms": None,
        "active_run_once_hard_timed_out_at_ms": None,
        "active_run_once_count": 0,
        "details": {},
    }


def worker_lane_statuses(workers: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for lane, manifests in manifests_by_lane().items():
        lane_name = str(getattr(lane, "value", lane))
        statuses = [workers[manifest.name] for manifest in manifests if manifest.name in workers]
        lanes[lane_name] = asdict(
            WorkerLaneStatus(
                lane=lane_name,
                enabled_workers=sum(1 for status in statuses if status.get("enabled")),
                running_workers=sum(1 for status in statuses if status.get("running")),
                failed_workers=sum(1 for status in statuses if _worker_failed(status)),
                soft_timed_out_workers=sum(
                    1 for status in statuses if status.get("active_run_once_soft_timed_out_at_ms") is not None
                ),
                hard_timed_out_workers=sum(
                    1 for status in statuses if status.get("active_run_once_hard_timed_out_at_ms") is not None
                ),
                oldest_active_run_once_age_ms=_max_int(
                    status.get("active_run_once_age_ms") for status in statuses
                ),
                iteration_duration_p99_ms=_max_float(
                    status.get("iteration_duration_p99_ms") for status in statuses
                ),
                queue_depth=_sum_int_or_none(status.get("queue_depth") for status in statuses),
            )
        )
    return lanes


def fill_worker_queue_depths(workers: dict[str, dict[str, Any]], runtime: object) -> None:
    db = getattr(runtime, "db", None)
    api_pool = getattr(db, "api_pool", None)
    connection = getattr(api_pool, "connection", None)
    if connection is None:
        return
    try:
        with connection() as conn:
            for worker_name, table in worker_queue_depth_tables().items():
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


def _worker_failed(status: dict[str, Any]) -> bool:
    if status.get("last_error"):
        return True
    result = status.get("last_result")
    return isinstance(result, dict) and result.get("ok") is False


def _max_int(values: object) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return max(integers) if integers else None


def _max_float(values: object) -> float | None:
    floats = [float(value) for value in values if value is not None]
    return max(floats) if floats else None


def _sum_int_or_none(values: object) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return sum(integers) if integers else None
