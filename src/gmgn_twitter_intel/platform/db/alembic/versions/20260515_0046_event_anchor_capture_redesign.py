"""Add event-anchored market tick capture facts."""

from __future__ import annotations

from alembic import op

revision = "20260515_0046"
down_revision = "20260514_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_ticks (
          tick_id TEXT PRIMARY KEY,
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          chain TEXT,
          token_address TEXT,
          exchange TEXT,
          instrument TEXT,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          source_tier TEXT NOT NULL CHECK (source_tier IN ('tier1_ws', 'tier2_poll', 'tier3_inline')),
          source_provider TEXT NOT NULL CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'okx_cex_rest')),
          observed_at_ms BIGINT NOT NULL,
          received_at_ms BIGINT NOT NULL,
          price_usd NUMERIC NOT NULL CHECK (price_usd > 0),
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          market_cap_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          CHECK (
            (
              target_type = 'chain_token'
              AND chain IS NOT NULL
              AND token_address IS NOT NULL
              AND exchange IS NULL
              AND instrument IS NULL
            )
            OR (
              target_type = 'cex_symbol'
              AND exchange IS NOT NULL
              AND instrument IS NOT NULL
              AND chain IS NULL
              AND token_address IS NULL
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_ticks_dedupe
          ON market_ticks(target_type, target_id, source_provider, observed_at_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_ticks_target_observed
          ON market_ticks(target_type, target_id, observed_at_ms DESC, tick_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_ticks_received
          ON market_ticks(received_at_ms DESC, tick_id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_capture_tier (
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
          reason TEXT NOT NULL CHECK (reason IN ('ws_subscribed', 'batch_poll', 'inline_only')),
          score NUMERIC NOT NULL DEFAULT 0,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(target_type, target_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS enriched_events (
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          resolution_id TEXT NOT NULL REFERENCES token_intent_resolutions(resolution_id) ON DELETE CASCADE,
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          t_event_ms BIGINT NOT NULL,
          tick_id TEXT REFERENCES market_ticks(tick_id) ON DELETE RESTRICT,
          tick_lag_ms BIGINT,
          capture_method TEXT NOT NULL CHECK (
            capture_method IN ('tier1_ws', 'tier2_poll', 'tier3_inline', 'unavailable')
          ),
          capture_reason TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY(event_id, intent_id),
          CHECK (
            (
              capture_method = 'unavailable'
              AND tick_id IS NULL
              AND tick_lag_ms IS NULL
            )
            OR (
              capture_method <> 'unavailable'
              AND tick_id IS NOT NULL
              AND tick_lag_ms IS NOT NULL
              AND tick_lag_ms >= 0
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enriched_events_event
          ON enriched_events(event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enriched_events_target_time
          ON enriched_events(target_type, target_id, t_event_ms DESC, event_id, intent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enriched_events_tick
          ON enriched_events(tick_id)
          WHERE tick_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_market_fact_update()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'market facts are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER forbid_market_ticks_update
          BEFORE UPDATE ON market_ticks
          FOR EACH ROW
          EXECUTE FUNCTION forbid_market_fact_update()
        """
    )
    op.execute(
        """
        CREATE TRIGGER forbid_enriched_events_update
          BEFORE UPDATE ON enriched_events
          FOR EACH ROW
          EXECUTE FUNCTION forbid_market_fact_update()
        """
    )
    op.execute("DROP TABLE IF EXISTS price_observations CASCADE")


def downgrade() -> None:
    raise RuntimeError(
        "20260515_0046 hard-cut migration is not safely reversible; "
        "rollback requires restoring a pre-migration backup."
    )
