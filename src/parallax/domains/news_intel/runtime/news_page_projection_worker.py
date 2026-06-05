from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_page_projection_work,
    mark_work_done,
    mark_work_error,
    page_news_item_ids,
)
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row


class NewsPageProjectionWorker(WorkerBase):
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
        rows: list[dict[str, Any]] = []
        deleted = 0
        unchanged = 0
        marked_error = 0
        story_groups_projected = 0
        story_member_items = 0

        with self._repository_session() as repos, _transaction(repos.conn):
            claimed = claim_page_projection_work(
                repos,
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                now_ms=now,
                lease_owner=self.name,
                commit=False,
            )
            if not claimed:
                return WorkerResult(
                    processed=0,
                    notes=_notes(
                        claimed=0,
                        projected=0,
                        deleted=0,
                        unchanged=0,
                        marked_error=0,
                        story_groups_projected=0,
                        story_member_items=0,
                    ),
                )

            claimed_ids = page_news_item_ids(claimed)
            try:
                with _transaction(repos.conn):
                    payloads = repos.news.load_story_projection_payloads_for_items(news_item_ids=claimed_ids)
                    story_keys: list[str] = []
                    member_item_ids: list[str] = []
                    for payload in payloads:
                        item, token_mentions, fact_candidates, current_brief, story, member_items = _projection_parts(
                            payload
                        )
                        rows.append(
                            build_news_page_row(
                                item=item,
                                token_mentions=token_mentions,
                                fact_candidates=fact_candidates,
                                agent_brief=current_brief,
                                story=story,
                                computed_at_ms=now,
                            )
                        )
                        story_key = str((story or {}).get("story_key") or item.get("story_key") or "")
                        if story_key:
                            story_keys.append(story_key)
                            story_groups_projected += 1
                        member_item_ids.extend(_member_news_item_ids(member_items=member_items, story=story, item=item))
                    story_member_items = len(set(member_item_ids))
            except Exception as exc:
                marked_error = mark_work_error(
                    repos,
                    claimed,
                    error=str(exc),
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                    commit=False,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(
                        claimed=len(claimed),
                        projected=0,
                        deleted=0,
                        unchanged=0,
                        marked_error=marked_error,
                        story_groups_projected=0,
                        story_member_items=0,
                    ),
                )

            try:
                with _transaction(repos.conn):
                    replacement = repos.news.replace_page_rows_for_story_targets(
                        news_item_ids=claimed_ids,
                        story_keys=story_keys,
                        rows=rows,
                        commit=False,
                    )
                    deleted = int(replacement.get("deleted", 0))
                    unchanged = int(replacement.get("unchanged", 0))
            except Exception as exc:
                marked_error = mark_work_error(
                    repos,
                    claimed,
                    error=str(exc),
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                    commit=False,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(
                        claimed=len(claimed),
                        projected=len(rows),
                        deleted=0,
                        unchanged=0,
                        marked_error=marked_error,
                        story_groups_projected=story_groups_projected,
                        story_member_items=story_member_items,
                    ),
                )

            mark_work_done(repos, claimed, now_ms=now, commit=False)

        return WorkerResult(
            processed=len(page_news_item_ids(claimed)),
            notes=_notes(
                claimed=len(claimed),
                projected=len(rows),
                deleted=deleted,
                unchanged=unchanged,
                marked_error=marked_error,
                story_groups_projected=story_groups_projected,
                story_member_items=story_member_items,
            ),
        )

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


def _projection_parts(
    payload: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
    list[dict[str, Any]],
]:
    item = dict(payload.get("item") or payload)
    current_brief = payload.get("current_brief")
    story = payload.get("story")
    return (
        item,
        [dict(row) for row in payload.get("token_mentions") or []],
        [dict(row) for row in payload.get("fact_candidates") or []],
        dict(current_brief) if current_brief is not None else None,
        dict(story) if story is not None else None,
        [dict(row) for row in payload.get("member_items") or []],
    )


def _member_news_item_ids(
    *,
    member_items: list[dict[str, Any]],
    story: Mapping[str, Any] | None,
    item: Mapping[str, Any],
) -> list[str]:
    member_ids = [str(row.get("news_item_id") or "") for row in member_items if str(row.get("news_item_id") or "")]
    if not member_ids and story:
        member_ids = [str(member_id) for member_id in story.get("member_news_item_ids") or [] if str(member_id)]
    if not member_ids:
        member_ids = [str(item["news_item_id"])]
    return member_ids


def _notes(
    *,
    claimed: int,
    projected: int,
    deleted: int,
    unchanged: int,
    marked_error: int,
    story_groups_projected: int,
    story_member_items: int,
) -> dict[str, int | str]:
    return {
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
        "claimed": int(claimed),
        "story_groups_projected": int(story_groups_projected),
        "story_member_items": int(story_member_items),
        "projected": int(projected),
        "deleted": int(deleted),
        "unchanged": int(unchanged),
        "marked_error": int(marked_error),
    }


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsPageProjectionWorker"]
