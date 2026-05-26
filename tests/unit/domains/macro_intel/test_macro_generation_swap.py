from __future__ import annotations

import re
from pathlib import Path

import pytest

from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository

ROOT = Path(__file__).resolve().parents[4]
REPOSITORY = (
    ROOT
    / "src"
    / "gmgn_twitter_intel"
    / "domains"
    / "macro_intel"
    / "repositories"
    / "macro_intel_repository.py"
)


def test_refresh_empty_generation_marks_failed_and_does_not_switch_active_pointer() -> None:
    conn = GenerationRefreshConnection(row_count=0)
    repo = MacroIntelRepository(conn)

    with pytest.raises(RuntimeError, match="macro_observation_series_generation_empty"):
        repo.refresh_observation_series_rows(
            projection_version="macro_regime_v4",
            now_ms=1_779_000_000_000,
            lookback_days=730,
            limit_per_series=252,
        )

    queries = "\n".join(query for query, _params in conn.executions)
    assert "INSERT INTO macro_observation_series_generations" in queries
    assert "failure_reason = 'macro_observation_series_generation_empty'" in queries
    assert "INSERT INTO macro_observation_series_active_generation" not in queries
    assert "UPDATE macro_observation_series_generations" in queries
    assert conn.executions[0][1][0] == "macro_regime_v4"
    assert conn.executions[1][1][0] == 730


def test_observation_series_readers_join_active_generation() -> None:
    conn = ReadConnection([])
    repo = MacroIntelRepository(conn)

    repo.latest_observations(limit=10, concept_keys=("asset:spy",))
    repo.observations_for_concepts(concept_keys=("asset:spy",), lookback_days=60, limit_per_series=20)
    repo.concept_history_counts(concept_keys=("asset:spy",), lookback_days=60)

    for query, _params in conn.executions:
        assert "macro_observation_series_active_generation" in query
        assert "active.generation_id = rows.generation_id" in query
        assert "active.concept_key = rows.concept_key" in query
        assert "FROM macro_observations" not in query


def test_refresh_sql_does_not_delete_all_projection_rows() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", source)

    assert re.search(
        r"DELETE\s+FROM\s+macro_observation_series_rows\s+WHERE\s+projection_version\s*=",
        normalized,
        re.IGNORECASE,
    ) is None
    assert "rows.generation_id = cleanup_candidates.generation_id" in source


class GenerationRefreshConnection:
    def __init__(self, *, row_count: int) -> None:
        self.row_count = row_count
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> GenerationRefreshCursor:
        self.executions.append((query, params))
        return GenerationRefreshCursor(
            [
                {
                    "generation_id": str(params[1]),
                    "row_count": self.row_count,
                    "status": "failed" if self.row_count == 0 else "active",
                    "cleanup_rows_deleted": 0,
                }
            ]
        )


class ReadConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> GenerationRefreshCursor:
        self.executions.append((query, params))
        return GenerationRefreshCursor(self.rows)


class GenerationRefreshCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None
