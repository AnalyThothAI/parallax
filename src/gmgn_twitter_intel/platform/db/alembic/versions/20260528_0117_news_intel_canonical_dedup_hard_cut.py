"""Add News Intel canonical dedup storage."""

from __future__ import annotations

from alembic import op

revision = "20260528_0117"
down_revision = "20260528_0116"
branch_labels = None
depends_on = None


_ADD_PROVIDER_STATUS_CONSTRAINT_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'news_provider_items_payload_status_check'
  ) THEN
    ALTER TABLE news_provider_items
      ADD CONSTRAINT news_provider_items_payload_status_check
      CHECK (provider_payload_status IN ('partial', 'ready'));
  END IF;
END $$;
"""

_ADD_NEWS_ITEMS_DEDUP_CONFIDENCE_CONSTRAINT_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'news_items_dedup_key_confidence_check'
  ) THEN
    ALTER TABLE news_items
      ADD CONSTRAINT news_items_dedup_key_confidence_check
      CHECK (dedup_key_confidence IN ('strong', 'medium', 'weak'));
  END IF;
END $$;
"""

_ADD_NEWS_ITEMS_URL_KIND_CONSTRAINT_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'news_items_url_identity_kind_check'
  ) THEN
    ALTER TABLE news_items
      ADD CONSTRAINT news_items_url_identity_kind_check
      CHECK (url_identity_kind IN ('article', 'live_page', 'homepage', 'aggregator', 'unknown'));
  END IF;
END $$;
"""

_BACKFILL_PROVIDER_ARTICLE_FIELDS_SQL = """
WITH provider_identity AS (
  SELECT
    provider_items.provider_item_id,
    sources.provider_type,
    CASE
      WHEN sources.provider_type = 'opennews' THEN COALESCE(
        NULLIF(provider_items.raw_payload_json ->> 'provider_article_id', ''),
        NULLIF(provider_items.raw_payload_json ->> 'article_id', ''),
        NULLIF(provider_items.raw_payload_json ->> 'id', ''),
        ''
      )
      ELSE COALESCE(
        NULLIF(provider_items.raw_payload_json ->> 'provider_article_id', ''),
        NULLIF(provider_items.raw_payload_json ->> 'article_id', ''),
        NULLIF(provider_items.raw_payload_json ->> 'id', ''),
        NULLIF(provider_items.raw_payload_json ->> 'sourceItemKey', ''),
        NULLIF(provider_items.source_item_key, ''),
        ''
      )
    END AS provider_article_id,
    CASE
      WHEN provider_items.raw_payload_json #>> '{provider_signal,status}' = 'ready' THEN 'ready'
      WHEN provider_items.raw_payload_json #>> '{aiRating,status}' = 'done' THEN 'ready'
      ELSE 'partial'
    END AS provider_payload_status,
    COALESCE(
      CASE
        WHEN provider_items.raw_payload_json ->> 'published_at_ms' ~ '^[0-9]+$'
          THEN NULLIF(provider_items.raw_payload_json ->> 'published_at_ms', '')::bigint
        ELSE NULL
      END,
      CASE
        WHEN provider_items.raw_payload_json ->> 'published_ms' ~ '^[0-9]+$'
          THEN NULLIF(provider_items.raw_payload_json ->> 'published_ms', '')::bigint
        ELSE NULL
      END,
      CASE
        WHEN provider_items.raw_payload_json ->> 'ts' ~ '^[0-9]+$'
          THEN NULLIF(provider_items.raw_payload_json ->> 'ts', '')::bigint
        ELSE NULL
      END
    ) AS provider_published_at_ms,
    provider_items.fetched_at_ms AS provider_observed_at_ms
  FROM news_provider_items AS provider_items
  JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
)
UPDATE news_provider_items AS provider_items
   SET provider_article_id = provider_identity.provider_article_id,
       provider_article_key = CASE
         WHEN provider_identity.provider_article_id <> ''
           THEN provider_identity.provider_type || ':' || provider_identity.provider_article_id
         ELSE ''
       END,
       provider_payload_status = provider_identity.provider_payload_status,
       provider_published_at_ms = provider_identity.provider_published_at_ms,
       provider_observed_at_ms = provider_identity.provider_observed_at_ms
  FROM provider_identity
 WHERE provider_identity.provider_item_id = provider_items.provider_item_id
   AND provider_items.provider_article_key = ''
"""

_CREATE_OBSERVATION_EDGES_SQL = """
CREATE TABLE IF NOT EXISTS news_item_observation_edges (
  provider_item_id TEXT PRIMARY KEY REFERENCES news_provider_items(provider_item_id) ON DELETE CASCADE,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
  provider_article_key TEXT NOT NULL DEFAULT '',
  match_type TEXT NOT NULL,
  match_confidence TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at_ms BIGINT NOT NULL,
  last_seen_at_ms BIGINT NOT NULL,
  CONSTRAINT news_item_observation_edges_match_type_check CHECK (
    match_type IN (
      'same_provider_article_id',
      'same_article_url',
      'same_content_hash',
      'weak_title_time_source'
    )
  ),
  CONSTRAINT news_item_observation_edges_match_confidence_check
    CHECK (match_confidence IN ('strong', 'medium', 'weak'))
)
"""

_CANONICAL_BACKFILL_CTE = """
WITH candidate_inputs AS (
  SELECT
    items.news_item_id,
    provider_items.provider_item_id,
    sources.provider_type,
    sources.source_id,
    sources.source_domain,
    COALESCE(NULLIF(provider_items.provider_article_id, ''), '') AS provider_article_id,
    COALESCE(NULLIF(provider_items.provider_article_key, ''), '') AS provider_article_key,
    COALESCE(NULLIF(items.canonical_url, ''), NULLIF(provider_items.canonical_url, ''), '') AS canonical_url,
    COALESCE(items.title, '') AS title,
    COALESCE(items.summary, '') AS summary,
    COALESCE(items.body_text, '') AS body_text,
    COALESCE(items.language, 'en') AS language,
    COALESCE(NULLIF(items.content_hash, ''), '') AS content_hash,
    COALESCE(NULLIF(items.title_fingerprint, ''), '') AS title_fingerprint,
    COALESCE(items.provider_signal_json, '{}'::jsonb) AS provider_signal_json,
    COALESCE(items.provider_token_impacts_json, '[]'::jsonb) AS provider_token_impacts_json,
    COALESCE(items.published_at_ms, 0) AS published_at_ms,
    COALESCE(items.fetched_at_ms, provider_items.fetched_at_ms, 0) AS fetched_at_ms,
    GREATEST(COALESCE(items.published_at_ms, 0), 0)
      - MOD(GREATEST(COALESCE(items.published_at_ms, 0), 0), 3600000) AS published_hour_ms,
    COALESCE(NULLIF(items.created_at_ms, 0), provider_items.fetched_at_ms, 0) AS first_seen_at_ms,
    COALESCE(NULLIF(items.updated_at_ms, 0), provider_items.fetched_at_ms, 0) AS last_seen_at_ms,
    lower(
      regexp_replace(
        split_part(
          COALESCE(NULLIF(items.canonical_url, ''), NULLIF(provider_items.canonical_url, ''), ''),
          '?',
          1
        ),
        '^https?://[^/]+',
        ''
      )
    ) AS url_path
  FROM news_items AS items
  JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = items.provider_item_id
  JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
),
url_features AS (
  SELECT
    candidate_inputs.*,
    NULLIF(trim(BOTH '/' FROM candidate_inputs.url_path), '') AS normalized_path,
    CASE
      WHEN NULLIF(trim(BOTH '/' FROM candidate_inputs.url_path), '') IS NULL THEN ARRAY[]::text[]
      ELSE regexp_split_to_array(trim(BOTH '/' FROM candidate_inputs.url_path), '/')
    END AS path_segments
  FROM candidate_inputs
),
candidates AS (
  SELECT
    url_features.*,
    CASE
      WHEN url_features.canonical_url ~* '^https?://'
       AND url_features.normalized_path IS NOT NULL
       AND NOT EXISTS (
         SELECT 1
           FROM unnest(url_features.path_segments) AS segment(value)
          WHERE segment.value ~ '(^live$|^live-|live-updates|liveblog|live-blog)'
       )
       AND url_features.normalized_path !~ (
         '^([a-z]{2}(-[a-z]{2})?/)?'
         || '(news|latest|markets|market|blog|research|crypto|business|world|technology|tech|'
         || 'press-release|press-releases)$'
       )
       AND (
         array_length(url_features.path_segments, 1) >= 2
         OR url_features.normalized_path ~ '(^|[-_/])([0-9]{6,}|[0-9a-f]{8,})($|[-_/])'
         OR url_features.normalized_path ~ (
           '(19|20)[0-9]{2}[-_/](0?[1-9]|1[0-2])[-_/]'
           || '(0?[1-9]|[12][0-9]|3[01])'
         )
       )
        THEN true
      ELSE false
    END AS is_article_url
  FROM url_features
),
identified AS (
  SELECT
    candidates.*,
    CASE
      WHEN candidates.content_hash <> ''
        THEN 'content-hash:' || candidates.content_hash
      WHEN candidates.provider_type = 'opennews' AND candidates.provider_article_id <> ''
        THEN 'provider:opennews:' || candidates.provider_article_id
      WHEN candidates.is_article_url
        THEN 'article-url:' || candidates.canonical_url
      ELSE 'weak-title-source-window:'
        || candidates.source_id || ':' || candidates.published_hour_ms::text || ':' || candidates.title_fingerprint
    END AS candidate_key,
    CASE
      WHEN candidates.content_hash <> '' THEN 'content_hash'
      WHEN candidates.provider_type = 'opennews' AND candidates.provider_article_id <> ''
        THEN 'provider_article_id'
      WHEN candidates.is_article_url THEN 'article_url'
      ELSE 'weak_title_time_source'
    END AS dedup_key_kind,
    CASE
      WHEN candidates.content_hash <> '' THEN 'strong'
      WHEN candidates.provider_type = 'opennews' AND candidates.provider_article_id <> '' THEN 'strong'
      WHEN candidates.is_article_url THEN 'strong'
      ELSE 'weak'
    END AS dedup_key_confidence,
    CASE
      WHEN candidates.canonical_url !~* '^https?://' THEN 'unknown'
      WHEN candidates.normalized_path IS NULL THEN 'homepage'
      WHEN EXISTS (
        SELECT 1
          FROM unnest(candidates.path_segments) AS segment(value)
         WHERE segment.value ~ '(^live$|^live-|live-updates|liveblog|live-blog)'
      ) THEN 'live_page'
      WHEN candidates.normalized_path ~ (
        '^([a-z]{2}(-[a-z]{2})?/)?'
        || '(news|latest|markets|market|blog|research|crypto|business|world|technology|tech|'
        || 'press-release|press-releases)$'
      ) THEN 'aggregator'
      WHEN candidates.is_article_url THEN 'article'
      ELSE 'unknown'
    END AS url_identity_kind,
    CASE
      WHEN candidates.content_hash <> '' THEN 'same_content_hash'
      WHEN candidates.provider_type = 'opennews' AND candidates.provider_article_id <> ''
        THEN 'same_provider_article_id'
      WHEN candidates.is_article_url THEN 'same_article_url'
      ELSE 'weak_title_time_source'
    END AS match_type,
    CASE
      WHEN candidates.content_hash <> '' THEN 'strong'
      WHEN candidates.provider_type = 'opennews' AND candidates.provider_article_id <> '' THEN 'strong'
      WHEN candidates.is_article_url THEN 'strong'
      ELSE 'weak'
    END AS match_confidence
  FROM candidates
),
ranked AS (
  SELECT
    identified.*,
    FIRST_VALUE(identified.news_item_id) OVER (
      PARTITION BY identified.candidate_key
      ORDER BY identified.published_at_ms DESC, identified.fetched_at_ms DESC, identified.news_item_id ASC
    ) AS representative_news_item_id,
    ROW_NUMBER() OVER (
      PARTITION BY identified.candidate_key
      ORDER BY identified.published_at_ms DESC, identified.fetched_at_ms DESC, identified.news_item_id ASC
    ) AS candidate_rank
  FROM identified
)
"""

_BACKFILL_NEWS_ITEM_CANONICAL_IDENTITIES_SQL = (
    _CANONICAL_BACKFILL_CTE
    + """
UPDATE news_items AS items
   SET canonical_item_key = ranked.candidate_key,
       dedup_key_kind = ranked.dedup_key_kind,
       dedup_key_confidence = ranked.dedup_key_confidence,
       url_identity_kind = ranked.url_identity_kind,
       canonical_policy_version = 'news_canonical_item_v1'
  FROM ranked
 WHERE items.news_item_id = ranked.news_item_id
   AND ranked.candidate_rank = 1
   AND items.canonical_item_key = ''
"""
)

_BACKFILL_OBSERVATION_EDGES_SQL = (
    _CANONICAL_BACKFILL_CTE
    + """
INSERT INTO news_item_observation_edges (
  provider_item_id, news_item_id, source_id, provider_article_key, match_type,
  match_confidence, policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
)
SELECT
  ranked.provider_item_id,
  ranked.representative_news_item_id,
  ranked.source_id,
  ranked.provider_article_key,
  ranked.match_type,
  ranked.match_confidence,
  'news_canonical_item_v1',
  jsonb_strip_nulls(
    jsonb_build_object(
      'policy_version', 'news_canonical_item_v1',
      'provider_type', ranked.provider_type,
      'source_id', ranked.source_id,
      'provider_article_id', NULLIF(ranked.provider_article_id, ''),
      'provider_article_key', NULLIF(ranked.provider_article_key, ''),
      'canonical_url', NULLIF(ranked.canonical_url, ''),
      'content_hash', NULLIF(ranked.content_hash, ''),
      'title_fingerprint', NULLIF(ranked.title_fingerprint, ''),
      'published_hour_ms', ranked.published_hour_ms,
      'representative_news_item_id', ranked.representative_news_item_id,
      'item_payload', jsonb_build_object(
        'canonical_url', ranked.canonical_url,
        'title', ranked.title,
        'summary', ranked.summary,
        'body_text', ranked.body_text,
        'language', ranked.language,
        'published_at_ms', ranked.published_at_ms,
        'fetched_at_ms', ranked.fetched_at_ms,
        'content_hash', ranked.content_hash,
        'title_fingerprint', ranked.title_fingerprint,
        'provider_signal_json', ranked.provider_signal_json,
        'provider_token_impacts_json', ranked.provider_token_impacts_json,
        'url_identity_kind', ranked.url_identity_kind
      )
    )
  ),
  ranked.first_seen_at_ms,
  ranked.last_seen_at_ms
FROM ranked
ON CONFLICT (provider_item_id) DO UPDATE SET
  news_item_id = EXCLUDED.news_item_id,
  source_id = EXCLUDED.source_id,
  provider_article_key = EXCLUDED.provider_article_key,
  match_type = EXCLUDED.match_type,
  match_confidence = EXCLUDED.match_confidence,
  policy_version = EXCLUDED.policy_version,
  evidence_json = EXCLUDED.evidence_json,
  last_seen_at_ms = EXCLUDED.last_seen_at_ms
"""
)

_DELETE_MERGED_NEWS_ITEMS_SQL = (
    _CANONICAL_BACKFILL_CTE
    + """
DELETE FROM news_items AS items
 USING ranked
 WHERE items.news_item_id = ranked.news_item_id
   AND ranked.news_item_id <> ranked.representative_news_item_id
"""
)

_BACKFILL_NEWS_ITEM_OBSERVATION_SUMMARY_SQL = """
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
       provider_article_keys_json = edge_summary.provider_article_keys_json
  FROM edge_summary
 WHERE items.news_item_id = edge_summary.news_item_id
"""

_BACKFILL_PAGE_ROW_SUMMARY_FIELDS_SQL = """
UPDATE news_page_rows AS rows
   SET canonical_item_key = items.canonical_item_key,
       duplicate_count = items.duplicate_observation_count,
       source_ids_json = items.source_ids_json,
       source_domains_json = items.source_domains_json,
       provider_article_keys_json = items.provider_article_keys_json
  FROM news_items AS items
 WHERE rows.news_item_id = items.news_item_id
"""

_DELETE_STORY_MEMBERS_SQL = "DELETE FROM news_story_members"
_DELETE_STORY_GROUPS_SQL = "DELETE FROM news_story_groups"
_CLEAR_PAGE_STORY_CONTEXT_SQL = "UPDATE news_page_rows SET story_id = NULL, story_json = '{}'::jsonb"
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
   WHERE items.lifecycle_status = 'processed'
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
  'news_canonical_dedup_hard_cut_rebuild',
  'news-canonical-dedup-hard-cut:' || targets.projection_name || ':' || targets.target_id,
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

_DROP_OLD_PROVIDER_ITEM_INDEX_SQL = "DROP INDEX CONCURRENTLY IF EXISTS ux_news_items_provider_item"
_CREATE_CANONICAL_ITEM_INDEX_SQL = """
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_news_items_canonical_item_key
  ON news_items(canonical_item_key)
  WHERE canonical_item_key <> ''
"""
_CREATE_PROVIDER_ARTICLE_KEY_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_provider_items_article_key
  ON news_provider_items(provider_article_key)
  WHERE provider_article_key <> ''
"""
_CREATE_EDGE_ITEM_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_item_observation_edges_item
  ON news_item_observation_edges(news_item_id, source_id)
"""
_CREATE_EDGE_ARTICLE_KEY_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_item_observation_edges_article_key
  ON news_item_observation_edges(provider_article_key)
  WHERE provider_article_key <> ''
"""
_CREATE_PAGE_ROW_CANONICAL_KEY_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_canonical_key
  ON news_page_rows(canonical_item_key)
"""
_CREATE_SOURCE_SYNC_LAG_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_sources_sync_lag
  ON news_sources(enabled, provider_type, sync_high_watermark_ms)
"""

_DROP_CANONICAL_INDEXES_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS ix_news_sources_sync_lag",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_canonical_key",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_news_item_observation_edges_article_key",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_news_item_observation_edges_item",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_news_provider_items_article_key",
    "DROP INDEX CONCURRENTLY IF EXISTS ux_news_items_canonical_item_key",
)
_RESTORE_PROVIDER_ITEM_INDEX_SQL = """
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_news_items_provider_item
  ON news_items(provider_item_id)
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    _add_news_source_sync_columns()
    _add_provider_article_columns()
    op.execute(_ADD_PROVIDER_STATUS_CONSTRAINT_SQL)
    op.execute(_BACKFILL_PROVIDER_ARTICLE_FIELDS_SQL)
    _add_news_item_canonical_columns()
    op.execute(_ADD_NEWS_ITEMS_DEDUP_CONFIDENCE_CONSTRAINT_SQL)
    op.execute(_ADD_NEWS_ITEMS_URL_KIND_CONSTRAINT_SQL)
    op.execute(_CREATE_OBSERVATION_EDGES_SQL)
    op.execute(_BACKFILL_NEWS_ITEM_CANONICAL_IDENTITIES_SQL)
    op.execute(_BACKFILL_OBSERVATION_EDGES_SQL)
    op.execute(_DELETE_MERGED_NEWS_ITEMS_SQL)
    op.execute(_BACKFILL_NEWS_ITEM_OBSERVATION_SUMMARY_SQL)
    _add_page_row_summary_columns()
    op.execute(_BACKFILL_PAGE_ROW_SUMMARY_FIELDS_SQL)
    op.execute(_DELETE_STORY_MEMBERS_SQL)
    op.execute(_DELETE_STORY_GROUPS_SQL)
    op.execute(_CLEAR_PAGE_STORY_CONTEXT_SQL)
    op.execute(_ENQUEUE_NEWS_REBUILD_TARGETS_SQL)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_DROP_OLD_PROVIDER_ITEM_INDEX_SQL)
        op.execute(_CREATE_CANONICAL_ITEM_INDEX_SQL)
        op.execute(_CREATE_PROVIDER_ARTICLE_KEY_INDEX_SQL)
        op.execute(_CREATE_EDGE_ITEM_INDEX_SQL)
        op.execute(_CREATE_EDGE_ARTICLE_KEY_INDEX_SQL)
        op.execute(_CREATE_PAGE_ROW_CANONICAL_KEY_INDEX_SQL)
        op.execute(_CREATE_SOURCE_SYNC_LAG_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for sql in _DROP_CANONICAL_INDEXES_SQL:
            op.execute(sql)
        op.execute(_RESTORE_PROVIDER_ITEM_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    op.execute("DROP TABLE IF EXISTS news_item_observation_edges")
    op.execute("ALTER TABLE news_items DROP CONSTRAINT IF EXISTS news_items_url_identity_kind_check")
    op.execute("ALTER TABLE news_items DROP CONSTRAINT IF EXISTS news_items_dedup_key_confidence_check")
    op.execute("ALTER TABLE news_provider_items DROP CONSTRAINT IF EXISTS news_provider_items_payload_status_check")

    _drop_page_row_summary_columns()
    _drop_news_item_canonical_columns()
    _drop_provider_article_columns()
    _drop_news_source_sync_columns()


def _add_news_source_sync_columns() -> None:
    op.execute("ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS sync_cursor_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS sync_high_watermark_ms BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS sync_overlap_ms BIGINT NOT NULL DEFAULT 900000")
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS sync_diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def _add_provider_article_columns() -> None:
    op.execute("ALTER TABLE news_provider_items ADD COLUMN IF NOT EXISTS provider_article_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE news_provider_items ADD COLUMN IF NOT EXISTS provider_article_key TEXT NOT NULL DEFAULT ''")
    op.execute(
        "ALTER TABLE news_provider_items "
        "ADD COLUMN IF NOT EXISTS provider_payload_status TEXT NOT NULL DEFAULT 'partial'"
    )
    op.execute("ALTER TABLE news_provider_items ADD COLUMN IF NOT EXISTS provider_published_at_ms BIGINT")
    op.execute(
        "ALTER TABLE news_provider_items ADD COLUMN IF NOT EXISTS provider_observed_at_ms BIGINT NOT NULL DEFAULT 0"
    )


def _add_news_item_canonical_columns() -> None:
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS canonical_item_key TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS dedup_key_kind TEXT NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS dedup_key_confidence TEXT NOT NULL DEFAULT 'weak'")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS url_identity_kind TEXT NOT NULL DEFAULT 'unknown'")
    op.execute(
        "ALTER TABLE news_items "
        "ADD COLUMN IF NOT EXISTS canonical_policy_version TEXT NOT NULL DEFAULT 'news_canonical_item_v1'"
    )
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS duplicate_observation_count INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS source_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS provider_article_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def _add_page_row_summary_columns() -> None:
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS canonical_item_key TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS duplicate_count INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        "ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS source_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE news_page_rows "
        "ADD COLUMN IF NOT EXISTS provider_article_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def _drop_page_row_summary_columns() -> None:
    for column_name in (
        "provider_article_keys_json",
        "source_domains_json",
        "source_ids_json",
        "duplicate_count",
        "canonical_item_key",
    ):
        op.execute(f"ALTER TABLE news_page_rows DROP COLUMN IF EXISTS {column_name}")


def _drop_news_item_canonical_columns() -> None:
    for column_name in (
        "provider_article_keys_json",
        "source_domains_json",
        "source_ids_json",
        "duplicate_observation_count",
        "canonical_policy_version",
        "url_identity_kind",
        "dedup_key_confidence",
        "dedup_key_kind",
        "canonical_item_key",
    ):
        op.execute(f"ALTER TABLE news_items DROP COLUMN IF EXISTS {column_name}")


def _drop_provider_article_columns() -> None:
    for column_name in (
        "provider_observed_at_ms",
        "provider_published_at_ms",
        "provider_payload_status",
        "provider_article_key",
        "provider_article_id",
    ):
        op.execute(f"ALTER TABLE news_provider_items DROP COLUMN IF EXISTS {column_name}")


def _drop_news_source_sync_columns() -> None:
    for column_name in (
        "sync_diagnostics_json",
        "sync_overlap_ms",
        "sync_high_watermark_ms",
        "sync_cursor_json",
    ):
        op.execute(f"ALTER TABLE news_sources DROP COLUMN IF EXISTS {column_name}")
