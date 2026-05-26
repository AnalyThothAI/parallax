"""Add equity event evidence and readiness hard-cut schema."""

from __future__ import annotations

from alembic import op

revision = "20260526_0103"
down_revision = "20260526_0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_evidence_artifacts (
          evidence_artifact_id TEXT PRIMARY KEY,
          event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE,
          provider_document_id TEXT REFERENCES equity_provider_documents(provider_document_id) ON DELETE SET NULL,
          source_id TEXT REFERENCES equity_event_sources(source_id) ON DELETE SET NULL,
          artifact_kind TEXT NOT NULL,
          extraction_status TEXT NOT NULL,
          source_url TEXT NOT NULL DEFAULT '',
          content_hash TEXT NOT NULL DEFAULT '',
          content_text TEXT NOT NULL DEFAULT '',
          content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          excerpt_text TEXT NOT NULL DEFAULT '',
          failure_reason TEXT,
          fetched_at_ms BIGINT NOT NULL DEFAULT 0,
          parsed_at_ms BIGINT NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            artifact_kind IN (
              'html_text',
              'xbrl',
              'companyfacts',
              'table',
              'exhibit_text',
              'transcript_text',
              'ir_text'
            )
          ),
          CHECK (extraction_status IN ('ready', 'unavailable', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_artifacts_document
          ON equity_event_evidence_artifacts(event_document_id, extraction_status, artifact_kind)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_brief_states (
          company_event_id TEXT PRIMARY KEY REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          brief_readiness_status TEXT NOT NULL,
          reason_code TEXT NOT NULL DEFAULT '',
          reason_detail TEXT NOT NULL DEFAULT '',
          input_hash TEXT NOT NULL DEFAULT '',
          source_updated_at_ms BIGINT NOT NULL DEFAULT 0,
          next_retry_after_ms BIGINT,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            brief_readiness_status IN (
              'pending_due',
              'in_progress',
              'ready',
              'insufficient',
              'failed_retryable',
              'failed_terminal',
              'stale',
              'historical_unscheduled',
              'disabled'
            )
          )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_documents
          ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS evidence_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS evidence_ready_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS fact_extraction_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS fact_extraction_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS fact_extracted_at_ms BIGINT
        """
    )
    op.execute(
        """
        ALTER TABLE equity_company_events
          ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS evidence_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS brief_readiness_status TEXT NOT NULL DEFAULT 'pending_due',
          ADD COLUMN IF NOT EXISTS brief_readiness_reason TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_sources
          ADD COLUMN IF NOT EXISTS last_material_document_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS last_evidence_ready_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS last_product_projection_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS last_no_new_data_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS last_actionable_error TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_page_rows
          ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS evidence_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS fact_extraction_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS fact_extraction_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS freshness_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE equity_event_documents
           SET evidence_status = 'unavailable',
               evidence_reason = 'historical_metadata_only',
               fact_extraction_status = 'no_evidence',
               fact_extraction_reason = 'historical_metadata_only'
         WHERE evidence_status = 'pending'
        """
    )
    op.execute(
        """
        INSERT INTO equity_event_brief_states (
          company_event_id,
          brief_readiness_status,
          reason_code,
          reason_detail,
          source_updated_at_ms,
          updated_at_ms
        )
        SELECT company_event_id,
               'historical_unscheduled',
               'historical_metadata_only',
               'Existing row predates evidence hydration hard cut.',
               updated_at_ms,
               updated_at_ms
          FROM equity_company_events
        ON CONFLICT (company_event_id) DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_equity_event_documents_evidence_status'
          ) THEN
            ALTER TABLE equity_event_documents
              ADD CONSTRAINT ck_equity_event_documents_evidence_status
              CHECK (evidence_status IN ('pending', 'ready', 'unavailable', 'failed'));
          END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_equity_event_documents_fact_extraction_status'
          ) THEN
            ALTER TABLE equity_event_documents
              ADD CONSTRAINT ck_equity_event_documents_fact_extraction_status
              CHECK (fact_extraction_status IN (
                'pending',
                'ready',
                'no_evidence',
                'no_extractable_facts',
                'failed'
              ));
          END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_equity_company_events_evidence_status'
          ) THEN
            ALTER TABLE equity_company_events
              ADD CONSTRAINT ck_equity_company_events_evidence_status
              CHECK (evidence_status IN ('pending', 'ready', 'unavailable', 'failed'));
          END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_equity_company_events_brief_readiness_status'
          ) THEN
            ALTER TABLE equity_company_events
              ADD CONSTRAINT ck_equity_company_events_brief_readiness_status
              CHECK (
                brief_readiness_status IN (
                  'pending_due',
                  'in_progress',
                  'ready',
                  'insufficient',
                  'failed_retryable',
                  'failed_terminal',
                  'stale',
                  'historical_unscheduled',
                  'disabled'
                )
              );
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS equity_event_brief_states")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_evidence_artifacts_document")
    op.execute("DROP TABLE IF EXISTS equity_event_evidence_artifacts")
    op.execute(
        """
        ALTER TABLE equity_event_sources
          DROP COLUMN IF EXISTS last_actionable_error,
          DROP COLUMN IF EXISTS last_no_new_data_at_ms,
          DROP COLUMN IF EXISTS last_product_projection_at_ms,
          DROP COLUMN IF EXISTS last_evidence_ready_at_ms,
          DROP COLUMN IF EXISTS last_material_document_at_ms
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_page_rows
          DROP COLUMN IF EXISTS freshness_json,
          DROP COLUMN IF EXISTS fact_extraction_reason,
          DROP COLUMN IF EXISTS fact_extraction_status,
          DROP COLUMN IF EXISTS evidence_reason,
          DROP COLUMN IF EXISTS evidence_status
        """
    )
    op.execute(
        """
        ALTER TABLE equity_company_events
          DROP CONSTRAINT IF EXISTS ck_equity_company_events_brief_readiness_status,
          DROP CONSTRAINT IF EXISTS ck_equity_company_events_evidence_status,
          DROP COLUMN IF EXISTS brief_readiness_reason,
          DROP COLUMN IF EXISTS brief_readiness_status,
          DROP COLUMN IF EXISTS evidence_reason,
          DROP COLUMN IF EXISTS evidence_status
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_documents
          DROP CONSTRAINT IF EXISTS ck_equity_event_documents_fact_extraction_status,
          DROP CONSTRAINT IF EXISTS ck_equity_event_documents_evidence_status,
          DROP COLUMN IF EXISTS fact_extracted_at_ms,
          DROP COLUMN IF EXISTS fact_extraction_reason,
          DROP COLUMN IF EXISTS fact_extraction_status,
          DROP COLUMN IF EXISTS evidence_ready_at_ms,
          DROP COLUMN IF EXISTS evidence_reason,
          DROP COLUMN IF EXISTS evidence_status
        """
    )
