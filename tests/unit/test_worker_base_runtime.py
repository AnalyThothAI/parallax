from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


def worker_settings(**overrides: Any) -> SimpleNamespace:
    payload = {
        "enabled": True,
        "interval_seconds": 0.001,
        "backoff": SimpleNamespace(base_ms=0, max_ms=0),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class Telemetry:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str, int]] = []
        self.durations: list[tuple[str, float]] = []

    def record_job(self, worker: str, status: str, count: int) -> None:
        self.jobs.append((worker, status, count))

    def record_processing_seconds(self, worker: str, duration: float) -> None:
        self.durations.append((worker, duration))

    def mark_last_run(self, worker: str) -> None:
        _ = worker


class TestWorker(WorkerBase):
    __test__ = False

    def __init__(self, *, results: list[Any] | None = None, settings: Any | None = None) -> None:
        self.results = list(results or [WorkerResult(processed=1)])
        self.events: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.closed = 0
        super().__init__(
            name="test",
            settings=settings or worker_settings(),
            db=object(),
            telemetry=Telemetry(),
        )

    async def on_start(self) -> None:
        self.events.append("start")

    async def on_stop(self) -> None:
        self.events.append("stop")

    async def on_close(self) -> None:
        self.closed += 1

    async def run_once(self) -> WorkerResult:
        self.events.append("run")
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            value = self.results.pop(0) if self.results else WorkerResult(skipped=1)
            if isinstance(value, BaseException):
                raise value
            if callable(value):
                value = await value()
            return value
        finally:
            self.in_flight -= 1


def test_run_one_iteration_is_sequential_and_records_status() -> None:
    async def scenario() -> None:
        worker = TestWorker(results=[WorkerResult(processed=2, notes={"source": "db"})])

        result = await worker.run_one_iteration()

        assert result.processed == 2
        assert worker.events == ["start", "run", "stop"]
        assert worker.max_in_flight == 1
        assert worker.status_payload() == {
            "enabled": True,
            "running": False,
            "effective_status": "stopped",
            "unavailable_reason": None,
            "last_started_at_ms": worker.last_started_at_ms,
            "last_finished_at_ms": worker.last_finished_at_ms,
            "last_result": {
                "processed": 2,
                "failed": 0,
                "dead": 0,
                "skipped": 0,
                "notes": {"source": "db"},
            },
            "last_error": None,
            "iteration_duration_p99_ms": worker.status_payload()["iteration_duration_p99_ms"],
        }

    asyncio.run(scenario())


def test_run_loop_never_overlaps_iterations() -> None:
    async def scenario() -> None:
        worker = TestWorker(results=[WorkerResult(processed=1)] * 3)
        calls = 0
        original = worker.run_once

        async def run_once() -> WorkerResult:
            nonlocal calls
            calls += 1
            result = await original()
            if calls == 3:
                await worker.stop()
            return result

        worker.run_once = run_once  # type: ignore[method-assign]
        await worker.run()

        assert calls == 3
        assert worker.max_in_flight == 1
        assert worker.events[0] == "start"
        assert worker.events[-1] == "stop"

    asyncio.run(scenario())


def test_stop_interrupts_interval_wait_without_cancelling_business_work() -> None:
    async def scenario() -> None:
        worker = TestWorker(settings=worker_settings(interval_seconds=60))
        task = asyncio.create_task(worker.run())
        while worker.last_finished_at_ms is None:
            await asyncio.sleep(0)

        await worker.stop()
        await asyncio.wait_for(task, timeout=1)

        assert worker.events == ["start", "run", "stop"]

    asyncio.run(scenario())


def test_failure_uses_backoff_then_recovers() -> None:
    async def scenario() -> None:
        worker = TestWorker(results=[RuntimeError("boom"), WorkerResult(processed=1)])
        original = worker.run_once

        async def run_once() -> WorkerResult:
            result = await original()
            await worker.stop()
            return result

        worker.run_once = run_once  # type: ignore[method-assign]
        await worker.run()

        assert worker.last_error is None
        assert worker.last_result == WorkerResult(processed=1)
        assert ("test", "failed", 1) in worker.telemetry.jobs

    asyncio.run(scenario())


def test_concurrent_entry_is_rejected() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocking_result() -> WorkerResult:
            entered.set()
            await release.wait()
            return WorkerResult(processed=1)

        worker = TestWorker(results=[blocking_result])
        task = asyncio.create_task(worker.run())
        await entered.wait()

        with pytest.raises(RuntimeError, match="already_running"):
            await worker.run_one_iteration()
        with pytest.raises(RuntimeError, match="already_running"):
            await worker.run()

        await worker.stop()
        release.set()
        await task

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid_result", [object(), None])
def test_invalid_worker_result_fails_closed(invalid_result: object | None) -> None:
    async def scenario() -> None:
        worker = TestWorker(results=[invalid_result])
        with pytest.raises(TypeError, match=f"run_once returned {type(invalid_result).__name__}"):
            await worker.run_one_iteration()
        assert worker.effective_status == "failed"

    asyncio.run(scenario())


def test_disabled_worker_iteration_is_a_noop() -> None:
    worker = TestWorker(settings=worker_settings(enabled=False))
    result = asyncio.run(worker.run_one_iteration())
    assert result == WorkerResult(skipped=1, notes={"reason": "disabled"})
    assert worker.events == []


def test_status_compacts_large_notes() -> None:
    worker = TestWorker(results=[WorkerResult(processed=1, notes={"text": "x" * 1000, "items": list(range(30))})])
    asyncio.run(worker.run_one_iteration())
    notes = worker.status_payload()["last_result"]["notes"]
    assert len(notes["text"]) == 500
    assert notes["items"][-1] == {"_truncated": 10}


def test_aclose_is_idempotent() -> None:
    async def scenario() -> None:
        worker = TestWorker()
        await worker.aclose()
        await worker.aclose()
        assert worker.closed == 1

    asyncio.run(scenario())
