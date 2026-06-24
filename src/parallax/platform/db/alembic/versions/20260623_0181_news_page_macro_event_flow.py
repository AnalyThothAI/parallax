"""Project News page macro event flow fields."""

from __future__ import annotations

from alembic import op

revision = "20260623_0181"
down_revision = "20260616_0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS macro_event_flow_json JSONB")
    op.execute(
        """
        WITH candidate_rows AS (
          SELECT
            rows.row_id,
            rows.market_scope_json ->> 'primary' AS category,
            CASE rows.market_scope_json ->> 'primary'
              WHEN 'macro_policy' THEN '美联储'
              WHEN 'rates' THEN '利率'
              WHEN 'equities' THEN '权益'
              WHEN 'us_equity' THEN '美股'
              WHEN 'fx' THEN '外汇'
              WHEN 'credit' THEN '信用'
              WHEN 'commodities' THEN '商品'
              WHEN 'crypto' THEN '加密'
              WHEN 'geopolitical' THEN '地缘'
              WHEN 'regulation' THEN '监管'
            END AS category_label,
            CASE rows.agent_brief_json ->> 'decision_class'
              WHEN 'driver' THEN 'high'
              WHEN 'watch' THEN 'medium'
              WHEN 'context' THEN 'low'
            END AS severity,
            CASE rows.agent_brief_json ->> 'decision_class'
              WHEN 'driver' THEN '高'
              WHEN 'watch' THEN '中'
              WHEN 'context' THEN '低'
            END AS severity_label,
            CASE rows.agent_brief_json ->> 'decision_class'
              WHEN 'driver' THEN 'mainline_driver'
              WHEN 'watch' THEN 'mainline_watch'
              WHEN 'context' THEN 'mainline_context'
            END AS impact,
            CASE rows.agent_brief_json ->> 'decision_class'
              WHEN 'driver' THEN '改变主线'
              WHEN 'watch' THEN '观察主线'
              WHEN 'context' THEN '不改主线'
            END AS impact_label,
            token_symbols.symbols
          FROM news_page_rows AS rows
          LEFT JOIN LATERAL (
            SELECT string_agg(symbol, ' · ' ORDER BY first_ordinal) AS symbols
              FROM (
                SELECT symbol, min(ordinality) AS first_ordinal
                  FROM (
                    SELECT
                      NULLIF(lane.value ->> 'symbol', '') AS symbol,
                      lane.ordinality
                    FROM jsonb_array_elements(
                      COALESCE(rows.token_lanes_json, '[]'::jsonb)
                    ) WITH ORDINALITY AS lane(value, ordinality)
                  ) AS raw_symbols
                 WHERE symbol IS NOT NULL
                 GROUP BY symbol
                 ORDER BY first_ordinal
                 LIMIT 3
              ) AS ordered_symbols
          ) AS token_symbols ON true
         WHERE rows.macro_event_flow_json IS NULL
           AND rows.projection_version = 'news_page_rows_v5'
           AND COALESCE(rows.agent_brief_json ->> 'status', '') = 'ready'
           AND COALESCE(rows.market_scope_json ->> 'primary', '') IN (
             'macro_policy',
             'rates',
             'equities',
             'us_equity',
             'fx',
             'credit',
             'commodities',
             'crypto',
             'geopolitical',
             'regulation'
           )
           AND COALESCE(rows.agent_brief_json ->> 'decision_class', '') IN ('driver', 'watch', 'context')
        )
        UPDATE news_page_rows AS rows
           SET macro_event_flow_json = jsonb_build_object(
             'window', 'recent',
             'window_label', '近期',
             'severity', candidate_rows.severity,
             'severity_label', candidate_rows.severity_label,
             'category', candidate_rows.category,
             'category_label', candidate_rows.category_label,
             'impact', candidate_rows.impact,
             'impact_label', candidate_rows.impact_label,
             'watch', concat_ws(' · ', NULLIF(candidate_rows.symbols, ''), candidate_rows.category_label)
           )
          FROM candidate_rows
         WHERE rows.row_id = candidate_rows.row_id
        """
    )
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_macro_event_flow_latest
              ON news_page_rows(projection_version, latest_at_ms DESC, row_id DESC)
              WHERE macro_event_flow_json IS NOT NULL
            """
        )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_macro_event_flow_latest")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS macro_event_flow_json")
