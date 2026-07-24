"""Add static CEX token icon source fields."""

from __future__ import annotations

from alembic import op

revision = "20260517_0057"
down_revision = "20260517_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_url TEXT")
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_source TEXT")
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_observed_at_ms BIGINT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_tokens_logo
          ON cex_tokens(updated_at_ms DESC)
          WHERE logo_url IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cex_tokens_logo")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_observed_at_ms")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_source")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_url")
