from __future__ import annotations

import io
import json
from collections import Counter
from types import SimpleNamespace

from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.cli import main


def test_cli_ops_worker_status_emits_manifest_workers_lanes_and_queue_depths(monkeypatch):
    from parallax.app.surfaces.cli.commands import ops as ops_module

    closed = {"value": False}
    captured = {}
    manifest_names = tuple(manifest.name for manifest in all_worker_manifests())
    base_worker = {
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
        "effective_status": "disabled",
        "unavailable_reason": None,
    }
    status_overrides = {
        "collector": {
            **base_worker,
            "effective_status": "intentionally_not_started",
        },
        "market_tick_stream": {
            **base_worker,
            "enabled": True,
            "running": True,
            "effective_status": "running",
        },
        "market_tick_poll": {
            **base_worker,
            "enabled": True,
            "effective_status": "stopped",
        },
        "token_radar_projection": {
            **base_worker,
            "enabled": True,
            "effective_status": "unavailable",
            "unavailable_reason": "missing_projection_dependency",
        },
        "token_profile_current": {
            **base_worker,
            "enabled": True,
            "running": True,
            "effective_status": "degraded",
            "unavailable_reason": "optional_profile_source_missing",
        },
        "pulse_candidate": {
            **base_worker,
            "enabled": True,
            "last_error": "agent lane failed",
            "effective_status": "failed",
        },
    }

    class FakeRows:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class FakeConn:
        def execute(self, sql, params=()):
            if "worker_queue_terminal_events" in sql:
                if "GROUP BY final_reason_bucket" in sql:
                    return FakeRows([])
                return FakeRows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
            if "GROUP BY status" not in sql:
                if "pulse_agent_jobs" in sql:
                    return FakeRows(
                        [
                            {
                                "total_count": 6,
                                "active_count": 6,
                                "due_count": 2,
                                "running_count": 1,
                                "failed_count": 3,
                                "blocked_count": 0,
                                "source_terminal_count": 0,
                                "oldest_due_at_ms": 1,
                                "oldest_running_at_ms": 2,
                                "max_attempt_count": 2,
                            }
                        ]
                    )
                if "notification_deliveries" in sql:
                    return FakeRows(
                        [
                            {
                                "total_count": 103,
                                "active_count": 4,
                                "due_count": 4,
                                "running_count": 0,
                                "failed_count": 0,
                                "blocked_count": 0,
                                "source_terminal_count": 0,
                                "oldest_due_at_ms": 1,
                                "oldest_running_at_ms": None,
                                "max_attempt_count": 1,
                            }
                        ]
                    )
                return FakeRows(
                    [
                        {
                            "total_count": 0,
                            "active_count": 0,
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
            if "pulse_agent_jobs" in sql:
                return FakeRows(
                    [
                        {"status": "pending", "count": 2},
                        {"status": "failed", "count": 3},
                        {"status": "running", "count": 1},
                    ]
                )
            if "notification_deliveries" in sql:
                return FakeRows(
                    [
                        {"status": "pending", "count": 4},
                        {"status": "delivered", "count": 99},
                    ]
                )
            return FakeRows([])

    class FakeConnectionContext:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def connection(self):
            return FakeConnectionContext()

    class FakeRuntime:
        def __init__(self):
            self.db = SimpleNamespace(api_pool=FakePool())
            self.collector = SimpleNamespace(
                status=SimpleNamespace(
                    to_dict=lambda: {
                        "started_at_ms": 1_700_000_000_000,
                        "frames_received": 88,
                        "twitter_events": 44,
                        "matched_twitter_events": 7,
                        "events_published": 7,
                        "duplicate_twitter_events": 0,
                        "duplicate_matched_twitter_events": 0,
                        "parse_errors": 0,
                        "snapshot_gate_outcomes": {"immediate_complete": 3},
                    }
                ),
                upstream_client=None,
            )
            self.scheduler = SimpleNamespace(
                status_payload=lambda: {name: dict(status_overrides.get(name, base_worker)) for name in manifest_names}
            )

        async def aclose(self):
            closed["value"] = True

    def fake_bootstrap(settings, *, start_collector):
        captured["settings"] = settings
        captured["start_collector"] = start_collector
        return FakeRuntime()

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace(ws_token="secret"))
    monkeypatch.setattr(ops_module, "bootstrap", fake_bootstrap)

    stdout = io.StringIO()
    code = main(["ops", "worker-status"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert captured["start_collector"] is False
    assert closed["value"] is True
    workers = payload["data"]["workers"]
    worker_lanes = payload["data"]["worker_lanes"]
    assert set(manifest_names).issubset(workers)
    assert all("queue_depth" in workers[name] for name in manifest_names)
    assert all("active_run_once_age_ms" in workers[name] for name in manifest_names)
    assert all("active_run_once_count" in workers[name] for name in manifest_names)
    assert "projection" in worker_lanes
    assert "agent" in worker_lanes
    lane_totals = Counter()
    for lane in worker_lanes.values():
        lane_totals.update(
            {
                "disabled": lane["disabled_workers"],
                "intentionally_not_started": lane["intentionally_not_started_workers"],
                "unavailable": lane["unavailable_workers"],
                "degraded": lane["degraded_workers"],
                "running": lane["running_workers"],
                "stopped": lane["stopped_workers"],
                "failed": lane["failed_workers"],
            }
        )
    assert lane_totals["disabled"] >= 1
    assert lane_totals["intentionally_not_started"] == 1
    assert lane_totals["unavailable"] == 1
    assert lane_totals["degraded"] == 1
    assert lane_totals["running"] >= 1
    assert lane_totals["stopped"] >= 1
    assert lane_totals["failed"] == 1
    assert workers["token_radar_projection"]["effective_status"] == "unavailable"
    assert workers["token_radar_projection"]["unavailable_reason"] == "missing_projection_dependency"
    assert workers["collector"]["effective_status"] == "intentionally_not_started"
    assert workers["pulse_candidate"]["queue_depth"] == 6
    assert workers["notification_delivery"]["queue_depth"] == 4
    assert workers["collector"]["details"]["frames_received"] == 88
    assert workers["collector"]["details"]["matched_twitter_events"] == 7
    assert workers["collector"]["details"]["snapshot_gate_outcomes"] == {"immediate_complete": 3}
    old_summary_jobs = "_".join(("watchlist", "summary", "jobs"))
    assert old_summary_jobs not in json.dumps(payload)
