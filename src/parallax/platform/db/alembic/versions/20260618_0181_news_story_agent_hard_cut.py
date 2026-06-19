"""Add News story agent current state."""

from __future__ import annotations

from alembic import op

revision = "20260618_0181"
down_revision = "20260616_0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_story_agent_runs (
          run_id TEXT PRIMARY KEY,
          story_brief_key TEXT NOT NULL,
          story_key TEXT NOT NULL,
          story_identity_version TEXT NOT NULL,
          representative_news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id),
          member_news_item_ids_json JSONB NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          backend TEXT NOT NULL,
          execution_trace_id TEXT,
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
          execution_started BOOLEAN NOT NULL,
          status TEXT NOT NULL,
          outcome TEXT NOT NULL,
          error_class TEXT,
          error TEXT,
          request_json JSONB NOT NULL,
          response_json JSONB,
          validation_errors_json JSONB NOT NULL,
          trace_metadata_json JSONB NOT NULL,
          usage_json JSONB NOT NULL,
          latency_ms INTEGER NOT NULL,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_story_agent_briefs (
          story_brief_key TEXT PRIMARY KEY,
          story_key TEXT NOT NULL,
          story_identity_version TEXT NOT NULL,
          representative_news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id),
          member_news_item_ids_json JSONB NOT NULL,
          agent_run_id TEXT NOT NULL REFERENCES news_story_agent_runs(run_id) ON DELETE CASCADE,
          status TEXT NOT NULL,
          direction TEXT NOT NULL,
          decision_class TEXT NOT NULL,
          brief_json JSONB NOT NULL,
          input_hash TEXT NOT NULL,
          artifact_version_hash TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          validator_version TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_story_agent_runs_story_finished
          ON news_story_agent_runs(story_key, finished_at_ms DESC, run_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_story_agent_runs_input
          ON news_story_agent_runs(story_brief_key, input_hash, artifact_version_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_story_agent_briefs_status
          ON news_story_agent_briefs(status, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_projection_name_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_target_kind_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
          CHECK (projection_name IN ('brief_input', 'page', 'source_quality', 'story_brief'))
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_check
          CHECK (
            (projection_name = 'source_quality' AND target_kind = 'source' AND "window" <> '')
            OR (
              projection_name IN ('brief_input', 'page')
              AND target_kind = 'news_item'
              AND "window" = ''
            )
            OR (
              projection_name = 'story_brief'
              AND target_kind = 'story'
              AND "window" = ''
            )
          )
        """
    )
    op.execute("ANALYZE news_story_agent_runs")
    op.execute("ANALYZE news_story_agent_briefs")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    """No downgrade for the News story agent hard cut."""
