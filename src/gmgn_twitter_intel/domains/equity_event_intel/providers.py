from __future__ import annotations

from typing import Any, Protocol


class EquityDocumentFetchResult(Protocol):
    status_code: int
    documents: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool


class EquityEventDocumentProvider(Protocol):
    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentFetchResult: ...

    def close(self) -> None: ...


__all__ = ["EquityDocumentFetchResult", "EquityEventDocumentProvider"]
