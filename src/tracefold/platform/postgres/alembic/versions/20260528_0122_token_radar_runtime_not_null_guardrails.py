"""Reassert Token Radar runtime NOT NULL guardrails."""

from __future__ import annotations

from alembic import op

revision = "20260528_0122"
down_revision = "20260528_0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_radar_dirty_targets
          ALTER COLUMN source_dirty SET DEFAULT false,
          ALTER COLUMN source_dirty SET NOT NULL,
          ALTER COLUMN market_dirty SET DEFAULT false,
          ALTER COLUMN market_dirty SET NOT NULL,
          ALTER COLUMN repair_dirty SET DEFAULT false,
          ALTER COLUMN repair_dirty SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_rank_source_events
          ALTER COLUMN source_payload_hash SET DEFAULT '',
          ALTER COLUMN source_payload_hash SET NOT NULL
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260528_0122 token radar runtime NOT NULL guardrails are not safely reversible; "
        "restore from backup or apply an explicit forward repair migration"
    )
