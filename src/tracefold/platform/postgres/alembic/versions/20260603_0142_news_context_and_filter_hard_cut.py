"""Hard-cut retired News context storage and private page filters."""

from __future__ import annotations

from alembic import op

revision = "20260603_0142"
down_revision = "20260601_0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        """
        UPDATE news_provider_items AS provider_items
           SET provider_article_id = '',
               provider_article_key = ''
          FROM news_sources AS sources
         WHERE sources.source_id = provider_items.source_id
           AND lower(trim(sources.provider_type)) <> 'opennews'
           AND (
             provider_items.provider_article_id <> ''
             OR provider_items.provider_article_key <> ''
           )
        """
    )
    op.execute(
        """
        UPDATE news_item_observation_edges AS edges
           SET provider_article_key = '',
               evidence_json = evidence_json - 'provider_article_id' - 'provider_article_key'
          FROM news_sources AS sources
         WHERE sources.source_id = edges.source_id
           AND lower(trim(sources.provider_type)) <> 'opennews'
           AND edges.provider_article_key <> ''
        """
    )
    op.execute(
        """
        WITH edge_summary AS (
          SELECT
            edges.news_item_id,
            COUNT(*)::int AS duplicate_observation_count,
            COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb) AS source_ids_json,
            COALESCE(
              jsonb_agg(DISTINCT sources.source_domain ORDER BY sources.source_domain),
              '[]'::jsonb
            ) AS source_domains_json,
            COALESCE(
              jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                FILTER (WHERE edges.provider_article_key <> ''),
              '[]'::jsonb
            ) AS provider_article_keys_json
          FROM news_item_observation_edges AS edges
          JOIN news_sources AS sources ON sources.source_id = edges.source_id
          GROUP BY edges.news_item_id
        )
        UPDATE news_items AS items
           SET duplicate_observation_count = edge_summary.duplicate_observation_count,
               source_ids_json = edge_summary.source_ids_json,
               source_domains_json = edge_summary.source_domains_json,
               provider_article_keys_json = edge_summary.provider_article_keys_json
          FROM edge_summary
         WHERE items.news_item_id = edge_summary.news_item_id
        """
    )
    op.execute(
        """
        UPDATE news_page_rows AS rows
           SET provider_article_keys_json = items.provider_article_keys_json
          FROM news_items AS items
         WHERE rows.news_item_id = items.news_item_id
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_news_context_items_source_effective_time")
    op.execute("DROP INDEX IF EXISTS idx_news_context_items_source_effective_time")
    op.execute("DROP INDEX IF EXISTS news_context_items_source_published_idx")
    op.execute("DROP INDEX IF EXISTS news_context_items_parent_published_idx")
    op.execute("DROP TABLE IF EXISTS news_context_items")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS context_policy_json")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_provider_type_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_source_role_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_trust_tier_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_content_class_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_decision_class_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_coverage_tags_gin")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_content_tags_gin")
    op.execute("ANALYZE news_sources")


def downgrade() -> None:
    """No downgrade for hard-cut removal of retired News context/filter storage."""
