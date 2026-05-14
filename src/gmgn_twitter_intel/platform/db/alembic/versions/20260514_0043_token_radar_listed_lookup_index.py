"""Add Token Radar listed-at lookup index."""

from __future__ import annotations

from alembic import op

revision = "20260514_0043"
down_revision = "20260514_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_listed_lookup
              ON token_radar_rows(
                projection_version,
                "window",
                scope,
                (COALESCE(target_type, '')),
                (COALESCE(target_id, intent_id)),
                computed_at_ms
              )
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_rows_listed_lookup")
