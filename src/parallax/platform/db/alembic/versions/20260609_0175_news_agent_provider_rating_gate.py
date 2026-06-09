"""Hard-cut low provider-rating News agent backlog."""

from alembic import op

revision = "20260609_0175"
down_revision = "20260609_0174"
branch_labels = None
depends_on = None

MIN_PROVIDER_RATING_SCORE = 80
AGENT_ADMISSION_VERSION = "news_item_agent_admission_market_v2"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TEMP TABLE _news_agent_provider_rating_gate_items ON COMMIT DROP AS
        WITH scored AS (
            SELECT items.news_item_id,
                   items.published_at_ms,
                   items.market_scope_json,
                   items.provider_signal_json,
                   CASE
                     WHEN items.provider_signal_json ->> 'score' ~ '^[0-9]+$'
                     THEN (items.provider_signal_json ->> 'score')::integer
                     ELSE NULL
                   END AS provider_rating_score
              FROM news_items AS items
             WHERE items.agent_admission_status IN ('eligible', 'eligible_refresh')
               AND items.agent_admission_version = '{AGENT_ADMISSION_VERSION}'
        )
        SELECT scored.news_item_id,
               scored.published_at_ms,
               scored.market_scope_json,
               scored.provider_signal_json,
               scored.provider_rating_score,
               CASE
                 WHEN scored.provider_rating_score IS NULL THEN 'provider_rating_missing'
                 ELSE 'provider_rating_below_threshold'
               END AS gate_reason
          FROM scored
         WHERE scored.provider_rating_score IS NULL
            OR scored.provider_rating_score < {MIN_PROVIDER_RATING_SCORE}
        """
    )
    op.execute(
        f"""
        WITH runtime_now AS (
            SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
        )
        UPDATE news_items AS items
           SET agent_admission_status = 'needs_review',
               agent_admission_reason = gated.gate_reason,
               agent_admission_json = jsonb_strip_nulls(
                   jsonb_build_object(
                       'eligible', false,
                       'status', 'needs_review',
                       'reason', gated.gate_reason,
                       'representative_news_item_id', items.news_item_id,
                       'version', '{AGENT_ADMISSION_VERSION}',
                       'basis', jsonb_build_object(
                           'market_scope', COALESCE(gated.market_scope_json -> 'scope', '[]'::jsonb),
                           'market_scope_primary', gated.market_scope_json ->> 'primary',
                           'market_scope_basis', COALESCE(gated.market_scope_json -> 'basis', '{{}}'::jsonb),
                           'provider_rating', jsonb_strip_nulls(
                               jsonb_build_object(
                                   'score', gated.provider_rating_score,
                                   'min_score', {MIN_PROVIDER_RATING_SCORE},
                                   'provider', gated.provider_signal_json ->> 'provider',
                                   'status', gated.provider_signal_json ->> 'status',
                                   'method', gated.provider_signal_json ->> 'method'
                               )
                           )
                       )
                   )
               ),
               agent_representative_news_item_id = items.news_item_id,
               agent_admission_computed_at_ms = runtime_now.now_ms,
               updated_at_ms = runtime_now.now_ms
          FROM _news_agent_provider_rating_gate_items AS gated,
               runtime_now
         WHERE items.news_item_id = gated.news_item_id
        """
    )
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS targets
         USING _news_agent_provider_rating_gate_items AS gated
         WHERE targets.projection_name = 'brief_input'
           AND targets.target_kind = 'news_item'
           AND targets.target_id = gated.news_item_id
        """
    )
    op.execute(
        f"""
        UPDATE news_projection_dirty_targets AS targets
           SET source_watermark_ms = GREATEST(
                   COALESCE(NULLIF(items.fetched_at_ms, 0), 0),
                   COALESCE(NULLIF(items.published_at_ms, 0), 0),
                   targets.source_watermark_ms
               )
          FROM news_items AS items
         WHERE targets.projection_name = 'brief_input'
           AND targets.target_kind = 'news_item'
           AND targets.target_id = items.news_item_id
           AND targets.source_watermark_ms = 0
           AND items.agent_admission_status IN ('eligible', 'eligible_refresh')
           AND items.agent_admission_version = '{AGENT_ADMISSION_VERSION}'
           AND items.provider_signal_json ->> 'score' ~ '^[0-9]+$'
           AND (items.provider_signal_json ->> 'score')::integer >= {MIN_PROVIDER_RATING_SCORE}
        """
    )
    op.execute(
        """
        WITH runtime_now AS (
            SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
        )
        INSERT INTO news_projection_dirty_targets (
            projection_name, target_kind, target_id, "window",
            dirty_reason, payload_hash, source_watermark_ms, priority,
            due_at_ms, leased_until_ms, lease_owner, attempt_count, last_error,
            first_dirty_at_ms, updated_at_ms
        )
        SELECT 'page',
               'news_item',
               gated.news_item_id,
               '',
               'news_agent_provider_rating_gate',
               md5(gated.news_item_id || ':news_agent_provider_rating_gate:' || gated.gate_reason),
               COALESCE(gated.published_at_ms, runtime_now.now_ms),
               100,
               runtime_now.now_ms,
               NULL,
               NULL,
               0,
               NULL,
               runtime_now.now_ms,
               runtime_now.now_ms
          FROM _news_agent_provider_rating_gate_items AS gated,
               runtime_now
        ON CONFLICT (projection_name, target_kind, target_id, "window") DO UPDATE
           SET dirty_reason = EXCLUDED.dirty_reason,
               payload_hash = EXCLUDED.payload_hash,
               source_watermark_ms = EXCLUDED.source_watermark_ms,
               priority = EXCLUDED.priority,
               due_at_ms = EXCLUDED.due_at_ms,
               leased_until_ms = NULL,
               lease_owner = NULL,
               attempt_count = 0,
               last_error = NULL,
               updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    pass
