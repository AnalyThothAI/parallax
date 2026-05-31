"""Persist derivatives open interest on market ticks."""

from __future__ import annotations

from alembic import op

revision = "20260521_0071"
down_revision = "20260520_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE market_ticks ADD COLUMN IF NOT EXISTS open_interest_usd NUMERIC")


def downgrade() -> None:
    op.execute("ALTER TABLE market_ticks DROP COLUMN IF EXISTS open_interest_usd")
