import asyncio

from gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker import HandleSummaryWorker
from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_service import HandleSummaryTriggerConfig


def test_handle_summary_worker_processes_due_jobs_concurrently():
    async def scenario():
        repo = FakeWatchlistRepository(
            [
                {"handle": "toly", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-1"},
                {"handle": "traderpow", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-2"},
            ]
        )
        provider = BarrierSummaryProvider()
        worker = HandleSummaryWorker(
            repository_session=lambda: FakeRepositorySession(repo),
            provider=provider,
            handles=("toly", "traderpow"),
            config=HandleSummaryTriggerConfig(),
            concurrency=2,
            poll_interval=1,
        )

        task = asyncio.create_task(worker.process_due_jobs_once_async(now_ms=1_000))
        await asyncio.sleep(0.05)
        started_before_release = provider.started
        provider.release.set()
        result = await asyncio.wait_for(task, timeout=1)

        assert started_before_release == 2
        assert result == {"claimed": 2, "processed": 2, "failed": 0}

    asyncio.run(scenario())


def test_handle_summary_worker_records_failed_run_audit():
    async def scenario():
        repo = FakeWatchlistRepository(
            [{"handle": "toly", "attempt_count": 1, "max_attempts": 3, "lease_token": "lease-1"}]
        )
        worker = HandleSummaryWorker(
            repository_session=lambda: FakeRepositorySession(repo),
            provider=FailingSummaryProvider(),
            handles=("toly",),
            config=HandleSummaryTriggerConfig(),
            concurrency=1,
            poll_interval=1,
        )

        result = await worker.process_due_jobs_once_async(now_ms=1_000)

        assert result == {"claimed": 1, "processed": 0, "failed": 1}
        assert repo.failed_runs[0]["status"] == "failed"
        assert repo.failed_runs[0]["handle"] == "toly"
        assert repo.failed_runs[0]["error"] == "provider exploded"
        assert repo.failed_jobs[0]["handle"] == "toly"

    asyncio.run(scenario())


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

    def claim_next_summary_job(self, *, now_ms, lease_ms):
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


class BarrierSummaryProvider:
    model = "test-model"

    def __init__(self):
        self.started = 0
        self.release = asyncio.Event()

    async def summarize_handle(self, **kwargs):
        self.started += 1
        await self.release.wait()
        return {"summary_zh": "账号主题摘要", "topics": [], "usage": {}}


class FailingSummaryProvider:
    model = "test-model"

    async def summarize_handle(self, **kwargs):
        raise RuntimeError("provider exploded")
