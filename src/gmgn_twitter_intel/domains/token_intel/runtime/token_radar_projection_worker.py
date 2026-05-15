from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION

DEFAULT_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_SCOPES = ("all", "matched")
DEFAULT_HOT_WINDOWS = ("5m",)
ADVISORY_LOCK_KEY = 2026051501

if TYPE_CHECKING:
    from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection


class TokenRadarProjectionWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_bus: Any | None = None,
        wake_waiter: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.windows = tuple(getattr(settings, "windows", DEFAULT_WINDOWS) or DEFAULT_WINDOWS)
        self.scopes = tuple(getattr(settings, "scopes", DEFAULT_SCOPES) or DEFAULT_SCOPES)
        hot_windows = tuple(getattr(settings, "hot_windows", DEFAULT_HOT_WINDOWS) or DEFAULT_HOT_WINDOWS)
        self.hot_windows = tuple(window for window in hot_windows if window in self.windows)
        self.limit = max(1, int(getattr(settings, "batch_size", 100) or 100))
        self.wake_bus = wake_bus
        self._cursor = 0

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await asyncio.to_thread(self.rebuild_once, now_ms=now_ms)
        failed = sum(1 for item in result["windows"].values() if str(item.get("status") or "") == "failed")
        processed = max(0, len(result["windows"]) - failed)
        return WorkerResult(
            processed=processed,
            failed=failed,
            notes={
                "computed_at_ms": result["computed_at_ms"],
                "rows_written": result["rows_written"],
                "source_rows": result["source_rows"],
                "window": result.get("window"),
                "scope": result.get("scope"),
                "windows": result["windows"],
            },
        )

    def rebuild_once(
        self,
        *,
        now_ms: int | None = None,
        windows: tuple[str, ...] | None = None,
        scopes: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        computed_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_error = None
        original_windows = self.windows
        original_scopes = self.scopes
        original_hot_windows = self.hot_windows
        original_limit = self.limit
        if windows is not None:
            self.windows = tuple(windows)
            self.hot_windows = tuple(window for window in self.hot_windows if window in self.windows)
        if scopes is not None:
            self.scopes = tuple(scopes)
        if limit is not None:
            self.limit = max(1, int(limit))
        try:
            return self._rebuild_once(computed_at_ms=computed_at_ms)
        finally:
            self.windows = original_windows
            self.scopes = original_scopes
            self.hot_windows = original_hot_windows
            self.limit = original_limit

    def _rebuild_once(self, *, computed_at_ms: int) -> dict[str, Any]:
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
                with self._repository_session() as repos:
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
        return result

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
        with self._repository_session() as repos:
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
            with self._repository_session() as repos:
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

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


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
