from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.app.runtime.wake_waiter import WakeWaiter


class FakeConn:
    def __init__(
        self,
        *,
        notifications: list[object] | None = None,
        fail_listen: bool = False,
        notify_sleep_seconds: float = 0.0,
    ) -> None:
        self.notifications = notifications or []
        self.fail_listen = fail_listen
        self.notify_sleep_seconds = notify_sleep_seconds
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0

    def execute(self, sql: str, params: tuple[Any, ...] | None = None):
        self.executed.append((sql, params))
        if self.fail_listen and sql.startswith("LISTEN"):
            raise RuntimeError("listen failed")
        return self

    def commit(self) -> None:
        self.commits += 1

    def notifies(self, *, timeout: float, stop_after: int):
        if self.notify_sleep_seconds:
            time.sleep(min(timeout, self.notify_sleep_seconds))
        yield from self.notifications[:stop_after]


class FakePool:
    def __init__(self, *connections: FakeConn) -> None:
        self.connections = list(connections)
        self.checkout_count = 0

    @contextmanager
    def connection(self):
        conn = self.connections[min(self.checkout_count, len(self.connections) - 1)]
        self.checkout_count += 1
        yield conn


def test_wait_listens_on_configured_channels_and_returns_true_on_notify() -> None:
    conn = FakeConn(notifications=[object()])
    waiter = WakeWaiter(FakePool(conn), channels=("market_observation_written", "resolution_updated"))

    assert waiter.wait(timeout=0.5) is True

    assert conn.executed == [
        ("LISTEN market_observation_written", None),
        ("LISTEN resolution_updated", None),
    ]
    assert conn.commits == 1


def test_wait_returns_false_on_timeout_for_catch_up() -> None:
    conn = FakeConn(notifications=[])
    waiter = WakeWaiter(FakePool(conn), channels=("token_radar_updated",))

    assert waiter.wait(timeout=0.01) is False


def test_wait_reconnects_after_listen_failure_and_still_times_out() -> None:
    first = FakeConn(fail_listen=True)
    second = FakeConn(notifications=[])
    pool = FakePool(first, second)
    waiter = WakeWaiter(pool, channels=("token_radar_updated",))

    assert waiter.wait(timeout=0.01) is False

    assert pool.checkout_count == 2
    assert second.executed == [("LISTEN token_radar_updated", None)]


def test_wake_unblocks_next_wait_without_database_notify() -> None:
    conn = FakeConn(notifications=[])
    waiter = WakeWaiter(FakePool(conn), channels=("token_radar_updated",))

    waiter.wake()

    assert waiter.wait(timeout=10) is True


def test_wake_interrupts_active_wait_between_notify_slices() -> None:
    conn = FakeConn(notifications=[], notify_sleep_seconds=0.05)
    waiter = WakeWaiter(FakePool(conn), channels=("token_radar_updated",))
    result: list[bool] = []
    thread = threading.Thread(target=lambda: result.append(waiter.wait(timeout=5)))

    started = time.monotonic()
    thread.start()
    time.sleep(0.05)
    waiter.wake()
    thread.join(timeout=1)

    assert result == [True]
    assert time.monotonic() - started < 1


def test_async_wait_wraps_blocking_wait() -> None:
    conn = FakeConn(notifications=[object()])
    waiter = WakeWaiter(FakePool(conn), channels=("token_radar_updated",))

    assert asyncio.run(waiter.async_wait(timeout=1)) is True
