from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.worker_scheduler import WorkerScheduler


class FakePool:
    def __init__(self) -> None:
        self.closed = False
        self.aclosed = False

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.aclosed = True


class FakeDB:
    def __init__(self) -> None:
        self.api_pool = FakePool()
        self.worker_pool = FakePool()
        self.wake_pool = FakePool()


class FakeWorker:
    def __init__(
        self,
        name: str,
        *,
        enabled: bool = True,
        fail_run: bool = False,
        never_stop: bool = False,
        exit_immediately: bool = False,
        fail_stop: bool = False,
        fail_close: bool = False,
    ) -> None:
        self.name = name
        self.settings = SimpleNamespace(enabled=enabled)
        self.fail_run = fail_run
        self.never_stop = never_stop
        self.exit_immediately = exit_immediately
        self.fail_stop = fail_stop
        self.fail_close = fail_close
        self.started_event = asyncio.Event()
        self.started_count = 0
        self.stop_event = asyncio.Event()
        self.stopped = 0
        self.closed = 0
        self.run_order: list[str] | None = None
        self.last_error: str | None = None

    async def run(self) -> None:
        if self.run_order is not None:
            self.run_order.append(self.name)
        self.started_count += 1
        self.started_event.set()
        if self.fail_run:
            self.last_error = "run failed"
            raise RuntimeError("run failed")
        if self.exit_immediately:
            return
        if self.never_stop:
            await asyncio.Event().wait()
        await self.stop_event.wait()

    async def stop(self) -> None:
        self.stopped += 1
        if self.fail_stop:
            raise RuntimeError(f"{self.name} stop failed")
        if not self.never_stop:
            self.stop_event.set()

    async def aclose(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise RuntimeError(f"{self.name} close failed")

    def status_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.enabled,
            "running": self.started_event.is_set() and not self.stop_event.is_set(),
            "last_error": self.last_error,
        }


def test_scheduler_starts_enabled_workers_in_dependency_order_with_task_names() -> None:
    async def scenario() -> None:
        run_order: list[str] = []
        workers = {
            "collector": FakeWorker("collector"),
            "token_capture_tier": FakeWorker("token_capture_tier"),
            "market_tick_stream": FakeWorker("market_tick_stream"),
            "market_tick_poll": FakeWorker("market_tick_poll"),
            "resolution_refresh": FakeWorker("resolution_refresh"),
            "asset_profile_refresh": FakeWorker("asset_profile_refresh"),
            "enrichment": FakeWorker("enrichment"),
            "handle_summary": FakeWorker("handle_summary"),
            "harness_ops": FakeWorker("harness_ops"),
            "pulse_candidate": FakeWorker("pulse_candidate"),
            "token_radar_projection": FakeWorker("token_radar_projection"),
            "notification_rule": FakeWorker("notification_rule"),
            "notification_delivery": FakeWorker("notification_delivery"),
            "live_price_gateway": FakeWorker("live_price_gateway"),
        }
        for worker in workers.values():
            worker.run_order = run_order
        scheduler = WorkerScheduler(workers=workers, db=FakeDB(), stop_timeout_seconds=0.1)

        await scheduler.start()
        await asyncio.gather(*(worker.started_event.wait() for worker in workers.values()))

        assert run_order == [
            "collector",
            "token_capture_tier",
            "market_tick_stream",
            "market_tick_poll",
            "live_price_gateway",
            "resolution_refresh",
            "asset_profile_refresh",
            "token_radar_projection",
            "pulse_candidate",
            "enrichment",
            "handle_summary",
            "harness_ops",
            "notification_rule",
            "notification_delivery",
        ]
        assert [task.get_name() for task in scheduler.tasks.values()] == [
            "worker:collector",
            "worker:token_capture_tier",
            "worker:market_tick_stream",
            "worker:market_tick_poll",
            "worker:live_price_gateway",
            "worker:resolution_refresh",
            "worker:asset_profile_refresh",
            "worker:token_radar_projection",
            "worker:pulse_candidate",
            "worker:enrichment",
            "worker:handle_summary",
            "worker:harness_ops",
            "worker:notification_rule",
            "worker:notification_delivery",
        ]
        await scheduler.stop()

    asyncio.run(scenario())


def test_scheduler_starts_configured_enrichment_concurrency_with_canonical_status_key() -> None:
    async def scenario() -> None:
        worker = FakeWorker("enrichment")
        worker.settings.concurrency = 3
        scheduler = WorkerScheduler(workers={"enrichment": worker}, db=FakeDB(), stop_timeout_seconds=0.1)

        await scheduler.start()
        await worker.started_event.wait()
        await asyncio.sleep(0)

        assert worker.started_count == 3
        assert set(scheduler.tasks) == {"enrichment#0", "enrichment#1", "enrichment#2"}
        assert {task.get_name() for task in scheduler.tasks.values()} == {
            "worker:enrichment#0",
            "worker:enrichment#1",
            "worker:enrichment#2",
        }
        assert set(scheduler.status_payload()) == {"enrichment"}

        await scheduler.stop()

        assert worker.stopped == 1
        assert worker.closed == 1

    asyncio.run(scenario())


def test_scheduler_keeps_disabled_workers_in_status_without_starting_them() -> None:
    async def scenario() -> None:
        enabled = FakeWorker("market_tick_stream")
        disabled = FakeWorker("collector", enabled=False)
        scheduler = WorkerScheduler(
            workers={"collector": disabled, "market_tick_stream": enabled},
            db=FakeDB(),
            stop_timeout_seconds=0.1,
        )

        await scheduler.start()
        await enabled.started_event.wait()

        assert list(scheduler.tasks) == ["market_tick_stream"]
        assert disabled.started_event.is_set() is False
        assert scheduler.status_payload()["collector"]["enabled"] is False
        await scheduler.stop()

    asyncio.run(scenario())


def test_scheduler_stop_stops_workers_cancels_stubborn_tasks_closes_workers_then_db_pools() -> None:
    async def scenario() -> None:
        db = FakeDB()
        worker = FakeWorker("collector", never_stop=True)
        scheduler = WorkerScheduler(workers={"collector": worker}, db=db, stop_timeout_seconds=0.01)

        await scheduler.start()
        await worker.started_event.wait()
        await scheduler.stop()

        assert worker.stopped == 1
        assert worker.closed == 1
        assert db.api_pool.aclosed is True
        assert db.worker_pool.aclosed is True
        assert db.wake_pool.aclosed is True
        assert all(task.cancelled() for task in scheduler.tasks.values())

    asyncio.run(scenario())


def test_scheduler_stop_collects_stop_errors_but_closes_other_workers_and_pools() -> None:
    async def scenario() -> None:
        db = FakeDB()
        failing = FakeWorker("market_tick_poll", fail_stop=True)
        other = FakeWorker("collector")
        scheduler = WorkerScheduler(
            workers={"market_tick_poll": failing, "collector": other},
            db=db,
            stop_timeout_seconds=0.01,
        )

        await scheduler.start()
        await asyncio.gather(failing.started_event.wait(), other.started_event.wait())
        with pytest.raises(ExceptionGroup, match="worker_scheduler_stop_failed") as excinfo:
            await scheduler.stop()

        assert any("market_tick_poll stop failed" in str(error) for error in excinfo.value.exceptions)
        assert failing.stopped == 1
        assert other.stopped == 1
        assert failing.closed == 1
        assert other.closed == 1
        assert db.api_pool.aclosed is True
        assert db.worker_pool.aclosed is True
        assert db.wake_pool.aclosed is True

    asyncio.run(scenario())


def test_scheduler_stop_collects_close_errors_but_closes_other_workers_and_pools() -> None:
    async def scenario() -> None:
        db = FakeDB()
        failing = FakeWorker("market_tick_poll", fail_close=True)
        other = FakeWorker("collector")
        scheduler = WorkerScheduler(
            workers={"market_tick_poll": failing, "collector": other},
            db=db,
            stop_timeout_seconds=0.01,
        )

        await scheduler.start()
        await asyncio.gather(failing.started_event.wait(), other.started_event.wait())
        with pytest.raises(ExceptionGroup, match="worker_scheduler_stop_failed") as excinfo:
            await scheduler.stop()

        assert any("market_tick_poll close failed" in str(error) for error in excinfo.value.exceptions)
        assert failing.stopped == 1
        assert other.stopped == 1
        assert failing.closed == 1
        assert other.closed == 1
        assert db.api_pool.aclosed is True
        assert db.worker_pool.aclosed is True
        assert db.wake_pool.aclosed is True

    asyncio.run(scenario())


def test_scheduler_unhealthy_reasons_reports_enabled_stopped_or_errored_workers_only() -> None:
    async def scenario() -> None:
        healthy = FakeWorker("market_tick_poll")
        stopped = FakeWorker("collector", exit_immediately=True)
        errored = FakeWorker("enrichment", fail_run=True)
        disabled = FakeWorker("pulse_candidate", enabled=False, fail_run=True)
        scheduler = WorkerScheduler(
            workers={
                "market_tick_poll": healthy,
                "collector": stopped,
                "enrichment": errored,
                "pulse_candidate": disabled,
            },
            db=FakeDB(),
            stop_timeout_seconds=0.1,
        )

        await scheduler.start()
        await healthy.started_event.wait()
        await errored.started_event.wait()
        await asyncio.sleep(0)

        reasons = scheduler.unhealthy_reasons()

        assert "worker:collector:stopped" in reasons
        assert "worker:enrichment:errored:run failed" in reasons
        assert not any("pulse_candidate" in reason for reason in reasons)
        await scheduler.stop()

    asyncio.run(scenario())
