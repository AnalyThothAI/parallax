from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from ..storage.postgres_client import transaction
from .harness_snapshot_builder import HarnessSnapshotBuilder


class EnrichmentWorker:
    def __init__(
        self,
        *,
        client,
        publisher=None,
        repository_session: Callable[[], AbstractContextManager[Any]],
        poll_interval: float = 2.0,
    ):
        self.repository_session = repository_session
        self.client = client
        self.publisher = publisher
        self.poll_interval = max(0.2, float(poll_interval))
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                processed = await self.process_one()
            except Exception as exc:
                logger.exception(f"enrichment worker loop failed: {exc}")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    async def process_one(self, *, now_ms: int | None = None) -> bool:
        with self.repository_session() as repos:
            job = repos.enrichment.claim_next_job(now_ms=now_ms or _now_ms())
        if job is None:
            return False

        with self.repository_session() as repos:
            event = repos.evidence.events_by_ids([str(job["event_id"])]).get(str(job["event_id"]))
        if event is None:
            with self.repository_session() as repos:
                repos.enrichment.fail_job(job=job, error="event_not_found")
            return True

        with self.repository_session() as repos:
            entities = repos.entities.entities_for_event(str(job["event_id"]))
        request = {"event_id": job["event_id"], "job_type": job["job_type"]}
        try:
            timeout_seconds = max(0.1, float(getattr(self.client, "timeout_seconds", 30.0) or 30.0))
            result = await asyncio.wait_for(
                self.client.enrich_event(event=event, entities=entities),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            with self.repository_session() as repos:
                repos.enrichment.fail_job(job=job, error=f"LLM request timed out after {timeout_seconds:g}s")
            return True
        except Exception as exc:
            with self.repository_session() as repos:
                repos.enrichment.fail_job(job=job, error=str(exc))
            return True

        try:
            with self.repository_session() as repos, transaction(repos.conn):
                run = repos.enrichment.complete_social_event_job(
                    job=job,
                    result=result,
                    provider=self.client.provider,
                    model=self.client.model,
                    request=request,
                    commit=False,
                )
                materialized = HarnessSnapshotBuilder(repos.harness, tokens=repos.tokens).materialize(
                    event=event,
                    extraction=result,
                    run_id=str(run["run_id"]),
                    model_version=self.client.model,
                    commit=False,
                )
        except Exception as exc:
            logger.exception(f"harness materialization failed event_id={event.get('event_id')}: {exc}")
            with self.repository_session() as repos:
                repos.enrichment.fail_job(job=job, error=str(exc))
            return True

        if self.publisher is not None:
            await self.publisher.publish(
                {
                    "type": "harness_update",
                    "event": event,
                    "entities": entities,
                    **materialized,
                }
            )
        return True


def _now_ms() -> int:
    return int(time.time() * 1000)
