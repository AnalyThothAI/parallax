"""Support stale-running enrichment job recovery."""

from __future__ import annotations

from alembic import op

revision = "20260506_0003"
down_revision = "20260506_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_enrichment_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_claim
        ON enrichment_jobs(priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed', 'running')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_enrichment_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_claim
        ON enrichment_jobs(priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )
