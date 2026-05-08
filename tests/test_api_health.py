import asyncio

from fastapi.testclient import TestClient

import gmgn_twitter_intel.api.app as app_module
from gmgn_twitter_intel.api.app import _build_runtime, _readiness_payload, create_app
from gmgn_twitter_intel.settings import CollectorConfig, Settings
from gmgn_twitter_intel.storage.postgres_client import postgres_health_check
from tests.postgres_test_utils import postgres_settings_storage, prepare_postgres_database


def make_settings(tmp_path, **kwargs) -> Settings:
    prepare_postgres_database()
    settings = Settings(
        handles=kwargs.pop("handles", ("toly",)),
        ws_token=kwargs.pop("ws_token", "secret"),
        storage=postgres_settings_storage(),
        **kwargs,
    )
    settings.set_config_dir(tmp_path / "app-home")
    return settings


def stop_runtime(runtime) -> None:
    asyncio.run(app_module._stop_runtime(runtime))


def test_healthz_and_readyz_return_status(tmp_path):
    settings = make_settings(tmp_path)
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
    assert ready.json()["store"] == "postgresql"
    assert ready.json()["db"]["ok"] is True
    assert ready.json()["db"]["probe"] == "postgres_liveness"
    assert ready.json()["enrichment"]["llm_configured"] is False
    assert ready.json()["enrichment"]["worker_running"] is False
    assert ready.json()["enrichment"]["job_counts"]["pending"] == 0
    assert ready.json()["harness_ops"]["worker_running"] is True
    assert ready.json()["token_radar_projection"]["worker_running"] is True
    assert ready.json()["message_market_observation"]["worker_running"] is False
    assert "token_resolution" not in ready.json()
    assert "provider_status" not in ready.json()


def test_runtime_postgres_health_check_reports_migration_version(tmp_path):
    settings = make_settings(tmp_path)
    runtime = _build_runtime(settings, start_collector=False)

    try:
        with runtime.db_pool.connection() as conn:
            status = postgres_health_check(conn)
    finally:
        stop_runtime(runtime)

    assert status["ok"] is True
    assert status["probe"] == "postgres_liveness"
    assert status["migration_version"] == "20260508_0011"


def test_runtime_uses_pool_sessions_without_pinned_connections(tmp_path):
    settings = make_settings(tmp_path)
    runtime = _build_runtime(settings, start_collector=False)

    try:
        assert not hasattr(runtime, "write_conn")
        assert not hasattr(runtime, "read_conn")
        assert not hasattr(runtime, "write_lock")
        with runtime.repositories() as repos:
            status = postgres_health_check(repos.conn)
    finally:
        stop_runtime(runtime)

    assert status["ok"] is True


def test_readiness_marks_started_collector_without_frames_unhealthy(tmp_path):
    class RunningTask:
        def done(self):
            return False

        def cancel(self):
            return None

    settings = make_settings(tmp_path, collector=CollectorConfig(stale_timeout=10))
    runtime = _build_runtime(settings, start_collector=False)
    runtime.start_collector = True
    runtime.collector_task = RunningTask()
    runtime.collector.status.started_at_ms = 1_000

    try:
        payload, status_code = _readiness_payload(runtime, now_ms=12_001)
    finally:
        runtime.db_pool.close()

    assert status_code == 503
    assert payload["ok"] is False
    assert "no_upstream_frames" in payload["reasons"]


def test_readiness_marks_database_probe_failure_unhealthy(tmp_path):
    settings = make_settings(tmp_path)
    runtime = _build_runtime(settings, start_collector=False)
    runtime.db_pool.close()

    try:
        payload, status_code = _readiness_payload(runtime)
    finally:
        pass

    assert status_code == 503
    assert payload["ok"] is False
    assert payload["db"]["ok"] is False
    assert "database_unhealthy" in payload["reasons"]


def test_watchdog_reasons_do_not_probe_database(tmp_path):
    class RunningTask:
        def done(self):
            return False

        def cancel(self):
            return None

    settings = make_settings(tmp_path, collector=CollectorConfig(stale_timeout=10))
    runtime = _build_runtime(settings, start_collector=False)
    runtime.start_collector = True
    runtime.collector_task = RunningTask()
    runtime.harness_ops_task = RunningTask()
    runtime.notification_task = RunningTask()
    runtime.token_radar_projection_task = RunningTask()
    runtime.collector.status.started_at_ms = 1_000
    runtime.db_pool.close()

    try:
        assert hasattr(app_module, "_watchdog_unhealthy_reasons")
        reasons = app_module._watchdog_unhealthy_reasons(runtime, now_ms=12_001)
    finally:
        pass

    assert reasons == ["no_upstream_frames"]
