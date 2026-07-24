"""Add macro daily brief current read model."""

from __future__ import annotations

from alembic import op

revision = "20260609_0159"
down_revision = "20260608_0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_daily_briefs (
          brief_key text PRIMARY KEY,
          projection_version text NOT NULL,
          brief_date date,
          asof_date date,
          status text NOT NULL,
          headline text NOT NULL,
          payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms bigint NOT NULL,
          updated_at_ms bigint NOT NULL,
          payload_hash text NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_daily_briefs_projection
          ON macro_daily_briefs(projection_version, brief_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_daily_briefs_asof
          ON macro_daily_briefs(asof_date DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macro_daily_briefs_asof")
    op.execute("DROP INDEX IF EXISTS idx_macro_daily_briefs_projection")
    op.execute("DROP TABLE IF EXISTS macro_daily_briefs")
