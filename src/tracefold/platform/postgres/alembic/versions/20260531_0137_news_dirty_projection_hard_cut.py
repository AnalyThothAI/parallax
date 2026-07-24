"""Hard cut retired News dirty projections and restore current brief backlog."""

from __future__ import annotations

from alembic import op

revision = "20260531_0137"
down_revision = "20260531_0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets
         WHERE projection_name = 'story'
            OR dirty_reason = 'news_story_projected'
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
          ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
          CHECK (projection_name IN ('brief_input', 'page', 'source_quality'))
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
          )
        """
    )
    op.execute(_REQUEUE_RECENT_PROVIDER_BRIEF_TARGETS_SQL)
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    """No downgrade for the hard-cut removal of retired News dirty projections."""


_REQUEUE_RECENT_PROVIDER_BRIEF_TARGETS_SQL = """
WITH runtime AS (
  SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
),
eligible AS (
  SELECT
    items.news_item_id,
    items.published_at_ms,
    COALESCE(NULLIF(items.provider_signal_json ->> 'score', '')::integer, 0) AS provider_score,
    runtime.now_ms
  FROM news_items AS items
  JOIN news_sources AS sources ON sources.source_id = items.source_id
  CROSS JOIN runtime
  WHERE sources.enabled = true
    AND COALESCE(lower(items.provider_signal_json ->> 'source'), '') = 'provider'
    AND COALESCE(items.provider_signal_json ->> 'score', '') ~ '^-?[0-9]+$'
    AND (items.provider_signal_json ->> 'score')::integer >= 80
    AND items.published_at_ms BETWEEN runtime.now_ms - (8 * 60 * 60 * 1000) AND runtime.now_ms
)
INSERT INTO news_projection_dirty_targets(
  projection_name,
  target_kind,
  target_id,
  "window",
  dirty_reason,
  payload_hash,
  source_watermark_ms,
  priority,
  due_at_ms,
  leased_until_ms,
  lease_owner,
  attempt_count,
  last_error,
  first_dirty_at_ms,
  updated_at_ms
)
SELECT
  'brief_input',
  'news_item',
  eligible.news_item_id,
  '',
  'news_current_provider_brief_backlog_restore',
  md5(
    'brief_input:' || eligible.news_item_id || ':' ||
    eligible.provider_score::text || ':' || eligible.published_at_ms::text
  ),
  eligible.published_at_ms,
  20,
  eligible.now_ms,
  NULL,
  NULL,
  0,
  NULL,
  eligible.now_ms,
  eligible.now_ms
FROM eligible
ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
  dirty_reason = EXCLUDED.dirty_reason,
  payload_hash = EXCLUDED.payload_hash,
  source_watermark_ms = GREATEST(
    news_projection_dirty_targets.source_watermark_ms,
    EXCLUDED.source_watermark_ms
  ),
  priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
  due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  last_error = NULL,
  updated_at_ms = EXCLUDED.updated_at_ms
"""
