from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, cast

from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.social_enrichment.providers import SocialEventEnrichmentProvider
from gmgn_twitter_intel.domains.social_enrichment.types.social_event_extraction import SCHEMA_VERSION
from gmgn_twitter_intel.domains.watchlist_intel.interfaces import (
    HandleSummaryTriggerConfig,
    WatchlistHandleSummaryService,
)


class EnrichmentWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        client: SocialEventEnrichmentProvider,
        publisher: Any = None,
        watchlist_summary_config: HandleSummaryTriggerConfig | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.client = client
        self.publisher = publisher
        self.watchlist_summary_config = watchlist_summary_config

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await self.process_one(now_ms=now_ms)

    async def process_one(self, *, now_ms: int | None = None) -> WorkerResult:
        reservation = self.client.try_reserve_execution("social.event_enrichment")
        if not reservation.acquired:
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "agent_backpressure_capacity_denied",
                    "agent_backpressure": _reservation_reason(reservation),
                    "agent_backpressure_capacity_denied": 1,
                },
            )
        try:
            job = await asyncio.to_thread(self._claim_next_job_sync, now_ms=now_ms or _now_ms())
            if job is None:
                return WorkerResult(skipped=1, notes={"reason": "no_job"})

            event = await asyncio.to_thread(self._event_by_id_sync, event_id=str(job["event_id"]))
            if event is None:
                await asyncio.to_thread(self._fail_job_sync, job=job, error="event_not_found")
                return WorkerResult(failed=1, notes={"reason": "event_not_found", "job_id": job.get("job_id")})

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
                    self.client.enrich_event(
                        event=event,
                        entities=entities,
                        run_id=run_id,
                        job=job,
                        reservation=reservation,
                    ),
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
                return WorkerResult(failed=1, notes={"reason": "model_timeout", "job_id": job.get("job_id")})
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
                return WorkerResult(failed=1, notes={"reason": "model_error", "job_id": job.get("job_id")})

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
                logger.exception(f"enrichment persistence failed event_id={event.get('event_id')}: {exc}")
                await asyncio.to_thread(self._fail_job_sync, job=job, error=str(exc))
                return WorkerResult(
                    failed=1,
                    notes={"reason": "enrichment_persistence_error", "job_id": job.get("job_id")},
                )

            if self.publisher is not None:
                await self.publisher.publish(
                    {
                        "type": "social_event_enrichment_update",
                        "event": event,
                        "entities": entities,
                        **materialized,
                    }
                )
            return WorkerResult(processed=1, notes={"job_id": job.get("job_id"), "event_id": job.get("event_id")})
        finally:
            await reservation.release()

    def _claim_next_job_sync(self, *, now_ms: int) -> dict[str, Any] | None:
        with self._repository_session() as repos:
            job = repos.enrichment.claim_next_job(now_ms=now_ms or _now_ms())
        return cast(dict[str, Any] | None, job)

    def _event_by_id_sync(self, *, event_id: str) -> dict[str, Any] | None:
        with self._repository_session() as repos:
            event = repos.evidence.events_by_ids([event_id]).get(event_id)
        return cast(dict[str, Any] | None, event)

    def _entities_for_event_sync(self, *, event_id: str) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            entities = repos.entities.entities_for_event(event_id)
        return cast(list[dict[str, Any]], entities)

    def _fail_job_sync(self, *, job: dict[str, Any], error: str) -> None:
        with self._repository_session() as repos:
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
        with self._repository_session() as repos:
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
        with self._repository_session() as repos, repos.unit_of_work():
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
            social_event_row = repos.social_event_extractions.upsert_extraction(
                event_id=str(event["event_id"]),
                run_id=str(run["run_id"]),
                author_handle=_author_handle(event),
                received_at_ms=int(event.get("received_at_ms") or finished_at_ms),
                schema_version=SCHEMA_VERSION,
                model_version=self.client.model,
                event_type=str(result.event_type),
                source_action=str(result.source_action),
                subject=str(result.subject),
                direction_hint=str(result.direction_hint),
                attention_mechanism=str(result.attention_mechanism),
                impact_hint=float(result.impact_hint),
                semantic_novelty_hint=float(result.semantic_novelty_hint),
                confidence=float(result.confidence),
                is_signal_event=bool(result.is_signal_event),
                anchor_terms=[asdict(anchor) for anchor in result.anchor_terms],
                token_candidates=[asdict(candidate) for candidate in result.token_candidates],
                semantic_risks=list(result.semantic_risks),
                summary_zh=str(result.summary_zh),
                raw_response=dict(result.raw_response),
                commit=False,
            )
            watchlist_summary_enqueued = False
            if self.watchlist_summary_config is not None and bool(getattr(result, "is_signal_event", False)):
                handle = str(getattr(result, "author_handle", "") or event.get("author_handle") or "")
                if handle:
                    summary_job = WatchlistHandleSummaryService(
                        repository=repos.watchlist_intel,
                        provider=None,
                        config=self.watchlist_summary_config,
                    ).enqueue_handle_summary_if_due(handle=handle, now_ms=finished_at_ms, commit=False)
                    watchlist_summary_enqueued = summary_job is not None
            return {
                "social_event": social_event_row,
                "watchlist_summary_enqueued": watchlist_summary_enqueued,
            }

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _reservation_reason(reservation: Any) -> str:
    reason = getattr(reservation, "reason", None)
    return str(getattr(reason, "value", reason) or "capacity_denied")


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


def _author_handle(event: dict[str, Any]) -> str | None:
    if event.get("author_handle"):
        return str(event["author_handle"]).strip().lstrip("@").lower()
    author = event.get("author")
    if isinstance(author, dict) and author.get("handle"):
        return str(author["handle"]).strip().lstrip("@").lower()
    return None
