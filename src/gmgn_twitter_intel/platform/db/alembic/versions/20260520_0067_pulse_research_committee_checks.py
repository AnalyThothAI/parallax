"""Hard-cut Pulse checks to the research committee runtime."""

from __future__ import annotations

from alembic import op

revision = "20260520_0067"
down_revision = "20260519_0066"
branch_labels = None
depends_on = None


_EVIDENCE_FIRST_STAGES = (
    "evidence_pack",
    "evidence_completeness_gate",
    "evidence_debate",
    "claim_verifier",
    "decision_maker",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
)
_RESEARCH_COMMITTEE_STAGES = (
    "evidence_pack",
    "evidence_completeness_gate",
    "signal_analyst",
    "bear_case",
    "claim_verifier",
    "risk_portfolio_judge",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
)
_EVIDENCE_FIRST_DISPLAY_STATUSES = (
    "display_trade_candidate",
    "display_token_watch",
    "display_risk_rejected_high_info",
    "hidden_abstain",
    "hidden_insufficient_evidence",
    "hidden_blocked_low_information",
    "hidden_invalid_output",
    "hidden_hold_publish",
)
_RESEARCH_COMMITTEE_DISPLAY_STATUSES = (*_EVIDENCE_FIRST_DISPLAY_STATUSES, "hidden_source_quality")


def upgrade() -> None:
    _replace_stage_check(
        name="chk_pulse_agent_run_steps_stage_research_committee",
        stages=_RESEARCH_COMMITTEE_STAGES,
    )
    _replace_display_status_check(
        name="chk_pulse_candidates_display_status_research_committee",
        statuses=_RESEARCH_COMMITTEE_DISPLAY_STATUSES,
    )


def downgrade() -> None:
    _replace_stage_check(
        name="chk_pulse_agent_run_steps_stage_evidence_first",
        stages=_EVIDENCE_FIRST_STAGES,
    )
    _replace_display_status_check(
        name="chk_pulse_candidates_display_status_evidence_first",
        statuses=_EVIDENCE_FIRST_DISPLAY_STATUSES,
    )


def _replace_stage_check(*, name: str, stages: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{stage}'" for stage in stages)
    op.execute("ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS pulse_agent_run_steps_stage_check")
    op.execute(
        "ALTER TABLE pulse_agent_run_steps "
        "DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_evidence_first"
    )
    op.execute(
        "ALTER TABLE pulse_agent_run_steps "
        "DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_research_committee"
    )
    op.execute(
        f"""
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT {name}
          CHECK (stage IN ({quoted})) NOT VALID
        """
    )


def _replace_display_status_check(*, name: str, statuses: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{status}'" for status in statuses)
    op.execute(
        "ALTER TABLE pulse_candidates "
        "DROP CONSTRAINT IF EXISTS chk_pulse_candidates_display_status_evidence_first"
    )
    op.execute(
        "ALTER TABLE pulse_candidates "
        "DROP CONSTRAINT IF EXISTS chk_pulse_candidates_display_status_research_committee"
    )
    op.execute(
        f"""
        ALTER TABLE pulse_candidates
          ADD CONSTRAINT {name}
          CHECK (display_status IN ({quoted})) NOT VALID
        """
    )
