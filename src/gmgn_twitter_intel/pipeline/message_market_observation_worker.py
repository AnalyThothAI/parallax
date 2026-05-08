from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from .message_market_observation import observe_message_market


class MessageMarketObservationWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        cex_client=None,
        dex_client=None,
        interval_seconds: float = 5.0,
        limit: int = 100,
    ) -> None:
        self.repository_session = repository_session
        self.cex_client = cex_client
        self.dex_client = dex_client
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.limit = max(1, int(limit))
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"message market observation worker failed: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        self.last_started_at_ms = observed_at_ms
        self.last_error = None
        with self.repository_session() as repos:
            result = observe_message_market(
                repos=repos,
                cex_client=self.cex_client,
                dex_client=self.dex_client,
                now_ms=observed_at_ms,
                limit=self.limit,
            )
        self.last_run_at_ms = int(time.time() * 1000)
        self.last_result = result
        return result

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        for client in (self.cex_client, self.dex_client):
            close = getattr(client, "close", None)
            if close:
                close()
