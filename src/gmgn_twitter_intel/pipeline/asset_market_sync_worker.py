from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from .asset_market_sync import sync_okx_cex_universe, sync_okx_dex_prices

DEX_PRICE_STALE_MS = 5 * 60 * 1000
DEX_PRICE_REFRESH_LIMIT = 500


class AssetMarketSyncWorker:
    def __init__(
        self,
        *,
        repository_session,
        client=None,
        dex_client=None,
        inst_types: tuple[str, ...],
        interval_seconds: float = 300.0,
    ) -> None:
        self.client = client
        self.dex_client = dex_client
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
            result: dict[str, Any] = {}
            ran_cex = self.client is not None and bool(self.inst_types)
            ran_dex = self.dex_client is not None
            if self.client is not None and self.inst_types:
                result["cex"] = sync_okx_cex_universe(
                    assets=repos.assets,
                    client=self.client,
                    inst_types=self.inst_types,
                    observed_at_ms=observed_at_ms,
                )
            if self.dex_client is not None:
                result["dex"] = sync_okx_dex_prices(
                    assets=repos.assets,
                    client=self.dex_client,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=DEX_PRICE_STALE_MS,
                    limit=DEX_PRICE_REFRESH_LIMIT,
                )
            if ran_cex and not ran_dex:
                return result["cex"]
            if ran_dex and not ran_cex:
                return result["dex"]
            return result

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        for client in (self.client, self.dex_client):
            close = getattr(client, "close", None)
            if close:
                close()


def _now_ms() -> int:
    return int(time.time() * 1000)
