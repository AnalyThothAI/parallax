import asyncio
import time
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker


class FakeClient:
    provider = "fake"
    model = "fake-model"

    async def enrich_event(self, *, event: Any, entities: Any, run_id: str, job: dict[str, Any]) -> Any:
        return None


class SlowEnrichmentRepository:
    def claim_next_job(self, *, now_ms: int) -> None:
        time.sleep(0.08)


class FakeRepos:
    enrichment = SlowEnrichmentRepository()


@contextmanager
def fake_repository_session():
    yield FakeRepos()


def test_process_one_does_not_block_event_loop_while_claiming_jobs():
    worker = EnrichmentWorker(
        client=FakeClient(),
        repository_session=fake_repository_session,
        poll_interval=0.2,
    )

    async def run_probe() -> None:
        task = asyncio.create_task(worker.process_one(now_ms=1_700_000_000_000))
        await asyncio.sleep(0.01)
        assert not task.done()
        assert await task is False

    asyncio.run(run_probe())
