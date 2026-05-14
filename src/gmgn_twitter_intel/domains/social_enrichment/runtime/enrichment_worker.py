from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast

from loguru import logger

from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessSnapshotBuilder
from gmgn_twitter_intel.domains.social_enrichment.providers import SocialEventEnrichmentProvider
from gmgn_twitter_intel.domains.watchlist_intel.interfaces import (
    HandleSummaryTriggerConfig,
    WatchlistHandleSummaryService,
)


class EnrichmentWorker:
    def __init__(
        self,
        *,
        client: SocialEventEnrichmentProvider,
        publisher: Any = None,
        repository_session: Callable[[], AbstractContextManager[Any]],
        poll_interval: float = 2.0,
        concurrency: int = 1,
        watchlist_summary_config: HandleSummaryTriggerConfig | None = None,
    ) -> None:
        self.repository_session = repository_session
        self.client = client
        self.publisher = publisher
        self.poll_interval = max(0.2, float(poll_interval))
        self.concurrency = max(1, min(16, int(concurrency)))
        self.watchlist_summary_config = watchlist_summary_config
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        if self.concurrency == 1:
            await self._run_loop()
            return
        tasks = [asyncio.create_task(self._run_loop()) for _ in range(self.concurrency)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_loop(self) -> None:
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
        job = await asyncio.to_thread(self._claim_next_job_sync, now_ms=now_ms or _now_ms())
        if job is None:
            return False

        event = await asyncio.to_thread(self._event_by_id_sync, event_id=str(job["event_id"]))
        if event is None:
            await asyncio.to_thread(self._fail_job_sync, job=job, error="event_not_found")
            return True

        entities = await asyncio.to_thread(self._entities_for_event_sync, event_id=str(job["event_id"]))
        run_id = _run_id(job)
        request = {
            "run_id": run_id,
            "job_id": job["job_id"],
            "event_id": job["event_id"],
            "job_type": job["job_type"],
            "attempt_count": job.get("attempt_count"),
        }
        request_audit = {}
        if hasattr(self.client, "request_audit"):
            request_audit = self.client.request_audit(event=event, entities=entities, run_id=run_id, job=job)
        started_at_ms = _now_ms()
        try:
            timeout_seconds = max(0.1, float(getattr(self.client, "timeout_seconds", 30.0) or 30.0))
            result = await asyncio.wait_for(
                self.client.enrich_event(event=event, entities=entities, run_id=run_id, job=job),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            error = f"Agents SDK request timed out after {timeout_seconds:g}s"
            await asyncio.to_thread(
                self._record_model_run_failure_sync,
                job=job,
                run_id=run_id,
                request=request,
                error=error,
                audit=request_audit,
                started_at_ms=started_at_ms,
                finished_at_ms=_now_ms(),
            )
            return True
        except Exception as exc:
            error = str(exc)
            await asyncio.to_thread(
                self._record_model_run_failure_sync,
                job=job,
                run_id=run_id,
                request=request,
                error=error,
                audit=request_audit,
                started_at_ms=started_at_ms,
                finished_at_ms=_now_ms(),
            )
            return True

        try:
            materialized = await asyncio.to_thread(
                self._complete_job_sync,
                job=job,
                event=event,
                result=result,
                run_id=run_id,
                request=request,
                started_at_ms=started_at_ms,
                finished_at_ms=_now_ms(),
            )
        except Exception as exc:
            logger.exception(f"harness materialization failed event_id={event.get('event_id')}: {exc}")
            await asyncio.to_thread(self._fail_job_sync, job=job, error=str(exc))
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

    def _claim_next_job_sync(self, *, now_ms: int) -> dict[str, Any] | None:
        with self.repository_session() as repos:
            job = repos.enrichment.claim_next_job(now_ms=now_ms or _now_ms())
        return cast(dict[str, Any] | None, job)

    def _event_by_id_sync(self, *, event_id: str) -> dict[str, Any] | None:
        with self.repository_session() as repos:
            event = repos.evidence.events_by_ids([event_id]).get(event_id)
        return cast(dict[str, Any] | None, event)

    def _entities_for_event_sync(self, *, event_id: str) -> list[dict[str, Any]]:
        with self.repository_session() as repos:
            entities = repos.entities.entities_for_event(event_id)
        return cast(list[dict[str, Any]], entities)

    def _fail_job_sync(self, *, job: dict[str, Any], error: str) -> None:
        with self.repository_session() as repos:
            repos.enrichment.fail_job(job=job, error=error)

    def _record_model_run_failure_sync(
        self,
        *,
        job: dict[str, Any],
        run_id: str,
        request: dict[str, Any],
        error: str,
        audit: dict[str, Any],
        started_at_ms: int,
        finished_at_ms: int,
    ) -> None:
        with self.repository_session() as repos:
            repos.enrichment.record_model_run_failure(
                job=job,
                run_id=run_id,
                provider=self.client.provider,
                model=self.client.model,
                request=request,
                error=error,
                audit=audit,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
            )
            repos.enrichment.fail_job(job=job, error=error)

    def _complete_job_sync(
        self,
        *,
        job: dict[str, Any],
        event: dict[str, Any],
        result: Any,
        run_id: str,
        request: dict[str, Any],
        started_at_ms: int,
        finished_at_ms: int,
    ) -> dict[str, Any]:
        with self.repository_session() as repos, repos.unit_of_work():
            run = repos.enrichment.complete_social_event_job(
                job=job,
                run_id=run_id,
                result=result,
                provider=self.client.provider,
                model=self.client.model,
                request=request,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
                commit=False,
            )
            materialized = HarnessSnapshotBuilder(repos.harness, assets=repos.assets).materialize(
                event=event,
                extraction=result,
                run_id=str(run["run_id"]),
                model_version=self.client.model,
                commit=False,
            )
            if self.watchlist_summary_config is not None and bool(getattr(result, "is_signal_event", False)):
                handle = str(getattr(result, "author_handle", "") or event.get("author_handle") or "")
                if handle:
                    WatchlistHandleSummaryService(
                        repository=repos.watchlist_intel,
                        provider=None,
                        config=self.watchlist_summary_config,
                    ).enqueue_handle_summary_if_due(handle=handle, now_ms=finished_at_ms, commit=False)
            return materialized


def _now_ms() -> int:
    return int(time.time() * 1000)


def _run_id(job: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(job.get("job_id") or ""),
            str(job.get("event_id") or ""),
            str(job.get("job_type") or ""),
            str(job.get("attempt_count") or 0),
            str(_now_ms()),
        ]
    )
    return "run-" + hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
