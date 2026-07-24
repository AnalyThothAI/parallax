"""Hard cut deterministic Macro projections to immutable DeepAgents research."""

from __future__ import annotations

from alembic import op

revision = "20260724_0194"
down_revision = "20260723_0193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    _drop_retired_macro_derived_state()
    _create_macro_research_state()
    _create_langgraph_checkpoint_state()


def downgrade() -> None:
    raise RuntimeError(
        "20260724_0194 is an irreversible Macro research hard cut; downgrade is unsupported, apply a forward fix"
    )


def _drop_retired_macro_derived_state() -> None:
    op.execute(
        """
        LOCK TABLE
          macro_projection_dirty_targets,
          macro_observation_series_rows,
          macro_observation_series_publication_state,
          macro_view_snapshots,
          macro_judgment_jobs,
          macro_judgment_publications,
          macro_judgment_outcomes
        IN ACCESS EXCLUSIVE MODE
        """
    )
    op.execute("DROP TABLE macro_judgment_outcomes")
    op.execute("DROP TABLE macro_judgment_publications")
    op.execute("DROP TABLE macro_judgment_jobs")
    op.execute("DROP FUNCTION reject_macro_judgment_job_identity_mutation()")
    op.execute("DROP FUNCTION reject_macro_judgment_immutable_row_mutation()")
    op.execute("DROP TABLE macro_view_snapshots")
    op.execute("DROP TABLE macro_observation_series_publication_state")
    op.execute("DROP TABLE macro_observation_series_rows")
    op.execute("DROP TABLE macro_projection_dirty_targets")


def _create_macro_research_state() -> None:
    op.execute(
        """
        CREATE TABLE macro_research_runs (
          session_date DATE PRIMARY KEY,
          market_cutoff_ms BIGINT NOT NULL CHECK (market_cutoff_ms >= 0),
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'running', 'retryable', 'failed', 'published')),
          sealed_at_ms BIGINT NOT NULL CHECK (sealed_at_ms >= market_cutoff_ms),
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
          due_at_ms BIGINT NOT NULL CHECK (due_at_ms >= 0),
          leased_until_ms BIGINT,
          lease_owner TEXT,
          last_error_code TEXT,
          last_error_message TEXT,
          created_at_ms BIGINT NOT NULL CHECK (created_at_ms >= 0),
          updated_at_ms BIGINT NOT NULL CHECK (updated_at_ms >= created_at_ms),
          UNIQUE (session_date, market_cutoff_ms),
          CONSTRAINT macro_research_runs_lease_shape_check CHECK (
            (
              status = 'running'
              AND leased_until_ms IS NOT NULL
              AND btrim(COALESCE(lease_owner, '')) <> ''
            )
            OR (
              status <> 'running'
              AND leased_until_ms IS NULL
              AND lease_owner IS NULL
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_research_runs_due
          ON macro_research_runs(status, due_at_ms, session_date)
          WHERE status IN ('pending', 'retryable', 'running')
        """
    )
    op.execute(
        """
        CREATE TABLE macro_research_publications (
          session_date DATE PRIMARY KEY,
          market_cutoff_ms BIGINT NOT NULL CHECK (market_cutoff_ms >= 0),
          artifact_json JSONB NOT NULL CHECK (jsonb_typeof(artifact_json) = 'object'),
          report_markdown TEXT NOT NULL CHECK (btrim(report_markdown) <> ''),
          audit_json JSONB NOT NULL CHECK (jsonb_typeof(audit_json) = 'object'),
          model_name TEXT NOT NULL CHECK (btrim(model_name) <> ''),
          prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
          workflow_version TEXT NOT NULL CHECK (btrim(workflow_version) <> ''),
          artifact_hash TEXT NOT NULL CHECK (btrim(artifact_hash) <> ''),
          published_at_ms BIGINT NOT NULL CHECK (published_at_ms >= market_cutoff_ms),
          FOREIGN KEY (session_date, market_cutoff_ms)
            REFERENCES macro_research_runs(session_date, market_cutoff_ms)
            ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_research_publications_latest
          ON macro_research_publications(session_date DESC)
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_macro_research_run_lifecycle()
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
             OR NEW.max_attempts IS DISTINCT FROM OLD.max_attempts
             OR NEW.created_at_ms IS DISTINCT FROM OLD.created_at_ms THEN
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
    )
    op.execute(
        """
        CREATE TRIGGER macro_research_runs_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON macro_research_runs
        FOR EACH ROW EXECUTE FUNCTION enforce_macro_research_run_lifecycle()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_macro_research_publication_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'macro_research_publication_immutable';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER macro_research_publications_immutable
        BEFORE UPDATE OR DELETE ON macro_research_publications
        FOR EACH ROW EXECUTE FUNCTION reject_macro_research_publication_mutation()
        """
    )


def _create_langgraph_checkpoint_state() -> None:
    # This is the exact latest table shape expected by
    # langgraph-checkpoint-postgres==3.1.0. Application startup does not run DDL.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_migrations (
          v INTEGER PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
          thread_id TEXT NOT NULL,
          checkpoint_ns TEXT NOT NULL DEFAULT '',
          checkpoint_id TEXT NOT NULL,
          parent_checkpoint_id TEXT,
          type TEXT,
          checkpoint JSONB NOT NULL,
          metadata JSONB NOT NULL DEFAULT '{}',
          PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
          thread_id TEXT NOT NULL,
          checkpoint_ns TEXT NOT NULL DEFAULT '',
          channel TEXT NOT NULL,
          version TEXT NOT NULL,
          type TEXT NOT NULL,
          blob BYTEA,
          PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_writes (
          thread_id TEXT NOT NULL,
          checkpoint_ns TEXT NOT NULL DEFAULT '',
          checkpoint_id TEXT NOT NULL,
          task_id TEXT NOT NULL,
          idx INTEGER NOT NULL,
          channel TEXT NOT NULL,
          type TEXT,
          blob BYTEA NOT NULL,
          task_path TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)")
    op.execute(
        """
        INSERT INTO checkpoint_migrations(v)
        SELECT generate_series(0, 9)
        ON CONFLICT(v) DO NOTHING
        """
    )
