from __future__ import annotations

from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.narrative_intel.repositories.discussion_digest_dirty_target_repository import (
    DiscussionDigestDirtyTargetRepository,
)
from parallax.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository import (
    NarrativeAdmissionDirtyTargetRepository,
)


def test_enqueue_targets_coalesces_by_full_narrative_key_and_versions() -> None:
    conn = _ScriptedConnection([])

    count = NarrativeAdmissionDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "projection_version": "admission-v1",
                "schema_version": "schema-v1",
                "source_watermark_ms": 10,
                "priority": 50,
                "payload_hash": "payload-old",
            },
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "projection_version": "admission-v2",
                "schema_version": "schema-v2",
                "source_watermark_ms": 11,
                "priority": 20,
                "payload_hash": "payload-new",
            },
        ],
        reason="token_radar_changed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == {"targets": 1}
    assert "INSERT INTO narrative_admission_dirty_targets" in sql
    assert 'ON CONFLICT(target_type, target_id, "window", scope) DO UPDATE SET' in sql
    assert "projection_version = CASE" in sql
    assert "schema_version = CASE" in sql
    assert "priority = LEAST(narrative_admission_dirty_targets.priority, EXCLUDED.priority)" in sql
    assert "first_dirty_at_ms = narrative_admission_dirty_targets.first_dirty_at_ms" in sql
    assert "leased_until_ms = CASE" in sql
    assert conn.params[-1]["target_types"] == ["Asset"]
    assert conn.params[-1]["target_ids"] == ["asset-1"]
    assert conn.params[-1]["windows"] == ["1h"]
    assert conn.params[-1]["scopes"] == ["all"]
    assert conn.params[-1]["projection_versions"] == ["admission-v2"]
    assert conn.params[-1]["schema_versions"] == ["schema-v2"]
    assert conn.params[-1]["payload_hashes"] == ["payload-new"]
    assert conn.params[-1]["source_watermark_ms_values"] == [11]
    assert conn.params[-1]["priorities"] == [20]
    assert conn.params[-1]["dirty_reason"] == "token_radar_changed"


def test_enqueue_targets_rejects_incomplete_narrative_target() -> None:
    conn = _ScriptedConnection([])

    with pytest.raises(ValueError, match="projection_version, schema_version"):
        NarrativeAdmissionDirtyTargetRepository(conn).enqueue_targets(
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-ignored",
                    "window": "1h",
                    "scope": "all",
                    "source_watermark_ms": 12,
                }
            ],
            reason="token_radar_changed",
            now_ms=1_700_000_000_000,
            commit=False,
        )
    assert conn.sql == []


def test_digest_claim_due_orders_by_priority_due_and_updated_and_increments_attempts() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "projection_version": "digest-v1",
                    "schema_version": "schema-v1",
                    "payload_hash": "payload-1",
                    "lease_owner": "digest-a",
                    "attempt_count": 1,
                    "source_watermark_ms": 10,
                    "dirty_reason": "admission_changed",
                }
            ]
        ]
    )

    rows = DiscussionDigestDirtyTargetRepository(conn).claim_due(
        now_ms=1_700_000_000_000,
        limit=25,
        lease_owner="digest-a",
        lease_ms=60_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows[0]["projection_version"] == "digest-v1"
    assert rows[0]["schema_version"] == "schema-v1"
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY priority ASC," in sql
    assert "due_at_ms ASC," in sql
    assert "updated_at_ms ASC" in sql
    assert "attempt_count = discussion_digest_dirty_targets.attempt_count + 1" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "digest-a"


def test_mark_done_requires_full_stale_completion_token_including_versions() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    deleted = NarrativeAdmissionDirtyTargetRepository(conn).mark_done(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "projection_version": "admission-v1",
                "schema_version": "schema-v1",
                "payload_hash": "payload-1",
                "lease_owner": "admission-a",
                "attempt_count": 2,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 1
    assert "DELETE FROM narrative_admission_dirty_targets queue" in sql
    assert "queue.projection_version = done.projection_version" in sql
    assert "queue.schema_version = done.schema_version" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert conn.params[-1]["projection_versions"] == ["admission-v1"]
    assert conn.params[-1]["schema_versions"] == ["schema-v1"]
    assert conn.params[-1]["payload_hashes"] == ["payload-1"]
    assert conn.params[-1]["lease_owners"] == ["admission-a"]
    assert conn.params[-1]["attempt_counts"] == [2]


def test_mark_error_releases_digest_claim_and_schedules_retry() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = DiscussionDigestDirtyTargetRepository(conn).mark_error(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "projection_version": "digest-v1",
                "schema_version": "schema-v1",
                "payload_hash": "payload-1",
                "lease_owner": "digest-a",
                "attempt_count": 3,
            }
        ],
        error="x" * 3000,
        now_ms=1_700_000_010_000,
        retry_ms=30_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated == 1
    assert "UPDATE discussion_digest_dirty_targets queue" in sql
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "last_error = %(last_error)s" in sql
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert len(conn.params[-1]["last_error"]) == 2048


def test_reschedule_releases_admission_claim_without_overwriting_business_reason() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = NarrativeAdmissionDirtyTargetRepository(conn).reschedule(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "projection_version": "admission-v1",
                "schema_version": "schema-v1",
                "payload_hash": "payload-1",
                "lease_owner": "admission-a",
                "attempt_count": 3,
            }
        ],
        due_at_ms=1_700_000_120_000,
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    set_clause = sql.split("SET", 1)[1].split("FROM", 1)[0]
    assert updated == 1
    assert "leased_until_ms = NULL" in set_clause
    assert "lease_owner = NULL" in set_clause
    assert "dirty_reason =" not in set_clause
    assert "attempt_count =" not in set_clause
    assert "max_attempt" not in sql.lower()
    assert conn.params[-1]["due_at_ms"] == 1_700_000_120_000


def test_queue_depth_counts_unleased_due_targets() -> None:
    conn = _ScriptedConnection([[{"count": 7}]])

    depth = DiscussionDigestDirtyTargetRepository(conn).queue_depth(now_ms=1_700_000_010_000)

    assert depth == 7
    assert "FROM discussion_digest_dirty_targets" in conn.sql[-1]
    assert "(leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)" in conn.sql[-1]


def test_completion_rejects_claim_without_projection_version() -> None:
    conn = _ScriptedConnection([])

    try:
        NarrativeAdmissionDirtyTargetRepository(conn).mark_done(
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "schema_version": "schema-v1",
                    "payload_hash": "payload-1",
                    "lease_owner": "admission-a",
                    "attempt_count": 1,
                }
            ],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "projection_version" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed projection_version")

    assert conn.sql == []


def test_repository_session_exposes_narrative_dirty_targets() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

    assert isinstance(session.narrative_admission_dirty_targets, NarrativeAdmissionDirtyTargetRepository)
    assert isinstance(session.discussion_digest_dirty_targets, DiscussionDigestDirtyTargetRepository)


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
