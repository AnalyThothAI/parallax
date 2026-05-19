from __future__ import annotations

from typing import Any, Protocol


class NewsFeedFetchResult(Protocol):
    status_code: int
    entries: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool


class NewsFeedProvider(Protocol):
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> NewsFeedFetchResult: ...

    def close(self) -> None: ...


__all__ = ["NewsFeedFetchResult", "NewsFeedProvider"]
