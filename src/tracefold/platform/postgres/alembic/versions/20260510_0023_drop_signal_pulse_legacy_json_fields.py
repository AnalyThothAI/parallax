"""Drop legacy Signal Pulse score-centered JSON fields."""

from __future__ import annotations

from alembic import op

revision = "20260510_0023"
down_revision = "20260510_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS thesis_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS radar_score_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS market_context_json")


def downgrade() -> None:
    op.execute("ALTER TABLE pulse_candidates ADD COLUMN IF NOT EXISTS thesis_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        "ALTER TABLE pulse_candidates ADD COLUMN IF NOT EXISTS radar_score_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE pulse_candidates ADD COLUMN IF NOT EXISTS market_context_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
