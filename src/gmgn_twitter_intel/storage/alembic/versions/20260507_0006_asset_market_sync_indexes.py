"""Add indexes for asset market refresh scheduling."""

from __future__ import annotations

from alembic import op

revision = "20260507_0006"
down_revision = "20260506_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_market_snapshots_venue_latest
          ON asset_market_snapshots(venue_id, observed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attributions_venue_recent
          ON asset_attributions(venue_id, decision_time_ms DESC)
          WHERE attribution_status <> 'superseded' AND venue_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_asset_attributions_venue_recent")
    op.execute("DROP INDEX IF EXISTS idx_asset_market_snapshots_venue_latest")
