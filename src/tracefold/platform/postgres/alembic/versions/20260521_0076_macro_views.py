"""Add macro views storage."""

from __future__ import annotations

from alembic import op

revision = "20260521_0076"
down_revision = "20260521_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_observations (
          observation_id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          series_key TEXT NOT NULL,
          observed_at DATE NOT NULL,
          value_numeric NUMERIC,
          unit TEXT,
          frequency TEXT,
          data_quality TEXT NOT NULL DEFAULT 'ok',
          source_ts TEXT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ingested_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_observations_identity
          ON macro_observations(source_name, series_key, observed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observations_latest
          ON macro_observations(series_key, observed_at DESC, ingested_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_view_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          asof_date DATE NOT NULL,
          status TEXT NOT NULL,
          regime TEXT NOT NULL,
          overall_score NUMERIC,
          panels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_view_snapshots_latest
          ON macro_view_snapshots(projection_version, computed_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macro_view_snapshots_latest")
    op.execute("DROP TABLE IF EXISTS macro_view_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_macro_observations_latest")
    op.execute("DROP INDEX IF EXISTS ux_macro_observations_identity")
    op.execute("DROP TABLE IF EXISTS macro_observations")
