from fastapi.testclient import TestClient

import gmgn_twitter_intel.api.app as app_module
from gmgn_twitter_intel.api.app import _build_runtime, _readiness_payload, create_app
from gmgn_twitter_intel.settings import CollectorConfig, Settings
from gmgn_twitter_intel.storage.sqlite_client import sqlite_health_check


def test_healthz_and_readyz_return_status(tmp_path):
    settings = Settings(
        handles=("toly",),
        ws_token="secret",
    )
    settings.set_config_dir(tmp_path / "app-home")
    app = create_app(
        settings=settings,
        start_collector=False,
    )

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.text == "ok\n"
    assert ready.status_code == 200
    assert ready.json()["collector"]["frames_received"] == 0
    assert ready.json()["store"].endswith("twitter_intel.sqlite3")
    assert ready.json()["db"]["ok"] is True
    assert ready.json()["db"]["probe"] == "sqlite_liveness"
    assert ready.json()["enrichment"]["llm_configured"] is False
    assert ready.json()["enrichment"]["worker_running"] is False
    assert ready.json()["enrichment"]["job_counts"]["pending"] == 0
    assert "provider_status" not in ready.json()


def test_runtime_sqlite_health_check_does_not_run_integrity_scan(tmp_path):
    settings = Settings(handles=("toly",), ws_token="secret")
    settings.set_config_dir(tmp_path / "app-home")
    runtime = _build_runtime(settings, start_collector=False)
    statements: list[str] = []
    runtime.evidence.conn.set_trace_callback(statements.append)

    try:
        status = sqlite_health_check(runtime.evidence.conn)
    finally:
        runtime.evidence.close()
        runtime.read_evidence.close()

    assert status["ok"] is True
    assert status["probe"] == "sqlite_liveness"
    assert all("quick_check" not in statement.lower() for statement in statements)
    assert all("integrity_check" not in statement.lower() for statement in statements)


def test_readiness_marks_started_collector_without_frames_unhealthy(tmp_path):
    class RunningTask:
        def done(self):
            return False

    settings = Settings(
        handles=("toly",),
        ws_token="secret",
        collector=CollectorConfig(stale_timeout=10),
    )
    settings.set_config_dir(tmp_path / "app-home")
    runtime = _build_runtime(settings, start_collector=False)
    runtime.start_collector = True
    runtime.collector_task = RunningTask()
    runtime.collector.status.started_at_ms = 1_000

    try:
        payload, status_code = _readiness_payload(runtime, now_ms=12_001)
    finally:
        runtime.evidence.close()
        runtime.read_evidence.close()

    assert status_code == 503
    assert payload["ok"] is False
    assert "no_upstream_frames" in payload["reasons"]


def test_readiness_marks_database_probe_failure_unhealthy(tmp_path):
    settings = Settings(
        handles=("toly",),
        ws_token="secret",
    )
    settings.set_config_dir(tmp_path / "app-home")
    runtime = _build_runtime(settings, start_collector=False)
    runtime.read_evidence.conn.close()

    try:
        payload, status_code = _readiness_payload(runtime)
    finally:
        runtime.evidence.close()

    assert status_code == 503
    assert payload["ok"] is False
    assert payload["db"]["ok"] is False
    assert "database_unhealthy" in payload["reasons"]


def test_watchdog_reasons_do_not_probe_database(tmp_path):
    class RunningTask:
        def done(self):
            return False

    settings = Settings(
        handles=("toly",),
        ws_token="secret",
        collector=CollectorConfig(stale_timeout=10),
    )
    settings.set_config_dir(tmp_path / "app-home")
    runtime = _build_runtime(settings, start_collector=False)
    runtime.start_collector = True
    runtime.collector_task = RunningTask()
    runtime.market_observation_task = RunningTask()
    runtime.notification_task = RunningTask()
    runtime.collector.status.started_at_ms = 1_000
    runtime.evidence.conn.close()

    try:
        assert hasattr(app_module, "_watchdog_unhealthy_reasons")
        reasons = app_module._watchdog_unhealthy_reasons(runtime, now_ms=12_001)
    finally:
        runtime.read_evidence.close()

    assert reasons == ["no_upstream_frames"]
