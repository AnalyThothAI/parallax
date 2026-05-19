from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_page_projection import build_news_page_row


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
        news_item_ids: list[str] = []
        rows: list[dict[str, Any]] = []

        with self._repository_session() as repos:
            for payload in repos.news.list_items_for_page_projection(limit=self._batch_size()):
                item, story, token_mentions, fact_candidates = _projection_parts(payload)
                news_item_id = str(item["news_item_id"])
                rows.append(
                    build_news_page_row(
                        item=item,
                        story=story,
                        token_mentions=token_mentions,
                        fact_candidates=fact_candidates,
                        computed_at_ms=now,
                    )
                )
                news_item_ids.append(news_item_id)
            if news_item_ids:
                repos.news.replace_page_rows_for_items(news_item_ids=news_item_ids, rows=rows)

        return WorkerResult(processed=len(rows), notes={"projection_version": NEWS_PAGE_PROJECTION_VERSION})

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))


def _projection_parts(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    item = dict(payload.get("item") or payload)
    story = payload.get("story")
    return (
        item,
        dict(story) if story is not None else None,
        [dict(row) for row in payload.get("token_mentions") or []],
        [dict(row) for row in payload.get("fact_candidates") or []],
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsPageProjectionWorker"]
