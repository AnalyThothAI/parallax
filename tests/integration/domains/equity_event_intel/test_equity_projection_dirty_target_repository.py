from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_projection_dirty_target_repository import (
    EquityProjectionDirtyTargetRepository,
)
from tests.postgres_test_utils import connect_postgres_test


def test_enqueue_coalesces_by_target_and_preserves_first_dirty_time() -> None:
    conn = _ScriptedConnection([])

    count = EquityProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
                "priority": 10,
            },
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-2",
                "source_watermark_ms": 200,
                "priority": 5,
            },
            {"projection_name": "page", "target_kind": "company_event", "target_id": ""},
        ],
        reason="event_processed",
        now_ms=1_700_000_000_000,
        due_at_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == 1
    assert "INSERT INTO equity_event_projection_dirty_targets" in sql
    assert "ON CONFLICT(projection_name, target_kind, target_id) DO UPDATE SET" in sql
    assert "first_dirty_at_ms = equity_event_projection_dirty_targets.first_dirty_at_ms" in sql
    assert "last_error = NULL" in sql
    assert "payload_hash = CASE" in sql
    assert "source_watermark_ms = GREATEST(" in sql
    assert "due_at_ms = LEAST(equity_event_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms)" in sql
    assert "priority = LEAST(equity_event_projection_dirty_targets.priority, EXCLUDED.priority)" in sql
    assert conn.params[-1]["projection_names"] == ["page"]
    assert conn.params[-1]["target_kinds"] == ["company_event"]
    assert conn.params[-1]["target_ids"] == ["event-1"]
    assert conn.params[-1]["payload_hashes"] == ["hash-2"]
    assert conn.params[-1]["source_watermark_ms_values"] == [200]
    assert conn.params[-1]["priorities"] == [5]
    assert conn.params[-1]["dirty_reason"] == "event_processed"
    assert conn.params[-1]["due_at_ms"] == 1_700_000_010_000
    assert conn.commits == 0


def test_claim_due_uses_skip_locked_claims_expired_leases_and_returns_completion_token() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "projection_name": "page",
                    "target_kind": "company_event",
                    "target_id": "event-1",
                    "payload_hash": "claim-hash",
                    "lease_owner": "worker-a",
                    "attempt_count": 2,
                }
            ]
        ]
    )

    rows = EquityProjectionDirtyTargetRepository(conn).claim_due(
        limit=25,
        lease_ms=60_000,
        now_ms=1_700_000_000_000,
        lease_owner="worker-a",
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows == [
        {
            "projection_name": "page",
            "target_kind": "company_event",
            "target_id": "event-1",
            "payload_hash": "claim-hash",
            "lease_owner": "worker-a",
            "attempt_count": 2,
        }
    ]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql
    assert "attempt_count = equity_event_projection_dirty_targets.attempt_count + 1" not in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "worker-a"


def test_second_claimer_skips_unexpired_leases() -> None:
    conn = _ScriptedConnection([[]])

    rows = EquityProjectionDirtyTargetRepository(conn).claim_due(
        limit=5,
        lease_ms=60_000,
        now_ms=1_700_000_010_000,
        lease_owner="worker-b",
        commit=False,
    )

    assert rows == []
    sql = conn.sql[-1]
    assert "due_at_ms <= %(now_ms)s" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql


def test_reenqueue_duplicate_while_leased_preserves_claim_token_when_payload_is_unchanged() -> None:
    conn = _ScriptedConnection([])

    EquityProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "old-claim-hash",
            }
        ],
        reason="brief_updated",
        now_ms=1_700_000_020_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert "payload_hash = CASE" in sql
    assert "leased_until_ms = CASE" in sql
    assert "lease_owner = CASE" in sql
    assert "EXCLUDED.source_watermark_ms > equity_event_projection_dirty_targets.source_watermark_ms" in sql
    assert "equity_event_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql
    assert "equity_event_projection_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason" in sql
    assert conn.params[-1]["payload_hashes"] == ["old-claim-hash"]

    token = {
        "projection_name": "page",
        "target_kind": "company_event",
        "target_id": "event-1",
        "payload_hash": "old-claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    EquityProjectionDirtyTargetRepository(conn).mark_done(
        [token],
        now_ms=1_700_000_030_000,
        commit=False,
    )
    EquityProjectionDirtyTargetRepository(conn).mark_error(
        [token],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_030_000,
        commit=False,
    )

    done_sql = conn.sql[-2]
    failed_sql = conn.sql[-1]
    assert "queue.payload_hash = done.payload_hash" in done_sql
    assert "queue.lease_owner = done.lease_owner" in done_sql
    assert "queue.attempt_count = done.attempt_count" in done_sql
    assert "queue.payload_hash = failed.payload_hash" in failed_sql
    assert "queue.lease_owner = failed.lease_owner" in failed_sql
    assert "queue.attempt_count = failed.attempt_count" in failed_sql


def test_reenqueue_material_change_while_leased_protects_old_done_and_error_tokens() -> None:
    conn = _ScriptedConnection([])

    EquityProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "new-hash",
            }
        ],
        reason="brief_updated",
        now_ms=1_700_000_020_000,
        commit=False,
    )

    token = {
        "projection_name": "page",
        "target_kind": "company_event",
        "target_id": "event-1",
        "payload_hash": "old-claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    EquityProjectionDirtyTargetRepository(conn).mark_done(
        [token],
        now_ms=1_700_000_030_000,
        commit=False,
    )
    EquityProjectionDirtyTargetRepository(conn).mark_error(
        [token],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_030_000,
        commit=False,
    )

    done_sql = conn.sql[-2]
    failed_sql = conn.sql[-1]
    assert "queue.payload_hash = done.payload_hash" in done_sql
    assert "queue.lease_owner = done.lease_owner" in done_sql
    assert "queue.attempt_count = done.attempt_count" in done_sql
    assert "queue.payload_hash = failed.payload_hash" in failed_sql
    assert "queue.lease_owner = failed.lease_owner" in failed_sql
    assert "queue.attempt_count = failed.attempt_count" in failed_sql


def test_mark_done_deletes_only_matching_claim_token() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    deleted = EquityProjectionDirtyTargetRepository(conn).mark_done(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 2,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 1
    assert "DELETE FROM equity_event_projection_dirty_targets queue" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert conn.params[-1]["payload_hashes"] == ["claim-hash"]
    assert conn.params[-1]["lease_owners"] == ["worker-a"]
    assert conn.params[-1]["attempt_counts"] == [2]


def test_mark_error_requires_token_and_schedules_retry() -> None:
    conn = _ScriptedConnection([])

    try:
        EquityProjectionDirtyTargetRepository(conn).mark_error(
            [{"projection_name": "page", "target_kind": "company_event", "target_id": "event-1"}],
            error="projection failed",
            retry_ms=30_000,
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_error to require claim token fields")

    assert conn.sql == []
    conn.rowcount = 1

    updated = EquityProjectionDirtyTargetRepository(conn).mark_error(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 2,
            }
        ],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated == 1
    assert "SET due_at_ms = %(due_at_ms)s" in sql
    assert "leased_until_ms = NULL" in sql
    assert "queue.payload_hash = failed.payload_hash" in sql
    assert "queue.lease_owner = failed.lease_owner" in sql
    assert "queue.attempt_count = failed.attempt_count" in sql
    assert "attempt_count = queue.attempt_count + %(attempt_increment)s" in sql
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert conn.params[-1]["last_error"] == "projection failed"
    assert conn.params[-1]["attempt_increment"] == 1


def test_mark_done_rejects_claim_token_without_target_key() -> None:
    conn = _ScriptedConnection([])

    try:
        EquityProjectionDirtyTargetRepository(conn).mark_done(
            [{"payload_hash": "claim-hash", "lease_owner": "worker-a", "attempt_count": 1}],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "target key" in str(exc)
    else:
        raise AssertionError("expected mark_done to require the full target key")

    assert conn.sql == []


def test_queue_depth_counts_due_unleased_and_expired_leases() -> None:
    conn = _ScriptedConnection([[{"count": 7}]])

    depth = EquityProjectionDirtyTargetRepository(conn).queue_depth(now_ms=1_700_000_000_000)

    sql = conn.sql[-1]
    assert depth == 7
    assert "count(*) AS count" in sql
    assert "due_at_ms <= %(now_ms)s" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql


def test_repository_session_exposes_equity_projection_dirty_targets() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

    assert isinstance(session.equity_projection_dirty_targets, EquityProjectionDirtyTargetRepository)


def test_postgres_equity_enqueue_is_monotonic_and_keeps_earliest_due(postgres_conn) -> None:
    repo = EquityProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "newer-hash",
                "source_watermark_ms": 200,
                "priority": 50,
            }
        ],
        reason="newer_reason",
        now_ms=1_700_000_000_000,
        due_at_ms=1_700_000_100_000,
    )
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "older-hash",
                "source_watermark_ms": 100,
                "priority": 10,
            }
        ],
        reason="older_reason",
        now_ms=1_700_000_010_000,
        due_at_ms=1_700_000_050_000,
    )

    row = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()
    assert row["source_watermark_ms"] == 200
    assert row["payload_hash"] == "newer-hash"
    assert row["dirty_reason"] == "newer_reason"
    assert row["due_at_ms"] == 1_700_000_050_000
    assert row["priority"] == 10
    assert row["first_dirty_at_ms"] == 1_700_000_000_000
    assert row["last_error"] is None


def test_postgres_equity_single_call_coalesces_monotonically_when_older_follows_newer(postgres_conn) -> None:
    repo = EquityProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "newer-hash",
                "source_watermark_ms": 300,
                "priority": 50,
            },
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "older-hash",
                "source_watermark_ms": 200,
                "priority": 5,
            },
        ],
        reason="same_call_reason",
        now_ms=1_700_000_000_000,
    )

    row = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()
    assert row["source_watermark_ms"] == 300
    assert row["payload_hash"] == "newer-hash"
    assert row["dirty_reason"] == "same_call_reason"
    assert row["priority"] == 5


def test_postgres_equity_single_call_fallback_hash_uses_newer_material_identity_not_min_priority(
    postgres_conn,
) -> None:
    repo = EquityProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "source_watermark_ms": 300,
                "priority": 50,
            },
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "source_watermark_ms": 200,
                "priority": 0,
            },
        ],
        reason="same_call_reason",
        now_ms=1_700_000_000_000,
    )
    coalesced = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()

    postgres_conn.execute("TRUNCATE equity_event_projection_dirty_targets")
    postgres_conn.commit()
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "source_watermark_ms": 300,
                "priority": 50,
            }
        ],
        reason="same_call_reason",
        now_ms=1_700_000_010_000,
    )
    single_newer = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()

    assert coalesced["source_watermark_ms"] == 300
    assert coalesced["priority"] == 0
    assert coalesced["payload_hash"] == single_newer["payload_hash"]


def test_postgres_equity_duplicate_while_leased_preserves_claim_but_material_update_invalidates_it(
    postgres_conn,
) -> None:
    repo = EquityProjectionDirtyTargetRepository(postgres_conn)
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_000_000,
    )
    first_claim = repo.claim_due(limit=1, lease_ms=60_000, now_ms=1_700_000_001_000, lease_owner="worker-a")[0]
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_002_000,
    )

    duplicate_row = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()
    assert duplicate_row["lease_owner"] == "worker-a"
    assert duplicate_row["leased_until_ms"] == 1_700_000_061_000
    assert repo.mark_done([first_claim], now_ms=1_700_000_003_000) == 1

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_004_000,
    )
    stale_claim = repo.claim_due(limit=1, lease_ms=60_000, now_ms=1_700_000_005_000, lease_owner="worker-a")[0]
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "company_event",
                "target_id": "event-1",
                "payload_hash": "hash-2",
                "source_watermark_ms": 101,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_006_000,
    )

    material_row = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()
    assert material_row["lease_owner"] is None
    assert material_row["leased_until_ms"] is None
    assert material_row["payload_hash"] == "hash-2"
    assert material_row["source_watermark_ms"] == 101
    assert repo.mark_done([stale_claim], now_ms=1_700_000_007_000) == 0
    assert repo.mark_error([stale_claim], error="stale", retry_ms=30_000, now_ms=1_700_000_008_000) == 0


def test_postgres_equity_fallback_hash_duplicate_while_leased_is_stable(postgres_conn) -> None:
    repo = EquityProjectionDirtyTargetRepository(postgres_conn)
    row = {
        "projection_name": "page",
        "target_kind": "company_event",
        "target_id": "event-1",
        "source_watermark_ms": 100,
        "priority": 20,
    }

    repo.enqueue_targets([row], reason="reason-1", now_ms=1_700_000_000_000)
    first_claim = repo.claim_due(limit=1, lease_ms=60_000, now_ms=1_700_000_001_000, lease_owner="worker-a")[0]
    first_hash = first_claim["payload_hash"]
    repo.enqueue_targets([{**row, "priority": 5}], reason="reason-1", now_ms=1_700_000_030_000)

    duplicate_row = postgres_conn.execute("SELECT * FROM equity_event_projection_dirty_targets").fetchone()
    assert duplicate_row["payload_hash"] == first_hash
    assert duplicate_row["lease_owner"] == "worker-a"
    assert duplicate_row["leased_until_ms"] == 1_700_000_061_000
    assert duplicate_row["priority"] == 5
    assert repo.mark_done([first_claim], now_ms=1_700_000_031_000) == 1


@pytest.fixture
def postgres_conn(tmp_path) -> Iterator[object]:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute(
            """
            CREATE TEMP TABLE equity_event_projection_dirty_targets (
              projection_name TEXT NOT NULL,
              target_kind TEXT NOT NULL,
              target_id TEXT NOT NULL,
              dirty_reason TEXT NOT NULL,
              payload_hash TEXT NOT NULL,
              source_watermark_ms BIGINT NOT NULL DEFAULT 0,
              priority INTEGER NOT NULL DEFAULT 100,
              due_at_ms BIGINT NOT NULL,
              leased_until_ms BIGINT,
              lease_owner TEXT,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              first_dirty_at_ms BIGINT NOT NULL,
              updated_at_ms BIGINT NOT NULL,
              PRIMARY KEY (projection_name, target_kind, target_id)
            )
            """
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


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
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        return result

    def fetchone(self) -> dict[str, Any] | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def commit(self) -> None:
        self.commits += 1
