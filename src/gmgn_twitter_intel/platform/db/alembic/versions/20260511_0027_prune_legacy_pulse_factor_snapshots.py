"""Prune Pulse rows carrying legacy token factor snapshots."""

from __future__ import annotations

from alembic import op

revision = "20260511_0027"
down_revision = "20260511_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM pulse_agent_jobs
        WHERE COALESCE(context_json #>> '{factor_snapshot,schema_version}', '')
          <> 'token_factor_snapshot_v2_alpha_gated'
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidates
        WHERE COALESCE(factor_snapshot_json->>'schema_version', '')
          <> 'token_factor_snapshot_v2_alpha_gated'
        """
    )


def downgrade() -> None:
    pass
