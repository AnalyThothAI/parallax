from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.services.source_quality_projection import (
    build_source_quality_rows,
    window_ms_for_label,
)


class NewsSourceQualityProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        processed = 0
        windows = self._windows()
        with self._repository_session() as repos:
            for window in windows:
                window_ms = window_ms_for_label(window)
                aggregate_inputs = repos.news.list_source_quality_inputs(
                    window_ms=window_ms,
                    now_ms=now,
                )
                rows = build_source_quality_rows(
                    aggregate_inputs=[dict(row) for row in aggregate_inputs],
                    window=window,
                    window_ms=window_ms,
                    computed_at_ms=now,
                )
                repos.news.replace_source_quality_rows(rows=rows, status_window=windows[0], commit=True)
                processed += len(rows)
        return WorkerResult(processed=processed, notes={"windows": windows})

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _windows(self) -> tuple[str, ...]:
        windows = tuple(str(window).strip().lower() for window in getattr(self.settings, "windows", ("24h", "7d")))
        return tuple(window for window in windows if window) or ("24h", "7d")


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsSourceQualityProjectionWorker"]
