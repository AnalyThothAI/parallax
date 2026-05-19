from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.watchlist_intel.providers import HandleTopicSummaryProvider
from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_service import (
    HandleSummaryInputs,
    HandleSummaryTriggerConfig,
    WatchlistHandleSummaryService,
    not_enough_input_response,
)


class HandleSummaryWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        provider: HandleTopicSummaryProvider,
        handles: tuple[str, ...],
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.provider = provider
        self.handles = tuple(handles)
        self.config = _trigger_config_from_settings(settings)
        self.concurrency = max(1, int(getattr(settings, "concurrency", 1) or 1))
        self.lease_ms = max(1_000, int(getattr(settings, "lease_ms", 120_000) or 120_000))
        self.provider_timeout_seconds = max(1.0, (self.lease_ms - 1_000) / 1000)
        self.reconcile_limit = max(1, int(getattr(settings, "reconcile_limit", 100) or 100))

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        started_at_ms = int(now_ms if now_ms is not None else _now_ms())
        try:
            reconcile = await asyncio.to_thread(self.reconcile_missing_jobs_once, now_ms=started_at_ms)
        except Exception as exc:
            logger.warning("watchlist handle summary reconcile failed: error={}", str(exc)[:300])
            reconcile = {
                "seen": 0,
                "enqueued": 0,
                "skipped": 0,
                "failed": 1,
                "error": type(exc).__name__,
            }
        process = await self.process_due_jobs_once_async(now_ms=started_at_ms)
        notes = {**{f"reconcile_{key}": value for key, value in reconcile.items()}, **process}
        skipped = int(reconcile.get("skipped") or 0)
        if not notes["claimed"] and not notes["reconcile_enqueued"]:
            skipped = max(1, skipped)
        return WorkerResult(
            processed=int(process.get("processed") or 0) + int(reconcile.get("enqueued") or 0),
            failed=int(process.get("failed") or 0) + int(reconcile.get("failed") or 0),
            skipped=skipped,
            notes=notes,
        )

    def reconcile_missing_jobs_once(self, *, now_ms: int | None = None) -> dict[str, int]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        since_ms = resolved_now_ms - max(1, int(self.config.window_days)) * 24 * 60 * 60 * 1000
        result = {"seen": 0, "enqueued": 0, "skipped": 0}
        with self._repository_session() as repos:
            rows = repos.watchlist_intel.handles_missing_summary_jobs(
                handles=self.handles,
                since_ms=since_ms,
                limit=self.reconcile_limit,
            )
            service = WatchlistHandleSummaryService(
                repository=repos.watchlist_intel,
                provider=None,
                config=self.config,
            )
            for row in rows:
                result["seen"] += 1
                if service.enqueue_handle_summary_if_due(
                    handle=str(row.get("handle") or ""),
                    now_ms=resolved_now_ms,
                    commit=True,
                ):
                    result["enqueued"] += 1
                else:
                    result["skipped"] += 1
        return result

    async def process_due_jobs_once_async(self, *, now_ms: int | None = None) -> dict[str, Any]:
        result = {"claimed": 0, "processed": 0, "failed": 0}
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        jobs: list[tuple[dict[str, Any], Any]] = []
        for _ in range(self.concurrency):
            reservation = self.provider.try_reserve_execution("watchlist.handle_summary")
            if not reservation.acquired:
                _record_agent_backpressure(result, reservation)
                break
            try:
                job = await asyncio.to_thread(self._claim_next_job_sync, now_ms=resolved_now_ms)
            except Exception:
                await reservation.release()
                raise
            if job is None:
                await reservation.release()
                break
            jobs.append((job, reservation))
        result["claimed"] = len(jobs)
        if not jobs:
            return result
        outcomes = await asyncio.gather(
            *(self._process_job(job, now_ms=resolved_now_ms, reservation=reservation) for job, reservation in jobs),
            return_exceptions=False,
        )
        for outcome in outcomes:
            if outcome.startswith("agent_backpressure:"):
                _record_agent_backpressure_reason(result, outcome.split(":", 1)[1])
                continue
            result[outcome] += 1
        return result

    async def _process_job(self, job: dict[str, Any], *, now_ms: int, reservation: Any) -> str:
        started_at_ms = _now_ms()
        request_audit: dict[str, Any] | None = None
        try:
            inputs = await asyncio.to_thread(self._summary_inputs_sync, job=job, now_ms=now_ms)
            if inputs.events:
                request_audit = self.provider.request_audit(
                    handle=inputs.handle,
                    events=inputs.events,
                    run_id=inputs.run_id,
                    job=job,
                    context=inputs.context,
                )
                response = await self._summarize_with_timeout(job=job, inputs=inputs, reservation=reservation)
                model = str(getattr(self.provider, "model", "") or "")
            else:
                response = not_enough_input_response()
                model = "deterministic:not_enough_input"
            await asyncio.to_thread(
                self._complete_summary_sync,
                job=job,
                inputs=inputs,
                response=response,
                model=model,
                started_at_ms=started_at_ms,
                finished_at_ms=_now_ms(),
            )
        except Exception as exc:
            if _is_agent_no_start_backpressure(exc):
                reason = _agent_backpressure_reason(exc)
                await asyncio.to_thread(
                    self._release_job_for_backpressure_sync,
                    job=job,
                    reason=reason,
                    now_ms=now_ms,
                )
                return f"agent_backpressure:{reason}"
            logger.warning(
                "watchlist handle summary job failed: handle={} error={}",
                job.get("handle"),
                str(exc)[:300],
            )
            try:
                await asyncio.to_thread(
                    self._record_failed_summary_sync,
                    job=job,
                    error=str(exc),
                    request_audit=request_audit,
                    started_at_ms=started_at_ms,
                    failed_at_ms=_now_ms(),
                )
            except Exception as record_exc:  # pragma: no cover - DB failure path
                logger.warning(
                    "watchlist handle summary failure audit write failed: handle={} error={}",
                    job.get("handle"),
                    str(record_exc)[:300],
                )
            return "failed"
        finally:
            await reservation.release()
        return "processed"

    async def _summarize_with_timeout(
        self,
        *,
        job: dict[str, Any],
        inputs: HandleSummaryInputs,
        reservation: Any,
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self.provider.summarize_handle(
                    handle=inputs.handle,
                    events=inputs.events,
                    run_id=inputs.run_id,
                    job=job,
                    context=inputs.context,
                    reservation=reservation,
                ),
                timeout=self.provider_timeout_seconds,
            )
        except TimeoutError as exc:
            message = f"watchlist summary provider timed out after {self.provider_timeout_seconds:g}s"
            raise TimeoutError(message) from exc

    def _claim_next_job_sync(self, *, now_ms: int) -> dict[str, Any] | None:
        with self._repository_session() as repos:
            return cast(
                dict[str, Any] | None,
                repos.watchlist_intel.claim_next_summary_job(
                    now_ms=now_ms,
                    lease_ms=self.lease_ms,
                ),
            )

    def _summary_inputs_sync(self, *, job: dict[str, Any], now_ms: int) -> HandleSummaryInputs:
        with self._repository_session() as repos:
            service = WatchlistHandleSummaryService(
                repository=repos.watchlist_intel,
                provider=None,
                config=self.config,
            )
            return service.summary_inputs(job, now_ms=now_ms)

    def _complete_summary_sync(
        self,
        *,
        job: dict[str, Any],
        inputs: HandleSummaryInputs,
        response: dict[str, Any],
        model: str,
        started_at_ms: int,
        finished_at_ms: int,
    ) -> dict[str, Any]:
        with self._repository_session() as repos:
            service = WatchlistHandleSummaryService(
                repository=repos.watchlist_intel,
                provider=None,
                config=self.config,
            )
            return service.complete_summary(
                job=job,
                inputs=inputs,
                response=response,
                model=model,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
            )

    def _record_failed_summary_sync(
        self,
        *,
        job: dict[str, Any],
        error: str,
        request_audit: dict[str, Any] | None,
        started_at_ms: int,
        failed_at_ms: int,
    ) -> None:
        handle = str(job.get("handle") or "")
        audit = dict(request_audit or {})
        usage = dict(audit.get("usage") or {})
        with self._repository_session() as repos, _unit_of_work(repos):
            repos.watchlist_intel.insert_summary_run(
                run_id=f"watchlist-summary-failed-{handle}-{job.get('attempt_count')}-{failed_at_ms}",
                handle=handle,
                status="failed",
                model=str(getattr(self.provider, "model", "") or ""),
                request_json={"job": dict(job), "agent_run_audit": audit} if audit else {"job": dict(job)},
                response_json=None,
                input_event_count=0,
                usage_json=usage,
                error=error,
                started_at_ms=started_at_ms,
                finished_at_ms=failed_at_ms,
                safety_net_used=bool(audit.get("safety_net_used", False)),
                safety_net_retries=int(audit.get("safety_net_retries") or 0),
                parse_mode=str(audit.get("parse_mode") or "strict"),
                commit=False,
            )
            repos.watchlist_intel.mark_summary_job_failed(job, error, now_ms=failed_at_ms, commit=False)

    def _release_job_for_backpressure_sync(self, *, job: dict[str, Any], reason: str, now_ms: int) -> None:
        with self._repository_session() as repos:
            repos.watchlist_intel.release_job_for_backpressure(
                job,
                reason=reason,
                now_ms=now_ms,
                delay_ms=30_000,
            )

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _trigger_config_from_settings(settings: Any) -> HandleSummaryTriggerConfig:
    return HandleSummaryTriggerConfig(
        signal_threshold=int(getattr(settings, "signal_threshold", 10) or 10),
        time_threshold_ms=int(getattr(settings, "time_threshold_ms", 1_800_000) or 1_800_000),
        min_interval_ms=int(getattr(settings, "min_interval_ms", 300_000) or 300_000),
        input_limit=int(getattr(settings, "input_limit", 80) or 80),
        window_days=int(getattr(settings, "window_days", 7) or 7),
        max_attempts=int(getattr(settings, "max_attempts", 3) or 3),
    )


@contextmanager
def _unit_of_work(repos: Any) -> Iterator[None]:
    unit_of_work = getattr(repos, "unit_of_work", None)
    if unit_of_work is None:
        yield
        return
    with unit_of_work():
        yield


def _now_ms() -> int:
    return int(time.time() * 1000)


def _record_agent_backpressure(result: dict[str, int | str], reservation: Any) -> None:
    result["agent_backpressure_capacity_denied"] = int(result.get("agent_backpressure_capacity_denied") or 0) + 1
    reason = getattr(reservation, "reason", None)
    result["agent_backpressure"] = getattr(reason, "value", reason) or "capacity_denied"


def _record_agent_backpressure_reason(result: dict[str, int | str], reason: str) -> None:
    result[f"agent_backpressure_{reason}"] = int(result.get(f"agent_backpressure_{reason}") or 0) + 1
    result["agent_backpressure"] = reason


def _is_agent_no_start_backpressure(exc: Exception) -> bool:
    error_class = getattr(exc, "error_class", None)
    execution_started = bool(getattr(exc, "execution_started", True))
    value = getattr(error_class, "value", error_class)
    return not execution_started and value in {"capacity_denied", "circuit_open", "rate_limited"}


def _agent_backpressure_reason(exc: Exception) -> str:
    error_class = getattr(exc, "error_class", None)
    return str(getattr(error_class, "value", error_class) or "capacity_denied")


__all__ = ["HandleSummaryWorker"]
