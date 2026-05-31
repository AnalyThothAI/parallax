from __future__ import annotations

from typing import Any, Protocol


class NewsReadModel(Protocol):
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
    ) -> dict[str, Any]: ...

    def get_item(self, *, news_item_id: str) -> dict[str, Any] | None: ...

    def get_fact(self, *, fact_candidate_id: str) -> dict[str, Any] | None: ...

    def source_status(self) -> list[dict[str, Any]]: ...


__all__ = ["NewsReadModel"]
