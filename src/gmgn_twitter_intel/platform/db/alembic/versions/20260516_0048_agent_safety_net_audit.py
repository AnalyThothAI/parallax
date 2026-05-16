"""Add safety_net audit columns to agent run-step tables.

PR 2 of unified-agent-worker-runtime. PR 1 wrote safety_net_used /
safety_net_retries / parse_mode inside trace_metadata_json jsonb. This
migration promotes them to dedicated columns on pulse_agent_run_steps,
model_runs and watchlist_handle_summary_runs so dashboards / SQL
aggregates can pivot on them without descending into jsonb.

The repository write paths are updated in the same PR; the legacy
trace_metadata_json keys keep being written for one release cycle so a
rollback can recover the values.
"""

from __future__ import annotations

from alembic import op

revision = "20260516_0048"
down_revision = "20260516_0047"
branch_labels = None
depends_on = None


_TABLES = (
    "pulse_agent_run_steps",
    "model_runs",
    "watchlist_handle_summary_runs",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS safety_net_used BOOLEAN NOT NULL DEFAULT FALSE")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS safety_net_retries INTEGER NOT NULL DEFAULT 0")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS parse_mode TEXT NOT NULL DEFAULT 'strict'")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pulse_agent_run_steps_safety_net "
        "ON pulse_agent_run_steps(safety_net_used, started_at_ms DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_runs_safety_net ON model_runs(safety_net_used, finished_at_ms DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_model_runs_safety_net")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_run_steps_safety_net")
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS parse_mode")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS safety_net_retries")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS safety_net_used")
