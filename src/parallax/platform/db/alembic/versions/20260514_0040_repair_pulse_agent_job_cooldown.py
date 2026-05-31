"""Repair pulse agent job cooldown column on pre-existing tables."""

from __future__ import annotations

from alembic import op

revision = "20260514_0040"
down_revision = "20260514_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE pulse_agent_jobs
        ADD COLUMN IF NOT EXISTS cooldown_until_ms BIGINT NOT NULL DEFAULT 0
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
        ON pulse_agent_jobs(status, next_run_at_ms, cooldown_until_ms, priority DESC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
        ON pulse_agent_jobs(status, next_run_at_ms, priority DESC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )
    op.execute("ALTER TABLE pulse_agent_jobs DROP COLUMN IF EXISTS cooldown_until_ms")
