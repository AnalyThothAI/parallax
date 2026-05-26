from __future__ import annotations

import io
import json
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests
from gmgn_twitter_intel.cli import main


def test_cli_ops_worker_status_emits_manifest_workers_lanes_and_queue_depths(monkeypatch):
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

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
    }

    class FakeRows:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConn:
        def execute(self, sql, params=()):
            if "enrichment_jobs" in sql:
                return FakeRows(
                    [
                        {"status": "pending", "count": 2},
                        {"status": "failed", "count": 3},
                        {"status": "running", "count": 1},
                    ]
                )
            if "watchlist_handle_summary_jobs" in sql:
                return FakeRows(
                    [
                        {"status": "pending", "count": 1},
                        {"status": "running", "count": 2},
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
                status_payload=lambda: {name: dict(base_worker) for name in manifest_names}
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
    assert worker_lanes["agent"]["queue_depth"] == 9
    assert workers["enrichment"]["queue_depth"] == 6
    assert workers["handle_summary"]["queue_depth"] == 3
    assert workers["notification_delivery"]["queue_depth"] == 4
    assert workers["collector"]["details"]["frames_received"] == 88
    assert workers["collector"]["details"]["matched_twitter_events"] == 7
    assert workers["collector"]["details"]["snapshot_gate_outcomes"] == {"immediate_complete": 3}
    old_summary_jobs = "_".join(("watchlist", "summary", "jobs"))
    assert old_summary_jobs not in json.dumps(payload)
