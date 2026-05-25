from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger

_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NOTIFY_WAIT_SLICE_SECONDS = 0.25


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
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            if self._local_wake.is_set():
                self._local_wake.clear()
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                return self._wait_once(timeout=remaining)
            except Exception as exc:
                logger.warning("wake waiter reconnecting after LISTEN failure: {}", exc)
                if deadline - time.monotonic() <= 0:
                    return False

    def _wait_once(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._wake_pool.connection() as conn:
            for channel in self._channels:
                conn.execute(f"LISTEN {channel}")
            commit = getattr(conn, "commit", None)
            if commit:
                commit()
            if self._local_wake.wait(timeout=0):
                self._local_wake.clear()
                return True
            notifies = getattr(conn, "notifies", None)
            if not notifies:
                return self._local_wake.wait(timeout=max(0.0, timeout))
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
