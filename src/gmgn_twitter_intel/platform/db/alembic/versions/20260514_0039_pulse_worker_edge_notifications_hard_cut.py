"""Hard-cut Signal Pulse worker to edge-state notifications."""

from __future__ import annotations

from alembic import op

revision = "20260514_0039"
down_revision = "20260514_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM pulse_agent_jobs
        WHERE candidate_type <> 'token_target'
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidates
        WHERE candidate_type <> 'token_target'
           OR pulse_status = 'theme_watch'
        """
    )
    op.execute(
        """
        UPDATE pulse_agent_runs
        SET outcome = CASE
          WHEN status = 'running' THEN 'running'
          WHEN status = 'failed' THEN 'failed'
          WHEN status = 'done' AND response_json->>'recommendation' = 'abstain'
            THEN 'abstain'
          WHEN status = 'done' THEN 'completed'
          ELSE 'failed'
        END
        WHERE outcome = 'pending'
        """
    )
    op.execute("ALTER TABLE pulse_agent_runs ALTER COLUMN outcome SET DEFAULT 'running'")
    op.execute("ALTER TABLE pulse_agent_jobs DROP COLUMN IF EXISTS cooldown_until_ms")
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS last_edge_events_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_candidate_edge_state (
          candidate_id TEXT PRIMARY KEY,
          latest_observed_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          last_processed_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          last_edge_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          last_edge_signature TEXT,
          last_job_id TEXT,
          last_agent_run_id TEXT,
          observed_at_ms BIGINT NOT NULL,
          last_processed_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_candidate_run_budget (
          candidate_id TEXT NOT NULL,
          hour_bucket_ms BIGINT NOT NULL,
          enqueue_count BIGINT NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(candidate_id, hour_bucket_ms)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidate_edge_state_updated
          ON pulse_candidate_edge_state(updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidate_run_budget_hour
          ON pulse_candidate_run_budget(hour_bucket_ms DESC, updated_at_ms DESC)
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
        ON pulse_agent_jobs(status, next_run_at_ms, priority DESC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed', 'running')
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_agent_jobs_candidate_type_hard_cut'
          ) THEN
            ALTER TABLE pulse_agent_jobs
              ADD CONSTRAINT chk_pulse_agent_jobs_candidate_type_hard_cut
              CHECK (candidate_type = 'token_target');
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_candidates_candidate_type_hard_cut'
          ) THEN
            ALTER TABLE pulse_candidates
              ADD CONSTRAINT chk_pulse_candidates_candidate_type_hard_cut
              CHECK (candidate_type = 'token_target');
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_candidates_status_hard_cut'
          ) THEN
            ALTER TABLE pulse_candidates
              ADD CONSTRAINT chk_pulse_candidates_status_hard_cut
              CHECK (pulse_status IN (
                'trade_candidate','token_watch','risk_rejected_high_info','blocked_low_information'
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
            SELECT 1 FROM pg_constraint WHERE conname = 'chk_pulse_agent_runs_outcome_hard_cut'
          ) THEN
            ALTER TABLE pulse_agent_runs
              ADD CONSTRAINT chk_pulse_agent_runs_outcome_hard_cut
              CHECK (outcome IN (
                'running','completed','abstain','abstain_critic_veto','abstain_insufficient_data','failed'
              ));
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pulse_agent_runs DROP CONSTRAINT IF EXISTS chk_pulse_agent_runs_outcome_hard_cut")
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_status_hard_cut")
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_candidate_type_hard_cut")
    op.execute("ALTER TABLE pulse_agent_jobs DROP CONSTRAINT IF EXISTS chk_pulse_agent_jobs_candidate_type_hard_cut")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
        ON pulse_agent_jobs(status, next_run_at_ms, priority DESC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidate_run_budget_hour")
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidate_edge_state_updated")
    op.execute("DROP TABLE IF EXISTS pulse_candidate_run_budget")
    op.execute("DROP TABLE IF EXISTS pulse_candidate_edge_state")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS last_edge_events_json")
    op.execute(
        """
        ALTER TABLE pulse_agent_jobs
          ADD COLUMN IF NOT EXISTS cooldown_until_ms BIGINT NOT NULL DEFAULT 0
        """
    )
    op.execute("ALTER TABLE pulse_agent_runs ALTER COLUMN outcome SET DEFAULT 'pending'")
