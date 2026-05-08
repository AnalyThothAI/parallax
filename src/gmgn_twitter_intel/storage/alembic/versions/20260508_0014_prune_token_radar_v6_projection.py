"""Prune token radar rows outside the v6 auditable contract."""

from __future__ import annotations

from alembic import op

revision = "20260508_0014"
down_revision = "20260508_0013"
branch_labels = None
depends_on = None

CURRENT_TOKEN_RADAR_VERSION = "token-radar-v6-auditable"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM token_radar_rows
        WHERE projection_version <> 'token-radar-v6-auditable'
        """
    )
    op.execute(
        """
        DELETE FROM projection_dirty_ranges
        WHERE projection_name = 'token-radar'
          AND projection_version <> 'token-radar-v6-auditable'
        """
    )
    op.execute(
        """
        DELETE FROM projection_runs
        WHERE projection_name = 'token-radar'
          AND projection_version <> 'token-radar-v6-auditable'
        """
    )
    op.execute(
        """
        DELETE FROM projection_offsets
        WHERE projection_name = 'token-radar'
          AND projection_version <> 'token-radar-v6-auditable'
        """
    )


def downgrade() -> None:
    pass
