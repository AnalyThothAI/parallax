"""Hard-cut Pulse agent run steps to the single decision stage."""

from __future__ import annotations

from alembic import op

revision = "20260608_0158"
down_revision = "20260608_0157"
branch_labels = None
depends_on = None

_SINGLE_DECISION_STAGES = (
    "evidence_pack",
    "evidence_completeness_gate",
    "pulse_decision",
    "claim_verifier",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
)

def upgrade() -> None:
    _replace_stage_check(
        name="chk_pulse_agent_run_steps_stage_single_decision",
        stages=_SINGLE_DECISION_STAGES,
    )


def downgrade() -> None:
    _replace_stage_check(
        name="chk_pulse_agent_run_steps_stage_single_decision",
        stages=_SINGLE_DECISION_STAGES,
    )


def _replace_stage_check(*, name: str, stages: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{stage}'" for stage in stages)
    op.execute("ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS pulse_agent_run_steps_stage_check")
    op.execute(
        "ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_evidence_first"
    )
    op.execute(
        "ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_research_committee"
    )
    op.execute(
        "ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_single_decision"
    )
    op.execute(
        f"""
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT {name}
          CHECK (stage IN ({quoted}))
        """
    )
