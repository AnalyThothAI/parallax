from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary

_MAX_WINDOWS_PER_CYCLE = 5


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
        results: list[MacroSyncRunSummary] = []
        for _ in range(self._batch_size()):
            result = service.run_claimed_window_once(lease_owner=self.name, now_ms=now_ms)
            if result is None:
                break
            results.append(result)
            if result.status not in {"ok", "partial"}:
                break
        if not results:
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
        processed = sum(1 for result in results if result.status in {"ok", "partial"})
        failed = len(results) - processed
        last_result = results[-1]
        return WorkerResult(
            processed=processed,
            failed=failed,
            notes={
                "claimed": len(results),
                "provider_calls": len(results),
                "sync_run_id": last_result.sync_run_id,
                "sync_run_ids": [result.sync_run_id for result in results],
                "import_run_id": last_result.import_run_id,
                "status": last_result.status,
                "statuses": [result.status for result in results],
                "imported_observation_count": sum(result.imported_observation_count for result in results),
                "max_observed_at": str(last_result.max_observed_at) if last_result.max_observed_at else None,
                "asof_date": str(last_result.asof_date) if last_result.asof_date else None,
                **enqueue_summary,
            },
        )

    def _batch_size(self) -> int:
        configured = max(1, int(getattr(self.settings, "batch_size", 1) or 1))
        return min(configured, _MAX_WINDOWS_PER_CYCLE)

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
