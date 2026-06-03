from __future__ import annotations

import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger as default_logger

from parallax.app.runtime.worker_result import WorkerResult
from parallax.app.runtime.worker_space import WorkerSpaceContract
from parallax.platform.cancellation import WORKER_HARD_TIMEOUT_CANCEL_REASON

_DEFAULT_INTERVAL_SECONDS = 5.0
_DEFAULT_BACKOFF_BASE_MS = 1000
_DEFAULT_BACKOFF_MAX_MS = 60_000
_MIN_WAIT_SECONDS = 0.001
_MAX_DURATION_SAMPLES = 256


@dataclass(slots=True)
class WorkerStatus:
    enabled: bool
    running: bool
    effective_status: str
    unavailable_reason: str | None
    last_started_at_ms: int | None
    last_finished_at_ms: int | None
    last_result: dict[str, Any] | None
    last_error: str | None
    iteration_duration_p99_ms: float | None
    queue_depth: int | None
    pool_wait_ms_p99: float | None
    active_run_once_started_at_ms: int | None
    active_run_once_age_ms: int | None
    active_run_once_soft_timed_out_at_ms: int | None
    active_run_once_hard_timed_out_at_ms: int | None
    active_run_once_count: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)


class WorkerRunSoftTimeout(TimeoutError):
    def __init__(self, message: str, *, first_report: bool) -> None:
        super().__init__(message)
        self.first_report = bool(first_report)


class WorkerRunHardTimeout(TimeoutError):
    pass


class WorkerBase(ABC):
    SINGLE_WRITER_KEY: int | None = None

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        llm: Any | None = None,
        wake_waiter: Any | None = None,
        job_queue: Any | None = None,
        logger: Any | None = None,
        worker_space_contract: WorkerSpaceContract | None = None,
    ) -> None:
        self.name = str(name)
        self.settings = settings
        self.db = db
        self.telemetry = telemetry
        self.llm = llm
        self.wake_waiter = wake_waiter
        self.job_queue = job_queue
        self.logger = logger or default_logger.bind(worker=self.name)
        self.worker_space_contract = worker_space_contract

        self.last_started_at_ms: int | None = None
        self.last_finished_at_ms: int | None = None
        self.last_result: WorkerResult | None = None
        self.last_error: str | None = None
        self.running = False
        self.active_run_once_started_at_ms: int | None = None
        self.active_run_once_soft_timed_out_at_ms: int | None = None
        self.active_run_once_hard_timed_out_at_ms: int | None = None

        self._stop_event = asyncio.Event()
        self._advisory_lock_connection: Any | None = None
        self._iteration_duration_ms: list[float] = []
        self._pool_wait_ms: list[float] = []
        self._consecutive_failures = 0
        self._closed = False
        self._run_once_tasks: set[asyncio.Task[WorkerResult | None]] = set()
        self._run_once_started_at_ms_by_id: dict[int, int] = {}
        self._soft_timeout_reported_for_task: set[int] = set()
        self._active_run_loops = 0

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        return None

    async def on_close(self) -> None:
        return None

    @abstractmethod
    async def run_once(self) -> WorkerResult:
        raise NotImplementedError

    def _runtime_context(self) -> Any:
        from parallax.app.runtime.runtime_worker_context import RuntimeWorkerContext
        from parallax.app.runtime.worker_space import WorkerSpace

        contract = self.worker_space_contract
        if contract is None:
            raise RuntimeError(f"worker:{self.name}:missing WorkerSpace contract")
        return RuntimeWorkerContext(
            worker_name=self.name,
            db=self.db,
            space=WorkerSpace(contract),
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    async def run(self) -> None:
        if not self.enabled:
            return
        if self._active_run_loops > 0:
            raise RuntimeError(f"worker:{self.name}:already_running")
        run_once_task: asyncio.Task[WorkerResult | None] | None = None
        self._active_run_loops = 1
        self.running = True
        try:
            await self.on_start()
            while not self._stop_event.is_set() or run_once_task is not None:
                if not await self._ensure_advisory_lock():
                    await self._wait_for_next_iteration(self.interval_seconds)
                    continue
                started = time.perf_counter()
                if run_once_task is None:
                    run_once_task = self._create_run_once_task()
                try:
                    result, run_once_task = await self._run_once_with_timeout(run_once_task)
                except asyncio.CancelledError:
                    await self._cancel_run_once_task(run_once_task)
                    run_once_task = None
                    raise
                except WorkerRunSoftTimeout as exc:
                    self.last_error = _error_text(exc)
                    self.last_result = None
                    if exc.first_report:
                        self._consecutive_failures += 1
                        self._record_failed_iteration(started)
                    await self._wait_for_next_iteration(self._backoff_seconds())
                    continue
                except Exception as exc:
                    if run_once_task is not None and run_once_task.done():
                        self._discard_run_once_task(run_once_task)
                        run_once_task = None
                    self._consecutive_failures += 1
                    self.last_error = _error_text(exc)
                    self.last_result = None
                    self._record_failed_iteration(started)
                    await self._wait_for_next_iteration(self._backoff_seconds())
                    continue

                self._consecutive_failures = 0
                self.last_error = None
                self.last_result = result
                self._record_successful_iteration(started, result)
                if self._stop_event.is_set():
                    break
                await self._wait_for_next_iteration(self.interval_seconds)
        finally:
            await self._cancel_run_once_task(run_once_task)
            self._active_run_loops = 0
            self.running = False
            await self.on_stop()

    async def stop(self) -> None:
        self._stop_event.set()
        wake = getattr(self.wake_waiter, "wake", None)
        if wake is not None:
            wake()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._cancel_all_run_once_tasks()
            await self.on_close()
        finally:
            self._release_advisory_lock()
            await self._close_wake_waiter()

    def status_payload(self) -> dict[str, Any]:
        return WorkerStatus(
            enabled=self.enabled,
            running=self.running,
            effective_status=self.effective_status,
            unavailable_reason=self.unavailable_reason,
            last_started_at_ms=self.last_started_at_ms,
            last_finished_at_ms=self.last_finished_at_ms,
            last_result=_worker_result_payload(self.last_result),
            last_error=self.last_error,
            iteration_duration_p99_ms=_p99(self._iteration_duration_ms),
            queue_depth=self._queue_depth(),
            pool_wait_ms_p99=self._pool_wait_ms_p99(),
            active_run_once_started_at_ms=self.active_run_once_started_at_ms,
            active_run_once_age_ms=self._active_run_once_age_ms(),
            active_run_once_soft_timed_out_at_ms=self.active_run_once_soft_timed_out_at_ms,
            active_run_once_hard_timed_out_at_ms=self.active_run_once_hard_timed_out_at_ms,
            active_run_once_count=len(self._run_once_tasks),
        ).payload()

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "enabled", True))

    @property
    def effective_status(self) -> str:
        explicit = getattr(self, "_effective_status", None)
        if explicit is not None:
            return str(explicit)
        if not self.enabled:
            return "disabled"
        if self.last_error or _worker_result_failed(self.last_result):
            return "failed"
        if self.running:
            return "running"
        return "stopped"

    @property
    def unavailable_reason(self) -> str | None:
        reason = getattr(self, "_unavailable_reason", None)
        return str(reason) if reason else None

    @property
    def interval_seconds(self) -> float:
        return max(0.0, float(getattr(self.settings, "interval_seconds", _DEFAULT_INTERVAL_SECONDS)))

    @property
    def soft_timeout_seconds(self) -> float:
        return max(0.0, float(self.settings.soft_timeout_seconds))

    @property
    def hard_timeout_seconds(self) -> float:
        return max(0.0, float(self.settings.hard_timeout_seconds))

    async def _run_once_with_timeout(
        self,
        task: asyncio.Task[WorkerResult | None] | None,
    ) -> tuple[WorkerResult, asyncio.Task[WorkerResult | None] | None]:
        if task is None:
            task = self._create_run_once_task()
        await self._cancel_if_hard_timed_out(task)
        timeout = self._next_run_once_wait_seconds(task)
        if timeout is None:
            try:
                result = await task
            except BaseException:
                self._discard_run_once_task(task)
                raise
        else:
            try:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except TimeoutError as exc:
                await self._cancel_if_hard_timed_out(task)
                raise self._soft_timeout_for_task(task) from exc
            except asyncio.CancelledError:
                raise
            except BaseException:
                self._discard_run_once_task(task)
                raise
        self._discard_run_once_task(task)
        if result is None:
            return WorkerResult(processed=1), None
        if not isinstance(result, WorkerResult):
            raise TypeError(f"worker:{self.name}:run_once returned {type(result).__name__}")
        return result, None

    def _create_run_once_task(self) -> asyncio.Task[WorkerResult | None]:
        started_at_ms = _now_ms()
        self.last_started_at_ms = started_at_ms
        self.active_run_once_started_at_ms = started_at_ms
        self.active_run_once_soft_timed_out_at_ms = None
        self.active_run_once_hard_timed_out_at_ms = None
        task = asyncio.create_task(self.run_once(), name=f"worker:{self.name}:run_once")
        self._run_once_tasks.add(task)
        self._run_once_started_at_ms_by_id[id(task)] = started_at_ms
        self._set_in_flight(len(self._run_once_tasks))
        return task

    async def _cancel_run_once_task(
        self,
        task: asyncio.Task[WorkerResult | None] | None,
        *,
        cancel_reason: str | None = None,
    ) -> None:
        if task is None:
            return
        if not task.done():
            task.cancel(cancel_reason)
        await asyncio.gather(task, return_exceptions=True)
        self._discard_run_once_task(task)

    async def _cancel_all_run_once_tasks(self) -> None:
        tasks = list(self._run_once_tasks)
        if not tasks:
            return
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for task in tasks:
            self._discard_run_once_task(task)

    def _discard_run_once_task(self, task: asyncio.Task[WorkerResult | None]) -> None:
        self._run_once_tasks.discard(task)
        task_id = id(task)
        self._run_once_started_at_ms_by_id.pop(task_id, None)
        self._soft_timeout_reported_for_task.discard(task_id)
        if not self._run_once_tasks:
            self.active_run_once_started_at_ms = None
            self.active_run_once_soft_timed_out_at_ms = None
            self.active_run_once_hard_timed_out_at_ms = None
        elif self._run_once_started_at_ms_by_id:
            self.active_run_once_started_at_ms = min(self._run_once_started_at_ms_by_id.values())
        self._set_in_flight(len(self._run_once_tasks))

    async def _cancel_if_hard_timed_out(self, task: asyncio.Task[WorkerResult | None]) -> None:
        hard_timeout = self.hard_timeout_seconds
        if hard_timeout <= 0:
            return
        started_at_ms = self._run_once_started_at_ms_by_id.get(id(task), self.active_run_once_started_at_ms)
        if started_at_ms is None:
            return
        age_seconds = max(0.0, (_now_ms() - started_at_ms) / 1000)
        if age_seconds < hard_timeout:
            return
        self.active_run_once_hard_timed_out_at_ms = _now_ms()
        await self._cancel_run_once_task(task, cancel_reason=WORKER_HARD_TIMEOUT_CANCEL_REASON)
        raise WorkerRunHardTimeout(f"worker:{self.name}:run_once hard timeout after {hard_timeout:g}s")

    def _next_run_once_wait_seconds(self, task: asyncio.Task[WorkerResult | None]) -> float | None:
        started_at_ms = self._run_once_started_at_ms_by_id.get(id(task), self.active_run_once_started_at_ms)
        if started_at_ms is None:
            return self.soft_timeout_seconds or None
        age_seconds = max(0.0, (_now_ms() - started_at_ms) / 1000)
        waits: list[float] = []
        hard_timeout = self.hard_timeout_seconds
        if hard_timeout > 0:
            waits.append(max(_MIN_WAIT_SECONDS, hard_timeout - age_seconds))
        soft_timeout = self.soft_timeout_seconds
        if soft_timeout > 0 and id(task) not in self._soft_timeout_reported_for_task:
            waits.append(max(_MIN_WAIT_SECONDS, soft_timeout - age_seconds))
        if not waits:
            return None
        return max(_MIN_WAIT_SECONDS, min(waits))

    def _soft_timeout_for_task(self, task: asyncio.Task[WorkerResult | None]) -> WorkerRunSoftTimeout:
        task_id = id(task)
        first_report = task_id not in self._soft_timeout_reported_for_task
        if first_report:
            self._soft_timeout_reported_for_task.add(task_id)
            self.active_run_once_soft_timed_out_at_ms = _now_ms()
        return WorkerRunSoftTimeout(
            f"worker:{self.name}:run_once soft timeout after {self.soft_timeout_seconds:g}s",
            first_report=first_report,
        )

    async def _ensure_advisory_lock(self) -> bool:
        key = self._advisory_lock_key()
        if key is None or self._advisory_lock_connection is not None:
            return True
        try:
            self._advisory_lock_connection = self.db.acquire_advisory_lock_connection(self.name, int(key))
        except Exception as exc:
            if "advisory_lock_unavailable" not in str(exc):
                raise
            self.last_error = None
            self.last_result = WorkerResult(skipped=1, notes={"reason": "advisory_lock_unavailable"})
            self.last_started_at_ms = _now_ms()
            self.last_finished_at_ms = self.last_started_at_ms
            self._record_result_metrics(self.last_result)
            return False
        return True

    def _advisory_lock_key(self) -> int | None:
        settings_key = getattr(self.settings, "advisory_lock_key", None)
        if settings_key is not None:
            return int(settings_key)
        if self.SINGLE_WRITER_KEY is not None:
            return int(self.SINGLE_WRITER_KEY)
        return None

    async def _wait_for_next_iteration(self, timeout: float) -> None:  # noqa: ASYNC109 - worker waits use wake hints.
        if self._stop_event.is_set():
            return
        timeout = _loop_wait_seconds(timeout)
        if self.wake_waiter is not None and hasattr(self.wake_waiter, "async_wait"):
            await self.wake_waiter.async_wait(timeout)
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
        except TimeoutError:
            return

    def _record_successful_iteration(self, started: float, result: WorkerResult) -> None:
        self.last_finished_at_ms = _now_ms()
        duration_seconds = max(0.0, time.perf_counter() - started)
        self._record_duration(duration_seconds * 1000)
        self._call_telemetry("record_processing_seconds", self.name, duration_seconds)
        self._call_telemetry("mark_last_run", self.name)
        self._record_result_metrics(result)

    def _record_failed_iteration(self, started: float) -> None:
        self.last_finished_at_ms = _now_ms()
        duration_seconds = max(0.0, time.perf_counter() - started)
        self._record_duration(duration_seconds * 1000)
        self._call_telemetry("record_processing_seconds", self.name, duration_seconds)
        self._call_telemetry("mark_last_run", self.name)
        self._call_telemetry("record_job", self.name, "failed", 1)

    def _record_result_metrics(self, result: WorkerResult) -> None:
        counts = {
            "success": result.processed,
            "failed": result.failed,
            "dead": result.dead,
            "skipped": result.skipped,
        }
        if sum(counts.values()) == 0:
            counts["success"] = 1
        for status, count in counts.items():
            if count:
                self._call_telemetry("record_job", self.name, status, count)

    def _set_in_flight(self, count: int) -> None:
        self._call_telemetry("set_jobs_in_flight", self.name, count)

    def _call_telemetry(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        method = getattr(self.telemetry, method_name, None)
        if method is not None:
            method(*args, **kwargs)

    def _record_duration(self, duration_ms: float) -> None:
        self._iteration_duration_ms.append(max(0.0, float(duration_ms)))
        del self._iteration_duration_ms[:-_MAX_DURATION_SAMPLES]

    def _backoff_seconds(self) -> float:
        backoff = getattr(self.settings, "backoff", None)
        base_ms = int(getattr(backoff, "base_ms", _DEFAULT_BACKOFF_BASE_MS))
        max_ms = int(getattr(backoff, "max_ms", _DEFAULT_BACKOFF_MAX_MS))
        delay_ms = min(max(0, max_ms), max(0, base_ms) * max(1, self._consecutive_failures))
        return _loop_wait_seconds(delay_ms / 1000)

    def _queue_depth(self) -> int | None:
        depth = getattr(self.job_queue, "depth", None)
        if depth is None:
            return None
        if isinstance(depth, int):
            return max(0, depth)
        if callable(depth):
            try:
                return max(0, int(depth()))
            except Exception:
                return None
        return None

    def _pool_wait_ms_p99(self) -> float | None:
        pool_wait_p99_ms = getattr(self.telemetry, "pool_wait_p99_ms", None)
        if pool_wait_p99_ms is not None:
            return pool_wait_p99_ms("worker")
        return _p99(self._pool_wait_ms)

    def _active_run_once_age_ms(self) -> int | None:
        if self.active_run_once_started_at_ms is None:
            return None
        return max(0, _now_ms() - self.active_run_once_started_at_ms)

    def _release_advisory_lock(self) -> None:
        if self._advisory_lock_connection is None:
            return
        release = getattr(self._advisory_lock_connection, "release", None)
        close = getattr(self._advisory_lock_connection, "close", None)
        releaser: Callable[[], Any] | None = release or close
        try:
            if releaser is not None:
                releaser()
        finally:
            self._advisory_lock_connection = None

    async def _close_wake_waiter(self) -> None:
        close = getattr(self.wake_waiter, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result


def _worker_result_payload(result: WorkerResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "processed": int(result.processed),
        "failed": int(result.failed),
        "dead": int(result.dead),
        "skipped": int(result.skipped),
        "notes": _compact_status_notes(result.notes),
    }


def _worker_result_failed(result: WorkerResult | None) -> bool:
    return result is not None and (int(result.failed) > 0 or int(result.dead) > 0)


def _compact_status_notes(notes: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _compact_status_value(value) for key, value in dict(notes).items()}


def _compact_status_value(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:500]
    if depth >= 2:
        return _compact_leaf(value)
    if isinstance(value, dict):
        items = list(value.items())[:20]
        compact = {str(key): _compact_status_value(item, depth=depth + 1) for key, item in items}
        if len(value) > 20:
            compact["_truncated"] = len(value) - 20
        return compact
    if isinstance(value, list | tuple):
        compact_list = [_compact_status_value(item, depth=depth + 1) for item in list(value)[:20]]
        if len(value) > 20:
            compact_list.append({"_truncated": len(value) - 20})
        return compact_list
    return _compact_leaf(value)


def _compact_leaf(value: Any) -> Any:
    text = str(value)
    return text[:500]


def _p99(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.99) - 1))
    return ordered[index]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _loop_wait_seconds(seconds: float) -> float:
    return max(_MIN_WAIT_SECONDS, float(seconds))


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
