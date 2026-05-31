"""Async event-anchor backfill: pending-backfill index + narrow trigger allowance.

The collector hot path can no longer call upstream providers, so it persists
``enriched_events`` rows with ``capture_method = 'unavailable'`` and
``capture_reason = 'pending_backfill'`` whenever no fresh ``market_ticks``
row is on hand. An async worker (``event_anchor_backfill``) catches up by
fetching a quote, inserting the new ``market_ticks`` row, and flipping the
enriched row to ``capture_method = 'tier3_inline'`` /
``capture_reason = 'async_backfill'`` with the freshly written ``tick_id``.

This migration:

* Adds a partial index that lets the worker page through pending rows
  ordered by ``created_at_ms`` ASC without a sequential scan.
* Replaces ``forbid_market_fact_update()`` so ``market_ticks`` remains
  fully append-only (any UPDATE still raises) while ``enriched_events``
  permits exactly the ``pending_backfill -> async_backfill`` transition.
  Every immutable column must remain unchanged across the UPDATE; any
  divergence raises ``market facts are append-only`` like before.
"""

from __future__ import annotations

from alembic import op

revision = "20260516_0049"
down_revision = "20260516_0048"
branch_labels = None
depends_on = None


_TRIGGER_ALLOWS_BACKFILL = """
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  -- Nested IF so OLD/NEW column references are only evaluated on the
  -- right table; otherwise PostgreSQL eagerly resolves all columns in
  -- the boolean expression even on tables that lack them.
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


_TRIGGER_BLANKET_DENY = """
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'market facts are append-only';
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enriched_events_pending_backfill
          ON enriched_events(created_at_ms ASC, event_id ASC, intent_id ASC)
          WHERE capture_method = 'unavailable'
            AND capture_reason = 'pending_backfill'
            AND tick_id IS NULL
        """
    )
    op.execute(_TRIGGER_ALLOWS_BACKFILL)


def downgrade() -> None:
    op.execute(_TRIGGER_BLANKET_DENY)
    op.execute("DROP INDEX IF EXISTS idx_enriched_events_pending_backfill")
