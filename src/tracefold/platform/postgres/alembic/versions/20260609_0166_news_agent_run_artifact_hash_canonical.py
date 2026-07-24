"""Canonicalize News agent run artifact hashes."""

from __future__ import annotations

from alembic import op

revision = "20260609_0166"
down_revision = "20260609_0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE news_item_agent_runs AS runs
           SET artifact_version_hash = briefs.artifact_version_hash
          FROM news_item_agent_briefs AS briefs
         WHERE briefs.agent_run_id = runs.run_id
           AND briefs.news_item_id = runs.news_item_id
           AND runs.artifact_version_hash IS DISTINCT FROM briefs.artifact_version_hash
           AND runs.input_hash = briefs.input_hash
           AND runs.prompt_version = briefs.prompt_version
           AND runs.schema_version = briefs.schema_version
           AND runs.validator_version = briefs.validator_version
        """
    )
    op.execute("ANALYZE news_item_agent_runs")


def downgrade() -> None:
    pass
