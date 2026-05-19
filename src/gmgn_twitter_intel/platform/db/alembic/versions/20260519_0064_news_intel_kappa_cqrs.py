"""Add news intel Kappa/CQRS tables."""

from __future__ import annotations

from alembic import op

revision = "20260519_0064"
down_revision = "20260518_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_sources (
          source_id TEXT PRIMARY KEY,
          provider_type TEXT NOT NULL,
          feed_url TEXT NOT NULL,
          source_domain TEXT NOT NULL,
          source_name TEXT NOT NULL,
          source_role TEXT NOT NULL DEFAULT 'observed_source',
          trust_tier TEXT NOT NULL DEFAULT 'standard',
          managed_by_config BOOLEAN NOT NULL DEFAULT TRUE,
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          refresh_interval_seconds INTEGER NOT NULL DEFAULT 300,
          etag TEXT,
          last_modified TEXT,
          last_fetch_at_ms BIGINT,
          last_success_at_ms BIGINT,
          next_fetch_after_ms BIGINT NOT NULL DEFAULT 0,
          consecutive_failures INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (provider_type IN ('rss', 'atom', 'json_feed')),
          CHECK (
            source_role IN (
              'official_exchange',
              'official_regulator',
              'official_protocol',
              'official_issuer',
              'specialist_media',
              'aggregator',
              'social',
              'observed_source'
            )
          ),
          CHECK (trust_tier IN ('official', 'high', 'standard', 'low'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_sources_due
          ON news_sources(enabled, next_fetch_after_ms, source_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_fetch_runs (
          fetch_run_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          fetched_count INTEGER NOT NULL DEFAULT 0,
          inserted_count INTEGER NOT NULL DEFAULT 0,
          updated_count INTEGER NOT NULL DEFAULT 0,
          duplicate_count INTEGER NOT NULL DEFAULT 0,
          http_status INTEGER,
          error TEXT,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          CHECK (status IN ('running', 'success', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_fetch_runs_source_time
          ON news_fetch_runs(source_id, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_provider_items (
          provider_item_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
          fetch_run_id TEXT REFERENCES news_fetch_runs(fetch_run_id) ON DELETE SET NULL,
          source_item_key TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          raw_payload_json JSONB NOT NULL,
          fetched_at_ms BIGINT NOT NULL,
          UNIQUE (source_id, source_item_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_items (
          news_item_id TEXT PRIMARY KEY,
          provider_item_id TEXT NOT NULL REFERENCES news_provider_items(provider_item_id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
          source_domain TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          body_text TEXT NOT NULL DEFAULT '',
          language TEXT NOT NULL DEFAULT 'en',
          published_at_ms BIGINT NOT NULL,
          fetched_at_ms BIGINT NOT NULL,
          content_hash TEXT NOT NULL,
          title_fingerprint TEXT NOT NULL,
          lifecycle_status TEXT NOT NULL DEFAULT 'raw',
          processing_attempts INTEGER NOT NULL DEFAULT 0,
          processing_error TEXT,
          processed_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed'))
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_news_items_provider_item ON news_items(provider_item_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_items_source_time
          ON news_items(source_id, published_at_ms DESC)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_items_url ON news_items(canonical_url)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_items_content_hash ON news_items(content_hash)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_items_title_trgm
          ON news_items USING GIN (title gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_item_entities (
          entity_id TEXT PRIMARY KEY,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          entity_type TEXT NOT NULL,
          raw_value TEXT NOT NULL,
          normalized_value TEXT NOT NULL,
          chain TEXT,
          span_start INTEGER NOT NULL,
          span_end INTEGER NOT NULL,
          text_surface TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          extraction_policy_version TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_news_item_entities_identity
          ON news_item_entities(
            news_item_id,
            entity_type,
            normalized_value,
            COALESCE(chain, ''),
            span_start,
            span_end
          )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_token_mentions (
          mention_id TEXT PRIMARY KEY,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          entity_id TEXT REFERENCES news_item_entities(entity_id) ON DELETE SET NULL,
          observed_symbol TEXT,
          chain_id TEXT,
          address TEXT,
          resolution_status TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          display_symbol TEXT,
          display_name TEXT,
          reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          candidate_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          evidence_strength TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          created_at_ms BIGINT NOT NULL,
          CHECK (
            resolution_status IN (
              'exact_address',
              'known_symbol',
              'unique_by_context',
              'ambiguous_symbol',
              'unknown_attention',
              'non_crypto',
              'nil'
            )
          ),
          CHECK (evidence_strength IN ('strong', 'medium', 'weak'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_token_mentions_item ON news_token_mentions(news_item_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_token_mentions_target
          ON news_token_mentions(target_type, target_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_token_mentions_status
          ON news_token_mentions(resolution_status)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_story_groups (
          story_id TEXT PRIMARY KEY,
          policy_version TEXT NOT NULL,
          representative_title TEXT NOT NULL,
          canonical_url TEXT,
          first_seen_at_ms BIGINT NOT NULL,
          latest_seen_at_ms BIGINT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 0,
          item_count INTEGER NOT NULL DEFAULT 0,
          token_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          status TEXT NOT NULL DEFAULT 'active',
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (status IN ('active', 'stale'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_story_groups_latest
          ON news_story_groups(latest_seen_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_story_members (
          story_id TEXT NOT NULL REFERENCES news_story_groups(story_id) ON DELETE CASCADE,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          relation TEXT NOT NULL,
          match_reason TEXT NOT NULL,
          match_score DOUBLE PRECISION NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (story_id, news_item_id),
          CHECK (relation IN ('representative', 'same_story'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_news_story_members_item
          ON news_story_members(news_item_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_fact_candidates (
          fact_candidate_id TEXT PRIMARY KEY,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          claim TEXT NOT NULL,
          realis TEXT NOT NULL,
          evidence_quote TEXT NOT NULL,
          evidence_span_start INTEGER NOT NULL,
          evidence_span_end INTEGER NOT NULL,
          source_role TEXT NOT NULL,
          required_slots_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          affected_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          validation_status TEXT NOT NULL,
          rejection_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          extraction_method TEXT NOT NULL,
          policy_version TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            realis IN (
              'actual',
              'scheduled',
              'official_proposed',
              'reported_claim',
              'opinion',
              'rumor',
              'generic',
              'stale'
            )
          ),
          CHECK (validation_status IN ('accepted', 'rejected', 'attention'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_fact_candidates_item ON news_fact_candidates(news_item_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_fact_candidates_status
          ON news_fact_candidates(validation_status)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_page_rows (
          row_id TEXT PRIMARY KEY,
          news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
          story_id TEXT,
          latest_at_ms BIGINT NOT NULL,
          lifecycle_status TEXT NOT NULL,
          headline TEXT NOT NULL,
          summary TEXT NOT NULL,
          source_domain TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          token_lanes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          fact_lanes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          story_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          computed_at_ms BIGINT NOT NULL,
          projection_version TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_latest
          ON news_page_rows(latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_source
          ON news_page_rows(source_domain, latest_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_source")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_latest")
    op.execute("DROP TABLE IF EXISTS news_page_rows")
    op.execute("DROP INDEX IF EXISTS idx_news_fact_candidates_status")
    op.execute("DROP INDEX IF EXISTS idx_news_fact_candidates_item")
    op.execute("DROP TABLE IF EXISTS news_fact_candidates")
    op.execute("DROP INDEX IF EXISTS ux_news_story_members_item")
    op.execute("DROP TABLE IF EXISTS news_story_members")
    op.execute("DROP INDEX IF EXISTS idx_news_story_groups_latest")
    op.execute("DROP TABLE IF EXISTS news_story_groups")
    op.execute("DROP INDEX IF EXISTS idx_news_token_mentions_status")
    op.execute("DROP INDEX IF EXISTS idx_news_token_mentions_target")
    op.execute("DROP INDEX IF EXISTS idx_news_token_mentions_item")
    op.execute("DROP TABLE IF EXISTS news_token_mentions")
    op.execute("DROP INDEX IF EXISTS ux_news_item_entities_identity")
    op.execute("DROP TABLE IF EXISTS news_item_entities")
    op.execute("DROP INDEX IF EXISTS idx_news_items_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_news_items_content_hash")
    op.execute("DROP INDEX IF EXISTS idx_news_items_url")
    op.execute("DROP INDEX IF EXISTS idx_news_items_source_time")
    op.execute("DROP INDEX IF EXISTS ux_news_items_provider_item")
    op.execute("DROP TABLE IF EXISTS news_items")
    op.execute("DROP TABLE IF EXISTS news_provider_items")
    op.execute("DROP INDEX IF EXISTS idx_news_fetch_runs_source_time")
    op.execute("DROP TABLE IF EXISTS news_fetch_runs")
    op.execute("DROP INDEX IF EXISTS idx_news_sources_due")
    op.execute("DROP TABLE IF EXISTS news_sources")
