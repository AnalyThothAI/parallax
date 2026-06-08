from __future__ import annotations

from parallax.domains.macro_intel.observation_identity import (
    macro_series_current_row_payload_hash,
)
from parallax.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository


def test_partition_refresh_upserts_only_claimed_concepts() -> None:
    selected_row = _series_row(concept_key="rates:dgs10")
    conn = PartitionRefreshConnection(selected_rows=[selected_row], existing_rows=[], insert_rowcount=1)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
        claimed_targets=[_dirty_target("rates:dgs10")],
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    source_query, source_params = conn.executions[0]
    delete_query, delete_params = next(
        (query, params) for query, params in conn.executions if "DELETE FROM macro_observation_series_rows" in query
    )
    insert_query, _insert_params = next(
        (query, params) for query, params in conn.executions if "INSERT INTO macro_observation_series_rows" in query
    )
    assert result["status"] == "published"
    assert result["rows_written"] == 1
    assert result["source_rows"] == 1
    assert "FROM macro_observations" in source_query
    assert "concept_key = ANY" in source_query
    assert source_params == (["rates:dgs10"], 730, "macro_regime_v4", 1_779_000_000_000, 252)
    assert "projection_version = %s" in delete_query
    assert "concept_key = ANY" in delete_query
    assert "NOT EXISTS" in delete_query
    assert "unnest(%s::text[], %s::date[])" in delete_query
    assert delete_params == (
        ["rates:dgs10"],
        ["2026-05-20"],
        "macro_regime_v4",
        ["rates:dgs10"],
    )
    assert "payload_hash" in insert_query
    assert "ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET" in insert_query
    assert "WHERE macro_observation_series_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in insert_query
    unbounded_delete = (
        'DELETE FROM macro_observation_series_rows\n                WHERE projection_version = %s\n                """'
    )
    assert unbounded_delete not in queries


def test_partition_refresh_skips_unchanged_concepts_without_delete_insert() -> None:
    selected_row = _series_row(concept_key="rates:dgs10")
    existing_hash = macro_series_current_row_payload_hash(selected_row)
    conn = PartitionRefreshConnection(
        selected_rows=[selected_row],
        existing_rows=[
            {
                "concept_key": "rates:dgs10",
                "observed_at": "2026-05-20",
                "series_rank": 1,
                "payload_hash": existing_hash,
            }
        ],
    )
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows_for_concepts(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
        claimed_targets=[_dirty_target("rates:dgs10")],
        concept_keys=("rates:dgs10",),
    )

    queries = "\n".join(query for query, _params in conn.executions)
    assert result["status"] == "unchanged"
    assert result["rows_written"] == 0
    assert result["source_rows"] == 1
    assert "DELETE FROM macro_observation_series_rows" not in queries
    assert "INSERT INTO macro_observation_series_rows" not in queries


def _dirty_target(concept_key: str) -> dict[str, object]:
    return {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "target_kind": "concept",
        "target_id": concept_key,
        "concept_key": concept_key,
        "min_observed_at": "2026-05-20",
        "max_observed_at": "2026-05-20",
        "source_watermark_date": "2026-05-20",
        "payload_hash": f"dirty-hash:{concept_key}",
        "lease_owner": "macro_view_projection",
        "attempt_count": 1,
    }


def _series_row(*, concept_key: str) -> dict[str, object]:
    return {
        "projection_version": "macro_regime_v4",
        "concept_key": concept_key,
        "observed_at": "2026-05-20",
        "series_rank": 1,
        "value_numeric": 4.7,
        "source_name": "fred",
        "series_key": "fred:DGS10",
        "source_priority": 100,
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": "2026-05-20",
        "raw_payload_json": {},
        "ingested_at_ms": 1,
        "projected_at_ms": 1_779_000_000_000,
    }


class PartitionRefreshConnection:
    def __init__(
        self,
        *,
        selected_rows: list[dict[str, object]],
        existing_rows: list[dict[str, object]],
        insert_rowcount: int = 0,
    ) -> None:
        self.selected_rows = selected_rows
        self.existing_rows = existing_rows
        self.insert_rowcount = insert_rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> Cursor:
        self.executions.append((query, params))
        if "WITH source_ranked AS" in query:
            return Cursor(self.selected_rows)
        if "FROM macro_observation_series_rows AS rows" in query and "payload_hash" in query:
            return Cursor(self.existing_rows)
        if "INSERT INTO macro_observation_series_rows" in query:
            return Cursor([], rowcount=self.insert_rowcount)
        return Cursor([])

    def transaction(self):
        return NullContext()


class NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class Cursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None
