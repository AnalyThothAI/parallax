"""Prune Pulse rows missing token factor market section."""

from __future__ import annotations

from alembic import op

revision = "20260511_0030"
down_revision = "20260511_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM pulse_agent_jobs
        WHERE context_json->'factor_snapshot' IS NOT NULL
          AND NOT ((context_json->'factor_snapshot') ? 'market')
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidates
        WHERE factor_snapshot_json IS NOT NULL
          AND factor_snapshot_json <> '{}'::jsonb
          AND NOT (factor_snapshot_json ? 'market')
        """
    )


def downgrade() -> None:
    pass
