from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger

from parallax.platform.validation import require_nonnegative_float

_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NOTIFY_WAIT_SLICE_SECONDS = 0.25


class WakeWaiterConnectionContractError(RuntimeError):
    pass


class WakeWaiter:
    def __init__(self, wake_pool: Any, *, channels: Sequence[str]) -> None:
        self._wake_pool = wake_pool
        self._channels = tuple(_normalize_channel(channel) for channel in channels if str(channel).strip())
        self._local_wake = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._closed = False

    def wake(self) -> None:
        self._local_wake.set()

    async def async_wait(self, timeout: float) -> bool:  # noqa: ASYNC109 - mirrors synchronous wait(timeout).
        if self._closed:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor_for_wait(), self.wait, timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.wake()
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def wait(self, timeout: float) -> bool:
        timeout_seconds = require_nonnegative_float(
            timeout,
            error_code="wake_waiter_timeout_seconds_required",
        )
        deadline = time.monotonic() + timeout_seconds
        retry_after_failure = False
        while True:
            if self._local_wake.is_set():
                self._local_wake.clear()
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0 and not retry_after_failure:
                return False
            try:
                retry_after_failure = False
                return self._wait_once(timeout=remaining)
            except WakeWaiterConnectionContractError:
                raise
            except Exception as exc:
                logger.warning("wake waiter reconnecting after LISTEN failure: {}", exc)
                if timeout_seconds <= 0:
                    return False
                retry_after_failure = True

    def _wait_once(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + _remaining_wait_seconds(timeout)
        with self._wake_pool.connection() as conn:
            for channel in self._channels:
                conn.execute(f"LISTEN {channel}")
            _commit_listen(conn)
            if self._local_wake.wait(timeout=0):
                self._local_wake.clear()
                return True
            notifies = _notifies(conn)
            while True:
                if self._local_wake.is_set():
                    self._local_wake.clear()
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                for _notify in notifies(timeout=min(remaining, _NOTIFY_WAIT_SLICE_SECONDS), stop_after=1):
                    return True

    def _executor_for_wait(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wake-waiter")
        return self._executor


def _normalize_channel(channel: str) -> str:
    normalized = str(channel).strip()
    if not _CHANNEL_RE.fullmatch(normalized):
        raise ValueError(f"invalid_wake_channel:{normalized}")
    return normalized


def _remaining_wait_seconds(value: float) -> float:
    return value if value > 0 else 0.0


def _commit_listen(conn: Any) -> None:
    try:
        commit = conn.commit
    except AttributeError as exc:
        raise WakeWaiterConnectionContractError("wake_waiter_commit_required") from exc
    if not callable(commit):
        raise WakeWaiterConnectionContractError("wake_waiter_commit_required")
    commit()


def _notifies(conn: Any) -> Any:
    try:
        notifies = conn.notifies
    except AttributeError as exc:
        raise WakeWaiterConnectionContractError("wake_waiter_notifies_required") from exc
    if not callable(notifies):
        raise WakeWaiterConnectionContractError("wake_waiter_notifies_required")
    return notifies
