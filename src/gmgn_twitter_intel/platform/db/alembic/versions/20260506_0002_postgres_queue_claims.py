from __future__ import annotations

from alembic import op

revision = "20260506_0002"
down_revision = "20260506_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_claim
        ON enrichment_jobs(priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_market_observations_claim_ready
        ON token_market_observations(priority ASC, next_run_at_ms ASC, created_at_ms ASC, observation_id ASC)
        WHERE status IN ('pending', 'provider_error', 'rate_limited')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_market_observations_claim_stale
        ON token_market_observations(updated_at_ms ASC, observation_id ASC)
        WHERE status = 'running'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_deliveries_claim
        ON notification_deliveries(next_run_at_ms ASC, created_at_ms ASC, delivery_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notification_deliveries_claim")
    op.execute("DROP INDEX IF EXISTS idx_token_market_observations_claim_stale")
    op.execute("DROP INDEX IF EXISTS idx_token_market_observations_claim_ready")
    op.execute("DROP INDEX IF EXISTS idx_enrichment_jobs_claim")
