from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import news_page_cursor


class NewsPageQuery:
    def __init__(self, *, repository: Any):
        self.repository = repository

    def list_news(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        lane: str | None = None,
        source: str | None = None,
        target: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        rows = self.repository.list_news_page_rows(
            limit=max(1, int(limit)),
            cursor=cursor,
            status=status,
            lane=lane,
            source=source,
            target=target,
            q=q,
        )
        next_cursor = news_page_cursor(rows[-1]) if rows else None
        return {"items": rows, "next_cursor": next_cursor}

    def get_item(self, *, news_item_id: str) -> dict[str, Any] | None:
        return self.repository.get_news_item_detail(news_item_id=news_item_id)

    def get_story(self, *, story_id: str) -> dict[str, Any] | None:
        return self.repository.get_news_story_detail(story_id=story_id)

    def get_fact(self, *, fact_candidate_id: str) -> dict[str, Any] | None:
        return self.repository.get_news_fact_detail(fact_candidate_id=fact_candidate_id)

    def source_status(self) -> list[dict[str, Any]]:
        return self.repository.list_source_status()
