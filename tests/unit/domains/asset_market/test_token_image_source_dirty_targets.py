from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    TokenImageSourceDirtyTargetRepository,
)

SOURCE_URL = "https://gmgn.ai/external-res/token-alpha.png"


def test_existing_by_source_targets_loads_exact_dirty_target_keys() -> None:
    source_url_hash = sha256(SOURCE_URL.encode("utf-8")).hexdigest()
    row = {
        "source_url_hash": source_url_hash,
        "source_url": SOURCE_URL,
        "target_type": "asset_profile",
        "target_id": "solana:alpha",
    }
    conn = _ScriptedConnection([[row]])
    repo = TokenImageSourceDirtyTargetRepository(conn)

    result = repo.existing_by_source_targets(
        [
            {
                "source_url": SOURCE_URL,
                "target_type": "asset_profile",
                "target_id": "solana:alpha",
            }
        ]
    )

    assert "JOIN incoming" in conn.sql
    assert conn.params == {
        "source_url_hashes": [source_url_hash],
        "target_types": ["asset_profile"],
        "target_ids": ["solana:alpha"],
    }
    assert result == {(source_url_hash, "asset_profile", "solana:alpha"): row}


@pytest.mark.parametrize(
    "operation",
    [
        lambda repo: repo.enqueue_targets([_target()], reason="token_profile_current_source_admission", now_ms=NOW_MS),
        lambda repo: repo.claim_due(now_ms=NOW_MS, limit=25, lease_owner="token_image_mirror", lease_ms=600_000),
        lambda repo: repo.mark_done([_dirty_claim()], now_ms=NOW_MS),
        lambda repo: repo.mark_error([_dirty_claim()], error="mirror failed", retry_ms=300_000, now_ms=NOW_MS),
    ],
)
def test_token_image_source_dirty_mutations_require_connection_transaction_before_sql_when_committing(
    operation: Callable[[TokenImageSourceDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="token_image_source_dirty_target_transaction_required"):
        operation(TokenImageSourceDirtyTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=NOW_MS, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="mirror failed",
                retry_ms=300_000,
                now_ms=NOW_MS,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_token_image_source_dirty_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[TokenImageSourceDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _ScriptedConnection([])
    claim = _dirty_claim()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="token image source dirty target completion requires attempt_count",
    ) as exc_info:
        operation(TokenImageSourceDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == ""


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=NOW_MS, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="mirror failed",
                retry_ms=300_000,
                now_ms=NOW_MS,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback(
    operation: Callable[[TokenImageSourceDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _ScriptedConnection([])
    claim = _dirty_claim()
    claim.pop("source_url_hash")

    with pytest.raises(
        ValueError,
        match="token image source dirty target completion requires full target key",
    ) as exc_info:
        operation(TokenImageSourceDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == ""


def test_token_image_source_dirty_completion_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(rowcount=None)
    repo = TokenImageSourceDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_image_source_dirty_target_rowcount_required"):
        repo.mark_done([_dirty_claim()], now_ms=NOW_MS, commit=False)


@pytest.mark.parametrize("rowcount", [True, False, "1", -1])
def test_token_image_source_dirty_completion_counts_reject_invalid_cursor_rowcount(rowcount: Any) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = TokenImageSourceDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_image_source_dirty_target_rowcount_invalid"):
        repo.mark_error([_dirty_claim()], error="mirror failed", retry_ms=30_000, now_ms=NOW_MS, commit=False)


NOW_MS = 1_700_000_000_000


def _target() -> dict[str, Any]:
    return {
        "source_url": SOURCE_URL,
        "source_provider": "gmgn",
        "source_kind": "asset_profiles.logo_url",
        "target_type": "Asset",
        "target_id": "asset-alpha",
        "raw_ref_json": {"asset_id": "asset-alpha"},
        "source_watermark_ms": NOW_MS,
        "priority": 30,
    }


def _dirty_claim() -> dict[str, Any]:
    return {
        "source_url": SOURCE_URL,
        "source_url_hash": sha256(SOURCE_URL.encode("utf-8")).hexdigest(),
        "target_type": "Asset",
        "target_id": "asset-alpha",
        "payload_hash": "payload-alpha",
        "lease_owner": "token_image_mirror",
        "attempt_count": 1,
    }


class _ScriptedConnection:
    def __init__(self, results: list[Any]) -> None:
        self.results = list(results)
        self.sql = ""
        self.params: Any = None

    def execute(self, sql: str, params: Any | None = None) -> _ScriptedConnection:
        self.sql = str(sql)
        self.params = params
        return self

    def fetchall(self) -> list[Any]:
        return self.results.pop(0)


class _RowcountConnection:
    def __init__(self, *, rowcount: Any) -> None:
        self.rowcount = rowcount
        self.sql = ""
        self.params: Any = None

    def execute(self, sql: str, params: Any | None = None) -> _RowcountCursor:
        self.sql = str(sql)
        self.params = params
        return _RowcountCursor(self.rowcount)


class _RowcountCursor:
    def __init__(self, rowcount: Any) -> None:
        if rowcount is not None:
            self.rowcount = rowcount


class _MissingTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _MissingTransactionConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        raise AssertionError("SQL must not run without connection transaction")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("manual commit fallback must not run")
