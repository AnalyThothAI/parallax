from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.worker_scheduler import WorkerScheduler


class FakeDB:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.closed = 0
        self.fail_close = fail_close

    async def aclose(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("db close failed")


class FakeWorker:
    def __init__(
        self,
        name: str,
        *,
        effective_status: str = "stopped",
        fail_run: bool = False,
        fail_stop: bool = False,
        fail_close: bool = False,
        fail_task_exit: bool = False,
    ) -> None:
        self.name = name
        self.settings = SimpleNamespace(enabled=effective_status != "disabled", concurrency=3)
        self._effective_status = effective_status
        self.fail_run = fail_run
        self.fail_stop = fail_stop
        self.fail_close = fail_close
        self.fail_task_exit = fail_task_exit
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.stop_requested = asyncio.Event()
        self.run_order: list[str] | None = None
        self.started_count = 0
        self.stopped = 0
        self.closed = 0
        self.last_error: str | None = None
        self.last_result: dict[str, Any] | None = None

    async def run(self) -> None:
        self.started_count += 1
        if self.run_order is not None:
            self.run_order.append(self.name)
        self.started.set()
        if self.fail_run:
            self.last_error = "run failed"
            raise RuntimeError("run failed")
        await self.stop_requested.wait()
        await self.release.wait()
        if self.fail_task_exit:
            raise RuntimeError(f"{self.name} task exit failed")

    async def stop(self) -> None:
        self.stopped += 1
        self.stop_requested.set()
        if self.fail_stop:
            self.release.set()
            raise RuntimeError(f"{self.name} stop failed")

    async def aclose(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise RuntimeError(f"{self.name} close failed")

    def status_payload(self) -> dict[str, Any]:
        running = self.started.is_set() and not self.stop_requested.is_set()
        status = self._effective_status
        if status == "stopped" and running:
            status = "running"
        return {
            "enabled": self.settings.enabled,
            "running": running,
            "effective_status": status,
            "unavailable_reason": "missing_provider" if status == "unavailable" else None,
            "last_result": self.last_result,
            "last_error": self.last_error,
        }


async def _finish_scheduler(scheduler: WorkerScheduler) -> None:
    stop_task = asyncio.create_task(scheduler.stop())
    await asyncio.gather(*(worker.stop_requested.wait() for worker in scheduler.workers.values()))
    for worker in scheduler.workers.values():
        worker.release.set()
    await stop_task


def test_scheduler_starts_one_task_per_enabled_worker_in_priority_order() -> None:
    async def scenario() -> None:
        run_order: list[str] = []
        workers = {
            "notification_delivery": FakeWorker("notification_delivery"),
            "collector": FakeWorker("collector"),
            "market_tick_poll": FakeWorker("market_tick_poll"),
        }
        for worker in workers.values():
            worker.run_order = run_order
        scheduler = WorkerScheduler(workers=workers, db=FakeDB())

        await scheduler.start()
        await asyncio.gather(*(worker.started.wait() for worker in workers.values()))

        assert run_order == ["collector", "market_tick_poll", "notification_delivery"]
        assert [task.get_name() for task in scheduler.tasks.values()] == [
            "worker:collector",
            "worker:market_tick_poll",
            "worker:notification_delivery",
        ]
        assert all(worker.started_count == 1 for worker in workers.values())
        await _finish_scheduler(scheduler)

    asyncio.run(scenario())


def test_scheduler_does_not_start_inactive_worker() -> None:
    async def scenario() -> None:
        disabled = FakeWorker("collector", effective_status="disabled")
        unavailable = FakeWorker("market_tick_stream", effective_status="unavailable")
        scheduler = WorkerScheduler(workers={"collector": disabled, "market_tick_stream": unavailable}, db=FakeDB())

        await scheduler.start()

        assert scheduler.tasks == {}
        assert disabled.started_count == 0
        assert unavailable.started_count == 0
        await scheduler.stop()

    asyncio.run(scenario())


def test_scheduler_rejects_repeated_start_without_losing_task() -> None:
    async def scenario() -> None:
        worker = FakeWorker("collector")
        scheduler = WorkerScheduler(workers={"collector": worker}, db=FakeDB())
        await scheduler.start()
        await worker.started.wait()
        task = scheduler.tasks["collector"]

        with pytest.raises(RuntimeError, match="already_started"):
            await scheduler.start()

        assert scheduler.tasks["collector"] is task
        await _finish_scheduler(scheduler)

    asyncio.run(scenario())


def test_scheduler_start_failure_stops_started_workers_without_cancelling_tasks() -> None:
    async def scenario() -> None:
        first = FakeWorker("collector", fail_run=True)
        second = FakeWorker("market_tick_poll")
        scheduler = WorkerScheduler(workers={"collector": first, "market_tick_poll": second}, db=FakeDB())

        with pytest.raises(RuntimeError, match="run failed"):
            await scheduler.start()

        assert scheduler.tasks == {}
        assert scheduler._started is False
        assert second.started_count == 0

    asyncio.run(scenario())


def test_stop_waits_for_current_iteration_before_closing_workers_and_db() -> None:
    async def scenario() -> None:
        worker = FakeWorker("collector")
        db = FakeDB()
        scheduler = WorkerScheduler(workers={"collector": worker}, db=db)
        await scheduler.start()
        await worker.started.wait()

        stop_task = asyncio.create_task(scheduler.stop())
        await worker.stop_requested.wait()
        await asyncio.sleep(0)
        assert not stop_task.done()
        assert not scheduler.tasks["collector"].cancelled()
        assert worker.closed == 0
        assert db.closed == 0

        worker.release.set()
        await stop_task

        assert worker.closed == 1
        assert db.closed == 1
        assert scheduler.tasks["collector"].done()
        assert not scheduler.tasks["collector"].cancelled()

    asyncio.run(scenario())


def test_stop_collects_lifecycle_errors_after_other_cleanup() -> None:
    async def scenario() -> None:
        failing = FakeWorker("collector", fail_stop=True, fail_close=True)
        other = FakeWorker("market_tick_poll")
        db = FakeDB(fail_close=True)
        scheduler = WorkerScheduler(workers={"collector": failing, "market_tick_poll": other}, db=db)
        await scheduler.start()
        await asyncio.gather(failing.started.wait(), other.started.wait())
        other.release.set()

        with pytest.raises(ExceptionGroup, match="worker_scheduler_stop_failed") as excinfo:
            await scheduler.stop()

        messages = {str(error) for error in excinfo.value.exceptions}
        assert messages == {"collector stop failed", "collector close failed", "db close failed"}
        assert other.closed == 1

    asyncio.run(scenario())


def test_stop_reports_worker_task_exit_error_after_cleanup() -> None:
    async def scenario() -> None:
        worker = FakeWorker("collector", fail_task_exit=True)
        db = FakeDB()
        scheduler = WorkerScheduler(workers={"collector": worker}, db=db)
        await scheduler.start()
        await worker.started.wait()

        stop_task = asyncio.create_task(scheduler.stop())
        await worker.stop_requested.wait()
        worker.release.set()
        with pytest.raises(ExceptionGroup, match="worker_scheduler_stop_failed") as excinfo:
            await stop_task

        assert [str(error) for error in excinfo.value.exceptions] == ["collector task exit failed"]
        assert worker.closed == 1
        assert db.closed == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("worker", "exception_type", "match"),
    [
        (SimpleNamespace(), AttributeError, "status_payload"),
        (
            SimpleNamespace(status_payload=lambda: (_ for _ in ()).throw(RuntimeError("status failed"))),
            RuntimeError,
            "status failed",
        ),
        (SimpleNamespace(status_payload=lambda: []), TypeError, "worker_status_payload_must_be_dict"),
    ],
)
def test_scheduler_requires_typed_status_payload(worker: object, exception_type: type[Exception], match: str) -> None:
    scheduler = WorkerScheduler(workers={"collector": worker}, db=FakeDB())
    with pytest.raises(exception_type, match=match):
        scheduler.status_payload()


def test_status_payload_preserves_formal_worker_state() -> None:
    failed = FakeWorker("token_radar_projection", effective_status="failed")
    failed.last_error = "database failed"
    unavailable = FakeWorker("market_tick_stream", effective_status="unavailable")
    disabled = FakeWorker("collector", effective_status="disabled")
    scheduler = WorkerScheduler(
        workers={
            "token_radar_projection": failed,
            "market_tick_stream": unavailable,
            "collector": disabled,
        },
        db=FakeDB(),
    )

    payload = scheduler.status_payload()

    assert payload["token_radar_projection"]["last_error"] == "database failed"
    assert payload["token_radar_projection"]["effective_status"] == "failed"
    assert payload["market_tick_stream"]["effective_status"] == "unavailable"
    assert payload["market_tick_stream"]["unavailable_reason"] == "missing_provider"
    assert payload["collector"]["effective_status"] == "disabled"
