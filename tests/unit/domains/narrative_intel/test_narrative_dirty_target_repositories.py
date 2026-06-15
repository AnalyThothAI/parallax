from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository import (
    NarrativeAdmissionDirtyTargetRepository,
    _payload_hash,
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
            "projection_version": "admission-v1",
            "schema_version": "schema-v1",
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
            "projection_version": "admission-v1",
            "schema_version": "schema-v1",
            "source_watermark_ms": 123,
            "dirty_reason": "token_radar_changed",
            "priority": 90,
            "due_at_ms": 999,
            "leased_until_ms": 888,
            "attempt_count": 3,
        }
    )

    assert second == first


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.enqueue_targets(
                [_target()],
                reason="token_radar_changed",
                now_ms=1_700_000_000_000,
            ),
            id="enqueue_targets",
        ),
        pytest.param(
            lambda repo: repo.claim_due(
                now_ms=1_700_000_000_000,
                limit=1,
                lease_owner="narrative_admission",
                lease_ms=60_000,
            ),
            id="claim_due",
        ),
        pytest.param(
            lambda repo: repo.mark_done([_claim()], now_ms=1_700_000_010_000),
            id="mark_done",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim()],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=30_000,
            ),
            id="mark_error",
        ),
        pytest.param(
            lambda repo: repo.reschedule(
                [_claim()],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
            ),
            id="reschedule",
        ),
    ],
)
def test_dirty_target_mutations_require_connection_transaction_before_sql_when_committing(operation) -> None:
    conn = _NoTransactionConnection([])

    with pytest.raises(RuntimeError, match="narrative_admission_dirty_target_transaction_required"):
        operation(NarrativeAdmissionDirtyTargetRepository(conn))

    assert conn.sql == []


def test_enqueue_targets_commit_owned_write_uses_connection_transaction_without_manual_commit() -> None:
    conn = _ScriptedConnection([])

    count = NarrativeAdmissionDirtyTargetRepository(conn).enqueue_targets(
        [_target()],
        reason="token_radar_changed",
        now_ms=1_700_000_000_000,
    )

    assert count == {"targets": 1}
    assert conn.transaction_commits == 1
    assert conn.manual_commits == 0
    assert conn.sql_depths == [1]


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


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False),
            "narrative_admission_dirty_target_rowcount_required",
            id="done",
        ),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=30_000,
                commit=False,
            ),
            "narrative_admission_dirty_target_rowcount_required",
            id="error",
        ),
        pytest.param(
            lambda repo, claim: repo.reschedule(
                [claim],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            "narrative_admission_dirty_target_rowcount_required",
            id="reschedule",
        ),
    ],
)
def test_completion_write_counts_require_cursor_rowcount(
    operation: Callable[[NarrativeAdmissionDirtyTargetRepository, dict[str, Any]], int],
    error_code: str,
) -> None:
    conn = _ScriptedConnection([], omit_rowcount=True)

    with pytest.raises(TypeError, match=error_code):
        operation(NarrativeAdmissionDirtyTargetRepository(conn), _claim())


@pytest.mark.parametrize(
    "rowcount",
    [
        pytest.param("bad", id="string"),
        pytest.param(True, id="bool"),
        pytest.param(-1, id="negative"),
    ],
)
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=30_000,
                commit=False,
            ),
            id="error",
        ),
        pytest.param(
            lambda repo, claim: repo.reschedule(
                [claim],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            id="reschedule",
        ),
    ],
)
def test_completion_write_counts_reject_invalid_cursor_rowcount(
    operation: Callable[[NarrativeAdmissionDirtyTargetRepository, dict[str, Any]], int],
    rowcount: object,
) -> None:
    conn = _ScriptedConnection([], rowcount=rowcount)

    with pytest.raises(TypeError, match="narrative_admission_dirty_target_rowcount_invalid"):
        operation(NarrativeAdmissionDirtyTargetRepository(conn), _claim())


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=30_000,
                commit=False,
            ),
            id="error",
        ),
        pytest.param(
            lambda repo, claim: repo.reschedule(
                [claim],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            id="reschedule",
        ),
    ],
)
def test_completion_requires_claim_attempt_field_without_default(operation) -> None:
    conn = _ScriptedConnection([])
    claim = _claim()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="narrative admission dirty target completion requires attempt_count",
    ) as exc_info:
        operation(NarrativeAdmissionDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


def test_repository_session_exposes_narrative_dirty_targets() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        pulse_job_running_timeout_ms=300_000,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.narrative_admission_dirty_targets, NarrativeAdmissionDirtyTargetRepository)


def _target() -> dict[str, Any]:
    return {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "projection_version": "admission-v1",
        "schema_version": "schema-v1",
        "source_watermark_ms": 10,
        "priority": 50,
        "payload_hash": "payload-1",
    }


def _claim() -> dict[str, Any]:
    return {
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


class _ScriptedConnection:
    def __init__(
        self,
        results: list[list[dict[str, Any]] | None],
        *,
        rowcount: object = 0,
        omit_rowcount: bool = False,
    ) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.sql_depths: list[int] = []
        if not omit_rowcount:
            self.rowcount = rowcount
        self.manual_commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        self.sql_depths.append(self.transaction_depth)
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
        self.manual_commits += 1

    def transaction(self) -> _Transaction:
        return _Transaction(self)


class _NoTransactionConnection(_ScriptedConnection):
    transaction = None


class _Transaction:
    def __init__(self, conn: _ScriptedConnection) -> None:
        self.conn = conn

    def __enter__(self) -> _ScriptedConnection:
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args) -> bool:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False
