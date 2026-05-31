"""Normalize terminal reason buckets for operator triage."""

from __future__ import annotations

from alembic import op

revision = "20260526_0103"
down_revision = "20260526_0102"
branch_labels = None
depends_on = None


_NORMALIZE_TERMINAL_REASON_BUCKETS_SQL = """
UPDATE worker_queue_terminal_events
SET final_reason_bucket = CASE
  WHEN final_reason ILIKE '%522%' THEN 'llm_provider_522'
  WHEN final_reason ILIKE '%retry_budget_exhausted%'
    OR final_reason ILIKE '%failed_exhausted%'
    OR final_reason ILIKE '%max_attempt%' THEN 'retry_budget_exhausted'
  WHEN final_reason ILIKE '%provider_no_quote%' THEN 'provider_no_quote'
  WHEN final_reason ILIKE '%provider_unavailable%'
    OR final_reason ILIKE '%transport%'
    OR final_reason ILIKE '%connection%' THEN 'provider_unavailable'
  WHEN final_reason ILIKE '%provider_error%' THEN 'provider_error'
  WHEN final_reason ILIKE '%no_market_data%' THEN 'no_market_data'
  WHEN final_reason ILIKE '%stale%' THEN 'stale_window_ttl'
  WHEN final_reason ILIKE '%timeout%' THEN 'timeout'
  WHEN final_reason ILIKE '%not_found%' THEN 'not_found'
  WHEN final_reason ILIKE '%semantic%' THEN 'semantic_unavailable'
  ELSE 'other'
END
WHERE final_reason_bucket IS DISTINCT FROM CASE
  WHEN final_reason ILIKE '%522%' THEN 'llm_provider_522'
  WHEN final_reason ILIKE '%retry_budget_exhausted%'
    OR final_reason ILIKE '%failed_exhausted%'
    OR final_reason ILIKE '%max_attempt%' THEN 'retry_budget_exhausted'
  WHEN final_reason ILIKE '%provider_no_quote%' THEN 'provider_no_quote'
  WHEN final_reason ILIKE '%provider_unavailable%'
    OR final_reason ILIKE '%transport%'
    OR final_reason ILIKE '%connection%' THEN 'provider_unavailable'
  WHEN final_reason ILIKE '%provider_error%' THEN 'provider_error'
  WHEN final_reason ILIKE '%no_market_data%' THEN 'no_market_data'
  WHEN final_reason ILIKE '%stale%' THEN 'stale_window_ttl'
  WHEN final_reason ILIKE '%timeout%' THEN 'timeout'
  WHEN final_reason ILIKE '%not_found%' THEN 'not_found'
  WHEN final_reason ILIKE '%semantic%' THEN 'semantic_unavailable'
  ELSE 'other'
END
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(_NORMALIZE_TERMINAL_REASON_BUCKETS_SQL)
    op.execute("ANALYZE worker_queue_terminal_events")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(
        """
        UPDATE worker_queue_terminal_events
        SET final_reason_bucket = CASE
          WHEN final_reason_bucket = 'llm_provider_522' THEN 'provider_llm_522'
          WHEN final_reason_bucket = 'stale_window_ttl' THEN 'stale_window'
          ELSE final_reason_bucket
        END
        WHERE final_reason_bucket IN ('llm_provider_522', 'stale_window_ttl')
        """
    )
    op.execute("ANALYZE worker_queue_terminal_events")
