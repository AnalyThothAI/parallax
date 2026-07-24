"""Add macrodata import runs and macro regime snapshot payloads."""

from __future__ import annotations

from alembic import op

revision = "20260521_0077"
down_revision = "20260521_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_import_runs (
          run_id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          bundle_name TEXT NOT NULL,
          asof_date DATE,
          status TEXT NOT NULL,
          observations_count INTEGER NOT NULL DEFAULT 0,
          coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          missing_series_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          series_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          started_at_ms BIGINT NOT NULL,
          completed_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_import_runs_latest
          ON macro_import_runs(completed_at_ms DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE macro_view_snapshots
          ADD COLUMN IF NOT EXISTS features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS chain_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS scenario_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS scorecard_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macro_import_runs_latest")
    op.execute("DROP TABLE IF EXISTS macro_import_runs")
    op.execute(
        """
        ALTER TABLE macro_view_snapshots
          DROP COLUMN IF EXISTS scorecard_json,
          DROP COLUMN IF EXISTS scenario_json,
          DROP COLUMN IF EXISTS chain_json,
          DROP COLUMN IF EXISTS features_json
        """
    )
