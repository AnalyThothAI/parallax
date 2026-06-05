from __future__ import annotations

import asyncio
import inspect
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
        stop_timeout_seconds: float = 30.0,
    ) -> None:
        self.workers = dict(workers)
        self.db = db
        self.stop_timeout_seconds = max(0.0, float(stop_timeout_seconds))
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
                concurrency = _worker_concurrency(name, worker)
                for index in range(concurrency):
                    task_key = name if concurrency == 1 else f"{name}#{index}"
                    self.tasks[task_key] = asyncio.create_task(worker.run(), name=f"worker:{task_key}")
                    await asyncio.sleep(0)
                    task = self.tasks[task_key]
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
                await _maybe_await(worker.stop())
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
                await _maybe_await(worker.aclose())
            except Exception as exc:
                errors.append(exc)
        await self._close_pools(errors)
        self._started = False
        if errors:
            raise ExceptionGroup("worker_scheduler_stop_failed", errors)

    def status_payload(self) -> dict[str, dict[str, Any]]:
        return {name: worker.status_payload() for name, worker in self.workers.items()}

    def unhealthy_reasons(self) -> list[str]:
        reasons: list[str] = []
        for name, worker in self.workers.items():
            effective_status = worker_effective_status(worker)
            if effective_status in {"disabled", "intentionally_not_started"}:
                continue
            if effective_status == "unavailable":
                reasons.append(f"worker:{name}:unavailable:{_worker_unavailable_reason(worker)}")
                continue
            task_items = _worker_task_items(self.tasks, name)
            if not task_items:
                failure_reason = _worker_failure_reason(name, worker, effective_status)
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
            failure_reason = _worker_failure_reason(name, worker, effective_status)
            if failure_reason is not None and not task_failure_emitted:
                reasons.append(failure_reason)
        return reasons

    def _ordered_worker_names(self) -> list[str]:
        return sorted(
            self.workers,
            key=lambda name: (_START_PRIORITY.get(name, 25), name),
        )

    async def _close_pools(self, errors: list[Exception]) -> None:
        close_bundle = getattr(self.db, "aclose", None)
        if close_bundle is not None:
            try:
                await _maybe_await(close_bundle())
            except Exception as exc:
                errors.append(exc)
            return
        for attr in ("api_pool", "worker_pool", "lock_pool", "tool_pool", "wake_pool"):
            pool = getattr(self.db, attr, None)
            if pool is not None:
                try:
                    await _close_resource(pool)
                except Exception as exc:
                    errors.append(exc)


def _worker_enabled(worker: Any) -> bool:
    settings = getattr(worker, "settings", None)
    return bool(getattr(settings, "enabled", True))


def _worker_startable(worker: Any) -> bool:
    return worker_effective_status(worker) not in {"disabled", "intentionally_not_started", "unavailable"}


def worker_effective_status(worker: Any) -> str:
    explicit = getattr(worker, "effective_status", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    payload = _worker_status_payload(worker)
    if payload:
        return effective_worker_status(payload)
    if not _worker_enabled(worker):
        return "disabled"
    if getattr(worker, "last_error", None):
        return "failed"
    if bool(getattr(worker, "running", False)):
        return "running"
    return "stopped"


def _worker_unavailable_reason(worker: Any) -> str:
    reason = getattr(worker, "unavailable_reason", None)
    if isinstance(reason, str) and reason:
        return reason
    payload = _worker_status_payload(worker)
    payload_reason = payload.get("unavailable_reason")
    if isinstance(payload_reason, str) and payload_reason:
        return payload_reason
    return "unavailable"


def _worker_failure_reason(name: str, worker: Any, effective_status: str) -> str | None:
    last_error = getattr(worker, "last_error", None)
    if _worker_hard_timed_out(worker):
        return f"worker:{name}:hard_timeout"
    if last_error:
        return f"worker:{name}:errored:{last_error}"
    if effective_status == "failed":
        return f"worker:{name}:failed"
    return None


def _worker_status_payload(worker: Any) -> dict[str, Any]:
    status_payload = getattr(worker, "status_payload", None)
    if not callable(status_payload):
        return {}
    try:
        payload = status_payload()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _worker_concurrency(name: str, worker: Any) -> int:
    _ = (name, worker)
    return 1


def _worker_hard_timed_out(worker: Any) -> bool:
    hard_timed_out_at_ms = getattr(worker, "active_run_once_hard_timed_out_at_ms", None)
    if hard_timed_out_at_ms is not None:
        return True
    last_error = getattr(worker, "last_error", None)
    return isinstance(last_error, str) and last_error.startswith("WorkerRunHardTimeout")


def _worker_task_items(
    tasks: Mapping[str, asyncio.Task[None]],
    name: str,
) -> list[tuple[str, asyncio.Task[None]]]:
    direct = tasks.get(name)
    if direct is not None:
        return [(name, direct)]
    prefix = f"{name}#"
    return [(task_key, task) for task_key, task in tasks.items() if task_key.startswith(prefix)]


async def _close_resource(resource: Any) -> None:
    aclose = getattr(resource, "aclose", None)
    if aclose is not None:
        await _maybe_await(aclose())
        return
    close = getattr(resource, "close", None)
    if close is not None:
        await _maybe_await(close())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except asyncio.CancelledError:
        return
