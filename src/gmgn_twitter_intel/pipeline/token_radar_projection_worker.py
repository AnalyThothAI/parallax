from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import sync_okx_dex_prices

from .token_radar_projection import MARKET_FRESH_MS, TokenRadarProjection

DEFAULT_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_SCOPES = ("all", "matched")
PREFLIGHT_HYDRATION_LIMIT = 40


class TokenRadarProjectionWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
        limit: int = 100,
        interval_seconds: float = 10.0,
        dex_client=None,
        preflight_hydration_limit: int = PREFLIGHT_HYDRATION_LIMIT,
    ) -> None:
        self.repository_session = repository_session
        self.windows = tuple(windows)
        self.scopes = tuple(scopes)
        self.limit = max(1, int(limit))
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.dex_client = dex_client
        self.preflight_hydration_limit = max(0, int(preflight_hydration_limit))
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False
        self._cursor = 0

    async def run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.to_thread(self.rebuild_once)
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"token radar projection worker failed: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._stopped = True

    def rebuild_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        computed_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = computed_at_ms
        self.last_error = None
        result: dict[str, Any] = {
            "computed_at_ms": computed_at_ms,
            "rows_written": 0,
            "source_rows": 0,
            "windows": {},
        }
        try:
            with self.repository_session() as repos:
                projection = TokenRadarProjection(
                    repos=repos,
                    market_hydrator=self._hydrate_market if self.dex_client is not None else None,
                    preflight_hydration_limit=self.preflight_hydration_limit,
                )
                window, scope = self._next_window_scope()
                key = f"{window}:{scope}"
                window_result = projection.rebuild(
                    window=window,
                    scope=scope,
                    now_ms=computed_at_ms,
                    limit=self.limit,
                )
                result["window"] = window
                result["scope"] = scope
                result["windows"][key] = window_result
                result["rows_written"] = int(window_result.get("rows_written") or 0)
                result["source_rows"] = int(window_result.get("source_rows") or 0)
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def _hydrate_market(self, *, repos, window, scope, now_ms, score_since_ms, stale_before_ms, limit):
        return sync_okx_dex_prices(
            registry=repos.registry,
            price_observations=repos.price_observations,
            client=self.dex_client,
            observed_at_ms=now_ms,
            stale_after_ms=MARKET_FRESH_MS,
            limit=limit,
            radar_since_ms=score_since_ms,
            hot_since_ms=score_since_ms,
            refresh_universe="radar_projection_preflight",
        )

    def close(self) -> None:
        close = getattr(self.dex_client, "close", None)
        if close:
            close()

    def _next_window_scope(self) -> tuple[str, str]:
        work_items = [(window, scope) for window in self.windows for scope in self.scopes]
        if not work_items:
            raise RuntimeError("token radar projection worker has no windows or scopes configured")
        item = work_items[self._cursor % len(work_items)]
        self._cursor += 1
        return item


def _now_ms() -> int:
    return int(time.time() * 1000)
