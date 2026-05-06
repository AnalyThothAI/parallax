from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from .asset_market_sync import sync_okx_cex_universe


class AssetMarketSyncWorker:
    def __init__(
        self,
        *,
        client,
        repository_session,
        inst_types: tuple[str, ...],
        interval_seconds: float = 300.0,
    ) -> None:
        self.client = client
        self.repository_session = repository_session
        self.inst_types = tuple(str(item).strip().upper() for item in inst_types if str(item).strip())
        self.interval_seconds = interval_seconds
        self._stopped = False
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None

    async def run(self) -> None:
        while not self._stopped:
            try:
                self.last_result = self.sync_once(now_ms=_now_ms())
                self.last_run_at_ms = _now_ms()
            except Exception as exc:  # pragma: no cover - watchdog path
                logger.exception(f"Asset market sync worker failed: {exc}")
            await asyncio.sleep(max(1.0, float(self.interval_seconds)))

    def sync_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_at_ms = int(now_ms or _now_ms())
        with self.repository_session() as repos:
            return sync_okx_cex_universe(
                assets=repos.assets,
                client=self.client,
                inst_types=self.inst_types,
                observed_at_ms=observed_at_ms,
            )

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close:
            close()


def _now_ms() -> int:
    return int(time.time() * 1000)
