"""Allow Pulse harness hash history per model identity."""

from __future__ import annotations

from alembic import op

revision = "20260514_0044"
down_revision = "20260514_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE pulse_agent_harness_versions
          DROP CONSTRAINT IF EXISTS pulse_agent_harness_versions_harness_version_provider_model_key
        """
    )


def downgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
          SELECT harness_hash,
                 row_number() OVER (
                   PARTITION BY harness_version, provider, model
                   ORDER BY created_at_ms DESC, harness_hash DESC
                 ) AS row_rank
          FROM pulse_agent_harness_versions
        )
        DELETE FROM pulse_agent_harness_versions AS stale
        USING ranked
        WHERE stale.harness_hash = ranked.harness_hash
          AND ranked.row_rank > 1
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_agent_harness_versions
          ADD CONSTRAINT pulse_agent_harness_versions_harness_version_provider_model_key
          UNIQUE(harness_version, provider, model)
        """
    )
