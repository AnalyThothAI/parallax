"""Allow one explicit operator retry for failed Macro research."""

from __future__ import annotations

from alembic import op

revision = "20260724_0195"
down_revision = "20260724_0194"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(_LIFECYCLE_FUNCTION_WITH_OPERATOR_RETRY)


def downgrade() -> None:
    raise RuntimeError("20260724_0195 is a forward-only Macro research recovery contract; apply a forward fix")


_LIFECYCLE_FUNCTION_WITH_OPERATOR_RETRY = """
CREATE OR REPLACE FUNCTION enforce_macro_research_run_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending'
       OR NEW.attempt_count <> 0
       OR NEW.leased_until_ms IS NOT NULL
       OR NEW.lease_owner IS NOT NULL THEN
      RAISE EXCEPTION 'macro_research_run_initial_state_invalid';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'macro_research_run_delete_forbidden';
  END IF;
  IF NEW.session_date IS DISTINCT FROM OLD.session_date
     OR NEW.market_cutoff_ms IS DISTINCT FROM OLD.market_cutoff_ms
     OR NEW.sealed_at_ms IS DISTINCT FROM OLD.sealed_at_ms
     OR NEW.created_at_ms IS DISTINCT FROM OLD.created_at_ms THEN
    RAISE EXCEPTION 'macro_research_run_frozen_fields_immutable';
  END IF;
  IF OLD.status = 'failed' AND NEW.status = 'retryable' THEN
    IF NEW.attempt_count <> OLD.attempt_count
       OR NEW.max_attempts <> GREATEST(OLD.max_attempts, OLD.attempt_count + 1)
       OR NEW.due_at_ms <> NEW.updated_at_ms
       OR NEW.updated_at_ms < OLD.updated_at_ms
       OR NEW.leased_until_ms IS NOT NULL
       OR NEW.lease_owner IS NOT NULL
       OR NEW.last_error_code IS NOT NULL
       OR NEW.last_error_message IS NOT NULL THEN
      RAISE EXCEPTION 'macro_research_run_operator_retry_shape_invalid';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.max_attempts IS DISTINCT FROM OLD.max_attempts THEN
    RAISE EXCEPTION 'macro_research_run_frozen_fields_immutable';
  END IF;
  IF OLD.status IN ('failed', 'published') THEN
    RAISE EXCEPTION 'macro_research_run_terminal';
  END IF;
  IF NOT (
    (OLD.status = 'pending' AND NEW.status = 'running')
    OR (OLD.status = 'retryable' AND NEW.status = 'running')
    OR (OLD.status = 'running' AND NEW.status IN ('running', 'retryable', 'failed', 'published'))
  ) THEN
    RAISE EXCEPTION 'macro_research_run_transition_invalid:%->%', OLD.status, NEW.status;
  END IF;
  IF NEW.attempt_count < OLD.attempt_count THEN
    RAISE EXCEPTION 'macro_research_run_attempt_count_decrease';
  END IF;
  RETURN NEW;
END
$$
"""
