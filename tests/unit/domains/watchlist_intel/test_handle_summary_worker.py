import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker import HandleSummaryWorker
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionErrorClass,
)


def test_handle_summary_worker_processes_due_jobs_concurrently():
    async def scenario():
        repo = FakeWatchlistRepository(
            [
                {"handle": "toly", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-1"},
                {"handle": "traderpow", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-2"},
            ]
        )
        db = FakeDB(repo)
        provider = BarrierSummaryProvider(db)
        worker = HandleSummaryWorker(
            name="handle_summary",
            settings=fake_settings(concurrency=2),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
            handles=("toly", "traderpow"),
        )

        assert isinstance(worker, WorkerBase)
        task = asyncio.create_task(worker.run_once(now_ms=1_000))
        await asyncio.sleep(0.05)
        started_before_release = provider.started
        provider.release.set()
        result = await asyncio.wait_for(task, timeout=1)

        assert started_before_release == 2
        assert result == WorkerResult(
            processed=2,
            notes={
                "reconcile_seen": 0,
                "reconcile_enqueued": 0,
                "reconcile_skipped": 0,
                "claimed": 2,
                "processed": 2,
                "failed": 0,
            },
        )
        assert provider.max_sessions_seen == 0

    asyncio.run(scenario())


def test_handle_summary_worker_records_failed_run_audit():
    async def scenario():
        repo = FakeWatchlistRepository(
            [{"handle": "toly", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-1"}]
        )
        db = FakeDB(repo)
        worker = HandleSummaryWorker(
            name="handle_summary",
            settings=fake_settings(concurrency=1),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingSummaryProvider(),
            handles=("toly",),
        )

        result = await worker.run_once(now_ms=1_000)

        assert result.processed == 0
        assert result.failed == 1
        assert result.notes["claimed"] == 1
        assert repo.failed_runs[0]["status"] == "failed"
        assert repo.failed_runs[0]["handle"] == "toly"
        assert repo.failed_runs[0]["error"] == "provider exploded"
        assert repo.failed_runs[0]["request_json"]["agent_run_audit"]["sdk_trace_id"] == "trace-toly"
        assert repo.failed_runs[0]["usage_json"] == {"input_tokens": 12}
        assert repo.failed_jobs[0]["handle"] == "toly"

    asyncio.run(scenario())


def test_handle_summary_worker_reports_reconcile_failure_as_iteration_result():
    async def scenario():
        repo = ReconcileFailingWatchlistRepository([])
        db = FakeDB(repo)
        worker = HandleSummaryWorker(
            name="handle_summary",
            settings=fake_settings(concurrency=1),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingSummaryProvider(),
            handles=("toly",),
        )

        result = await worker.run_once(now_ms=1_000)

        assert result.processed == 0
        assert result.failed == 1
        assert result.notes["reconcile_failed"] == 1
        assert result.notes["reconcile_error"] == "TimeoutError"
        assert result.notes["claimed"] == 0

    asyncio.run(scenario())


def test_handle_summary_worker_does_not_claim_when_agent_capacity_denied():
    async def scenario():
        repo = FakeWatchlistRepository(
            [{"handle": "toly", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-1"}]
        )
        db = FakeDB(repo)
        worker = HandleSummaryWorker(
            name="handle_summary",
            settings=fake_settings(concurrency=1),
            db=db,
            telemetry=SimpleNamespace(),
            provider=CapacityDeniedSummaryProvider(),
            handles=("toly",),
        )

        result = await worker.run_once(now_ms=1_000)

        assert result.processed == 0
        assert result.skipped == 1
        assert result.notes["agent_backpressure_capacity_denied"] == 1
        assert result.notes["claimed"] == 0
        assert repo.claim_calls == 0

    asyncio.run(scenario())


def fake_settings(*, concurrency=1):
    return SimpleNamespace(
        enabled=True,
        interval_seconds=1.0,
        concurrency=concurrency,
        lease_ms=120_000,
        reconcile_limit=100,
        signal_threshold=10,
        time_threshold_ms=1_800_000,
        min_interval_ms=300_000,
        input_limit=80,
        window_days=7,
        max_attempts=3,
        statement_timeout_seconds=9.0,
    )


class FakeDB:
    def __init__(self, watchlist_repo):
        self.watchlist_repo = watchlist_repo
        self.active_sessions = 0
        self.sessions = []

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        self.active_sessions += 1
        try:
            yield FakeRepositorySession(self.watchlist_repo)
        finally:
            self.active_sessions -= 1


class FakeRepositorySession:
    def __init__(self, watchlist_repo):
        self.watchlist_intel = watchlist_repo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeWatchlistRepository:
    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.completed = []
        self.failed_jobs = []
        self.failed_runs = []
        self.claim_calls = 0

    def handles_missing_summary_jobs(self, *, handles, since_ms, limit):
        return []

    def claim_next_summary_job(self, *, now_ms, lease_ms):
        self.claim_calls += 1
        if not self.jobs:
            return None
        return self.jobs.pop(0)

    def signal_events_for_summary(self, *, handle, since_ms, limit):
        return [{"event_id": f"event-{handle}", "summary_zh": "信号摘要", "received_at_ms": 900}]

    def count_signal_events_total(self, handle):
        return 1

    def complete_handle_summary(self, *, job, handle, summary, run):
        self.completed.append({"job": job, "handle": handle, "summary": summary, "run": run})
        return summary

    def mark_summary_job_failed(self, job, error, *, now_ms, retry_delay_ms=30_000, commit=True):
        self.failed_jobs.append({"handle": job["handle"], "error": error, "now_ms": now_ms})
        return {**job, "status": "failed", "last_error": error}

    def insert_summary_run(self, **run):
        self.failed_runs.append(run)
        return run


class ReconcileFailingWatchlistRepository(FakeWatchlistRepository):
    def handles_missing_summary_jobs(self, *, handles, since_ms, limit):
        raise TimeoutError("summary reconcile timed out")


class BarrierSummaryProvider:
    model = "test-model"

    def __init__(self, db):
        self.db = db
        self.started = 0
        self.max_sessions_seen = 0
        self.closed = False
        self.release = asyncio.Event()

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation:
        return AgentCapacityReservation(lane=lane, acquired=True)

    def request_audit(self, *, handle, events, run_id, job, context):
        return {"sdk_trace_id": f"trace-{handle}", "usage": {"input_tokens": 12}}

    async def summarize_handle(self, **kwargs):
        self.started += 1
        self.max_sessions_seen = max(self.max_sessions_seen, self.db.active_sessions)
        await self.release.wait()
        return {"summary_zh": "账号主题摘要", "topics": [], "usage": {}}

    async def aclose(self):
        self.closed = True


class FailingSummaryProvider:
    model = "test-model"

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation:
        return AgentCapacityReservation(lane=lane, acquired=True)

    def request_audit(self, *, handle, events, run_id, job, context):
        return {"sdk_trace_id": f"trace-{handle}", "usage": {"input_tokens": 12}}

    async def summarize_handle(self, **kwargs):
        raise RuntimeError("provider exploded")


class CapacityDeniedSummaryProvider(FailingSummaryProvider):
    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation:
        return AgentCapacityReservation(
            lane=lane,
            acquired=False,
            reason=AgentExecutionErrorClass.CAPACITY_DENIED,
        )


def test_handle_summary_worker_aclose_does_not_close_runtime_owned_provider():
    repo = FakeWatchlistRepository([])
    db = FakeDB(repo)
    provider = BarrierSummaryProvider(db)
    worker = HandleSummaryWorker(
        name="handle_summary",
        settings=fake_settings(concurrency=1),
        db=db,
        telemetry=SimpleNamespace(),
        provider=provider,
        handles=("toly",),
    )

    asyncio.run(worker.aclose())

    assert provider.closed is False
