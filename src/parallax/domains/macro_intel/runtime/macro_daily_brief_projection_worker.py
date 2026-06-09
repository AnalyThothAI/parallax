from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION
from parallax.domains.macro_intel.services.macro_daily_brief import build_macro_daily_brief

if TYPE_CHECKING:
    from parallax.app.runtime.repository_session import RepositorySession


class MacroDailyBriefProjectionWorker(WorkerBase):
    def __init__(self, *, clock_ms: Callable[[], int] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            snapshot = repos.macro_intel.latest_snapshot(projection_version=MACRO_VIEW_PROJECTION_VERSION)
            brief = build_macro_daily_brief(snapshot=snapshot, computed_at_ms=now)
            changed = repos.macro_intel.upsert_macro_daily_brief(brief, now_ms=now)
        return WorkerResult(
            processed=1,
            notes={
                "brief_key": str(brief["brief_key"]),
                "projection_version": str(brief["projection_version"]),
                "status": str(brief["status"]),
                "rows_written": 1 if changed else 0,
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


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["MacroDailyBriefProjectionWorker"]
