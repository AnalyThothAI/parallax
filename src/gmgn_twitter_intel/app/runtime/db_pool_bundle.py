from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession, repositories_for_connection
from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry
from gmgn_twitter_intel.app.runtime.wake_bus import WakeBus
from gmgn_twitter_intel.app.runtime.wake_waiter import WakeWaiter
from gmgn_twitter_intel.platform.db.postgres_client import create_pool, with_password_from_file

_API_STATEMENT_TIMEOUT_SECONDS = 5.0
_WORKER_STATEMENT_TIMEOUT_SECONDS = 30.0
_WORKER_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS = 60.0
_WAKE_KEEPALIVES_IDLE_SECONDS = 30
_WAKE_KEEPALIVES_INTERVAL_SECONDS = 10
_WAKE_KEEPALIVES_COUNT = 3


@dataclass(slots=True)
class DBPoolBundle:
    api_pool: Any
    worker_pool: Any
    wake_pool: Any
    tool_pool: Any | None = None
    lock_pool: Any | None = None
    wake_pool_max_size: int = 0
    enabled_wake_listener_concurrency: int = 0
    telemetry: TelemetryRegistry | None = field(default_factory=TelemetryRegistry)

    @classmethod
    def create(cls, settings: Any, *, telemetry: TelemetryRegistry | None = None) -> DBPoolBundle:
        dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
        api_pool_max = max(2, int(settings.postgres_pool_max_size))
        worker_pool_max = max(2, int(settings.postgres_pool_max_size))
        try:
            api_pool = create_pool(
                dsn,
                min_size=1,
                max_size=api_pool_max,
                connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
                application_name="gmgn_api",
                statement_timeout_seconds=_API_STATEMENT_TIMEOUT_SECONDS,
            )
            worker_pool = create_pool(
                dsn,
                min_size=max(0, min(int(settings.postgres_pool_min_size), worker_pool_max)),
                max_size=worker_pool_max,
                connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
                application_name="gmgn_worker",
                statement_timeout_seconds=_WORKER_STATEMENT_TIMEOUT_SECONDS,
                idle_in_transaction_session_timeout_seconds=_WORKER_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS,
            )
            lock_pool = create_pool(
                dsn,
                min_size=0,
                max_size=worker_pool_max,
                connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
                application_name="gmgn_worker_lock",
                statement_timeout_seconds=_API_STATEMENT_TIMEOUT_SECONDS,
                keepalives=True,
                keepalives_idle=_WAKE_KEEPALIVES_IDLE_SECONDS,
                keepalives_interval=_WAKE_KEEPALIVES_INTERVAL_SECONDS,
                keepalives_count=_WAKE_KEEPALIVES_COUNT,
            )
            tool_pool = create_pool(
                dsn,
                min_size=0,
                max_size=3,
                connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
                application_name="gmgn_agent_tools",
                statement_timeout_seconds=_API_STATEMENT_TIMEOUT_SECONDS,
                read_only=True,
            )
            computed_wake_listener_concurrency = enabled_wake_listener_concurrency(settings)
            computed_wake_pool_max_size = wake_pool_max_size(settings)
            wake_pool = create_pool(
                dsn,
                min_size=1,
                max_size=computed_wake_pool_max_size,
                connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
                application_name="gmgn_wake",
                statement_timeout_seconds=None,
                keepalives=True,
                keepalives_idle=_WAKE_KEEPALIVES_IDLE_SECONDS,
                keepalives_interval=_WAKE_KEEPALIVES_INTERVAL_SECONDS,
                keepalives_count=_WAKE_KEEPALIVES_COUNT,
            )
        except Exception:
            for pool in (
                locals().get("api_pool"),
                locals().get("worker_pool"),
                locals().get("lock_pool"),
                locals().get("tool_pool"),
                locals().get("wake_pool"),
            ):
                close = getattr(pool, "close", None)
                if close:
                    close()
            raise
        return cls(
            api_pool=api_pool,
            worker_pool=worker_pool,
            wake_pool=wake_pool,
            tool_pool=tool_pool,
            lock_pool=lock_pool,
            wake_pool_max_size=computed_wake_pool_max_size,
            enabled_wake_listener_concurrency=computed_wake_listener_concurrency,
            telemetry=telemetry if telemetry is not None else TelemetryRegistry(),
        )

    @contextmanager
    def api_session(self) -> Iterator[RepositorySession]:
        with self._checkout(self.api_pool, pool_name="api") as conn:
            yield repositories_for_connection(conn)

    @contextmanager
    def worker_session(
        self,
        name: str,
        statement_timeout_seconds: float | None = None,
    ) -> Iterator[RepositorySession]:
        started = time.perf_counter()
        conn = self.worker_pool.getconn()
        self._record_pool_wait("worker", (time.perf_counter() - started) * 1000)
        returned = False
        try:
            _set_config(conn, "application_name", f"worker:{_normalize_worker_name(name)}")
            if statement_timeout_seconds is not None:
                _set_config(conn, "statement_timeout", _statement_timeout_value(statement_timeout_seconds))
            try:
                yield repositories_for_connection(conn)
            except BaseException:
                try:
                    _reset_worker_connection(conn, statement_timeout_seconds=statement_timeout_seconds)
                except Exception:
                    _discard_connection(self.worker_pool, conn)
                    returned = True
                else:
                    self.worker_pool.putconn(conn)
                    returned = True
                raise
            _reset_worker_connection(conn, statement_timeout_seconds=statement_timeout_seconds)
            self.worker_pool.putconn(conn)
            returned = True
        except Exception:
            if not returned:
                _discard_connection(self.worker_pool, conn)
            raise

    def wake_emitter(self) -> WakeBus:
        return WakeBus(self.wake_pool.connection)

    def wake_listener(self, name: str, channels: tuple[str, ...]) -> WakeWaiter:
        _normalize_worker_name(name)
        return WakeWaiter(self.wake_pool, channels=channels)

    def acquire_advisory_lock_connection(self, worker_name: str, key: int) -> AdvisoryLockConnection:
        pool = self.lock_pool if self.lock_pool is not None else self.worker_pool
        pool_name = "worker_lock" if self.lock_pool is not None else "worker"
        application_prefix = "worker_lock" if self.lock_pool is not None else "worker"
        reset_application_name = "gmgn_worker_lock" if self.lock_pool is not None else "gmgn_worker"
        started = time.perf_counter()
        conn = pool.getconn()
        self._record_pool_wait(pool_name, (time.perf_counter() - started) * 1000)
        try:
            _set_config(conn, "application_name", f"{application_prefix}:{_normalize_worker_name(worker_name)}")
            row = conn.execute("SELECT pg_try_advisory_lock(%s) AS locked", (int(key),)).fetchone()
            if not row or not bool(row["locked"]):
                raise RuntimeError("advisory_lock_unavailable")
            return AdvisoryLockConnection(
                pool=pool,
                conn=conn,
                key=int(key),
                reset_application_name=reset_application_name,
            )
        except Exception:
            _return_or_discard(pool, conn, application_name=reset_application_name)
            raise

    @contextmanager
    def _checkout(self, pool: Any, *, pool_name: str) -> Iterator[Any]:
        started = time.perf_counter()
        context = pool.connection()
        conn = context.__enter__()
        self._record_pool_wait(pool_name, (time.perf_counter() - started) * 1000)
        clean_exit = False
        try:
            yield conn
            clean_exit = True
        except BaseException as exc:
            context.__exit__(type(exc), exc, exc.__traceback__)
            raise
        finally:
            if clean_exit:
                context.__exit__(None, None, None)

    def _record_pool_wait(self, pool_name: str, wait_ms: float) -> None:
        if self.telemetry is not None:
            self.telemetry.record_pool_wait(pool_name, wait_ms)


@dataclass(slots=True)
class AdvisoryLockConnection:
    pool: Any
    conn: Any
    key: int
    reset_application_name: str = "gmgn_worker"
    _released: bool = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.conn, name)

    def release(self) -> None:
        if self._released:
            return
        try:
            self.conn.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
            _set_config(self.conn, "application_name", self.reset_application_name)
        except Exception:
            self._discard()
            raise
        else:
            self.pool.putconn(self.conn)
            self._released = True

    def _discard(self) -> None:
        _discard_connection(self.pool, self.conn)
        self._released = True

    def close(self) -> None:
        self.release()

    def __enter__(self) -> AdvisoryLockConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        if exc_type is None:
            self.release()
            return False
        try:
            self.release()
        except Exception as release_exc:
            add_note = getattr(exc, "add_note", None)
            if add_note:
                add_note(f"advisory lock release failed: {release_exc}")
        return False


def _normalize_worker_name(name: str) -> str:
    return str(name).strip().replace(" ", "_") or "unknown"


def _statement_timeout_value(seconds: float) -> str:
    return f"{max(0, int(float(seconds) * 1000))}ms"


def wake_pool_max_size(settings: Any) -> int:
    return max(3, enabled_wake_listener_concurrency(settings) + 2)


def enabled_wake_listener_concurrency(settings: Any) -> int:
    workers = getattr(settings, "workers", None)
    if workers is None:
        return 0
    wake_slots = 0
    for worker_settings in _iter_worker_settings(workers):
        if not bool(getattr(worker_settings, "enabled", True)):
            continue
        wakes_on = tuple(getattr(worker_settings, "wakes_on", ()) or ())
        if not wakes_on:
            continue
        wake_slots += max(1, int(getattr(worker_settings, "concurrency", 1) or 1))
    return wake_slots


def _iter_worker_settings(workers: Any) -> Iterator[Any]:
    fields = getattr(type(workers), "model_fields", None)
    if isinstance(fields, dict):
        for name in fields:
            yield getattr(workers, name)
        return
    for name, value in vars(workers).items():
        if not str(name).startswith("_"):
            yield value


def _set_config(conn: Any, name: str, value: str) -> None:
    conn.execute("SELECT set_config(%s, %s, false)", (str(name), str(value)))


def _reset_worker_connection(conn: Any, *, statement_timeout_seconds: float | None) -> None:
    if statement_timeout_seconds is not None:
        _set_config(conn, "statement_timeout", _statement_timeout_value(_WORKER_STATEMENT_TIMEOUT_SECONDS))
    _set_config(conn, "application_name", "gmgn_worker")


def _return_or_discard(pool: Any, conn: Any, *, application_name: str = "gmgn_worker") -> None:
    try:
        _set_config(conn, "application_name", application_name)
    except Exception:
        _discard_connection(pool, conn)
        return
    pool.putconn(conn)


def _discard_connection(pool: Any, conn: Any) -> None:
    discard = getattr(pool, "close_returns", None)
    if discard:
        discard(conn)
        return
    close = getattr(conn, "close", None)
    if close:
        close()
    pool.putconn(conn)
