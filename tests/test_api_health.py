import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

import gmgn_twitter_intel.app.runtime.app as app_module
from gmgn_twitter_intel.app.runtime.app import _build_runtime, _readiness_payload, create_app
from gmgn_twitter_intel.platform.config.settings import CollectorConfig, Settings
from gmgn_twitter_intel.platform.db.postgres_client import postgres_health_check
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version
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
    assert ready.json()["pulse_agent"]["enabled"] is False
    assert ready.json()["pulse_agent"]["configured"] is False
    assert ready.json()["pulse_agent"]["worker_running"] is False
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
    assert status["migration_version"] == latest_migration_version()


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


def test_build_runtime_creates_pulse_worker_when_enabled_and_configured(monkeypatch, tmp_path):
    class FakePool:
        @contextmanager
        def connection(self):
            yield object()

        def close(self):
            return None

    class FakePulseProvider:
        provider = "fake"
        timeout_seconds = 1.0
        artifact_version_hash = "artifact:gpt-pulse"

        def __init__(self, *, model):
            self.model = model

    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        llm={
            "api_key": "test-key",
            "pulse_agent_enabled": True,
            "pulse_agent_model": "gpt-pulse",
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    monkeypatch.setattr(app_module, "create_pool", lambda *_, **__: FakePool())
    monkeypatch.setattr(app_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(
        app_module,
        "wire_providers",
        lambda settings, *, start_collector: SimpleNamespace(
            ingestion=SimpleNamespace(upstream_client_factory=None),
            asset_market=SimpleNamespace(
                projection_dex_market=None,
                sync_cex_market=None,
                sync_dex_market=None,
                message_cex_market=None,
                message_dex_market=None,
                discovery_dex_market=None,
                discovery_chain_ids=(),
            ),
            social_enrichment=SimpleNamespace(event_enrichment=None),
            pulse_lab=SimpleNamespace(recommendation_provider=FakePulseProvider(model=settings.pulse_agent_model)),
        ),
    )

    runtime = _build_runtime(settings, start_collector=False)

    try:
        assert runtime.pulse_candidate_worker is not None
        assert runtime.pulse_candidate_worker.recommendation_client.model == "gpt-pulse"
        assert runtime.pulse_candidate_worker.batch_size == settings.pulse_agent_batch_size
    finally:
        runtime.db_pool.close()


def test_start_runtime_tasks_starts_pulse_worker_task():
    async def scenario():
        runtime = _minimal_runtime()
        runtime.pulse_candidate_worker = FakePulseWorker()

        app_module._start_runtime_tasks(runtime)

        try:
            assert runtime.pulse_candidate_task is not None
            assert not runtime.pulse_candidate_task.done()
        finally:
            runtime.pulse_candidate_task.cancel()
            await asyncio.gather(runtime.pulse_candidate_task, return_exceptions=True)

    asyncio.run(scenario())


def test_watchdog_reports_stopped_pulse_worker_when_created():
    runtime = _minimal_runtime()
    runtime.pulse_candidate_worker = FakePulseWorker()
    runtime.pulse_candidate_task = DoneTask()

    reasons = app_module._watchdog_unhealthy_reasons(runtime, now_ms=12_001)

    assert "pulse_candidate_worker_stopped" in reasons


def test_readiness_includes_pulse_agent_fields(monkeypatch):
    runtime = _minimal_runtime()
    runtime.pulse_candidate_worker = SimpleNamespace(
        last_started_at_ms=1_000,
        last_run_at_ms=2_000,
        last_result={"processed": 1},
        last_error=None,
    )
    runtime.pulse_candidate_task = RunningTask()
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})
    monkeypatch.setattr(app_module, "_enrichment_job_counts", lambda _: {})
    monkeypatch.setattr(app_module, "_notification_summary", lambda _: {})

    payload, status_code = _readiness_payload(runtime, now_ms=12_001)

    assert status_code == 200
    assert payload["pulse_agent"]["enabled"] is True
    assert payload["pulse_agent"]["configured"] is True
    assert payload["pulse_agent"]["worker_running"] is True
    assert payload["pulse_agent"]["model"] == "gpt-pulse"
    assert payload["pulse_agent"]["last_result"] == {"processed": 1}


def test_stop_runtime_closes_pulse_worker_client():
    async def scenario():
        runtime = _minimal_runtime()
        runtime.collector = SimpleNamespace(stop=_noop_async)
        runtime.db_pool = SimpleNamespace(close=lambda: None)
        runtime.pulse_candidate_worker = FakePulseWorker()

        await app_module._stop_runtime(runtime)

        assert runtime.pulse_candidate_worker.stopped is True
        assert runtime.pulse_candidate_worker.closed is True

    asyncio.run(scenario())


class FakePulseWorker:
    last_started_at_ms = None
    last_run_at_ms = None
    last_result = None
    last_error = None

    def __init__(self):
        self.stopped = False
        self.closed = False

    async def run(self):
        await asyncio.Event().wait()

    def stop(self):
        self.stopped = True

    async def aclose(self):
        self.closed = True


async def _noop_async():
    return None


class RunningTask:
    def done(self):
        return False

    def cancel(self):
        return None


class DoneTask:
    def done(self):
        return True

    def cancel(self):
        return None


def _minimal_runtime():
    settings = SimpleNamespace(
        handles=("toly",),
        llm_configured=False,
        llm_trace_enabled=False,
        llm_trace_export_configured=False,
        llm_trace_include_sensitive_data=False,
        enrichment_concurrency=1,
        notifications=SimpleNamespace(enabled=False),
        pulse_agent_enabled=True,
        pulse_agent_configured=True,
        pulse_agent_model="gpt-pulse",
        pulse_agent_batch_size=7,
        pulse_agent_interval_seconds=11.0,
        pulse_agent_max_attempts=4,
        okx_cex_sync_enabled=False,
    )
    return SimpleNamespace(
        settings=settings,
        start_collector=False,
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0})),
        collector_task=None,
        enrichment_worker=None,
        enrichment_task=None,
        harness_ops_worker=None,
        harness_ops_task=None,
        notification_worker=None,
        notification_task=None,
        notification_delivery_worker=None,
        notification_delivery_task=None,
        asset_market_sync_worker=None,
        asset_market_sync_task=None,
        message_market_observation_worker=None,
        message_market_observation_task=None,
        token_discovery_worker=None,
        token_discovery_task=None,
        token_radar_projection_worker=None,
        token_radar_projection_task=None,
        pulse_candidate_worker=None,
        pulse_candidate_task=None,
        supervisor_task=None,
        db_pool=SimpleNamespace(close=lambda: None),
    )
