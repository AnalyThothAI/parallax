from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from parallax.app.runtime.queue_health import empty_queue_health, fill_worker_queue_healths
from parallax.app.runtime.worker_manifest import (
    manifest_by_name,
    manifests_by_lane,
)


@dataclass(frozen=True, slots=True)
class WorkerLaneStatus:
    lane: str
    enabled_workers: int
    running_workers: int
    stopped_workers: int
    disabled_workers: int
    intentionally_not_started_workers: int
    unavailable_workers: int
    degraded_workers: int
    failed_workers: int
    soft_timed_out_workers: int
    hard_timed_out_workers: int
    oldest_active_run_once_age_ms: int | None
    iteration_duration_p99_ms: float | None
    queue_depth: int | None
    queue_health: dict[str, Any]


def workers_status_payload(runtime: object) -> dict[str, Any]:
    workers = manifest_worker_statuses(_runtime_worker_statuses(runtime))
    fill_worker_queue_healths(workers, runtime)
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
            if key == "effective_status":
                continue
            status.setdefault(key, value)
        status["effective_status"] = _worker_effective_status(status)
        if status.get("unavailable_reason") is not None:
            status["unavailable_reason"] = str(status["unavailable_reason"])
    return workers


def empty_worker_status() -> dict[str, Any]:
    return {
        "enabled": False,
        "running": False,
        "effective_status": "disabled",
        "unavailable_reason": None,
        "last_started_at_ms": None,
        "last_finished_at_ms": None,
        "last_result": None,
        "last_error": None,
        "iteration_duration_p99_ms": None,
        "queue_depth": None,
        "queue_health": empty_queue_health(),
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
                running_workers=sum(1 for status in statuses if _worker_effective_status(status) == "running"),
                stopped_workers=sum(1 for status in statuses if _worker_effective_status(status) == "stopped"),
                disabled_workers=sum(1 for status in statuses if _worker_effective_status(status) == "disabled"),
                intentionally_not_started_workers=sum(
                    1 for status in statuses if _worker_effective_status(status) == "intentionally_not_started"
                ),
                unavailable_workers=sum(1 for status in statuses if _worker_effective_status(status) == "unavailable"),
                degraded_workers=sum(1 for status in statuses if _worker_effective_status(status) == "degraded"),
                failed_workers=sum(1 for status in statuses if _worker_effective_status(status) == "failed"),
                soft_timed_out_workers=sum(
                    1 for status in statuses if status.get("active_run_once_soft_timed_out_at_ms") is not None
                ),
                hard_timed_out_workers=sum(
                    1 for status in statuses if status.get("active_run_once_hard_timed_out_at_ms") is not None
                ),
                oldest_active_run_once_age_ms=_max_int(status.get("active_run_once_age_ms") for status in statuses),
                iteration_duration_p99_ms=_max_float(status.get("iteration_duration_p99_ms") for status in statuses),
                queue_depth=_sum_int_or_none(status.get("queue_depth") for status in statuses),
                queue_health=_lane_queue_health(statuses),
            )
        )
    return lanes


def effective_worker_status(status: Mapping[str, Any]) -> str:
    return _worker_effective_status(dict(status))


def _worker_effective_status(status: dict[str, Any]) -> str:
    explicit = status.get("effective_status")
    if isinstance(explicit, str) and explicit in {
        "disabled",
        "intentionally_not_started",
        "unavailable",
        "degraded",
        "running",
        "stopped",
        "failed",
    }:
        return explicit
    if not status.get("enabled"):
        return "disabled"
    if _worker_failed(status):
        return "failed"
    if _worker_degraded(status):
        return "degraded"
    if status.get("running"):
        return "running"
    return "stopped"


def _worker_failed(status: dict[str, Any]) -> bool:
    if status.get("last_error"):
        return True
    result = status.get("last_result")
    if not isinstance(result, dict):
        return False
    if result.get("ok") is False:
        return True
    return _positive_result_count(result, "failed") or _positive_result_count(result, "dead")


def _positive_result_count(result: dict[str, Any], key: str) -> bool:
    try:
        return int(result.get(key) or 0) > 0
    except (TypeError, ValueError):
        return False


def _worker_degraded(status: dict[str, Any]) -> bool:
    result = status.get("last_result")
    if not isinstance(result, dict):
        return False
    if result.get("degraded") is True:
        return True
    if str(result.get("status") or "").strip().lower() == "degraded":
        return True
    notes = result.get("notes")
    if not isinstance(notes, dict):
        return False
    if notes.get("degraded") is True:
        return True
    return str(notes.get("status") or "").strip().lower() == "degraded"


def _max_int(values: object) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return max(integers) if integers else None


def _max_float(values: object) -> float | None:
    floats = [float(value) for value in values if value is not None]
    return max(floats) if floats else None


def _sum_int_or_none(values: object) -> int | None:
    integers = [int(value) for value in values if value is not None]
    return sum(integers) if integers else None


def _lane_queue_health(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    queue_healths: list[dict[str, Any]] = []
    for worker_status in statuses:
        health = worker_status.get("queue_health")
        if isinstance(health, dict) and health.get("table_count"):
            queue_healths.append(health)
    if not queue_healths:
        return empty_queue_health()
    blocked_count = _sum_health_int(queue_healths, "blocked_count")
    failed_count = _sum_health_int(queue_healths, "failed_count")
    unavailable_count = _sum_health_int(queue_healths, "unavailable_table_count")
    contract_failure_count = _sum_health_int(queue_healths, "contract_failure_count")
    adapter_error_count = _sum_health_int(queue_healths, "adapter_error_count")
    manifest_mismatch_count = _sum_health_int(queue_healths, "manifest_mismatch_count")
    queue_depth = _sum_health_int(queue_healths, "queue_depth")
    status = _lane_queue_status(queue_healths)
    return {
        "status": status,
        "reason": _lane_queue_reason(
            status,
            unavailable_count=unavailable_count,
            blocked_count=blocked_count,
            adapter_error_count=adapter_error_count,
            manifest_mismatch_count=manifest_mismatch_count,
        ),
        "table_count": _sum_health_int(queue_healths, "table_count"),
        "unavailable_table_count": unavailable_count,
        "contract_failure_count": contract_failure_count,
        "adapter_error_count": adapter_error_count,
        "manifest_mismatch_count": manifest_mismatch_count,
        "queue_depth": queue_depth,
        "due_count": _sum_health_int(queue_healths, "due_count"),
        "running_count": _sum_health_int(queue_healths, "running_count"),
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "source_terminal_count": _sum_health_int(queue_healths, "source_terminal_count"),
        "terminal_count": _sum_health_int(queue_healths, "terminal_count"),
        "unresolved_terminal_count": _sum_health_int(queue_healths, "unresolved_terminal_count"),
        "oldest_due_age_ms": _max_int(health.get("oldest_due_age_ms") for health in queue_healths),
        "oldest_running_age_ms": _max_int(health.get("oldest_running_age_ms") for health in queue_healths),
        "max_attempt_count": _max_int(health.get("max_attempt_count") for health in queue_healths),
    }


def _sum_health_int(queue_healths: list[dict[str, Any]], key: str) -> int:
    total = 0
    for health in queue_healths:
        total += int(health.get(key) or 0)
    return total


def _lane_queue_status(queue_healths: list[dict[str, Any]]) -> str:
    statuses = [str(health.get("status")) for health in queue_healths]
    for status in ("unavailable", "blocked", "degraded", "ok"):
        if status in statuses:
            return status
    return "idle"


def _lane_queue_reason(
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
