"""Add Token Radar V3 intent and read-model tables."""

from __future__ import annotations

from alembic import op

revision = "20260507_0007"
down_revision = "20260507_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS text_surface TEXT")
    op.execute("ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS span_start BIGINT")
    op.execute("ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS span_end BIGINT")
    op.execute("ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS sentence_id BIGINT")
    op.execute("ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS local_group_key TEXT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_entities_span_lookup
          ON event_entities(event_id, text_surface, sentence_id, span_start)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_evidence (
          evidence_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          source_kind TEXT NOT NULL,
          source_id TEXT NOT NULL,
          evidence_type TEXT NOT NULL,
          raw_value TEXT NOT NULL,
          normalized_symbol TEXT,
          chain_hint TEXT,
          address_hint TEXT,
          provider TEXT,
          provider_ref TEXT,
          text_surface TEXT NOT NULL,
          span_start BIGINT NOT NULL,
          span_end BIGINT NOT NULL,
          sentence_id BIGINT NOT NULL,
          local_group_key TEXT NOT NULL,
          strength TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_evidence_event_source_span
          ON token_evidence(
            event_id, source_kind, source_id, evidence_type, raw_value, span_start, span_end
          )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_evidence_event ON token_evidence(event_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_evidence_symbol ON token_evidence(normalized_symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_evidence_address ON token_evidence(lower(address_hint))")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_intents (
          intent_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          intent_key TEXT NOT NULL,
          construction_policy TEXT NOT NULL,
          primary_evidence_id TEXT REFERENCES token_evidence(evidence_id) ON DELETE SET NULL,
          display_symbol TEXT,
          display_name TEXT,
          chain_hint TEXT,
          address_hint TEXT,
          intent_status TEXT NOT NULL,
          intent_confidence DOUBLE PRECISION NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_token_intents_event_key ON token_intents(event_id, intent_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_intents_event ON token_intents(event_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_intent_evidence (
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          evidence_id TEXT NOT NULL REFERENCES token_evidence(evidence_id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          PRIMARY KEY(intent_id, evidence_id, role)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_intent_resolutions (
          resolution_id TEXT PRIMARY KEY,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
          primary_venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          resolution_status TEXT NOT NULL,
          identity_status TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          resolver_policy_version TEXT NOT NULL,
          reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          decision_time_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_intent_active_resolution
          ON token_intent_resolutions(intent_id)
          WHERE resolution_status <> 'superseded'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_intent_resolutions_event
          ON token_intent_resolutions(event_id, decision_time_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_intent_resolution_candidates (
          candidate_id TEXT PRIMARY KEY,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
          venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          provider TEXT NOT NULL,
          candidate_kind TEXT NOT NULL,
          score DOUBLE PRECISION NOT NULL,
          decision TEXT NOT NULL,
          reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          raw_observation_id TEXT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_intent_candidates_intent
          ON token_intent_resolution_candidates(intent_id, score DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_provider_observations (
          observation_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          request_kind TEXT NOT NULL,
          request_key TEXT NOT NULL,
          chain_hint TEXT,
          address_hint TEXT,
          symbol_hint TEXT,
          status TEXT NOT NULL,
          raw_payload_hash TEXT,
          raw_payload_json JSONB,
          error_code TEXT,
          error_message TEXT,
          observed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_provider_observations_lookup
          ON market_provider_observations(provider, request_kind, request_key, observed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rows (
          row_id TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
          primary_venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          primary_venue_json JSONB,
          attention_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          resolution_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          decision TEXT NOT NULL,
          data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_radar_rows_rank
          ON token_radar_rows(projection_version, "window", scope, lane, computed_at_ms, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rows_latest
          ON token_radar_rows(projection_version, "window", scope, lane, computed_at_ms DESC, rank ASC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_signal_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          row_id TEXT NOT NULL REFERENCES token_radar_rows(row_id) ON DELETE CASCADE,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
          primary_venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          decision_time_ms BIGINT NOT NULL,
          score_version TEXT NOT NULL,
          score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_signal_outcomes (
          outcome_id TEXT PRIMARY KEY,
          snapshot_id TEXT NOT NULL REFERENCES asset_signal_snapshots(snapshot_id) ON DELETE CASCADE,
          horizon TEXT NOT NULL,
          status TEXT NOT NULL,
          entry_snapshot_id TEXT REFERENCES asset_market_snapshots(snapshot_id) ON DELETE SET NULL,
          exit_snapshot_id TEXT REFERENCES asset_market_snapshots(snapshot_id) ON DELETE SET NULL,
          entry_price DOUBLE PRECISION,
          exit_price DOUBLE PRECISION,
          actual_return DOUBLE PRECISION,
          benchmark_return DOUBLE PRECISION,
          abnormal_return DOUBLE PRECISION,
          realized_vol DOUBLE PRECISION,
          normalized_outcome DOUBLE PRECISION,
          market_coverage_status TEXT NOT NULL,
          settled_at_ms BIGINT NOT NULL
        )
        """
    )
    for table in (
        "token_signal_outcomes",
        "token_signal_snapshots",
        "token_market_observations",
        "event_token_attributions",
        "event_token_mentions",
        "token_market_snapshots",
        "tokens",
        "asset_flow_window_snapshots",
        "asset_attention_bucket_authors",
        "asset_attention_buckets",
        "asset_resolution_jobs",
        "asset_resolution_candidates",
        "asset_attributions",
        "asset_mentions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS asset_signal_outcomes")
    op.execute("DROP TABLE IF EXISTS asset_signal_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rows_latest")
    op.execute("DROP INDEX IF EXISTS ux_token_radar_rows_rank")
    op.execute("DROP TABLE IF EXISTS token_radar_rows")
    op.execute("DROP INDEX IF EXISTS idx_market_provider_observations_lookup")
    op.execute("DROP TABLE IF EXISTS market_provider_observations")
    op.execute("DROP INDEX IF EXISTS idx_token_intent_candidates_intent")
    op.execute("DROP TABLE IF EXISTS token_intent_resolution_candidates")
    op.execute("DROP INDEX IF EXISTS idx_token_intent_resolutions_event")
    op.execute("DROP INDEX IF EXISTS ux_token_intent_active_resolution")
    op.execute("DROP TABLE IF EXISTS token_intent_resolutions")
    op.execute("DROP TABLE IF EXISTS token_intent_evidence")
    op.execute("DROP INDEX IF EXISTS idx_token_intents_event")
    op.execute("DROP INDEX IF EXISTS ux_token_intents_event_key")
    op.execute("DROP TABLE IF EXISTS token_intents")
    op.execute("DROP INDEX IF EXISTS idx_token_evidence_address")
    op.execute("DROP INDEX IF EXISTS idx_token_evidence_symbol")
    op.execute("DROP INDEX IF EXISTS idx_token_evidence_event")
    op.execute("DROP INDEX IF EXISTS ux_token_evidence_event_source_span")
    op.execute("DROP TABLE IF EXISTS token_evidence")
    op.execute("DROP INDEX IF EXISTS idx_event_entities_span_lookup")
    op.execute("ALTER TABLE event_entities DROP COLUMN IF EXISTS local_group_key")
    op.execute("ALTER TABLE event_entities DROP COLUMN IF EXISTS sentence_id")
    op.execute("ALTER TABLE event_entities DROP COLUMN IF EXISTS span_end")
    op.execute("ALTER TABLE event_entities DROP COLUMN IF EXISTS span_start")
    op.execute("ALTER TABLE event_entities DROP COLUMN IF EXISTS text_surface")
