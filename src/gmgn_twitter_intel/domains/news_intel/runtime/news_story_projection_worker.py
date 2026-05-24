from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_story_grouping import (
    choose_story_assignment,
    new_story_id,
)


class NewsStoryProjectionWorker(WorkerBase):
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
                    claimed = repos.news_projection_dirty_targets.claim_due(
                        limit=self._batch_size(),
                        lease_ms=self._lease_ms(),
                        now_ms=now,
                        lease_owner=self.name,
                        projection_name="story",
                        commit=False,
                    )
                    if not claimed:
                        result = WorkerResult(processed=0, notes=_notes(claimed=0, story_rows=0, marked_error=0))
                        return result

                    try:
                        items = repos.news.load_items_for_story_projection(news_item_ids=_target_ids(claimed))
                    except Exception as exc:
                        marked_error = repos.news_projection_dirty_targets.mark_error(
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
                            story_rows = _write_story_rows(repos=repos, items=items, now_ms=now)
                            downstream_targets = _page_dirty_targets(items, source_watermark_ms=now)
                            if downstream_targets:
                                repos.news_projection_dirty_targets.enqueue_targets(
                                    downstream_targets,
                                    reason="news_story_projected",
                                    now_ms=now,
                                    commit=False,
                                )
                            repos.news_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)
                    except Exception as exc:
                        marked_error = repos.news_projection_dirty_targets.mark_error(
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

                    result = WorkerResult(
                        processed=len(_processed_target_ids(claimed)),
                        notes=_notes(claimed=len(claimed), story_rows=story_rows, marked_error=marked_error),
                    )
            except Exception as exc:
                if claimed:
                    with _transaction(repos.conn):
                        marked_error = repos.news_projection_dirty_targets.mark_error(
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
            raise RuntimeError("news story projection worker finished without a result")
        if story_rows > 0 and self.wake_bus is not None:
            self.wake_bus.notify_news_story_updated(count=story_rows)
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


def _write_story_rows(*, repos: Any, items: Iterable[Mapping[str, Any]], now_ms: int) -> int:
    story_rows = 0
    for item in items:
        item_payload = dict(item)
        candidates = repos.news.find_story_candidates_for_item(item_payload)
        assignment = choose_story_assignment(item=item_payload, candidates=[dict(row) for row in candidates])
        if assignment.story_id is None:
            story_id = new_story_id(news_item_id=str(item_payload["news_item_id"]))
            relation = "representative"
            repos.news.create_story_from_item(
                story_id=story_id,
                item=item_payload,
                policy_version=NEWS_STORY_POLICY_VERSION,
                now_ms=now_ms,
                commit=False,
            )
        else:
            story_id = assignment.story_id
            relation = assignment.relation
            repos.news.refresh_story_from_member(story_id=story_id, item=item_payload, now_ms=now_ms, commit=False)
        repos.news.add_story_member(
            story_id=story_id,
            news_item_id=str(item_payload["news_item_id"]),
            relation=relation,
            match_reason=assignment.match_reason,
            match_score=assignment.match_score,
            now_ms=now_ms,
            commit=False,
        )
        story_rows += 1
    return story_rows


def _page_dirty_targets(items: Iterable[Mapping[str, Any]], *, source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": str(item["news_item_id"]),
            "source_watermark_ms": int(source_watermark_ms),
        }
        for item in items
    ]


def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == "story"
            and str(row.get("target_kind") or "") == "news_item"
            and str(row.get("window") or "") == ""
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
        "policy_version": NEWS_STORY_POLICY_VERSION,
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


__all__ = ["NewsStoryProjectionWorker"]
