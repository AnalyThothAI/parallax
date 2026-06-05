"""Reprocess legacy News analysis rows under the persisted agent contract."""

from __future__ import annotations

from alembic import op

revision = "20260605_0151"
down_revision = "20260605_0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_REQUEUE_LEGACY_ANALYSIS_ROWS_SQL)
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    raise RuntimeError(
        "20260605_0151 News legacy analysis reprocess is not safely reversible; "
        "rows may already have been reprocessed by current workers"
    )


_REQUEUE_LEGACY_ANALYSIS_ROWS_SQL = """
WITH runtime AS (
  SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
),
touched AS (
  UPDATE news_items AS items
     SET lifecycle_status = 'raw',
         processing_attempts = 0,
         processing_lease_owner = NULL,
         processing_leased_until_ms = NULL,
         processing_next_due_at_ms = 0,
         processing_error = NULL,
         processing_terminal_error = NULL,
         analysis_admission_reason = 'legacy_reprocess_required',
         analysis_admission_json = jsonb_build_object(
           'status', 'needs_review',
           'reason', 'legacy_reprocess_required',
           'version', 'news_analysis_admission_v1'
         ),
         agent_requirement_status = 'not_required',
         agent_requirement_reason = 'item_not_processed',
         agent_requirement_priority = 100,
         agent_requirement_json = jsonb_build_object(
           'status', 'not_required',
           'reason', 'item_not_processed',
           'version', 'news_item_agent_requirement_v1',
           'basis', jsonb_build_object('reset_reason', 'legacy_analysis_reprocess')
         ),
         agent_requirement_version = 'news_item_agent_requirement_v1',
         updated_at_ms = runtime.now_ms
    FROM runtime
   WHERE items.lifecycle_status = 'processed'
     AND items.analysis_admission_status = 'needs_review'
  RETURNING items.news_item_id, items.published_at_ms, runtime.now_ms
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
  'page',
  'news_item',
  touched.news_item_id,
  '',
  'news_legacy_analysis_reprocess',
  md5('page:legacy_analysis_reprocess:' || touched.news_item_id || ':' || touched.now_ms::text),
  GREATEST(COALESCE(touched.published_at_ms, 0), touched.now_ms),
  10,
  touched.now_ms,
  NULL,
  NULL,
  0,
  NULL,
  touched.now_ms,
  touched.now_ms
FROM touched
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
