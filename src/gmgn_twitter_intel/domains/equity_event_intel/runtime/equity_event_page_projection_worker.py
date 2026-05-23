from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.equity_event_intel.services.page_projection import (
    build_equity_company_timeline_row,
    build_equity_event_alert_candidate,
    build_equity_event_calendar_row,
    build_equity_event_page_row,
)


class EquityEventPageProjectionWorker(WorkerBase):
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
        page_rows: list[dict[str, Any]] = []
        timeline_rows: list[dict[str, Any]] = []
        alert_rows: list[dict[str, Any]] = []
        calendar_rows: list[dict[str, Any]] = []
        company_event_ids: list[str] = []
        expected_event_ids: list[str] = []
        inactive_expected_event_ids: list[str] = []

        with self._repository_session() as repos:
            for payload in repos.equity_events.list_events_for_page_projection(limit=self._batch_size()):
                event, company, story, facts, documents, brief = _event_projection_parts(payload)
                page_row = build_equity_event_page_row(
                    event=event,
                    company=company,
                    story=story,
                    facts=facts,
                    documents=documents,
                    brief=brief,
                    computed_at_ms=now,
                )
                page_rows.append(page_row)
                timeline_rows.append(build_equity_company_timeline_row(page_row=page_row, computed_at_ms=now))
                alert = build_equity_event_alert_candidate(
                    event=event,
                    page_row=page_row,
                    facts=page_row["facts_json"],
                    computed_at_ms=now,
                )
                if alert is not None:
                    alert_rows.append(alert)
                company_event_ids.append(str(event["company_event_id"]))

            for payload in repos.equity_events.list_expected_events_for_calendar_projection(limit=self._batch_size()):
                expected_event, observed_event, company = _calendar_projection_parts(payload)
                calendar_rows.append(
                    build_equity_event_calendar_row(
                        expected_event=expected_event,
                        observed_event=observed_event,
                        company=company,
                        now_ms=now,
                        computed_at_ms=now,
                    )
                )
                expected_event_ids.append(str(expected_event["expected_event_id"]))
            inactive_expected_event_ids = repos.equity_events.list_inactive_expected_event_ids_for_calendar_projection(
                limit=self._batch_size()
            )

            if company_event_ids:
                repos.equity_events.replace_page_rows(company_event_ids=company_event_ids, rows=page_rows, commit=False)
                repos.equity_events.replace_alert_candidates(
                    company_event_ids=company_event_ids,
                    rows=alert_rows,
                    commit=False,
                )
                repos.equity_events.replace_company_timeline_rows(
                    rows=timeline_rows,
                    company_event_ids=company_event_ids,
                    commit=False,
                )
            if expected_event_ids:
                repos.equity_events.replace_calendar_rows(
                    expected_event_ids=expected_event_ids,
                    rows=calendar_rows,
                    commit=False,
                )
            if inactive_expected_event_ids:
                repos.equity_events.replace_calendar_rows(
                    expected_event_ids=inactive_expected_event_ids,
                    rows=[],
                    commit=False,
                )
            repos.conn.commit()

        processed = (
            len(set(company_event_ids))
            + len(set(expected_event_ids))
            + len(set(inactive_expected_event_ids))
        )
        if processed and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_page_updated(count=processed)
        return WorkerResult(
            processed=processed,
            notes={
                "projection_version": EQUITY_EVENT_PAGE_PROJECTION_VERSION,
                "page_rows": len(page_rows),
                "calendar_rows": len(calendar_rows),
                "alert_candidates": len(alert_rows),
                "timeline_rows": len(timeline_rows),
            },
        )

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))


def _event_projection_parts(
    payload: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    event = dict(payload.get("event") or payload)
    company = payload.get("company")
    story = payload.get("story")
    brief = payload.get("brief")
    return (
        event,
        dict(company) if company is not None else None,
        dict(story) if story is not None else None,
        [dict(row) for row in payload.get("facts") or []],
        [dict(row) for row in payload.get("documents") or []],
        dict(brief) if brief is not None else None,
    )


def _calendar_projection_parts(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    expected_event = dict(payload.get("expected_event") or payload)
    observed_event = payload.get("observed_event")
    company = payload.get("company")
    return (
        expected_event,
        dict(observed_event) if observed_event is not None else None,
        dict(company) if company is not None else None,
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["EquityEventPageProjectionWorker"]
