"""Rekey remaining OpenNews article story identities to v2."""

from __future__ import annotations

from alembic import op

revision = "20260609_0168"
down_revision = "20260609_0167"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH old_opennews_stories AS (
          SELECT items.news_item_id,
                 items.title_fingerprint,
                 items.published_at_ms,
                 items.market_scope_json,
                 ARRAY(
                   SELECT CASE
                            WHEN token.value = 'jpm' THEN 'jpmorgan'
                            WHEN token.value = 'deposits' THEN 'deposit'
                            ELSE token.value
                          END
                     FROM regexp_split_to_table(COALESCE(items.title_fingerprint, ''), '\\s+')
                          WITH ORDINALITY AS token(value, token_order)
                    WHERE token.value <> ''
                      AND token.value NOT IN (
                        'a', 'after', 'amid', 'an', 'and', 'around', 'as', 'at', 'by', 'for',
                        'from', 'in', 'latest', 'market', 'markets', 'move', 'news', 'of',
                        'on', 'said', 'says', 'see', 'the', 'to', 'update', 'weigh', 'weighs',
                        'with'
                      )
                    ORDER BY token.token_order ASC
                 ) AS material_tokens
            FROM news_items AS items
           WHERE items.story_key ~ '^news-story:opennews-article:'
        ),
        story_rekeys AS (
          SELECT news_item_id,
                 title_fingerprint,
                 market_scope_json,
                 material_tokens,
                 floor((published_at_ms + 10800000)::numeric / 21600000)::bigint AS title_bucket,
                 CASE
                   WHEN COALESCE(array_length(material_tokens, 1), 0) >= 5
                     THEN array_to_string(material_tokens[1:8], '-')
                   ELSE regexp_replace(lower(news_item_id), '[^a-z0-9]+', '-', 'g')
                 END AS identity_slug,
                 CASE
                   WHEN COALESCE(array_length(material_tokens, 1), 0) >= 5
                     THEN 'material_title_shifted_time_bucket'
                   ELSE 'weak_item_level'
                 END AS identity_method
            FROM old_opennews_stories
        ),
        updated_items AS (
          UPDATE news_items AS items
             SET story_key = CASE
                   WHEN story_rekeys.identity_method = 'material_title_shifted_time_bucket'
                     THEN 'news-story:title:' || story_rekeys.identity_slug || chr(58) || 't' ||
                          story_rekeys.title_bucket
                   ELSE 'news-story:item:' || story_rekeys.identity_slug
                 END,
                 story_identity_version = 'news_story_identity_v2',
                 story_identity_json = CASE
                   WHEN story_rekeys.identity_method = 'material_title_shifted_time_bucket'
                     THEN jsonb_build_object(
                       'story_key',
                       'news-story:title:' || story_rekeys.identity_slug || chr(58) || 't' || story_rekeys.title_bucket,
                       'confidence', 'medium',
                       'basis', jsonb_build_object(
                         'method', 'material_title_shifted_time_bucket',
                         'fingerprint', story_rekeys.identity_slug,
                         'time_bucket_ms', 21600000,
                         'bucket_offset_ms', 10800000,
                         'bucket', story_rekeys.title_bucket,
                         'normalized_title', story_rekeys.title_fingerprint,
                         'market_scope', COALESCE(story_rekeys.market_scope_json -> 'scope', '[]'::jsonb),
                         'market_scope_primary', COALESCE(story_rekeys.market_scope_json ->> 'primary', '')
                       ),
                       'version', 'news_story_identity_v2'
                     )
                   ELSE jsonb_build_object(
                       'story_key', 'news-story:item:' || story_rekeys.identity_slug,
                       'confidence', 'weak',
                       'basis', jsonb_build_object(
                         'method', 'weak_item_level',
                         'normalized_title', story_rekeys.title_fingerprint,
                         'market_scope', COALESCE(story_rekeys.market_scope_json -> 'scope', '[]'::jsonb),
                         'market_scope_primary', COALESCE(story_rekeys.market_scope_json ->> 'primary', '')
                       ),
                       'version', 'news_story_identity_v2'
                     )
                 END,
                 updated_at_ms = (extract(epoch from now()) * 1000)::bigint
            FROM story_rekeys
           WHERE items.news_item_id = story_rekeys.news_item_id
             AND items.story_key ~ '^news-story:opennews-article:'
          RETURNING items.news_item_id, items.story_key
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
          'news_story_identity_v2_remaining_opennews',
          'news_story_identity_v2_remaining_opennews:' || updated_items.news_item_id || ':' || updated_items.story_key,
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
          attempt_count = 0,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    pass
