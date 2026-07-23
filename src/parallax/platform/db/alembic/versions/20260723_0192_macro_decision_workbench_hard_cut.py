"""Hard cut the Macro current projection to the decision-workbench contract."""

from __future__ import annotations

from alembic import op

revision = "20260723_0192"
down_revision = "20260723_0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute(
        """
        LOCK TABLE
          macro_projection_dirty_targets,
          macro_observation_series_rows,
          macro_observation_series_publication_state,
          macro_view_snapshots
        IN SHARE ROW EXCLUSIVE MODE
        """
    )
    op.execute("DELETE FROM macro_projection_dirty_targets")
    op.execute("DELETE FROM macro_observation_series_rows")
    op.execute("DELETE FROM macro_observation_series_publication_state")
    op.execute("DELETE FROM macro_view_snapshots")
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), fact_watermark AS (
          SELECT
            COALESCE(MAX(ingested_at_ms), 0)::bigint AS source_watermark_ms,
            MIN(observed_at) AS min_observed_at,
            MAX(observed_at) AS max_observed_at
          FROM macro_observations
        )
        INSERT INTO macro_projection_dirty_targets(
          projection_name,
          projection_version,
          target_kind,
          target_id,
          payload_hash,
          dirty_reason,
          source_watermark_ms,
          priority,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          created_at_ms,
          updated_at_ms,
          concept_key,
          min_observed_at,
          max_observed_at,
          source_watermark_date
        )
        SELECT
          'macro_evidence',
          'macro_decision_v2',
          'current',
          'current',
          'schema-hard-cut-0192:macro-decision-v2',
          'schema_hard_cut_0192',
          fact_watermark.source_watermark_ms,
          0,
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms,
          NULL,
          fact_watermark.min_observed_at,
          fact_watermark.max_observed_at,
          fact_watermark.max_observed_at
        FROM migration_clock
        CROSS JOIN fact_watermark
        """
    )
    op.execute("ANALYZE macro_projection_dirty_targets")


def downgrade() -> None:
    raise RuntimeError(
        "20260723_0192 is an irreversible derived-state hard cut; restore the pre-migration backup to downgrade"
    )
