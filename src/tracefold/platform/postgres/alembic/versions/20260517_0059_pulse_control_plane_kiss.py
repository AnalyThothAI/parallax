"""Add Signal Pulse admission budgets and suppression state."""

from __future__ import annotations

from alembic import op

revision = "20260517_0059"
down_revision = "20260517_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_target_run_budget (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          hour_bucket_ms BIGINT NOT NULL,
          enqueue_count BIGINT NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(target_type, target_id, hour_bucket_ms)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidate_edge_state
          ADD COLUMN IF NOT EXISTS last_suppressed_reason TEXT,
          ADD COLUMN IF NOT EXISTS last_suppressed_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS pending_score_band TEXT,
          ADD COLUMN IF NOT EXISTS pending_score_band_count BIGINT NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_target_run_budget_hour
          ON pulse_target_run_budget(hour_bucket_ms DESC, updated_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pulse_target_run_budget_hour")
    op.execute("DROP TABLE IF EXISTS pulse_target_run_budget")
    op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS pending_score_band_count")
    op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS pending_score_band")
    op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS last_suppressed_at_ms")
    op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS last_suppressed_reason")
