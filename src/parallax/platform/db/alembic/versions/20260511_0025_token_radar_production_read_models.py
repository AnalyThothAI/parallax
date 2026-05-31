"""Add production read models for token radar."""

from __future__ import annotations

from alembic import op

revision = "20260511_0025"
down_revision = "20260511_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_publications (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          published_computed_at_ms BIGINT,
          published_row_count BIGINT NOT NULL DEFAULT 0,
          published_source_rows BIGINT NOT NULL DEFAULT 0,
          published_source_max_received_at_ms BIGINT NOT NULL DEFAULT 0,
          refresh_status TEXT NOT NULL DEFAULT 'missing',
          reason TEXT,
          refresh_computed_at_ms BIGINT,
          refresh_started_at_ms BIGINT,
          refresh_finished_at_ms BIGINT,
          refresh_row_count BIGINT NOT NULL DEFAULT 0,
          refresh_source_rows BIGINT NOT NULL DEFAULT 0,
          error TEXT,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS current_market_field_facts (
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          field_key TEXT NOT NULL,
          value_json JSONB NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          provider TEXT NOT NULL,
          source_observation_id TEXT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(subject_type, subject_id, field_key, source_observation_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_market_price_baselines (
          resolution_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          event_received_at_ms BIGINT NOT NULL,
          first_price_observed_at_ms BIGINT,
          first_price_usd DOUBLE PRECISION,
          first_price_quote DOUBLE PRECISION,
          first_price_quote_symbol TEXT,
          first_price_basis TEXT,
          event_price_observation_id TEXT,
          event_price_observation_kind TEXT,
          event_price_provider TEXT,
          event_price_observed_at_ms BIGINT,
          event_price_usd DOUBLE PRECISION,
          event_price_quote DOUBLE PRECISION,
          event_price_quote_symbol TEXT,
          event_price_basis TEXT,
          before_event_price_observed_at_ms BIGINT,
          before_event_price_usd DOUBLE PRECISION,
          before_event_price_quote DOUBLE PRECISION,
          before_event_price_quote_symbol TEXT,
          before_event_price_basis TEXT,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_publication_read
            ON token_radar_rows(projection_version, "window", scope, computed_at_ms, lane, rank)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_current_market_field_facts_latest
            ON current_market_field_facts(
              subject_type, subject_id, field_key, observed_at_ms DESC, source_observation_id DESC
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_market_price_baselines_resolution
            ON token_market_price_baselines(resolution_id)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_market_price_baselines_resolution")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_current_market_field_facts_latest")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_rows_publication_read")
    op.execute("DROP TABLE IF EXISTS token_market_price_baselines")
    op.execute("DROP TABLE IF EXISTS current_market_field_facts")
    op.execute("DROP TABLE IF EXISTS token_radar_publications")
