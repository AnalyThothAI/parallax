"""Hard-cut Token Radar storage onto partition-safe PostgreSQL tables."""

from __future__ import annotations

from alembic import op

revision = "20260523_0090"
down_revision = "20260523_0089"
branch_labels = None
depends_on = None


MARKET_FACT_UPDATE_TRIGGER = """
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  IF TG_TABLE_NAME = 'enriched_events' THEN
    IF OLD.capture_method = 'unavailable'
       AND OLD.capture_reason = 'pending_backfill'
       AND OLD.tick_observed_at_ms IS NULL
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
           AND NEW.tick_observed_at_ms IS NOT NULL
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
           AND NEW.tick_observed_at_ms IS NULL
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


RADAR_CURRENT_COLUMNS = """
  row_id TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  lane TEXT NOT NULL,
  target_type_key TEXT NOT NULL,
  identity_id TEXT NOT NULL,
  computed_at_ms BIGINT NOT NULL,
  source_max_received_at_ms BIGINT NOT NULL,
  rank BIGINT NOT NULL,
  rank_score DOUBLE PRECISION,
  intent_id TEXT,
  event_id TEXT,
  target_type TEXT,
  target_id TEXT,
  pricefeed_id TEXT,
  intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  primary_venue_json JSONB,
  target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  attention_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  resolution_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  price_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_version TEXT NOT NULL,
  decision TEXT NOT NULL,
  data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload_hash TEXT NOT NULL,
  listed_at_ms BIGINT NOT NULL,
  created_at_ms BIGINT NOT NULL
"""


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_radar_rows CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_current_rows CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_history CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_snapshot_audit CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_target_features CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_dirty_targets CASCADE")
    op.execute("DROP TABLE IF EXISTS market_tick_current CASCADE")
    op.execute("DROP TABLE IF EXISTS enriched_events CASCADE")
    op.execute("DROP TABLE IF EXISTS market_ticks CASCADE")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_ticks (
          observed_at_ms BIGINT NOT NULL,
          tick_id TEXT NOT NULL,
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          chain TEXT,
          token_address TEXT,
          exchange TEXT,
          instrument TEXT,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          source_tier TEXT NOT NULL CHECK (source_tier IN ('tier1_ws', 'tier2_poll', 'tier3_inline')),
          source_provider TEXT NOT NULL
            CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'binance_cex_rest', 'gmgn_dex_quote')),
          received_at_ms BIGINT NOT NULL,
          price_usd NUMERIC NOT NULL CHECK (price_usd > 0),
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          market_cap_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          payload_hash TEXT NOT NULL DEFAULT '',
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (observed_at_ms, tick_id),
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
        ) PARTITION BY RANGE (observed_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_ticks_default
          PARTITION OF market_ticks DEFAULT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_ticks_dedupe
          ON market_ticks(observed_at_ms, target_type, target_id, source_provider)
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
        CREATE TABLE IF NOT EXISTS market_tick_current (
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          tick_observed_at_ms BIGINT NOT NULL,
          tick_id TEXT NOT NULL,
          source_tier TEXT NOT NULL,
          source_provider TEXT NOT NULL,
          chain TEXT,
          token_address TEXT,
          exchange TEXT,
          instrument TEXT,
          pricefeed_id TEXT,
          price_usd NUMERIC NOT NULL CHECK (price_usd > 0),
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          market_cap_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          payload_hash TEXT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id),
          FOREIGN KEY (tick_observed_at_ms, tick_id)
            REFERENCES market_ticks(observed_at_ms, tick_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        ALTER TABLE market_tick_current SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_tick_current_updated
          ON market_tick_current(updated_at_ms DESC, target_type, target_id)
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
          tick_observed_at_ms BIGINT,
          tick_id TEXT,
          tick_lag_ms BIGINT,
          capture_method TEXT NOT NULL CHECK (
            capture_method IN ('tier1_ws', 'tier2_poll', 'tier3_inline', 'unavailable')
          ),
          capture_reason TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY(event_id, intent_id),
          FOREIGN KEY (tick_observed_at_ms, tick_id)
            REFERENCES market_ticks(observed_at_ms, tick_id) ON DELETE RESTRICT,
          CHECK (
            (
              capture_method = 'unavailable'
              AND tick_observed_at_ms IS NULL
              AND tick_id IS NULL
              AND tick_lag_ms IS NULL
            )
            OR (
              capture_method <> 'unavailable'
              AND tick_observed_at_ms IS NOT NULL
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
          ON enriched_events(tick_observed_at_ms, tick_id)
          WHERE tick_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enriched_events_pending_backfill
          ON enriched_events(created_at_ms ASC, event_id ASC, intent_id ASC)
          WHERE capture_method = 'unavailable'
            AND capture_reason = 'pending_backfill'
            AND tick_id IS NULL
        """
    )
    op.execute(MARKET_FACT_UPDATE_TRIGGER)
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

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_target_features (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          latest_event_received_at_ms BIGINT NOT NULL,
          latest_market_observed_at_ms BIGINT,
          attention_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          market_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          credibility_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          rank_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_intent_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_resolution_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          payload_hash TEXT NOT NULL,
          last_scored_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_version, "window", scope, lane, target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_target_features_rank
          ON token_radar_target_features(projection_version, "window", scope, lane, rank_score DESC, identity_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_dirty_targets (
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count BIGINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          PRIMARY KEY (target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_dirty_targets_claim
          ON token_radar_dirty_targets(due_at_ms ASC, updated_at_ms ASC, target_type_key, identity_id)
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS token_radar_current_rows (
          {RADAR_CURRENT_COLUMNS},
          PRIMARY KEY (row_id),
          UNIQUE (projection_version, "window", scope, lane, rank),
          UNIQUE (projection_version, "window", scope, lane, target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_current_rows SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_read
          ON token_radar_current_rows(projection_version, "window", scope, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_target
          ON token_radar_current_rows(target_type, target_id, computed_at_ms DESC)
          WHERE target_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_history (
          row_id TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          recorded_at_ms BIGINT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL,
          previous_rank BIGINT,
          rank BIGINT NOT NULL,
          rank_delta BIGINT,
          rank_score DOUBLE PRECISION,
          decision TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          payload_hash TEXT NOT NULL,
          listed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (row_id, recorded_at_ms)
        ) PARTITION BY RANGE (recorded_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_history_default
          PARTITION OF token_radar_rank_history DEFAULT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_history_read
          ON token_radar_rank_history(projection_version, "window", scope, recorded_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_history_target
          ON token_radar_rank_history(target_type, target_id, recorded_at_ms DESC)
          WHERE target_id IS NOT NULL
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit (
          snapshot_id TEXT NOT NULL,
          audit_reason TEXT NOT NULL CHECK (
            audit_reason IN ('rank_enter', 'rank_exit', 'decision_change', 'manual_sample', 'debug_error')
          ),
          recorded_at_ms BIGINT NOT NULL,
          {RADAR_CURRENT_COLUMNS},
          PRIMARY KEY (snapshot_id, recorded_at_ms)
        ) PARTITION BY RANGE (recorded_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit_default
          PARTITION OF token_radar_snapshot_audit DEFAULT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_snapshot_audit_read
          ON token_radar_snapshot_audit(projection_version, "window", scope, recorded_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_snapshot_audit_settlement
          ON token_radar_snapshot_audit(factor_version, "window", scope, computed_at_ms, target_type, target_id)
          WHERE target_id IS NOT NULL
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260523_0090 token-radar PostgreSQL hard-cut migration is not safely reversible; "
        "rollback requires restoring a pre-migration backup."
    )
