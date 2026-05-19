from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime import db_pool_bundle
from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.wake_waiter import WakeWaiter


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

    def execute(self, sql: str, params: tuple[Any, ...] | None = None):
        self.executed.append((sql, params))
        haystack = f"{sql} {params or ''}"
        if self.fail_on and self.fail_on in haystack and len(self.executed) > self.fail_after:
            raise RuntimeError(f"failed:{self.fail_on}")
        return self

    def fetchone(self):
        return {"locked": self.advisory_lock}

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

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True


class FakePool:
    def __init__(self, conn: FakeConn | None = None) -> None:
        self.conn = conn or FakeConn()
        self.contexts: list[FakeConnectionContext] = []
        self.put_back: list[FakeConn] = []
        self.closed: list[FakeConn] = []

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


class FakeTelemetry:
    def __init__(self) -> None:
        self.pool_waits: list[tuple[str, float]] = []

    def record_pool_wait(self, pool: str, wait_ms: float) -> None:
        self.pool_waits.append((pool, wait_ms))


@dataclass
class FakeSettings:
    postgres_dsn: str = "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    postgres_password_file: object | None = None
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 10
    postgres_connect_timeout_seconds: float = 5.0


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


def test_api_session_yields_repositories_and_records_pool_wait(monkeypatch) -> None:
    conn = FakeConn()
    telemetry = FakeTelemetry()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout: {"conn": checkout})
    bundle = DBPoolBundle(api_pool=FakePool(conn), worker_pool=FakePool(), wake_pool=FakePool(), telemetry=telemetry)

    with bundle.api_session() as repos:
        assert repos == {"conn": conn}

    assert telemetry.pool_waits[0][0] == "api"
    assert telemetry.pool_waits[0][1] >= 0


def test_worker_session_sets_and_restores_application_name(monkeypatch) -> None:
    conn = FakeConn()
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout: checkout)
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=FakePool(conn), wake_pool=FakePool())

    with bundle.worker_session("pulse_candidate", statement_timeout_seconds=12) as repos:
        assert repos is conn

    assert conn.executed == [
        ("SELECT set_config(%s, %s, false)", ("application_name", "worker:pulse_candidate")),
        ("SELECT set_config(%s, %s, false)", ("statement_timeout", "12000ms")),
        ("SELECT set_config(%s, %s, false)", ("statement_timeout", "30000ms")),
        ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker")),
    ]


def test_worker_session_preserves_body_error_and_discards_when_reset_fails(monkeypatch) -> None:
    conn = FakeConn(fail_on="statement_timeout", fail_after=2)
    pool = FakePool(conn)
    monkeypatch.setattr(db_pool_bundle, "repositories_for_connection", lambda checkout: checkout)
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    with (
        pytest.raises(RuntimeError, match="body failed"),
        bundle.worker_session(
            "pulse_candidate",
            statement_timeout_seconds=12,
        ),
    ):
        raise RuntimeError("body failed")

    assert pool.closed == [conn]
    assert pool.put_back == []


def test_acquire_advisory_lock_connection_returns_held_connection_until_release() -> None:
    pool = FakePool(FakeConn(advisory_lock=True))
    telemetry = FakeTelemetry()
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool(), telemetry=telemetry)

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
    bundle = DBPoolBundle(
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
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    with pytest.raises(RuntimeError, match="advisory_lock_unavailable"):
        bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    assert pool.put_back == [pool.conn]
    assert pool.conn.executed[-1] == ("SELECT set_config(%s, %s, false)", ("application_name", "gmgn_worker"))


def test_advisory_lock_release_discards_connection_when_unlock_fails() -> None:
    pool = FakePool(FakeConn(advisory_lock=True, fail_on="pg_advisory_unlock"))
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    with pytest.raises(RuntimeError, match="failed:pg_advisory_unlock"):
        locked.release()
    assert pool.put_back == []
    assert pool.closed == [pool.conn]


def test_advisory_lock_context_preserves_body_error_when_unlock_fails() -> None:
    pool = FakePool(FakeConn(advisory_lock=True, fail_on="pg_advisory_unlock"))
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=pool, wake_pool=FakePool())

    locked = bundle.acquire_advisory_lock_connection("token_radar_projection", 2026051501)

    with pytest.raises(RuntimeError, match="body failed") as excinfo, locked:
        raise RuntimeError("body failed")
    assert any("failed:pg_advisory_unlock" in note for note in getattr(excinfo.value, "__notes__", ()))
    assert pool.put_back == []
    assert pool.closed == [pool.conn]


def test_wake_emitter_uses_wake_pool_connection() -> None:
    conn = FakeConn()
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=FakePool(), wake_pool=FakePool(conn))

    bundle.wake_emitter().notify_token_radar_updated(window="5m", scope="all")

    assert conn.executed[0][0] == "SELECT pg_notify(%s, %s)"
    assert conn.executed[0][1][0] == "token_radar_updated"


def test_wake_listener_uses_wake_pool_and_configured_channels() -> None:
    conn = FakeConn()
    bundle = DBPoolBundle(api_pool=FakePool(), worker_pool=FakePool(), wake_pool=FakePool(conn))

    waiter = bundle.wake_listener("pulse_candidate", channels=("token_radar_updated",))

    assert isinstance(waiter, WakeWaiter)
    assert waiter.wait(timeout=0.01) is False
    assert conn.executed == [("LISTEN token_radar_updated", None)]
