from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION

DEFAULT_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_SCOPES = ("all", "matched")
DEFAULT_HOT_WINDOWS = ("5m",)

if TYPE_CHECKING:
    from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection


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
        wake_bus: Any | None = None,
        wake_listener: Any | None = None,
    ) -> None:
        self.repository_session = repository_session
        self.windows = tuple(windows)
        self.scopes = tuple(scopes)
        self.hot_windows = tuple(window for window in hot_windows if window in self.windows)
        self.limit = max(1, int(limit))
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.wake_bus = wake_bus
        self.wake_listener = wake_listener
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped: bool = False
        self._wake_queue: asyncio.Queue[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cursor = 0

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake_queue = asyncio.Queue(maxsize=1)
        listener_task = asyncio.create_task(self._listen_for_wake_hints())
        try:
            while not self._stopped:
                try:
                    await asyncio.to_thread(self.rebuild_once)
                except asyncio.CancelledError:
                    self._stopped = True
                    raise
                except Exception as exc:  # pragma: no cover - watchdog path
                    self.last_error = str(exc)
                    logger.exception(f"token radar projection worker failed: {exc}")
                if self._stopped:
                    break
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._wake_queue.get(), timeout=self.interval_seconds)
        finally:
            listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await listener_task
            self._wake_queue = None
            self._loop = None

    def stop(self) -> None:
        self._stopped = True
        self._enqueue_wake()

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
        coverage = self._latest_coverage()
        missing_items = self._missing_work_items(coverage)
        if missing_items:
            work_items = _dedupe_work_items([*self._hot_work_items(), *missing_items])
            primary_item = missing_items[0]
        else:
            work_items, primary_item = self._next_work_items()
        for window, scope in work_items:
            key = f"{window}:{scope}"
            try:
                with self.repository_session() as repos:
                    projection = _projection_class()(repos=repos)
                    window_result = projection.rebuild(
                        window=window,
                        scope=scope,
                        now_ms=computed_at_ms,
                        limit=self.limit,
                    )
            except Exception as exc:
                self.last_error = self.last_error or str(exc)
                logger.exception(f"token radar projection window failed: window={window} scope={scope} error={exc}")
                window_result = {
                    "rows_written": 0,
                    "source_rows": 0,
                    "computed_at_ms": computed_at_ms,
                    "status": "failed",
                    "error": str(exc),
                }
                self._mark_failed_coverage(
                    window=window,
                    scope=scope,
                    computed_at_ms=computed_at_ms,
                    error=str(exc),
                )
            result["windows"][key] = window_result
            result["rows_written"] += int(window_result.get("rows_written") or 0)
            result["source_rows"] += int(window_result.get("source_rows") or 0)
            result["window"] = primary_item[0]
            result["scope"] = primary_item[1]
            if str(window_result.get("status") or "") == "ready" and self.wake_bus is not None:
                self.wake_bus.notify_token_radar_updated(window=window, scope=scope)
            self.last_result = result
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def close(self) -> None:
        return None

    async def _listen_for_wake_hints(self) -> None:
        while not self._stopped:
            if self.wake_listener is None:
                await asyncio.sleep(self.interval_seconds)
                continue
            try:
                listen_projection_wakes = cast(Callable[..., None], self.wake_listener.listen_projection_wakes)
                await asyncio.to_thread(
                    listen_projection_wakes,
                    on_wake=self._enqueue_wake_threadsafe,
                    should_stop=lambda: self._stopped,
                    interval_seconds=self.interval_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - listener diagnostics
                logger.debug(f"token radar projection wake listener unavailable: {exc}")
                await asyncio.sleep(self.interval_seconds)

    def _enqueue_wake_threadsafe(self) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._enqueue_wake)

    def _enqueue_wake(self) -> None:
        queue = self._wake_queue
        if queue is None or queue.full():
            return
        queue.put_nowait(None)

    def _next_work_items(self) -> tuple[list[tuple[str, str]], tuple[str, str]]:
        hot_items = self._hot_work_items()
        background_item = self._next_background_window_scope()
        work_items = list(hot_items)
        if background_item is not None and background_item not in work_items:
            work_items.append(background_item)
        if not work_items:
            raise RuntimeError("token radar projection worker has no windows or scopes configured")
        return work_items, background_item or work_items[-1]

    def _next_background_window_scope(self) -> tuple[str, str] | None:
        work_items = [
            (window, scope) for window in self.windows if window not in self.hot_windows for scope in self.scopes
        ]
        if not work_items:
            return None
        item = work_items[self._cursor % len(work_items)]
        self._cursor += 1
        return item

    def _hot_work_items(self) -> list[tuple[str, str]]:
        return [(window, scope) for window in self.hot_windows for scope in self.scopes]

    def _latest_coverage(self) -> dict[tuple[str, str], dict[str, Any]]:
        with self.repository_session() as repos:
            return cast(
                dict[tuple[str, str], dict[str, Any]],
                repos.token_radar.latest_coverage(
                    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                    windows=self.windows,
                    scopes=self.scopes,
                ),
            )

    def _missing_work_items(self, coverage: dict[tuple[str, str], dict[str, Any]]) -> list[tuple[str, str]]:
        return [
            (window, scope)
            for window in self.windows
            for scope in self.scopes
            if str(coverage.get((window, scope), {}).get("status") or "") != "ready"
        ]

    def _mark_failed_coverage(self, *, window: str, scope: str, computed_at_ms: int, error: str) -> None:
        try:
            with self.repository_session() as repos:
                repos.token_radar.mark_coverage(
                    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    status="failed",
                    reason="projection_window_failed",
                    source_rows=0,
                    row_count=0,
                    computed_at_ms=computed_at_ms,
                    started_at_ms=computed_at_ms,
                    finished_at_ms=_now_ms(),
                    error=error,
                    commit=True,
                )
        except Exception as exc:  # pragma: no cover - diagnostic side path
            logger.exception(f"failed to mark token radar projection coverage failure: {exc}")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dedupe_work_items(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _projection_class() -> type[TokenRadarProjection]:
    from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection

    return TokenRadarProjection
