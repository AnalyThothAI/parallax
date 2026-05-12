from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.asset_market.services.asset_profile_refresh import refresh_asset_profiles_once


class AssetProfileRefreshWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        dex_profile_market: Any = None,
        interval_seconds: float = 60.0,
        limit: int = 50,
    ) -> None:
        self.repository_session = repository_session
        self.dex_profile_market = dex_profile_market
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
                logger.exception(f"asset profile refresh worker failed: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        self.last_started_at_ms = observed_at_ms
        self.last_error = None
        try:
            with self.repository_session() as repos:
                result = refresh_asset_profiles_once(
                    repos=repos,
                    dex_profile_market=self.dex_profile_market,
                    now_ms=observed_at_ms,
                    limit=self.limit,
                )
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_run_at_ms = int(time.time() * 1000)
        self.last_result = result
        return result

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        close = getattr(self.dex_profile_market, "close", None)
        if close:
            close()
