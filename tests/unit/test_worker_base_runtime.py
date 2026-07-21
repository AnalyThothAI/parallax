from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.telemetry import TelemetryRegistry
from parallax.platform.cancellation import WORKER_HARD_TIMEOUT_CANCEL_REASON
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class FakeTelemetry:
    def __init__(self) -> None:
        self.processing_seconds: list[tuple[str, float]] = []
        self.jobs: list[tuple[str, str, int]] = []
        self.in_flight: list[tuple[str, int]] = []
        self.last_runs: list[str] = []

    def record_processing_seconds(self, worker: str, seconds: float) -> None:
        self.processing_seconds.append((worker, seconds))

    def record_job(self, worker: str, status: str, count: int = 1) -> None:
        self.jobs.append((worker, status, count))

    def set_jobs_in_flight(self, worker: str, count: int) -> None:
        self.in_flight.append((worker, count))

    def mark_last_run(self, worker: str, *, timestamp: float | None = None) -> None:
        self.last_runs.append(worker)

    def pool_wait_p99_ms(self, pool: str | None = None) -> float | None:
        if pool == "worker":
            return 12.5
        return None


class FakeWakeWaiter:
    def __init__(self) -> None:
        self.waits: list[float] = []
        self.wake_count = 0
        self.close_count = 0
        self._event = asyncio.Event()

    async def async_wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            return False
        self._event.clear()
        return True

    def wake(self) -> None:
        self.wake_count += 1
        self._event.set()

    def close(self) -> None:
        self.close_count += 1


class AwaitableCloseResult:
    def __init__(self) -> None:
        self.awaited = False

    def __await__(self) -> Any:
        self.awaited = True
        return iter(())


class AwaitableCloseWakeWaiter(FakeWakeWaiter):
    def __init__(self) -> None:
        super().__init__()
        self.close_result = AwaitableCloseResult()

    def close(self) -> AwaitableCloseResult:
        self.close_count += 1
        return self.close_result


class FakeAdvisoryLock:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeDB:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = outcomes or []
        self.acquire_calls: list[tuple[str, int]] = []

    def acquire_advisory_lock_connection(self, worker_name: str, key: int) -> FakeAdvisoryLock:
        self.acquire_calls.append((worker_name, key))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def worker_settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 0.01,
        "hard_timeout_seconds": 0.0,
        "backoff": SimpleNamespace(base_ms=1, max_ms=5),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CountingWorker(WorkerBase):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.started = 0
        self.stopped = 0
        self.closed = 0
        self.calls = 0

    async def on_start(self) -> None:
        self.started += 1

    async def run_once(self) -> WorkerResult:
        self.calls += 1
        await self.stop()
        return WorkerResult(processed=2, failed=1, dead=1, skipped=1)

    async def on_stop(self) -> None:
        self.stopped += 1

    async def on_close(self) -> None:
        self.closed += 1


def test_run_one_iteration_uses_worker_lifecycle_timeout_and_result_accounting() -> None:
    telemetry = FakeTelemetry()
    worker = CountingWorker(
        name="once",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=telemetry,
    )

    result = asyncio.run(worker.run_one_iteration())

    assert result == WorkerResult(processed=2, failed=1, dead=1, skipped=1)
    assert (worker.started, worker.calls, worker.stopped) == (1, 1, 1)
    assert worker.running is False
    assert worker.last_result == result
    assert worker.last_error is None
    assert telemetry.last_runs == ["once"]


def test_run_one_iteration_owns_and_releases_single_writer_lock() -> None:
    lock = FakeAdvisoryLock()
    db = FakeDB([lock])
    worker = CountingWorker(
        name="locked-once",
        settings=worker_settings(advisory_lock_key=2026072101),
        db=db,
        telemetry=FakeTelemetry(),
    )

    asyncio.run(worker.run_one_iteration())

    assert db.acquire_calls == [("locked-once", 2026072101)]
    assert lock.released is True


def test_run_one_iteration_reports_advisory_lock_contention_without_running_business_work() -> None:
    worker = CountingWorker(
        name="contended-once",
        settings=worker_settings(advisory_lock_key=2026072102),
        db=FakeDB([RuntimeError("advisory_lock_unavailable")]),
        telemetry=FakeTelemetry(),
    )

    result = asyncio.run(worker.run_one_iteration())

    assert result == WorkerResult(skipped=1, notes={"reason": "advisory_lock_unavailable"})
    assert worker.calls == 0
    assert (worker.started, worker.stopped) == (1, 1)


def test_worker_base_requires_formal_settings_fields_without_runtime_defaults() -> None:
    worker = CountingWorker(
        name="missing_enabled",
        settings=SimpleNamespace(
            interval_seconds=0.01,
            hard_timeout_seconds=0.0,
            backoff=SimpleNamespace(base_ms=1, max_ms=5),
        ),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )
    with pytest.raises(AttributeError, match="enabled"):
        _ = worker.enabled

    worker = CountingWorker(
        name="missing_interval",
        settings=SimpleNamespace(
            enabled=True,
            hard_timeout_seconds=0.0,
            backoff=SimpleNamespace(base_ms=1, max_ms=5),
        ),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )
    with pytest.raises(AttributeError, match="interval_seconds"):
        _ = worker.interval_seconds

    worker = CountingWorker(
        name="missing_backoff",
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=0.01,
            hard_timeout_seconds=0.0,
        ),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )
    with pytest.raises(AttributeError, match="backoff"):
        worker._backoff_seconds()

    worker = CountingWorker(
        name="missing_backoff_base",
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=0.01,
            hard_timeout_seconds=0.0,
            backoff=SimpleNamespace(max_ms=5),
        ),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )
    with pytest.raises(AttributeError, match="base_ms"):
        worker._backoff_seconds()


@pytest.mark.parametrize(
    ("field", "attribute", "value", "error"),
    [
        ("interval_seconds", "interval_seconds", -0.1, "worker_interval_seconds_required"),
        ("interval_seconds", "interval_seconds", True, "worker_interval_seconds_required"),
        ("interval_seconds", "interval_seconds", "0.01", "worker_interval_seconds_required"),
        ("hard_timeout_seconds", "hard_timeout_seconds", -0.1, "worker_hard_timeout_seconds_required"),
        ("hard_timeout_seconds", "hard_timeout_seconds", True, "worker_hard_timeout_seconds_required"),
        ("hard_timeout_seconds", "hard_timeout_seconds", "0.0", "worker_hard_timeout_seconds_required"),
    ],
)
def test_worker_base_rejects_malformed_timing_settings_without_runtime_repair(
    field: str,
    attribute: str,
    value: Any,
    error: str,
) -> None:
    worker = CountingWorker(
        name="timing_contract",
        settings=worker_settings(**{field: value}),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )

    with pytest.raises(ValueError, match=error):
        getattr(worker, attribute)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("base_ms", -1, "worker_backoff_base_ms_required"),
        ("base_ms", True, "worker_backoff_base_ms_required"),
        ("base_ms", "1", "worker_backoff_base_ms_required"),
        ("max_ms", -1, "worker_backoff_max_ms_required"),
        ("max_ms", True, "worker_backoff_max_ms_required"),
        ("max_ms", "5", "worker_backoff_max_ms_required"),
    ],
)
def test_worker_base_rejects_malformed_backoff_settings_without_runtime_repair(
    field: str,
    value: Any,
    error: str,
) -> None:
    backoff_values = {"base_ms": 1, "max_ms": 5}
    backoff_values[field] = value
    worker = CountingWorker(
        name="backoff_contract",
        settings=worker_settings(backoff=SimpleNamespace(**backoff_values)),
        db=FakeDB(),
        telemetry=FakeTelemetry(),
    )

    with pytest.raises(ValueError, match=error):
        worker._backoff_seconds()


def test_worker_base_run_calls_hooks_updates_status_and_metrics() -> None:
    async def scenario() -> None:
        telemetry = FakeTelemetry()
        waiter = FakeWakeWaiter()
        worker = CountingWorker(
            name="unit_worker",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=telemetry,
            wake_waiter=waiter,
        )

        await worker.run()
        await worker.aclose()

        assert worker.started == 1
        assert worker.stopped == 1
        assert worker.closed == 1
        assert worker.calls == 1
        assert telemetry.in_flight == [("unit_worker", 1), ("unit_worker", 0)]
        assert telemetry.processing_seconds[0][0] == "unit_worker"
        assert telemetry.jobs == [
            ("unit_worker", "success", 2),
            ("unit_worker", "failed", 1),
            ("unit_worker", "dead", 1),
            ("unit_worker", "skipped", 1),
        ]
        assert telemetry.last_runs == ["unit_worker"]
        payload = worker.status_payload()
        assert payload["enabled"] is True
        assert payload["running"] is False
        assert payload["last_started_at_ms"] is not None
        assert payload["last_finished_at_ms"] is not None
        assert payload["last_result"] == {
            "processed": 2,
            "failed": 1,
            "dead": 1,
            "skipped": 1,
            "notes": {},
        }
        assert payload["last_error"] is None
        assert payload["iteration_duration_p99_ms"] >= 0
        assert "queue_depth" not in payload
        assert payload["pool_wait_ms_p99"] == 12.5

    asyncio.run(scenario())


def test_worker_status_payload_maps_degraded_result_notes_to_effective_status() -> None:
    class DegradedWorker(WorkerBase):
        async def run_once(self) -> WorkerResult:
            await self.stop()
            return WorkerResult(processed=1, notes={"degraded": True, "provider_state": "degraded_recoverable"})

    async def scenario() -> None:
        worker = DegradedWorker(
            name="degraded_worker",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
        )

        await worker.run()
        payload = worker.status_payload()

        assert payload["effective_status"] == "degraded"
        assert payload["last_result"]["notes"]["degraded"] is True

    asyncio.run(scenario())


def test_worker_status_payload_failed_result_takes_precedence_over_degraded_notes() -> None:
    class FailedDegradedWorker(WorkerBase):
        async def run_once(self) -> WorkerResult:
            await self.stop()
            return WorkerResult(failed=1, notes={"degraded": True})

    async def scenario() -> None:
        worker = FailedDegradedWorker(
            name="failed_degraded_worker",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
        )

        await worker.run()

        assert worker.status_payload()["effective_status"] == "failed"

    asyncio.run(scenario())


def test_worker_base_rejects_concurrent_run_on_same_instance() -> None:
    class BlockingWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def run_once(self) -> WorkerResult:
            self.entered.set()
            await self.release.wait()
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        worker = BlockingWorker(
            name="blocking_worker",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
        )
        running = asyncio.create_task(worker.run())
        await worker.entered.wait()

        with pytest.raises(RuntimeError, match="worker:blocking_worker:already_running"):
            await worker.run()

        worker.release.set()
        await running
        await worker.aclose()

    asyncio.run(scenario())


def test_worker_base_exception_records_error_without_synthetic_timeout_state() -> None:
    class FlakyWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            if self.calls == 1:
                await asyncio.sleep(0.05)
            await self.stop()
            raise RuntimeError("boom")

    async def scenario() -> None:
        telemetry = FakeTelemetry()
        waiter = FakeWakeWaiter()
        worker = FlakyWorker(
            name="flaky",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=telemetry,
            wake_waiter=waiter,
        )

        await worker.run()

        assert worker.calls == 1
        assert "boom" in (worker.last_error or "")
        assert ("flaky", "failed", 1) in telemetry.jobs
        assert waiter.waits == []

    asyncio.run(scenario())


def test_worker_status_payload_compacts_large_result_notes() -> None:
    class NotesWorker(WorkerBase):
        async def run_once(self) -> WorkerResult:
            self._stop_event.set()
            return WorkerResult(
                processed=1,
                notes={
                    "claimed": 1,
                    "large_text": "x" * 800,
                    "large_list": list(range(25)),
                    "large_dict": {f"k{i}": i for i in range(25)},
                },
            )

    async def scenario() -> None:
        worker = NotesWorker(
            name="notes_worker",
            settings=worker_settings(interval_seconds=0),
            db=None,
            telemetry=FakeTelemetry(),
        )

        await worker.run()
        payload = worker.status_payload()

        notes = payload["last_result"]["notes"]
        assert notes["claimed"] == 1
        assert len(notes["large_text"]) == 500
        assert len(notes["large_list"]) == 21
        assert notes["large_list"][-1] == {"_truncated": 5}
        assert notes["large_dict"]["_truncated"] == 5

    asyncio.run(scenario())


def test_worker_base_success_wait_floors_zero_interval_to_positive_timeout() -> None:
    class TwoIterationWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            if self.calls == 2:
                await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        waiter = FakeWakeWaiter()
        worker = TwoIterationWorker(
            name="zero_interval",
            settings=worker_settings(interval_seconds=0),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=waiter,
        )

        await worker.run()

        assert waiter.waits[0] > 0

    asyncio.run(scenario())


def test_worker_base_failure_backoff_floors_zero_backoff_to_positive_timeout() -> None:
    class FailingThenStoppingWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        waiter = FakeWakeWaiter()
        worker = FailingThenStoppingWorker(
            name="zero_backoff",
            settings=worker_settings(backoff=SimpleNamespace(base_ms=0, max_ms=0)),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=waiter,
        )

        await worker.run()

        assert waiter.waits[0] > 0

    asyncio.run(scenario())


def test_worker_base_on_start_failure_still_calls_on_stop_and_clears_running() -> None:
    class StartFailWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.stopped = 0

        async def on_start(self) -> None:
            raise RuntimeError("start failed")

        async def run_once(self) -> WorkerResult:
            raise AssertionError("run_once should not be called")

        async def on_stop(self) -> None:
            self.stopped += 1

    async def scenario() -> None:
        worker = StartFailWorker(
            name="start_fail",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
        )

        try:
            await worker.run()
        except RuntimeError as exc:
            assert str(exc) == "start failed"
        else:
            raise AssertionError("on_start failure should propagate")

        assert worker.stopped == 1
        assert worker.running is False

    asyncio.run(scenario())


def test_worker_base_advisory_lock_unavailable_skips_until_acquired_and_releases_on_close() -> None:
    class LockedWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        lock = FakeAdvisoryLock()
        db = FakeDB([RuntimeError("advisory_lock_unavailable"), lock])
        telemetry = FakeTelemetry()
        worker = LockedWorker(
            name="locked",
            settings=worker_settings(advisory_lock_key=2026051501),
            db=db,
            telemetry=telemetry,
            wake_waiter=FakeWakeWaiter(),
        )

        await worker.run()
        await worker.aclose()

        assert db.acquire_calls == [("locked", 2026051501), ("locked", 2026051501)]
        assert worker.calls == 1
        assert ("locked", "skipped", 1) in telemetry.jobs
        assert worker.last_result == WorkerResult(processed=1)
        assert lock.released is True

    asyncio.run(scenario())


def test_worker_base_requires_advisory_lock_release_contract() -> None:
    class CloseOnlyLock:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class LockedWorker(WorkerBase):
        async def run_once(self) -> WorkerResult:
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        lock = CloseOnlyLock()
        db = FakeDB([lock])
        worker = LockedWorker(
            name="release_contract",
            settings=worker_settings(advisory_lock_key=2026061301),
            db=db,
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )

        await worker.run()
        with pytest.raises(RuntimeError, match="worker_advisory_lock_release_required"):
            await worker.aclose()

        assert lock.close_calls == 0

    asyncio.run(scenario())


def test_worker_base_uses_formal_advisory_lock_key_instead_of_single_writer_fallback() -> None:
    class ClassLockedWorker(WorkerBase):
        SINGLE_WRITER_KEY = 2026051501

        async def run_once(self) -> WorkerResult:
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        lock = FakeAdvisoryLock()
        db = FakeDB([lock])
        worker = ClassLockedWorker(
            name="class_locked",
            settings=worker_settings(advisory_lock_key=2026061301),
            db=db,
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )

        await worker.run()
        await worker.aclose()

        assert db.acquire_calls == [("class_locked", 2026061301)]
        assert lock.released is True

    asyncio.run(scenario())


def test_worker_base_requires_formal_advisory_lock_key_for_single_writer() -> None:
    class ClassLockedWorker(WorkerBase):
        SINGLE_WRITER_KEY = 2026051501

        async def run_once(self) -> WorkerResult:
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        db = FakeDB([FakeAdvisoryLock()])
        worker = ClassLockedWorker(
            name="class_locked_missing_settings",
            settings=worker_settings(),
            db=db,
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )

        with pytest.raises(RuntimeError, match="worker_advisory_lock_key_required"):
            await worker.run()

        assert db.acquire_calls == []

    asyncio.run(scenario())


def test_worker_base_status_reads_worker_pool_wait_p99_from_telemetry() -> None:
    telemetry = TelemetryRegistry()
    telemetry.record_pool_wait("worker", 5)
    telemetry.record_pool_wait("worker", 15)
    worker = CountingWorker(
        name="pool_wait_status",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=telemetry,
    )

    assert worker.status_payload()["pool_wait_ms_p99"] == 15


def test_worker_base_stop_wakes_waiter() -> None:
    async def scenario() -> None:
        waiter = FakeWakeWaiter()
        worker = CountingWorker(
            name="wakeful",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=waiter,
        )

        await worker.stop()

        assert waiter.wake_count == 1

    asyncio.run(scenario())


def test_worker_base_stop_requires_injected_wake_waiter_wake_contract() -> None:
    async def scenario() -> None:
        worker = CountingWorker(
            name="malformed_wake_stop",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=object(),
        )

        with pytest.raises(AttributeError, match="wake"):
            await worker.stop()

    asyncio.run(scenario())


def test_worker_base_wait_requires_injected_wake_waiter_async_wait_contract() -> None:
    async def scenario() -> None:
        worker = CountingWorker(
            name="malformed_wake_wait",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=object(),
        )

        with pytest.raises(AttributeError, match="async_wait"):
            await worker._wait_for_next_iteration(0.0)

    asyncio.run(scenario())


def test_worker_base_aclose_closes_wake_waiter() -> None:
    async def scenario() -> None:
        waiter = FakeWakeWaiter()
        worker = CountingWorker(
            name="wake_close",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=waiter,
        )

        await worker.aclose()
        await worker.aclose()

        assert waiter.close_count == 1

    asyncio.run(scenario())


def test_worker_base_aclose_requires_injected_wake_waiter_close_contract() -> None:
    async def scenario() -> None:
        worker = CountingWorker(
            name="malformed_wake_close",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=object(),
        )

        with pytest.raises(AttributeError, match="close"):
            await worker.aclose()

    asyncio.run(scenario())


def test_worker_base_aclose_requires_sync_wake_waiter_close_contract_without_awaitable_fallback() -> None:
    async def scenario() -> None:
        waiter = AwaitableCloseWakeWaiter()
        worker = CountingWorker(
            name="malformed_wake_close_result",
            settings=worker_settings(),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=waiter,
        )

        with pytest.raises(RuntimeError, match="worker_wake_waiter_close_must_be_sync"):
            await worker.aclose()

        assert waiter.close_count == 1
        assert waiter.close_result.awaited is False

    asyncio.run(scenario())


def test_worker_base_long_iteration_records_one_success_without_synthetic_failure() -> None:
    class SlowThenStopWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0
            self.first_started_at_ms_seen: int | None = None

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            self.first_started_at_ms_seen = self.last_started_at_ms
            await asyncio.sleep(0.03)
            await self.stop()
            return WorkerResult(processed=1)

    async def scenario() -> None:
        telemetry = FakeTelemetry()
        waiter = FakeWakeWaiter()
        worker = SlowThenStopWorker(
            name="slow_status",
            settings=worker_settings(interval_seconds=0.001),
            db=FakeDB(),
            telemetry=telemetry,
            wake_waiter=waiter,
        )

        await worker.run()

        assert worker.calls == 1
        assert worker.last_started_at_ms == worker.first_started_at_ms_seen
        assert telemetry.jobs.count(("slow_status", "failed", 1)) == 0
        assert telemetry.jobs.count(("slow_status", "success", 1)) == 1
        assert waiter.waits == []
        assert worker.last_result == WorkerResult(processed=1)
        assert worker.status_payload()["active_run_once_age_ms"] is None

    asyncio.run(scenario())


def test_worker_base_hard_timeout_cancels_in_flight_task_and_discards_it() -> None:
    class HardTimedWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0
            self.active = 0
            self.max_active = 0
            self.cancelled = False
            self.cancel_reason: str | None = None

        async def run_once(self) -> WorkerResult:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError as exc:
                self.cancelled = True
                self.cancel_reason = exc.args[0] if exc.args else None
                await self.stop()
                raise
            finally:
                self.active -= 1

    async def scenario() -> None:
        worker = HardTimedWorker(
            name="hard_timeout",
            settings=worker_settings(
                hard_timeout_seconds=0.005,
                interval_seconds=0.001,
            ),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )
        run_task = asyncio.create_task(worker.run())
        try:
            await asyncio.wait_for(run_task, timeout=0.2)
        finally:
            if not run_task.done():
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)

        assert worker.cancelled is True
        assert worker.cancel_reason == WORKER_HARD_TIMEOUT_CANCEL_REASON
        assert worker.max_active == 1
        assert worker._run_once_tasks == set()
        assert "WorkerRunHardTimeout" in (worker.last_error or "")

    asyncio.run(scenario())


def test_worker_base_status_payload_includes_active_task_age_without_soft_timeout_state() -> None:
    class SlowStatusWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.started = asyncio.Event()

        async def run_once(self) -> WorkerResult:
            self.started.set()
            await asyncio.sleep(10)
            return WorkerResult(processed=1)

    async def scenario() -> None:
        worker = SlowStatusWorker(
            name="active_status",
            settings=worker_settings(
                hard_timeout_seconds=0.0,
                interval_seconds=0.001,
            ),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )
        run_task = asyncio.create_task(worker.run())
        try:
            await worker.started.wait()
            for _ in range(100):
                payload = worker.status_payload()
                if (payload["active_run_once_age_ms"] or 0) > 0:
                    break
                await asyncio.sleep(0.001)
            payload = worker.status_payload()

            assert payload["active_run_once_started_at_ms"] is not None
            assert payload["active_run_once_age_ms"] > 0
            assert "active_run_once_soft_timed_out_at_ms" not in payload
            assert payload["active_run_once_count"] == 1
        finally:
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

    asyncio.run(scenario())


def test_worker_base_cancelled_run_cancels_shielded_timed_out_run_once_task() -> None:
    class StubbornWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()
            self.completed = False

        async def run_once(self) -> WorkerResult:
            self.started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
            self.completed = True
            return WorkerResult(processed=1)

    async def scenario() -> None:
        worker = StubbornWorker(
            name="stubborn_timeout",
            settings=worker_settings(interval_seconds=0.001),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )
        run_task = asyncio.create_task(worker.run())
        await worker.started.wait()
        await asyncio.sleep(0.01)

        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)

        assert worker.cancelled.is_set()
        assert worker.completed is False
        assert worker._run_once_tasks == set()

    asyncio.run(scenario())


def test_worker_base_aclose_cancels_single_in_flight_task_after_rejected_concurrent_run() -> None:
    class ConcurrentStubbornWorker(WorkerBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.started_count = 0
            self.started_event = asyncio.Event()
            self.cancelled_count = 0

        async def run_once(self) -> WorkerResult:
            self.started_count += 1
            self.started_event.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled_count += 1
                raise
            return WorkerResult(processed=1)

    async def scenario() -> None:
        worker = ConcurrentStubbornWorker(
            name="concurrent_stubborn",
            settings=worker_settings(interval_seconds=0.001),
            db=FakeDB(),
            telemetry=FakeTelemetry(),
            wake_waiter=FakeWakeWaiter(),
        )
        first = asyncio.create_task(worker.run(), name="worker:concurrent_stubborn#0")
        await worker.started_event.wait()
        with pytest.raises(RuntimeError, match="worker:concurrent_stubborn:already_running"):
            await worker.run()
        await asyncio.sleep(0.01)

        await worker.stop()
        await worker.aclose()
        await asyncio.gather(first, return_exceptions=True)

        assert worker.cancelled_count == 1
        assert worker._run_once_tasks == set()

    asyncio.run(scenario())
