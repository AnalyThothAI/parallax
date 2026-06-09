from __future__ import annotations

from parallax.domains.macro_intel.observation_identity import (
    macro_series_current_row_payload_hash,
)
from parallax.domains.macro_intel.repositories.macro_intel_repository import (
    MacroIntelRepository,
    _series_source_signature,
)
from parallax.domains.macro_intel.services.macro_regime_engine import build_macro_view_snapshot


def test_build_macro_view_snapshot_uses_stable_current_identity() -> None:
    snapshot = build_macro_view_snapshot([_observation()], computed_at_ms=1_779_000_000_000)

    assert snapshot["snapshot_id"] == "macro-view:macro_regime_v4:current"
    assert snapshot["projection_version"] == "macro_regime_v4"
    assert snapshot["computed_at_ms"] == 1_779_000_000_000


def test_insert_snapshot_returns_false_when_only_computed_at_ms_changes() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    first = build_macro_view_snapshot([_observation()], computed_at_ms=1_779_000_000_000)
    second = build_macro_view_snapshot([_observation()], computed_at_ms=1_779_000_060_000)

    assert repo.insert_snapshot(first) is True
    assert repo.insert_snapshot(second) is False

    queries = "\n".join(query for query, _params in conn.executions)
    assert "payload_hash" in queries
    assert "ON CONFLICT(snapshot_id) DO UPDATE" in queries
    assert "payload_hash IS DISTINCT FROM excluded.payload_hash" in queries
    assert "RETURNING true AS changed" in queries
    assert conn.payload_hashes[0] == conn.payload_hashes[1]


def test_insert_snapshot_leaves_commit_to_projection_worker_transaction() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    snapshot = build_macro_view_snapshot([_observation()], computed_at_ms=1_779_000_000_000)

    repo.insert_snapshot(snapshot)

    assert conn.commit_count == 0


def test_macro_series_source_signature_ignores_now_ms_and_ingested_at_ms() -> None:
    base_row = _series_row(ingested_at_ms=100, projected_at_ms=1_779_000_000_000)
    changed_timing_row = _series_row(ingested_at_ms=200, projected_at_ms=1_779_000_060_000)

    signature_at_t1 = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[base_row],
    )
    signature_at_t2 = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[changed_timing_row],
    )

    assert signature_at_t1 == signature_at_t2


def test_macro_series_source_signature_changes_when_value_changes() -> None:
    before = _series_row(value_numeric=4.7)
    after = _series_row(value_numeric=4.8)

    signature_before = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[before],
    )
    signature_after = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[after],
    )

    assert signature_before != signature_after


def test_refresh_observation_series_rows_skips_writes_when_source_signature_unchanged() -> None:
    selected_row = _series_row()
    signature = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[selected_row],
    )
    conn = CurrentRefreshConnection(
        selected_rows=[selected_row],
        publication_state={"projection_version": "macro_regime_v4", "source_signature": signature},
        existing_rows=[
            {
                "concept_key": selected_row["concept_key"],
                "observed_at": selected_row["observed_at"],
                "series_rank": selected_row["series_rank"],
                "payload_hash": macro_series_current_row_payload_hash(selected_row),
            }
        ],
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "unchanged"
    assert result["rows_written"] == 0
    assert result["source_rows"] == 1
    assert result["source_signature"] == signature
    assert "INSERT INTO macro_observation_series_rows" not in queries
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_publication_state" in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "macro_observation_series_generations" not in queries


def test_refresh_observation_series_rows_upserts_current_rows_when_signature_changes() -> None:
    selected_row = _series_row()
    conn = CurrentRefreshConnection(selected_rows=[selected_row], publication_state=None, insert_rowcount=1)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "published"
    assert result["rows_written"] == 1
    assert result["source_rows"] == 1
    assert "DELETE FROM macro_observation_series_rows" in queries
    assert "INSERT INTO macro_observation_series_rows" in queries
    assert "NOT EXISTS" in queries
    assert "ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET" in queries
    assert "WHERE macro_observation_series_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in queries
    assert "INSERT INTO macro_observation_series_publication_state" in queries
    assert "generation_id" not in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "macro_observation_series_generations" not in queries


def test_insert_observation_series_rows_chunks_under_postgres_bind_parameter_limit() -> None:
    conn = InsertChunkConnection()
    repo = MacroIntelRepository(conn)
    rows = [_series_row() for _ in range(5_000)]

    rows_written = repo._insert_observation_series_rows(rows)

    insert_executions = [
        (query, params) for query, params in conn.executions if "INSERT INTO macro_observation_series_rows" in query
    ]
    assert rows_written == 5_000
    assert len(insert_executions) == 2
    assert all(len(params) <= 65_535 for _query, params in insert_executions)
    assert [len(params) // 16 for _query, params in insert_executions] == [4_000, 1_000]


def test_refresh_empty_current_partition_without_existing_rows_is_unchanged() -> None:
    conn = CurrentRefreshConnection(selected_rows=[], publication_state=None)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "unchanged"
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_rows" not in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "macro_observation_series_generations" not in queries


def test_refresh_empty_current_partition_marks_failed_and_preserves_existing_rows() -> None:
    empty_signature = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[],
    )
    conn = CurrentRefreshConnection(
        selected_rows=[],
        publication_state={"projection_version": "macro_regime_v4", "source_signature": empty_signature},
        existing_rows=[
            {
                "concept_key": "rates:dgs10",
                "observed_at": "2026-05-20",
                "series_rank": 1,
                "payload_hash": "old",
            }
        ],
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_060_000,
        lookback_days=730,
        limit_per_series=252,
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "failed"
    assert result["rows_written"] == 0
    assert "empty current refresh" in result["latest_attempt_error"]
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_publication_state" in queries


def test_observation_series_readers_read_current_rows_directly() -> None:
    conn = ReadConnection([])
    repo = MacroIntelRepository(conn)

    repo.latest_observations(limit=10, concept_keys=("asset:spy",))
    repo.observations_for_concepts(concept_keys=("asset:spy",), lookback_days=60, limit_per_series=20)
    repo.concept_history_counts(concept_keys=("asset:spy",), lookback_days=60)

    for query, _params in conn.executions[:2]:
        assert "FROM macro_observation_series_rows AS rows" in query
        assert "macro_observation_series_active_generation" not in query
        assert "generation_id" not in query
        assert "FROM macro_observations" not in query

    history_query, history_params = conn.executions[2]
    assert "FROM macro_observations AS observations" in history_query
    assert "observations.value_numeric IS NOT NULL" in history_query
    assert "FROM macro_observation_series_rows AS rows" not in history_query
    assert "projection_version = %s" not in history_query
    assert history_params == (["asset:spy"], 60)


def _series_row(
    *,
    value_numeric: float = 4.7,
    ingested_at_ms: int = 100,
    projected_at_ms: int = 1_779_000_000_000,
) -> dict[str, object]:
    return {
        "projection_version": "macro_regime_v4",
        "concept_key": "rates:dgs10",
        "observed_at": "2026-05-20",
        "series_rank": 1,
        "value_numeric": value_numeric,
        "source_name": "fred",
        "series_key": "fred:DGS10",
        "source_priority": 100,
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": "2026-05-20",
        "raw_payload_json": {},
        "ingested_at_ms": ingested_at_ms,
        "projected_at_ms": projected_at_ms,
    }


def _observation() -> dict[str, object]:
    return {
        "source_name": "fred",
        "concept_key": "vol:vix",
        "series_key": "fred:VIXCLS",
        "source_priority": 100,
        "observed_at": "2026-05-20",
        "value_numeric": 18.2,
        "unit": "index",
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": "2026-05-20",
    }


class CurrentRefreshConnection:
    def __init__(
        self,
        *,
        selected_rows: list[dict[str, object]],
        publication_state: dict[str, object] | None,
        existing_rows: list[dict[str, object]] | None = None,
        insert_rowcount: int = 0,
    ) -> None:
        self.selected_rows = selected_rows
        self.publication_state = publication_state
        self.existing_rows = existing_rows or []
        self.insert_rowcount = insert_rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> Cursor:
        self.executions.append((query, params))
        if "WITH source_ranked AS" in query:
            return Cursor(self.selected_rows)
        if "FROM macro_observation_series_rows AS rows" in query and "payload_hash" in query:
            return Cursor(self.existing_rows)
        if "SELECT *" in query and "FROM macro_observation_series_publication_state" in query:
            return Cursor([self.publication_state] if self.publication_state else [])
        if "INSERT INTO macro_observation_series_rows" in query:
            return Cursor([], rowcount=self.insert_rowcount)
        return Cursor([])

    def transaction(self):
        return NullContext()


class ReadConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> Cursor:
        self.executions.append((query, params))
        return Cursor(self.rows)


class InsertChunkConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> Cursor:
        self.executions.append((query, params))
        return Cursor([], rowcount=len(params) // 16)


class SnapshotConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.payload_hashes: list[object] = []
        self.current_payload_hash: object | None = None
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> Cursor:
        self.executions.append((query, params))
        payload_hash = params[-1]
        self.payload_hashes.append(payload_hash)
        changed = self.current_payload_hash != payload_hash
        self.current_payload_hash = payload_hash
        return Cursor([{"changed": changed}] if changed else [], rowcount=1 if changed else 0)

    def commit(self) -> None:
        self.commit_count += 1


class NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class Cursor:
    def __init__(self, rows: list[dict[str, object] | None], *, rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return [row for row in self.rows if row is not None]

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None
