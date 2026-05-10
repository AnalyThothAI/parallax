from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

DEFAULT_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_SCOPES = ("all", "matched")
DEFAULT_HOT_WINDOWS = ("5m",)


class TokenRadarProjectionWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
        hot_windows: tuple[str, ...] = DEFAULT_HOT_WINDOWS,
        limit: int = 100,
        interval_seconds: float = 10.0,
    ) -> None:
        self.repository_session = repository_session
        self.windows = tuple(windows)
        self.scopes = tuple(scopes)
        self.hot_windows = tuple(window for window in hot_windows if window in self.windows)
        self.limit = max(1, int(limit))
        self.interval_seconds = max(1.0, float(interval_seconds))
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
                projection = _projection_class()(repos=repos)
                work_items, primary_item = self._next_work_items()
                for window, scope in work_items:
                    key = f"{window}:{scope}"
                    window_result = projection.rebuild(
                        window=window,
                        scope=scope,
                        now_ms=computed_at_ms,
                        limit=self.limit,
                    )
                    result["windows"][key] = window_result
                    result["rows_written"] += int(window_result.get("rows_written") or 0)
                    result["source_rows"] += int(window_result.get("source_rows") or 0)
                result["window"] = primary_item[0]
                result["scope"] = primary_item[1]
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def close(self) -> None:
        return None

    def _next_work_items(self) -> tuple[list[tuple[str, str]], tuple[str, str]]:
        hot_items = [(window, scope) for window in self.hot_windows for scope in self.scopes]
        background_item = self._next_background_window_scope()
        work_items = list(hot_items)
        if background_item is not None and background_item not in work_items:
            work_items.append(background_item)
        if not work_items:
            raise RuntimeError("token radar projection worker has no windows or scopes configured")
        return work_items, background_item or work_items[-1]

    def _next_background_window_scope(self) -> tuple[str, str] | None:
        work_items = [
            (window, scope)
            for window in self.windows
            if window not in self.hot_windows
            for scope in self.scopes
        ]
        if not work_items:
            return None
        item = work_items[self._cursor % len(work_items)]
        self._cursor += 1
        return item


def _now_ms() -> int:
    return int(time.time() * 1000)


def _projection_class():
    from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection

    return TokenRadarProjection
