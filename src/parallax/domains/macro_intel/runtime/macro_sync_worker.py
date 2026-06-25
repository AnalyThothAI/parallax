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
        settings: Any,
        db: Any,
        telemetry: Any,
        settings_root: Any,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        runner: object | None = None,
        service_factory: Callable[[], MacroSyncService] | None = None,
        name: str = "macro_sync",
    ) -> None:
        if settings is None:
            raise RuntimeError("macro_sync_settings_required")
        if db is None:
            raise RuntimeError("macro_sync_db_required")
        if settings_root is None:
            raise RuntimeError("macro_sync_settings_root_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.settings_root = settings_root
        self.wake_emitter = wake_emitter
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
        configured = _required_positive_int(
            self.settings.batch_size,
            error_code="macro_sync_batch_size_required",
        )
        return min(configured, _MAX_WINDOWS_PER_CYCLE)

    def _service(self) -> MacroSyncService:
        if self.service_factory is not None:
            return self.service_factory()
        return MacroSyncService(
            settings=self.settings_root,
            db=self.db,
            runner=self.runner,  # type: ignore[arg-type]
            wake_emitter=self.wake_emitter,
            clock_ms=self.clock_ms,
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


__all__ = ["MacroSyncWorker"]
