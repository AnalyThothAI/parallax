"""Add durable macro sync source watermarks."""

from __future__ import annotations

from alembic import op

revision = "20260603_0146"
down_revision = "20260603_0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_sync_state (
          source_name TEXT NOT NULL,
          bundle_name TEXT NOT NULL,
          max_observed_at DATE,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(source_name, bundle_name)
        )
        """
    )
    op.execute(
        """
        INSERT INTO macro_sync_state(source_name, bundle_name, max_observed_at, updated_at_ms)
        SELECT source_name, bundle_name,
               MAX(COALESCE(max_seen_observed_at, max_observed_at, requested_end)),
               (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT
          FROM macro_sync_runs
         WHERE status IN ('ok', 'partial')
         GROUP BY source_name, bundle_name
        HAVING MAX(COALESCE(max_seen_observed_at, max_observed_at, requested_end)) IS NOT NULL
        ON CONFLICT(source_name, bundle_name) DO UPDATE SET
          max_observed_at = EXCLUDED.max_observed_at,
          updated_at_ms = EXCLUDED.updated_at_ms
        WHERE macro_sync_state.max_observed_at IS DISTINCT FROM EXCLUDED.max_observed_at
        """
    )
    op.execute(
        """
        INSERT INTO macro_sync_state(source_name, bundle_name, max_observed_at, updated_at_ms)
        SELECT 'macrodata-cli', 'macro-core', MAX(observed_at),
               (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT
          FROM macro_observations
         WHERE NOT EXISTS (
           SELECT 1
             FROM macro_sync_state
            WHERE source_name = 'macrodata-cli'
              AND bundle_name = 'macro-core'
         )
         HAVING MAX(observed_at) IS NOT NULL
        ON CONFLICT(source_name, bundle_name) DO UPDATE SET
          max_observed_at = EXCLUDED.max_observed_at,
          updated_at_ms = EXCLUDED.updated_at_ms
        WHERE macro_sync_state.max_observed_at IS DISTINCT FROM EXCLUDED.max_observed_at
        """
    )
    op.execute("ANALYZE macro_sync_state")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS macro_sync_state")
