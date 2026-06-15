from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.asset_profile_refresh_target_repository import (
    AssetProfileRefreshTargetRepository,
)

NOW_MS = 1_700_000_000_000


@pytest.mark.parametrize(
    "operation",
    (
        lambda repo: repo.enqueue_targets([_target()], reason="resolution_updated", now_ms=NOW_MS),
        lambda repo: repo.claim_due(
            provider="gmgn_dex_profile",
            now_ms=NOW_MS,
            limit=25,
            lease_owner="asset_profile_refresh",
            lease_ms=600_000,
        ),
        lambda repo: repo.reschedule(
            [_claim()],
            due_at_ms=NOW_MS + 60_000,
            now_ms=NOW_MS,
            reason="profile_ready_written",
        ),
        lambda repo: repo.mark_error(
            [_claim()],
            error="provider failed",
            now_ms=NOW_MS,
            retry_ms=300_000,
        ),
    ),
)
def test_asset_profile_refresh_target_mutations_require_connection_transaction_before_sql_when_committing(
    operation: Callable[[AssetProfileRefreshTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="asset_profile_refresh_target_transaction_required"):
        operation(AssetProfileRefreshTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "operation",
    (
        pytest.param(
            lambda repo, claim: repo.reschedule(
                [claim],
                due_at_ms=NOW_MS + 60_000,
                now_ms=NOW_MS,
                reason="profile_ready_written",
                commit=False,
            ),
            id="reschedule",
        ),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="provider failed",
                now_ms=NOW_MS,
                retry_ms=300_000,
                commit=False,
            ),
            id="error",
        ),
    ),
)
def test_asset_profile_refresh_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[AssetProfileRefreshTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _MissingTransactionConnection()
    claim = _claim()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="asset profile refresh target completion requires attempt_count",
    ) as exc_info:
        operation(AssetProfileRefreshTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


def test_asset_profile_refresh_completion_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(omit_rowcount=True)
    repo = AssetProfileRefreshTargetRepository(conn)

    with pytest.raises(TypeError, match="asset_profile_refresh_target_rowcount_required"):
        repo.reschedule(
            [_claim()],
            due_at_ms=NOW_MS + 60_000,
            now_ms=NOW_MS,
            reason="profile_ready_written",
            commit=False,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_asset_profile_refresh_completion_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = AssetProfileRefreshTargetRepository(conn)

    with pytest.raises(TypeError, match="asset_profile_refresh_target_rowcount_invalid"):
        repo.mark_error(
            [_claim()],
            error="provider failed",
            now_ms=NOW_MS,
            retry_ms=300_000,
            commit=False,
        )


def _target() -> dict[str, Any]:
    return {
        "provider": "gmgn_dex_profile",
        "target_type": "Asset",
        "target_id": "asset-1",
        "chain_id": "solana",
        "address": "abc",
        "symbol": "ABC",
        "source_watermark_ms": NOW_MS,
        "priority": 40,
    }


def _claim() -> dict[str, Any]:
    return {
        "provider": "gmgn_dex_profile",
        "target_type": "Asset",
        "target_id": "asset-1",
        "payload_hash": "hash:asset-1",
        "lease_owner": "asset_profile_refresh",
        "attempt_count": 1,
    }


class _MissingTransactionConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: object | None = None) -> object:
        self.sql.append(sql)
        raise AssertionError("SQL must not run before repository transaction guard")

    def commit(self) -> None:
        self.commits += 1


class _RowcountConnection:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: object | None = None) -> _RowcountCursor:
        del sql, params
        return _RowcountCursor(rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class _RowcountCursor:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount
