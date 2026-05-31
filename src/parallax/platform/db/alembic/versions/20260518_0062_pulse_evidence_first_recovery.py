"""Add Pulse evidence-first packet storage and state checks."""

from __future__ import annotations

from alembic import op

revision = "20260518_0062"
down_revision = "20260518_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_evidence_packets (
          evidence_packet_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
          candidate_id TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          evidence_packet_hash TEXT NOT NULL UNIQUE,
          packet_json JSONB NOT NULL,
          summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_fingerprints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_evidence_packets_run
          ON pulse_evidence_packets(run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_evidence_packets_candidate_created
          ON pulse_evidence_packets(candidate_id, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_evidence_packets_target_created
          ON pulse_evidence_packets(target_type, target_id, created_at_ms DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_agent_runs
          ADD COLUMN IF NOT EXISTS evidence_packet_id TEXT,
          ADD COLUMN IF NOT EXISTS evidence_packet_hash TEXT,
          ADD COLUMN IF NOT EXISTS evidence_status TEXT,
          ADD COLUMN IF NOT EXISTS display_status TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS evidence_packet_hash TEXT,
          ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'insufficient',
          ADD COLUMN IF NOT EXISTS decision_status TEXT NOT NULL DEFAULT 'invalid',
          ADD COLUMN IF NOT EXISTS display_status TEXT NOT NULL DEFAULT 'hidden_insufficient_evidence',
          ADD COLUMN IF NOT EXISTS claim_verification_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS evidence_gate_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE pulse_candidates
        SET display_status = 'hidden_insufficient_evidence',
            evidence_status = 'insufficient',
            decision_status = 'invalid'
        """
    )
    op.execute("ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS pulse_agent_run_steps_stage_check")
    op.execute("ALTER TABLE pulse_agent_runs DROP CONSTRAINT IF EXISTS chk_pulse_agent_runs_outcome_hard_cut")
    _add_check_if_missing(
        "chk_pulse_agent_run_steps_stage_evidence_first",
        """
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT chk_pulse_agent_run_steps_stage_evidence_first
          CHECK (stage IN (
            'evidence_pack',
            'evidence_completeness_gate',
            'evidence_debate',
            'claim_verifier',
            'decision_maker',
            'recommendation_clipper',
            'deterministic_eval',
            'write_gate'
          )) NOT VALID
        """,
    )
    _add_check_if_missing(
        "chk_pulse_agent_runs_outcome_evidence_first",
        """
        ALTER TABLE pulse_agent_runs
          ADD CONSTRAINT chk_pulse_agent_runs_outcome_evidence_first
          CHECK (outcome IN (
            'running',
            'completed',
            'abstain_insufficient_evidence',
            'blocked_market_contract',
            'blocked_social_contract',
            'blocked_identity_contract',
            'invalid_schema',
            'invalid_unknown_evidence_ref',
            'invalid_unsupported_claim',
            'timeout',
            'provider_rate_limited',
            'provider_unavailable',
            'unexpected_exception'
          )) NOT VALID
        """,
    )
    _add_check_if_missing(
        "chk_pulse_candidates_display_status_evidence_first",
        """
        ALTER TABLE pulse_candidates
          ADD CONSTRAINT chk_pulse_candidates_display_status_evidence_first
          CHECK (display_status IN (
            'display_trade_candidate',
            'display_token_watch',
            'display_risk_rejected_high_info',
            'hidden_abstain',
            'hidden_insufficient_evidence',
            'hidden_blocked_low_information',
            'hidden_invalid_output',
            'hidden_hold_publish'
          )) NOT VALID
        """,
    )
    _add_check_if_missing(
        "chk_pulse_candidates_evidence_status_evidence_first",
        """
        ALTER TABLE pulse_candidates
          ADD CONSTRAINT chk_pulse_candidates_evidence_status_evidence_first
          CHECK (evidence_status IN (
            'complete',
            'partial',
            'insufficient',
            'stale',
            'invalid'
          )) NOT VALID
        """,
    )
    _add_check_if_missing(
        "chk_pulse_candidates_decision_status_evidence_first",
        """
        ALTER TABLE pulse_candidates
          ADD CONSTRAINT chk_pulse_candidates_decision_status_evidence_first
          CHECK (decision_status IN (
            'trade_candidate',
            'token_watch',
            'risk_rejected_high_info',
            'abstain',
            'invalid'
          )) NOT VALID
        """,
    )
    _add_check_if_missing(
        "chk_pulse_candidates_public_requires_packet",
        """
        ALTER TABLE pulse_candidates
          ADD CONSTRAINT chk_pulse_candidates_public_requires_packet
          CHECK (
            display_status LIKE 'hidden_%'
            OR evidence_packet_hash IS NOT NULL
          ) NOT VALID
        """,
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_public_requires_packet")
    op.execute(
        "ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_decision_status_evidence_first"
    )
    op.execute(
        "ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_evidence_status_evidence_first"
    )
    op.execute(
        "ALTER TABLE pulse_candidates DROP CONSTRAINT IF EXISTS chk_pulse_candidates_display_status_evidence_first"
    )
    op.execute("ALTER TABLE pulse_agent_runs DROP CONSTRAINT IF EXISTS chk_pulse_agent_runs_outcome_evidence_first")
    op.execute(
        "ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT IF EXISTS chk_pulse_agent_run_steps_stage_evidence_first"
    )
    op.execute(
        """
        ALTER TABLE pulse_agent_run_steps
          ADD CONSTRAINT pulse_agent_run_steps_stage_check
          CHECK (stage IN ('investigator','decision_maker','research_only_gate'))
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_agent_runs
          ADD CONSTRAINT chk_pulse_agent_runs_outcome_hard_cut
          CHECK (outcome IN (
            'running','completed','abstain','abstain_critic_veto','abstain_insufficient_data','failed'
          )) NOT VALID
        """
    )
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS evidence_gate_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS claim_verification_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS display_status")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS decision_status")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS evidence_status")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS evidence_packet_hash")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS display_status")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS evidence_status")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS evidence_packet_hash")
    op.execute("ALTER TABLE pulse_agent_runs DROP COLUMN IF EXISTS evidence_packet_id")
    op.execute("DROP INDEX IF EXISTS idx_pulse_evidence_packets_target_created")
    op.execute("DROP INDEX IF EXISTS idx_pulse_evidence_packets_candidate_created")
    op.execute("DROP INDEX IF EXISTS idx_pulse_evidence_packets_run")
    op.execute("DROP TABLE IF EXISTS pulse_evidence_packets")


def _add_check_if_missing(constraint_name: str, ddl: str) -> None:
    escaped = ddl.replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = '{constraint_name}'
          ) THEN
            EXECUTE '{escaped}';
          END IF;
        END $$;
        """
    )
