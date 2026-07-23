from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from parallax.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)


class NewsSourceProviderError(RuntimeError):
    def __init__(self, error_code: str, *, status_code: int | None = None, terminal: bool = False) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.terminal = terminal


class NewsSourceProvider(Protocol):
    @property
    def provider_type(self) -> str: ...

    def fetch(
        self,
        source: NewsSourceSnapshot,
        *,
        since_ms: int | None = None,
        cursor: Mapping[str, Any] | None = None,
        cache: NewsSourceHttpCache | None = None,
        limit: int | None = None,
    ) -> NewsProviderFetchResult: ...

    def close(self) -> None: ...


__all__ = ["NewsSourceProvider", "NewsSourceProviderError"]
