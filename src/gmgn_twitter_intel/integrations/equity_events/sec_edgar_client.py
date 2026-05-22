from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class SecEdgarSubmissionFetchResult:
    status_code: int
    payload: dict[str, Any] = field(default_factory=dict)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class SecEdgarClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized_user_agent = str(user_agent or "").strip()
        if not normalized_user_agent:
            raise ValueError("SEC EDGAR User-Agent is required")
        self._client = httpx.Client(
            timeout=max(0.1, float(timeout_seconds)),
            headers={"User-Agent": normalized_user_agent},
            follow_redirects=True,
            transport=transport,
        )

    def fetch_company_submissions(
        self,
        cik: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> SecEdgarSubmissionFetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        response = self._client.get(_company_submissions_url(cik), headers=headers)
        if response.status_code == 304:
            return SecEdgarSubmissionFetchResult(
                status_code=304,
                etag=response.headers.get("etag") or etag,
                last_modified=response.headers.get("last-modified") or last_modified,
                not_modified=True,
            )
        response.raise_for_status()
        return SecEdgarSubmissionFetchResult(
            status_code=response.status_code,
            payload=response.json(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            not_modified=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def _company_submissions_url(cik: str) -> str:
    digits = "".join(character for character in str(cik) if character.isdigit())
    if not digits:
        raise ValueError("SEC EDGAR CIK is required")
    cik10 = digits.zfill(10)
    return f"https://data.sec.gov/submissions/CIK{cik10}.json"


__all__ = ["SecEdgarClient", "SecEdgarSubmissionFetchResult"]
