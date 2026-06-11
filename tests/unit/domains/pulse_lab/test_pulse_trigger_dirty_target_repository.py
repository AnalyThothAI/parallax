from __future__ import annotations

from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.pulse_lab.repositories.pulse_trigger_dirty_target_repository import (
    PulseTriggerDirtyTargetRepository,
    _payload_hash,
)


def test_enqueue_targets_coalesces_by_full_pulse_key_and_uses_lower_priority() -> None:
    conn = _ScriptedConnection([])

    count = PulseTriggerDirtyTargetRepository(conn).enqueue_targets(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "source_watermark_ms": 10,
                "priority": 50,
                "payload_hash": "payload-old",
            },
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "source_watermark_ms": 11,
                "priority": 20,
                "payload_hash": "payload-new",
            },
            {"target_type": "", "target_id": "asset-ignored", "window": "1h", "scope": "all"},
        ],
        reason="token_radar_changed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == {"targets": 1}
    assert "INSERT INTO pulse_trigger_dirty_targets" in sql
    assert 'ON CONFLICT(target_type, target_id, "window", scope) DO UPDATE SET' in sql
    assert "priority = LEAST(pulse_trigger_dirty_targets.priority, EXCLUDED.priority)" in sql
    assert "first_dirty_at_ms = pulse_trigger_dirty_targets.first_dirty_at_ms" in sql
    assert "leased_until_ms = CASE" in sql
    assert conn.params[-1]["target_types"] == ["Asset"]
    assert conn.params[-1]["target_ids"] == ["asset-1"]
    assert conn.params[-1]["windows"] == ["1h"]
    assert conn.params[-1]["scopes"] == ["all"]
    assert conn.params[-1]["payload_hashes"] == ["payload-new"]
    assert conn.params[-1]["source_watermark_ms_values"] == [11]
    assert conn.params[-1]["priorities"] == [20]
    assert conn.params[-1]["dirty_reason"] == "token_radar_changed"


def test_claim_due_orders_by_priority_due_and_updated_and_increments_attempts() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "payload_hash": "payload-1",
                    "lease_owner": "pulse-a",
                    "attempt_count": 1,
                    "source_watermark_ms": 10,
                    "dirty_reason": "token_radar_changed",
                }
            ]
        ]
    )

    rows = PulseTriggerDirtyTargetRepository(conn).claim_due(
        now_ms=1_700_000_000_000,
        limit=25,
        lease_owner="pulse-a",
        lease_ms=60_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows[0]["payload_hash"] == "payload-1"
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY priority ASC," in sql
    assert "due_at_ms ASC," in sql
    assert "updated_at_ms ASC" in sql
    assert "attempt_count = pulse_trigger_dirty_targets.attempt_count + 1" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "pulse-a"


def test_payload_hash_rejects_legacy_non_string_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _payload_hash({123: "legacy", "target_type": "Asset", "target_id": "asset-1"})


def test_payload_hash_ignores_queue_lifecycle_fields() -> None:
    first = _payload_hash(
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "window": "1h",
            "scope": "all",
            "source_watermark_ms": 123,
            "dirty_reason": "token_radar_changed",
            "priority": 10,
            "due_at_ms": 100,
            "leased_until_ms": 200,
            "attempt_count": 1,
        }
    )
    second = _payload_hash(
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "window": "1h",
            "scope": "all",
            "source_watermark_ms": 123,
            "dirty_reason": "token_radar_changed",
            "priority": 90,
            "due_at_ms": 999,
            "leased_until_ms": 888,
            "attempt_count": 3,
        }
    )

    assert second == first


def test_mark_done_requires_full_stale_completion_token() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    deleted = PulseTriggerDirtyTargetRepository(conn).mark_done(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "payload_hash": "payload-1",
                "lease_owner": "pulse-a",
                "attempt_count": 2,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 1
    assert "DELETE FROM pulse_trigger_dirty_targets queue" in sql
    assert 'queue."window" = done."window"' in sql
    assert "queue.scope = done.scope" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert conn.params[-1]["payload_hashes"] == ["payload-1"]
    assert conn.params[-1]["lease_owners"] == ["pulse-a"]
    assert conn.params[-1]["attempt_counts"] == [2]


def test_reschedule_releases_claim_without_terminal_attempt_limit() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = PulseTriggerDirtyTargetRepository(conn).reschedule(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "payload_hash": "payload-1",
                "lease_owner": "pulse-a",
                "attempt_count": 3,
            }
        ],
        due_at_ms=1_700_000_120_000,
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated == 1
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "dirty_reason =" not in sql.split("SET", 1)[1].split("FROM", 1)[0]
    assert "attempt_count =" not in sql.split("SET", 1)[1].split("FROM", 1)[0]
    assert "max_attempt" not in sql.lower()
    assert conn.params[-1]["due_at_ms"] == 1_700_000_120_000


def test_completion_rejects_claim_without_payload_hash() -> None:
    conn = _ScriptedConnection([])

    try:
        PulseTriggerDirtyTargetRepository(conn).mark_done(
            [{"target_type": "Asset", "target_id": "asset-1", "window": "1h", "scope": "all"}],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed payload_hash")

    assert conn.sql == []


def test_repository_session_exposes_pulse_trigger_dirty_targets() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

    assert isinstance(session.pulse_trigger_dirty_targets, PulseTriggerDirtyTargetRepository)


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
