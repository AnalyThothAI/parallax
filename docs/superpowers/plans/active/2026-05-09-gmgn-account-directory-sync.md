# GMGN Account Directory Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull GMGN's curated Twitter account directory (~2000 KOL/trader/founder/etc handles with platform-follower counts and editorial tags) and persist it onto `account_profiles` so future scoring can use trader-relevance weights — via a one-shot CLI command, no background worker.

**Architecture:** Extend the existing empty `account_profiles` table with four nullable columns (`gmgn_user_id`, `gmgn_user_tags`, `gmgn_platform_followers`, `gmgn_directory_observed_at_ms`). Add a thin paged client for `https://gmgn.ai/vas/api/v1/twitter/user/search` using the same `curl_cffi` impersonation pattern as `market/gmgn_openapi_client.py`. Wire it through a new `ops sync-gmgn-directory` CLI subcommand that paginates the full directory and upserts via a new `AccountQualityRepository.upsert_directory_entry()` method. No new tables, no read-side scoring change, no background scheduling — surface the data on the existing `account_quality()` payload (which already does `SELECT *`) and stop.

**Tech Stack:** Python 3.13, `curl_cffi` (already in deps), `httpx.MockTransport` for offline tests, Alembic, `argparse` CLI, PostgreSQL 17 via `psycopg`, `pytest`.

**Out of scope (deferred):** read-side scoring change in `diffusion_health._top_authors()` or `propagation_scoring`; bumping `score_version`; daily background sync; historical follower time-series; Twitter API v2 enrichment; per-tweet engagement counts.

---

## File Structure

**Create:**
- `src/gmgn_twitter_intel/storage/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py` — Alembic migration
- `src/gmgn_twitter_intel/market/gmgn_directory_client.py` — paged HTTP client
- `tests/test_gmgn_directory_client.py` — offline client tests
- `tests/fixtures/gmgn_directory_page1.json` — captured response fixture
- `tests/fixtures/gmgn_directory_page2.json` — captured response fixture (last page, no token)

**Modify:**
- `src/gmgn_twitter_intel/storage/account_quality_repository.py` — add `upsert_directory_entry()` method
- `tests/test_account_quality_repository.py` — add test for new method
- `src/gmgn_twitter_intel/cli.py` — add `ops sync-gmgn-directory` subcommand at parser (around line 188 next to `sync-okx-cex-universe`) and dispatcher (around line 649)
- `tests/test_cli.py` — add CLI dispatch test using mocked client
- `src/gmgn_twitter_intel/settings.py` — add optional `gmgn_directory_base_url` setting (default `https://gmgn.ai`)

---

## Task 1: Alembic migration adding GMGN directory columns

**Files:**
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py`

**Goal:** Add four nullable columns and one supporting index to `account_profiles`. Reversible.

- [ ] **Step 1: Write the failing test**

Edit `tests/test_account_quality_repository.py` and add at the bottom:

```python
def test_account_profiles_has_gmgn_directory_columns(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'account_profiles'
              AND column_name IN (
                'gmgn_user_id',
                'gmgn_user_tags',
                'gmgn_platform_followers',
                'gmgn_directory_observed_at_ms'
              )
            ORDER BY column_name
            """
        ).fetchall()
        actual = {row["column_name"]: (row["data_type"], row["is_nullable"]) for row in rows}
        index_rows = conn.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'account_profiles'
              AND indexname = 'idx_account_profiles_gmgn_followers'
            """
        ).fetchall()
    finally:
        conn.close()

    assert actual == {
        "gmgn_user_id": ("text", "YES"),
        "gmgn_user_tags": ("ARRAY", "YES"),
        "gmgn_platform_followers": ("bigint", "YES"),
        "gmgn_directory_observed_at_ms": ("bigint", "YES"),
    }
    assert len(index_rows) == 1
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/test_account_quality_repository.py::test_account_profiles_has_gmgn_directory_columns -v`
Expected: FAIL because the columns/index do not exist yet.

- [ ] **Step 3: Write the migration**

Create `src/gmgn_twitter_intel/storage/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py`:

```python
"""Add GMGN account directory columns to account_profiles."""

from __future__ import annotations

from alembic import op

revision = "20260509_0016"
down_revision = "20260508_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE account_profiles
          ADD COLUMN IF NOT EXISTS gmgn_user_id TEXT,
          ADD COLUMN IF NOT EXISTS gmgn_user_tags TEXT[],
          ADD COLUMN IF NOT EXISTS gmgn_platform_followers BIGINT,
          ADD COLUMN IF NOT EXISTS gmgn_directory_observed_at_ms BIGINT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_account_profiles_gmgn_followers
          ON account_profiles (gmgn_platform_followers DESC NULLS LAST)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_account_profiles_gmgn_followers")
    op.execute(
        """
        ALTER TABLE account_profiles
          DROP COLUMN IF EXISTS gmgn_directory_observed_at_ms,
          DROP COLUMN IF EXISTS gmgn_platform_followers,
          DROP COLUMN IF EXISTS gmgn_user_tags,
          DROP COLUMN IF EXISTS gmgn_user_id
        """
    )
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/test_account_quality_repository.py::test_account_profiles_has_gmgn_directory_columns -v`
Expected: PASS.

- [ ] **Step 5: Apply migration to local Docker postgres so subsequent dev work sees the columns**

Run: `uv run gmgn-twitter-intel db migrate`
Expected output: JSON `{"ok": true, ...}` mentioning `20260509_0016`.

Verify with:
```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "\d account_profiles"
```
Expected: lists the four new columns and the new index.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/storage/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py tests/test_account_quality_repository.py
git commit -m "feat(storage): add GMGN directory columns to account_profiles"
```

---

## Task 2: GMGN directory HTTP client

**Files:**
- Create: `src/gmgn_twitter_intel/market/gmgn_directory_client.py`
- Create: `tests/fixtures/gmgn_directory_page1.json`
- Create: `tests/fixtures/gmgn_directory_page2.json`
- Create: `tests/test_gmgn_directory_client.py`

**Goal:** A small, focused client that paginates `gmgn.ai/vas/api/v1/twitter/user/search`, returns parsed entries plus next-page cursor, and is fully testable offline via `httpx.MockTransport` (mirroring the `GmgnOpenApiClient` test pattern at `tests/test_gmgn_openapi_client.py:8-53`).

- [ ] **Step 1: Save fixtures from observed live response**

Create `tests/fixtures/gmgn_directory_page1.json`:

```json
{
  "code": 0,
  "reason": "",
  "message": "",
  "data": {
    "users": [
      {"handle": "realdonaldtrump", "name": "Donald J. Trump", "avatar": "https://example.test/trump.png", "user_id": "107780257626128497", "user_tags": ["politics"], "platform": 2, "followers": 19782, "followed": false},
      {"handle": "cz", "name": "CZ", "avatar": "https://example.test/cz.png", "user_id": "dxCeCLOM7uOFJKX8EnS3Kw", "user_tags": ["binance_square"], "platform": 2, "followers": 18548, "followed": false}
    ],
    "page_token": "Y3o6MTg1NDg="
  }
}
```

Create `tests/fixtures/gmgn_directory_page2.json`:

```json
{
  "code": 0,
  "reason": "",
  "message": "",
  "data": {
    "users": [
      {"handle": "elonmusk", "name": "Elon Musk", "avatar": "https://example.test/elon.png", "user_id": "44196397", "user_tags": ["founder", "kol"], "platform": 2, "followers": 29396, "followed": false}
    ],
    "page_token": ""
  }
}
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_gmgn_directory_client.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import httpx

from gmgn_twitter_intel.market.gmgn_directory_client import (
    GmgnDirectoryClient,
    GmgnDirectoryEntry,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_client_parses_page_and_returns_next_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/vas/api/v1/twitter/user/search"
        assert request.url.params["limit"] == "50"
        assert request.url.params["handle"] == ""
        assert request.url.params.get_list("user_tags") == [
            "kol", "trader", "master", "politics", "media",
            "companies", "founder", "exchange", "celebrity",
            "binance_square", "other",
        ]
        assert "page_token" not in request.url.params
        return httpx.Response(200, json=_load("gmgn_directory_page1.json"))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        page = client.fetch_page(page_token=None)
    finally:
        client.close()

    assert page.next_page_token == "Y3o6MTg1NDg="
    assert page.entries == [
        GmgnDirectoryEntry(
            handle="realdonaldtrump",
            gmgn_user_id="107780257626128497",
            user_tags=("politics",),
            platform_followers=19782,
        ),
        GmgnDirectoryEntry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square",),
            platform_followers=18548,
        ),
    ]
    assert len(requests) == 1


def test_client_passes_page_token_on_subsequent_request():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("page_token"))
        return httpx.Response(200, json=_load("gmgn_directory_page2.json"))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        page = client.fetch_page(page_token="Y3o6MTg1NDg=")
    finally:
        client.close()

    assert seen == ["Y3o6MTg1NDg="]
    assert page.next_page_token is None
    assert page.entries[0].handle == "elonmusk"
    assert page.entries[0].user_tags == ("founder", "kol")


def test_iter_pages_walks_until_empty_token_and_dedupes_by_handle():
    responses = iter([
        _load("gmgn_directory_page1.json"),
        _load("gmgn_directory_page2.json"),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        entries = list(client.iter_entries(max_pages=10))
    finally:
        client.close()

    handles = [entry.handle for entry in entries]
    assert handles == ["realdonaldtrump", "cz", "elonmusk"]


def test_client_raises_on_non_zero_envelope_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "message": "auth required", "data": None})

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        import pytest
        from gmgn_twitter_intel.market.gmgn_directory_client import GmgnDirectoryError
        with pytest.raises(GmgnDirectoryError, match="auth required"):
            client.fetch_page(page_token=None)
    finally:
        client.close()
```

- [ ] **Step 3: Run tests, confirm they fail**

Run: `uv run pytest tests/test_gmgn_directory_client.py -v`
Expected: FAIL with `ModuleNotFoundError: gmgn_twitter_intel.market.gmgn_directory_client`.

- [ ] **Step 4: Implement the client**

Create `src/gmgn_twitter_intel/market/gmgn_directory_client.py`:

```python
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


@dataclass(frozen=True, slots=True)
class GmgnDirectoryPage:
    entries: tuple[GmgnDirectoryEntry, ...]
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
        entries = tuple(_entry_from_dict(item) for item in users if isinstance(item, dict))
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
            payload = response.json()
        elif self._curl_session is not None:
            response = self._curl_session.get(
                f"{self._base_url}{self._path}",
                params=params,
                timeout=self._timeout_seconds,
            )
            payload = response.json()
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
```

- [ ] **Step 5: Run tests, confirm they pass**

Run: `uv run pytest tests/test_gmgn_directory_client.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Run lint**

Run: `uv run ruff check src/gmgn_twitter_intel/market/gmgn_directory_client.py tests/test_gmgn_directory_client.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/market/gmgn_directory_client.py tests/test_gmgn_directory_client.py tests/fixtures/gmgn_directory_page1.json tests/fixtures/gmgn_directory_page2.json
git commit -m "feat(market): add GMGN twitter directory paged client"
```

---

## Task 3: Repository write method for directory entries

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/account_quality_repository.py:12-48`
- Modify: `tests/test_account_quality_repository.py`

**Goal:** Add `upsert_directory_entry()` that owns the four `gmgn_*` columns and creates the `account_profiles` row if it does not exist. Existing handle-derived columns (`first_seen_ms`, `latest_seen_ms`, `follower_max`, `watched_status`) get sentinel defaults on insert and remain untouched on conflict — directory sync owns the directory fields and only the directory fields.

- [ ] **Step 1: Write failing test**

Append to `tests/test_account_quality_repository.py`:

```python
def test_upsert_directory_entry_inserts_then_updates_directory_fields_only(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = AccountQualityRepository(conn)
        repo.upsert_profile(
            handle="cz",
            first_seen_ms=100,
            latest_seen_ms=200,
            follower_max=1234,
            watched_status="public",
        )
        repo.upsert_directory_entry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square",),
            platform_followers=18548,
            observed_at_ms=1_700_000_000_000,
        )
        repo.upsert_directory_entry(
            handle="elonmusk",
            gmgn_user_id="44196397",
            user_tags=("founder", "kol"),
            platform_followers=29396,
            observed_at_ms=1_700_000_000_001,
        )
        repo.upsert_directory_entry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square", "founder"),
            platform_followers=18999,
            observed_at_ms=1_700_000_000_999,
        )
        cz = repo.account_quality("cz")["profile"]
        elon = repo.account_quality("elonmusk")["profile"]
    finally:
        conn.close()

    assert cz["follower_max"] == 1234
    assert cz["first_seen_ms"] == 100
    assert cz["latest_seen_ms"] == 200
    assert cz["watched_status"] == "public"
    assert cz["gmgn_user_id"] == "dxCeCLOM7uOFJKX8EnS3Kw"
    assert list(cz["gmgn_user_tags"]) == ["binance_square", "founder"]
    assert cz["gmgn_platform_followers"] == 18999
    assert cz["gmgn_directory_observed_at_ms"] == 1_700_000_000_999

    assert elon["gmgn_user_id"] == "44196397"
    assert list(elon["gmgn_user_tags"]) == ["founder", "kol"]
    assert elon["gmgn_platform_followers"] == 29396
    assert elon["follower_max"] is None
    assert elon["watched_status"] == "public"
    assert elon["first_seen_ms"] == 1_700_000_000_001
    assert elon["latest_seen_ms"] == 1_700_000_000_001
```

- [ ] **Step 2: Run test, confirm it fails**

Run: `uv run pytest tests/test_account_quality_repository.py::test_upsert_directory_entry_inserts_then_updates_directory_fields_only -v`
Expected: FAIL with `AttributeError: 'AccountQualityRepository' object has no attribute 'upsert_directory_entry'`.

- [ ] **Step 3: Implement the method**

In `src/gmgn_twitter_intel/storage/account_quality_repository.py`, add this method to `AccountQualityRepository` (place it after `upsert_profile`, before `upsert_token_call_stat`):

```python
    def upsert_directory_entry(
        self,
        *,
        handle: str,
        gmgn_user_id: str | None,
        user_tags: tuple[str, ...],
        platform_followers: int | None,
        observed_at_ms: int,
        commit: bool = True,
    ) -> None:
        normalized = _handle(handle)
        now_ms = _now_ms()
        tags_list = list(user_tags)
        self.conn.execute(
            """
            INSERT INTO account_profiles(
              handle, first_seen_ms, latest_seen_ms, follower_max, watched_status,
              gmgn_user_id, gmgn_user_tags, gmgn_platform_followers, gmgn_directory_observed_at_ms,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(handle) DO UPDATE SET
              gmgn_user_id = excluded.gmgn_user_id,
              gmgn_user_tags = excluded.gmgn_user_tags,
              gmgn_platform_followers = excluded.gmgn_platform_followers,
              gmgn_directory_observed_at_ms = excluded.gmgn_directory_observed_at_ms,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                normalized,
                int(observed_at_ms),
                int(observed_at_ms),
                None,
                "public",
                gmgn_user_id,
                tags_list,
                int(platform_followers) if platform_followers is not None else None,
                int(observed_at_ms),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
```

- [ ] **Step 4: Run test, confirm it passes**

Run: `uv run pytest tests/test_account_quality_repository.py::test_upsert_directory_entry_inserts_then_updates_directory_fields_only -v`
Expected: PASS.

- [ ] **Step 5: Run the full repository test file to confirm no regression**

Run: `uv run pytest tests/test_account_quality_repository.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/gmgn_twitter_intel/storage/account_quality_repository.py tests/test_account_quality_repository.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/storage/account_quality_repository.py tests/test_account_quality_repository.py
git commit -m "feat(storage): upsert GMGN directory fields on account_profiles"
```

---

## Task 4: CLI `ops sync-gmgn-directory` subcommand

**Files:**
- Modify: `src/gmgn_twitter_intel/cli.py` (parser around line 188, dispatcher around line 649)
- Modify: `tests/test_cli.py`

**Goal:** Add a one-shot CLI command that constructs a `GmgnDirectoryClient`, walks all pages, upserts every entry into `account_profiles` via `AccountQualityRepository.upsert_directory_entry()`, and prints a JSON summary on stdout. No background task. No hidden retry. Tested with a stub client passed via dependency injection.

- [ ] **Step 1: Refactor for testability — extract pure sync function**

This step adds a small helper that is easy to unit-test, then the CLI dispatcher calls it. Add to the bottom of `src/gmgn_twitter_intel/cli.py` (just above `def _postgres_connection`):

```python
def _run_sync_gmgn_directory(
    *,
    client: Any,
    repository: Any,
    now_ms: int,
    max_pages: int,
) -> dict:
    upserted = 0
    skipped_no_handle = 0
    handles: list[str] = []
    for entry in client.iter_entries(max_pages=max_pages):
        if not entry.handle:
            skipped_no_handle += 1
            continue
        repository.upsert_directory_entry(
            handle=entry.handle,
            gmgn_user_id=entry.gmgn_user_id,
            user_tags=entry.user_tags,
            platform_followers=entry.platform_followers,
            observed_at_ms=now_ms,
            commit=False,
        )
        upserted += 1
        handles.append(entry.handle)
    repository.conn.commit()
    return {
        "upserted": upserted,
        "skipped_no_handle": skipped_no_handle,
        "first_handles": handles[:5],
        "last_handles": handles[-5:],
        "observed_at_ms": now_ms,
    }
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_cli.py`:

```python
def test_run_sync_gmgn_directory_walks_all_pages_and_upserts():
    from gmgn_twitter_intel.cli import _run_sync_gmgn_directory
    from gmgn_twitter_intel.market.gmgn_directory_client import GmgnDirectoryEntry

    class FakeClient:
        def __init__(self, entries):
            self._entries = entries
            self.calls: list[int] = []

        def iter_entries(self, *, max_pages):
            self.calls.append(max_pages)
            return iter(self._entries)

    class FakeRepo:
        def __init__(self):
            self.upserts: list[dict] = []
            self.commits = 0

            class _Conn:
                outer = self

                def commit(self_inner):
                    self_inner.outer.commits += 1

            self.conn = _Conn()

        def upsert_directory_entry(self, **kwargs):
            self.upserts.append(kwargs)

    entries = [
        GmgnDirectoryEntry(handle="cz", gmgn_user_id="X", user_tags=("kol",), platform_followers=100),
        GmgnDirectoryEntry(handle="", gmgn_user_id=None, user_tags=(), platform_followers=None),
        GmgnDirectoryEntry(handle="elonmusk", gmgn_user_id="Y", user_tags=("founder",), platform_followers=200),
    ]
    client = FakeClient(entries)
    repo = FakeRepo()

    summary = _run_sync_gmgn_directory(
        client=client,
        repository=repo,
        now_ms=1_700_000_000_000,
        max_pages=42,
    )

    assert client.calls == [42]
    assert repo.commits == 1
    assert [u["handle"] for u in repo.upserts] == ["cz", "elonmusk"]
    assert all(u["observed_at_ms"] == 1_700_000_000_000 for u in repo.upserts)
    assert all(u["commit"] is False for u in repo.upserts)
    assert summary == {
        "upserted": 2,
        "skipped_no_handle": 1,
        "first_handles": ["cz", "elonmusk"],
        "last_handles": ["cz", "elonmusk"],
        "observed_at_ms": 1_700_000_000_000,
    }


def test_cli_ops_sync_gmgn_directory_dispatches_to_runner(monkeypatch, tmp_path):
    import io
    import json
    from gmgn_twitter_intel import cli as cli_module

    captured = {}

    def fake_runner(*, client, repository, now_ms, max_pages):
        captured["client"] = client
        captured["repository_type"] = type(repository).__name__
        captured["now_ms"] = now_ms
        captured["max_pages"] = max_pages
        return {"upserted": 7, "skipped_no_handle": 0, "first_handles": [], "last_handles": [], "observed_at_ms": now_ms}

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    monkeypatch.setattr(cli_module, "_run_sync_gmgn_directory", fake_runner)
    monkeypatch.setattr(cli_module, "GmgnDirectoryClient", FakeClient)
    monkeypatch.setattr(cli_module, "_now_ms", lambda: 1_700_000_000_000)

    stdout = io.StringIO()
    code = cli_module.main(
        ["ops", "sync-gmgn-directory", "--max-pages", "3"],
        stdout=stdout,
    )

    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload == {
        "ok": True,
        "data": {
            "upserted": 7,
            "skipped_no_handle": 0,
            "first_handles": [],
            "last_handles": [],
            "observed_at_ms": 1_700_000_000_000,
        },
    }
    assert captured["max_pages"] == 3
    assert captured["repository_type"] == "AccountQualityRepository"
    assert isinstance(captured["client"], FakeClient)
```

- [ ] **Step 3: Run tests, confirm they fail**

Run: `uv run pytest tests/test_cli.py::test_run_sync_gmgn_directory_walks_all_pages_and_upserts tests/test_cli.py::test_cli_ops_sync_gmgn_directory_dispatches_to_runner -v`
Expected: first test FAIL with `ImportError`/`AttributeError` for `_run_sync_gmgn_directory`; second FAIL with `argparse: invalid choice 'sync-gmgn-directory'`.

- [ ] **Step 4: Add the parser option**

In `src/gmgn_twitter_intel/cli.py`, just before `return parser` at line 232 (next to other ops subcommands), add:

```python
    sync_gmgn_directory = ops_subcommands.add_parser(
        "sync-gmgn-directory",
        help="one-shot sync of GMGN twitter directory into account_profiles",
    )
    sync_gmgn_directory.add_argument("--max-pages", type=int, default=200)
```

- [ ] **Step 5: Add the dispatcher branch and import**

At the top of `src/gmgn_twitter_intel/cli.py`, ensure the import for the new client exists. Find the existing imports of `GmgnOpenApiClient`, and add adjacent:

```python
from .market.gmgn_directory_client import GmgnDirectoryClient
```

In the dispatcher, after the `sync-okx-cex-universe` branch (around line 649) and before the next `if command == "ops"` block, add:

```python
        if command == "ops" and args.ops_command == "sync-gmgn-directory":
            client = GmgnDirectoryClient()
            try:
                data = _run_sync_gmgn_directory(
                    client=client,
                    repository=AccountQualityRepository(signals.conn),
                    now_ms=_now_ms(),
                    max_pages=int(args.max_pages),
                )
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0
```

Verify `AccountQualityRepository` is already imported at the top of `cli.py`. If not, add the import.

- [ ] **Step 6: Run tests, confirm they pass**

Run: `uv run pytest tests/test_cli.py::test_run_sync_gmgn_directory_walks_all_pages_and_upserts tests/test_cli.py::test_cli_ops_sync_gmgn_directory_dispatches_to_runner -v`
Expected: 2 PASS.

- [ ] **Step 7: Run the full test suite to confirm no regression**

Run: `uv run pytest`
Expected: full suite passes (skipped tests OK if PG fixtures unavailable in some environments, but the new tests must run).

- [ ] **Step 8: Lint and compile-check**

Run:
```bash
uv run ruff check src tests
uv run python -m compileall src tests
```
Expected: no issues.

- [ ] **Step 9: Commit**

```bash
git add src/gmgn_twitter_intel/cli.py tests/test_cli.py
git commit -m "feat(cli): add ops sync-gmgn-directory one-shot command"
```

---

## Task 5: Live smoke test (manual gate)

**Files:** none — verification step against the live `gmgn.ai` endpoint.

**Goal:** Confirm the wire format hasn't drifted from the fixtures and that ~2000 entries land in `account_profiles` end-to-end. This is a single one-shot run; do not schedule it.

- [ ] **Step 1: Run the live sync**

Run: `uv run gmgn-twitter-intel ops sync-gmgn-directory --max-pages 60`

Expected stdout: a single JSON line `{"ok": true, "data": {"upserted": <N>, ...}}` where `N` is in the range 1500–3000. Total wall time should be roughly `pages × 1s` (sleep between pages).

If the command errors with HTTP 403 or a Cloudflare challenge HTML, this is expected real-world drift — record the failure and stop. Do NOT add retry logic, header tweaks, or a longer sleep in the same session.

- [ ] **Step 2: Verify the data landed**

Run:
```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
  SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE gmgn_user_id IS NOT NULL) AS with_user_id,
    COUNT(*) FILTER (WHERE gmgn_platform_followers IS NOT NULL) AS with_followers,
    MAX(gmgn_platform_followers) AS max_followers,
    MIN(gmgn_directory_observed_at_ms) AS earliest_observed_ms
  FROM account_profiles;
"
```

Expected: `total ≥ 1500`, `with_user_id ≈ total`, `with_followers ≈ total`, `max_followers ≥ 30000` (cz_binance / heyibinance / elonmusk all live in the high tens of thousands).

- [ ] **Step 3: Spot-check a known handle**

Run:
```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
  SELECT handle, gmgn_user_id, gmgn_user_tags, gmgn_platform_followers
  FROM account_profiles
  WHERE handle IN ('cz', 'elonmusk', 'realdonaldtrump', 'cz_binance')
  ORDER BY gmgn_platform_followers DESC NULLS LAST;
"
```

Expected: rows present with platform_followers > 0 and at least one user_tag per row.

- [ ] **Step 4: No commit**

This task creates no code changes — it only verifies the prior tasks work end-to-end. Stop here. Decisions about read-side scoring integration belong to a future plan once we have observed the data for a few days.

---

## Self-Review Notes

- **Spec coverage:** every minimum-loop requirement (migration, client, CLI, one-shot run) maps to Tasks 1–5. Reading-side scoring change explicitly deferred per user instruction.
- **Empty table preservation:** `upsert_directory_entry` writes `follower_max=NULL`, `watched_status='public'` only on insert; existing rows keep all non-directory fields untouched (test in Task 3 covers this).
- **Naming consistency:** `gmgn_user_id`, `gmgn_user_tags`, `gmgn_platform_followers`, `gmgn_directory_observed_at_ms` used identically across migration, repository, client, and tests.
- **No new tables, no new score_version, no daily worker, no Twitter API v2 call** — matches the user's "minimum production closure" scope.
- **Cloudflare resilience:** the client uses the same `curl_cffi.requests.Session(impersonate="chrome")` pattern as `market/gmgn_openapi_client.py` (line 57), so production calls can clear Cloudflare while tests use `httpx.MockTransport` with no network.
- **Rollback procedure:** revert commits in reverse order. The Alembic migration has a working `downgrade()` — `uv run alembic downgrade -1` removes the four columns and the index cleanly because they are nullable and the table remains empty in the worst-case rollback window.
