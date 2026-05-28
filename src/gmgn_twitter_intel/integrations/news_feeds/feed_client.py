from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import feedparser
import httpx


@dataclass(frozen=True, slots=True)
class FeedFetchResult:
    status_code: int
    entries: list[dict[str, Any]] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    feed: dict[str, Any] = field(default_factory=dict)
    next_cursor: dict[str, Any] = field(default_factory=dict)


class FeedClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        user_agent: str = "gmgn-twitter-intel/1.0",
        max_attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._client = httpx.Client(
            timeout=max(0.1, float(timeout_seconds)),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            transport=transport,
        )

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        provider_type: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> FeedFetchResult:
        del provider_type, source
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = self._get_with_retry(str(url), headers=headers)
        if response.status_code == 304:
            return FeedFetchResult(
                status_code=304,
                etag=response.headers.get("etag") or etag,
                last_modified=response.headers.get("last-modified") or last_modified,
                not_modified=True,
            )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        return FeedFetchResult(
            status_code=response.status_code,
            entries=[dict(entry) for entry in parsed.entries],
            etag=response.headers.get("etag") or getattr(parsed, "etag", None),
            last_modified=response.headers.get("last-modified") or getattr(parsed, "modified", None),
            not_modified=False,
            feed=dict(getattr(parsed, "feed", {}) or {}),
        )

    def _get_with_retry(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(url, headers=headers)
            except httpx.TransportError:
                if attempt >= self._max_attempts:
                    raise
                continue
            if response.status_code >= 500 and attempt < self._max_attempts:
                continue
            return response
        raise RuntimeError("unreachable feed retry state")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FeedClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
