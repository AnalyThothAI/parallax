"""Allow Pulse no-start backpressure run outcomes."""

from __future__ import annotations

from alembic import op

revision = "20260519_0066"
down_revision = "20260519_0065"
branch_labels = None
depends_on = None


_BASE_OUTCOMES = (
    "running",
    "completed",
    "abstain_insufficient_evidence",
    "blocked_market_contract",
    "blocked_social_contract",
    "blocked_identity_contract",
    "invalid_schema",
    "invalid_unknown_evidence_ref",
    "invalid_unsupported_claim",
    "timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "unexpected_exception",
)
_BACKPRESSURE_OUTCOMES = (
    "backpressure_capacity_denied",
    "backpressure_circuit_open",
    "backpressure_rate_limited",
)


def upgrade() -> None:
    _replace_outcome_check(_BASE_OUTCOMES + _BACKPRESSURE_OUTCOMES)


def downgrade() -> None:
    _replace_outcome_check(_BASE_OUTCOMES)


def _replace_outcome_check(outcomes: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{outcome}'" for outcome in outcomes)
    op.execute("ALTER TABLE pulse_agent_runs DROP CONSTRAINT IF EXISTS chk_pulse_agent_runs_outcome_evidence_first")
    op.execute(
        f"""
        ALTER TABLE pulse_agent_runs
          ADD CONSTRAINT chk_pulse_agent_runs_outcome_evidence_first
          CHECK (outcome IN ({quoted})) NOT VALID
        """
    )
