from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_registry import WORKER_START_PRIORITY

_START_PRIORITY = WORKER_START_PRIORITY

_SCHEDULER_CONCURRENT_WORKERS = {"enrichment"}


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

    async def start(self) -> None:
        for name in self._ordered_worker_names():
            worker = self.workers[name]
            if not _worker_enabled(worker):
                continue
            concurrency = _worker_concurrency(name, worker)
            for index in range(concurrency):
                task_key = name if concurrency == 1 else f"{name}#{index}"
                self.tasks[task_key] = asyncio.create_task(worker.run(), name=f"worker:{task_key}")
                await asyncio.sleep(0)

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
        if errors:
            raise ExceptionGroup("worker_scheduler_stop_failed", errors)

    def status_payload(self) -> dict[str, dict[str, Any]]:
        return {name: worker.status_payload() for name, worker in self.workers.items()}

    def unhealthy_reasons(self) -> list[str]:
        reasons: list[str] = []
        for name, worker in self.workers.items():
            if not _worker_enabled(worker):
                continue
            task_items = _worker_task_items(self.tasks, name)
            if not task_items:
                reasons.append(f"worker:{name}:stopped")
                continue
            for task_key, task in task_items:
                if task.cancelled():
                    reasons.append(f"worker:{task_key}:stopped")
                    continue
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        reasons.append(f"worker:{task_key}:errored:{exc}")
                    else:
                        reasons.append(f"worker:{task_key}:stopped")
                    continue
            last_error = getattr(worker, "last_error", None)
            if last_error:
                reasons.append(f"worker:{name}:errored:{last_error}")
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


def _worker_concurrency(name: str, worker: Any) -> int:
    if name not in _SCHEDULER_CONCURRENT_WORKERS:
        return 1
    settings = getattr(worker, "settings", None)
    return max(1, int(getattr(settings, "concurrency", 1) or 1))


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
