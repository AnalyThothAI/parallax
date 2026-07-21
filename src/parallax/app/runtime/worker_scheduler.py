from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from parallax.app.runtime.worker_manifest import worker_start_priority
from parallax.app.runtime.worker_status import effective_worker_status

_START_PRIORITY = worker_start_priority()


class WorkerScheduler:
    def __init__(
        self,
        *,
        workers: Mapping[str, Any],
        db: Any,
    ) -> None:
        self.workers = dict(workers)
        self.db = db
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("worker_scheduler:already_started")
        self._started = True
        try:
            for name in self._ordered_worker_names():
                worker = self.workers[name]
                if not _worker_startable(worker):
                    continue
                self.tasks[name] = asyncio.create_task(worker.run(), name=f"worker:{name}")
                await asyncio.sleep(0)
                task = self.tasks[name]
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
        except Exception:
            for name in self.tasks:
                await self.workers[name].stop()
            if self.tasks:
                await asyncio.gather(*self.tasks.values(), return_exceptions=True)
            self.tasks.clear()
            self._started = False
            raise

    async def stop(self) -> None:
        errors: list[Exception] = []
        for worker in self.workers.values():
            try:
                await worker.stop()
            except Exception as exc:
                errors.append(exc)
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for task in self.tasks.values():
            task_error = _task_exception(task)
            if task_error is not None:
                errors.append(task_error)
        for worker in self.workers.values():
            try:
                await worker.aclose()
            except Exception as exc:
                errors.append(exc)
        try:
            await self.db.aclose()
        except Exception as exc:
            errors.append(exc)
        self._started = False
        if errors:
            raise ExceptionGroup("worker_scheduler_stop_failed", errors)

    def status_payload(self) -> dict[str, dict[str, Any]]:
        return {name: _worker_status_payload(worker) for name, worker in self.workers.items()}

    def _ordered_worker_names(self) -> list[str]:
        return sorted(
            self.workers,
            key=lambda name: (_START_PRIORITY.get(name, 25), name),
        )


def _worker_startable(worker: Any) -> bool:
    return worker_effective_status(worker) not in {"disabled", "intentionally_not_started", "unavailable"}


def worker_effective_status(worker: Any) -> str:
    return effective_worker_status(_worker_status_payload(worker))


def _worker_status_payload(worker: Any) -> dict[str, Any]:
    payload = worker.status_payload()
    if not isinstance(payload, Mapping):
        raise TypeError("worker_status_payload_must_be_dict")
    return dict(payload)


def _task_exception(task: asyncio.Task[Any]) -> Exception | None:
    if not task.done():
        return None
    if task.cancelled():
        return None
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return None
    return error if isinstance(error, Exception) else None
