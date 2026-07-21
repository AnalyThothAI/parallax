from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import ClassVar

import pytest


def test_source_dirty_event_queue_coalesces_by_source_event_edge() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    repo = module.TokenRadarSourceDirtyEventRepository(_ScriptedConnection(rowcount=1))

    count = repo.enqueue_events(
        [
            {"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"},
            {"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"},
        ],
        reason="resolution_updated",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = "\n".join(_ScriptedConnection.last_sql)
    assert count == 1
    assert "INSERT INTO token_radar_source_dirty_events" in sql
    assert "ON CONFLICT(projection_version, source_event_id, target_type_key, identity_id) DO UPDATE SET" in sql
    assert "source_event_ids_json" not in sql
    assert "jsonb_agg" not in sql
    assert _ScriptedConnection.last_params[-1]["source_event_ids"] == ["event-1"]
    assert _ScriptedConnection.last_params[-1]["target_type_keys"] == ["Asset"]
    assert _ScriptedConnection.last_params[-1]["identity_ids"] == ["asset-1"]


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            {"event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"},
            id="event-id-alias",
        ),
        pytest.param(
            {"source_event_id": "event-1", "target_type": "Asset", "target_id": "asset-1"},
            id="legacy-target-aliases",
        ),
        pytest.param(
            {"source_event_id": "event-1", "target_type_key": "Asset", "target_id": "asset-1"},
            id="legacy-identity-alias",
        ),
        pytest.param({"source_event_id": "", "target_type_key": "Asset", "identity_id": "asset-1"}, id="blank-event"),
    ],
)
def test_source_dirty_event_enqueue_requires_formal_edge_identity_without_alias_fallback(
    row: dict[str, str],
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    repo = module.TokenRadarSourceDirtyEventRepository(_ScriptedConnection())

    with pytest.raises(ValueError, match="token_radar_source_dirty_event_enqueue_identity_required"):
        repo.enqueue_events(
            [row],
            reason="resolution_updated",
            now_ms=1_700_000_000_000,
            commit=False,
        )

    assert _ScriptedConnection.last_sql == []


def test_source_dirty_event_payload_hash_ignores_lease_lifecycle() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")

    first = module.source_dirty_event_payload_hash(
        {
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_at_ms": 1,
            "leased_until_ms": 2,
            "attempt_count": 3,
        }
    )
    second = module.source_dirty_event_payload_hash(
        {
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_at_ms": 9,
            "leased_until_ms": 10,
            "attempt_count": 11,
        }
    )

    assert second == first


def test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        module.source_dirty_event_payload_hash(
            {123: "legacy", "source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"}
        )


def test_source_dirty_event_claim_due_requires_returning_rowcount() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_required"):
        module.TokenRadarSourceDirtyEventRepository(conn).claim_due(
            limit=25,
            lease_ms=60_000,
            now_ms=1_700_000_000_000,
            lease_owner="worker-a",
            commit=False,
        )


def test_source_dirty_event_claim_due_rejects_returning_rowcount_mismatch() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(rowcount=2)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_invalid"):
        module.TokenRadarSourceDirtyEventRepository(conn).claim_due(
            limit=25,
            lease_ms=60_000,
            now_ms=1_700_000_000_000,
            lease_owner="worker-a",
            commit=False,
        )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "token_radar_source_dirty_event_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "token_radar_source_dirty_event_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "token_radar_source_dirty_event_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "token_radar_source_dirty_event_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "token_radar_source_dirty_event_claim_lease_ms_required", id="bool-lease"),
        pytest.param(
            {"lease_ms": "60000"},
            "token_radar_source_dirty_event_claim_lease_ms_required",
            id="string-lease",
        ),
    ],
)
def test_source_dirty_event_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "limit": 25,
        "lease_ms": 60_000,
        "now_ms": 1_700_000_000_000,
        "lease_owner": "worker-a",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        module.TokenRadarSourceDirtyEventRepository(conn).claim_due(**params)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize("limit", [-1, True, "25"])
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo, limit: repo.list_recent_resolved_events(
                since_ms=1_700_000_000_000,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="list-recent-resolved",
        ),
        pytest.param(
            lambda repo, limit: repo.count_recent_resolved_event_candidates(
                since_ms=1_700_000_000_000,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="count-recent-resolved",
        ),
    ],
)
def test_source_dirty_event_recent_limit_rejects_malformed_before_sql(
    operation: Callable[[object, object], object],
    limit: object,
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection()

    with pytest.raises(ValueError, match="token_radar_source_dirty_event_limit_required"):
        operation(module.TokenRadarSourceDirtyEventRepository(conn), limit)

    assert _ScriptedConnection.last_sql == []


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda repo: repo.enqueue_events(
                [{"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"}],
                reason="unit",
                now_ms=1_700_000_000_000,
            ),
            id="enqueue_events",
        ),
        pytest.param(
            lambda repo: repo.claim_due(
                limit=1,
                lease_ms=60_000,
                now_ms=1_700_000_000_000,
                lease_owner="token_radar_projection",
            ),
            id="claim_due",
        ),
        pytest.param(
            lambda repo: repo.mark_done([_claim()], now_ms=1_700_000_000_000),
            id="mark_done",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim()],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_000_000,
            ),
            id="mark_error",
        ),
    ],
)
def test_source_dirty_event_mutations_require_connection_transaction_before_sql_when_committing(
    mutation: Callable[[object], object],
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _MissingTransactionConnection()
    repo = module.TokenRadarSourceDirtyEventRepository(conn)

    with pytest.raises(RuntimeError, match="token_radar_source_dirty_event_transaction_required"):
        mutation(repo)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo: repo.mark_done([_claim()], now_ms=1_700_000_000_000, commit=False), id="done"),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim()],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_000_000,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_source_dirty_event_write_counts_require_cursor_rowcount(
    mutation: Callable[[object], object],
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_required"):
        mutation(module.TokenRadarSourceDirtyEventRepository(conn))


@pytest.mark.parametrize("rowcount", ("bad", "1"))
def test_source_dirty_event_write_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_invalid"):
        module.TokenRadarSourceDirtyEventRepository(conn).mark_error(
            [_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="token_radar_projection",
            now_ms=1_700_000_000_000,
            commit=False,
        )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"retry_ms": 0}, "token_radar_source_dirty_event_retry_ms_required", id="zero-retry"),
        pytest.param({"retry_ms": True}, "token_radar_source_dirty_event_retry_ms_required", id="bool-retry"),
        pytest.param({"retry_ms": "30000"}, "token_radar_source_dirty_event_retry_ms_required", id="string-retry"),
        pytest.param({"max_attempts": 0}, "token_radar_source_dirty_event_max_attempts_required", id="zero-attempts"),
        pytest.param(
            {"max_attempts": True},
            "token_radar_source_dirty_event_max_attempts_required",
            id="bool-attempts",
        ),
        pytest.param(
            {"max_attempts": "3"},
            "token_radar_source_dirty_event_max_attempts_required",
            id="string-attempts",
        ),
    ],
)
def test_source_dirty_event_mark_error_rejects_malformed_retry_policy_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "error": "projection failed",
        "retry_ms": 30_000,
        "max_attempts": 3,
        "worker_name": "token_radar_projection",
        "now_ms": 1_700_000_000_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        module.TokenRadarSourceDirtyEventRepository(conn).mark_error([_claim()], **params)

    assert conn.sql == []
    assert conn.commits == 0


def test_source_dirty_event_enqueue_requires_cursor_rowcount() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_required"):
        module.TokenRadarSourceDirtyEventRepository(conn).enqueue_events(
            [{"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"}],
            reason="unit",
            now_ms=1_700_000_000_000,
            commit=False,
        )


def test_source_dirty_event_error_terminalizes_exhausted_claim() -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _TerminalizingConnection()
    claim = _claim()

    changed = module.TokenRadarSourceDirtyEventRepository(conn).mark_error(
        [claim],
        error="projection failed",
        retry_ms=30_000,
        max_attempts=1,
        worker_name="token_radar_projection",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    assert changed == 1
    assert "DELETE FROM token_radar_source_dirty_events queue" in conn.sql_log[0]
    assert any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql_log)
    assert conn.terminal_params["worker_name"] == "token_radar_projection"
    assert conn.terminal_params["source_table"] == "token_radar_source_dirty_events"
    assert conn.terminal_params["target_key"] == f"{claim['projection_version']}:event-1:Asset:asset-1"
    assert conn.terminal_params["final_status"] == "terminal"
    assert conn.terminal_params["final_reason"] == "token_radar_projection_retry_budget_exhausted: projection failed"
    assert conn.terminal_params["final_reason_bucket"] == "retry_budget_exhausted"
    assert conn.terminal_params["attempt_count"] == 1
    assert conn.terminal_params["payload_hash"] == "hash-1"


@pytest.mark.parametrize("rowcount", ("bad", "1", True, -1))
def test_source_dirty_event_enqueue_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_source_dirty_event_rowcount_invalid"):
        module.TokenRadarSourceDirtyEventRepository(conn).enqueue_events(
            [{"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"}],
            reason="unit",
            now_ms=1_700_000_000_000,
            commit=False,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_000_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_000_000,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_source_dirty_event_completion_requires_claim_attempt_field_without_default(
    mutation: Callable[[object, dict[str, object]], object],
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection()
    claim = _claim()
    claim.pop("attempt_count")

    with pytest.raises(ValueError, match="token radar source dirty completion requires attempt_count") as exc_info:
        mutation(module.TokenRadarSourceDirtyEventRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert _ScriptedConnection.last_sql == []


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("projection_version", {}, id="projection_version"),
        pytest.param("source_event_id", {"event_id": "event-1"}, id="source_event_id"),
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target_type_key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity_id"),
    ],
)
@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_000_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_000_000,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_source_dirty_event_completion_requires_formal_identity_fields_without_alias_fallback(
    mutation: Callable[[object, dict[str, object]], object],
    field: str,
    aliases: dict[str, object],
) -> None:
    module = import_module("parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository")
    conn = _ScriptedConnection()
    claim = _claim()
    claim.pop(field)
    claim.update(aliases)

    with pytest.raises(ValueError, match=field) as exc_info:
        mutation(module.TokenRadarSourceDirtyEventRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert _ScriptedConnection.last_sql == []


def _claim() -> dict[str, object]:
    return {
        "projection_version": "token_radar_projection_v1",
        "source_event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "hash-1",
        "lease_owner": "token_radar_projection",
        "attempt_count": 1,
    }


class _ScriptedConnection:
    last_sql: ClassVar[list[str]] = []
    last_params: ClassVar[list[dict[str, object]]] = []

    def __init__(self, *, rowcount: object = 0, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount
        self.commits = 0
        _ScriptedConnection.last_sql = []
        _ScriptedConnection.last_params = []

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _ScriptedConnection:
        _ScriptedConnection.last_sql.append(str(sql))
        _ScriptedConnection.last_params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def commit(self) -> None:
        self.commits += 1


class _MissingTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        raise AssertionError("source dirty repository must fail before SQL when transaction is missing")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("source dirty repository must not manually commit when transaction is missing")


class _TerminalizingConnection:
    def __init__(self) -> None:
        self.rowcount = 1
        self.sql_log: list[str] = []
        self.terminal_params: dict[str, object] = {}

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _TerminalizingCursor:
        self.sql_log.append(str(sql))
        normalized = " ".join(str(sql).split()).lower()
        if "delete from token_radar_source_dirty_events queue" in normalized:
            return _TerminalizingCursor(rowcount=1, rows=[{**_claim(), "first_dirty_at_ms": 1_700_000_000_000}])
        if "select terminal_generation" in normalized:
            return _TerminalizingCursor(rowcount=0, rows=[])
        if "select coalesce(max(terminal_generation)" in normalized:
            return _TerminalizingCursor(rowcount=1, rows=[{"terminal_generation": 1}])
        if "insert into worker_queue_terminal_events" in normalized:
            self.terminal_params = dict(params or {})
            return _TerminalizingCursor(rowcount=1, rows=[self.terminal_params])
        raise AssertionError(f"unexpected SQL: {sql}")


class _TerminalizingCursor:
    def __init__(self, *, rowcount: int, rows: list[dict[str, object]]) -> None:
        self.rowcount = rowcount
        self._rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows

    def fetchone(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None
