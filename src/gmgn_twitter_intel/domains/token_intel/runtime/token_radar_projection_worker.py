from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS

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
        self.cold_interval_ms = int(float(getattr(settings, "cold_interval_seconds", 60.0) or 0) * 1000)
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
                "status": result.get("status"),
                "claimed": result.get("claimed"),
                "catch_up_enqueued": result.get("catch_up_enqueued"),
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
        try:
            with self._repository_session() as repos:
                projection = _projection_class()(repos=repos)
                result = projection.rebuild_dirty_targets(
                    windows=self.windows,
                    scopes=self.scopes,
                    now_ms=computed_at_ms,
                    limit=self.limit,
                    rank_limit=self.limit,
                    lease_owner=self.name,
                )
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception(f"token radar dirty target projection failed: error={exc}")
            result = {
                "computed_at_ms": computed_at_ms,
                "rows_written": 0,
                "source_rows": 0,
                "status": "failed",
                "error": str(exc),
                "claimed": 0,
                "catch_up_enqueued": 0,
                "windows": {},
            }

        result.setdefault("computed_at_ms", computed_at_ms)
        result.setdefault("rows_written", 0)
        result.setdefault("source_rows", 0)
        result.setdefault("windows", {})
        result.setdefault("claimed", 0)
        result.setdefault("catch_up_enqueued", 0)
        result["window"] = self.windows[0] if self.windows else None
        result["scope"] = self.scopes[0] if self.scopes else None

        if str(result.get("status") or "") == "failed":
            self.last_error = self.last_error or str(result.get("error") or "token radar projection failed")

        if int(result.get("claimed") or 0) <= 0 and str(result.get("status") or "") != "failed":
            result["catch_up_enqueued"] = self._enqueue_recent_dirty_targets(computed_at_ms=computed_at_ms)

        for key, window_result in result["windows"].items():
            if str(window_result.get("status") or "") != "ready" or self.wake_bus is None:
                continue
            window, scope = str(key).split(":", 1)
            self.wake_bus.notify_token_radar_updated(window=window, scope=scope)
        return result

    def _enqueue_recent_dirty_targets(self, *, computed_at_ms: int) -> int:
        lookback_ms = max((WINDOW_MS.get(window, 0) for window in self.windows), default=0)
        if lookback_ms <= 0:
            lookback_ms = 60 * 60 * 1000
        with self._repository_session() as repos:
            dirty_repo = getattr(repos, "token_radar_dirty_targets", None)
            if dirty_repo is None:
                return 0
            return int(
                dirty_repo.enqueue_recent_resolved_targets(
                    since_ms=max(0, int(computed_at_ms) - lookback_ms),
                    now_ms=int(computed_at_ms),
                    limit=self.limit,
                    reason="projection_catch_up",
                    commit=True,
                )
            )

    def _next_work_items(
        self,
        *,
        coverage: dict[tuple[str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> tuple[list[tuple[str, str]], tuple[str, str]]:
        hot_items = self._hot_work_items()
        background_item = self._next_background_window_scope(
            coverage=coverage,
            computed_at_ms=computed_at_ms,
        )
        work_items = list(hot_items)
        if background_item is not None and background_item not in work_items:
            work_items.append(background_item)
        if not work_items:
            raise RuntimeError("token radar projection worker has no windows or scopes configured")
        return work_items, background_item or work_items[-1]

    def _next_background_window_scope(
        self,
        *,
        coverage: dict[tuple[str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> tuple[str, str] | None:
        work_items = [
            (window, scope) for window in self.windows if window not in self.hot_windows for scope in self.scopes
        ]
        if not work_items:
            return None
        for _ in range(len(work_items)):
            item = work_items[self._cursor % len(work_items)]
            self._cursor += 1
            latest = coverage.get(item, {}).get("computed_at_ms")
            if latest is None or computed_at_ms - int(latest) >= self.cold_interval_ms:
                return item
        return None

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

    def _missing_work_items(
        self,
        coverage: dict[tuple[str, str], dict[str, Any]],
        *,
        computed_at_ms: int,
    ) -> list[tuple[str, str]]:
        missing: list[tuple[str, str]] = []
        for window in self.windows:
            for scope in self.scopes:
                item = (window, scope)
                item_coverage = coverage.get(item, {})
                status = str(item_coverage.get("status") or "")
                if status == "ready":
                    continue
                latest = item_coverage.get("computed_at_ms")
                if (
                    status == "failed"
                    and latest is not None
                    and computed_at_ms - int(latest) < self.cold_interval_ms
                ):
                    continue
                missing.append(item)
        return missing

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
