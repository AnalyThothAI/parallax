from __future__ import annotations

import pytest

from parallax.app.runtime.worker_status import manifest_worker_statuses, worker_lane_statuses


def test_manifest_worker_statuses_rejects_unknown_worker_entries() -> None:
    with pytest.raises(ValueError, match="Unknown worker status entries: stray_worker"):
        manifest_worker_statuses({"stray_worker": {}})


def test_worker_lane_statuses_aggregate_failures_and_timeouts() -> None:
    workers = manifest_worker_statuses(
        {
            "token_radar_projection": {
                "enabled": True,
                "running": True,
                "last_error": RuntimeError("projection failed"),
                "iteration_duration_p99_ms": 12.5,
                "active_run_once_age_ms": 20,
            },
            "token_profile_current": {
                "enabled": True,
                "running": False,
                "last_result": {"ok": False},
                "iteration_duration_p99_ms": 30.0,
                "active_run_once_age_ms": 50,
                "active_run_once_hard_timed_out_at_ms": 2_000,
            },
        }
    )

    projection = worker_lane_statuses(workers)["projection"]

    assert projection["enabled_workers"] >= 2
    assert projection["running_workers"] == 0
    assert projection["failed_workers"] >= 2
    assert "soft_timed_out_workers" not in projection
    assert projection["hard_timed_out_workers"] >= 1
    assert projection["oldest_active_run_once_age_ms"] == 50
    assert projection["iteration_duration_p99_ms"] == 30.0


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
