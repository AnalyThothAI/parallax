from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
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
        processed = 0
        with self._repository_session() as repos:
            for item in repos.news.list_items_missing_story(limit=self._batch_size()):
                candidates = repos.news.find_story_candidates_for_item(item)
                assignment = choose_story_assignment(item=dict(item), candidates=[dict(row) for row in candidates])
                if assignment.story_id is None:
                    story_id = new_story_id(news_item_id=str(item["news_item_id"]))
                    relation = "representative"
                    repos.news.create_story_from_item(
                        story_id=story_id,
                        item=item,
                        policy_version=NEWS_STORY_POLICY_VERSION,
                        now_ms=now,
                    )
                else:
                    story_id = assignment.story_id
                    relation = assignment.relation
                    repos.news.refresh_story_from_member(story_id=story_id, item=item, now_ms=now)
                repos.news.add_story_member(
                    story_id=story_id,
                    news_item_id=str(item["news_item_id"]),
                    relation=relation,
                    match_reason=assignment.match_reason,
                    match_score=assignment.match_score,
                    now_ms=now,
                )
                processed += 1

        if processed > 0 and self.wake_bus is not None:
            self.wake_bus.notify_news_story_updated(count=processed)
        return WorkerResult(processed=processed, notes={"policy_version": NEWS_STORY_POLICY_VERSION})

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsStoryProjectionWorker"]
