import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import parallax.app.runtime.app as app_module
import parallax.app.runtime.bootstrap as bootstrap_module
from parallax.app.runtime.app import _readiness_payload, create_app
from parallax.app.runtime.bootstrap import Runtime, bootstrap
from parallax.platform.config.settings import Settings
from parallax.platform.db.postgres_client import postgres_health_check
from parallax.platform.db.postgres_migrations import latest_migration_version
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


def close_runtime(runtime: Runtime) -> None:
    asyncio.run(runtime.aclose())


class FakePool:
    def __init__(self) -> None:
        self.closed = False

    @contextmanager
    def connection(self):
        yield FakeQueueHealthConn()

    def close(self):
        self.closed = True


class FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeQueueHealthConn:
    def execute(self, sql, params=None):
        if "FROM worker_queue_terminal_events" in sql:
            return FakeRows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
        if "GROUP BY status" in sql:
            return FakeRows([{"status": "pending", "count": 1}])
        return FakeRows(
            [
                {
                    "total_count": 1,
                    "active_count": 1,
                    "due_count": 0,
                    "running_count": 0,
                    "failed_count": 0,
                    "blocked_count": 0,
                    "oldest_due_at_ms": None,
                    "oldest_running_at_ms": None,
                    "max_attempt_count": 0,
                }
            ]
        )


class FakeDB:
    def __init__(self) -> None:
        self.api_pool = FakePool()
        self.worker_pool = FakePool()
        self.tool_pool = FakePool()
        self.wake_pool = FakePool()

    @contextmanager
    def api_session(self):
        yield SimpleNamespace()

    @contextmanager
    def worker_session(self, _name):
        yield SimpleNamespace()

    def wake_emitter(self):
        return None

    def wake_listener(self, _name, _channels):
        return None

    def acquire_advisory_lock_connection(self, _name, _key):
        return SimpleNamespace(release=lambda: None)


class FakePulseProvider:
    provider = "fake"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:gpt-pulse"

    def __init__(self, *, model):
        self.model = model


class FakeClosableProvider:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class FakeAsyncClosableProvider:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class FakeFailingProvider:
    def close(self) -> None:
        raise RuntimeError("provider failed")


class FakeProviderWrapper:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.closed = 0

    def close(self) -> None:
        self.closed += 1
        self.inner.close()


class FailingScheduler:
    def status_payload(self):
        return {}

    def unhealthy_reasons(self):
        return []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        raise RuntimeError("scheduler failed")


class NoopScheduler:
    def status_payload(self):
        return {}

    def unhealthy_reasons(self):
        return []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def fake_wired_providers(
    settings,
    *,
    start_collector,
    agent_execution_gateway=None,
    asset_market=None,
    news_intel=None,
    upstream_client_factory=None,
):
    return SimpleNamespace(
        ingestion=SimpleNamespace(upstream_client_factory=upstream_client_factory),
        asset_market=asset_market
        or SimpleNamespace(
            cex_market=None,
            dex_discovery_market=None,
            dex_quote_market=None,
            dex_candle_market=None,
            dex_profile_sources=(),
            stream_dex_market=None,
            discovery_chain_ids=(),
        ),
        pulse_lab=SimpleNamespace(
            decision_provider=FakePulseProvider(model=settings.agent_runtime_model_for_lane("pulse.decision"))
        ),
        narrative_intel=SimpleNamespace(narrative_provider=None),
        news_intel=news_intel or SimpleNamespace(feed_client=None, brief_provider=None),
        macrodata=SimpleNamespace(stock_quote_provider=None),
        agent_execution_gateway=agent_execution_gateway,
    )


def patch_runtime_dependencies(monkeypatch, *, asset_market=None, news_intel=None, upstream_client_factory=None):
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: FakeDB())
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(
        bootstrap_module,
        "wire_providers",
        lambda settings, *, start_collector, agent_execution_gateway=None, db_pool=None: fake_wired_providers(
            settings,
            start_collector=start_collector,
            agent_execution_gateway=agent_execution_gateway,
            asset_market=asset_market,
            news_intel=news_intel,
            upstream_client_factory=upstream_client_factory,
        ),
    )


def test_healthz_handler_is_async_to_avoid_threadpool_starvation(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings=settings, start_collector=False)

    route = next(route for route in app.routes if getattr(route, "path", None) == "/healthz")

    assert inspect.iscoroutinefunction(route.endpoint)


def test_healthz_readyz_and_metrics_return_status(monkeypatch, tmp_path):
    async def noop_scheduler_start(self) -> None:
        return None

    monkeypatch.setattr(
        "tests.integration.test_api_health.prepare_postgres_database",
        lambda: None,
    )
    monkeypatch.setattr(
        "parallax.app.runtime.worker_scheduler.WorkerScheduler.start",
        noop_scheduler_start,
    )
    patch_runtime_dependencies(monkeypatch, news_intel=SimpleNamespace(feed_client=object(), brief_provider=None))
    monkeypatch.setattr(
        app_module,
        "postgres_health_check",
        lambda *_, **__: {"ok": True, "probe": "postgres_liveness"},
    )
    settings = make_settings(tmp_path, workers={"cex_oi_radar_board": {"enabled": False}})
    app = create_app(settings=settings, start_collector=False)

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")
        api_status = client.get("/api/status", headers={"Authorization": "Bearer secret"})
        metrics = client.get("/metrics")

    payload = ready.json()
    api_status_payload = api_status.json()["data"]
    assert health.status_code == 200
    assert health.text == "ok\n"
    assert ready.status_code == 503
    assert api_status.status_code == 200
    assert api_status_payload["workers"] == payload["workers"]
    assert api_status_payload["worker_lanes"] == payload["worker_lanes"]
    assert api_status_payload["reasons"] == payload["reasons"]
    assert payload["store"] == "postgresql"
    assert payload["db"]["ok"] is True
    assert payload["db"]["probe"] == "postgres_liveness"
    legacy_worker_sections = {
        "collector",
        "enrichment",
        "notifications",
        "token_radar_projection",
        "watchlist_handle_summary",
        "market_tick_stream",
        "market_tick_poll",
        "token_capture_tier",
        "asset_profile_refresh",
        "resolution_refresh",
        "live_price_gateway",
        "pulse_agent",
        "token_resolution",
        "provider_status",
    }
    assert not (legacy_worker_sections & set(payload))
    assert set(payload["workers"]) >= {
        "collector",
        "token_radar_projection",
        "pulse_candidate",
        "event_anchor_backfill",
    }
    assert payload["workers"]["collector"]["enabled"] is False
    assert payload["workers"]["collector"]["effective_status"] == "intentionally_not_started"
    assert payload["workers"]["collector"]["unavailable_reason"] is None
    assert payload["workers"]["collector"]["last_result"] is None
    assert payload["workers"]["market_tick_stream"]["effective_status"] == "unavailable"
    assert payload["workers"]["market_tick_stream"]["unavailable_reason"] == "missing_asset_market_stream_provider"
    assert payload["workers"]["market_tick_poll"]["effective_status"] == "unavailable"
    assert payload["workers"]["market_tick_poll"]["unavailable_reason"] == "missing_asset_market_quote_provider"
    assert "worker:market_tick_stream:unavailable:missing_asset_market_stream_provider" in payload["reasons"]
    assert "worker:market_tick_poll:unavailable:missing_asset_market_quote_provider" in payload["reasons"]
    worker_unavailable_reasons = sorted(reason for reason in payload["reasons"] if ":unavailable:" in reason)
    assert worker_unavailable_reasons == [
        "worker:market_tick_poll:unavailable:missing_asset_market_quote_provider",
        "worker:market_tick_stream:unavailable:missing_asset_market_stream_provider",
    ]
    assert not any("factory_not_constructed" in reason for reason in payload["reasons"])
    assert "event_anchor_backfill" in payload["workers"]
    assert payload["workers"]["event_anchor_backfill"]["enabled"] is True
    assert set(payload["worker_lanes"]) >= {"ingest", "projection", "agent"}
    for lane in payload["worker_lanes"].values():
        assert set(lane) >= {
            "disabled_workers",
            "intentionally_not_started_workers",
            "unavailable_workers",
            "degraded_workers",
            "running_workers",
            "stopped_workers",
            "failed_workers",
        }
    assert payload["worker_lanes"]["ingest"]["intentionally_not_started_workers"] >= 1
    assert payload["worker_lanes"]["ingest"]["unavailable_workers"] >= 1
    assert payload["worker_lanes"]["projection"]["enabled_workers"] >= 1
    assert payload["worker_lanes"]["agent"]["failed_workers"] == 0
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "gmgn_db_pool_wait_ms" in metrics.text

    runtime = SimpleNamespace(
        scheduler=NoopScheduler(),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {"snapshot_gate_outcomes": {}}),
            upstream_client=None,
        ),
        db=FakeDB(),
        settings=SimpleNamespace(handles=("toly",)),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
    )
    monkeypatch.setattr(app_module, "postgres_health_check", lambda *_, **__: {"ok": True})

    calls = 0

    def backlog_workers_status_payload(_runtime):
        nonlocal calls
        calls += 1
        return {
            "workers": {
                "token_radar_projection": {
                    "queue_health": {
                        "status": "blocked",
                        "reason": "blocked_work_present",
                        "table_count": 1,
                        "unavailable_table_count": 0,
                        "queue_depth": 3,
                        "due_count": 2,
                        "running_count": 0,
                        "failed_count": 0,
                        "blocked_count": 1,
                        "terminal_count": 1,
                        "unresolved_terminal_count": 1,
                        "tables": {
                            "token_radar_dirty_targets": {
                                "available": True,
                                "error_code": None,
                                "queue_depth": 3,
                                "unresolved_terminal_count": 1,
                            }
                        },
                    }
                }
            },
            "worker_lanes": {"projection": {"queue_health": {"status": "blocked"}}},
        }

    monkeypatch.setattr(app_module, "workers_status_payload", backlog_workers_status_payload)
    readiness_payload, readiness_status = _readiness_payload(runtime)
    assert calls == 1
    assert readiness_status == 200
    assert readiness_payload["ok"] is True
    assert readiness_payload["reasons"] == []

    def contract_failure_workers_status_payload(_runtime):
        return {
            "workers": {
                "token_radar_projection": {
                    "queue_health": {
                        "status": "unavailable",
                        "reason": "queue_table_unavailable",
                        "table_count": 1,
                        "unavailable_table_count": 1,
                        "queue_depth": None,
                        "due_count": 0,
                        "running_count": 0,
                        "failed_count": 0,
                        "blocked_count": 0,
                        "terminal_count": 0,
                        "unresolved_terminal_count": 0,
                        "tables": {
                            "token_radar_dirty_targets": {
                                "available": False,
                                "error_code": "adapter_query_failure",
                            }
                        },
                    }
                }
            },
            "worker_lanes": {"projection": {"queue_health": {"status": "unavailable"}}},
        }

    monkeypatch.setattr(app_module, "workers_status_payload", contract_failure_workers_status_payload)
    readiness_payload, readiness_status = _readiness_payload(runtime)
    assert readiness_status == 503
    assert readiness_payload["ok"] is False
    assert "queue_health_adapter_query_failure" in readiness_payload["reasons"]


def test_runtime_aclose_closes_wired_providers_even_when_scheduler_stop_fails(monkeypatch, tmp_path):
    sync_provider = FakeClosableProvider()
    async_provider = FakeAsyncClosableProvider()
    providers = fake_wired_providers(make_settings(tmp_path), start_collector=False)
    providers = SimpleNamespace(
        **{
            **providers.__dict__,
            "asset_market": SimpleNamespace(
                cex_market=sync_provider,
                dex_quote_market=sync_provider,
                stream_dex_market=SimpleNamespace(inner=async_provider),
                discovery_chain_ids=(),
            ),
            "macrodata": SimpleNamespace(stock_quote_provider=sync_provider),
        }
    )
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: FakeDB())
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(bootstrap_module, "wire_providers", lambda *_, **__: providers)

    runtime = bootstrap(make_settings(tmp_path), start_collector=False)
    runtime.scheduler = FailingScheduler()

    try:
        close_runtime(runtime)
    except RuntimeError as exc:
        assert str(exc) == "scheduler failed"
    else:
        raise AssertionError("expected scheduler failure")

    assert sync_provider.closed == 1
    assert async_provider.closed == 1


def test_runtime_aclose_does_not_recurse_into_closable_provider_wrappers(monkeypatch, tmp_path):
    inner = FakeClosableProvider()
    wrapper = FakeProviderWrapper(inner)
    providers = fake_wired_providers(make_settings(tmp_path), start_collector=False)
    providers = SimpleNamespace(
        **{
            **providers.__dict__,
            "asset_market": SimpleNamespace(stream_dex_market=wrapper, discovery_chain_ids=()),
        }
    )
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: FakeDB())
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(bootstrap_module, "wire_providers", lambda *_, **__: providers)

    runtime = bootstrap(make_settings(tmp_path), start_collector=False)
    runtime.scheduler = NoopScheduler()

    close_runtime(runtime)

    assert wrapper.closed == 1
    assert inner.closed == 1


def test_runtime_aclose_groups_scheduler_and_provider_cleanup_failures(monkeypatch, tmp_path):
    providers = fake_wired_providers(make_settings(tmp_path), start_collector=False)
    providers = SimpleNamespace(
        **{
            **providers.__dict__,
            "asset_market": SimpleNamespace(stream_dex_market=FakeFailingProvider(), discovery_chain_ids=()),
        }
    )
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: FakeDB())
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(bootstrap_module, "wire_providers", lambda *_, **__: providers)

    runtime = bootstrap(make_settings(tmp_path), start_collector=False)
    runtime.scheduler = FailingScheduler()

    with pytest.raises(ExceptionGroup, match="runtime_close_failed") as excinfo:
        close_runtime(runtime)

    messages = {str(error) for error in excinfo.value.exceptions}
    assert messages == {"scheduler failed", "provider failed"}


def test_bootstrap_failure_after_provider_wiring_closes_providers(monkeypatch, tmp_path):
    sync_provider = FakeClosableProvider()
    async_provider = FakeAsyncClosableProvider()
    providers = SimpleNamespace(
        asset_market=SimpleNamespace(cex_market=sync_provider, nested={"async": async_provider}),
        macrodata=SimpleNamespace(stock_quote_provider=sync_provider),
    )
    db = FakeDB()
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: db)
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(bootstrap_module, "wire_providers", lambda *_, **__: providers)
    monkeypatch.setattr(
        bootstrap_module,
        "_assemble_runtime",
        lambda **_: (_ for _ in ()).throw(RuntimeError("assemble failed")),
    )

    try:
        bootstrap(make_settings(tmp_path), start_collector=False)
    except RuntimeError as exc:
        assert str(exc) == "assemble failed"
    else:
        raise AssertionError("expected assemble failure")

    assert sync_provider.closed == 1
    assert async_provider.closed == 1
    assert db.api_pool.closed is True
    assert db.worker_pool.closed is True
    assert db.tool_pool.closed is True
    assert db.wake_pool.closed is True


def test_runtime_postgres_health_check_reports_migration_version(tmp_path):
    runtime = bootstrap(make_settings(tmp_path), start_collector=False)

    try:
        with runtime.db.api_pool.connection() as conn:
            status = postgres_health_check(conn)
    finally:
        close_runtime(runtime)

    assert status["ok"] is True
    assert status["probe"] == "postgres_liveness"
    assert status["migration_version"] == latest_migration_version()


def test_runtime_uses_db_pool_bundle_sessions_without_pinned_connections(tmp_path):
    runtime = bootstrap(make_settings(tmp_path), start_collector=False)

    try:
        assert not hasattr(runtime, "api_db_pool")
        assert not hasattr(runtime, "worker_db_pool")
        assert not hasattr(runtime, "wake_db_pool")
        with runtime.repositories() as repos:
            status = postgres_health_check(repos.conn)
    finally:
        close_runtime(runtime)

    assert status["ok"] is True


def test_readiness_marks_database_probe_failure_unhealthy(tmp_path):
    runtime = bootstrap(make_settings(tmp_path), start_collector=False)
    runtime.db.api_pool.close()

    try:
        payload, status_code = _readiness_payload(runtime)
    finally:
        close_runtime(runtime)

    assert status_code == 503
    assert payload["ok"] is False
    assert payload["db"]["ok"] is False
    assert "database_unhealthy" in payload["reasons"]


def test_bootstrap_creates_pulse_worker_when_enabled_and_configured(monkeypatch, tmp_path):
    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        llm={
            "api_key": "test-key",
        },
        workers={
            "agent_runtime": {"lanes": {"pulse.decision": {"model": "gpt-pulse"}}},
            "pulse_candidate": {"batch_size": 7},
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(monkeypatch)

    runtime = bootstrap(settings, start_collector=False)

    try:
        pulse = runtime.workers["pulse_candidate"]
        assert pulse.status_payload()["enabled"] is True
        assert pulse.decision_client.model == "gpt-pulse"
        assert pulse.batch_size == settings.workers.pulse_candidate.batch_size
    finally:
        close_runtime(runtime)


def test_disabled_workers_are_present_but_not_started(monkeypatch, tmp_path):
    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        workers={
            "token_radar_projection": {"enabled": False},
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(monkeypatch)

    runtime = bootstrap(settings, start_collector=False)

    try:
        assert runtime.workers["token_radar_projection"].status_payload()["enabled"] is False
        asyncio.run(runtime.scheduler.start())
        assert "token_radar_projection" not in runtime.scheduler.tasks
    finally:
        close_runtime(runtime)


def test_disabled_collector_does_not_create_upstream_client(monkeypatch, tmp_path):
    created_upstream_clients = []

    def upstream_client_factory(on_frame):
        client = SimpleNamespace(on_frame=on_frame)
        created_upstream_clients.append(client)
        return client

    asset_market = SimpleNamespace(
        cex_market=object(),
        dex_discovery_market=None,
        dex_quote_market=None,
        dex_candle_market=None,
        dex_profile_sources=(),
        stream_dex_market=object(),
        discovery_chain_ids=(),
    )
    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        workers={
            "collector": {"enabled": False},
            "live_price_gateway": {"enabled": False},
            "token_radar_projection": {"enabled": False},
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(
        monkeypatch,
        asset_market=asset_market,
        upstream_client_factory=upstream_client_factory,
    )

    runtime = bootstrap(settings, start_collector=True)

    try:
        assert runtime.start_collector is False
        assert runtime.collector.upstream_client is None
        assert created_upstream_clients == []
        assert runtime.workers["collector"].status_payload()["enabled"] is False
        assert runtime.workers["live_price_gateway"].status_payload()["enabled"] is False
        assert runtime.providers.asset_market.stream_dex_market is asset_market.stream_dex_market
    finally:
        close_runtime(runtime)


def test_start_collector_false_only_disables_collector(monkeypatch, tmp_path):
    asset_market = SimpleNamespace(
        cex_market=object(),
        dex_discovery_market=object(),
        dex_quote_market=object(),
        dex_candle_market=None,
        dex_profile_sources=(SimpleNamespace(provider="gmgn_dex_profile", market=object()),),
        stream_dex_market=object(),
        discovery_chain_ids=("solana",),
    )
    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        workers={
            "market_tick_stream": {"enabled": True},
            "market_tick_poll": {"enabled": True},
            "token_capture_tier": {"enabled": True},
            "asset_profile_refresh": {"enabled": True},
            "resolution_refresh": {"enabled": True},
            "live_price_gateway": {"enabled": True},
            "token_radar_projection": {"enabled": False},
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(monkeypatch, asset_market=asset_market)

    runtime = bootstrap(settings, start_collector=False)

    try:
        assert runtime.workers["collector"].status_payload()["enabled"] is False
        for name in (
            "market_tick_stream",
            "market_tick_poll",
            "token_capture_tier",
            "asset_profile_refresh",
            "resolution_refresh",
            "live_price_gateway",
        ):
            assert runtime.workers[name].status_payload()["enabled"] is True
    finally:
        close_runtime(runtime)


def test_notification_delivery_starts_when_rule_worker_disabled(monkeypatch, tmp_path):
    settings = Settings(
        ws_token="secret",
        storage={"postgres": {"dsn": "postgresql://fake/db", "password_file": None}},
        notifications={
            "enabled": True,
            "channels": {
                "audit_log": {
                    "enabled": True,
                    "provider": "log",
                    "min_severity": "info",
                }
            },
        },
        workers={"notification_rule": {"enabled": False}, "notification_delivery": {"enabled": True}},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(monkeypatch)

    runtime = bootstrap(settings, start_collector=False)

    try:
        assert runtime.workers["notification_rule"].status_payload()["enabled"] is False
        assert runtime.workers["notification_delivery"].status_payload()["enabled"] is True
    finally:
        close_runtime(runtime)


def test_readiness_uses_scheduler_workers_payload(monkeypatch):
    agent_execution = {
        "global_max_concurrency": 4,
        "global_in_flight": 0,
        "lanes": {
            "pulse.decision_maker": {
                "max_concurrency": 1,
                "in_flight": 0,
                "circuit_state": "closed",
                "capacity_denied_total": 0,
                "circuit_open_total": 0,
                "timeout_total": 0,
            }
        },
    }
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0})),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=SimpleNamespace(status_snapshot=lambda: agent_execution),
        scheduler=SimpleNamespace(
            status_payload=lambda: {
                "pulse_candidate": {
                    "enabled": True,
                    "running": True,
                    "last_started_at_ms": 1_000,
                    "last_finished_at_ms": 2_000,
                    "last_result": {"processed": 1},
                    "last_error": None,
                    "iteration_duration_p99_ms": None,
                    "queue_depth": None,
                    "pool_wait_ms_p99": None,
                }
            },
            unhealthy_reasons=lambda: [],
        ),
    )
    worker_status = {
        "workers": runtime.scheduler.status_payload(),
        "worker_lanes": {},
    }
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})
    monkeypatch.setattr(app_module, "workers_status_payload", lambda _: worker_status)

    payload, status_code = _readiness_payload(runtime, now_ms=12_001)

    assert status_code == 200
    assert payload["workers"]["pulse_candidate"]["running"] is True
    assert payload["workers"]["pulse_candidate"]["last_result"] == {"processed": 1}
    assert payload["agent_execution"] == agent_execution
    assert "pulse_agent" not in payload


def test_readiness_worker_lanes_count_each_effective_status(monkeypatch):
    projection_statuses = {
        "market_tick_current_projection": {"enabled": False, "running": False, "effective_status": "disabled"},
        "token_capture_tier": {
            "enabled": False,
            "running": False,
            "effective_status": "intentionally_not_started",
        },
        "token_profile_current": {
            "enabled": True,
            "running": False,
            "effective_status": "unavailable",
            "unavailable_reason": "missing_profile_source",
        },
        "token_radar_projection": {"enabled": True, "running": True, "effective_status": "degraded"},
        "narrative_admission": {"enabled": True, "running": True, "effective_status": "running"},
        "news_page_projection": {"enabled": True, "running": False, "effective_status": "stopped"},
        "news_source_quality_projection": {
            "enabled": True,
            "running": False,
            "effective_status": "failed",
            "last_error": "projection failed",
        },
        "cex_oi_radar_board": {"enabled": True, "running": False, "effective_status": "stopped"},
        "macro_view_projection": {"enabled": False, "running": False, "effective_status": "disabled"},
        "macro_daily_brief_projection": {"enabled": False, "running": False, "effective_status": "disabled"},
    }
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0})),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
        scheduler=SimpleNamespace(
            status_payload=lambda: projection_statuses,
            unhealthy_reasons=lambda: [],
        ),
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})
    monkeypatch.setattr(app_module, "_news_provider_contract_payload", lambda _: {"ok": True})

    payload, _status_code = _readiness_payload(runtime, now_ms=12_001)

    projection = payload["worker_lanes"]["projection"]
    assert projection["disabled_workers"] == 3
    assert projection["intentionally_not_started_workers"] == 1
    assert projection["unavailable_workers"] == 1
    assert projection["degraded_workers"] == 1
    assert projection["running_workers"] == 1
    assert projection["stopped_workers"] == 2
    assert projection["failed_workers"] == 1


def test_readiness_reports_result_derived_failed_worker(monkeypatch):
    failed_worker = SimpleNamespace(
        status_payload=lambda: {
            "enabled": True,
            "running": False,
            "last_result": {"ok": False},
            "last_error": None,
        }
    )
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0})),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
        scheduler=bootstrap_module.WorkerScheduler(
            workers={"token_radar_projection": failed_worker},
            db=FakeDB(),
        ),
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})
    monkeypatch.setattr(app_module, "_news_provider_contract_payload", lambda _: {"ok": True})

    payload, status_code = _readiness_payload(runtime, now_ms=12_001)

    assert status_code == 503
    assert payload["ok"] is False
    assert payload["workers"]["token_radar_projection"]["effective_status"] == "failed"
    assert "worker:token_radar_projection:failed" in payload["reasons"]


def test_readiness_reports_okx_circuit_open_without_failing_app(monkeypatch):
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0})),
        providers=SimpleNamespace(
            asset_market=SimpleNamespace(
                stream_dex_market=SimpleNamespace(
                    connection_state_payload=lambda: {
                        "provider": "okx_dex_ws",
                        "state": "circuit_open",
                        "last_state_change_at_ms": 12_000,
                        "last_error_category": "connect_timeout",
                    }
                )
            )
        ),
        agent_execution_gateway=None,
        scheduler=SimpleNamespace(
            status_payload=lambda: {},
            unhealthy_reasons=lambda: [],
        ),
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})
    monkeypatch.setattr(app_module, "workers_status_payload", lambda _: {"workers": {}, "worker_lanes": {}})

    payload, status_code = _readiness_payload(runtime, now_ms=12_001)

    assert status_code == 200
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["provider_states"]["okx_dex_ws"]["state"] == "circuit_open"
    assert payload["provider_states"]["okx_dex_ws"]["last_error_category"] == "connect_timeout"
