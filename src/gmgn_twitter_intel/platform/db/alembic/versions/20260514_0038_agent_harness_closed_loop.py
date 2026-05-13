"""Add closed-loop agent harness ledger."""

from __future__ import annotations

from alembic import op

revision = "20260514_0038"
down_revision = "20260514_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_harness_versions (
          harness_hash TEXT PRIMARY KEY,
          harness_version TEXT NOT NULL,
          strategy TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          manifest_json JSONB NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(harness_version, provider, model)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_agent_runs
          ADD COLUMN IF NOT EXISTS harness_version TEXT NOT NULL DEFAULT 'pulse-decision-harness-v1',
          ADD COLUMN IF NOT EXISTS harness_hash TEXT NOT NULL DEFAULT 'sha256:unversioned'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_runs_harness
          ON pulse_agent_runs(harness_hash, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_eval_cases (
          eval_case_id TEXT PRIMARY KEY,
          source_run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
          harness_hash TEXT NOT NULL,
          eval_type TEXT NOT NULL CHECK (eval_type IN ('deterministic')),
          route TEXT NOT NULL CHECK (route IN ('cex','meme','research_only')),
          recommendation TEXT NOT NULL CHECK (
            recommendation IN ('high_conviction','trade_candidate','watchlist','ignore','abstain')
          ),
          input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          expected_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          rubric_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL CHECK (status IN ('active','retired')),
          created_at_ms BIGINT NOT NULL,
          UNIQUE(source_run_id, eval_type)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_eval_cases_source
          ON pulse_agent_eval_cases(source_run_id, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_eval_cases_harness
          ON pulse_agent_eval_cases(harness_hash, route, recommendation, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_eval_results (
          eval_result_id TEXT PRIMARY KEY,
          eval_case_id TEXT NOT NULL REFERENCES pulse_agent_eval_cases(eval_case_id) ON DELETE CASCADE,
          harness_hash TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('pass','fail')),
          score DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
          grader_version TEXT NOT NULL,
          details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(eval_case_id, harness_hash, grader_version)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_eval_results_case
          ON pulse_agent_eval_results(eval_case_id, created_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_eval_results_case")
    op.execute("DROP TABLE IF EXISTS pulse_agent_eval_results")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_eval_cases_harness")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_eval_cases_source")
    op.execute("DROP TABLE IF EXISTS pulse_agent_eval_cases")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_runs_harness")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS harness_hash")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS harness_version")
    op.execute("DROP TABLE IF EXISTS pulse_agent_harness_versions")
