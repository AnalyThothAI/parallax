from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.news_intel.repositories import news_projection_dirty_target_repository as dirty_target_repository_module
from gmgn_twitter_intel.domains.news_intel.repositories.news_projection_dirty_target_repository import (
    NewsProjectionDirtyTargetRepository,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_enqueue_coalesces_by_news_item_target_and_preserves_first_dirty_time() -> None:
    conn = _ScriptedConnection([])

    count = NewsProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
                "priority": 10,
            },
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "hash-2",
                "source_watermark_ms": 200,
                "priority": 5,
            },
        ],
        reason="item_processed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == 1
    assert "INSERT INTO news_projection_dirty_targets" in sql
    assert 'ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET' in sql
    assert "first_dirty_at_ms = news_projection_dirty_targets.first_dirty_at_ms" in sql
    assert "last_error = NULL" in sql
    assert "payload_hash = CASE" in sql
    assert "source_watermark_ms = GREATEST(" in sql
    assert "due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms)" in sql
    assert "priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority)" in sql
    assert conn.params[-1]["projection_names"] == ["page"]
    assert conn.params[-1]["target_kinds"] == ["news_item"]
    assert conn.params[-1]["target_ids"] == ["item-1"]
    assert conn.params[-1]["windows"] == [""]
    assert conn.params[-1]["payload_hashes"] == ["hash-2"]
    assert conn.params[-1]["source_watermark_ms_values"] == [200]
    assert conn.params[-1]["priorities"] == [5]


def test_news_source_quality_uniqueness_includes_window() -> None:
    conn = _ScriptedConnection([])

    count = NewsProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "source_quality",
                "target_kind": "source",
                "target_id": "source-1",
                "window": "24h",
                "payload_hash": "hash-24h",
            },
            {
                "projection_name": "source_quality",
                "target_kind": "source",
                "target_id": "source-1",
                "window": "7d",
                "payload_hash": "hash-7d",
            },
        ],
        reason="source_quality_window_due",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    assert count == 2
    assert 'ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET' in conn.sql[-1]
    assert conn.params[-1]["target_ids"] == ["source-1", "source-1"]
    assert conn.params[-1]["windows"] == ["24h", "7d"]


def test_claim_due_returns_full_completion_token_and_skips_unexpired_leases() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                    "payload_hash": "claim-hash",
                    "lease_owner": "worker-a",
                    "attempt_count": 2,
                }
            ],
            [],
        ]
    )

    claimed = NewsProjectionDirtyTargetRepository(conn).claim_due(
        limit=10,
        lease_ms=60_000,
        now_ms=1_700_000_000_000,
        lease_owner="worker-a",
        commit=False,
    )
    skipped = NewsProjectionDirtyTargetRepository(conn).claim_due(
        limit=10,
        lease_ms=60_000,
        now_ms=1_700_000_010_000,
        lease_owner="worker-b",
        commit=False,
    )

    assert claimed == [
        {
            "projection_name": "source_quality",
            "target_kind": "source",
            "target_id": "source-1",
            "window": "24h",
            "payload_hash": "claim-hash",
            "lease_owner": "worker-a",
            "attempt_count": 2,
        }
    ]
    assert skipped == []
    sql = conn.sql[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql
    assert "attempt_count = news_projection_dirty_targets.attempt_count + 1" not in sql


def test_reenqueue_duplicate_while_leased_preserves_claim_token_when_payload_is_unchanged() -> None:
    conn = _ScriptedConnection([])

    NewsProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
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
    assert "EXCLUDED.source_watermark_ms > news_projection_dirty_targets.source_watermark_ms" in sql
    assert "news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql
    assert "news_projection_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason" in sql
    assert conn.params[-1]["payload_hashes"] == ["old-claim-hash"]

    token = {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "item-1",
        "window": "",
        "payload_hash": "old-claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    NewsProjectionDirtyTargetRepository(conn).mark_done([token], now_ms=1_700_000_030_000, commit=False)
    NewsProjectionDirtyTargetRepository(conn).mark_error(
        [token],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_030_000,
        commit=False,
    )
    assert "queue.payload_hash = done.payload_hash" in conn.sql[-2]
    assert "queue.lease_owner = done.lease_owner" in conn.sql[-2]
    assert "queue.attempt_count = done.attempt_count" in conn.sql[-2]
    assert "queue.payload_hash = failed.payload_hash" in conn.sql[-1]
    assert "queue.lease_owner = failed.lease_owner" in conn.sql[-1]
    assert "queue.attempt_count = failed.attempt_count" in conn.sql[-1]
    assert "attempt_count = queue.attempt_count + %(attempt_increment)s" in conn.sql[-1]
    assert conn.params[-1]["attempt_increment"] == 1


def test_reenqueue_material_change_while_leased_protects_old_done_and_error_tokens() -> None:
    conn = _ScriptedConnection([])

    NewsProjectionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "new-hash",
            }
        ],
        reason="brief_updated",
        now_ms=1_700_000_020_000,
        commit=False,
    )

    token = {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "item-1",
        "window": "",
        "payload_hash": "old-claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    NewsProjectionDirtyTargetRepository(conn).mark_done([token], now_ms=1_700_000_030_000, commit=False)
    NewsProjectionDirtyTargetRepository(conn).mark_error(
        [token],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_030_000,
        commit=False,
    )
    assert "queue.payload_hash = done.payload_hash" in conn.sql[-2]
    assert "queue.lease_owner = done.lease_owner" in conn.sql[-2]
    assert "queue.attempt_count = done.attempt_count" in conn.sql[-2]
    assert "queue.payload_hash = failed.payload_hash" in conn.sql[-1]
    assert "queue.lease_owner = failed.lease_owner" in conn.sql[-1]
    assert "queue.attempt_count = failed.attempt_count" in conn.sql[-1]


def test_mark_done_and_mark_error_require_full_claim_token() -> None:
    conn = _ScriptedConnection([])

    missing_window_token = {"projection_name": "page", "target_kind": "news_item", "target_id": "item-1"}
    for method_name in ("mark_done", "mark_error"):
        try:
            if method_name == "mark_done":
                NewsProjectionDirtyTargetRepository(conn).mark_done(
                    [missing_window_token],
                    now_ms=1_700_000_010_000,
                    commit=False,
                )
            else:
                NewsProjectionDirtyTargetRepository(conn).mark_error(
                    [missing_window_token],
                    error="projection failed",
                    retry_ms=30_000,
                    now_ms=1_700_000_010_000,
                    commit=False,
                )
        except ValueError as exc:
            assert "window" in str(exc)
        else:
            raise AssertionError(f"expected {method_name} to require window from claim_due")

    missing_payload_token = {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "item-1",
        "window": "",
    }
    try:
        NewsProjectionDirtyTargetRepository(conn).mark_done(
            [missing_payload_token],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claim token fields")

    assert conn.sql == []


def test_mark_error_rejects_source_quality_token_without_window() -> None:
    conn = _ScriptedConnection([])

    try:
        NewsProjectionDirtyTargetRepository(conn).mark_error(
            [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "payload_hash": "claim-hash",
                    "lease_owner": "worker-a",
                    "attempt_count": 1,
                }
            ],
            error="projection failed",
            retry_ms=30_000,
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "window" in str(exc)
    else:
        raise AssertionError("expected source_quality completion to require window")

    assert conn.sql == []


def test_mark_done_deletes_rows_and_mark_error_schedules_retry() -> None:
    conn = _ScriptedConnection([])
    token = {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": "source-1",
        "window": "24h",
        "payload_hash": "claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 2,
    }

    conn.rowcount = 1
    assert NewsProjectionDirtyTargetRepository(conn).mark_done([token], now_ms=1_700_000_010_000, commit=False) == 1
    assert "DELETE FROM news_projection_dirty_targets queue" in conn.sql[-1]
    assert 'queue."window" = done."window"' in conn.sql[-1]

    conn.rowcount = 1
    assert (
        NewsProjectionDirtyTargetRepository(conn).mark_error(
            [token],
            error="projection failed",
            retry_ms=30_000,
            now_ms=1_700_000_010_000,
            commit=False,
        )
        == 1
    )
    sql = conn.sql[-1]
    assert "SET due_at_ms = %(due_at_ms)s" in sql
    assert "leased_until_ms = NULL" in sql
    assert 'queue."window" = failed."window"' in sql
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert conn.params[-1]["last_error"] == "projection failed"


def test_terminalize_targets_commit_false_does_not_open_or_commit_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    claimed = {
        "projection_name": "brief_input",
        "target_kind": "news_item",
        "target_id": "item-1",
        "window": "",
        "payload_hash": "claim-hash",
        "lease_owner": "worker-a",
        "attempt_count": 2,
    }
    conn = _ScriptedConnection([[claimed]])
    terminal_events: list[dict[str, Any]] = []

    def fake_terminalize_source_row(conn_arg: Any, **kwargs: Any) -> dict[str, Any]:
        assert conn_arg is conn
        terminal_events.append(dict(kwargs))
        return {}

    monkeypatch.setattr(dirty_target_repository_module, "terminalize_source_row", fake_terminalize_source_row)

    count = NewsProjectionDirtyTargetRepository(conn).terminalize_targets(
        [claimed],
        worker_name="news_item_brief",
        final_reason="domain_validation_failed",
        final_reason_bucket="domain_validation_failed",
        now_ms=1_700_000_010_000,
        semantic_payload_hash="semantic-hash",
        commit=False,
    )

    assert count == 1
    assert conn.transaction_enters == 0
    assert conn.commits == 0
    assert terminal_events[0]["commit"] is False
    assert terminal_events[0]["payload_hash"] == "semantic-hash"
    assert terminal_events[0]["attempt_count"] == 2
    assert "DELETE FROM news_projection_dirty_targets queue" in conn.sql[-1]
    assert "RETURNING queue.*" in conn.sql[-1]


def test_queue_depth_counts_due_unleased_and_expired_leases() -> None:
    conn = _ScriptedConnection([[{"count": 9}]])

    depth = NewsProjectionDirtyTargetRepository(conn).queue_depth(
        now_ms=1_700_000_000_000,
        projection_name="source_quality",
    )

    sql = conn.sql[-1]
    assert depth == 9
    assert "count(*) AS count" in sql
    assert "due_at_ms <= %(now_ms)s" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql
    assert "projection_name = %(projection_name)s" in sql


def test_repository_session_exposes_news_projection_dirty_targets() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

    assert isinstance(session.news_projection_dirty_targets, NewsProjectionDirtyTargetRepository)


def test_postgres_news_enqueue_is_monotonic_and_keeps_earliest_due(postgres_conn) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
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
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "older-hash",
                "source_watermark_ms": 100,
                "priority": 10,
            }
        ],
        reason="older_reason",
        now_ms=1_700_000_010_000,
        due_at_ms=1_700_000_050_000,
    )

    row = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()
    assert row["source_watermark_ms"] == 200
    assert row["payload_hash"] == "newer-hash"
    assert row["dirty_reason"] == "newer_reason"
    assert row["due_at_ms"] == 1_700_000_050_000
    assert row["priority"] == 10
    assert row["first_dirty_at_ms"] == 1_700_000_000_000
    assert row["last_error"] is None


def test_postgres_news_single_call_coalesces_monotonically_when_older_follows_newer(postgres_conn) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "newer-hash",
                "source_watermark_ms": 300,
                "priority": 50,
            },
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "older-hash",
                "source_watermark_ms": 200,
                "priority": 5,
            },
        ],
        reason="same_call_reason",
        now_ms=1_700_000_000_000,
    )

    row = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()
    assert row["source_watermark_ms"] == 300
    assert row["payload_hash"] == "newer-hash"
    assert row["dirty_reason"] == "same_call_reason"
    assert row["priority"] == 5


def test_postgres_news_single_call_fallback_hash_uses_newer_material_identity_not_min_priority(
    postgres_conn,
) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "source_watermark_ms": 300,
                "priority": 50,
            },
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "source_watermark_ms": 200,
                "priority": 0,
            },
        ],
        reason="same_call_reason",
        now_ms=1_700_000_000_000,
    )
    coalesced = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()

    postgres_conn.execute("TRUNCATE news_projection_dirty_targets")
    postgres_conn.commit()
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
                "source_watermark_ms": 300,
                "priority": 50,
            }
        ],
        reason="same_call_reason",
        now_ms=1_700_000_010_000,
    )
    single_newer = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()

    assert coalesced["source_watermark_ms"] == 300
    assert coalesced["priority"] == 0
    assert coalesced["payload_hash"] == single_newer["payload_hash"]


def test_postgres_news_duplicate_while_leased_preserves_claim_but_material_update_invalidates_it(postgres_conn) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)
    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
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
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "hash-1",
                "source_watermark_ms": 100,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_002_000,
    )

    duplicate_row = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()
    assert duplicate_row["lease_owner"] == "worker-a"
    assert duplicate_row["leased_until_ms"] == 1_700_000_061_000
    assert repo.mark_done([first_claim], now_ms=1_700_000_003_000) == 1

    repo.enqueue_targets(
        [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "item-1",
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
                "target_kind": "news_item",
                "target_id": "item-1",
                "payload_hash": "hash-2",
                "source_watermark_ms": 101,
            }
        ],
        reason="reason-1",
        now_ms=1_700_000_006_000,
    )

    material_row = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()
    assert material_row["lease_owner"] is None
    assert material_row["leased_until_ms"] is None
    assert material_row["payload_hash"] == "hash-2"
    assert material_row["source_watermark_ms"] == 101
    assert repo.mark_done([stale_claim], now_ms=1_700_000_007_000) == 0
    assert repo.mark_error([stale_claim], error="stale", retry_ms=30_000, now_ms=1_700_000_008_000) == 0


def test_postgres_news_fallback_hash_duplicate_while_leased_is_stable(postgres_conn) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)
    row = {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "item-1",
        "source_watermark_ms": 100,
        "priority": 20,
    }

    repo.enqueue_targets([row], reason="reason-1", now_ms=1_700_000_000_000)
    first_claim = repo.claim_due(limit=1, lease_ms=60_000, now_ms=1_700_000_001_000, lease_owner="worker-a")[0]
    first_hash = first_claim["payload_hash"]
    repo.enqueue_targets([{**row, "priority": 5}], reason="reason-1", now_ms=1_700_000_030_000)

    duplicate_row = postgres_conn.execute("SELECT * FROM news_projection_dirty_targets").fetchone()
    assert duplicate_row["payload_hash"] == first_hash
    assert duplicate_row["lease_owner"] == "worker-a"
    assert duplicate_row["leased_until_ms"] == 1_700_000_061_000
    assert duplicate_row["priority"] == 5
    assert repo.mark_done([first_claim], now_ms=1_700_000_031_000) == 1


def test_postgres_news_source_quality_window_uniqueness(postgres_conn) -> None:
    repo = NewsProjectionDirtyTargetRepository(postgres_conn)

    count = repo.enqueue_targets(
        [
            {
                "projection_name": "source_quality",
                "target_kind": "source",
                "target_id": "source-1",
                "window": "24h",
                "payload_hash": "hash-24h",
            },
            {
                "projection_name": "source_quality",
                "target_kind": "source",
                "target_id": "source-1",
                "window": "7d",
                "payload_hash": "hash-7d",
            },
        ],
        reason="source_quality_window_due",
        now_ms=1_700_000_000_000,
    )

    rows = postgres_conn.execute(
        """
        SELECT target_id, "window", payload_hash
        FROM news_projection_dirty_targets
        ORDER BY "window"
        """
    ).fetchall()
    assert count == 2
    assert [dict(row) for row in rows] == [
        {"target_id": "source-1", "window": "24h", "payload_hash": "hash-24h"},
        {"target_id": "source-1", "window": "7d", "payload_hash": "hash-7d"},
    ]


def test_terminalize_targets_deletes_hot_row_and_records_terminal_event(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsProjectionDirtyTargetRepository(conn)
        now = 1_779_000_000_000
        repo.enqueue_targets(
            [{"projection_name": "brief_input", "target_kind": "news_item", "target_id": "item-terminal"}],
            reason="unit",
            now_ms=now,
        )
        claimed = repo.claim_due(limit=1, lease_ms=60_000, now_ms=now, lease_owner="worker:test")

        count = repo.terminalize_targets(
            claimed,
            worker_name="news_item_brief",
            final_reason="domain_validation_failed",
            final_reason_bucket="domain_validation_failed",
            semantic_payload_hash="semantic-hash-1",
            now_ms=now + 1,
        )

        row = conn.execute(
            """
            SELECT *
            FROM worker_queue_terminal_events
            WHERE worker_name = 'news_item_brief'
              AND source_table = 'news_projection_dirty_targets'
              AND target_key LIKE '%semantic-hash-1'
            """
        ).fetchone()
        depth = repo.queue_depth(now_ms=now + 1, projection_name="brief_input")
    finally:
        conn.close()

    assert count == 1
    assert depth == 0
    assert row is not None
    assert row["final_reason_bucket"] == "domain_validation_failed"


def test_terminalize_targets_skips_event_when_claim_token_is_stale(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsProjectionDirtyTargetRepository(conn)
        now = 1_779_000_000_000
        repo.enqueue_targets(
            [
                {
                    "projection_name": "brief_input",
                    "target_kind": "news_item",
                    "target_id": "item-stale-terminal",
                    "payload_hash": "claim-hash",
                }
            ],
            reason="unit",
            now_ms=now,
        )
        claimed = repo.claim_due(limit=1, lease_ms=60_000, now_ms=now, lease_owner="worker:test")
        conn.execute(
            """
            UPDATE news_projection_dirty_targets
            SET payload_hash = 'replacement-hash'
            WHERE target_id = 'item-stale-terminal'
            """
        )
        conn.commit()

        count = repo.terminalize_targets(
            claimed,
            worker_name="news_item_brief",
            final_reason="domain_validation_failed",
            final_reason_bucket="domain_validation_failed",
            semantic_payload_hash="semantic-stale-hash",
            now_ms=now + 1,
        )

        row = conn.execute(
            """
            SELECT *
            FROM worker_queue_terminal_events
            WHERE worker_name = 'news_item_brief'
              AND source_table = 'news_projection_dirty_targets'
              AND target_key LIKE '%semantic-stale-hash'
            """
        ).fetchone()
    finally:
        conn.close()

    assert count == 0
    assert row is None


@pytest.fixture
def postgres_conn(tmp_path) -> Iterator[object]:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute(
            """
            CREATE TEMP TABLE news_projection_dirty_targets (
              projection_name TEXT NOT NULL,
              target_kind TEXT NOT NULL,
              target_id TEXT NOT NULL,
              "window" TEXT NOT NULL DEFAULT '',
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
              PRIMARY KEY (projection_name, target_kind, target_id, "window")
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
        self.transaction_enters = 0

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

    def transaction(self) -> _ScriptedTransaction:
        return _ScriptedTransaction(self)


class _ScriptedTransaction:
    def __init__(self, conn: _ScriptedConnection) -> None:
        self.conn = conn

    def __enter__(self) -> _ScriptedTransaction:
        self.conn.transaction_enters += 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.conn.commit()
