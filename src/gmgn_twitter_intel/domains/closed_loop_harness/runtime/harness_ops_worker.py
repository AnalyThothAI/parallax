from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from ..services.harness_ops import (
    attribute_harness_credits,
    materialize_market_ready_seeds,
    settle_harness_snapshots,
    update_harness_weights,
)

HORIZONS = ("6h", "24h")


class HarnessOpsWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        poll_interval: float = 60.0,
        batch_limit: int = 200,
    ):
        self.repository_session = repository_session
        self.poll_interval = max(1.0, float(poll_interval))
        self.batch_limit = max(1, int(batch_limit))
        self.last_result: dict[str, Any] | None = None
        self.last_run_at_ms: int | None = None
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await asyncio.to_thread(self.process_once)
            except Exception as exc:
                logger.exception(f"harness ops worker loop failed: {exc}")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    def process_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms if now_ms is not None else _now_ms()
        result: dict[str, Any] = {"materialize": {}, "settlement": {}, "credit": {}, "weights": {}}
        with self.repository_session() as repos:
            result["materialize"] = materialize_market_ready_seeds(
                harness=repos.harness,
                evidence=repos.evidence,
                assets=repos.assets,
                limit=self.batch_limit,
            )
            for horizon in HORIZONS:
                result["settlement"][horizon] = settle_harness_snapshots(
                    harness=repos.harness,
                    assets=repos.assets,
                    horizon=horizon,
                    now_ms=now,
                    limit=self.batch_limit,
                )
                result["credit"][horizon] = attribute_harness_credits(
                    harness=repos.harness,
                    horizon=horizon,
                    limit=self.batch_limit,
                )
            result["weights"] = update_harness_weights(harness=repos.harness, limit=self.batch_limit * 10)
        self.last_run_at_ms = now
        self.last_result = result
        return result


def _now_ms() -> int:
    return int(time.time() * 1000)
