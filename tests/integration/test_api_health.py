import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import parallax.app.runtime.bootstrap as bootstrap_module
import parallax.app.surfaces.api.app as app_module
from parallax.app.runtime.bootstrap import Runtime, bootstrap
from parallax.app.runtime.runtime_snapshot import RuntimeSnapshot, capture_runtime_snapshot
from parallax.app.runtime.worker_manifest import worker_names
from parallax.app.surfaces.api.app import _readiness_payload, _status_payload, create_app
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


def attach_runtime_snapshot(runtime: SimpleNamespace) -> SimpleNamespace:
    runtime.snapshot = RuntimeSnapshot.startup(
        startup_db_status={"ok": True, "probe": "startup"},
        composition={"ok": True},
        news_provider_contract=getattr(runtime, "news_provider_contract", {"ok": True}),
    )

    def current_snapshot() -> RuntimeSnapshot:
        runtime.snapshot = capture_runtime_snapshot(runtime)
        return runtime.snapshot

    runtime.current_snapshot = current_snapshot
    return runtime


def full_worker_statuses(**overrides: dict[str, object]) -> dict[str, dict[str, object]]:
    statuses = {
        name: {
            "enabled": False,
            "running": False,
            "effective_status": "disabled",
            "unavailable_reason": None,
            "last_started_at_ms": None,
            "last_finished_at_ms": None,
            "last_result": None,
            "last_error": None,
            "iteration_duration_p99_ms": None,
        }
        for name in worker_names()
    }
    for name, values in overrides.items():
        statuses[name].update(values)
    return statuses


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
                    "source_terminal_count": 0,
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
        self.notification_delivery_running_timeout_ms = 120_000
        self.notification_delivery_stale_running_terminalization_batch_size = 100

    @contextmanager
    def api_session(self):
        yield SimpleNamespace()

    @contextmanager
    def worker_session(self, _name):
        yield SimpleNamespace()

    async def aclose(self) -> None:
        for pool in (self.api_pool, self.worker_pool):
            pool.close()


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


class FakeWiredProviders(SimpleNamespace):
    def __init__(self, **kwargs) -> None:
        kwargs["asset_market"] = _complete_fake_asset_market(kwargs.get("asset_market"))
        super().__init__(**kwargs)

    async def aclose(self) -> None:
        errors: list[Exception] = []
        seen: set[int] = set()
        for value in self.__dict__.values():
            await _close_fake_provider_tree(value, errors=errors, seen=seen)
        if errors:
            raise ExceptionGroup("fake_wired_provider_cleanup_failed", errors)


def _complete_fake_asset_market(asset_market=None) -> SimpleNamespace:
    values = dict(getattr(asset_market, "__dict__", {})) if asset_market is not None else {}
    values.setdefault("cex_market", None)
    values.setdefault("dex_discovery_market", None)
    values.setdefault("dex_quote_market", None)
    values.setdefault("dex_candle_market", None)
    values.setdefault("dex_profile_sources", ())
    values.setdefault("stream_dex_market", None)
    values.setdefault("discovery_chain_ids", ())
    values.setdefault("provider_health", ())
    return SimpleNamespace(**values)


def _leaf_exception_messages(exc: BaseException) -> set[str]:
    if isinstance(exc, ExceptionGroup):
        messages: set[str] = set()
        for inner in exc.exceptions:
            messages.update(_leaf_exception_messages(inner))
        return messages
    return {str(exc)}


async def _close_fake_provider_tree(value, *, errors: list[Exception], seen: set[int]) -> None:
    if value is None or isinstance(value, str | bytes | int | float | bool):
        return
    object_id = id(value)
    if object_id in seen:
        return
    seen.add(object_id)
    close = getattr(value, "close", None)
    if callable(close):
        try:
            close()
        except Exception as exc:
            errors.append(exc)
        return
    aclose = getattr(value, "aclose", None)
    if callable(aclose):
        try:
            await aclose()
        except Exception as exc:
            errors.append(exc)
        return
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list | tuple | set | frozenset):
        children = value
    else:
        children = getattr(value, "__dict__", {}).values()
    for child in children:
        await _close_fake_provider_tree(child, errors=errors, seen=seen)


class FailingScheduler:
    def status_payload(self):
        return {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        raise RuntimeError("scheduler failed")


class NoopScheduler:
    def status_payload(self):
        return {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def fake_wired_providers(
    settings,
    *,
    start_collector,
    asset_market=None,
    news_intel=None,
    upstream_client_factory=None,
):
    return FakeWiredProviders(
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
        news_intel=news_intel or SimpleNamespace(feed_client=None, story_brief_provider=None),
    )


def patch_runtime_dependencies(monkeypatch, *, asset_market=None, news_intel=None, upstream_client_factory=None):
    monkeypatch.setattr(bootstrap_module.DBPoolBundle, "create", lambda *_, **__: FakeDB())
    monkeypatch.setattr(bootstrap_module, "postgres_health_check", lambda *_, **__: {"ok": True})
    monkeypatch.setattr(
        bootstrap_module,
        "wire_providers",
        lambda settings, *, start_collector, agent_execution_gateway=None: fake_wired_providers(
            settings,
            start_collector=start_collector,
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


def test_lifespan_closes_runtime_when_scheduler_start_fails(monkeypatch):
    events: list[str] = []

    class FailingScheduler:
        async def start(self) -> None:
            events.append("start")
            raise RuntimeError("worker start failed")

    class FailingRuntime:
        scheduler = FailingScheduler()

        async def aclose(self) -> None:
            events.append("close")

    monkeypatch.setattr(app_module, "bootstrap", lambda *_args, **_kwargs: FailingRuntime())
    app = create_app(settings=Settings(ws_token="secret"), start_collector=False)

    with pytest.raises(RuntimeError, match="worker start failed"), TestClient(app):
        pass

    assert events == ["start", "close"]


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
    patch_runtime_dependencies(
        monkeypatch,
        news_intel=SimpleNamespace(feed_client=FakeClosableProvider(), story_brief_provider=None),
    )
    monkeypatch.setattr(
        app_module,
        "postgres_liveness_check",
        lambda *_, **__: {"ok": True, "probe": "postgres_liveness"},
    )
    settings = make_settings(tmp_path)
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
    assert ready.status_code == 200
    assert api_status.status_code == 200
    assert payload["store"] == "postgresql"
    assert payload["db"]["ok"] is True
    assert payload["db"]["probe"] == "postgres_liveness"
    assert payload["composition"] == {"ok": True}
    assert "workers" not in payload
    assert "worker_lanes" not in payload
    legacy_worker_sections = {
        "collector",
        "enrichment",
        "notifications",
        "token_radar_projection",
        "watchlist_handle_summary",
        "market_tick_stream",
        "market_tick_poll",
        "asset_profile_refresh",
        "resolution_refresh",
        "token_resolution",
        "provider_status",
    }
    assert not (legacy_worker_sections & set(api_status_payload))
    assert set(api_status_payload["workers"]) >= {
        "collector",
        "token_radar_projection",
        "event_anchor_backfill",
    }
    assert api_status_payload["workers"]["collector"]["enabled"] is False
    assert api_status_payload["workers"]["collector"]["effective_status"] == "intentionally_not_started"
    assert api_status_payload["workers"]["collector"]["unavailable_reason"] is None
    assert api_status_payload["workers"]["collector"]["last_result"] is None
    assert api_status_payload["workers"]["market_tick_stream"]["effective_status"] == "unavailable"
    assert (
        api_status_payload["workers"]["market_tick_stream"]["unavailable_reason"]
        == "missing_asset_market_stream_provider"
    )
    assert api_status_payload["workers"]["market_tick_poll"]["effective_status"] == "unavailable"
    assert (
        api_status_payload["workers"]["market_tick_poll"]["unavailable_reason"] == "missing_asset_market_quote_provider"
    )
    assert "worker:market_tick_stream:unavailable:missing_asset_market_stream_provider" in api_status_payload["reasons"]
    assert "worker:market_tick_poll:unavailable:missing_asset_market_quote_provider" in api_status_payload["reasons"]
    worker_unavailable_reasons = sorted(reason for reason in api_status_payload["reasons"] if ":unavailable:" in reason)
    assert worker_unavailable_reasons == [
        "worker:asset_profile_refresh:unavailable:missing_asset_profile_provider",
        "worker:market_tick_poll:unavailable:missing_asset_market_quote_provider",
        "worker:market_tick_stream:unavailable:missing_asset_market_stream_provider",
        "worker:news_story_brief:unavailable:missing_llm_configuration",
        "worker:notification_delivery:unavailable:missing_notification_delivery_channel",
        "worker:resolution_refresh:unavailable:missing_asset_discovery_provider",
    ]
    assert not any("factory_not_constructed" in reason for reason in api_status_payload["reasons"])
    assert "event_anchor_backfill" in api_status_payload["workers"]
    assert api_status_payload["workers"]["event_anchor_backfill"]["enabled"] is True
    assert "worker_lanes" not in api_status_payload
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "gmgn_db_pool_wait_ms" in metrics.text


def test_runtime_aclose_closes_wired_providers_even_when_scheduler_stop_fails(monkeypatch, tmp_path):
    sync_provider = FakeClosableProvider()
    async_provider = FakeAsyncClosableProvider()
    providers = fake_wired_providers(make_settings(tmp_path), start_collector=False)
    providers = FakeWiredProviders(
        **{
            **providers.__dict__,
            "asset_market": SimpleNamespace(
                cex_market=sync_provider,
                dex_quote_market=sync_provider,
                stream_dex_market=SimpleNamespace(inner=async_provider),
                discovery_chain_ids=(),
            ),
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
    providers = FakeWiredProviders(
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
    providers = FakeWiredProviders(
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

    messages = _leaf_exception_messages(excinfo.value)
    assert messages == {"scheduler failed", "provider failed"}


def test_bootstrap_failure_after_provider_wiring_closes_providers(monkeypatch, tmp_path):
    sync_provider = FakeClosableProvider()
    async_provider = FakeAsyncClosableProvider()
    providers = FakeWiredProviders(
        asset_market=SimpleNamespace(cex_market=sync_provider, nested={"async": async_provider}),
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


def test_readiness_does_not_query_worker_provider_or_business_freshness(monkeypatch):
    class ForbiddenDependency:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"readiness queried non-core dependency: {name}")

    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", notifications={"enabled": False}),
        db=FakeDB(),
        snapshot=RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={"ok": True},
        ),
        scheduler=ForbiddenDependency(),
        collector=ForbiddenDependency(),
        providers=ForbiddenDependency(),
        agent_execution_gateway=ForbiddenDependency(),
        repositories=lambda: None,
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _: {"ok": True, "probe": "fake"})

    payload, status_code = _readiness_payload(runtime)

    assert status_code == 200
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["db"] == {"ok": True, "probe": "fake"}


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
        assert runtime.scheduler.workers["token_radar_projection"].status_payload()["enabled"] is False
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
        assert runtime.collector.upstream_client is None
        assert created_upstream_clients == []
        assert runtime.scheduler.workers["collector"].status_payload()["enabled"] is False
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
            "asset_profile_refresh": {"enabled": True},
            "resolution_refresh": {"enabled": True},
            "token_radar_projection": {"enabled": False},
        },
        notifications={"enabled": False},
    )
    settings.set_config_dir(tmp_path / "app-home")
    patch_runtime_dependencies(monkeypatch, asset_market=asset_market)

    runtime = bootstrap(settings, start_collector=False)

    try:
        assert runtime.scheduler.workers["collector"].status_payload()["enabled"] is False
        for name in (
            "market_tick_stream",
            "market_tick_poll",
            "asset_profile_refresh",
            "resolution_refresh",
        ):
            assert runtime.scheduler.workers[name].status_payload()["enabled"] is True
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
        assert runtime.scheduler.workers["notification_rule"].status_payload()["enabled"] is False
        assert runtime.scheduler.workers["notification_delivery"].status_payload()["enabled"] is True
    finally:
        close_runtime(runtime)


def test_status_uses_runtime_snapshot_worker_and_agent_state():
    agent_execution = {
        "lane": "news.story_brief",
        "model": "gpt-news",
        "provider_family": "openai",
        "output_strategy": "json_object",
        "schema_enforcement": "client_validate",
        "max_concurrency": 1,
        "rpm_limit": 60,
        "timeout_seconds": 180.0,
        "in_flight": 0,
        "provider_running": 0,
        "circuit_state": "closed",
        "circuit_open_until_ms": None,
        "capacity_denied_total": 0,
        "circuit_open_total": 0,
        "timeout_total": 0,
        "last_denied_at_ms": None,
        "last_timeout_at_ms": None,
        "oldest_in_flight_age_ms": None,
    }
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0}), upstream_client=None),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=SimpleNamespace(status_snapshot=lambda: agent_execution),
        news_provider_contract={"ok": True},
        scheduler=SimpleNamespace(
            tasks={},
            status_payload=lambda: full_worker_statuses(
                news_story_brief={
                    "enabled": True,
                    "running": True,
                    "effective_status": "running",
                    "last_started_at_ms": 1_000,
                    "last_finished_at_ms": 2_000,
                    "last_result": {"processed": 1},
                    "last_error": None,
                    "iteration_duration_p99_ms": None,
                },
            ),
        ),
    )
    attach_runtime_snapshot(runtime)

    payload = _status_payload(runtime)

    assert payload["workers"]["news_story_brief"]["running"] is True
    assert payload["workers"]["news_story_brief"]["last_result"] == {"processed": 1}
    assert payload["agent_execution"] == agent_execution


def test_status_reports_formal_failed_worker():
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0}), upstream_client=None),
        db=FakeDB(),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
        scheduler=SimpleNamespace(
            tasks={},
            status_payload=lambda: full_worker_statuses(
                token_radar_projection={
                    "enabled": True,
                    "effective_status": "failed",
                    "last_result": {"ok": False},
                },
            ),
        ),
    )
    attach_runtime_snapshot(runtime)

    payload = _status_payload(runtime)

    assert payload["ok"] is False
    assert payload["workers"]["token_radar_projection"]["effective_status"] == "failed"
    assert "worker:token_radar_projection:failed" in payload["reasons"]


def test_status_reports_terminal_news_source_as_degraded() -> None:
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0}), upstream_client=None),
        db=FakeDB(),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
        scheduler=SimpleNamespace(
            tasks={},
            status_payload=lambda: full_worker_statuses(
                news_fetch={
                    "enabled": True,
                    "effective_status": "degraded",
                    "last_result": {
                        "processed": 0,
                        "failed": 0,
                        "notes": {
                            "degraded": True,
                            "terminal_sources": {"source-402": "provider_payment_required"},
                        },
                    },
                },
            ),
        ),
    )
    attach_runtime_snapshot(runtime)

    payload = _status_payload(runtime)

    assert payload["ok"] is False
    assert payload["workers"]["news_fetch"]["effective_status"] == "degraded"
    assert payload["reasons"] == ["worker:news_fetch:degraded"]


def test_status_reports_okx_circuit_open_as_degraded_without_failing_readiness():
    runtime = SimpleNamespace(
        settings=Settings(ws_token="secret", handles=("toly",), notifications={"enabled": False}),
        collector=SimpleNamespace(status=SimpleNamespace(to_dict=lambda: {"frames_received": 0}), upstream_client=None),
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
        news_provider_contract={"ok": True},
        scheduler=SimpleNamespace(
            tasks={},
            status_payload=full_worker_statuses,
        ),
    )
    attach_runtime_snapshot(runtime)

    payload = _status_payload(runtime)

    assert payload["ok"] is False
    assert payload["reasons"] == ["provider:okx_dex_ws:circuit_open"]
    assert payload["provider_states"]["okx_dex_ws"]["state"] == "circuit_open"
    assert payload["provider_states"]["okx_dex_ws"]["last_error_category"] == "connect_timeout"
