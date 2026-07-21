from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.asset_market.repositories.token_profile_current_dirty_target_repository import (
    TokenProfileCurrentDirtyTargetRepository,
)


def test_enqueue_targets_coalesces_by_target_and_uses_lower_priority() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    count = TokenProfileCurrentDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "source_watermark_ms": 10,
                "priority": 90,
                "payload_hash": "payload-old",
            },
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "source_watermark_ms": 11,
                "priority": 20,
                "payload_hash": "payload-new",
            },
            {"target_type": "", "target_id": "asset-ignored"},
        ],
        reason="token_radar_changed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == {"targets": 1}
    assert "INSERT INTO token_profile_current_dirty_targets" in sql
    assert "ON CONFLICT(target_type, target_id) DO UPDATE SET" in sql
    assert "priority = LEAST(token_profile_current_dirty_targets.priority, EXCLUDED.priority)" in sql
    assert "first_dirty_at_ms = token_profile_current_dirty_targets.first_dirty_at_ms" in sql
    assert "leased_until_ms = CASE" in sql
    assert conn.params[-1]["target_types"] == ["Asset"]
    assert conn.params[-1]["target_ids"] == ["asset-1"]
    assert conn.params[-1]["payload_hashes"] == ["payload-new"]
    assert conn.params[-1]["source_watermark_ms_values"] == [11]
    assert conn.params[-1]["priorities"] == [20]
    assert conn.params[-1]["dirty_reason"] == "token_radar_changed"


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1"},
            id="missing",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "computed_at_ms": 1_700_000_001_000},
            id="computed-at",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "updated_at_ms": 1_700_000_002_000},
            id="updated-at",
        ),
        pytest.param(
            ("Asset", "asset-1"),
            id="tuple-target",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": None},
            id="none",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": 0},
            id="zero",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": -1},
            id="negative",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": True},
            id="bool",
        ),
        pytest.param(
            {"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": "1700000001000"},
            id="string",
        ),
    ],
)
def test_enqueue_targets_requires_formal_source_watermark_without_runtime_fallback(target) -> None:
    conn = _ScriptedConnection([])

    with pytest.raises(ValueError, match="token_profile_current_dirty_target_source_watermark_required"):
        TokenProfileCurrentDirtyTargetRepository(conn).enqueue_targets(
            [target],
            reason="token_radar_changed",
            now_ms=1_700_000_000_000,
            commit=False,
        )

    assert conn.sql == []


def test_claim_due_orders_by_priority_due_and_updated_and_increments_attempts() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "payload_hash": "payload-1",
                    "lease_owner": "profile-a",
                    "attempt_count": 1,
                    "source_watermark_ms": 10,
                    "dirty_reason": "token_radar_changed",
                }
            ]
        ]
    )

    rows = TokenProfileCurrentDirtyTargetRepository(conn).claim_due(
        now_ms=1_700_000_000_000,
        limit=25,
        lease_owner="profile-a",
        lease_ms=60_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows[0]["payload_hash"] == "payload-1"
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY priority ASC," in sql
    assert "due_at_ms ASC," in sql
    assert "updated_at_ms ASC" in sql
    assert "attempt_count = token_profile_current_dirty_targets.attempt_count + 1" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "profile-a"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "token_profile_current_dirty_target_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "token_profile_current_dirty_target_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "token_profile_current_dirty_target_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "token_profile_current_dirty_target_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "token_profile_current_dirty_target_claim_lease_ms_required", id="bool-lease"),
        pytest.param(
            {"lease_ms": "60000"},
            "token_profile_current_dirty_target_claim_lease_ms_required",
            id="string-lease",
        ),
    ],
)
def test_profile_current_dirty_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "now_ms": 1_700_000_000_000,
        "limit": 25,
        "lease_owner": "profile-a",
        "lease_ms": 60_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        TokenProfileCurrentDirtyTargetRepository(conn).claim_due(**params)

    assert conn.sql == []
    assert conn.commits == 0


def test_mark_done_requires_full_stale_completion_token() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    deleted = TokenProfileCurrentDirtyTargetRepository(conn).mark_done(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "payload_hash": "payload-1",
                "lease_owner": "profile-a",
                "attempt_count": 2,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 1
    assert "DELETE FROM token_profile_current_dirty_targets queue" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert conn.params[-1]["payload_hashes"] == ["payload-1"]
    assert conn.params[-1]["lease_owners"] == ["profile-a"]
    assert conn.params[-1]["attempt_counts"] == [2]


def test_mark_error_releases_claim_below_terminal_attempt_limit() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = TokenProfileCurrentDirtyTargetRepository(conn).mark_error(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "payload_hash": "payload-1",
                "lease_owner": "profile-a",
                "attempt_count": 2,
            }
        ],
        error="source failed",
        retry_ms=30_000,
        max_attempts=3,
        worker_name="token_profile_current",
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    set_clause = sql.split("SET", 1)[1].split("FROM", 1)[0]
    assert updated == 1
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "attempt_count =" not in set_clause
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert conn.params[-1]["last_error"] == "source failed"


def test_mark_error_terminalizes_claim_at_retry_budget() -> None:
    exhausted = {
        **_dirty_claim(),
        "attempt_count": 3,
        "first_dirty_at_ms": 1_700_000_000_000,
        "updated_at_ms": 1_700_000_009_000,
    }
    conn = _ScriptedConnection(
        [
            [exhausted],
            [],
            [{"terminal_generation": 1}],
            [{"terminal_id": "terminal-1", "terminal_generation": 1}],
        ]
    )

    changed = TokenProfileCurrentDirtyTargetRepository(conn).mark_error(
        [exhausted],
        error="source failed",
        retry_ms=30_000,
        max_attempts=3,
        worker_name="token_profile_current",
        now_ms=1_700_000_010_000,
        commit=False,
    )

    assert changed == 1
    assert "RETURNING queue.*" in conn.sql[0]
    assert "INSERT INTO worker_queue_terminal_events" in conn.sql[-1]
    assert conn.params[-1]["source_table"] == "token_profile_current_dirty_targets"
    assert conn.params[-1]["target_key"] == "Asset:asset-1"
    assert conn.params[-1]["final_reason"].startswith("retry_budget_exhausted:")


@pytest.mark.parametrize("retry_ms", [0, True, "30000"])
def test_profile_current_dirty_mark_error_rejects_malformed_retry_before_transaction(retry_ms: object) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(ValueError, match="token_profile_current_dirty_target_retry_ms_required"):
        TokenProfileCurrentDirtyTargetRepository(conn).mark_error(
            [_dirty_claim()],
            error="source failed",
            retry_ms=retry_ms,  # type: ignore[arg-type]
            max_attempts=3,
            worker_name="token_profile_current",
            now_ms=1_700_000_010_000,
        )

    assert conn.sql == []
    assert conn.commits == 0


def test_completion_rejects_claim_without_payload_hash() -> None:
    conn = _ScriptedConnection([])

    try:
        TokenProfileCurrentDirtyTargetRepository(conn).mark_done(
            [{"target_type": "Asset", "target_id": "asset-1", "attempt_count": 1}],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed payload_hash")

    assert conn.sql == []


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="source failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_profile_current",
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_profile_current_dirty_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[TokenProfileCurrentDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _ScriptedConnection([])
    claim = _dirty_claim()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="token profile current dirty target completion requires attempt_count",
    ) as exc_info:
        operation(TokenProfileCurrentDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


@pytest.mark.parametrize("attempt_count", [0, True, "1"])
def test_profile_current_dirty_completion_rejects_malformed_attempt_count(attempt_count: object) -> None:
    conn = _ScriptedConnection([])
    claim = {**_dirty_claim(), "attempt_count": attempt_count}

    with pytest.raises(
        ValueError,
        match="token profile current dirty target completion requires attempt_count",
    ):
        TokenProfileCurrentDirtyTargetRepository(conn).mark_done(
            [claim],
            now_ms=1_700_000_010_000,
            commit=False,
        )

    assert conn.sql == []


def test_profile_current_dirty_completion_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(omit_rowcount=True)
    repo = TokenProfileCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_profile_current_dirty_target_rowcount_required"):
        repo.mark_done([_dirty_claim()], now_ms=1_700_000_010_000, commit=False)


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_profile_current_dirty_completion_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = TokenProfileCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="token_profile_current_dirty_target_rowcount_invalid"):
        repo.mark_error(
            [_dirty_claim()],
            error="source failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="token_profile_current",
            now_ms=1_700_000_010_000,
            commit=False,
        )


def test_repository_session_exposes_token_profile_current_dirty_targets() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.token_profile_current_dirty_targets, TokenProfileCurrentDirtyTargetRepository)


@pytest.mark.parametrize(
    "operation",
    [
        lambda repo: repo.enqueue_targets(
            [{"target_type": "Asset", "target_id": "asset-1", "source_watermark_ms": 1_700_000_000_000}],
            reason="token_radar_changed",
            now_ms=1_700_000_000_000,
        ),
        lambda repo: repo.claim_due(
            now_ms=1_700_000_000_000,
            limit=25,
            lease_owner="profile-a",
            lease_ms=60_000,
        ),
        lambda repo: repo.mark_done([_dirty_claim()], now_ms=1_700_000_010_000),
        lambda repo: repo.mark_error(
            [_dirty_claim()],
            error="source failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="token_profile_current",
            now_ms=1_700_000_010_000,
        ),
    ],
)
def test_profile_current_dirty_mutations_require_connection_transaction_before_sql_when_committing(
    operation: Callable[[TokenProfileCurrentDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="token_profile_current_dirty_target_transaction_required"):
        operation(TokenProfileCurrentDirtyTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


def _dirty_claim() -> dict[str, Any]:
    return {
        "target_type": "Asset",
        "target_id": "asset-1",
        "payload_hash": "payload-1",
        "lease_owner": "profile-a",
        "attempt_count": 1,
    }


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.rowcount = 0
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            self.rowcount = 0
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        self.rowcount = len(result)
        return result

    def fetchone(self) -> dict[str, Any] | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def commit(self) -> None:
        self.commits += 1


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


class _RowcountConnection:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _RowcountCursor:
        del sql, params
        return _RowcountCursor(rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class _RowcountCursor:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount
