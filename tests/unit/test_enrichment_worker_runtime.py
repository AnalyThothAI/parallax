import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker


class FakeClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.closed = False

    async def enrich_event(self, *, event: Any, entities: Any, run_id: str, job: dict[str, Any]) -> Any:
        return None

    async def aclose(self) -> None:
        self.closed = True


class SlowEnrichmentRepository:
    def claim_next_job(self, *, now_ms: int) -> None:
        time.sleep(0.08)


class FakeRepos:
    enrichment = SlowEnrichmentRepository()


class FakeDB:
    def __init__(self):
        self.sessions: list[dict[str, Any]] = []

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        yield FakeRepos()


def test_process_one_does_not_block_event_loop_while_claiming_jobs():
    db = FakeDB()
    worker = EnrichmentWorker(
        name="enrichment",
        settings=SimpleNamespace(interval_seconds=0.2, statement_timeout_seconds=12.0),
        db=db,
        telemetry=SimpleNamespace(),
        client=FakeClient(),
    )

    async def run_probe() -> None:
        task = asyncio.create_task(worker.run_once(now_ms=1_700_000_000_000))
        await asyncio.sleep(0.01)
        assert not task.done()
        result = await task
        assert result == WorkerResult(skipped=1, notes={"reason": "no_job"})

    asyncio.run(run_probe())
    assert db.sessions == [{"name": "enrichment", "statement_timeout_seconds": 12.0}]


def test_enrichment_worker_is_worker_base_and_run_once_reports_result_status():
    db = FakeDB()
    worker = EnrichmentWorker(
        name="enrichment",
        settings=SimpleNamespace(interval_seconds=0.2),
        db=db,
        telemetry=SimpleNamespace(),
        client=FakeClient(),
    )

    assert isinstance(worker, WorkerBase)
    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes == {"reason": "no_job"}


def test_enrichment_worker_aclose_does_not_close_runtime_owned_client():
    db = FakeDB()
    client = FakeClient()
    worker = EnrichmentWorker(
        name="enrichment",
        settings=SimpleNamespace(interval_seconds=0.2),
        db=db,
        telemetry=SimpleNamespace(),
        client=client,
    )

    asyncio.run(worker.aclose())

    assert client.closed is False
