from __future__ import annotations

import inspect
from typing import Any

import pytest

from parallax.domains.narrative_intel.repositories.narrative_repository import (
    NarrativeRepository,
    admission_payload_hash,
)


def test_load_radar_admission_target_reads_ready_publication_state_without_generation_gate() -> None:
    source = inspect.getsource(NarrativeRepository.load_radar_admission_target)

    assert "token_radar_publication_state" in source
    assert "token_radar_projection_coverage" not in source
    assert "latest_attempt_status = 'ready'" in source
    assert "token_radar_current_rows.generation_id = latest.current_generation_id" not in source
    assert "latest.current_published_at_ms AS computed_at_ms" in source


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.upsert_admissions([_admission_row()], now_ms=2_000),
            id="upsert_admissions",
        ),
        pytest.param(
            lambda repo: repo.stale_admission_target(
                target_type="Asset",
                target_id="asset-1",
                window="1h",
                scope="all",
            ),
            id="stale_admission_target",
        ),
    ],
)
def test_narrative_admission_mutations_require_connection_transaction_before_sql_when_committing(operation) -> None:
    conn = _NoTransactionConnection()

    with pytest.raises(RuntimeError, match="narrative_admission_transaction_required"):
        operation(NarrativeRepository(conn))

    assert conn.sql == []


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        pytest.param(
            lambda repo: repo.upsert_admissions([_admission_row()], now_ms=2_000),
            {"upserted": 1, "seen": 1},
            id="upsert_admissions",
        ),
        pytest.param(
            lambda repo: repo.stale_admission_target(
                target_type="Asset",
                target_id="asset-1",
                window="1h",
                scope="all",
            ),
            {"staled_admissions": 1},
            id="stale_admission_target",
        ),
    ],
)
def test_narrative_admission_commit_owned_writes_use_connection_transaction_without_manual_commit(
    operation, expected
) -> None:
    conn = _ScriptedConnection()

    assert operation(NarrativeRepository(conn)) == expected
    assert conn.transaction_commits == 1
    assert conn.manual_commits == 0
    assert conn.sql_depths == [1]


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.upsert_admissions([_admission_row()], now_ms=2_000, commit=False),
            id="upsert_admissions",
        ),
        pytest.param(
            lambda repo: repo.stale_admission_target(
                target_type="Asset",
                target_id="asset-1",
                window="1h",
                scope="all",
                commit=False,
            ),
            id="stale_admission_target",
        ),
    ],
)
def test_narrative_admission_write_counts_require_cursor_rowcount(operation) -> None:
    conn = _ScriptedConnection(rowcount=_ROWCOUNT_MISSING)

    with pytest.raises(TypeError, match="narrative_repository_rowcount_required"):
        operation(NarrativeRepository(conn))


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1))
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.upsert_admissions([_admission_row()], now_ms=2_000, commit=False),
            id="upsert_admissions",
        ),
        pytest.param(
            lambda repo: repo.stale_admission_target(
                target_type="Asset",
                target_id="asset-1",
                window="1h",
                scope="all",
                commit=False,
            ),
            id="stale_admission_target",
        ),
    ],
)
def test_narrative_admission_write_counts_reject_invalid_cursor_rowcount(operation, rowcount: Any) -> None:
    conn = _ScriptedConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="narrative_repository_rowcount_invalid"):
        operation(NarrativeRepository(conn))


@pytest.mark.parametrize("limit", [0, -1, True, "1"])
def test_narrative_upsert_admissions_rejects_malformed_limit_before_transaction(limit: object) -> None:
    conn = _ScriptedConnection()

    with pytest.raises(ValueError, match="narrative_admission_upsert_limit_required"):
        NarrativeRepository(conn).upsert_admissions(
            [_admission_row()],
            now_ms=2_000,
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.sql == []
    assert conn.transaction_commits == 0


@pytest.mark.parametrize(
    ("removed_field", "legacy_field", "legacy_value"),
    [
        pytest.param("schema_version", None, None, id="schema-version"),
        pytest.param("status", None, None, id="status"),
        pytest.param("reason", None, None, id="reason"),
        pytest.param("priority", None, None, id="priority"),
        pytest.param("source_event_ids", "source_event_ids_json", ["event-legacy"], id="source-ids-alias"),
        pytest.param("source_max_received_at_ms", "source_window_end_ms", 1_500, id="source-watermark-alias"),
        pytest.param("projection_computed_at_ms", "computed_at_ms", 1_800, id="computed-at-alias"),
    ],
)
def test_narrative_upsert_rejects_missing_formal_fields_without_legacy_alias_repair(
    removed_field: str,
    legacy_field: str | None,
    legacy_value: object,
) -> None:
    row = _admission_row()
    row.pop(removed_field)
    if legacy_field is not None:
        row[legacy_field] = legacy_value
    conn = _ScriptedConnection()

    with pytest.raises(ValueError, match=r"narrative_admission_repository_(required|invalid)"):
        NarrativeRepository(conn).upsert_admissions([row], now_ms=2_000, commit=False)

    assert conn.sql == []


def test_admission_payload_hash_rejects_legacy_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        admission_payload_hash(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_admission_v1",
                "status": "admitted",
                "source_event_ids_json": ["event-1"],
                123: "legacy",
            }
        )


def test_current_narrative_admissions_read_only_admissions() -> None:
    conn = _ReadConnection(
        rows=[
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "status": "admitted",
                "reason": "radar_row",
                "source_event_count": 4,
                "independent_author_count": 3,
                "projection_computed_at_ms": 1_900,
            }
        ]
    )

    result = NarrativeRepository(conn).current_narrative_admissions_for_targets(
        [{"target_type": "Asset", "target_id": "asset-1"}],
        window="1h",
        scope="all",
        schema_version="narrative_intel_v1",
    )

    snapshot = result[("Asset", "asset-1")]
    assert snapshot["status"] == "admitted"
    assert snapshot["currentness"] == {"display_status": "current", "reason": "radar_row"}
    assert len(conn.calls) == 1
    sql, _params = conn.calls[0]
    assert "FROM narrative_admissions" in sql
    assert "token_discussion_digests" not in sql
    assert "token_mention_semantics" not in sql


def _admission_row() -> dict[str, Any]:
    return {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "schema_version": "narrative_intel_v1",
        "status": "admitted",
        "reason": "radar_row",
        "priority": 10,
        "last_radar_rank": 1,
        "last_rank_score": 88.5,
        "source_event_ids": ["event-1"],
        "source_max_received_at_ms": 1_500,
        "projection_computed_at_ms": 1_800,
        "source_window_start_ms": 1_000,
        "source_window_end_ms": 1_500,
        "source_event_count": 1,
        "independent_author_count": 1,
        "admission_generation": "1h:all:1500",
    }


_ROWCOUNT_MISSING = object()


class _ScriptedConnection:
    def __init__(self, *, rowcount: object = 1) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.sql_depths: list[int] = []
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount
        self.manual_commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: Any = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        return self

    def commit(self) -> None:
        self.manual_commits += 1

    def transaction(self) -> _Transaction:
        return _Transaction(self)


class _NoTransactionConnection(_ScriptedConnection):
    transaction = None


class _ReadConnection:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _ReadCursor:
        self.calls.append((str(sql), params))
        return _ReadCursor(self.rows)


class _ReadCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


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


def test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values() -> None:
    class LegacyJsonbLikeAdapter:
        def __init__(self) -> None:
            self.obj = {"source_event_ids": ["event-1"]}

    with pytest.raises(ValueError, match="current payload hash payload has unsupported values"):
        admission_payload_hash(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_admission_v1",
                "status": "admitted",
                "source_event_ids_json": LegacyJsonbLikeAdapter(),
            }
        )
