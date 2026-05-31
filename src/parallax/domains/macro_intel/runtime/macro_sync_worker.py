from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService


class MacroSyncWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings_root: object,
        wake_bus: object,
        clock_ms: Callable[[], int] | None = None,
        runner: object | None = None,
        service_factory: Callable[[], MacroSyncService] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.settings_root = settings_root
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms
        self.runner = runner
        self.service_factory = service_factory

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        service = self._service()
        enqueue_summary = service.enqueue_due_windows(now_ms=now_ms)
        result = service.run_claimed_window_once(lease_owner=self.name, now_ms=now_ms)
        if result is None:
            return WorkerResult(
                processed=0,
                skipped=1,
                notes={
                    "claimed": 0,
                    "provider_calls": 0,
                    "imported_observation_count": 0,
                    **enqueue_summary,
                },
            )
        return WorkerResult(
            processed=1 if result.status in {"ok", "partial"} else 0,
            failed=0 if result.status in {"ok", "partial"} else 1,
            notes={
                "claimed": 1,
                "provider_calls": 1,
                "sync_run_id": result.sync_run_id,
                "import_run_id": result.import_run_id,
                "status": result.status,
                "imported_observation_count": result.imported_observation_count,
                "max_observed_at": str(result.max_observed_at) if result.max_observed_at else None,
                "asof_date": str(result.asof_date) if result.asof_date else None,
            },
        )

    def _service(self) -> MacroSyncService:
        if self.service_factory is not None:
            return self.service_factory()
        return MacroSyncService(
            settings=self.settings_root,
            db=self.db,
            runner=self.runner,  # type: ignore[arg-type]
            wake_bus=self.wake_bus,
            clock_ms=self.clock_ms,
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["MacroSyncWorker"]
