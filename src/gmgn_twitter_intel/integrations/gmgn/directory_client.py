from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from curl_cffi import requests as curl_requests

DEFAULT_BASE_URL = "https://gmgn.ai"
DEFAULT_PATH = "/vas/api/v1/twitter/user/search"
DEFAULT_USER_TAGS: tuple[str, ...] = (
    "kol", "trader", "master", "politics", "media",
    "companies", "founder", "exchange", "celebrity",
    "binance_square", "other",
)
DEFAULT_LIMIT = 50
DEFAULT_FINGERPRINT: dict[str, str] = {
    "device_id": "06f9aeca-dc4b-43d3-b9d8-edb2d6ee1a23",
    "fp_did": "2e4701601dc44a62409f7c5d24bc5c49",
    "client_id": "gmgn_web_20260508-13058-10dbcde",
    "from_app": "gmgn",
    "app_ver": "20260508-13058-10dbcde",
    "tz_name": "Asia/Shanghai",
    "tz_offset": "28800",
    "app_lang": "zh-CN",
    "os": "web",
    "worker": "0",
}


class GmgnDirectoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GmgnDirectoryEntry:
    handle: str
    gmgn_user_id: str | None
    user_tags: tuple[str, ...]
    platform_followers: int | None


@dataclass(slots=True)
class GmgnDirectoryPage:
    entries: list[GmgnDirectoryEntry]
    next_page_token: str | None


class GmgnDirectoryClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        path: str = DEFAULT_PATH,
        user_tags: tuple[str, ...] = DEFAULT_USER_TAGS,
        limit: int = DEFAULT_LIMIT,
        timeout_seconds: float = 15.0,
        sleep_between_pages_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._path = path
        self._user_tags = tuple(user_tags)
        self._limit = int(limit)
        self._timeout_seconds = float(timeout_seconds)
        self._sleep_between_pages_seconds = float(sleep_between_pages_seconds)
        self._httpx_client: httpx.Client | None = None
        self._curl_session: curl_requests.Session | None = None
        if transport is not None:
            self._httpx_client = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=transport,
            )
        else:
            self._curl_session = curl_requests.Session(impersonate="chrome")

    def close(self) -> None:
        if self._httpx_client is not None:
            self._httpx_client.close()
        if self._curl_session is not None:
            self._curl_session.close()

    def fetch_page(self, *, page_token: str | None) -> GmgnDirectoryPage:
        params: list[tuple[str, str]] = list(DEFAULT_FINGERPRINT.items())
        params.append(("limit", str(self._limit)))
        params.append(("handle", ""))
        params.extend(("user_tags", tag) for tag in self._user_tags)
        if page_token:
            params.append(("page_token", page_token))
        envelope = self._send(params)
        data = envelope.get("data") or {}
        users = data.get("users") or []
        entries = [_entry_from_dict(item) for item in users if isinstance(item, dict)]
        next_token = data.get("page_token") or None
        return GmgnDirectoryPage(entries=entries, next_page_token=next_token)

    def iter_entries(self, *, max_pages: int = 200) -> Iterator[GmgnDirectoryEntry]:
        seen_handles: set[str] = set()
        page_token: str | None = None
        for page_index in range(max_pages):
            page = self.fetch_page(page_token=page_token)
            for entry in page.entries:
                normalized = entry.handle.strip().lower()
                if not normalized or normalized in seen_handles:
                    continue
                seen_handles.add(normalized)
                yield entry
            page_token = page.next_page_token
            if not page_token:
                return
            if self._sleep_between_pages_seconds > 0 and page_index + 1 < max_pages:
                time.sleep(self._sleep_between_pages_seconds)

    def _send(self, params: list[tuple[str, str]]) -> dict[str, Any]:
        if self._httpx_client is not None:
            response = self._httpx_client.get(self._path, params=params)
            status_code = response.status_code
            try:
                payload = response.json()
            except ValueError as exc:
                raise GmgnDirectoryError(
                    f"GET {self._path} returned non-JSON HTTP {status_code}"
                ) from exc
        elif self._curl_session is not None:
            response = self._curl_session.get(
                f"{self._base_url}{self._path}",
                params=params,
                timeout=self._timeout_seconds,
            )
            status_code = response.status_code
            try:
                payload = response.json()
            except ValueError as exc:
                raise GmgnDirectoryError(
                    f"GET {self._path} returned non-JSON HTTP {status_code}"
                ) from exc
        else:
            raise GmgnDirectoryError("client not initialized")
        if not isinstance(payload, dict):
            raise GmgnDirectoryError("response envelope is not a JSON object")
        if payload.get("code") != 0:
            message = payload.get("message") or payload.get("reason") or "unknown error"
            raise GmgnDirectoryError(str(message))
        return payload


def _entry_from_dict(item: dict[str, Any]) -> GmgnDirectoryEntry:
    handle = str(item.get("handle") or "").strip().lower()
    user_id_raw = item.get("user_id")
    user_id = str(user_id_raw) if user_id_raw is not None else None
    tags_raw = item.get("user_tags") or []
    user_tags = tuple(str(tag) for tag in tags_raw if tag)
    followers_raw = item.get("followers")
    followers = int(followers_raw) if isinstance(followers_raw, (int, float)) else None
    return GmgnDirectoryEntry(
        handle=handle,
        gmgn_user_id=user_id,
        user_tags=user_tags,
        platform_followers=followers,
    )
