# News Intel Dedup Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治 News Intel 的 provider/WS/REST 重复、container URL 过度合并、disabled source serving 污染和 item-scoped agent brief 成本问题。

**Architecture:** Hard cut：`news_items` 改为 canonical item 语义，raw `news_provider_items` 通过 observation edge 连接到 canonical item；story/page/brief 只消费 canonical item。OpenNews WS 与 REST 都作为 at-least-once provider input，REST 使用 source-level high watermark + overlap bounded page scan；不保留 legacy `news_item_id` lookup、双写、双读或旧 page row 兼容路径。

**Atomic cutover constraint:** storage migration and canonical writer cutover are one deployable slice. Dropping `ux_news_items_provider_item` without also moving the writer off `ON CONFLICT(provider_item_id)` breaks PostgreSQL conflict inference. Do not merge or validate the migration as a standalone deployable PR.

**Tech Stack:** Python 3.12, PostgreSQL, Alembic, psycopg, FastAPI, pytest, ruff, existing worker dirty-target queue.

---

## Pre-flight

- [x] Spec is approved: `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`.
- [x] Implementation runs in worktree `.worktrees/news-intel-dedup-root-fix/` on branch `codex/news-intel-dedup-root-fix`.
- [x] Verify active runtime config before real-data diagnostics: `uv run parallax config`; report only paths and booleans.
- [x] Baseline `uv run ruff check .` passes.
- [x] Baseline `uv run pytest tests/unit/domains/news_intel tests/unit/integrations/news_feeds tests/integration/domains/news_intel tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_boundaries.py` passes.
- [x] Hard-cut gate: no legacy item-id resolver, no dual API read path, no old page-row fallback, no frontend-only dedup, no scheduled full-table scanner.
- [x] Atomic writer gate: the same green checkpoint that introduces `ux_news_items_canonical_item_key` also proves `NewsRepository` no longer writes `news_items` through `ON CONFLICT(provider_item_id)`.

Known-failing baseline tests: none expected. If baseline fails, record exact failing tests before editing.

## File-level edits

### Storage / migrations

- Create `src/parallax/platform/db/alembic/versions/20260528_0117_news_intel_canonical_dedup_hard_cut.py`.

  Alembic header:

  ```python
  revision = "20260528_0117"
  down_revision = "20260528_0116"
  branch_labels = None
  depends_on = None
  ```

  Add source sync state:

  ```sql
  ALTER TABLE news_sources
    ADD COLUMN IF NOT EXISTS sync_cursor_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_sources
    ADD COLUMN IF NOT EXISTS sync_high_watermark_ms BIGINT NOT NULL DEFAULT 0;
  ALTER TABLE news_sources
    ADD COLUMN IF NOT EXISTS sync_overlap_ms BIGINT NOT NULL DEFAULT 900000;
  ALTER TABLE news_sources
    ADD COLUMN IF NOT EXISTS sync_diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ```

  Add provider article identity on raw observations:

  ```sql
  ALTER TABLE news_provider_items
    ADD COLUMN IF NOT EXISTS provider_article_id TEXT NOT NULL DEFAULT '';
  ALTER TABLE news_provider_items
    ADD COLUMN IF NOT EXISTS provider_article_key TEXT NOT NULL DEFAULT '';
  ALTER TABLE news_provider_items
    ADD COLUMN IF NOT EXISTS provider_payload_status TEXT NOT NULL DEFAULT 'partial';
  ALTER TABLE news_provider_items
    ADD COLUMN IF NOT EXISTS provider_published_at_ms BIGINT;
  ALTER TABLE news_provider_items
    ADD COLUMN IF NOT EXISTS provider_observed_at_ms BIGINT NOT NULL DEFAULT 0;
  ALTER TABLE news_provider_items
    ADD CONSTRAINT news_provider_items_payload_status_check
    CHECK (provider_payload_status IN ('partial', 'ready'));
  ```

  Backfill provider article fields from existing observations:

  ```sql
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
      END AS provider_payload_status
      -- plus provider_published_at_ms/provider_observed_at_ms extraction as in migration.
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
         provider_payload_status = CASE
           WHEN provider_identity.provider_payload_status = 'ready' THEN 'ready'
           ELSE provider_items.provider_payload_status
         END,
         provider_observed_at_ms = provider_items.fetched_at_ms
    FROM provider_identity
   WHERE provider_identity.provider_item_id = provider_items.provider_item_id
     AND provider_items.provider_article_key = '';
  ```

  Backfill canonical item fields and observation ledger before creating the canonical unique index:

  - Existing `news_items` must not remain with `canonical_item_key = ''` after the migration.
  - Existing `news_items` must get at least one `news_item_observation_edges` row when `provider_item_id` points at a raw observation.
  - SQL backfill priority is conservative and deterministic: OpenNews official `provider_article_id/article_id/id` > HTTP article-like URL > `content_hash` > weak source/hour/title fallback.
  - If historical rows collide on a canonical key, backfill creates observation edges to a deterministic representative, refreshes summaries, and deletes merged duplicate `news_items`; it does not create `legacy-news-item:*` identities or a compatibility read path.
  - Migration tests must prove the canonical unique index can be created, OpenNews `sourceItemKey` is not promoted to provider article id, and no serving-visible zero-key/zero-edge item remains immediately after upgrade.

  Add canonical item fields to `news_items`:

  ```sql
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS canonical_item_key TEXT NOT NULL DEFAULT '';
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS dedup_key_kind TEXT NOT NULL DEFAULT 'unknown';
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS dedup_key_confidence TEXT NOT NULL DEFAULT 'weak';
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS url_identity_kind TEXT NOT NULL DEFAULT 'unknown';
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS canonical_policy_version TEXT NOT NULL DEFAULT 'news_canonical_item_v1';
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS duplicate_observation_count INTEGER NOT NULL DEFAULT 1;
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS source_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS provider_article_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_items
    ADD CONSTRAINT news_items_dedup_key_confidence_check
    CHECK (dedup_key_confidence IN ('strong', 'medium', 'weak'));
  ALTER TABLE news_items
    ADD CONSTRAINT news_items_url_identity_kind_check
    CHECK (url_identity_kind IN ('article', 'live_page', 'homepage', 'aggregator', 'unknown'));
  ```

  Add observation edge table:

  ```sql
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
    CHECK (
      match_type IN (
        'same_provider_article_id',
        'same_article_url',
        'same_content_hash',
        'weak_title_time_source'
      )
    ),
    CHECK (match_confidence IN ('strong', 'medium', 'weak'))
  );
  ```

  Add public row duplicate/source summary fields:

  ```sql
  ALTER TABLE news_page_rows
    ADD COLUMN IF NOT EXISTS canonical_item_key TEXT NOT NULL DEFAULT '';
  ALTER TABLE news_page_rows
    ADD COLUMN IF NOT EXISTS duplicate_count INTEGER NOT NULL DEFAULT 1;
  ALTER TABLE news_page_rows
    ADD COLUMN IF NOT EXISTS source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_page_rows
    ADD COLUMN IF NOT EXISTS source_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_page_rows
    ADD COLUMN IF NOT EXISTS provider_article_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ```

  Add indexes in `autocommit_block()`:

  ```sql
  DROP INDEX CONCURRENTLY IF EXISTS ux_news_items_provider_item;
  CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_news_items_canonical_item_key
    ON news_items(canonical_item_key)
    WHERE canonical_item_key <> '';
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_provider_items_article_key
    ON news_provider_items(provider_article_key)
    WHERE provider_article_key <> '';
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_item_observation_edges_item
    ON news_item_observation_edges(news_item_id, source_id);
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_item_observation_edges_article_key
    ON news_item_observation_edges(provider_article_key)
    WHERE provider_article_key <> '';
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_canonical_key
    ON news_page_rows(canonical_item_key);
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_sources_sync_lag
    ON news_sources(enabled, provider_type, sync_high_watermark_ms);
  ```

  Downgrade drops new indexes, table, constraints, and columns. Downgrade is destructive for hard-cut canonical fields and is only safe before canonical rebuild.

### `src/parallax/domains/news_intel/services/news_url_identity.py`

- Create focused URL identity classifier.

  Public API:

  ```python
  URL_IDENTITY_KINDS = ("article", "live_page", "homepage", "aggregator", "unknown")

  def url_identity_kind(canonical_url: str) -> str:
      """Return article/live_page/homepage/aggregator/unknown for a canonical URL."""

  def is_article_identity(canonical_url: str, *, kind: str | None = None) -> bool:
      """True only when URL can participate in hard URL dedup by itself."""
  ```

- Rules:
  - Empty URL or non-http `opennews://item/<id>` is `unknown`.
  - `path in {"", "/"}` is `homepage`.
  - Path containing `/live`, `/live/`, `live-updates`, `liveblog`, `live-blog` is `live_page`.
  - Known generic publisher domains with root-like paths are `aggregator`.
  - HTTP URL with at least two non-empty path segments or an article id/date slug is `article`.

- Tests:
  - Add `tests/unit/domains/news_intel/test_news_url_identity.py`.
  - Test TASS root, AFP root, NYT live URL, OpenNews fallback URL, Binance announcement article URL.

### `src/parallax/domains/news_intel/services/news_canonical_identity.py`

- Create deterministic canonical identity service.

  Public API:

  ```python
  CANONICAL_POLICY_VERSION = "news_canonical_item_v1"

  @dataclass(frozen=True, slots=True)
  class CanonicalIdentity:
      canonical_item_key: str
      news_item_id: str
      dedup_key_kind: str
      dedup_key_confidence: str
      url_identity_kind: str
      match_type: str
      match_confidence: str
      evidence: dict[str, Any]

  def provider_article_key(*, provider_type: str, provider_article_id: str) -> str:
      """Return '<provider_type>:<provider_article_id>' when both values are present."""

  def canonical_identity_for_observation(
      *,
      provider_type: str,
      source_id: str,
      provider_article_id: str,
      canonical_url: str,
      content_hash: str,
      title_fingerprint: str,
      published_at_ms: int,
  ) -> CanonicalIdentity:
      """Choose provider article id, article URL, or content hash as the canonical hard key."""

  def stable_news_item_id(canonical_item_key: str) -> str:
      """Return 'news-item-' plus sha256(canonical_item_key) first 32 hex chars."""
  ```

- Key priority:
  - OpenNews with non-empty `provider_article_id`: `provider:opennews:<id>`, strong, `same_provider_article_id`.
  - Article-like URL: `article-url:<canonical_url>`, strong, `same_article_url`.
  - Non-empty content hash: `content-hash:<hash>`, strong, `same_content_hash`.
  - Final weak fallback: `weak-title-source-window:<source_id>:<published_hour_ms>:<title_fingerprint>`, weak, `weak_title_time_source`; fallback rows must still produce diagnostics and not exact story merge.

- Tests:
  - `test_opennews_id_wins_over_url`.
  - `test_container_url_does_not_win_over_content_hash`.
  - `test_article_url_wins_when_provider_id_missing`.
  - `test_stable_news_item_id_order_independent`.

### `src/parallax/domains/news_intel/types/source_provider.py`

- Lines 41-57: keep `NewsProviderObservation` as normalized content plus raw payload; provider article identity is carried in `raw_payload` from provider wiring and materialized by `NewsRepository.upsert_provider_item`.
- Lines 72-81: keep `NewsProviderFetchResult.next_cursor` and make OpenNews fetch worker persistence use it; no compatibility wrapper.

### `src/parallax/integrations/news_feeds/feed_client.py`

- Lines 10-18: add cursor to `FeedFetchResult`.

  Signature:

  ```python
  @dataclass(frozen=True, slots=True)
  class FeedFetchResult:
      status_code: int
      entries: list[dict[str, Any]] = field(default_factory=list)
      etag: str | None = None
      last_modified: str | None = None
      not_modified: bool = False
      feed: dict[str, Any] = field(default_factory=dict)
      next_cursor: dict[str, Any] = field(default_factory=dict)
  ```

### `src/parallax/integrations/news_feeds/provider_registry.py`

- Lines 13-49, 58-127, 150-168: pass `cursor` through the registry contract.

  Updated signatures:

  ```python
  def fetch(
      self,
      *,
      feed_url: str,
      provider_type: str,
      etag: str | None = None,
      last_modified: str | None = None,
      source: Mapping[str, Any] | None = None,
      limit: int | None = None,
      cursor: Mapping[str, Any] | None = None,
  ) -> FeedFetchResult:
  ```

- RSS/CryptoPanic providers ignore cursor by contract and do not create fallback behavior.
- `OpenNewsNewsFeedProvider.fetch` forwards `cursor` to `OpenNewsFeedClient.fetch`.

### `src/parallax/integrations/news_feeds/opennews_client.py`

- Lines 28-64: update `fetch` to accept cursor.

  Signature:

  ```python
  def fetch(
      self,
      url: str,
      *,
      source: dict[str, Any] | None = None,
      limit: int | None = None,
      cursor: Mapping[str, Any] | None = None,
  ) -> FeedFetchResult:
  ```

- Lines 69-174: `_fetch_async` merges WS and REST entries by OpenNews article id and returns `next_cursor`.
- Lines 176-203: replace single REST request with bounded page scan.

  New signatures:

  ```python
  async def _fetch_rest_entries(
      self,
      *,
      subscription: Mapping[str, Any],
      policy: Mapping[str, Any],
      limit: int | None,
      cursor: Mapping[str, Any],
  ) -> tuple[list[dict[str, Any]], dict[str, Any]]:

  def _rest_search_body(
      *,
      subscription: Mapping[str, Any],
      policy: Mapping[str, Any],
      limit: int | None,
      page: int,
  ) -> dict[str, Any]:
  ```

- Page scan policy:
  - `rest_limit = min(policy.rest_limit, 100)`.
  - `max_pages = policy.max_rest_pages` default 5.
  - `overlap_ms = max(policy.overlap_ms, 10 * 60 * 1000)` default 15 minutes.
  - `previous_high_watermark_ms = cursor.high_watermark_ms` default 0.
  - Stop after an empty page, after `max_pages`, or when page oldest `published_at_ms < previous_high_watermark_ms - overlap_ms`.
  - `next_cursor.high_watermark_ms = max(previous_high_watermark_ms, max_observed_published_at_ms)`.
  - `next_cursor` includes `pages_scanned`, `rest_received`, `stop_reason`, `overlap_ms`, `oldest_seen_ms`.

- Lines 411-439: `_entry_from_params` adds OpenNews identity fields into each entry only when official `provider_article_id/article_id/id` is present. `sourceItemKey` is observation identity only, never provider article identity:

  ```python
  "id": article_id,
  "provider_article_id": article_id,
  "provider_article_key": f"opennews:{article_id}",
  ```

- Lines 446-460: `_merge_entry` remains status-aware; add test that ready AI payload is not overwritten by later partial payload.

- Tests in `tests/unit/integrations/news_feeds/test_opennews_client.py`:
  - `test_opennews_rest_scans_pages_until_overlap_stop`.
  - `test_opennews_rest_returns_high_watermark_cursor_after_commit_candidate`.
  - `test_opennews_ready_payload_not_overwritten_by_later_partial`.
  - Update existing REST test expected body to include page 1 and cursor diagnostics.

### `src/parallax/app/runtime/provider_wiring/news.py`

- Lines 53-79: pass OpenNews cursor into registry; map normalized entries to `NewsProviderObservation` without inventing provider article identity. OpenNews identity fields stay in `raw_payload` and are materialized from official id fields by the repository.

- `NewsProviderFetchResult.next_cursor` is set from `feed_result.next_cursor`.
- Tests:
  - `tests/unit/integrations/news_feeds/test_provider_registry.py::test_registry_passes_opennews_cursor`.
  - `tests/unit/domains/news_intel/test_feed_item_normalizer.py` updated for provider article fields.

### `src/parallax/domains/news_intel/repositories/news_repository.py`

- Lines 73-177: include sync columns in `upsert_source` payload only when source config explicitly sets them; default DB values remain canonical.
- Lines 179-224: after disabling unconfigured sources, call new helper `delete_page_rows_for_disabled_sources(commit=False)` and return disabled ids in a compact result payload or expose a separate repository method used by `NewsFetchWorker`.
- Lines 437-500: extend `upsert_provider_item` signature.

  Signature:

  ```python
  def upsert_provider_item(
      self,
      *,
      source_id: str,
      fetch_run_id: str,
      source_item_key: str,
      canonical_url: str,
      payload_hash: str,
      raw_payload: Mapping[str, Any] | None = None,
      raw_payload_json: Mapping[str, Any] | None = None,
      fetched_at_ms: int,
      provider_article_id: str = "",
      provider_article_key: str = "",
      provider_payload_status: str = "partial",
      provider_published_at_ms: int | None = None,
      commit: bool = True,
  ) -> dict[str, Any]:
  ```

- Replace `upsert_news_item` with `upsert_canonical_news_item`; do not keep an `upsert_news_item` compatibility wrapper.

  Signature:

  ```python
  def upsert_canonical_news_item(
      self,
      *,
      provider_item_id: str,
      source_id: str,
      source_domain: str,
      canonical_item_key: str,
      dedup_key_kind: str,
      dedup_key_confidence: str,
      url_identity_kind: str,
      match_type: str,
      match_confidence: str,
      match_evidence: Mapping[str, Any],
      canonical_url: str,
      title: str,
      summary: str = "",
      body_text: str = "",
      language: str = "en",
      published_at_ms: int | None = None,
      fetched_at_ms: int,
      content_hash: str,
      title_fingerprint: str,
      now_ms: int,
      provider_article_key: str = "",
      provider_signal: Mapping[str, Any] | None = None,
      provider_token_impacts: Sequence[Mapping[str, Any]] | None = None,
      commit: bool = True,
  ) -> dict[str, Any]:
  ```

- Upsert algorithm:
  - Look up `news_items` by `canonical_item_key`.
  - If missing, insert deterministic `news_item_id = stable_news_item_id(canonical_item_key)`.
  - If present, merge representative payload only when incoming payload outranks current payload:
    - ready provider signal outranks partial.
    - newer `published_at_ms` outranks older only when current is partial.
    - non-fallback URL outranks `opennews://item/<id>`.
    - deterministic tie-breaker keeps the existing representative; ingestion order must not change canonical content when rank is equal.
  - If the same `provider_item_id` moves from an old canonical key to a stronger new canonical key, atomically remap the edge to the new canonical item and refresh both old and new summaries.
  - A canonical item with zero observation edges after remap is deleted or made non-serving in the same transaction; zero-edge canonical rows are not valid serving facts.
  - Insert or update `news_item_observation_edges(provider_item_id)`.
  - Recompute `duplicate_observation_count`, `source_ids_json`, `source_domains_json`, `provider_article_keys_json` from edges.
  - If canonical content hash changes, mark item raw and delete item-scoped derived facts for that canonical item only.
  - Remove the current block that mutates `news_story_members/news_story_groups` from fetch path; story projection is the only runtime writer of story membership/group read models.

- Add source sync methods:

  ```python
  def source_sync_cursor(self, *, source_id: str) -> dict[str, Any]:
      """Return high watermark and cursor JSON for provider fetch."""

  def update_source_sync_state(
      self,
      *,
      source_id: str,
      next_cursor: Mapping[str, Any],
      now_ms: int,
      commit: bool = True,
  ) -> None:
      """Persist sync_cursor_json, sync_high_watermark_ms, sync_overlap_ms, sync_diagnostics_json."""
  ```

- Add rebuild and diagnostics methods:

  ```python
  def rebuild_canonical_news_items_batch(
      self,
      *,
      source_ids: Sequence[str] | None,
      min_fetched_at_ms: int | None,
      limit: int,
      now_ms: int,
      execute: bool,
      commit: bool = True,
  ) -> dict[str, Any]:
      """Hard-cut rebuild canonical items from news_provider_items and clear derived rows for touched items."""

  def delete_page_rows_for_disabled_sources(self, *, commit: bool = True) -> int:
      """Delete page rows whose canonical item has no enabled observation edge."""

  def news_dedup_diagnostics(self) -> dict[str, Any]:
      """Return disabled page rows, duplicate content groups, duplicate canonical visible rows, OpenNews lag."""
  ```

- Lines 789-866: list only enabled representative rows by joining `news_item_observation_edges` and `news_sources`.

  Add SQL predicate:

  ```sql
  AND EXISTS (
    SELECT 1
      FROM news_item_observation_edges AS edges
      JOIN news_sources AS sources ON sources.source_id = edges.source_id
     WHERE edges.news_item_id = news_page_rows.news_item_id
       AND sources.enabled = true
  )
  ```

- Lines 1292-1356: `load_items_for_page_projection` aggregates only enabled observation edges and returns no payload for canonical items with zero enabled source edges.
- Lines 1514-1640: `get_news_item_detail` returns canonical item + observation edges + provider items. Route parameter remains `{news_item_id}` but its value is canonical item id only; there is no legacy lookup by old provider-item-scoped id.
- Lines 1642 onward: `get_news_story_detail` lists canonical item members and nests duplicate observations under each member.
- Lines 1966-2034: `list_source_status` includes `sync_high_watermark_ms`, `sync_diagnostics_json`, raw observation count, canonical item count, duplicate edge count and disabled serving row count.

### `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`

- Lines 57-118: capture disabled source ids from reconcile and delete disabled-source page rows inside the same transaction that disables sources; enqueue source-quality targets for changed sources.
- Lines 120-142: pass source sync cursor to OpenNews provider only; RSS/CryptoPanic receive an empty cursor:

  ```python
  source_cursor = (
      repos.news.source_sync_cursor(source_id)
      if str(source.get("provider_type") or "").strip().lower() == "opennews"
      else {}
  )
  feed_result = self.feed_client.fetch(
      snapshot,
      since_ms=int(source_cursor.get("high_watermark_ms") or 0) or None,
      cursor=source_cursor,
      cache=cache,
      limit=self._batch_size(),
  )
  ```

- Lines 175-210: after `_persist_entries`, call `repos.news.update_source_sync_state(source_id=source_id, next_cursor=feed_result.next_cursor, now_ms=now_ms, commit=False)` before `finish_fetch_run`.
- Lines 218-298: replace per-observation `upsert_news_item` with canonical identity resolution:

  ```python
  identity = canonical_identity_for_observation(
      provider_type=str(source.get("provider_type") or ""),
      source_id=source_id,
      provider_article_id=observation.provider_article_id,
      canonical_url=observation.canonical_url,
      content_hash=item_content_hash,
      title_fingerprint=item_title_fingerprint,
      published_at_ms=observation.published_at_ms,
  )
  news = repository.upsert_canonical_news_item(
      provider_item_id=provider["provider_item_id"],
      source_id=source_id,
      source_domain=source_domain,
      canonical_item_key=identity.canonical_item_key,
      dedup_key_kind=identity.dedup_key_kind,
      dedup_key_confidence=identity.dedup_key_confidence,
      url_identity_kind=identity.url_identity_kind,
      match_type=identity.match_type,
      match_confidence=identity.match_confidence,
      match_evidence=identity.evidence,
      canonical_url=observation.canonical_url,
      title=observation.title,
      summary=observation.summary,
      body_text=observation.body_text,
      language=observation.language,
      published_at_ms=observation.published_at_ms,
      fetched_at_ms=fetched_at_ms,
      content_hash=item_content_hash,
      title_fingerprint=item_title_fingerprint,
      now_ms=fetched_at_ms,
      provider_article_key=observation.provider_article_key,
      provider_signal=observation.provider_signal,
      provider_token_impacts=observation.provider_token_impacts,
      commit=False,
  )
  ```

- Dirty targets target canonical `news_item_id`; if duplicate observation only updates edge summary, enqueue `page` and `brief_input` for the canonical item, not a new story unless canonical content materially changed.
- Tests:
  - `tests/integration/domains/news_intel/test_news_ingest_flow.py::test_duplicate_opennews_ws_and_rest_article_id_produces_one_canonical_item`.
  - `tests/integration/domains/news_intel/test_news_ingest_flow.py::test_same_content_hash_multiple_provider_ids_projects_one_news_row`.
  - Update existing ingest test to keep RSS cursor empty and assert canonical item semantics.

### `src/parallax/domains/news_intel/services/news_story_grouping.py`

- Lines 23-64: story matching consumes canonical item fields and URL identity.
- Exact URL story match only when `url_identity_kind == "article"`.
- Exact content hash candidate path must work by adding candidate `content_hash`.
- `new_story_id` signature changes:

  ```python
  def new_story_id(*, canonical_item_key: str, representative_title: str) -> str:
      """Return deterministic story id from policy version plus canonical item key/title."""
  ```

- Tests:
  - `tests/unit/domains/news_intel/test_news_story_grouping.py::test_container_url_does_not_force_same_story`.
  - `tests/unit/domains/news_intel/test_news_story_grouping.py::test_article_url_can_match_same_story`.
  - `tests/unit/domains/news_intel/test_news_story_grouping.py::test_same_content_hash_candidate_matches_when_loaded`.
  - `tests/unit/domains/news_intel/test_news_story_grouping.py::test_new_story_id_is_order_independent_for_canonical_key`.

### `src/parallax/domains/news_intel/runtime/news_story_projection_worker.py`

- Lines 150-182: call updated `new_story_id(canonical_item_key=str(item_payload["canonical_item_key"]), representative_title=str(item_payload["title"]))`.
- Lines 185-195: downstream targets remain canonical `news_item` ids; no provider-observation targets.
- Tests:
  - `tests/unit/domains/news_intel/test_news_story_projection_dirty_targets.py` updated for canonical target ids.
  - `tests/architecture/test_news_intel_boundaries.py` asserts fetch worker does not write `news_story_groups/news_story_members`.

### `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`

- Keep worker shape, but item ids are canonical ids.
- Ensure `list_unprocessed_items` joins only canonical `news_items`.
- On canonical representative update, reprocessing deletes/replaces facts for canonical item only.
- Tests:
  - `tests/unit/domains/news_intel/test_news_workers.py::test_item_process_runs_once_for_duplicate_canonical_item`.

### `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`

- Treat `news_item_id` as canonical item id.
- `load_items_for_brief_targets` must aggregate duplicate/source evidence and avoid duplicate brief runs for duplicate observations.
- Tests:
  - `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_duplicate_observations_do_not_create_second_brief_run`.
  - `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py` updated for canonical item ids.

### `src/parallax/domains/news_intel/services/news_page_projection.py`

- Lines 13-66: build row id from canonical item id and include duplicate/source summaries.

  Add row fields:

  ```python
  "canonical_item_key": str(item.get("canonical_item_key") or ""),
  "duplicate_count": int(item.get("duplicate_observation_count") or 1),
  "source_ids_json": _json_list(item.get("source_ids_json")),
  "source_domains_json": _json_list(item.get("source_domains_json")),
  "provider_article_keys_json": _json_list(item.get("provider_article_keys_json")),
  ```

- `_source_payload` includes primary source plus `sources` summary array when available.
- Tests:
  - `tests/unit/domains/news_intel/test_news_page_projection.py::test_page_row_uses_canonical_item_identity`.
  - `tests/unit/domains/news_intel/test_news_page_projection.py::test_page_row_includes_duplicate_source_summary`.

### `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`

- Lines 49-84: unchanged worker lifecycle, but claimed ids are canonical item ids.
- If `load_items_for_page_projection` returns no payload for a claimed canonical item because all sources are disabled, `replace_page_rows_for_items` deletes its row and marks dirty target done.
- Tests:
  - `tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_disabled_source_canonical_item_deletes_page_row`.
  - `tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_exact_duplicate_content_visible_once`.

### `src/parallax/domains/news_intel/queries/news_page_query.py`

- Lines 35-36: parameter remains named `news_item_id` because the public path already uses that segment, but its value is a canonical item id. No legacy lookup is attempted.
- Add method docstring:

  ```python
  def get_item(self, *, news_item_id: str) -> dict[str, Any] | None:
      """Load canonical news item detail by canonical news_item_id only."""
  ```

### `src/parallax/app/surfaces/api/routes_news.py`

- Lines 42-49: error remains `news_item_not_found`; detail payload now includes canonical item and observation evidence.
- Lines 72-83: source status response includes dedup and sync diagnostics.
- Do not add `include_legacy`, `legacy_id`, `raw_item_id`, or fallback query params.
- Tests:
  - `tests/unit/test_api_news_contract.py::test_news_api_item_detail_uses_canonical_item_id_only`.
  - `tests/unit/test_api_news_contract.py::test_news_source_status_includes_dedup_sync_diagnostics`.

### `src/parallax/app/surfaces/cli/parser.py`

- Lines 113-290: add two ops commands.

  Parser shape:

  ```python
  rebuild_news_canonical = ops_subcommands.add_parser(
      "rebuild-news-canonical-items",
      help="hard-cut rebuild of News canonical items and derived projections from raw provider observations",
  )
  rebuild_news_canonical.add_argument("--source-id", action="append", default=[])
  rebuild_news_canonical.add_argument("--since-ms", type=int, default=None)
  rebuild_news_canonical.add_argument("--batch-size", type=int, default=1000)
  rebuild_news_canonical.add_argument("--max-batches", type=int, default=1)
  rebuild_news_canonical.add_argument("--execute", action="store_true")

  ops_subcommands.add_parser(
      "news-dedup-diagnostics",
      help="print News canonical dedup and OpenNews sync diagnostics without secrets",
  )
  ```

### `src/parallax/app/surfaces/cli/commands/ops.py`

- Lines 79-359: route the two new ops commands.

  Handler branches:

  ```python
  if args.ops_command == "rebuild-news-canonical-items":
      return _rebuild_news_canonical_items(args)

  if args.ops_command == "news-dedup-diagnostics":
      return _news_dedup_diagnostics()
  ```

- Create helper functions in same file or focused runtime module. Prefer focused module if helper exceeds 80 lines.

### `src/parallax/app/runtime/news_dedup_rebuild.py`

- Create hard-cut rebuild service used by CLI.

  Public API:

  ```python
  def rebuild_news_canonical_items(
      *,
      repositories: Any,
      source_ids: Sequence[str],
      since_ms: int | None,
      batch_size: int,
      max_batches: int,
      execute: bool,
      now_ms: int,
  ) -> dict[str, Any]:
      """Rebuild canonical news items and enqueue story/page/brief dirty targets from raw observations."""

  def news_dedup_diagnostics(*, repositories: Any) -> dict[str, Any]:
      """Return redacted canonical dedup, disabled serving row and OpenNews sync diagnostics."""
  ```

- Rebuild behavior:
  - Requires `--execute` to mutate.
  - Reads only `news_provider_items` and `news_sources`.
  - Computes canonical identity using the same service as fetch.
  - Deletes derived rows for touched canonical item ids: `news_page_rows`, `news_story_members`, stale `news_story_groups`, `news_item_agent_briefs`, `news_item_agent_runs`, `news_item_entities`, `news_token_mentions`, `news_fact_candidates`.
  - Deletes replaced old `news_items` rows in the selected scope.
  - Inserts canonical `news_items` and `news_item_observation_edges`.
  - Enqueues `story`, `page`, `brief_input`, and `source_quality` dirty targets.
  - Running the same command twice returns zero additional canonical item growth.

### `src/parallax/app/runtime/ops_diagnostics.py`

- Lines around news diagnostics aggregation: include `news_dedup_diagnostics` output under `domains.news.dedup`.
- Do not include tokens, API keys, Authorization headers, cookie values, or raw payload bodies.

### `docs/WORKERS.md`

- Update News worker rows:
  - `news_fetch` writes raw observations, canonical item rows, observation edges, source sync cursor.
  - `news_story_projection` consumes canonical items only.
  - `news_page_projection` writes representative rows only.
  - OpenNews sync docs state WS is low latency and REST is bounded catch-up with high watermark.

### `docs/CONTRACTS.md`

- Update `/api/news`, `/api/news/items/{news_item_id}`, `/api/news/stories/{story_id}`, `/api/news/sources/status` semantics.
- State `news_item_id` is canonical item id after the hard cut.
- State no legacy item id lookup exists.

## PR breakdown

1. **PR 1 - Storage, deterministic identity, and writer cutover gate**: migration, URL identity service, canonical identity service, canonical writer upsert, observation edge ledger, migration/repository unit tests. Mergeable only when the writer no longer uses `news_items ON CONFLICT(provider_item_id)` and migration leaves no zero-key/zero-edge serving rows.
2. **PR 2 - OpenNews sync contract**: FeedFetchResult cursor, provider registry cursor pass-through, OpenNews bounded REST page scan, ready/partial merge tests.
3. **PR 3 - Fetch hard cut canonical writes**: repository canonical upsert, observation edges, fetch worker dirty-target changes, source sync persistence, disabled-source page-row deletion.
4. **PR 4 - Projection and brief hard cut**: story/page/brief workers consume canonical items, representative page rows, detail queries, architecture boundary test.
5. **PR 5 - Ops rebuild and API diagnostics**: rebuild command, dedup diagnostics command, `/api/news/sources/status` diagnostics, docs updates, full verification.

## Rollout order

1. Create worktree and branch:

   ```bash
   git worktree add .worktrees/news-intel-dedup-root-fix -b codex/news-intel-dedup-root-fix main
   ```

2. Run baselines in the worktree:

   ```bash
   uv run ruff check .
   uv run pytest tests/unit/domains/news_intel tests/unit/integrations/news_feeds tests/integration/domains/news_intel tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_boundaries.py
   ```

3. Apply migration:

   ```bash
   uv run alembic upgrade head
   ```

4. Run dry diagnostics:

   ```bash
   uv run parallax ops news-dedup-diagnostics
   uv run parallax ops rebuild-news-canonical-items --batch-size 1000 --max-batches 1
   ```

5. Execute hard-cut canonical rebuild:

   ```bash
   uv run parallax ops rebuild-news-canonical-items --batch-size 1000 --max-batches 100 --execute
   ```

6. Drain workers in this order until each reports processed 0 or only expected skips: `news_item_process`, `news_story_projection`, `news_item_brief`, `news_page_projection`, `news_source_quality_projection`.

7. Verify public read path:

   ```bash
   curl -s http://127.0.0.1:8765/api/news?limit=200 | jq '.data.items | length'
   curl -s http://127.0.0.1:8765/api/news/sources/status | jq '.data.source_hygiene, .data.sources[0].sync_diagnostics_json'
   uv run parallax ops news-dedup-diagnostics
   ```

8. Run full completion gate:

   ```bash
   make check-all
   ```

## Rollback

- Before step 3: delete the worktree branch or revert code normally.
- After migration before rebuild: downgrade `20260528_0116` if no canonical rebuild has run.
- After rebuild: database rollback requires restoring the pre-rollout PostgreSQL backup. This is a hard cut; there is no legacy dual-read recovery path.
- If OpenNews sync regresses but canonical rebuild is correct, pause `news_fetch`, fix PR 2 code, keep canonical tables, and resume fetch after tests pass.
- If page projection emits bad rows, truncate only `news_page_rows`, enqueue bounded `page` dirty targets from canonical `news_items`, and rerun `news_page_projection`.

## Acceptance test commands

- AC1:

  ```bash
  uv run parallax config
  ```

  Expected: reports `config_path=/Users/qinghuan/.parallax/config.yaml`, `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`, no secret values.

- AC2 and AC3:

  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_ready_payload_not_overwritten_by_later_partial -q
  uv run pytest tests/integration/domains/news_intel/test_news_ingest_flow.py::test_duplicate_opennews_ws_and_rest_article_id_produces_one_canonical_item -q
  ```

- AC4 and AC5:

  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_rest_scans_pages_until_overlap_stop -q
  uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_rest_returns_high_watermark_cursor_after_commit_candidate -q
  ```

- AC6 and AC7:

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_exact_duplicate_content_visible_once -q
  uv run pytest tests/integration/domains/news_intel/test_news_ingest_flow.py::test_same_content_hash_multiple_provider_ids_projects_one_news_row -q
  ```

- AC8:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py::test_container_url_does_not_force_same_story -q
  ```

- AC9:

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_disabled_source_canonical_item_deletes_page_row -q
  ```

- AC10:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py::test_new_story_id_is_order_independent_for_canonical_key -q
  ```

- AC11:

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_canonical_page_projection_unchanged_write_count_is_zero -q
  ```

- AC12:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_duplicate_observations_do_not_create_second_brief_run -q
  ```

- AC13:

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_rebuild_news_canonical_items_is_idempotent -q
  ```

- AC14:

  ```bash
  uv run parallax ops rebuild-news-canonical-items --batch-size 1000 --max-batches 100 --execute
  uv run parallax ops news-dedup-diagnostics
  ```

  Expected JSON fields: `disabled_page_rows=0`, `visible_duplicate_content_hash_excess=0`, `same_canonical_rows_visible=0`.

- Full gate:

  ```bash
  make check-all
  ```

## Verification

Record final verification in `docs/superpowers/plans/active/2026-05-28-news-intel-dedup-root-fix-verification-cn.md` before claiming implementation complete. Include full `make check-all` output, `Coverage`, `Skipped tests`, `E2E golden path`, OpenNews dedup diagnostics output, and remaining risks.
