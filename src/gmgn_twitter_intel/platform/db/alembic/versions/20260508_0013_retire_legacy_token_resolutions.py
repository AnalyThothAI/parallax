"""Retire non-current token resolver policies."""

from __future__ import annotations

from alembic import op

revision = "20260508_0013"
down_revision = "20260508_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE token_intent_resolutions
        SET record_status = 'retired',
            is_current = false,
            superseded_at_ms = COALESCE(superseded_at_ms, decision_time_ms)
        WHERE is_current = true
          AND resolver_policy_version <> 'token_radar_v5_identity_resolver'
        """
    )


def downgrade() -> None:
    pass
