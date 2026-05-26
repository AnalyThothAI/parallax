"""Add macro generation swap state and equity evidence jobs."""

from __future__ import annotations

from alembic import op

revision = "20260526_0107"
down_revision = "20260526_0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_observation_series_generations (
          projection_version TEXT NOT NULL,
          generation_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'building',
          source_row_count BIGINT NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          activated_at_ms BIGINT,
          completed_at_ms BIGINT,
          failure_reason TEXT,
          PRIMARY KEY (projection_version, generation_id),
          CHECK (status IN ('building', 'active', 'superseded', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_observation_series_active_generation (
          projection_version TEXT NOT NULL,
          concept_key TEXT NOT NULL,
          generation_id TEXT NOT NULL,
          activated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_version, concept_key)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ADD COLUMN IF NOT EXISTS generation_id TEXT NOT NULL DEFAULT 'initial-active'
        """
    )
    op.execute(
        """
        UPDATE macro_observation_series_rows
           SET generation_id = 'initial-active'
         WHERE generation_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO macro_observation_series_generations (
          projection_version,
          generation_id,
          status,
          source_row_count,
          created_at_ms,
          activated_at_ms,
          completed_at_ms
        )
        SELECT projection_version,
               'initial-active',
               'active',
               count(*)::bigint,
               COALESCE(max(projected_at_ms), 0),
               COALESCE(max(projected_at_ms), 0),
               COALESCE(max(projected_at_ms), 0)
          FROM macro_observation_series_rows
         GROUP BY projection_version
        ON CONFLICT (projection_version, generation_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO macro_observation_series_active_generation (
          projection_version,
          concept_key,
          generation_id,
          activated_at_ms
        )
        SELECT projection_version,
               concept_key,
               'initial-active',
               COALESCE(max(projected_at_ms), 0)
          FROM macro_observation_series_rows
         GROUP BY projection_version, concept_key
        ON CONFLICT (projection_version, concept_key) DO UPDATE
          SET generation_id = EXCLUDED.generation_id,
              activated_at_ms = EXCLUDED.activated_at_ms
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          DROP CONSTRAINT IF EXISTS macro_observation_series_rows_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ADD CONSTRAINT macro_observation_series_rows_pkey
          PRIMARY KEY (projection_version, concept_key, observed_at, generation_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_evidence_jobs (
          evidence_job_id TEXT PRIMARY KEY,
          event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE,
          company_event_id TEXT REFERENCES equity_company_events(company_event_id) ON DELETE SET NULL,
          source_id TEXT REFERENCES equity_event_sources(source_id) ON DELETE SET NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          priority TEXT NOT NULL DEFAULT 'P2',
          due_at_ms BIGINT NOT NULL DEFAULT 0,
          started_at_ms BIGINT,
          finished_at_ms BIGINT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3,
          lease_owner TEXT,
          leased_until_ms BIGINT,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (status IN ('pending', 'running', 'success', 'failed_retryable', 'failed_terminal')),
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (attempt_count >= 0),
          CHECK (max_attempts > 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_due
          ON equity_event_evidence_jobs(priority, due_at_ms, evidence_job_id)
          WHERE status IN ('pending', 'failed_retryable')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_running
          ON equity_event_evidence_jobs(started_at_ms, leased_until_ms, evidence_job_id)
          WHERE status = 'running'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_equity_event_evidence_jobs_running")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_evidence_jobs_due")
    op.execute("DROP TABLE IF EXISTS equity_event_evidence_jobs")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          DROP CONSTRAINT IF EXISTS macro_observation_series_rows_pkey
        """
    )
    op.execute(
        """
        WITH ranked AS (
          SELECT rows.ctid AS row_ctid,
                 row_number() OVER (
                   PARTITION BY rows.projection_version, rows.concept_key, rows.observed_at
                   ORDER BY
                     CASE WHEN active.generation_id = rows.generation_id THEN 0 ELSE 1 END,
                     CASE WHEN rows.generation_id = 'initial-active' THEN 0 ELSE 1 END,
                     rows.projected_at_ms DESC,
                     rows.generation_id DESC
                 ) AS keep_rank
            FROM macro_observation_series_rows AS rows
            LEFT JOIN macro_observation_series_active_generation AS active
              ON active.projection_version = rows.projection_version
             AND active.concept_key = rows.concept_key
        )
        DELETE FROM macro_observation_series_rows AS rows
        USING ranked
        WHERE rows.ctid = ranked.row_ctid
          AND ranked.keep_rank > 1
        """
    )
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ADD CONSTRAINT macro_observation_series_rows_pkey
          PRIMARY KEY (projection_version, concept_key, observed_at)
        """
    )
    op.execute("ALTER TABLE macro_observation_series_rows DROP COLUMN IF EXISTS generation_id")
    op.execute("DROP TABLE IF EXISTS macro_observation_series_active_generation")
    op.execute("DROP TABLE IF EXISTS macro_observation_series_generations")
