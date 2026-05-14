from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.watchlist_intel.providers import HandleTopicSummaryProvider
from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_service import (
    HandleSummaryTriggerConfig,
    WatchlistHandleSummaryService,
)


class HandleSummaryWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        provider: HandleTopicSummaryProvider,
        handles: tuple[str, ...],
        config: HandleSummaryTriggerConfig,
        poll_interval: float = 2.0,
        concurrency: int = 1,
        lease_ms: int = 120_000,
        reconcile_limit: int = 100,
    ) -> None:
        self.repository_session = repository_session
        self.provider = provider
        self.handles = tuple(handles)
        self.config = config
        self.poll_interval = max(1.0, float(poll_interval))
        self.concurrency = max(1, int(concurrency))
        self.lease_ms = max(1_000, int(lease_ms))
        self.provider_timeout_seconds = max(1.0, (self.lease_ms - 1_000) / 1000)
        self.reconcile_limit = max(1, int(reconcile_limit))
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await self.run_once_async()
            except asyncio.CancelledError:
                self._stopped = True
                raise
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"watchlist handle summary worker failed: {exc}")
            if not self._stopped:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped = True

    async def aclose(self) -> None:
        close = getattr(self.provider, "aclose", None)
        if close is not None:
            await close()
            return
        close_sync = getattr(self.provider, "close", None)
        if close_sync is not None:
            close_sync()

    async def run_once_async(self, *, now_ms: int | None = None) -> dict[str, int]:
        started_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = started_at_ms
        self.last_error = None
        reconcile = self.reconcile_missing_jobs_once(now_ms=started_at_ms)
        process = await self.process_due_jobs_once_async(now_ms=started_at_ms)
        result = {**{f"reconcile_{key}": value for key, value in reconcile.items()}, **process}
        self.last_result = result
        self.last_run_at_ms = _now_ms()
        return result

    def reconcile_missing_jobs_once(self, *, now_ms: int | None = None) -> dict[str, int]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        since_ms = resolved_now_ms - max(1, int(self.config.window_days)) * 24 * 60 * 60 * 1000
        result = {"seen": 0, "enqueued": 0, "skipped": 0}
        with self.repository_session() as repos:
            rows = repos.watchlist_intel.handles_missing_summary_jobs(
                handles=self.handles,
                since_ms=since_ms,
                limit=self.reconcile_limit,
            )
            service = WatchlistHandleSummaryService(
                repository=repos.watchlist_intel,
                provider=self.provider,
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

    async def process_due_jobs_once_async(self, *, now_ms: int | None = None) -> dict[str, int]:
        result = {"claimed": 0, "processed": 0, "failed": 0}
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        jobs: list[dict[str, Any]] = []
        for _ in range(self.concurrency):
            with self.repository_session() as repos:
                job = repos.watchlist_intel.claim_next_summary_job(
                    now_ms=resolved_now_ms,
                    lease_ms=self.lease_ms,
                )
            if job is None:
                break
            jobs.append(job)
        result["claimed"] = len(jobs)
        if not jobs:
            return result
        outcomes = await asyncio.gather(
            *(self._process_job(job, now_ms=resolved_now_ms) for job in jobs),
            return_exceptions=False,
        )
        for outcome in outcomes:
            result[outcome] += 1
        return result

    async def _process_job(self, job: dict[str, Any], *, now_ms: int) -> str:
        try:
            with self.repository_session() as repos:
                service = WatchlistHandleSummaryService(
                    repository=repos.watchlist_intel,
                    provider=self.provider,
                    config=self.config,
                )
                await asyncio.wait_for(
                    service.summarize_handle(job, now_ms=now_ms),
                    timeout=self.provider_timeout_seconds,
                )
        except Exception as exc:
            logger.warning(
                "watchlist handle summary job failed: handle={} error={}",
                job.get("handle"),
                str(exc)[:300],
            )
            with suppress(Exception), self.repository_session() as repos:
                repos.watchlist_intel.insert_summary_run(
                    run_id=f"watchlist-summary-failed-{job.get('handle')}-{job.get('attempt_count')}-{now_ms}",
                    handle=str(job.get("handle") or ""),
                    status="failed",
                    model=str(getattr(self.provider, "model", "") or ""),
                    request_json={"job": dict(job)},
                    response_json=None,
                    input_event_count=0,
                    usage_json={},
                    error=str(exc),
                    started_at_ms=now_ms,
                    finished_at_ms=_now_ms(),
                    commit=False,
                )
                repos.watchlist_intel.mark_summary_job_failed(job, str(exc), now_ms=now_ms, commit=True)
            return "failed"
        return "processed"


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["HandleSummaryWorker"]
