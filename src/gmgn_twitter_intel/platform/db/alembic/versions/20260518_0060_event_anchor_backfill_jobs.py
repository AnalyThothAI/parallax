"""Decouple event-anchor backfill jobs from enriched_events facts.

``enriched_events`` now carries only event-anchor fact lifecycle. The
``event_anchor_backfill_jobs`` table owns due-time, retry, attempt, and
expiry control state for the async worker. Existing stale pending anchors
are hard-cut to terminal ``backfill_expired`` during upgrade; only fresh
pending anchors receive jobs.
"""

from __future__ import annotations

from alembic import op

revision = "20260518_0060"
down_revision = "20260517_0059"
branch_labels = None
depends_on = None

ACTIVE_WINDOW_MS = 300_000

_TRIGGER_EVENT_ANCHOR_LIFECYCLE = """
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  IF TG_TABLE_NAME = 'enriched_events' THEN
    IF OLD.capture_method = 'unavailable'
       AND OLD.capture_reason = 'pending_backfill'
       AND OLD.tick_id IS NULL
       AND OLD.tick_lag_ms IS NULL
       AND NEW.event_id = OLD.event_id
       AND NEW.intent_id = OLD.intent_id
       AND NEW.resolution_id = OLD.resolution_id
       AND NEW.target_type = OLD.target_type
       AND NEW.target_id = OLD.target_id
       AND NEW.t_event_ms = OLD.t_event_ms
       AND NEW.created_at_ms = OLD.created_at_ms
       AND (
         (
           NEW.capture_method IN ('tier1_ws', 'tier2_poll', 'tier3_inline')
           AND NEW.capture_reason = 'async_backfill'
           AND NEW.tick_id IS NOT NULL
           AND NEW.tick_lag_ms IS NOT NULL
           AND NEW.tick_lag_ms >= 0
         )
         OR
         (
           NEW.capture_method = 'unavailable'
           AND NEW.capture_reason IN (
             'backfill_expired',
             'invalid_resolution',
             'missing_market_key',
             'missing_provider',
             'no_market_data',
             'provider_error',
             'provider_no_quote',
             'provider_timeout',
             'rate_limited',
             'unknown'
           )
           AND NEW.tick_id IS NULL
           AND NEW.tick_lag_ms IS NULL
         )
       )
    THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'market facts are append-only';
END;
$$ LANGUAGE plpgsql
"""

_TRIGGER_ALLOWS_ASYNC_BACKFILL_ONLY = """
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  IF TG_TABLE_NAME = 'enriched_events' THEN
    IF OLD.capture_method = 'unavailable'
       AND OLD.capture_reason = 'pending_backfill'
       AND OLD.tick_id IS NULL
       AND NEW.capture_method = 'tier3_inline'
       AND NEW.capture_reason = 'async_backfill'
       AND NEW.tick_id IS NOT NULL
       AND NEW.tick_lag_ms IS NOT NULL
       AND NEW.event_id = OLD.event_id
       AND NEW.intent_id = OLD.intent_id
       AND NEW.resolution_id = OLD.resolution_id
       AND NEW.target_type = OLD.target_type
       AND NEW.target_id = OLD.target_id
       AND NEW.t_event_ms = OLD.t_event_ms
       AND NEW.created_at_ms = OLD.created_at_ms
    THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'market facts are append-only';
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_anchor_backfill_jobs(
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          resolution_id TEXT NOT NULL REFERENCES token_intent_resolutions(resolution_id) ON DELETE CASCADE,
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          t_event_ms BIGINT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'expired', 'failed')),
          next_run_at_ms BIGINT NOT NULL,
          active_until_ms BIGINT NOT NULL,
          attempt_count BIGINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_reason TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(event_id, intent_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_anchor_backfill_jobs_due
          ON event_anchor_backfill_jobs(next_run_at_ms ASC, created_at_ms ASC, event_id ASC, intent_id ASC)
          WHERE status = 'pending'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_anchor_backfill_jobs_expired
          ON event_anchor_backfill_jobs(active_until_ms ASC, created_at_ms ASC, event_id ASC, intent_id ASC)
          WHERE status = 'pending'
        """
    )
    op.execute(_TRIGGER_EVENT_ANCHOR_LIFECYCLE)
    op.execute(
        f"""
        WITH clock AS (
          SELECT ((EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint) AS now_ms
        )
        UPDATE enriched_events
        SET capture_method = 'unavailable',
            capture_reason = 'backfill_expired'
        FROM clock
        WHERE enriched_events.capture_method = 'unavailable'
          AND enriched_events.capture_reason = 'pending_backfill'
          AND enriched_events.tick_id IS NULL
          AND enriched_events.tick_lag_ms IS NULL
          AND enriched_events.created_at_ms < clock.now_ms - {ACTIVE_WINDOW_MS}
        """
    )
    op.execute(
        f"""
        WITH clock AS (
          SELECT ((EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint) AS now_ms
        )
        INSERT INTO event_anchor_backfill_jobs(
          event_id,
          intent_id,
          resolution_id,
          target_type,
          target_id,
          t_event_ms,
          status,
          next_run_at_ms,
          active_until_ms,
          attempt_count,
          last_reason,
          created_at_ms,
          updated_at_ms
        )
        SELECT
          enriched_events.event_id,
          enriched_events.intent_id,
          enriched_events.resolution_id,
          enriched_events.target_type,
          enriched_events.target_id,
          enriched_events.t_event_ms,
          'pending',
          enriched_events.created_at_ms,
          enriched_events.created_at_ms + {ACTIVE_WINDOW_MS},
          0,
          NULL,
          enriched_events.created_at_ms,
          clock.now_ms
        FROM enriched_events
        CROSS JOIN clock
        WHERE enriched_events.capture_method = 'unavailable'
          AND enriched_events.capture_reason = 'pending_backfill'
          AND enriched_events.tick_id IS NULL
          AND enriched_events.tick_lag_ms IS NULL
          AND enriched_events.created_at_ms >= clock.now_ms - {ACTIVE_WINDOW_MS}
        ON CONFLICT(event_id, intent_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(_TRIGGER_ALLOWS_ASYNC_BACKFILL_ONLY)
    op.execute("DROP TABLE IF EXISTS event_anchor_backfill_jobs")
