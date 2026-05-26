from __future__ import annotations

import pytest

from gmgn_twitter_intel.app.runtime.worker_status import manifest_worker_statuses, worker_lane_statuses


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
    assert projection["running_workers"] >= 1
    assert projection["failed_workers"] >= 2
    assert projection["soft_timed_out_workers"] >= 1
    assert projection["hard_timed_out_workers"] >= 1
    assert projection["oldest_active_run_once_age_ms"] == 50
    assert projection["iteration_duration_p99_ms"] == 30.0
    assert projection["queue_depth"] == 7
