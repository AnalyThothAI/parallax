"""Make public News canonical URLs a hard global identity."""

from __future__ import annotations

from alembic import op

revision = "20260529_0123"
down_revision = "20260528_0122"
branch_labels = None
depends_on = None


_CREATE_PUBLIC_URL_MAP_SQL = """
CREATE TEMP TABLE tmp_news_public_url_hard_identity_map ON COMMIT DROP AS
WITH public_items AS (
  SELECT
    items.news_item_id,
    items.canonical_url,
    items.published_at_ms,
    items.fetched_at_ms,
    items.lifecycle_status,
    COALESCE(provider_items.provider_payload_status, 'partial') AS provider_payload_status
  FROM news_items AS items
  LEFT JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = items.provider_item_id
  WHERE items.canonical_url ~* '^https?://'
),
ranked AS (
  SELECT
    public_items.*,
    FIRST_VALUE(public_items.news_item_id) OVER (
      PARTITION BY public_items.canonical_url
      ORDER BY
        CASE WHEN public_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
        CASE WHEN public_items.lifecycle_status = 'processed' THEN 0 ELSE 1 END,
        public_items.published_at_ms DESC,
        public_items.fetched_at_ms DESC,
        public_items.news_item_id ASC
    ) AS representative_news_item_id,
    ROW_NUMBER() OVER (
      PARTITION BY public_items.canonical_url
      ORDER BY
        CASE WHEN public_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
        CASE WHEN public_items.lifecycle_status = 'processed' THEN 0 ELSE 1 END,
        public_items.published_at_ms DESC,
        public_items.fetched_at_ms DESC,
        public_items.news_item_id ASC
    ) AS candidate_rank
  FROM public_items
)
SELECT
  ranked.news_item_id,
  ranked.canonical_url,
  ranked.representative_news_item_id,
  ranked.candidate_rank
FROM ranked
"""

_CREATE_PUBLIC_URL_MAP_INDEXES_SQL = """
CREATE INDEX tmp_news_public_url_hard_identity_item_idx
  ON tmp_news_public_url_hard_identity_map(news_item_id);
CREATE INDEX tmp_news_public_url_hard_identity_representative_idx
  ON tmp_news_public_url_hard_identity_map(representative_news_item_id);
CREATE INDEX tmp_news_public_url_hard_identity_url_idx
  ON tmp_news_public_url_hard_identity_map(canonical_url);
"""

_RELAX_EDGE_MATCH_TYPE_CONSTRAINT_SQL = """
ALTER TABLE news_item_observation_edges
  DROP CONSTRAINT IF EXISTS news_item_observation_edges_match_type_check;
ALTER TABLE news_item_observation_edges
  ADD CONSTRAINT news_item_observation_edges_match_type_check CHECK (
    match_type IN (
      'same_provider_article_id',
      'same_article_url',
      'same_canonical_url',
      'same_content_hash',
      'weak_title_time_source'
    )
  )
"""

_PROMOTE_PUBLIC_URL_REPRESENTATIVES_SQL = """
UPDATE news_items AS items
   SET canonical_item_key = 'canonical-url:' || url_map.canonical_url,
       dedup_key_kind = 'canonical_url',
       dedup_key_confidence = 'strong',
       canonical_policy_version = 'news_canonical_item_v2',
       updated_at_ms = GREATEST(
         COALESCE(items.updated_at_ms, 0),
         (extract(epoch FROM clock_timestamp()) * 1000)::bigint
       )
  FROM tmp_news_public_url_hard_identity_map AS url_map
 WHERE items.news_item_id = url_map.representative_news_item_id
   AND url_map.candidate_rank = 1
"""

_REMAPPING_PUBLIC_URL_EDGES_SQL = """
UPDATE news_item_observation_edges AS edges
   SET news_item_id = url_map.representative_news_item_id,
       match_type = CASE
         WHEN COALESCE(
                NULLIF(provider_items.canonical_url, ''),
                edges.evidence_json #>> '{item_payload,canonical_url}',
                ''
              )
              = url_map.canonical_url
           THEN 'same_canonical_url'
         ELSE edges.match_type
       END,
       match_confidence = CASE
         WHEN COALESCE(
                NULLIF(provider_items.canonical_url, ''),
                edges.evidence_json #>> '{item_payload,canonical_url}',
                ''
              )
              = url_map.canonical_url
           THEN 'strong'
         ELSE edges.match_confidence
       END,
       policy_version = 'news_canonical_item_v2',
       evidence_json = edges.evidence_json || jsonb_build_object(
         'public_url_hard_identity_reason', 'same_canonical_url',
         'public_url_hard_identity_canonical_url', url_map.canonical_url,
         'public_url_hard_identity_representative_news_item_id', url_map.representative_news_item_id,
         'public_url_hard_identity_at_ms', (extract(epoch FROM clock_timestamp()) * 1000)::bigint
       ),
       last_seen_at_ms = GREATEST(
         COALESCE(edges.last_seen_at_ms, 0),
         (extract(epoch FROM clock_timestamp()) * 1000)::bigint
       )
  FROM tmp_news_public_url_hard_identity_map AS url_map,
       news_provider_items AS provider_items
 WHERE edges.news_item_id = url_map.news_item_id
   AND provider_items.provider_item_id = edges.provider_item_id
"""

_DELETE_DUPLICATE_PUBLIC_URL_ITEMS_SQL = """
DELETE FROM news_items AS items
 USING tmp_news_public_url_hard_identity_map AS url_map
 WHERE items.news_item_id = url_map.news_item_id
   AND url_map.news_item_id <> url_map.representative_news_item_id
"""

_REFRESH_NEWS_ITEM_OBSERVATION_SUMMARY_SQL = """
WITH edge_summary AS (
  SELECT
    edges.news_item_id,
    COUNT(*)::int AS duplicate_observation_count,
    COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb) AS source_ids_json,
    COALESCE(jsonb_agg(DISTINCT sources.source_domain ORDER BY sources.source_domain), '[]'::jsonb)
      AS source_domains_json,
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
       provider_article_keys_json = edge_summary.provider_article_keys_json,
       updated_at_ms = GREATEST(
         COALESCE(items.updated_at_ms, 0),
         (extract(epoch FROM clock_timestamp()) * 1000)::bigint
       )
  FROM edge_summary
 WHERE items.news_item_id = edge_summary.news_item_id
"""

_REFRESH_PAGE_ROW_CANONICAL_SUMMARY_SQL = """
UPDATE news_page_rows AS rows
   SET canonical_item_key = items.canonical_item_key,
       duplicate_count = items.duplicate_observation_count,
       source_ids_json = items.source_ids_json,
       source_domains_json = items.source_domains_json,
       provider_article_keys_json = items.provider_article_keys_json
  FROM news_items AS items
 WHERE rows.news_item_id = items.news_item_id
"""

_CLEAR_STORY_READ_MODELS_SQL = """
DELETE FROM news_story_members;
DELETE FROM news_story_groups;
UPDATE news_page_rows SET story_id = NULL, story_json = '{}'::jsonb;
"""

_ENQUEUE_NEWS_REBUILD_TARGETS_SQL = """
WITH clock AS (
  SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
),
targets AS (
  SELECT projections.projection_name,
         items.news_item_id AS target_id,
         GREATEST(COALESCE(items.updated_at_ms, 0), COALESCE(items.fetched_at_ms, 0)) AS source_watermark_ms,
         clock.now_ms
    FROM news_items AS items
    CROSS JOIN clock
    CROSS JOIN (VALUES ('story'), ('page'), ('brief_input')) AS projections(projection_name)
   WHERE items.canonical_url ~* '^https?://'
)
INSERT INTO news_projection_dirty_targets (
  projection_name, target_kind, target_id, "window", dirty_reason, payload_hash,
  source_watermark_ms, priority, due_at_ms, leased_until_ms, lease_owner,
  attempt_count, last_error, first_dirty_at_ms, updated_at_ms
)
SELECT
  targets.projection_name,
  'news_item',
  targets.target_id,
  '',
  'news_public_url_hard_identity_rebuild',
  'news-public-url-hard-identity:' || targets.projection_name || ':' || targets.target_id,
  targets.source_watermark_ms,
  10,
  targets.now_ms,
  NULL,
  NULL,
  0,
  NULL,
  targets.now_ms,
  targets.now_ms
FROM targets
ON CONFLICT (projection_name, target_kind, target_id, "window") DO UPDATE SET
  dirty_reason = EXCLUDED.dirty_reason,
  payload_hash = EXCLUDED.payload_hash,
  source_watermark_ms = GREATEST(
    news_projection_dirty_targets.source_watermark_ms,
    EXCLUDED.source_watermark_ms
  ),
  priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
  due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  last_error = NULL,
  updated_at_ms = EXCLUDED.updated_at_ms
"""

_CREATE_PUBLIC_CANONICAL_URL_INDEX_SQL = """
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_news_items_public_canonical_url
  ON news_items(canonical_url)
  WHERE canonical_url ~* '^https?://'
"""

_CREATE_PROVIDER_CANONICAL_URL_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_provider_items_canonical_url
  ON news_provider_items(canonical_url)
  WHERE canonical_url ~* '^https?://'
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_RELAX_EDGE_MATCH_TYPE_CONSTRAINT_SQL)
    op.execute(_CREATE_PUBLIC_URL_MAP_SQL)
    op.execute(_CREATE_PUBLIC_URL_MAP_INDEXES_SQL)
    op.execute(_PROMOTE_PUBLIC_URL_REPRESENTATIVES_SQL)
    op.execute(_REMAPPING_PUBLIC_URL_EDGES_SQL)
    op.execute(_DELETE_DUPLICATE_PUBLIC_URL_ITEMS_SQL)
    op.execute(_REFRESH_NEWS_ITEM_OBSERVATION_SUMMARY_SQL)
    op.execute(_REFRESH_PAGE_ROW_CANONICAL_SUMMARY_SQL)
    op.execute(_CLEAR_STORY_READ_MODELS_SQL)
    op.execute(_ENQUEUE_NEWS_REBUILD_TARGETS_SQL)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_CREATE_PUBLIC_CANONICAL_URL_INDEX_SQL)
        op.execute(_CREATE_PROVIDER_CANONICAL_URL_INDEX_SQL)
        op.execute("ANALYZE news_items")
        op.execute("ANALYZE news_provider_items")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260529_0123 News public URL hard identity is not safely reversible; "
        "restore from backup or apply an explicit forward repair migration"
    )
