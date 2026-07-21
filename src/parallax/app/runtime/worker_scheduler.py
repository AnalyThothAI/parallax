from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from parallax.app.runtime.worker_manifest import worker_start_priority
from parallax.app.runtime.worker_status import effective_worker_status
from parallax.platform.validation import require_nonnegative_float

_START_PRIORITY = worker_start_priority()


class WorkerScheduler:
    def __init__(
        self,
        *,
        workers: Mapping[str, Any],
        db: Any,
        stop_timeout_seconds: float = 30.0,
    ) -> None:
        self.workers = dict(workers)
        self.db = db
        self.stop_timeout_seconds = require_nonnegative_float(
            stop_timeout_seconds,
            error_code="worker_scheduler_stop_timeout_seconds_required",
        )
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
            tasks = list(self.tasks.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
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
        pending = [task for task in self.tasks.values() if not task.done()]
        if pending:
            done, still_pending = await asyncio.wait(pending, timeout=self.stop_timeout_seconds)
            for task in done:
                _consume_task_exception(task)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)
        for task in self.tasks.values():
            if task.done():
                _consume_task_exception(task)
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

    def unhealthy_reasons(self) -> list[str]:
        reasons: list[str] = []
        for name, worker in self.workers.items():
            payload = _worker_status_payload(worker)
            effective_status = _payload_effective_status(payload)
            if effective_status in {"disabled", "intentionally_not_started"}:
                continue
            if effective_status == "unavailable":
                reasons.append(f"worker:{name}:unavailable:{_worker_unavailable_reason(payload)}")
                continue
            task_items = _worker_task_items(self.tasks, name)
            if not task_items:
                failure_reason = _worker_failure_reason(name, payload, effective_status)
                if failure_reason is not None:
                    reasons.append(failure_reason)
                    continue
                reasons.append(f"worker:{name}:stopped")
                continue
            task_failure_emitted = False
            for task_key, task in task_items:
                if task.cancelled():
                    reasons.append(f"worker:{task_key}:stopped")
                    continue
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        reasons.append(f"worker:{task_key}:errored:{exc}")
                        task_failure_emitted = True
                    else:
                        reasons.append(f"worker:{task_key}:stopped")
                    continue
            failure_reason = _worker_failure_reason(name, payload, effective_status)
            if failure_reason is not None and not task_failure_emitted:
                reasons.append(failure_reason)
        return reasons

    def _ordered_worker_names(self) -> list[str]:
        return sorted(
            self.workers,
            key=lambda name: (_START_PRIORITY.get(name, 25), name),
        )


def _worker_startable(worker: Any) -> bool:
    return worker_effective_status(worker) not in {"disabled", "intentionally_not_started", "unavailable"}


def worker_effective_status(worker: Any) -> str:
    payload = _worker_status_payload(worker)
    return _payload_effective_status(payload)


def _payload_effective_status(payload: Mapping[str, Any]) -> str:
    return effective_worker_status(payload)


def _worker_unavailable_reason(payload: Mapping[str, Any]) -> str:
    payload_reason = payload.get("unavailable_reason")
    if isinstance(payload_reason, str) and payload_reason:
        return payload_reason
    return "unavailable"


def _worker_failure_reason(name: str, payload: Mapping[str, Any], effective_status: str) -> str | None:
    last_error = payload.get("last_error")
    if _worker_hard_timed_out(payload):
        return f"worker:{name}:hard_timeout"
    if last_error:
        return f"worker:{name}:errored:{last_error}"
    if effective_status == "failed":
        return f"worker:{name}:failed"
    return None


def _worker_status_payload(worker: Any) -> dict[str, Any]:
    payload = worker.status_payload()
    if not isinstance(payload, Mapping):
        raise TypeError("worker_status_payload_must_be_dict")
    return dict(payload)


def _worker_hard_timed_out(payload: Mapping[str, Any]) -> bool:
    hard_timed_out_at_ms = payload.get("active_run_once_hard_timed_out_at_ms")
    if hard_timed_out_at_ms is not None:
        return True
    last_error = payload.get("last_error")
    return isinstance(last_error, str) and last_error.startswith("WorkerRunHardTimeout")


def _worker_task_items(
    tasks: Mapping[str, asyncio.Task[None]],
    name: str,
) -> list[tuple[str, asyncio.Task[None]]]:
    direct = tasks.get(name)
    return [(name, direct)] if direct is not None else []


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except asyncio.CancelledError:
        return
