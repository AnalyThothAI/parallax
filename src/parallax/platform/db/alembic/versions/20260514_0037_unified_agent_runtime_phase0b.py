"""Hard-cut Signal Pulse to unified agent runtime decisions."""

from __future__ import annotations

from alembic import op

revision = "20260514_0037"
down_revision = "20260513_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE pulse_agent_runs
          ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS decision_route TEXT NOT NULL DEFAULT 'research_only',
          ADD COLUMN IF NOT EXISTS decision_stage_count BIGINT NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS decision_route TEXT NOT NULL DEFAULT 'research_only',
          ADD COLUMN IF NOT EXISTS decision_recommendation TEXT NOT NULL DEFAULT 'abstain',
          ADD COLUMN IF NOT EXISTS decision_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS decision_abstain_reason TEXT,
          ADD COLUMN IF NOT EXISTS decision_stage_count BIGINT NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS decision_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_candidates_decision_route'
          ) THEN
            ALTER TABLE pulse_candidates
              ADD CONSTRAINT chk_pulse_candidates_decision_route
              CHECK (decision_route IN ('cex','meme','research_only'));
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_candidates_decision_recommendation'
          ) THEN
            ALTER TABLE pulse_candidates
              ADD CONSTRAINT chk_pulse_candidates_decision_recommendation
              CHECK (decision_recommendation IN (
                'high_conviction','trade_candidate','watchlist','ignore','abstain'
              ));
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_candidates_decision_confidence'
          ) THEN
            ALTER TABLE pulse_candidates
              ADD CONSTRAINT chk_pulse_candidates_decision_confidence
              CHECK (decision_confidence >= 0 AND decision_confidence <= 1);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_run_steps (
          step_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
          stage TEXT NOT NULL CHECK (stage IN ('analyst','critic','judge','research_only_gate')),
          route TEXT NOT NULL CHECK (route IN ('cex','meme','research_only')),
          attempt_index BIGINT NOT NULL DEFAULT 0,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          prompt_text TEXT NOT NULL DEFAULT '',
          response_json JSONB,
          trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          latency_ms BIGINT NOT NULL DEFAULT 0,
          status TEXT NOT NULL CHECK (status IN ('ok','failed','timeout','skipped')),
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(run_id, stage, attempt_index)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_run_steps_run_stage
          ON pulse_agent_run_steps(run_id, stage, attempt_index)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidates_decision_latest
          ON pulse_candidates(
            pulse_version, "window", scope, decision_route, decision_recommendation, updated_at_ms DESC
          )
        """
    )
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS agent_recommendation_json")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS agent_recommendation_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidates_decision_latest")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_run_steps_run_stage")
    op.execute("DROP TABLE IF EXISTS pulse_agent_run_steps")
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_decision_confidence")
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_decision_recommendation")
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_decision_route")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_stage_count")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_abstain_reason")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_confidence")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_recommendation")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_route")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS decision_stage_count")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS decision_route")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS outcome")
