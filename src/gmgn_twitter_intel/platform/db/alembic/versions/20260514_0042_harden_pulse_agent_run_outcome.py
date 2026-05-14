"""Harden Signal Pulse agent run outcome contract."""

from __future__ import annotations

from alembic import op

revision = "20260514_0042"
down_revision = "20260514_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pulse_agent_runs ALTER COLUMN outcome DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE pulse_agent_runs ALTER COLUMN outcome SET DEFAULT 'running'")
