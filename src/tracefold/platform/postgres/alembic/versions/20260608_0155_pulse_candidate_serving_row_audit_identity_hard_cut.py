"""Drop Pulse candidate serving-row agent run identity."""

from __future__ import annotations

from alembic import op

revision = "20260608_0155"
down_revision = "20260608_0154"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS agent_run_id")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS agent_run_id TEXT REFERENCES pulse_agent_runs(run_id) ON DELETE SET NULL
        """
    )
