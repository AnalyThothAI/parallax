from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any

import httpx


class SecEdgarInvalidCikError(ValueError):
    pass


class SecEdgarInvalidJsonError(ValueError):
    pass


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
        min_interval_seconds: float = 0.11,
        max_attempts: int = 2,
        backoff_seconds: float = 0.5,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized_user_agent = str(user_agent or "").strip()
        if not normalized_user_agent:
            raise ValueError("SEC EDGAR User-Agent is required")
        self._min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._max_attempts = max(1, int(max_attempts))
        self._backoff_seconds = max(0.0, float(backoff_seconds))
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._last_request_at: float | None = None
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

        response = self._get_with_retry(_company_submissions_url(cik), headers=headers)
        if response.status_code == 304:
            return SecEdgarSubmissionFetchResult(
                status_code=304,
                etag=response.headers.get("etag") or etag,
                last_modified=response.headers.get("last-modified") or last_modified,
                not_modified=True,
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except JSONDecodeError as exc:
            raise SecEdgarInvalidJsonError("SEC EDGAR response was not valid JSON") from exc
        return SecEdgarSubmissionFetchResult(
            status_code=response.status_code,
            payload=payload,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            not_modified=False,
        )

    def _get_with_retry(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._pace()
            response = self._client.get(url, headers=headers)
            self._last_request_at = self._clock()
            if response.status_code not in {429} and response.status_code < 500:
                return response
            if attempt >= self._max_attempts:
                return response
            self._sleep(_retry_delay(response, attempt=attempt, fallback_seconds=self._backoff_seconds))
        if response is None:
            raise RuntimeError("unreachable SEC EDGAR retry state")
        return response

    def _pace(self) -> None:
        if self._last_request_at is None or self._min_interval_seconds <= 0:
            return
        elapsed = self._clock() - self._last_request_at
        delay = self._min_interval_seconds - elapsed
        if delay > 0:
            self._sleep(delay)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def _company_submissions_url(cik: str) -> str:
    digits = _normalize_cik(cik)
    if not digits:
        raise SecEdgarInvalidCikError("SEC EDGAR CIK is required")
    cik10 = digits.zfill(10)
    return f"https://data.sec.gov/submissions/CIK{cik10}.json"


def _normalize_cik(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("cik"):
        normalized = normalized[3:].strip()
    if not normalized.isdigit():
        raise SecEdgarInvalidCikError("SEC EDGAR CIK must be numeric or CIK-prefixed numeric")
    return normalized


def _retry_delay(response: httpx.Response, *, attempt: int, fallback_seconds: float) -> float:
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    if retry_after is not None:
        return retry_after
    return fallback_seconds * (2 ** max(0, attempt - 1))


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)


__all__ = [
    "SecEdgarClient",
    "SecEdgarInvalidCikError",
    "SecEdgarInvalidJsonError",
    "SecEdgarSubmissionFetchResult",
]
