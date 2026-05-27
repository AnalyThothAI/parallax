from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import (
    MacroIntelRepository,
    _series_source_signature,
)


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
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
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


def test_refresh_observation_series_rows_replaces_current_rows_when_signature_changes() -> None:
    selected_row = _series_row()
    conn = CurrentRefreshConnection(selected_rows=[selected_row], publication_state=None, insert_rowcount=1)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "published"
    assert result["rows_written"] == 1
    assert result["source_rows"] == 1
    assert "DELETE FROM macro_observation_series_rows" in queries
    assert "INSERT INTO macro_observation_series_rows" in queries
    assert "INSERT INTO macro_observation_series_publication_state" in queries
    assert "generation_id" not in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "macro_observation_series_generations" not in queries


def test_refresh_empty_current_rows_marks_failed_and_does_not_replace_current_rows() -> None:
    conn = CurrentRefreshConnection(selected_rows=[], publication_state=None)
    repo = MacroIntelRepository(conn)

    with pytest.raises(RuntimeError, match="macro_observation_series_empty"):
        repo.refresh_observation_series_rows(
            projection_version="macro_regime_v4",
            now_ms=1_779_000_000_000,
            lookback_days=730,
            limit_per_series=252,
        )

    queries = "\n".join(query for query, _params in conn.executions)
    assert "INSERT INTO macro_observation_series_publication_state" in queries
    assert "macro_observation_series_empty" in str(conn.executions[-1][1])
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_rows" not in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "macro_observation_series_generations" not in queries


def test_refresh_empty_current_rows_fails_even_when_empty_signature_matches_previous_failure() -> None:
    empty_signature = _series_source_signature(
        projection_version="macro_regime_v4",
        lookback_days=730,
        limit_per_series=252,
        rows=[],
    )
    conn = CurrentRefreshConnection(
        selected_rows=[],
        publication_state={"projection_version": "macro_regime_v4", "source_signature": empty_signature},
    )
    repo = MacroIntelRepository(conn)

    with pytest.raises(RuntimeError, match="macro_observation_series_empty"):
        repo.refresh_observation_series_rows(
            projection_version="macro_regime_v4",
            now_ms=1_779_000_060_000,
            lookback_days=730,
            limit_per_series=252,
        )

    queries = "\n".join(query for query, _params in conn.executions)
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_rows" not in queries
    assert conn.executions[-1][1][3] == "failed"
    assert conn.executions[-1][1][6] == "macro_observation_series_empty"


def test_observation_series_readers_read_current_rows_directly() -> None:
    conn = ReadConnection([])
    repo = MacroIntelRepository(conn)

    repo.latest_observations(limit=10, concept_keys=("asset:spy",))
    repo.observations_for_concepts(concept_keys=("asset:spy",), lookback_days=60, limit_per_series=20)
    repo.concept_history_counts(concept_keys=("asset:spy",), lookback_days=60)

    for query, _params in conn.executions:
        assert "FROM macro_observation_series_rows AS rows" in query
        assert "macro_observation_series_active_generation" not in query
        assert "generation_id" not in query
        assert "FROM macro_observations" not in query


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


class CurrentRefreshConnection:
    def __init__(
        self,
        *,
        selected_rows: list[dict[str, object]],
        publication_state: dict[str, object] | None,
        insert_rowcount: int = 0,
    ) -> None:
        self.selected_rows = selected_rows
        self.publication_state = publication_state
        self.insert_rowcount = insert_rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> Cursor:
        self.executions.append((query, params))
        if "WITH source_ranked AS" in query:
            return Cursor(self.selected_rows)
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
