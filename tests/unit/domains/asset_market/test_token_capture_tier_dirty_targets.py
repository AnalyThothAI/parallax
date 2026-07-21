from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.token_capture_tier_dirty_target_repository import (
    TokenCaptureTierDirtyTargetRepository,
    token_capture_tier_rank_set_payload_hash,
)

NOW_MS = 1_700_000_000_000


@pytest.mark.parametrize(
    "operation",
    (
        lambda repo: repo.enqueue_rank_set(
            reason="token_radar_updated",
            rows=[_rank_row()],
            source_watermark_ms=NOW_MS,
            now_ms=NOW_MS,
        ),
        lambda repo: repo.claim_due(
            now_ms=NOW_MS,
            limit=25,
            lease_owner="token_capture_tier",
            lease_ms=600_000,
        ),
        lambda repo: repo.mark_done([_claim()], now_ms=NOW_MS),
        lambda repo: repo.mark_error(
            [_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="token_capture_tier",
            now_ms=NOW_MS,
        ),
    ),
)
def test_token_capture_tier_dirty_mutations_require_connection_transaction_before_sql_when_committing(
    operation: Callable[[TokenCaptureTierDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="token_capture_tier_dirty_target_transaction_required"):
        operation(TokenCaptureTierDirtyTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "token_capture_tier_dirty_target_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "token_capture_tier_dirty_target_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "token_capture_tier_dirty_target_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "token_capture_tier_dirty_target_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "token_capture_tier_dirty_target_claim_lease_ms_required", id="bool-lease"),
        pytest.param(
            {"lease_ms": "600000"},
            "token_capture_tier_dirty_target_claim_lease_ms_required",
            id="string-lease",
        ),
    ],
)
def test_token_capture_tier_dirty_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "now_ms": NOW_MS,
        "limit": 25,
        "lease_owner": "token_capture_tier",
        "lease_ms": 600_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        TokenCaptureTierDirtyTargetRepository(conn).claim_due(**params)

    assert conn.sql == []
    assert conn.commits == 0


def test_token_capture_tier_rank_set_hash_requires_formal_current_identity() -> None:
    row = _rank_row()
    row.pop("target_type_key")
    row.pop("identity_id")

    with pytest.raises(RuntimeError, match="token_capture_tier_rank_set_identity_required"):
        token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row])


def test_token_capture_tier_rank_set_hash_uses_formal_identity_over_legacy_aliases() -> None:
    formal_row = _rank_row()
    conflicting_legacy_row = {
        **formal_row,
        "target_type": "LegacyAsset",
        "target_id": "legacy-asset",
    }

    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[conflicting_legacy_row]) == (
        token_capture_tier_rank_set_payload_hash(reason="repair", rows=[formal_row])
    )


def test_token_capture_tier_dirty_write_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(rowcount=None)
    repo = TokenCaptureTierDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_capture_tier_dirty_target_rowcount_required"):
        repo.enqueue_rank_set(
            reason="token_radar_updated",
            rows=[_rank_row()],
            source_watermark_ms=NOW_MS,
            now_ms=NOW_MS,
            commit=False,
        )


def test_token_capture_tier_dirty_error_releases_claim_below_retry_budget() -> None:
    conn = _RowcountConnection(rowcount=1)

    changed = TokenCaptureTierDirtyTargetRepository(conn).mark_error(
        [_claim()],
        error="projection failed",
        retry_ms=30_000,
        max_attempts=3,
        worker_name="token_capture_tier",
        now_ms=NOW_MS,
        commit=False,
    )

    assert changed == 1
    assert "UPDATE token_capture_tier_dirty_targets queue" in conn.sql
    assert "leased_until_ms = NULL" in conn.sql
    assert conn.params["due_at_ms"] == NOW_MS + 30_000


@pytest.mark.parametrize("max_attempts", [0, True, "3"])
def test_token_capture_tier_dirty_error_requires_formal_attempt_budget(max_attempts: object) -> None:
    conn = _ScriptedConnection()

    with pytest.raises(ValueError, match="token_capture_tier_dirty_target_max_attempts_required"):
        TokenCaptureTierDirtyTargetRepository(conn).mark_error(
            [_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=max_attempts,  # type: ignore[arg-type]
            worker_name="token_capture_tier",
            now_ms=NOW_MS,
            commit=False,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", -1])
def test_token_capture_tier_dirty_write_counts_reject_invalid_cursor_rowcount(rowcount: Any) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = TokenCaptureTierDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_capture_tier_dirty_target_rowcount_invalid"):
        repo.mark_done([_claim()], now_ms=NOW_MS, commit=False)


@pytest.mark.parametrize(
    "source_watermark_ms",
    [None, 0, -1, True, "1700000000000"],
)
def test_token_capture_tier_dirty_enqueue_requires_formal_source_watermark_without_row_or_runtime_fallback(
    source_watermark_ms: object,
) -> None:
    conn = _ScriptedConnection()

    with pytest.raises(ValueError, match="token_capture_tier_dirty_target_source_watermark_required"):
        TokenCaptureTierDirtyTargetRepository(conn).enqueue_rank_set(
            reason="token_radar_updated",
            rows=[_rank_row()],
            source_watermark_ms=source_watermark_ms,  # type: ignore[arg-type]
            now_ms=NOW_MS,
            commit=False,
        )

    assert conn.sql == ""


@pytest.mark.parametrize("attempt_count", [0, True, "1"])
def test_token_capture_tier_dirty_completion_rejects_malformed_attempt_count(attempt_count: object) -> None:
    conn = _ScriptedConnection()
    claim = {**_claim(), "attempt_count": attempt_count}

    with pytest.raises(
        ValueError,
        match="token capture tier dirty target completion requires attempt_count",
    ):
        TokenCaptureTierDirtyTargetRepository(conn).mark_done(
            [claim],
            now_ms=NOW_MS,
            commit=False,
        )

    assert conn.sql == ""


def _rank_row() -> dict[str, Any]:
    return {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "chain_id": "solana",
        "address": "abc",
        "lane": "hot",
        "rank": 1,
        "rank_score": "10",
        "decision": "include",
        "quality_status": "ready",
        "source_watermark_ms": NOW_MS,
    }


def _claim() -> dict[str, Any]:
    return {
        "work_name": "active_live_market_rank_set",
        "partition_key": "global",
        "payload_hash": "hash:rank-set",
        "lease_owner": "token_capture_tier",
        "attempt_count": 1,
    }


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


class _ScriptedConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: object | None = None

    def execute(self, sql: str, params: object | None = None) -> object:
        self.sql = str(sql)
        self.params = params
        raise AssertionError("SQL must not run for malformed capture-tier dirty target")


class _MissingTransactionConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: object | None = None) -> object:
        self.sql.append(sql)
        raise AssertionError("SQL must not run before repository transaction guard")

    def commit(self) -> None:
        self.commits += 1
