from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.services.company_identity import validate_company_identity
from gmgn_twitter_intel.domains.equity_event_intel.services.event_classifier import classify_equity_event
from gmgn_twitter_intel.domains.equity_event_intel.services.fact_candidates import (
    build_fact_candidates,
    build_source_spans,
    document_text,
)


class EquityEventProcessWorker(WorkerBase):
    def __init__(
        self,
        *,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            documents = repos.equity_events.list_unprocessed_event_documents(limit=self._batch_size())
        if not documents:
            return WorkerResult(skipped=1, notes={"reason": "no_unprocessed_documents"})

        processed = 0
        failed = 0
        for document in documents:
            event_document_id = str(document["event_document_id"])
            try:
                identity = validate_company_identity(document)
                event = classify_equity_event(document)
                text = document_text(document)
                spans = build_source_spans(
                    company_event_id=event.company_event_id,
                    event_document_id=event_document_id,
                    source_id=document.get("source_id"),
                    text=text,
                    now_ms=now,
                )
                source_span_id = spans[0].span_id if spans else ""
                candidates = (
                    build_fact_candidates(
                        company_event_id=event.company_event_id,
                        event_document_id=event_document_id,
                        source_span_id=source_span_id,
                        company_id=event.company_id,
                        ticker=event.ticker,
                        event_type=event.event_type,
                        period=event.fiscal_period,
                        source_role=event.source_role,
                        title=event.summary,
                        body_text=text,
                        now_ms=now,
                    )
                    if source_span_id
                    else []
                )
                with self._repository_session() as repos:
                    old_company_event_ids = repos.equity_events.company_event_ids_for_document(
                        event_document_id=event_document_id
                    )
                    repos.equity_events.clear_story_members_for_document(
                        event_document_id=event_document_id,
                        active_company_event_id=event.company_event_id,
                        now_ms=now,
                        commit=False,
                    )
                    repos.equity_events.upsert_company_event(
                        company_event_id=event.company_event_id,
                        company_id=event.company_id,
                        ticker=event.ticker,
                        primary_document_id=event.primary_document_id,
                        event_type=event.event_type,
                        priority=event.priority,
                        source_role=event.source_role,
                        fiscal_period=event.fiscal_period,
                        event_time_ms=event.event_time_ms,
                        discovered_at_ms=event.discovered_at_ms,
                        lifecycle_status=event.lifecycle_status,
                        validation_status=identity.validation_status,
                        summary=event.summary,
                        now_ms=now,
                        commit=False,
                    )
                    repos.equity_events.replace_source_spans(
                        event_document_id=event_document_id,
                        company_event_id=event.company_event_id,
                        spans=spans,
                        commit=False,
                    )
                    repos.equity_events.replace_fact_candidates(
                        event_document_id=event_document_id,
                        company_event_id=event.company_event_id,
                        candidates=candidates,
                        commit=False,
                    )
                    repos.equity_events.mark_event_document_processed(
                        event_document_id=event_document_id,
                        processed_at_ms=now,
                        commit=False,
                    )
                    company_event_ids = _unique_ids([event.company_event_id, *old_company_event_ids])
                    expected_event_ids = repos.equity_events.matching_expected_event_ids_for_company_events(
                        company_event_ids=company_event_ids
                    )
                    dirty_targets = _company_event_dirty_targets(
                        company_event_ids=company_event_ids,
                        source_watermark_ms=now,
                    )
                    dirty_targets.extend(
                        _expected_event_dirty_targets(
                            expected_event_ids=expected_event_ids,
                            source_watermark_ms=now,
                        )
                    )
                    repos.equity_projection_dirty_targets.enqueue_targets(
                        dirty_targets,
                        reason="event_processed",
                        now_ms=now,
                        commit=False,
                    )
                    repos.conn.commit()
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive worker path.
                failed += 1
                self._mark_document_failed(event_document_id=event_document_id, error=exc, now_ms=now)

        if processed > 0 and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_processed(count=processed)
        return WorkerResult(processed=processed, failed=failed, notes={"claimed": len(documents)})

    def _mark_document_failed(self, *, event_document_id: str, error: Exception, now_ms: int) -> None:
        try:
            with self._repository_session() as repos:
                repos.equity_events.mark_event_document_process_failed(
                    event_document_id=event_document_id,
                    error=str(error)[:2_000],
                    now_ms=now_ms,
                )
        except Exception:
            return

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _company_event_dirty_targets(*, company_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": projection_name,
            "target_kind": "company_event",
            "target_id": company_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for company_event_id in company_event_ids
        for projection_name in ("story", "brief_input", "page", "timeline", "alert")
    ]


def _expected_event_dirty_targets(*, expected_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": "calendar",
            "target_kind": "expected_event",
            "target_id": expected_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for expected_event_id in expected_event_ids
    ]


def _unique_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = ["EquityEventProcessWorker"]
