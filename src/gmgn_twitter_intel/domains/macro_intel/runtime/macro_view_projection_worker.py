from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, cast

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import (
    build_macro_view_snapshot,
)

if TYPE_CHECKING:
    from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession


class MacroViewProjectionWorker(WorkerBase):
    def __init__(self, *, clock_ms: Callable[[], int] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            projected_rows_written = repos.macro_intel.refresh_observation_series_rows(
                projection_version=MACRO_VIEW_PROJECTION_VERSION,
                now_ms=now,
                lookback_days=self._lookback_days(),
                limit_per_series=self._limit_per_series(),
            )
            observations = repos.macro_intel.observations_for_concepts(
                concept_keys=MACRO_CORE_CONCEPTS,
                lookback_days=self._lookback_days(),
                limit_per_series=self._limit_per_series(),
            )
            snapshot = build_macro_view_snapshot(observations, computed_at_ms=now)
            repos.macro_intel.insert_snapshot(snapshot)
        return WorkerResult(
            processed=1,
            notes={
                "claimed": 1,
                "queue_depth": 0,
                "source_rows_scanned": len(observations),
                "targets_loaded": len(MACRO_CORE_CONCEPTS),
                "rows_written": 1,
                "projected_rows_written": projected_rows_written,
                "projection_version": str(snapshot["projection_version"]),
                "status": str(snapshot["status"]),
                "regime": str(snapshot["regime"]),
                "history_coverage_ratio": str(
                    (snapshot.get("source_coverage_json") or {}).get("history_coverage_ratio", 0.0)
                ),
                "data_gap_count": str(len(snapshot.get("data_gaps_json") or [])),
            },
        )

    def _repository_session(self) -> AbstractContextManager[RepositorySession]:
        return cast(
            "AbstractContextManager[RepositorySession]",
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
            ),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 250)))

    def _lookback_days(self) -> int:
        return max(1, int(getattr(self.settings, "lookback_days", MACRO_VIEW_HISTORY_LOOKBACK_DAYS)))

    def _limit_per_series(self) -> int:
        return max(1, int(getattr(self.settings, "limit_per_series", MACRO_VIEW_HISTORY_LIMIT_PER_SERIES)))


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["MacroViewProjectionWorker"]
