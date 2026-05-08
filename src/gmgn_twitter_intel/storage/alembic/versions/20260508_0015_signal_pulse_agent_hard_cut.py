"""Add Signal Lab Pulse agent storage foundation."""

from __future__ import annotations

from alembic import op

revision = "20260508_0015"
down_revision = "20260508_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_jobs (
          job_id TEXT PRIMARY KEY,
          candidate_id TEXT NOT NULL,
          candidate_type TEXT NOT NULL,
          subject_key TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          trigger_signature TEXT NOT NULL,
          timeline_signature TEXT NOT NULL,
          context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          priority BIGINT NOT NULL,
          status TEXT NOT NULL,
          attempt_count BIGINT NOT NULL DEFAULT 0,
          max_attempts BIGINT NOT NULL DEFAULT 3,
          next_run_at_ms BIGINT NOT NULL,
          cooldown_until_ms BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          UNIQUE(candidate_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_agent_runs (
          run_id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL REFERENCES pulse_agent_jobs(job_id) ON DELETE CASCADE,
          candidate_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          backend TEXT NOT NULL DEFAULT 'openai_agents_sdk',
          sdk_trace_id TEXT,
          workflow_name TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          artifact_version_hash TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          input_hash TEXT NOT NULL,
          output_hash TEXT,
          trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          latency_ms BIGINT NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          request_json JSONB NOT NULL,
          response_json JSONB,
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_candidates (
          candidate_id TEXT PRIMARY KEY,
          candidate_type TEXT NOT NULL,
          subject_key TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          symbol TEXT,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          pulse_status TEXT NOT NULL,
          verdict TEXT NOT NULL,
          social_phase TEXT NOT NULL,
          narrative_type TEXT NOT NULL,
          candidate_score DOUBLE PRECISION NOT NULL,
          score_band TEXT NOT NULL,
          trigger_signature TEXT NOT NULL,
          timeline_signature TEXT NOT NULL,
          thesis_json JSONB NOT NULL,
          radar_score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          market_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          gate_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          risk_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          evidence_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          agent_run_id TEXT REFERENCES pulse_agent_runs(run_id) ON DELETE SET NULL,
          pulse_version TEXT NOT NULL,
          gate_version TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_playbook_snapshots (
          playbook_id TEXT PRIMARY KEY,
          candidate_id TEXT NOT NULL REFERENCES pulse_candidates(candidate_id) ON DELETE CASCADE,
          target_type TEXT,
          target_id TEXT,
          horizon TEXT NOT NULL,
          decision_time_ms BIGINT NOT NULL,
          playbook_status TEXT NOT NULL,
          side TEXT NOT NULL,
          setup_json JSONB NOT NULL,
          confirmation_json JSONB NOT NULL,
          invalidation_json JSONB NOT NULL,
          risk_json JSONB NOT NULL,
          entry_market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          playbook_version TEXT NOT NULL,
          outcome_status TEXT NOT NULL DEFAULT 'pending',
          created_at_ms BIGINT NOT NULL,
          UNIQUE(candidate_id, horizon, playbook_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_playbook_outcomes (
          playbook_id TEXT PRIMARY KEY REFERENCES pulse_playbook_snapshots(playbook_id) ON DELETE CASCADE,
          settled_at_ms BIGINT NOT NULL,
          actual_return DOUBLE PRECISION,
          benchmark_return DOUBLE PRECISION,
          abnormal_return DOUBLE PRECISION,
          max_favorable_excursion DOUBLE PRECISION,
          max_adverse_excursion DOUBLE PRECISION,
          confirmation_hit BOOLEAN NOT NULL DEFAULT false,
          invalidation_hit BOOLEAN NOT NULL DEFAULT false,
          outcome_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
        ON pulse_agent_jobs(status, next_run_at_ms, cooldown_until_ms, priority DESC, created_at_ms ASC, job_id ASC)
        WHERE status IN ('pending', 'failed')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_scope_status
        ON pulse_agent_jobs("window", scope, status, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_runs_job_finished
        ON pulse_agent_runs(job_id, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_runs_candidate_started
        ON pulse_agent_runs(candidate_id, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidates_latest
        ON pulse_candidates(pulse_version, "window", scope, pulse_status, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidates_target
        ON pulse_candidates(target_type, target_id, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidates_subject
        ON pulse_candidates(subject_key, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_playbook_snapshots_candidate
        ON pulse_playbook_snapshots(candidate_id, horizon, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_playbook_snapshots_target
        ON pulse_playbook_snapshots(target_type, target_id, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_playbook_outcomes_settled
        ON pulse_playbook_outcomes(settled_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pulse_playbook_outcomes_settled")
    op.execute("DROP INDEX IF EXISTS idx_pulse_playbook_snapshots_target")
    op.execute("DROP INDEX IF EXISTS idx_pulse_playbook_snapshots_candidate")
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidates_subject")
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidates_target")
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidates_latest")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_runs_candidate_started")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_runs_job_finished")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_scope_status")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim")
    op.execute("DROP TABLE IF EXISTS pulse_playbook_outcomes")
    op.execute("DROP TABLE IF EXISTS pulse_playbook_snapshots")
    op.execute("DROP TABLE IF EXISTS pulse_candidates")
    op.execute("DROP TABLE IF EXISTS pulse_agent_runs")
    op.execute("DROP TABLE IF EXISTS pulse_agent_jobs")
