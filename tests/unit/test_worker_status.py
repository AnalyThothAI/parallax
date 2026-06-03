from __future__ import annotations

import pytest

from parallax.app.runtime.worker_status import manifest_worker_statuses, worker_lane_statuses


def test_manifest_worker_statuses_rejects_unknown_worker_entries() -> None:
    with pytest.raises(ValueError, match="Unknown worker status entries: stray_worker"):
        manifest_worker_statuses({"stray_worker": {}})


def test_worker_lane_statuses_aggregate_failures_timeouts_and_depths() -> None:
    workers = manifest_worker_statuses(
        {
            "token_radar_projection": {
                "enabled": True,
                "running": True,
                "last_error": RuntimeError("projection failed"),
                "iteration_duration_p99_ms": 12.5,
                "queue_depth": 5,
                "queue_health": {
                    "status": "blocked",
                    "reason": "blocked_work_present",
                    "table_count": 1,
                    "unavailable_table_count": 0,
                    "queue_depth": 5,
                    "due_count": 2,
                    "running_count": 1,
                    "failed_count": 0,
                    "blocked_count": 3,
                    "terminal_count": 4,
                    "unresolved_terminal_count": 3,
                    "oldest_due_age_ms": 100,
                    "oldest_running_age_ms": 50,
                    "max_attempt_count": 2,
                    "tables": {},
                },
                "active_run_once_age_ms": 20,
                "active_run_once_soft_timed_out_at_ms": 1_000,
            },
            "token_profile_current": {
                "enabled": True,
                "running": False,
                "last_result": {"ok": False},
                "iteration_duration_p99_ms": 30.0,
                "queue_depth": 2,
                "active_run_once_age_ms": 50,
                "active_run_once_hard_timed_out_at_ms": 2_000,
            },
        }
    )

    projection = worker_lane_statuses(workers)["projection"]

    assert projection["enabled_workers"] >= 2
    assert projection["running_workers"] == 0
    assert projection["failed_workers"] >= 2
    assert projection["soft_timed_out_workers"] >= 1
    assert projection["hard_timed_out_workers"] >= 1
    assert projection["oldest_active_run_once_age_ms"] == 50
    assert projection["iteration_duration_p99_ms"] == 30.0
    assert projection["queue_depth"] == 7
    assert projection["queue_health"]["queue_depth"] == 5
    assert projection["queue_health"]["terminal_count"] == 4
    assert projection["queue_health"]["unresolved_terminal_count"] == 3
    assert projection["queue_health"]["blocked_count"] == 3


def test_worker_lane_statuses_count_each_worker_in_one_effective_status_bucket() -> None:
    workers = manifest_worker_statuses(
        {
            "token_profile_current": {
                "enabled": True,
                "running": True,
                "effective_status": "degraded",
            },
            "token_radar_projection": {
                "enabled": True,
                "running": False,
                "effective_status": "stopped",
            },
            "market_tick_current_projection": {
                "enabled": True,
                "running": False,
                "effective_status": "stopped",
            },
        }
    )

    projection = worker_lane_statuses(workers)["projection"]

    assert projection["degraded_workers"] == 1
    assert projection["running_workers"] == 0
    assert projection["stopped_workers"] == 2


def test_worker_lane_statuses_failed_result_counts_failed_before_degraded_notes() -> None:
    workers = manifest_worker_statuses(
        {
            "token_profile_current": {
                "enabled": True,
                "running": True,
                "last_result": {"failed": 1, "notes": {"degraded": True}},
            },
        }
    )

    projection = worker_lane_statuses(workers)["projection"]

    assert projection["failed_workers"] == 1
    assert projection["degraded_workers"] == 0
    assert projection["running_workers"] == 0
