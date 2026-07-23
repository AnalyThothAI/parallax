from __future__ import annotations

from datetime import date

import pytest

from parallax.domains.macro_intel.repositories.macro_intel_repository import (
    MacroIntelRepository,
    _series_source_signature,
)
from parallax.domains.macro_intel.services.macro_evidence_snapshot import (
    build_macro_evidence_snapshot,
)
from tests.support.query_contract import assert_query_contract


def test_build_macro_evidence_snapshot_uses_stable_contract_version() -> None:
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)

    assert snapshot["projection_version"] == "macro_evidence_v1"
    assert snapshot["computed_at_ms"] == 1_779_000_000_000
    assert set(snapshot) == {
        "projection_version",
        "fact_watermark",
        "market_cutoff",
        "computed_at_ms",
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    }


def test_insert_snapshot_returns_false_when_only_computed_at_ms_changes() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    first = _snapshot(computed_at_ms=1_779_000_000_000)
    second = _snapshot(computed_at_ms=1_779_000_060_000)

    assert repo.insert_snapshot(first) is True
    assert repo.insert_snapshot(second) is False

    queries = "\n".join(query for query, _params in conn.executions)
    assert "payload_hash" in queries
    assert "ON CONFLICT(snapshot_key) DO UPDATE" in queries
    assert "payload_hash IS DISTINCT FROM excluded.payload_hash" in queries
    assert "RETURNING true AS changed" in queries
    assert "overall_score" not in queries
    assert "module_views_json" not in queries
    assert conn.payload_hashes[0] == conn.payload_hashes[1]


def test_insert_snapshot_leaves_commit_to_projection_worker_transaction() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)

    repo.insert_snapshot(snapshot)

    assert conn.commit_count == 0


def test_snapshot_page_reads_one_persisted_page_without_observation_rebuild() -> None:
    expected = {"page_id": "overview", "snapshot": {}}
    conn = ReadConnection([{"page": expected}])
    repo = MacroIntelRepository(conn)

    assert repo.snapshot_page("overview") == expected

    query, params = conn.executions[0]
    assert "SELECT overview_json AS page" in query
    assert "FROM macro_view_snapshots" in query
    assert "macro_observations" not in query
    assert params == ()


def test_snapshot_page_rejects_retired_or_unknown_modules() -> None:
    repo = MacroIntelRepository(ReadConnection([]))

    with pytest.raises(ValueError, match="macro_evidence_page_unknown"):
        repo.snapshot_page("rates/yield-curve")


def test_insert_snapshot_requires_every_explicit_page_payload() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)
    del snapshot["overview"]

    with pytest.raises(RuntimeError, match="macro_evidence_snapshot_shape_invalid"):
        repo.insert_snapshot(snapshot)

    assert conn.executions == []


@pytest.mark.parametrize(
    "field_name",
    (
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    ),
)
def test_insert_snapshot_rejects_misshaped_page_before_sql(field_name: str) -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)
    snapshot[field_name] = []

    with pytest.raises(RuntimeError, match=f"macro_evidence_snapshot_payload_invalid:{field_name}"):
        repo.insert_snapshot(snapshot)

    assert conn.executions == []


def test_insert_snapshot_rejects_page_metadata_that_diverges_from_atomic_snapshot() -> None:
    conn = SnapshotConnection()
    repo = MacroIntelRepository(conn)
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)
    snapshot["credit"]["snapshot"]["fact_watermark"] = "2026-01-01"

    with pytest.raises(RuntimeError, match="macro_evidence_page_snapshot_mismatch:credit"):
        repo.insert_snapshot(snapshot)

    assert conn.executions == []


def test_macro_series_source_signature_uses_only_compact_payload() -> None:
    base_row = _series_row()
    changed_timing_row = _series_row() | {"ignored_runtime_clock": 1_779_000_060_000}

    signature_at_t1 = _series_source_signature(
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[base_row],
    )
    signature_at_t2 = _series_source_signature(
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[changed_timing_row],
    )

    assert signature_at_t1 == signature_at_t2


def test_macro_series_source_signature_changes_when_value_changes() -> None:
    before = _series_row(value_numeric=4.7)
    after = _series_row(value_numeric=4.8)

    signature_before = _series_source_signature(
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[before],
    )
    signature_after = _series_source_signature(
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[after],
    )

    assert signature_before != signature_after


def test_refresh_observation_series_rows_skips_writes_when_source_signature_unchanged() -> None:
    selected_row = _series_row()
    signature = _series_source_signature(
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[selected_row],
    )
    conn = CurrentRefreshConnection(
        selected_rows=[selected_row],
        publication_state={"projection_version": "macro_evidence_v1", "source_signature": signature},
        existing_rows=[_current_series_row(selected_row)],
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_evidence_v1",
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
        projection_version="macro_evidence_v1",
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
    assert "event_metadata_json" in queries
    assert "IS DISTINCT FROM" in queries
    assert "payload_hash" not in next(
        query for query, _params in conn.executions if "INSERT INTO macro_observation_series_rows" in query
    )
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
    assert [len(params) // 10 for _query, params in insert_executions] == [4_000, 1_000]


def test_refresh_empty_current_partition_without_existing_rows_is_unchanged() -> None:
    conn = CurrentRefreshConnection(selected_rows=[], publication_state=None)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_evidence_v1",
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
        projection_version="macro_evidence_v1",
        lookback_days=730,
        limit_per_series=252,
        rows=[],
    )
    conn = CurrentRefreshConnection(
        selected_rows=[],
        publication_state={"projection_version": "macro_evidence_v1", "source_signature": empty_signature},
        existing_rows=[_current_series_row(_series_row()) | {"value_numeric": 4.6}],
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_evidence_v1",
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

    repo.observations_for_concepts(concept_keys=("asset:spy",), lookback_days=60, limit_per_series=20)
    repo.concept_history_counts(concept_keys=("asset:spy",), lookback_days=60)

    for query, _params in conn.executions[:1]:
        assert "macro_observation_series_rows AS series" in query
        assert "macro_observation_series_active_generation" not in query
        assert "generation_id" not in query
        assert "FROM macro_observations" not in query

    history_query, history_params = conn.executions[1]
    assert_query_contract(
        history_query,
        params=history_params,
        required_tables=("macro_observation_series_rows",),
        forbidden_tables=("macro_observations", "macro_observation_series_active_generation"),
        required_predicates=("projection_version = %s", "value_numeric IS NOT NULL"),
        forbidden_fragments=("generation_id", "row_number() over", "series_rank = 1"),
        expected_params=(["asset:spy"], "macro_evidence_v1", 60),
    )


def test_material_fact_max_observed_at_reads_raw_facts_not_compact_series() -> None:
    conn = ReadConnection([{"max_observed_at": date(2026, 5, 21)}])
    repo = MacroIntelRepository(conn)

    result = repo.material_fact_max_observed_at(
        concept_keys=("asset:spy", "credit:hy_oas"),
        through_date=date(2026, 5, 22),
    )

    assert result == date(2026, 5, 21)
    query, params = conn.executions[0]
    assert_query_contract(
        query,
        params=params,
        required_tables=("macro_observations",),
        forbidden_tables=("macro_observation_series_rows",),
        required_predicates=("concept_key = ANY(%s::text[])", "observed_at <= %s"),
        expected_params=(["asset:spy", "credit:hy_oas"], date(2026, 5, 22)),
    )


def _series_row(
    *,
    value_numeric: float = 4.7,
) -> dict[str, object]:
    return {
        "projection_version": "macro_evidence_v1",
        "concept_key": "rates:dgs10",
        "observed_at": "2026-05-20",
        "value_numeric": value_numeric,
        "source_name": "fred",
        "series_key": "fred:DGS10",
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "raw_payload_json": {},
    }


def _current_series_row(selected_row: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in selected_row.items() if key != "raw_payload_json"} | {
        "event_metadata_json": {}
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


def _snapshot(*, computed_at_ms: int) -> dict[str, object]:
    return build_macro_evidence_snapshot([_observation()], computed_at_ms=computed_at_ms)


class CurrentRefreshConnection:
    def __init__(
        self,
        *,
        selected_rows: list[dict[str, object]],
        publication_state: dict[str, object] | None,
        existing_rows: list[dict[str, object]] | None = None,
        insert_rowcount: int = 0,
        delete_rowcount: object = 0,
    ) -> None:
        self.selected_rows = selected_rows
        self.publication_state = publication_state
        self.existing_rows = existing_rows or []
        self.insert_rowcount = insert_rowcount
        self.delete_rowcount = delete_rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> Cursor:
        self.executions.append((query, params))
        if "FROM macro_observations" in query:
            return Cursor(self.selected_rows)
        if "SELECT" in query and "rows.event_metadata_json" in query:
            return Cursor(self.existing_rows)
        if "SELECT *" in query and "FROM macro_observation_series_publication_state" in query:
            return Cursor([self.publication_state] if self.publication_state else [])
        if "DELETE FROM macro_observation_series_rows" in query:
            count = int(self.delete_rowcount)
            return Cursor([{"deleted": 1}] * count, rowcount=count)
        if "INSERT INTO macro_observation_series_rows" in query:
            return Cursor([{"changed": 1}] * self.insert_rowcount, rowcount=self.insert_rowcount)
        return Cursor([])

    def transaction(self):
        return NullContext()


class CurrentRefreshConnectionWithNonCallableTransaction(CurrentRefreshConnection):
    transaction = None


class ReadConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> Cursor:
        self.executions.append((query, params))
        return Cursor(self.rows)


_ROWCOUNT_FROM_PARAMS = object()


class InsertChunkConnection:
    def __init__(self, *, rowcount: object = _ROWCOUNT_FROM_PARAMS) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = rowcount

    def execute(self, query: str, params: tuple[object, ...]) -> Cursor:
        self.executions.append((query, params))
        if self.rowcount is _ROWCOUNT_FROM_PARAMS:
            count = len(params) // 10
            return Cursor([{"changed": 1}] * count, rowcount=count)
        count = int(self.rowcount)
        return Cursor([{"changed": 1}] * count, rowcount=count)


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
    def __init__(self, rows: list[dict[str, object] | None], *, rowcount: object = 0) -> None:
        self.rows = rows
        if rowcount is not None:
            self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return [row for row in self.rows if row is not None]

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None
