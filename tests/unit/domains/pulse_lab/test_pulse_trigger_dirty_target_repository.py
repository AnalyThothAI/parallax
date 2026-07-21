from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.pulse_lab.repositories.pulse_trigger_dirty_target_repository import (
    PulseTriggerDirtyTargetRepository,
    _payload_hash,
)

_MISSING = object()


def test_enqueue_targets_coalesces_by_full_pulse_key_and_uses_lower_priority() -> None:
    conn = _ScriptedConnection([], rowcount=1)

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


@pytest.mark.parametrize(
    "source_watermark_ms",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_enqueue_targets_requires_formal_source_watermark_without_zero_fallback(source_watermark_ms: object) -> None:
    conn = _ScriptedConnection([])
    target: dict[str, Any] = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
    }
    if source_watermark_ms is not _MISSING:
        target["source_watermark_ms"] = source_watermark_ms

    with pytest.raises(ValueError, match="pulse_trigger_dirty_target_source_watermark_required"):
        PulseTriggerDirtyTargetRepository(conn).enqueue_targets(
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


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"limit": 0}, "pulse_trigger_dirty_target_claim_limit_required", id="zero-limit"),
        pytest.param({"limit": -1}, "pulse_trigger_dirty_target_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "pulse_trigger_dirty_target_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "pulse_trigger_dirty_target_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "pulse_trigger_dirty_target_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": -1}, "pulse_trigger_dirty_target_claim_lease_ms_required", id="negative-lease"),
        pytest.param({"lease_ms": True}, "pulse_trigger_dirty_target_claim_lease_ms_required", id="bool-lease"),
        pytest.param({"lease_ms": "60000"}, "pulse_trigger_dirty_target_claim_lease_ms_required", id="string-lease"),
        pytest.param({"lease_owner": ""}, "pulse_trigger_dirty_target_claim_lease_owner_required", id="empty-owner"),
    ],
)
def test_claim_due_requires_formal_claim_contract_before_sql(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    conn = _ScriptedConnection([])
    kwargs: dict[str, object] = {
        "now_ms": 1_700_000_000_000,
        "limit": 25,
        "lease_owner": "pulse-a",
        "lease_ms": 60_000,
        "commit": False,
        **overrides,
    }

    with pytest.raises(ValueError, match=error_code):
        PulseTriggerDirtyTargetRepository(conn).claim_due(**kwargs)  # type: ignore[arg-type]

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


def test_mark_error_terminalizes_exhausted_claims_into_queue_terminal() -> None:
    claim = {
        **_claimed_dirty_target(),
        "attempt_count": 2,
        "dirty_reason": "token_radar_changed",
        "source_watermark_ms": 1_700_000_000_000,
        "first_dirty_at_ms": 1_700_000_000_000,
        "updated_at_ms": 1_700_000_005_000,
    }
    conn = _ScriptedConnection(
        [
            [claim],
            [],
            [{"terminal_generation": 1}],
            [{"terminal_id": "terminal-1", "source_row_json": {}}],
        ],
        rowcount=1,
    )

    changed = PulseTriggerDirtyTargetRepository(conn).mark_error(
        [claim],
        error="boom",
        now_ms=1_700_000_010_000,
        retry_ms=30_000,
        max_attempts=2,
        worker_name="pulse_candidate",
        commit=False,
    )

    assert changed == 1
    assert any(
        "DELETE FROM pulse_trigger_dirty_targets queue" in sql and "RETURNING queue.*" in sql for sql in conn.sql
    )
    assert any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)
    terminal_params = conn.params[-1]
    assert terminal_params["worker_name"] == "pulse_candidate"
    assert terminal_params["source_table"] == "pulse_trigger_dirty_targets"
    assert terminal_params["final_status"] == "terminal"
    assert terminal_params["final_reason"] == "pulse_trigger_dirty_retry_budget_exhausted: boom"
    assert terminal_params["attempt_count"] == 2


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"retry_ms": 0}, "pulse_trigger_dirty_target_retry_ms_required", id="zero-retry"),
        pytest.param({"retry_ms": -1}, "pulse_trigger_dirty_target_retry_ms_required", id="negative-retry"),
        pytest.param({"retry_ms": True}, "pulse_trigger_dirty_target_retry_ms_required", id="bool-retry"),
        pytest.param({"retry_ms": "30000"}, "pulse_trigger_dirty_target_retry_ms_required", id="string-retry"),
        pytest.param({"max_attempts": 0}, "pulse_trigger_dirty_target_max_attempts_required", id="zero-max"),
        pytest.param({"max_attempts": -1}, "pulse_trigger_dirty_target_max_attempts_required", id="negative-max"),
        pytest.param({"max_attempts": True}, "pulse_trigger_dirty_target_max_attempts_required", id="bool-max"),
        pytest.param({"max_attempts": "3"}, "pulse_trigger_dirty_target_max_attempts_required", id="string-max"),
    ],
)
def test_mark_error_requires_formal_retry_contract_before_sql(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    conn = _ScriptedConnection([])
    kwargs: dict[str, object] = {
        "error": "boom",
        "now_ms": 1_700_000_010_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "worker_name": "pulse_candidate",
        "commit": False,
        **overrides,
    }

    with pytest.raises(ValueError, match=error_code):
        PulseTriggerDirtyTargetRepository(conn).mark_error([_claimed_dirty_target()], **kwargs)  # type: ignore[arg-type]

    assert conn.sql == []


def test_completion_rejects_claim_without_payload_hash() -> None:
    conn = _ScriptedConnection([])

    try:
        PulseTriggerDirtyTargetRepository(conn).mark_done(
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "attempt_count": 1,
                }
            ],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed payload_hash")

    assert conn.sql == []


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False),
            "pulse_trigger_dirty_target_rowcount_required",
            id="done",
        ),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=30_000,
                max_attempts=3,
                worker_name="pulse_candidate",
                commit=False,
            ),
            "pulse_trigger_dirty_target_rowcount_required",
            id="error",
        ),
        pytest.param(
            lambda repo, claim: repo.reschedule(
                [claim],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            "pulse_trigger_dirty_target_rowcount_required",
            id="reschedule",
        ),
    ],
)
def test_completion_write_counts_require_cursor_rowcount(
    operation: Callable[[PulseTriggerDirtyTargetRepository, dict[str, Any]], int],
    error_code: str,
) -> None:
    conn = _ScriptedConnection([], omit_rowcount=True)

    with pytest.raises(TypeError, match=error_code):
        operation(PulseTriggerDirtyTargetRepository(conn), _claimed_dirty_target())


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
                max_attempts=3,
                worker_name="pulse_candidate",
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
    operation: Callable[[PulseTriggerDirtyTargetRepository, dict[str, Any]], int],
    rowcount: object,
) -> None:
    conn = _ScriptedConnection([], rowcount=rowcount)

    with pytest.raises(TypeError, match="pulse_trigger_dirty_target_rowcount_invalid"):
        operation(PulseTriggerDirtyTargetRepository(conn), _claimed_dirty_target())


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
                max_attempts=3,
                worker_name="pulse_candidate",
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
    claim = _claimed_dirty_target()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="pulse trigger dirty target completion requires attempt_count",
    ) as exc_info:
        operation(PulseTriggerDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


@pytest.mark.parametrize("attempt_count", [0, True, "1"])
def test_completion_rejects_malformed_claim_attempt_before_sql(attempt_count: object) -> None:
    conn = _ScriptedConnection([])
    claim = {**_claimed_dirty_target(), "attempt_count": attempt_count}

    with pytest.raises(
        ValueError,
        match="pulse trigger dirty target completion requires attempt_count",
    ):
        PulseTriggerDirtyTargetRepository(conn).mark_done(
            [claim],
            now_ms=1_700_000_010_000,
            commit=False,
        )

    assert conn.sql == []


def test_repository_session_exposes_pulse_trigger_dirty_targets() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        pulse_job_running_timeout_ms=300_000,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.pulse_trigger_dirty_targets, PulseTriggerDirtyTargetRepository)


@pytest.mark.parametrize(
    ("method_name", "operation"),
    [
        (
            "enqueue_targets",
            lambda repository: repository.enqueue_targets(
                [
                    {
                        "target_type": "Asset",
                        "target_id": "asset-1",
                        "window": "1h",
                        "scope": "all",
                        "source_watermark_ms": 10,
                    }
                ],
                reason="token_radar_changed",
                now_ms=1_700_000_000_000,
            ),
        ),
        (
            "claim_due",
            lambda repository: repository.claim_due(
                now_ms=1_700_000_000_000,
                limit=25,
                lease_owner="pulse-a",
                lease_ms=60_000,
            ),
        ),
        (
            "mark_done",
            lambda repository: repository.mark_done(
                [_claimed_dirty_target()],
                now_ms=1_700_000_010_000,
            ),
        ),
        (
            "mark_error",
            lambda repository: repository.mark_error(
                [_claimed_dirty_target()],
                error="boom",
                now_ms=1_700_000_010_000,
                retry_ms=60_000,
                max_attempts=3,
                worker_name="pulse_candidate",
            ),
        ),
        (
            "reschedule",
            lambda repository: repository.reschedule(
                [_claimed_dirty_target()],
                due_at_ms=1_700_000_120_000,
                now_ms=1_700_000_010_000,
            ),
        ),
    ],
)
def test_pulse_trigger_dirty_target_mutations_require_connection_transaction_before_sql_when_committing(
    method_name: str,
    operation: Callable[[PulseTriggerDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="pulse_repository_transaction_required"):
        operation(PulseTriggerDirtyTargetRepository(conn))

    assert conn.sql == [], method_name


def _claimed_dirty_target() -> dict[str, Any]:
    return {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "payload-1",
        "lease_owner": "pulse-a",
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
        if not omit_rowcount:
            self.rowcount = rowcount
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            if hasattr(self, "rowcount"):
                self.rowcount = 0
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        if hasattr(self, "rowcount"):
            self.rowcount = len(result)
        return result

    def fetchone(self) -> dict[str, Any] | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def commit(self) -> None:
        self.commits += 1


class _MissingTransactionConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _MissingTransactionConnection:
        del params
        self.sql.append(str(sql))
        raise AssertionError("SQL executed before transaction contract was required")
