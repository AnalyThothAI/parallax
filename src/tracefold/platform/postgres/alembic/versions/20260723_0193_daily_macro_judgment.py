"""Add the immutable Daily Macro SPY Judgment publication lane."""

from __future__ import annotations

from alembic import op

revision = "20260723_0193"
down_revision = "20260723_0192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute(
        """
        CREATE TABLE macro_judgment_jobs (
          session_date DATE PRIMARY KEY,
          market_cutoff_ms BIGINT NOT NULL CHECK (market_cutoff_ms >= 0),
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'running', 'retryable', 'blocked', 'failed', 'published')),
          evidence_pack_json JSONB NOT NULL CHECK (jsonb_typeof(evidence_pack_json) = 'object'),
          evidence_pack_hash TEXT NOT NULL CHECK (btrim(evidence_pack_hash) <> ''),
          compiler_version TEXT NOT NULL CHECK (btrim(compiler_version) <> ''),
          selection_policy_version TEXT NOT NULL CHECK (btrim(selection_policy_version) <> ''),
          sealed_at_ms BIGINT NOT NULL CHECK (sealed_at_ms >= market_cutoff_ms),
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
          due_at_ms BIGINT NOT NULL CHECK (due_at_ms >= 0),
          leased_until_ms BIGINT,
          lease_owner TEXT,
          reviewer_disposition TEXT
            CHECK (reviewer_disposition IS NULL OR reviewer_disposition IN ('pass', 'revise', 'block')),
          last_error TEXT,
          created_at_ms BIGINT NOT NULL CHECK (created_at_ms >= 0),
          updated_at_ms BIGINT NOT NULL CHECK (updated_at_ms >= created_at_ms)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_judgment_jobs_due
          ON macro_judgment_jobs(status, due_at_ms, session_date)
          WHERE status IN ('pending', 'retryable', 'running')
        """
    )
    op.execute(
        """
        CREATE TABLE macro_judgment_publications (
          session_date DATE PRIMARY KEY
            REFERENCES macro_judgment_jobs(session_date) ON DELETE RESTRICT,
          market_cutoff_ms BIGINT NOT NULL CHECK (market_cutoff_ms >= 0),
          evidence_pack_hash TEXT NOT NULL CHECK (btrim(evidence_pack_hash) <> ''),
          judgment_json JSONB NOT NULL CHECK (jsonb_typeof(judgment_json) = 'object'),
          memo_text TEXT NOT NULL CHECK (btrim(memo_text) <> ''),
          review_json JSONB NOT NULL CHECK (jsonb_typeof(review_json) = 'object'),
          agent_audit_json JSONB NOT NULL CHECK (jsonb_typeof(agent_audit_json) = 'object'),
          model_name TEXT NOT NULL CHECK (btrim(model_name) <> ''),
          prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
          schema_version TEXT NOT NULL CHECK (btrim(schema_version) <> ''),
          workflow_version TEXT NOT NULL CHECK (btrim(workflow_version) <> ''),
          renderer_version TEXT NOT NULL CHECK (btrim(renderer_version) <> ''),
          published_at_ms BIGINT NOT NULL CHECK (published_at_ms >= market_cutoff_ms)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_judgment_publications_latest
          ON macro_judgment_publications(session_date DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE macro_judgment_outcomes (
          session_date DATE NOT NULL
            REFERENCES macro_judgment_publications(session_date) ON DELETE RESTRICT,
          horizon_sessions INTEGER NOT NULL CHECK (horizon_sessions IN (5, 20)),
          target_session_date DATE NOT NULL CHECK (target_session_date > session_date),
          start_close DOUBLE PRECISION NOT NULL CHECK (start_close > 0),
          target_close DOUBLE PRECISION NOT NULL CHECK (target_close > 0),
          realized_return_pct DOUBLE PRECISION NOT NULL,
          source_evidence_refs_json JSONB NOT NULL
            CHECK (
              jsonb_typeof(source_evidence_refs_json) = 'array'
              AND jsonb_array_length(source_evidence_refs_json) >= 2
            ),
          computed_at_ms BIGINT NOT NULL CHECK (computed_at_ms >= 0),
          PRIMARY KEY (session_date, horizon_sessions)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_judgment_outcomes_target
          ON macro_judgment_outcomes(target_session_date, horizon_sessions)
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_macro_judgment_job_identity_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'macro_judgment_job_delete_forbidden';
          END IF;
          IF NEW.session_date IS DISTINCT FROM OLD.session_date
             OR NEW.market_cutoff_ms IS DISTINCT FROM OLD.market_cutoff_ms
             OR NEW.evidence_pack_json IS DISTINCT FROM OLD.evidence_pack_json
             OR NEW.evidence_pack_hash IS DISTINCT FROM OLD.evidence_pack_hash
             OR NEW.compiler_version IS DISTINCT FROM OLD.compiler_version
             OR NEW.selection_policy_version IS DISTINCT FROM OLD.selection_policy_version
             OR NEW.sealed_at_ms IS DISTINCT FROM OLD.sealed_at_ms
             OR NEW.max_attempts IS DISTINCT FROM OLD.max_attempts
             OR NEW.created_at_ms IS DISTINCT FROM OLD.created_at_ms THEN
            RAISE EXCEPTION 'macro_judgment_job_frozen_fields_immutable';
          END IF;
          RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER macro_judgment_jobs_immutable_identity
        BEFORE UPDATE OR DELETE ON macro_judgment_jobs
        FOR EACH ROW EXECUTE FUNCTION reject_macro_judgment_job_identity_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_macro_judgment_immutable_row_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION '%_immutable', TG_TABLE_NAME;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER macro_judgment_publications_immutable
        BEFORE UPDATE OR DELETE ON macro_judgment_publications
        FOR EACH ROW EXECUTE FUNCTION reject_macro_judgment_immutable_row_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER macro_judgment_outcomes_immutable
        BEFORE UPDATE OR DELETE ON macro_judgment_outcomes
        FOR EACH ROW EXECUTE FUNCTION reject_macro_judgment_immutable_row_mutation()
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260723_0193 adds immutable research history and cannot be downgraded without restoring a backup"
    )
