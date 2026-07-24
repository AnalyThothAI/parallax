"""Make Token Radar current rows serve by stable product identity."""

from __future__ import annotations

from alembic import op

revision = "20260608_0157"
down_revision = "20260608_0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_venue_rank")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_rank
          ON token_radar_current_rows(projection_version, "window", scope, venue, lane, rank)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_venue_rank")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_rank
          ON token_radar_current_rows(projection_version, "window", scope, venue, lane, rank)
        """
    )
