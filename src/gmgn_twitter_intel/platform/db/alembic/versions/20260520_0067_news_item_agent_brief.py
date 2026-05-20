"""Add news item agent brief audit and current read model."""

from __future__ import annotations

from alembic import op

revision = "20260520_0067"
down_revision = "20260519_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_item_agent_runs (
          run_id TEXT PRIMARY KEY,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
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
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_runs_item_finished
          ON news_item_agent_runs(news_item_id, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_runs_outcome_finished
          ON news_item_agent_runs(outcome, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_runs_sdk_trace
          ON news_item_agent_runs(sdk_trace_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_item_agent_briefs (
          news_item_id TEXT PRIMARY KEY REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          agent_run_id TEXT NOT NULL REFERENCES news_item_agent_runs(run_id) ON DELETE CASCADE,
          status TEXT NOT NULL,
          direction TEXT NOT NULL,
          decision_class TEXT NOT NULL,
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
          CHECK (direction IN ('bullish', 'bearish', 'mixed', 'neutral')),
          CHECK (decision_class IN ('driver', 'watch', 'context', 'discard'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_briefs_status
          ON news_item_agent_briefs(status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_briefs_updated
          ON news_item_agent_briefs(updated_at_ms DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS agent_brief_json JSONB NOT NULL DEFAULT '{"status":"pending"}'::jsonb,
          ADD COLUMN IF NOT EXISTS agent_status TEXT NOT NULL DEFAULT 'pending',
          ADD COLUMN IF NOT EXISTS agent_brief_computed_at_ms BIGINT
        """
    )
    op.execute(
        """
        UPDATE news_page_rows
           SET agent_brief_json = '{"status":"pending"}'::jsonb
         WHERE agent_brief_json = '{}'::jsonb
           AND agent_status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS agent_brief_computed_at_ms")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS agent_status")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS agent_brief_json")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_briefs_updated")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_briefs_status")
    op.execute("DROP TABLE IF EXISTS news_item_agent_briefs")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_runs_sdk_trace")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_runs_outcome_finished")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_runs_item_finished")
    op.execute("DROP TABLE IF EXISTS news_item_agent_runs")
