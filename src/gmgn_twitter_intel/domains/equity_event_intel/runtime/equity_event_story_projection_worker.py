from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_STORY_POLICY_VERSION
from gmgn_twitter_intel.domains.equity_event_intel.services.story_grouping import (
    choose_story_assignment,
    new_story_id,
)


class EquityEventStoryProjectionWorker(WorkerBase):
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
        claimed: list[dict[str, Any]] = []
        story_rows = 0
        marked_error = 0
        result: WorkerResult | None = None

        with self._repository_session() as repos:
            try:
                with _transaction(repos.conn):
                    claimed = repos.equity_projection_dirty_targets.claim_due(
                        limit=self._batch_size(),
                        lease_ms=self._lease_ms(),
                        now_ms=now,
                        lease_owner=self.name,
                        projection_name="story",
                        target_kind="company_event",
                        commit=False,
                    )
                    if not claimed:
                        result = WorkerResult(
                            processed=0,
                            notes=_notes(claimed=0, story_rows=0, marked_error=0),
                        )
                        return result

                    try:
                        events = repos.equity_events.load_events_for_story_projection(
                            company_event_ids=_target_ids(claimed),
                        )
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
                            notes=_notes(claimed=len(claimed), story_rows=0, marked_error=marked_error),
                        )
                        return result

                    try:
                        with _transaction(repos.conn):
                            story_rows = _write_story_rows(repos=repos, events=events, now_ms=now)
                            downstream_targets = _downstream_targets(events, source_watermark_ms=now)
                            if downstream_targets:
                                repos.equity_projection_dirty_targets.enqueue_targets(
                                    downstream_targets,
                                    reason="story_projected",
                                    now_ms=now,
                                    commit=False,
                                )
                            repos.equity_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)
                    except Exception as exc:
                        story_rows = 0
                        marked_error = repos.equity_projection_dirty_targets.mark_error(
                            claimed,
                            error=str(exc),
                            retry_ms=self._retry_ms(),
                            now_ms=now,
                            commit=False,
                        )
                        result = WorkerResult(
                            failed=len(claimed),
                            notes=_notes(claimed=len(claimed), story_rows=0, marked_error=marked_error),
                        )
                        return result

                    processed = len(_processed_target_ids(claimed))
                    result = WorkerResult(
                        processed=processed,
                        notes=_notes(claimed=len(claimed), story_rows=story_rows, marked_error=marked_error),
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
                    notes=_notes(claimed=len(claimed), story_rows=story_rows, marked_error=marked_error),
                )

        if result is None:
            raise RuntimeError("equity event story projection worker finished without a result")
        if story_rows > 0 and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_story_updated(count=story_rows)
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


def _write_story_rows(*, repos: Any, events: Iterable[Mapping[str, Any]], now_ms: int) -> int:
    story_rows = 0
    for event in events:
        event_payload = dict(event)
        current_story_id = str(event_payload.get("current_story_id") or "")
        if current_story_id:
            story_id = current_story_id
            relation = str(event_payload.get("current_story_relation") or "member")
            match_reason = "existing_membership"
            match_score = 1.0
            repos.equity_events.refresh_story_from_member(
                story_id=story_id,
                event=event_payload,
                now_ms=now_ms,
                commit=False,
            )
        else:
            candidates = repos.equity_events.find_story_candidates_for_event(event_payload)
            assignment = choose_story_assignment(event=event_payload, candidates=[dict(row) for row in candidates])
            match_reason = assignment.match_reason
            match_score = assignment.match_score
            if assignment.story_id is not None:
                story_id = assignment.story_id
                relation = assignment.relation
                repos.equity_events.refresh_story_from_member(
                    story_id=story_id,
                    event=event_payload,
                    now_ms=now_ms,
                    commit=False,
                )
            else:
                story_id = new_story_id(company_event_id=str(event_payload["company_event_id"]))
                relation = "representative"
                repos.equity_events.create_story_from_event(
                    story_id=story_id,
                    event=event_payload,
                    policy_version=EQUITY_EVENT_STORY_POLICY_VERSION,
                    now_ms=now_ms,
                    commit=False,
                )
        repos.equity_events.add_story_member(
            story_id=story_id,
            company_event_id=str(event_payload["company_event_id"]),
            relation=relation,
            match_reason=match_reason,
            match_score=match_score,
            now_ms=now_ms,
            commit=False,
        )
        story_rows += 1
    return story_rows


def _downstream_targets(events: Iterable[Mapping[str, Any]], *, source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": projection_name,
            "target_kind": "company_event",
            "target_id": str(event["company_event_id"]),
            "source_watermark_ms": int(source_watermark_ms),
        }
        for event in events
        for projection_name in ("page", "timeline", "alert")
    ]


def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == "story" and str(row.get("target_kind") or "") == "company_event"
        ]
    )


def _processed_target_ids(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    return set(_target_ids(rows))


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


def _notes(*, claimed: int, story_rows: int, marked_error: int) -> dict[str, int | str]:
    return {
        "policy_version": EQUITY_EVENT_STORY_POLICY_VERSION,
        "claimed": int(claimed),
        "story_rows": int(story_rows),
        "marked_error": int(marked_error),
    }


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["EquityEventStoryProjectionWorker"]
