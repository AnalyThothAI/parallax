"""Hard-cut News story identity v2."""

from __future__ import annotations

from alembic import op

revision = "20260609_0167"
down_revision = "20260609_0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH candidate_inputs AS (
          SELECT items.news_item_id,
                 items.title,
                 items.title_fingerprint,
                 items.published_at_ms,
                 items.market_scope_json,
                 provider_items.canonical_url AS provider_canonical_url,
                 concat_ws(' ', items.title, items.summary, items.body_text) AS text_raw,
                 lower(concat_ws(' ', items.title, items.summary, items.body_text)) AS text_lower,
                 upper(concat_ws(' ', items.title, items.summary, items.body_text)) AS text_upper
            FROM news_items AS items
            JOIN news_provider_items AS provider_items
              ON provider_items.provider_item_id = items.provider_item_id
           WHERE items.story_key ~ '^news-story:opennews-article:'
             AND concat_ws(' ', items.title, items.summary, items.body_text) ~ '[\\(（][A-Z][A-Z0-9]{1,11}[\\)）]'
        ),
        parsed AS (
          SELECT candidate_inputs.*,
                 CASE
                   WHEN text_lower LIKE '%upbit%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?upbit\\.com(/|$)'
                     THEN 'upbit'
                   WHEN text_lower LIKE '%bithumb%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?bithumb\\.com(/|$)'
                     THEN 'bithumb'
                   WHEN text_lower LIKE '%binance%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?binance\\.com(/|$)'
                     THEN 'binance'
                   WHEN text_lower LIKE '%coinbase%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?coinbase\\.com(/|$)'
                     THEN 'coinbase'
                   WHEN text_lower LIKE '%okx%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?okx\\.com(/|$)'
                     THEN 'okx'
                   WHEN text_lower LIKE '%bybit%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?bybit\\.com(/|$)'
                     THEN 'bybit'
                   WHEN text_lower LIKE '%kraken%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?kraken\\.com(/|$)'
                     THEN 'kraken'
                   WHEN text_lower LIKE '%kucoin%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?kucoin\\.com(/|$)'
                     THEN 'kucoin'
                   WHEN text_lower LIKE '%mexc%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?mexc\\.com(/|$)'
                     THEN 'mexc'
                   WHEN text_lower LIKE '%gate%'
                     OR provider_canonical_url ~* '^https?://([^/]+\\.)?gate\\.io(/|$)'
                     THEN 'gate'
                   ELSE ''
                 END AS venue,
                 lower(
                   COALESCE(
                     (regexp_match(title, '[\\(（]([A-Z][A-Z0-9]{1,11})[\\)）]'))[1],
                     (regexp_match(text_raw, '[\\(（]([A-Z][A-Z0-9]{1,11})[\\)）]'))[1],
                     ''
                   )
                 ) AS asset
            FROM candidate_inputs
        ),
        exchange_listing_inputs AS (
          SELECT parsed.*,
                 floor((parsed.published_at_ms + 43200000)::numeric / 86400000)::bigint AS bucket,
                 ARRAY(
                   SELECT quote
                     FROM unnest(ARRAY['btc', 'eth', 'eur', 'krw', 'try', 'usd', 'usdc', 'usdt'])
                          AS quotes(quote)
                   WHERE quote <> parsed.asset
                      AND (
                        parsed.text_upper ~ ('(^|[^A-Z0-9])' || upper(quote) || '([^A-Z0-9]|$)')
                        OR (
                          quote = 'krw'
                          AND (
                            parsed.text_lower LIKE '%원화%'
                            OR parsed.text_lower LIKE '%韩元%'
                            OR parsed.text_lower LIKE '%韓元%'
                          )
                        )
                      )
                    ORDER BY quote ASC
                 ) AS quote_assets
            FROM parsed
           WHERE parsed.venue <> ''
             AND parsed.asset <> ''
             AND parsed.asset NOT IN ('btc', 'eth', 'eur', 'krw', 'try', 'usd', 'usdc', 'usdt')
             AND (
               parsed.text_lower ~ '(list|listed|listing|add|added|addition|trade|trading|market|support)'
               OR parsed.text_lower LIKE '%交易%'
               OR parsed.text_lower LIKE '%上线%'
               OR parsed.text_lower LIKE '%上新%'
               OR parsed.text_lower LIKE '%市场%'
               OR parsed.text_lower LIKE '%支撑%'
               OR parsed.text_lower LIKE '%마켓%'
               OR parsed.text_lower LIKE '%상장%'
               OR parsed.text_lower LIKE '%추가%'
             )
        ),
        story_rekeys AS (
          SELECT news_item_id,
                 venue,
                 asset,
                 bucket,
                 'exchange-listing:' || venue || ':' || asset || ':' ||
                   COALESCE(NULLIF(array_to_string(quote_assets, '-'), ''), 'spot') AS subject,
                 'news-story:event:exchange-listing:' || venue || ':' || asset || ':' ||
                   COALESCE(NULLIF(array_to_string(quote_assets, '-'), ''), 'spot') || chr(58) || 't' || bucket
                   AS new_story_key,
                 title_fingerprint,
                 market_scope_json
            FROM exchange_listing_inputs
        ),
        updated_items AS (
          UPDATE news_items AS items
             SET story_key = story_rekeys.new_story_key,
                 story_identity_version = 'news_story_identity_v2',
                 story_identity_json = jsonb_build_object(
                   'story_key', story_rekeys.new_story_key,
                   'confidence', 'strong',
                   'basis', jsonb_build_object(
                     'method', 'exchange_listing_event_key',
                     'subject', story_rekeys.subject,
                     'time_bucket_ms', 86400000,
                     'bucket_offset_ms', 43200000,
                     'bucket', story_rekeys.bucket,
                     'normalized_title', story_rekeys.title_fingerprint,
                     'market_scope', COALESCE(story_rekeys.market_scope_json -> 'scope', '[]'::jsonb),
                     'market_scope_primary', COALESCE(story_rekeys.market_scope_json ->> 'primary', '')
                   ),
                   'version', 'news_story_identity_v2'
                 ),
                 updated_at_ms = (extract(epoch from now()) * 1000)::bigint
            FROM story_rekeys
           WHERE items.news_item_id = story_rekeys.news_item_id
             AND items.story_key IS DISTINCT FROM story_rekeys.new_story_key
          RETURNING items.news_item_id
        )
        INSERT INTO news_projection_dirty_targets (
          projection_name,
          target_kind,
          target_id,
          "window",
          dirty_reason,
          payload_hash,
          source_watermark_ms,
          priority,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          first_dirty_at_ms,
          updated_at_ms
        )
        SELECT
          'page',
          'news_item',
          updated_items.news_item_id,
          '',
          'news_story_identity_v2',
          'news_story_identity_v2:' || updated_items.news_item_id,
          0,
          100,
          (extract(epoch from now()) * 1000)::bigint,
          NULL,
          NULL,
          0,
          NULL,
          (extract(epoch from now()) * 1000)::bigint,
          (extract(epoch from now()) * 1000)::bigint
        FROM updated_items
        ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
          dirty_reason = EXCLUDED.dirty_reason,
          payload_hash = EXCLUDED.payload_hash,
          priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
          due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    pass
