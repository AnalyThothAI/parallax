"""Hard cut macro WorkerSpace root-fix schema."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260528_0116"
down_revision = "20260527_0115"
branch_labels = None
depends_on = None


_HASH_BACKFILL_BATCH_SIZE = 1_000
_NON_FACT_RAW_PAYLOAD_KEYS = {
    "fetch_ts",
    "fetched_at",
    "fetched_at_ms",
    "provider_fetch_ts",
    "provider_fetched_at",
    "provider_fetched_at_ms",
    "received_at",
    "received_at_ms",
    "run_id",
    "sync_run_id",
    "import_run_id",
}


_MACRO_RUN_COUNT_COLUMN_SQL = (
    "ALTER TABLE macro_import_runs ADD COLUMN IF NOT EXISTS seen_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_import_runs ADD COLUMN IF NOT EXISTS inserted_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_import_runs ADD COLUMN IF NOT EXISTS changed_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_import_runs ADD COLUMN IF NOT EXISTS noop_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS seen_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS inserted_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS changed_observation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS noop_observation_count INTEGER NOT NULL DEFAULT 0",
)


_MACRO_RUN_COUNT_CONSTRAINT_SQL = (
    """
    ALTER TABLE macro_import_runs
      ADD CONSTRAINT chk_macro_import_runs_seen_observation_count
      CHECK (seen_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_import_runs
      ADD CONSTRAINT chk_macro_import_runs_inserted_observation_count
      CHECK (inserted_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_import_runs
      ADD CONSTRAINT chk_macro_import_runs_changed_observation_count
      CHECK (changed_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_import_runs
      ADD CONSTRAINT chk_macro_import_runs_noop_observation_count
      CHECK (noop_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_sync_runs
      ADD CONSTRAINT chk_macro_sync_runs_seen_observation_count
      CHECK (seen_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_sync_runs
      ADD CONSTRAINT chk_macro_sync_runs_inserted_observation_count
      CHECK (inserted_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_sync_runs
      ADD CONSTRAINT chk_macro_sync_runs_changed_observation_count
      CHECK (changed_observation_count >= 0)
    """,
    """
    ALTER TABLE macro_sync_runs
      ADD CONSTRAINT chk_macro_sync_runs_noop_observation_count
      CHECK (noop_observation_count >= 0)
    """,
)


_DROP_RETIRED_MACRO_TABLE_SQL = (
    "DROP TABLE IF EXISTS macro_observation_series_active_generation",
    "DROP TABLE IF EXISTS macro_observation_series_generations",
    "DROP TABLE IF EXISTS macro_view_snapshots_compact",
    "DROP TABLE IF EXISTS macro_view_snapshot_generations",
    "DROP TABLE IF EXISTS macro_regime_snapshots",
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    _drop_retired_macro_tables()
    _delete_non_v4_macro_read_models()
    _add_macro_observation_fact_hash()
    _add_macro_run_observation_counts()
    _hard_cut_macro_series_rows_to_dates()
    _add_macro_dirty_target_watermarks()
    _add_cex_current_payload_hash()

    for table_name in (
        "cex_oi_radar_publication_state",
        "macro_observations",
        "macro_import_runs",
        "macro_sync_runs",
        "macro_observation_series_rows",
        "macro_projection_dirty_targets",
        "macro_view_snapshots",
        "macro_observation_series_publication_state",
    ):
        op.execute(f"ANALYZE {table_name}")


def downgrade() -> None:
    raise RuntimeError(
        "20260528_0116 macro WorkerSpace root-fix hard cut is not safely reversible; "
        "restore from backup or rebuild Macro facts and read models from provider inputs."
    )


def _drop_retired_macro_tables() -> None:
    for statement in _DROP_RETIRED_MACRO_TABLE_SQL:
        op.execute(statement)


def _delete_non_v4_macro_read_models() -> None:
    op.execute("DELETE FROM macro_view_snapshots WHERE projection_version <> 'macro_regime_v4'")
    op.execute("DELETE FROM macro_observation_series_rows WHERE projection_version <> 'macro_regime_v4'")
    op.execute("DELETE FROM macro_projection_dirty_targets WHERE projection_version <> 'macro_regime_v4'")
    op.execute("DELETE FROM macro_observation_series_publication_state WHERE projection_version <> 'macro_regime_v4'")


def _add_macro_observation_fact_hash() -> None:
    op.execute("ALTER TABLE macro_observations ADD COLUMN IF NOT EXISTS fact_payload_hash TEXT")
    _backfill_macro_observation_fact_hashes()
    op.execute("ALTER TABLE macro_observations ALTER COLUMN fact_payload_hash SET NOT NULL")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observations_fact_payload_hash
          ON macro_observations(fact_payload_hash)
        """
    )


def _add_macro_run_observation_counts() -> None:
    for statement in _MACRO_RUN_COUNT_COLUMN_SQL:
        op.execute(statement)
    for statement in _MACRO_RUN_COUNT_CONSTRAINT_SQL:
        op.execute(statement)

    op.execute(
        """
        UPDATE macro_import_runs
        SET
          seen_observation_count = COALESCE(NULLIF(seen_observation_count, 0), observations_count, 0),
          inserted_observation_count = COALESCE(NULLIF(inserted_observation_count, 0), observations_count, 0),
          changed_observation_count = COALESCE(changed_observation_count, 0),
          noop_observation_count = COALESCE(noop_observation_count, 0)
        """
    )
    op.execute(
        """
        ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS max_seen_observed_at DATE
        """
    )
    op.execute(
        """
        ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS min_changed_observed_at DATE
        """
    )
    op.execute(
        """
        ALTER TABLE macro_sync_runs ADD COLUMN IF NOT EXISTS max_changed_observed_at DATE
        """
    )
    op.execute(
        """
        UPDATE macro_sync_runs
        SET
          seen_observation_count = COALESCE(NULLIF(seen_observation_count, 0), observations_count, 0),
          inserted_observation_count = COALESCE(
            NULLIF(inserted_observation_count, 0),
            imported_observation_count,
            observations_count,
            0
          ),
          changed_observation_count = COALESCE(changed_observation_count, 0),
          noop_observation_count = CASE
            WHEN noop_observation_count > 0 THEN noop_observation_count
            ELSE GREATEST(COALESCE(observations_count, 0) - COALESCE(imported_observation_count, 0), 0)
          END,
          max_seen_observed_at = COALESCE(max_seen_observed_at, max_observed_at),
          min_changed_observed_at = COALESCE(
            min_changed_observed_at,
            CASE WHEN imported_observation_count > 0 THEN requested_start ELSE NULL END
          ),
          max_changed_observed_at = COALESCE(
            max_changed_observed_at,
            CASE WHEN imported_observation_count > 0 THEN max_observed_at ELSE NULL END
          )
        """
    )


def _hard_cut_macro_series_rows_to_dates() -> None:
    op.execute("ALTER TABLE macro_observation_series_rows ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          DROP CONSTRAINT IF EXISTS macro_observation_series_rows_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          DROP CONSTRAINT IF EXISTS macro_observation_series_rows_compact_pkey
        """
    )
    op.execute(
        """
        DELETE FROM macro_observation_series_rows AS rows
        USING (
          SELECT
            ctid,
            row_number() OVER (
              PARTITION BY projection_version, concept_key, observed_at::date
              ORDER BY projected_at_ms DESC, ingested_at_ms DESC, series_rank ASC, source_name ASC, series_key ASC
            ) AS duplicate_rank
          FROM macro_observation_series_rows
        ) AS ranked
        WHERE rows.ctid = ranked.ctid
          AND ranked.duplicate_rank > 1
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows ALTER COLUMN observed_at TYPE DATE
          USING observed_at::date
        """
    )
    _backfill_macro_series_current_row_payload_hashes()
    op.execute("ALTER TABLE macro_observation_series_rows ALTER COLUMN payload_hash SET NOT NULL")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ADD CONSTRAINT macro_observation_series_rows_pkey
          PRIMARY KEY (projection_version, concept_key, observed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observation_series_rows_payload_hash
          ON macro_observation_series_rows(projection_version, payload_hash)
        """
    )


def macro_observation_fact_payload_hash(observation: Mapping[str, Any]) -> str:
    payload = {
        "source_name": observation.get("source_name"),
        "series_key": observation.get("series_key"),
        "concept_key": observation.get("concept_key"),
        "observed_at": observation.get("observed_at"),
        "value_numeric": observation.get("value_numeric"),
        "unit": observation.get("unit"),
        "frequency": observation.get("frequency"),
        "data_quality": observation.get("data_quality"),
        "source_ts": observation.get("source_ts"),
        "raw_payload_json": _fact_raw_payload(observation.get("raw_payload_json") or {}),
    }
    return _stable_payload_hash(payload)


def macro_series_current_row_payload_hash(row: Mapping[str, Any]) -> str:
    payload = {
        "projection_version": row.get("projection_version"),
        "concept_key": row.get("concept_key"),
        "observed_at": row.get("observed_at"),
        "series_rank": int(row.get("series_rank") or 0),
        "value_numeric": row.get("value_numeric"),
        "source_name": row.get("source_name"),
        "series_key": row.get("series_key"),
        "source_priority": int(row.get("source_priority") or 0),
        "unit": row.get("unit"),
        "frequency": row.get("frequency"),
        "data_quality": row.get("data_quality"),
        "source_ts": row.get("source_ts"),
        "raw_payload_json": row.get("raw_payload_json") or {},
    }
    return _stable_payload_hash(payload)


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_json_ready(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}"


def _fact_raw_payload(raw_payload: object) -> dict[str, Any]:
    if not isinstance(raw_payload, Mapping):
        return {}
    return {str(key): value for key, value in raw_payload.items() if str(key) not in _NON_FACT_RAW_PAYLOAD_KEYS}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, set | frozenset):
        return sorted(_json_ready(inner) for inner in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _backfill_macro_observation_fact_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          observation_id,
          source_name,
          series_key,
          concept_key,
          observed_at,
          value_numeric,
          unit,
          frequency,
          data_quality,
          source_ts,
          raw_payload_json
        FROM macro_observations
        WHERE fact_payload_hash IS NULL OR fact_payload_hash = ''
        ORDER BY observation_id
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE macro_observations
        SET fact_payload_hash = :fact_payload_hash
        WHERE observation_id = :observation_id
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _HASH_BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            bind.execute(
                update_hash,
                {
                    "observation_id": row["observation_id"],
                    "fact_payload_hash": macro_observation_fact_payload_hash(dict(row)),
                },
            )


def _backfill_macro_series_current_row_payload_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          ctid::text AS row_ctid,
          projection_version,
          concept_key,
          observed_at,
          series_rank,
          value_numeric,
          source_name,
          series_key,
          source_priority,
          unit,
          frequency,
          data_quality,
          source_ts,
          raw_payload_json
        FROM macro_observation_series_rows
        WHERE payload_hash IS NULL OR payload_hash = ''
        ORDER BY projection_version, concept_key, observed_at
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE macro_observation_series_rows
        SET payload_hash = :payload_hash
        WHERE ctid = CAST(:row_ctid AS tid)
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _HASH_BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            bind.execute(
                update_hash,
                {
                    "row_ctid": row["row_ctid"],
                    "payload_hash": macro_series_current_row_payload_hash(dict(row)),
                },
            )


def _add_macro_dirty_target_watermarks() -> None:
    op.execute("ALTER TABLE macro_projection_dirty_targets ADD COLUMN IF NOT EXISTS concept_key TEXT")
    op.execute("ALTER TABLE macro_projection_dirty_targets ADD COLUMN IF NOT EXISTS min_observed_at DATE")
    op.execute("ALTER TABLE macro_projection_dirty_targets ADD COLUMN IF NOT EXISTS max_observed_at DATE")
    op.execute("ALTER TABLE macro_projection_dirty_targets ADD COLUMN IF NOT EXISTS source_watermark_date DATE")
    op.execute(
        """
        UPDATE macro_projection_dirty_targets
        SET
          concept_key = COALESCE(concept_key, NULLIF(target_id, 'current')),
          source_watermark_date = COALESCE(source_watermark_date, to_timestamp(source_watermark_ms / 1000)::date)
        """
    )


def _add_cex_current_payload_hash() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS cex_oi_radar_publication_state
          ADD COLUMN IF NOT EXISTS current_payload_hash TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE macro_projection_dirty_targets
          ADD CONSTRAINT chk_macro_projection_dirty_targets_observed_range
          CHECK (
            min_observed_at IS NULL
            OR max_observed_at IS NULL
            OR min_observed_at <= max_observed_at
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_projection_dirty_targets_watermark
          ON macro_projection_dirty_targets(
            projection_version,
            concept_key,
            source_watermark_date,
            min_observed_at,
            max_observed_at
          )
        """
    )
