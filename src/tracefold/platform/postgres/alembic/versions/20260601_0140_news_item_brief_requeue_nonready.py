"""Requeue non-ready News item briefs for lightweight prompt contract."""

from __future__ import annotations

from alembic import op

revision = "20260601_0140"
down_revision = "20260601_0139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_CLEAR_NONREADY_CURRENT_BRIEFS_SQL)
    op.execute("ANALYZE news_item_agent_briefs")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    """No downgrade for clearing non-ready current brief read-model rows."""


_CLEAR_NONREADY_CURRENT_BRIEFS_SQL = """
WITH runtime AS (
  SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
),
cleared AS (
  DELETE FROM news_item_agent_briefs
   WHERE status IN ('failed', 'insufficient')
  RETURNING news_item_id
),
cleared_items AS (
  SELECT
    items.news_item_id,
    items.published_at_ms,
    CASE
      WHEN COALESCE(items.provider_signal_json ->> 'score', '') ~ '^-?[0-9]+$'
      THEN (items.provider_signal_json ->> 'score')::integer
      ELSE 0
    END AS provider_score,
    runtime.now_ms
  FROM cleared
  JOIN news_items AS items ON items.news_item_id = cleared.news_item_id
  CROSS JOIN runtime
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
  target.projection_name,
  'news_item',
  target.news_item_id,
  '',
  'news_item_brief_lightweight_nonready_requeue',
  md5(target.projection_name || ':' || target.news_item_id || ':' || target.now_ms::text),
  target.published_at_ms,
  target.priority,
  target.now_ms,
  NULL,
  NULL,
  0,
  NULL,
  target.now_ms,
  target.now_ms
FROM (
  SELECT
    'page' AS projection_name,
    cleared_items.news_item_id,
    cleared_items.published_at_ms,
    10 AS priority,
    cleared_items.now_ms
  FROM cleared_items
  UNION ALL
  SELECT
    'brief_input' AS projection_name,
    cleared_items.news_item_id,
    cleared_items.published_at_ms,
    20 AS priority,
    cleared_items.now_ms
  FROM cleared_items
  WHERE cleared_items.provider_score >= 80
) AS target
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
