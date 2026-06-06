"""Add News page search document."""

from __future__ import annotations

from alembic import op

revision = "20260605_0150"
down_revision = "20260605_0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        WITH search_docs AS (
          SELECT
            rows.row_id,
            btrim(
              regexp_replace(
                concat_ws(
                  ' ',
                  rows.headline,
                  rows.summary,
                  rows.source_domain,
                  rows.source_json ->> 'source_domain',
                  rows.source_json ->> 'provider_type',
                  rows.source_json ->> 'source_id',
                  rows.source_json ->> 'source_name',
                  rows.source_json ->> 'source_role',
                  rows.source_json ->> 'trust_tier',
                  rows.source_json ->> 'source_quality_status',
                  source_ids.terms,
                  source_domains.terms,
                  token_terms.terms,
                  fact_terms.terms
                ),
                '\\s+',
                ' ',
                'g'
              )
            ) AS search_text
          FROM news_page_rows AS rows
          LEFT JOIN LATERAL (
            SELECT string_agg(value, ' ' ORDER BY value) AS terms
              FROM jsonb_array_elements_text(COALESCE(rows.source_ids_json, '[]'::jsonb)) AS source_id(value)
             WHERE value <> ''
          ) AS source_ids ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(value, ' ' ORDER BY value) AS terms
              FROM jsonb_array_elements_text(COALESCE(rows.source_domains_json, '[]'::jsonb)) AS source_domain(value)
             WHERE value <> ''
          ) AS source_domains ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(term, ' ' ORDER BY ordinal, field_order) AS terms
              FROM jsonb_array_elements(COALESCE(rows.token_lanes_json, '[]'::jsonb))
                   WITH ORDINALITY AS lane(value, ordinal)
              CROSS JOIN LATERAL (
                VALUES
                  (1, lane.value ->> 'symbol'),
                  (2, lane.value ->> 'target_id'),
                  (3, lane.value ->> 'resolution_status'),
                  (4, lane.value ->> 'target_type'),
                  (5, lane.value ->> 'display_name')
              ) AS fields(field_order, term)
             WHERE term <> ''
          ) AS token_terms ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(term, ' ' ORDER BY ordinal, field_order) AS terms
              FROM jsonb_array_elements(COALESCE(rows.fact_lanes_json, '[]'::jsonb))
                   WITH ORDINALITY AS fact(value, ordinal)
              CROSS JOIN LATERAL (
                VALUES
                  (1, fact.value ->> 'event_type'),
                  (2, fact.value ->> 'status'),
                  (3, fact.value ->> 'claim'),
                  (4, fact.value ->> 'realis')
              ) AS fields(field_order, term)
             WHERE term <> ''
          ) AS fact_terms ON true
        )
        UPDATE news_page_rows AS rows
           SET search_text = COALESCE(search_docs.search_text, '')
          FROM search_docs
         WHERE rows.row_id = search_docs.row_id
        """
    )

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_page_rows_search_text_trgm
              ON news_page_rows USING GIN (search_text gin_trgm_ops)
              WHERE search_text <> ''
            """
        )
        op.execute("ANALYZE news_page_rows")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_page_rows_search_text_trgm")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS search_text")
