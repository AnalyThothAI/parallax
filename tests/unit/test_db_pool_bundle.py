from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime import db_pool_bundle
from parallax.app.runtime.db_pool_bundle import (
    DBPoolBundle,
    enabled_wake_listener_concurrency,
    wake_pool_max_size,
)
from parallax.app.runtime.wake_bus import WakeBus
from parallax.app.runtime.wake_waiter import WakeWaiter
from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.platform.config.settings import WorkersSettings


class FakeConn:
    def __init__(
        self,
        *,
        advisory_lock: bool = True,
        fail_on: str | None = None,
        fail_after: int = 0,
    ) -> None:
        self.advisory_lock = advisory_lock
        self.fail_on = fail_on
        self.fail_after = fail_after
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.closed = False
        self.commits = 0

    def execute(self, sql: str, params: tuple[Any, ...] | None = None):
        self.executed.append((sql, params))
        haystack = f"{sql} {params or ''}"
        if self.fail_on and self.fail_on in haystack and len(self.executed) > self.fail_after:
            raise RuntimeError(f"failed:{self.fail_on}")
        return self

    def fetchone(self):
        return {"locked": self.advisory_lock}

    def commit(self) -> None:
        self.commits += 1

    def notifies(self, *, timeout: float, stop_after: int):
        yield from ()

    def close(self) -> None:
        self.closed = True


class FakeNoCommitConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None):
        self.executed.append((sql, params))
        return self


class FakeConnectionContext:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConn:
        self.entered = True
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True


class FakePool:
    def __init__(self, conn: FakeConn | None = None) -> None:
        self.conn = conn or FakeConn()
        self.contexts: list[FakeConnectionContext] = []
        self.put_back: list[FakeConn] = []
        self.closed: list[FakeConn] = []
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def connection(self) -> FakeConnectionContext:
        context = FakeConnectionContext(self.conn)
        self.contexts.append(context)
        return context

    def getconn(self) -> FakeConn:
        return self.conn

    def putconn(self, conn: FakeConn) -> None:
        self.put_back.append(conn)

    def close_returns(self, conn: FakeConn) -> None:
        self.closed.append(conn)
        conn.close()


class MissingClosePool:
    pass


class FailingClosePool:
    def close(self) -> None:
        raise RuntimeError("close failed")


class AwaitableCloseResult:
    def __init__(self) -> None:
        self.awaited = False

    def __await__(self) -> Any:
        self.awaited = True
        return iter(())


class AwaitableClosePool(FakePool):
    def __init__(self) -> None:
        super().__init__()
        self.close_result = AwaitableCloseResult()

    def close(self) -> AwaitableCloseResult:
        self.close_calls += 1
        return self.close_result


class FakeTelemetry:
    def __init__(self) -> None:
        self.pool_waits: list[tuple[str, float]] = []

    def record_pool_wait(self, pool: str, wait_ms: float) -> None:
        self.pool_waits.append((pool, wait_ms))


def _db_bundle(**kwargs: Any) -> DBPoolBundle:
    return DBPoolBundle(
        pulse_job_running_timeout_ms=300_000,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
        **kwargs,
    )


def _fake_wake_sizing_workers(**overrides: Any) -> SimpleNamespace:
    worker_settings = {
        manifest.name: SimpleNamespace(enabled=False, wakes_on=manifest.wakes_on, concurrency=1)
        for manifest in all_worker_manifests()
        if manifest.wakes_on
    }
    pulse_candidate = worker_settings.get("pulse_candidate")
    if pulse_candidate is None:
        pulse_candidate = SimpleNamespace(enabled=False, wakes_on=("token_radar_updated",), concurrency=1)
        worker_settings["pulse_candidate"] = pulse_candidate
    pulse_candidate.job_running_timeout_ms = 300_000
    notification_delivery = worker_settings.get("notification_delivery")
    if notification_delivery is None:
        notification_delivery = SimpleNamespace(enabled=False, wakes_on=(), concurrency=1)
        worker_settings["notification_delivery"] = notification_delivery
    notification_delivery.running_timeout_ms = 300_000
    notification_delivery.stale_running_terminalization_batch_size = 100
    worker_settings.update(overrides)
    return SimpleNamespace(**worker_settings)


@dataclass
class FakeSettings:
    postgres_dsn: str = "postgresql://parallax_app@postgres:5432/parallax"
    postgres_password_file: object | None = None
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 10
    postgres_connect_timeout_seconds: float = 5.0
    workers: object = field(default_factory=_fake_wake_sizing_workers)


def test_create_builds_distinct_pool_roles(monkeypatch) -> None:
    created: list[dict[str, Any]] = []

    def fake_create_pool(dsn: str, **kwargs: Any) -> FakePool:
        created.append({"dsn": dsn, **kwargs})
        return FakePool()

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)

    bundle = DBPoolBundle.create(FakeSettings())

    assert isinstance(bundle.api_pool, FakePool)
    assert isinstance(bundle.lock_pool, FakePool)
    assert bundle.pulse_job_running_timeout_ms == 300_000
    assert bundle.notification_delivery_running_timeout_ms == 300_000
    assert bundle.notification_delivery_stale_running_terminalization_batch_size == 100
    assert bundle.wake_pool_max_size == 3
    assert bundle.enabled_wake_listener_concurrency == 0
    assert [item["application_name"] for item in created] == [
        "gmgn_api",
        "gmgn_worker",
        "gmgn_worker_lock",
        "gmgn_agent_tools",
        "gmgn_wake",
    ]
    assert created[0]["statement_timeout_seconds"] == 5.0
    assert created[1]["statement_timeout_seconds"] == 30.0
    assert created[1]["idle_in_transaction_session_timeout_seconds"] == 60.0
    assert created[2]["min_size"] == 0
    assert created[2]["max_size"] == 10
    assert created[2]["statement_timeout_seconds"] == 5.0
    assert created[3]["statement_timeout_seconds"] == 5.0
    assert created[3]["read_only"] is True
    assert created[3]["max_size"] == 3
    assert created[4]["statement_timeout_seconds"] is None
    assert created[4]["keepalives"] is True
    assert created[4]["keepalives_idle"] > 0
    assert created[4]["keepalives_interval"] > 0
    assert created[4]["keepalives_count"] > 0
    assert created[4]["max_size"] == 3


def test_create_sizes_wake_pool_for_configured_wake_listeners(monkeypatch) -> None:
    created: list[dict[str, Any]] = []

    def fake_create_pool(dsn: str, **kwargs: Any) -> FakePool:
        created.append({"dsn": dsn, **kwargs})
        return FakePool()

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)
    settings = FakeSettings(
        workers=_fake_wake_sizing_workers(
            market_tick_current_projection=SimpleNamespace(
                enabled=True,
                wakes_on=("market_tick_written",),
                concurrency=1,
            ),
            token_radar_projection=SimpleNamespace(
                enabled=True,
                wakes_on=("market_tick_current_updated",),
                concurrency=1,
            ),
            news_page_projection=SimpleNamespace(
                enabled=True,
                wakes_on=("news_item_written",),
                concurrency=2,
            ),
            narrative_admission=SimpleNamespace(
                enabled=False,
                wakes_on=("ignored",),
                concurrency=1,
            ),
        )
    )

    bundle = DBPoolBundle.create(settings)

    assert enabled_wake_listener_concurrency(settings) == 4
    assert wake_pool_max_size(settings) >= 4 + 2
    assert bundle.enabled_wake_listener_concurrency == 4
    assert bundle.wake_pool_max_size == 6
    assert created[4]["application_name"] == "gmgn_wake"
    assert created[4]["max_size"] == 6


def test_enabled_wake_listener_concurrency_requires_workers_settings_contract() -> None:
    with pytest.raises(AttributeError, match="workers"):
        enabled_wake_listener_concurrency(SimpleNamespace())


def test_enabled_wake_listener_concurrency_requires_manifest_worker_settings_contract() -> None:
    settings = SimpleNamespace(workers=SimpleNamespace())

    with pytest.raises(AttributeError, match="market_tick_current_projection"):
        enabled_wake_listener_concurrency(settings)


def test_enabled_wake_listener_concurrency_rejects_malformed_concurrency_before_sizing() -> None:
    settings = SimpleNamespace(
        workers=SimpleNamespace(
            market_tick_current_projection=SimpleNamespace(
                enabled=True,
                wakes_on=("market_tick_written",),
                concurrency=0,
            )
        )
    )

    with pytest.raises(ValueError, match="worker_wake_listener_concurrency_required:market_tick_current_projection"):
        enabled_wake_listener_concurrency(settings)


def test_create_failure_records_missing_close_contract_for_partial_pool(monkeypatch) -> None:
    created = 0

    def fake_create_pool(dsn: str, **kwargs: Any) -> object:
        nonlocal created
        created += 1
        if created == 1:
            return MissingClosePool()
        raise RuntimeError("worker pool failed")

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)

    with pytest.raises(RuntimeError, match="worker pool failed") as excinfo:
        DBPoolBundle.create(FakeSettings())

    notes = "\n".join(getattr(excinfo.value, "__notes__", ()))
    assert "partial db pool cleanup failed" in notes
    assert "AttributeError" in notes
    assert "close" in notes


def test_create_failure_preserves_original_error_when_partial_pool_close_fails(monkeypatch) -> None:
    created = 0

    def fake_create_pool(dsn: str, **kwargs: Any) -> object:
        nonlocal created
        created += 1
        if created == 1:
            return FailingClosePool()
        raise RuntimeError("worker pool failed")

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)

    with pytest.raises(RuntimeError, match="worker pool failed") as excinfo:
        DBPoolBundle.create(FakeSettings())

    notes = "\n".join(getattr(excinfo.value, "__notes__", ()))
    assert "partial db pool cleanup failed: RuntimeError: close failed" in notes


def test_wake_pool_size_covers_enabled_listener_concurrency_for_default_workers() -> None:
    settings = SimpleNamespace(workers=WorkersSettings())

    wake_concurrency = enabled_wake_listener_concurrency(settings)

    assert wake_concurrency > 0
    assert wake_pool_max_size(settings) >= wake_concurrency + 2


def test_api_session_yields_repositories_and_records_pool_wait(monkeypatch) -> None:
    conn = FakeConn()
    telemetry = FakeTelemetry()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout, **_kwargs: {"conn": checkout})
    bundle = _db_bundle(api_pool=FakePool(conn), worker_pool=FakePool(), wake_pool=FakePool(), telemetry=telemetry)

    with bundle.api_session() as repos:
        assert repos == {"conn": conn}

    assert telemetry.pool_waits[0][0] == "api"
    assert telemetry.pool_waits[0][1] >= 0


def test_worker_session_sets_and_restores_application_name(monkeypatch) -> None:
    conn = FakeConn()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout, **_kwargs: checkout)
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=FakePool(conn), wake_pool=FakePool())

    with bundle.worker_session("pulse_candidate", statement_timeout_seconds=12) as repos:
        assert repos is conn

    assert conn.executed == [
        ("SELECT set_config(%s, %s, false)", ("application_name", "worker:pulse_candidate")),
        ("SELECT set_config(%s, %s, false)", ("statement_timeout", "12000ms")),
        ("SELECT set_config(%s, %s, false)", ("statement_timeout", "30000ms")),
        ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker")),
    ]


@pytest.mark.parametrize("statement_timeout_seconds", [-1, True, "12"])
def test_worker_session_rejects_malformed_statement_timeout_without_runtime_repair(
    statement_timeout_seconds: Any,
    monkeypatch,
) -> None:
    conn = FakeConn()
    pool = FakePool(conn)
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout, **_kwargs: checkout)
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    with (
        pytest.raises(ValueError, match="db_statement_timeout_seconds_required"),
        bundle.worker_session("pulse_candidate", statement_timeout_seconds=statement_timeout_seconds),
    ):
        pass

    assert conn.executed == [
        ("SELECT set_config(%s, %s, false)", ("application_name", "worker:pulse_candidate")),
    ]
    assert conn.closed is True
    assert pool.put_back == [conn]


def test_worker_session_preserves_body_error_and_discards_when_reset_fails(monkeypatch) -> None:
    conn = FakeConn(fail_on="statement_timeout", fail_after=2)
    pool = FakePool(conn)
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout, **_kwargs: checkout)
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    with (
        pytest.raises(RuntimeError, match="body failed"),
        bundle.worker_session(
            "pulse_candidate",
            statement_timeout_seconds=12,
        ),
    ):
        raise RuntimeError("body failed")

    assert conn.closed is True
    assert pool.closed == []
    assert pool.put_back == [conn]


def test_discard_connection_uses_connection_close_then_pool_putconn_without_pool_close_returns() -> None:
    class PoolWithForbiddenCloseReturns(FakePool):
        def close_returns(self, conn: FakeConn) -> None:
            raise AssertionError("pool close_returns fallback must not be used")

    conn = FakeConn()
    pool = PoolWithForbiddenCloseReturns(conn)

    db_pool_bundle._discard_connection(pool, conn)

    assert conn.closed is True
    assert pool.closed == []
    assert pool.put_back == [conn]


def test_acquire_advisory_lock_connection_returns_held_connection_until_release() -> None:
    pool = FakePool(FakeConn(advisory_lock=True))
    telemetry = FakeTelemetry()
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool(), telemetry=telemetry)

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    assert locked.execute("SELECT 1") is pool.conn
    assert pool.conn.executed[:2] == [
        ("SELECT set_config(%s, %s, false)", ("application_name", "worker:token_radar_projection")),
        ("SELECT pg_try_advisory_lock(%s) AS locked", (2026051501,)),
    ]
    locked.release()
    assert pool.put_back == [pool.conn]
    assert pool.conn.executed[-2:] == [
        ("SELECT pg_advisory_unlock(%s)", (2026051501,)),
        ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker")),
    ]
    assert telemetry.pool_waits[0][0] == "worker"


def test_acquire_advisory_lock_connection_uses_lock_pool_when_present() -> None:
    worker_pool = FakePool(FakeConn(advisory_lock=True))
    lock_pool = FakePool(FakeConn(advisory_lock=True))
    bundle = _db_bundle(
        api_pool=FakePool(),
        worker_pool=worker_pool,
        wake_pool=FakePool(),
        lock_pool=lock_pool,
    )

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    assert worker_pool.conn.executed == []
    assert lock_pool.conn.executed[:2] == [
        ("SELECT set_config(%s, %s, false)", ("application_name", "worker_lock:token_radar_projection")),
        ("SELECT pg_try_advisory_lock(%s) AS locked", (2026051501,)),
    ]
    locked.release()
    assert lock_pool.put_back == [lock_pool.conn]
    assert lock_pool.conn.executed[-2:] == [
        ("SELECT pg_advisory_unlock(%s)", (2026051501,)),
        ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker_lock")),
    ]


def test_acquire_advisory_lock_connection_releases_unlocked_connection() -> None:
    pool = FakePool(FakeConn(advisory_lock=False))
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    with pytest.raises(RuntimeError, match="advisory_lock_unavailable"):
        bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    assert pool.put_back == [pool.conn]
    assert pool.conn.executed[-1] == ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker"))


def test_advisory_lock_release_discards_connection_when_unlock_fails() -> None:
    pool = FakePool(FakeConn(advisory_lock=True, fail_on="pg_advisory_unlock"))
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    with pytest.raises(RuntimeError, match="failed:pg_advisory_unlock"):
        locked.release()
    assert pool.put_back == [pool.conn]
    assert pool.closed == []
    assert pool.conn.closed is True


def test_advisory_lock_context_preserves_body_error_when_unlock_fails() -> None:
    pool = FakePool(FakeConn(advisory_lock=True, fail_on="pg_advisory_unlock"))
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    with pytest.raises(RuntimeError, match="body failed") as excinfo, locked:
        raise RuntimeError("body failed")
    assert any("failed:pg_advisory_unlock" in note for note in getattr(excinfo.value, "__notes__", ()))
    assert pool.put_back == [pool.conn]
    assert pool.closed == []
    assert pool.conn.closed is True


def test_wake_emitter_uses_wake_pool_connection() -> None:
    conn = FakeConn()
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=FakePool(), wake_pool=FakePool(conn))

    bundle.wake_emitter().notify_token_radar_updated(window="5m", scope="all")

    assert conn.executed[0][0] == "SELECT pg_notify(%s, %s)"
    assert conn.executed[0][1][0] == "token_radar_updated"
    assert conn.commits == 1


def test_wake_emitter_requires_callable_commit_before_notify_completion() -> None:
    conn = FakeNoCommitConn()
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=FakePool(), wake_pool=FakePool(conn))

    with pytest.raises(RuntimeError, match="wake_bus_commit_required"):
        bundle.wake_emitter().notify_token_radar_updated(window="5m", scope="all")

    assert conn.executed[0][0] == "SELECT pg_notify(%s, %s)"


def test_wake_bus_requires_connection_context_without_raw_connection_fallback() -> None:
    conn = FakeConn()
    bus = WakeBus(lambda: conn)

    with pytest.raises(RuntimeError, match="wake_bus_connection_context_required"):
        bus.notify_token_radar_updated(window="5m", scope="all")

    assert conn.executed == []
    assert conn.commits == 0


def test_wake_listener_uses_wake_pool_and_configured_channels() -> None:
    conn = FakeConn()
    bundle = _db_bundle(api_pool=FakePool(), worker_pool=FakePool(), wake_pool=FakePool(conn))

    waiter = bundle.wake_listener("pulse_candidate", channels=("token_radar_updated",))

    assert isinstance(waiter, WakeWaiter)
    assert waiter.wait(timeout=0.01) is False
    assert conn.executed == [("LISTEN token_radar_updated", None)]


def test_db_pool_bundle_aclose_closes_all_pool_roles_once() -> None:
    api_pool = FakePool()
    worker_pool = FakePool()
    lock_pool = FakePool()
    tool_pool = FakePool()
    wake_pool = FakePool()
    bundle = _db_bundle(
        api_pool=api_pool,
        worker_pool=worker_pool,
        lock_pool=lock_pool,
        tool_pool=tool_pool,
        wake_pool=wake_pool,
    )

    asyncio.run(bundle.aclose())

    assert api_pool.close_calls == 1
    assert worker_pool.close_calls == 1
    assert lock_pool.close_calls == 1
    assert tool_pool.close_calls == 1
    assert wake_pool.close_calls == 1


def test_db_pool_bundle_aclose_requires_sync_pool_close_contract_without_awaitable_fallback() -> None:
    api_pool = AwaitableClosePool()
    worker_pool = FakePool()
    wake_pool = FakePool()
    bundle = _db_bundle(api_pool=api_pool, worker_pool=worker_pool, wake_pool=wake_pool)

    with pytest.raises(ExceptionGroup) as excinfo:
        asyncio.run(bundle.aclose())

    assert any("db_pool_close_must_be_sync" in str(exc) for exc in excinfo.value.exceptions)
    assert api_pool.close_calls == 1
    assert api_pool.close_result.awaited is False
    assert worker_pool.close_calls == 1
    assert wake_pool.close_calls == 1
