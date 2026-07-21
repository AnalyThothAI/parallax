from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime import db_pool_bundle
from parallax.app.runtime.db_pool_bundle import DBPoolBundle


class FakeConn:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> FakeConn:
        self.executed.append((sql, params))
        if self.fail_on and self.fail_on in f"{sql} {params}":
            raise RuntimeError(f"failed:{self.fail_on}")
        return self

    def close(self) -> None:
        self.closed = True


class FakeConnectionContext:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConn:
        self.entered = True
        return self.conn

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.exited = True


class FakePool:
    def __init__(self, conn: FakeConn | None = None) -> None:
        self.conn = conn or FakeConn()
        self.contexts: list[FakeConnectionContext] = []
        self.put_back: list[FakeConn] = []
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


class MissingClosePool:
    pass


class FailingClosePool:
    def close(self) -> None:
        raise RuntimeError("close failed")


class AwaitableClosePool(FakePool):
    def close(self) -> Any:
        self.close_calls += 1
        return SimpleNamespace(__await__=lambda: iter(()))


class FakeTelemetry:
    def __init__(self) -> None:
        self.pool_waits: list[tuple[str, float]] = []

    def record_pool_wait(self, pool: str, wait_ms: float) -> None:
        self.pool_waits.append((pool, wait_ms))


def _workers() -> SimpleNamespace:
    return SimpleNamespace(
        notification_delivery=SimpleNamespace(
            running_timeout_ms=300_000,
            stale_running_terminalization_batch_size=100,
        )
    )


@dataclass
class FakeSettings:
    storage: object = field(
        default_factory=lambda: SimpleNamespace(
            postgres=SimpleNamespace(
                dsn="postgresql://parallax_app@postgres:5432/parallax",
                pool_min_size=1,
                pool_max_size=10,
                connect_timeout_seconds=5.0,
            )
        )
    )
    postgres_password_file: object | None = None
    workers: object = field(default_factory=_workers)


def _bundle(*, api_pool: Any | None = None, worker_pool: Any | None = None) -> DBPoolBundle:
    return DBPoolBundle(
        api_pool=api_pool or FakePool(),
        worker_pool=worker_pool or FakePool(),
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
        telemetry=FakeTelemetry(),
    )


def test_create_builds_only_api_and_worker_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, Any]] = []

    def fake_create_pool(dsn: str, **kwargs: Any) -> FakePool:
        created.append({"dsn": dsn, **kwargs})
        return FakePool()

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)

    bundle = DBPoolBundle.create(FakeSettings())

    assert isinstance(bundle.api_pool, FakePool)
    assert isinstance(bundle.worker_pool, FakePool)
    assert [item["application_name"] for item in created] == ["gmgn_api", "gmgn_worker"]
    assert created[0]["statement_timeout_seconds"] == 5.0
    assert created[1]["statement_timeout_seconds"] == 30.0
    assert created[1]["idle_in_transaction_session_timeout_seconds"] == 60.0


def test_create_failure_closes_already_created_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakePool()
    calls = 0

    def fake_create_pool(dsn: str, **kwargs: Any) -> FakePool:
        nonlocal calls
        _ = dsn, kwargs
        calls += 1
        if calls == 2:
            raise RuntimeError("worker pool failed")
        return first

    monkeypatch.setattr(db_pool_bundle, "create_pool", fake_create_pool)
    monkeypatch.setattr(db_pool_bundle, "with_password_from_file", lambda dsn, password_file: dsn)

    with pytest.raises(RuntimeError, match="worker pool failed"):
        DBPoolBundle.create(FakeSettings())

    assert first.close_calls == 1


@pytest.mark.parametrize("pool", [MissingClosePool(), FailingClosePool()])
def test_partial_cleanup_preserves_original_error(pool: object) -> None:
    error = RuntimeError("create failed")
    db_pool_bundle._close_partial_pools(error, pool)
    assert error.__notes__
    assert "partial db pool cleanup failed" in error.__notes__[0]


def test_api_session_yields_bound_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    bundle = _bundle(api_pool=pool)
    expected = object()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda conn, **kwargs: expected)

    with bundle.api_session() as repos:
        assert repos is expected

    assert pool.contexts[0].entered is True
    assert pool.contexts[0].exited is True
    assert bundle.telemetry.pool_waits[0][0] == "api"


def test_worker_session_sets_and_restores_connection_state(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    bundle = _bundle(worker_pool=pool)
    expected = object()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda conn, **kwargs: expected)

    with bundle.worker_session("token radar", statement_timeout_seconds=12) as repos:
        assert repos is expected

    values = [params for _sql, params in pool.conn.executed]
    assert ("application_name", "worker:token_radar") in values
    assert ("statement_timeout", "12000ms") in values
    assert ("statement_timeout", "30000ms") in values
    assert ("application_name", "gmgn_worker") in values
    assert pool.put_back == [pool.conn]


@pytest.mark.parametrize("value", [-1, True, "12"])
def test_worker_session_rejects_malformed_statement_timeout(value: object) -> None:
    bundle = _bundle()
    with (
        pytest.raises(ValueError, match="db_statement_timeout_seconds_required"),
        bundle.worker_session("worker", statement_timeout_seconds=value),  # type: ignore[arg-type]
    ):
        pass


def test_worker_session_discards_connection_when_reset_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(fail_on="gmgn_worker")
    pool = FakePool(conn)
    bundle = _bundle(worker_pool=pool)
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda conn, **kwargs: object())

    with pytest.raises(RuntimeError, match="failed:gmgn_worker"), bundle.worker_session("worker"):
        pass

    assert conn.closed is True
    assert pool.put_back == [conn]


def test_aclose_closes_both_pools_once() -> None:
    async def scenario() -> None:
        api_pool = FakePool()
        worker_pool = FakePool()
        bundle = _bundle(api_pool=api_pool, worker_pool=worker_pool)
        await bundle.aclose()
        assert api_pool.close_calls == 1
        assert worker_pool.close_calls == 1

    asyncio.run(scenario())


def test_aclose_rejects_awaitable_pool_close_contract() -> None:
    async def scenario() -> None:
        awaitable_pool = AwaitableClosePool()
        bundle = _bundle(api_pool=awaitable_pool)
        with pytest.raises(ExceptionGroup, match="db_pool_bundle_close_failed"):
            await bundle.aclose()

    asyncio.run(scenario())
