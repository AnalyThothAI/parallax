"""Add equity event intel Kappa/CQRS tables."""

from __future__ import annotations

from alembic import op

revision = "20260522_0081"
down_revision = "20260521_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_sources (
          source_id TEXT PRIMARY KEY,
          provider_type TEXT NOT NULL,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          cik TEXT,
          source_role TEXT NOT NULL,
          trust_tier TEXT NOT NULL DEFAULT 'standard',
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          refresh_interval_seconds INTEGER NOT NULL DEFAULT 300,
          etag TEXT,
          last_modified TEXT,
          last_fetch_at_ms BIGINT,
          last_success_at_ms BIGINT,
          next_fetch_after_ms BIGINT NOT NULL DEFAULT 0,
          consecutive_failures INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (provider_type IN ('sec_submissions', 'company_ir_rss', 'company_ir_atom', 'configured_calendar')),
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (trust_tier IN ('official', 'high', 'standard', 'low'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_sources_due
          ON equity_event_sources(enabled, next_fetch_after_ms, source_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_fetch_runs (
          fetch_run_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL REFERENCES equity_event_sources(source_id) ON DELETE CASCADE,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          fetched_count INTEGER NOT NULL DEFAULT 0,
          inserted_count INTEGER NOT NULL DEFAULT 0,
          updated_count INTEGER NOT NULL DEFAULT 0,
          duplicate_count INTEGER NOT NULL DEFAULT 0,
          http_status INTEGER,
          error TEXT,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          CHECK (status IN ('running', 'success', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_fetch_runs_source_time
          ON equity_event_fetch_runs(source_id, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_universe_members (
          company_id TEXT PRIMARY KEY,
          ticker TEXT NOT NULL,
          company_name TEXT NOT NULL DEFAULT '',
          cik TEXT,
          exchange TEXT,
          active BOOLEAN NOT NULL DEFAULT TRUE,
          priority TEXT NOT NULL DEFAULT 'P3',
          config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_equity_event_universe_ticker ON equity_event_universe_members(ticker)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_expected_events (
          expected_event_id TEXT PRIMARY KEY,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          event_type TEXT NOT NULL,
          fiscal_period TEXT,
          expected_at_ms BIGINT NOT NULL,
          source_id TEXT NOT NULL,
          source_role TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'expected',
          confidence DOUBLE PRECISION NOT NULL DEFAULT 1,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (status IN ('expected', 'observed', 'cancelled', 'stale'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_expected_events_due
          ON equity_expected_events(status, expected_at_ms, ticker)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_provider_documents (
          provider_document_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL REFERENCES equity_event_sources(source_id) ON DELETE CASCADE,
          fetch_run_id TEXT REFERENCES equity_event_fetch_runs(fetch_run_id) ON DELETE SET NULL,
          provider_document_key TEXT NOT NULL,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          cik TEXT,
          document_url TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          raw_payload_json JSONB NOT NULL,
          fetched_at_ms BIGINT NOT NULL,
          UNIQUE (source_id, provider_document_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_documents (
          event_document_id TEXT PRIMARY KEY,
          provider_document_id TEXT NOT NULL
            REFERENCES equity_provider_documents(provider_document_id) ON DELETE CASCADE,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          cik TEXT,
          source_id TEXT NOT NULL REFERENCES equity_event_sources(source_id) ON DELETE CASCADE,
          source_role TEXT NOT NULL,
          document_type TEXT NOT NULL,
          form_type TEXT,
          accession_number TEXT,
          fiscal_period TEXT,
          document_url TEXT NOT NULL,
          event_time_ms BIGINT NOT NULL,
          discovered_at_ms BIGINT NOT NULL,
          content_hash TEXT NOT NULL,
          lifecycle_status TEXT NOT NULL DEFAULT 'raw',
          processing_attempts INTEGER NOT NULL DEFAULT 0,
          processing_error TEXT,
          processed_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_documents_company_time
          ON equity_event_documents(company_id, event_time_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_document_revisions (
          revision_id TEXT PRIMARY KEY,
          event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE,
          provider_document_id TEXT REFERENCES equity_provider_documents(provider_document_id) ON DELETE SET NULL,
          revision_number INTEGER NOT NULL,
          content_hash TEXT NOT NULL,
          diff_hash TEXT,
          revision_reason TEXT NOT NULL DEFAULT '',
          fetched_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE (event_document_id, revision_number)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_section_diffs (
          diff_id TEXT PRIMARY KEY,
          event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE,
          previous_revision_id TEXT REFERENCES equity_document_revisions(revision_id) ON DELETE SET NULL,
          current_revision_id TEXT REFERENCES equity_document_revisions(revision_id) ON DELETE SET NULL,
          section_key TEXT NOT NULL,
          change_type TEXT NOT NULL,
          previous_hash TEXT,
          current_hash TEXT,
          summary TEXT NOT NULL DEFAULT '',
          diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          CHECK (change_type IN ('added', 'removed', 'changed', 'unchanged'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_company_events (
          company_event_id TEXT PRIMARY KEY,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          primary_document_id TEXT REFERENCES equity_event_documents(event_document_id) ON DELETE SET NULL,
          event_type TEXT NOT NULL,
          priority TEXT NOT NULL,
          source_role TEXT NOT NULL,
          fiscal_period TEXT,
          event_time_ms BIGINT NOT NULL,
          discovered_at_ms BIGINT NOT NULL,
          lifecycle_status TEXT NOT NULL DEFAULT 'raw',
          validation_status TEXT NOT NULL DEFAULT 'pending',
          summary TEXT NOT NULL DEFAULT '',
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale')),
          CHECK (validation_status IN ('accepted', 'attention', 'rejected', 'pending'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_company_events_latest
          ON equity_company_events(event_time_ms DESC, company_event_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_source_spans (
          span_id TEXT PRIMARY KEY,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          event_document_id TEXT REFERENCES equity_event_documents(event_document_id) ON DELETE SET NULL,
          source_id TEXT REFERENCES equity_event_sources(source_id) ON DELETE SET NULL,
          span_type TEXT NOT NULL,
          section_key TEXT,
          span_start INTEGER NOT NULL DEFAULT 0,
          span_end INTEGER NOT NULL DEFAULT 0,
          evidence_quote TEXT NOT NULL DEFAULT '',
          confidence DOUBLE PRECISION NOT NULL DEFAULT 1,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_fact_candidates (
          fact_candidate_id TEXT PRIMARY KEY,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          event_document_id TEXT REFERENCES equity_event_documents(event_document_id) ON DELETE SET NULL,
          source_span_id TEXT REFERENCES equity_event_source_spans(span_id) ON DELETE SET NULL,
          fact_type TEXT NOT NULL,
          claim TEXT NOT NULL,
          evidence_quote TEXT NOT NULL,
          source_role TEXT NOT NULL,
          validation_status TEXT NOT NULL,
          rejection_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          extraction_method TEXT NOT NULL,
          policy_version TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (validation_status IN ('accepted', 'attention', 'rejected', 'pending'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_fact_candidates_event
          ON equity_event_fact_candidates(company_event_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_story_groups (
          story_id TEXT PRIMARY KEY,
          policy_version TEXT NOT NULL,
          representative_headline TEXT NOT NULL,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          first_seen_at_ms BIGINT NOT NULL,
          latest_seen_at_ms BIGINT NOT NULL,
          event_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'active',
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (status IN ('active', 'stale'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_story_members (
          story_id TEXT NOT NULL REFERENCES equity_event_story_groups(story_id) ON DELETE CASCADE,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          relation TEXT NOT NULL,
          match_reason TEXT NOT NULL,
          match_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (story_id, company_event_id),
          CHECK (relation IN ('representative', 'same_story'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_equity_event_story_members_event
          ON equity_event_story_members(company_event_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_agent_runs (
          run_id TEXT PRIMARY KEY,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          backend TEXT NOT NULL DEFAULT 'openai_agents_sdk',
          sdk_trace_id TEXT,
          workflow_name TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          lane TEXT NOT NULL,
          artifact_version_hash TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          validator_version TEXT NOT NULL,
          guardrail_version TEXT NOT NULL,
          input_hash TEXT NOT NULL,
          output_hash TEXT,
          execution_started BOOLEAN NOT NULL DEFAULT FALSE,
          status TEXT NOT NULL,
          outcome TEXT NOT NULL,
          error_class TEXT,
          error TEXT,
          request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          response_json JSONB,
          validation_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          latency_ms BIGINT NOT NULL DEFAULT 0,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          CHECK (status IN ('completed', 'failed', 'backpressure')),
          CHECK (
            outcome IN (
              'ready',
              'insufficient',
              'failed',
              'backpressure_capacity_denied',
              'backpressure_circuit_open',
              'backpressure_rate_limited'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_agent_briefs (
          company_event_id TEXT PRIMARY KEY REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          agent_run_id TEXT NOT NULL REFERENCES equity_event_agent_runs(run_id) ON DELETE CASCADE,
          status TEXT NOT NULL,
          validation_status TEXT NOT NULL DEFAULT 'pending',
          brief_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          input_hash TEXT NOT NULL,
          artifact_version_hash TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          validator_version TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (status IN ('ready', 'insufficient', 'failed')),
          CHECK (validation_status IN ('accepted', 'attention', 'rejected', 'pending'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_page_rows (
          row_id TEXT PRIMARY KEY,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          story_id TEXT,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          company_name TEXT NOT NULL DEFAULT '',
          event_type TEXT NOT NULL,
          priority TEXT NOT NULL,
          source_role TEXT NOT NULL,
          latest_event_at_ms BIGINT NOT NULL,
          lifecycle_status TEXT NOT NULL,
          headline TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          facts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          documents_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          brief_json JSONB NOT NULL DEFAULT '{"status":"pending"}'::jsonb,
          computed_at_ms BIGINT NOT NULL,
          projection_version TEXT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_page_rows_latest
          ON equity_event_page_rows(latest_event_at_ms DESC, company_event_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_calendar_rows (
          row_id TEXT PRIMARY KEY,
          expected_event_id TEXT REFERENCES equity_expected_events(expected_event_id) ON DELETE CASCADE,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          company_name TEXT NOT NULL DEFAULT '',
          event_type TEXT NOT NULL,
          priority TEXT NOT NULL DEFAULT 'P2',
          source_role TEXT NOT NULL,
          fiscal_period TEXT,
          expected_at_ms BIGINT NOT NULL,
          status TEXT NOT NULL,
          headline TEXT NOT NULL DEFAULT '',
          calendar_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms BIGINT NOT NULL,
          projection_version TEXT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_calendar_rows_time
          ON equity_event_calendar_rows(expected_at_ms ASC, ticker)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_alert_candidates (
          alert_candidate_id TEXT PRIMARY KEY,
          company_event_id TEXT NOT NULL REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          event_type TEXT NOT NULL,
          priority TEXT NOT NULL,
          lifecycle_status TEXT NOT NULL,
          validation_status TEXT NOT NULL DEFAULT 'pending',
          alert_status TEXT NOT NULL DEFAULT 'pending',
          reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms BIGINT NOT NULL,
          projection_version TEXT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale')),
          CHECK (validation_status IN ('accepted', 'attention', 'rejected', 'pending')),
          CHECK (alert_status IN ('pending', 'sent', 'suppressed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_company_timeline_rows (
          row_id TEXT PRIMARY KEY,
          company_id TEXT NOT NULL,
          ticker TEXT NOT NULL,
          company_event_id TEXT REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
          story_id TEXT,
          event_type TEXT NOT NULL,
          priority TEXT NOT NULL,
          source_role TEXT NOT NULL,
          event_time_ms BIGINT NOT NULL,
          lifecycle_status TEXT NOT NULL,
          headline TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms BIGINT NOT NULL,
          projection_version TEXT NOT NULL,
          CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
          CHECK (
            source_role IN (
              'official_regulator',
              'official_issuer',
              'calendar',
              'transcript',
              'specialist_media',
              'observed_source'
            )
          ),
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale'))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS equity_company_timeline_rows")
    op.execute("DROP TABLE IF EXISTS equity_event_alert_candidates")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_calendar_rows_time")
    op.execute("DROP TABLE IF EXISTS equity_event_calendar_rows")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_page_rows_latest")
    op.execute("DROP TABLE IF EXISTS equity_event_page_rows")
    op.execute("DROP TABLE IF EXISTS equity_event_agent_briefs")
    op.execute("DROP TABLE IF EXISTS equity_event_agent_runs")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_story_members_event")
    op.execute("DROP TABLE IF EXISTS equity_event_story_members")
    op.execute("DROP TABLE IF EXISTS equity_event_story_groups")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_fact_candidates_event")
    op.execute("DROP TABLE IF EXISTS equity_event_fact_candidates")
    op.execute("DROP TABLE IF EXISTS equity_event_source_spans")
    op.execute("DROP INDEX IF EXISTS idx_equity_company_events_latest")
    op.execute("DROP TABLE IF EXISTS equity_company_events")
    op.execute("DROP TABLE IF EXISTS equity_section_diffs")
    op.execute("DROP TABLE IF EXISTS equity_document_revisions")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_documents_company_time")
    op.execute("DROP TABLE IF EXISTS equity_event_documents")
    op.execute("DROP TABLE IF EXISTS equity_provider_documents")
    op.execute("DROP INDEX IF EXISTS idx_equity_expected_events_due")
    op.execute("DROP TABLE IF EXISTS equity_expected_events")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_universe_ticker")
    op.execute("DROP TABLE IF EXISTS equity_event_universe_members")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_fetch_runs_source_time")
    op.execute("DROP TABLE IF EXISTS equity_event_fetch_runs")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_sources_due")
    op.execute("DROP TABLE IF EXISTS equity_event_sources")
