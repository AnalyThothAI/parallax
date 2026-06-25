from __future__ import annotations

from typing import Any, cast

from parallax.domains.news_intel.repositories.news_repository import news_page_cursor


class NewsPageQuery:
    def __init__(self, *, repository: Any):
        self.repository = repository

    def list_news(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        signal: str | None = None,
        macro_event_flow: bool = False,
        q: str | None = None,
    ) -> dict[str, Any]:
        requested_limit = _required_positive_int(limit, "news_page_query_limit_required")
        options: dict[str, Any] = {}
        if macro_event_flow:
            options["macro_event_flow"] = True
        rows = self.repository.list_news_page_rows(
            limit=requested_limit + 1,
            cursor=cursor,
            status=status,
            signal=signal,
            q=q,
            **options,
        )
        items = [_public_news_row(row) for row in rows[:requested_limit]]
        next_cursor = news_page_cursor(items[-1]) if len(rows) > requested_limit and items else None
        return {"items": items, "next_cursor": next_cursor}

    def get_item(self, *, news_item_id: str) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.repository.get_news_item_detail(news_item_id=news_item_id))

    def get_fact(self, *, fact_candidate_id: str) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.repository.get_news_fact_detail(fact_candidate_id=fact_candidate_id))

    def source_status(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.repository.list_source_status())


def _public_news_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)
