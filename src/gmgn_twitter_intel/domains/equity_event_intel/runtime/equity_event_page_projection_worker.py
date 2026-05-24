from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
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

_PROJECTION_NAMES = ("page", "timeline", "alert", "calendar")
_COMPANY_EVENT_PROJECTIONS = frozenset({"page", "timeline", "alert"})
_CALENDAR_PROJECTIONS = frozenset({"calendar"})


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
        self._claim_projection_cursor = 0

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        claimed: list[dict[str, Any]] = []
        page_rows: list[dict[str, Any]] = []
        timeline_rows: list[dict[str, Any]] = []
        alert_rows: list[dict[str, Any]] = []
        calendar_rows: list[dict[str, Any]] = []
        deleted = 0
        marked_error = 0
        result: WorkerResult | None = None
        notify_count = 0

        with self._repository_session() as repos:
            try:
                with _transaction(repos.conn):
                    claimed = self._claim_due_targets(repos=repos, now_ms=now)
                    if not claimed:
                        result = WorkerResult(
                            processed=0,
                            notes=_notes(
                                claimed=0,
                                page_rows=0,
                                calendar_rows=0,
                                alert_rows=0,
                                timeline_rows=0,
                                deleted=0,
                                marked_error=0,
                            ),
                        )
                        return result

                    page_ids = _target_ids_for_projection(claimed, projection_name="page", target_kind="company_event")
                    timeline_ids = _target_ids_for_projection(
                        claimed,
                        projection_name="timeline",
                        target_kind="company_event",
                    )
                    alert_ids = _target_ids_for_projection(
                        claimed,
                        projection_name="alert",
                        target_kind="company_event",
                    )
                    company_event_ids = _unique_values([*page_ids, *timeline_ids, *alert_ids])
                    expected_event_ids = _target_ids_for_projection(
                        claimed,
                        projection_name="calendar",
                        target_kind="expected_event",
                    )
                    try:
                        event_payloads = (
                            repos.equity_events.load_event_page_projection_payloads(company_event_ids=company_event_ids)
                            if company_event_ids
                            else []
                        )
                        calendar_payloads = (
                            repos.equity_events.load_expected_calendar_projection_payloads(
                                expected_event_ids=expected_event_ids,
                                now_ms=now,
                            )
                            if expected_event_ids
                            else []
                        )
                        loaded_expected_event_ids: list[str] = []
                        page_rows_by_event_id: dict[str, dict[str, Any]] = {}
                        timeline_rows_by_event_id: dict[str, dict[str, Any]] = {}
                        alert_rows_by_event_id: dict[str, dict[str, Any]] = {}
                        for payload in event_payloads:
                            event, company, story, facts, documents, brief = _event_projection_parts(payload)
                            company_event_id = str(event["company_event_id"])
                            page_row = build_equity_event_page_row(
                                event=event,
                                company=company,
                                story=story,
                                facts=facts,
                                documents=documents,
                                brief=brief,
                                computed_at_ms=now,
                            )
                            page_rows_by_event_id[company_event_id] = page_row
                            timeline_rows_by_event_id[company_event_id] = build_equity_company_timeline_row(
                                page_row=page_row,
                                computed_at_ms=now,
                            )
                            alert = build_equity_event_alert_candidate(
                                event=event,
                                page_row=page_row,
                                facts=page_row["facts_json"],
                                computed_at_ms=now,
                            )
                            if alert is not None:
                                alert_rows_by_event_id[company_event_id] = alert

                        for payload in calendar_payloads:
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
                            loaded_expected_event_ids.append(str(expected_event["expected_event_id"]))

                        future_calendar_targets = _future_calendar_targets(calendar_rows, now_ms=now)
                    except Exception as exc:
                        marked_error = repos.equity_projection_dirty_targets.mark_error(
                            claimed,
                            error=str(exc),
                            retry_ms=self._retry_ms(),
                            now_ms=now,
                            commit=False,
                        )
                        result = WorkerResult(
                            failed=len(claimed),
                            notes=_notes(
                                claimed=len(claimed),
                                page_rows=len(page_rows),
                                calendar_rows=len(calendar_rows),
                                alert_rows=len(alert_rows),
                                timeline_rows=len(timeline_rows),
                                deleted=deleted,
                                marked_error=marked_error,
                            ),
                        )
                        return result
                    deleted_before_projection_write = deleted
                    try:
                        with _transaction(repos.conn):
                            if page_ids:
                                page_rows = _rows_for_ids(page_rows_by_event_id, page_ids)
                                repos.equity_events.replace_page_rows(
                                    company_event_ids=page_ids,
                                    rows=page_rows,
                                    commit=False,
                                )
                                deleted += len(set(page_ids) - set(page_rows_by_event_id))
                            if alert_ids:
                                alert_rows = _rows_for_ids(alert_rows_by_event_id, alert_ids)
                                repos.equity_events.replace_alert_candidates(
                                    company_event_ids=alert_ids,
                                    rows=alert_rows,
                                    commit=False,
                                )
                                deleted += len(set(alert_ids) - set(alert_rows_by_event_id))
                            if timeline_ids:
                                timeline_rows = _rows_for_ids(timeline_rows_by_event_id, timeline_ids)
                                repos.equity_events.replace_company_timeline_rows(
                                    rows=timeline_rows,
                                    company_event_ids=timeline_ids,
                                    commit=False,
                                )
                                deleted += len(set(timeline_ids) - set(timeline_rows_by_event_id))
                            if expected_event_ids:
                                repos.equity_events.replace_calendar_rows(
                                    expected_event_ids=expected_event_ids,
                                    rows=calendar_rows,
                                    commit=False,
                                )
                                deleted += len(set(expected_event_ids) - set(loaded_expected_event_ids))
                    except Exception as exc:
                        deleted = deleted_before_projection_write
                        marked_error = repos.equity_projection_dirty_targets.mark_error(
                            claimed,
                            error=str(exc),
                            retry_ms=self._retry_ms(),
                            now_ms=now,
                            commit=False,
                        )
                        result = WorkerResult(
                            failed=len(claimed),
                            notes=_notes(
                                claimed=len(claimed),
                                page_rows=len(page_rows),
                                calendar_rows=len(calendar_rows),
                                alert_rows=len(alert_rows),
                                timeline_rows=len(timeline_rows),
                                deleted=deleted,
                                marked_error=marked_error,
                            ),
                        )
                        return result

                    repos.equity_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)
                    for target in future_calendar_targets:
                        repos.equity_projection_dirty_targets.enqueue_targets(
                            [target],
                            reason="calendar_status_boundary",
                            now_ms=now,
                            due_at_ms=int(target["due_at_ms"]),
                            commit=False,
                        )
                    processed = len(_processed_target_keys(claimed))
                    notify_count = processed
                    result = WorkerResult(
                        processed=processed,
                        notes=_notes(
                            claimed=len(claimed),
                            page_rows=len(page_rows),
                            calendar_rows=len(calendar_rows),
                            alert_rows=len(alert_rows),
                            timeline_rows=len(timeline_rows),
                            deleted=deleted,
                            marked_error=marked_error,
                        ),
                    )
            except Exception as exc:
                if claimed:
                    with _transaction(repos.conn):
                        marked_error = repos.equity_projection_dirty_targets.mark_error(
                            claimed,
                            error=str(exc),
                            retry_ms=self._retry_ms(),
                            now_ms=now,
                            commit=False,
                        )
                return WorkerResult(
                    failed=len(claimed) or 1,
                    notes=_notes(
                        claimed=len(claimed),
                        page_rows=len(page_rows),
                        calendar_rows=len(calendar_rows),
                        alert_rows=len(alert_rows),
                        timeline_rows=len(timeline_rows),
                        deleted=deleted,
                        marked_error=marked_error,
                    ),
                )

        if result is None:
            raise RuntimeError("equity event page projection worker finished without a result")
        if notify_count and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_page_updated(count=notify_count)
        return result

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", 120_000)))

    def _retry_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_ms", 30_000)))

    def _claim_due_targets(self, *, repos: Any, now_ms: int) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        remaining = self._batch_size()
        start_index = self._claim_projection_cursor % len(_PROJECTION_NAMES)
        projection_names = [*_PROJECTION_NAMES[start_index:], *_PROJECTION_NAMES[:start_index]]
        self._claim_projection_cursor = (start_index + 1) % len(_PROJECTION_NAMES)
        for projection_name in projection_names:
            if remaining <= 0:
                break
            rows = repos.equity_projection_dirty_targets.claim_due(
                limit=remaining,
                lease_ms=self._lease_ms(),
                now_ms=now_ms,
                lease_owner=self.name,
                projection_name=projection_name,
                commit=False,
            )
            claimed.extend(dict(row) for row in rows)
            remaining -= len(rows)
        return claimed


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


def _target_ids_for_projection(
    rows: Iterable[Mapping[str, Any]],
    *,
    projection_name: str,
    target_kind: str,
) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == projection_name
            and str(row.get("target_kind") or "") == target_kind
        ]
    )


def _unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _rows_for_ids(rows_by_id: Mapping[str, dict[str, Any]], target_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [rows_by_id[target_id] for target_id in target_ids if target_id in rows_by_id]


def _future_calendar_targets(rows: Iterable[Mapping[str, Any]], *, now_ms: int) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "") != "expected":
            continue
        due_at_ms = int(row["expected_at_ms"]) + 1
        if due_at_ms <= int(now_ms):
            continue
        targets.append(
            {
                "projection_name": "calendar",
                "target_kind": "expected_event",
                "target_id": str(row["expected_event_id"]),
                "source_watermark_ms": int(row.get("source_watermark_ms") or now_ms),
                "due_at_ms": due_at_ms,
            }
        )
    return targets


def _processed_target_keys(rows: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in rows:
        projection_name = str(row.get("projection_name") or "")
        target_kind = str(row.get("target_kind") or "")
        target_id = str(row.get("target_id") or "")
        if projection_name in _COMPANY_EVENT_PROJECTIONS and target_kind == "company_event":
            keys.add(("company_event", target_id))
        elif projection_name in _CALENDAR_PROJECTIONS and target_kind == "expected_event":
            keys.add(("expected_event", target_id))
    return keys


def _notes(
    *,
    claimed: int,
    page_rows: int,
    calendar_rows: int,
    alert_rows: int,
    timeline_rows: int,
    deleted: int,
    marked_error: int,
) -> dict[str, int | str]:
    return {
        "projection_version": EQUITY_EVENT_PAGE_PROJECTION_VERSION,
        "claimed": int(claimed),
        "page_rows": int(page_rows),
        "calendar_rows": int(calendar_rows),
        "alert_candidates": int(alert_rows),
        "timeline_rows": int(timeline_rows),
        "deleted": int(deleted),
        "marked_error": int(marked_error),
    }


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["EquityEventPageProjectionWorker"]
