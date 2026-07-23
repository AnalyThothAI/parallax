from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel.queries.news_page_query import NewsPageQuery


def test_news_page_query_uses_positive_limit_with_lookahead() -> None:
    repository = FakeNewsRepository(
        rows=[
            {"row_id": "row-2", "news_item_id": "news-2", "latest_at_ms": 2, "computed_at_ms": 2},
            {"row_id": "row-1", "news_item_id": "news-1", "latest_at_ms": 1, "computed_at_ms": 1},
        ]
    )

    result = NewsPageQuery(page_repository=repository, source_repository=repository).list_news(limit=1)

    assert [item["news_item_id"] for item in result["items"]] == ["news-2"]
    assert repository.calls == [{"limit": 2, "cursor": None, "status": None, "q": None}]


@pytest.mark.parametrize("limit", [0, -1, True, "10"])
def test_news_page_query_rejects_malformed_limit_before_repository_call(limit: object) -> None:
    repository = FakeNewsRepository(rows=[])

    with pytest.raises(ValueError, match="news_page_query_limit_required"):
        NewsPageQuery(page_repository=repository, source_repository=repository).list_news(  # type: ignore[arg-type]
            limit=limit
        )

    assert repository.calls == []


class FakeNewsRepository:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def list_news_page_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(kwargs))
        return self.rows[: kwargs["limit"]]
