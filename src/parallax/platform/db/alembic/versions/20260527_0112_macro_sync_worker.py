"""Add macro sync worker control-plane storage."""

from __future__ import annotations

from alembic import op

revision = "20260527_0112"
down_revision = "20260527_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_sync_windows (
          sync_window_id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          bundle_name TEXT NOT NULL,
          window_start DATE NOT NULL,
          window_end DATE NOT NULL,
          trigger_reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          payload_hash TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 8,
          last_error_code TEXT,
          last_error_message TEXT,
          last_run_id TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          completed_at_ms BIGINT,
          CONSTRAINT chk_macro_sync_windows_range CHECK (window_start <= window_end),
          CONSTRAINT chk_macro_sync_windows_status CHECK (
            status IN ('pending', 'running', 'retryable', 'done', 'failed')
          ),
          CONSTRAINT chk_macro_sync_windows_attempt_count CHECK (attempt_count >= 0),
          CONSTRAINT chk_macro_sync_windows_max_attempts CHECK (max_attempts >= 1),
          CONSTRAINT chk_macro_sync_windows_attempt_budget CHECK (attempt_count <= max_attempts),
          CONSTRAINT chk_macro_sync_windows_priority CHECK (priority >= 0),
          CONSTRAINT chk_macro_sync_windows_due_at CHECK (due_at_ms >= 0),
          CONSTRAINT chk_macro_sync_windows_created_at CHECK (created_at_ms >= 0),
          CONSTRAINT chk_macro_sync_windows_updated_at CHECK (updated_at_ms >= created_at_ms),
          CONSTRAINT chk_macro_sync_windows_lease CHECK (
            leased_until_ms IS NULL OR leased_until_ms >= 0
          ),
          CONSTRAINT chk_macro_sync_windows_completed CHECK (
            completed_at_ms IS NULL OR completed_at_ms >= created_at_ms
          )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_sync_windows_identity
          ON macro_sync_windows(source_name, bundle_name, window_start, window_end, trigger_reason)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_due
          ON macro_sync_windows(priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)
          WHERE status IN ('pending', 'retryable')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_lease
          ON macro_sync_windows(leased_until_ms)
          WHERE status = 'running'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_sync_runs (
          sync_run_id TEXT PRIMARY KEY,
          sync_window_id TEXT REFERENCES macro_sync_windows(sync_window_id) ON DELETE SET NULL,
          source_name TEXT NOT NULL,
          bundle_name TEXT NOT NULL,
          requested_start DATE NOT NULL,
          requested_end DATE NOT NULL,
          status TEXT NOT NULL,
          import_run_id TEXT REFERENCES macro_import_runs(run_id) ON DELETE SET NULL,
          asof_date DATE,
          max_observed_at DATE,
          observations_count INTEGER NOT NULL DEFAULT 0,
          imported_observation_count INTEGER NOT NULL DEFAULT 0,
          coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          missing_series_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          series_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          fred_api_key_env TEXT,
          fred_api_key_configured BOOLEAN NOT NULL DEFAULT false,
          error_code TEXT,
          error_message TEXT,
          started_at_ms BIGINT NOT NULL,
          completed_at_ms BIGINT NOT NULL,
          duration_ms BIGINT NOT NULL,
          CONSTRAINT chk_macro_sync_runs_status CHECK (
            status IN ('ok', 'partial', 'retryable_error', 'failed', 'config_error')
          ),
          CONSTRAINT chk_macro_sync_runs_range CHECK (requested_start <= requested_end),
          CONSTRAINT chk_macro_sync_runs_observations_count CHECK (observations_count >= 0),
          CONSTRAINT chk_macro_sync_runs_imported_observation_count CHECK (imported_observation_count >= 0),
          CONSTRAINT chk_macro_sync_runs_started_at CHECK (started_at_ms >= 0),
          CONSTRAINT chk_macro_sync_runs_completed_at CHECK (completed_at_ms >= started_at_ms),
          CONSTRAINT chk_macro_sync_runs_duration CHECK (duration_ms >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_runs_latest
          ON macro_sync_runs(completed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_runs_window
          ON macro_sync_runs(sync_window_id, completed_at_ms DESC)
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_macro_observations_max_observed
              ON macro_observations(observed_at DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_macro_observations_max_observed")
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_runs_window")
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_runs_latest")
    op.execute("DROP TABLE IF EXISTS macro_sync_runs")
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_windows_lease")
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_windows_due")
    op.execute("DROP INDEX IF EXISTS ux_macro_sync_windows_identity")
    op.execute("DROP TABLE IF EXISTS macro_sync_windows")
