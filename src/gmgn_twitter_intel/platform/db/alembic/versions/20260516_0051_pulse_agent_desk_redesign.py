"""Pulse agent desk redesign: drop narrative_type + flip stage CHECK to two-stage.

Atomic hard cut performed alongside production code + tests:

* ``pulse_candidates.narrative_type`` is removed entirely. The previous
  worker always wrote ``'direct_token'`` so the column carried no signal
  and forced downstream surfaces (signal_pulse_service, notification
  payloads) to pass through a dead field. Dropping it lets the new
  investigator -> decision_maker pipeline emit narrative information
  inside the structured decision payload instead.
* ``pulse_agent_run_steps.stage`` CHECK constraint is rewritten from the
  three-stage analyst/critic/judge taxonomy to the new two-stage
  investigator/decision_maker pipeline. ``research_only_gate`` is
  preserved on both sides because the research-only branch keeps writing
  it.

``NOT VALID`` is mandatory on both upgrade and downgrade: any historical
row whose ``stage`` value does not satisfy the new constraint must not
block the ALTER. PostgreSQL will only enforce the new check against new
INSERT/UPDATE rows; legacy rows remain queryable for audit purposes.
"""

from __future__ import annotations

from alembic import op

revision = "20260516_0051"
down_revision = "20260516_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS narrative_type")

    op.execute("ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT pulse_agent_run_steps_stage_check")
    op.execute(
        """
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT pulse_agent_run_steps_stage_check
          CHECK (stage IN ('investigator', 'decision_maker', 'research_only_gate'))
          NOT VALID
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE pulse_candidates "
        "ADD COLUMN IF NOT EXISTS narrative_type TEXT NOT NULL DEFAULT 'direct_token'"
    )

    op.execute("ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT pulse_agent_run_steps_stage_check")
    op.execute(
        """
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT pulse_agent_run_steps_stage_check
          CHECK (stage IN ('analyst', 'critic', 'judge', 'research_only_gate'))
          NOT VALID
        """
    )
