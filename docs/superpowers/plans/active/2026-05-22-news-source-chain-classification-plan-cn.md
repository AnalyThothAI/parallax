# News Source Chain Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Active plan, not implemented
**Date:** 2026-05-22
**Owning spec:** `docs/superpowers/specs/active/2026-05-22-news-source-chain-classification-cn.md`
**Recommended branch:** `codex/news-source-chain-classification`

**Goal:** Upgrade News Intel from RSS/CryptoPanic page ingestion into a classified, multi-source, authority-aware information-source chain while keeping Postgres facts and rebuildable read models as the only business truth.

**Architecture:** Keep the existing `news_fetch -> news_item_process -> news_story_projection -> news_item_brief -> news_page_projection` chain. Add source classification fields to `news_sources`, introduce a provider registry behind the fetch worker, store comments/replies as `news_context_items`, add a single-writer `news_source_quality_projection` read model, and make fact acceptance check source authority scope instead of role alone.

**Tech Stack:** Python 3.13, Pydantic settings, PostgreSQL/Alembic, psycopg3 repository sessions, existing RSS/CryptoPanic integrations, FastAPI read-only API routes, pytest architecture/unit/integration tests, React/TypeScript only after API contract changes need UI.

---

## Review Verdict

The spec is directionally sound and fits the existing News Intel boundary. The current chain already has the right spine:

- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py:45` reconciles configured sources into `news_sources`, claims due rows, releases the DB session, then fetches provider IO outside the session.
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py:49` performs deterministic entity extraction, token resolution, and fact candidate construction from persisted `news_items`.
- `src/gmgn_twitter_intel/domains/news_intel/services/news_fact_candidates.py:23` already gates accepted facts by official source roles, but it lacks authority scope, event-class mapping, and non-official corroboration policy.
- `src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py:106` only emits compact `source_role` and `trust_tier`, so provider type, coverage tags, content class, authority reasons, and source quality are not yet product-visible.
- `tests/architecture/test_worker_runtime_contracts.py:170` enforces single-writer read models. Any new `news_source_quality_rows` table must be listed there with exactly one runtime writer.

The main correction is scope. The spec spans six subsystems; shipping all providers in one branch would be brittle. The executable plan below ships a foundation first, then adds provider waves behind disabled-by-default config.

## Code-Review Findings

1. `NewsSourceSettings` currently uses `extra="forbid"` and `provider_type: Literal["rss", "atom", "json_feed", "cryptopanic"]` in `src/gmgn_twitter_intel/platform/config/settings.py:488`. New fields such as `coverage_tags`, `authority_scope`, and provider types such as `openbb` or `telegram_public` will fail config parsing until Task 1 lands.
2. The DB has matching check constraints in `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:37` and the CryptoPanic expansion in `20260521_0075_news_source_cryptopanic_provider.py:19`. Migration work must precede any operator config using new provider or source-role values.
3. `NewsRepository._source_payload` only forwards the original source fields at `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:1542`. Source reconciliation will silently drop new classification fields until repository payloads are extended.
4. Current fact acceptance is too coarse: `source_role in official_*` is necessary but not sufficient. Official protocol sources must only accept in-scope protocol/token/repo events; official exchange sources must only accept venue-scoped listing/delisting/maintenance events.
5. Social/community/comment data should not be appended into `news_items.body_text`; otherwise item brief and fact extraction cannot distinguish primary evidence from market chatter. `news_context_items` must come before Reddit/HN/Twitter reply expansion.
6. The real runtime config paths were confirmed with `uv run gmgn-twitter-intel config`: config and workers paths point at `~/.gmgn-twitter-intel/`. Current real news sources are RSS media/finance sources, and the real `workers.yaml` should add `news_item_brief_updated` to `news_page_projection.wakes_on` for timely UI refresh.

## Release Shape

Ship in two branches if possible.

1. **Foundation branch:** Tasks 1 through 7. This makes classification, registry compatibility, context facts, quality rows, authority validation, API filters, docs, and tests work while preserving existing RSS/CryptoPanic behavior.
2. **Provider wave branch:** Task 8 plus provider-specific tests. Add OpenBB, Telegram, GitHub, Reddit/HN, and Twitter/X adapters one provider family at a time, disabled by default until source-quality diagnostics are visible.

Do not merge provider adapters before the foundation branch can ingest existing RSS/CryptoPanic sources unchanged.

## Pre-Flight

- [ ] Confirm the only existing working tree change is the spec/plan work:
  ```bash
  git status --short
  ```
  Expected: either clean or only `docs/superpowers/specs/active/2026-05-22-news-source-chain-classification-cn.md` and this plan file.

- [ ] Create an isolated branch:
  ```bash
  git switch -c codex/news-source-chain-classification
  ```
  Expected: branch name prints as `codex/news-source-chain-classification`.

- [ ] Confirm real runtime config paths before using live provider data:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`. Report only paths, redacted booleans, counts, and diagnostics.

- [ ] Baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  uv run pytest tests/unit/domains/news_intel -q
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_providers_wiring.py -q
  ```
  Expected: pass, or record baseline failures before changing code.

## File Structure

### Create

- `src/gmgn_twitter_intel/domains/news_intel/types/source_classification.py`
  Shared literals and normalization helpers for provider types, source roles, coverage tags, cost classes, content classes, and context types.
- `src/gmgn_twitter_intel/domains/news_intel/types/source_provider.py`
  `NewsSourceSnapshot`, `NewsSourceHttpCache`, `NewsProviderObservation`, `NewsProviderContextObservation`, and `NewsProviderFetchResult`.
- `src/gmgn_twitter_intel/domains/news_intel/services/source_authority.py`
  Deterministic authority-scope validator used by fact candidate construction.
- `src/gmgn_twitter_intel/domains/news_intel/services/source_quality_projection.py`
  Pure functions that compute rolling source-quality rows from repository aggregate payloads.
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_source_quality_projection_worker.py`
  Single runtime writer for `news_source_quality_rows`.
- `src/gmgn_twitter_intel/integrations/news_feeds/provider_registry.py`
  Registry that routes provider types to source providers and wraps existing RSS/CryptoPanic clients.
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py`
  Source classification and `news_context_items` migration.
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py`
  Source quality read-model migration.
- `tests/unit/domains/news_intel/test_source_classification.py`
- `tests/unit/domains/news_intel/test_source_authority.py`
- `tests/unit/domains/news_intel/test_source_quality_projection.py`
- `tests/unit/integrations/news_feeds/test_provider_registry.py`
- `tests/integration/domains/news_intel/test_news_source_classification_repository.py`
- `tests/integration/domains/news_intel/test_news_context_items_repository.py`
- `tests/integration/domains/news_intel/test_news_source_quality_repository.py`

### Modify

- `config.example.yaml`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/WORKERS.md`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/news_intel.py`
- `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_news.py`
- `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/news_intel/providers.py`
- `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py`
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py`
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_brief_worker.py`
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_page_projection_worker.py`
- `src/gmgn_twitter_intel/domains/news_intel/services/news_fact_candidates.py`
- `src/gmgn_twitter_intel/domains/news_intel/services/news_item_brief_input.py`
- `src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py`
- `src/gmgn_twitter_intel/domains/news_intel/types/__init__.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/unit/test_worker_settings.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/unit/test_providers_wiring.py`
- `tests/unit/test_api_news_contract.py`
- `tests/unit/domains/news_intel/test_news_fact_candidates.py`
- `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- `tests/unit/domains/news_intel/test_news_page_projection.py`
- `tests/unit/domains/news_intel/test_news_workers.py`
- `tests/integration/domains/news_intel/test_news_repository.py`

## Task 1: Source Taxonomy, Settings, And DB Classification

**Files:**
- Create: `src/gmgn_twitter_intel/domains/news_intel/types/source_classification.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/types/__init__.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Test: `tests/unit/domains/news_intel/test_source_classification.py`
- Test: `tests/unit/test_settings.py`
- Test: `tests/integration/domains/news_intel/test_news_source_classification_repository.py`

- [ ] **Step 1: Add failing taxonomy tests**
  ```python
  from gmgn_twitter_intel.platform.config.settings import NewsSourceSettings

  def test_news_source_settings_accept_classification_fields() -> None:
      source = NewsSourceSettings(
          source_id="coinbase-announcements",
          provider_type="rss",
          feed_url="https://example.com/feed.xml",
          source_domain="coinbase.com",
          source_name="Coinbase Announcements",
          source_role="official_exchange",
          trust_tier="official",
          coverage_tags=["crypto_exchange", "exchange_listing"],
          asset_universe=["BTC", "ETH"],
          authority_scope={"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
          fetch_policy={"max_items": 50},
          context_policy={"fetch_discussion": False},
          cost_policy={"class": "free"},
      )

      assert source.coverage_tags == ("crypto_exchange", "exchange_listing")
      assert source.authority_scope["event_types"] == ["exchange_listing"]
  ```

- [ ] **Step 2: Run taxonomy tests to verify failure**
  ```bash
  uv run pytest tests/unit/test_settings.py::test_news_source_settings_accept_classification_fields -q
  ```
  Expected: fails because `NewsSourceSettings` rejects new fields.

- [ ] **Step 3: Implement source classification literals**
  ```python
  PROVIDER_TYPES = (
      "rss", "atom", "json_feed", "cryptopanic", "openbb", "telegram_public",
      "twitter_profile", "twitter_thread_context", "reddit", "hackernews",
      "github", "ossinsight", "manual_api",
  )
  SOURCE_ROLES = (
      "official_exchange", "official_regulator", "official_protocol", "official_issuer",
      "specialist_media", "aggregator", "social", "community", "developer_signal",
      "observed_source",
  )
  TRUST_TIERS = ("official", "high", "standard", "low")
  COVERAGE_TAGS = (
      "crypto_market", "crypto_policy", "crypto_security", "crypto_exchange",
      "crypto_protocol", "crypto_etf", "macro_policy", "equity_market",
      "single_stock", "developer_release", "community_discussion", "social_viral",
      "onchain_flow", "fund_flow", "exchange_listing",
  )

  def normalize_string_tuple(value: object) -> tuple[str, ...]:
      if value is None:
          return ()
      if isinstance(value, str):
          raw_values = [part.strip() for part in value.split(",")]
      else:
          raw_values = [str(part).strip() for part in value]  # type: ignore[arg-type]
      return tuple(part for part in raw_values if part)
  ```

- [ ] **Step 4: Extend settings and domain source config**
  ```python
  coverage_tags: tuple[str, ...] = ()
  asset_universe: tuple[str, ...] = ()
  authority_scope: dict[str, Any] = Field(default_factory=dict)
  fetch_policy: dict[str, Any] = Field(default_factory=dict)
  context_policy: dict[str, Any] = Field(default_factory=dict)
  cost_policy: dict[str, Any] = Field(default_factory=dict)

  @field_validator("coverage_tags", "asset_universe", mode="before")
  @classmethod
  def parse_string_tuple(cls, value: Any) -> tuple[str, ...]:
      return normalize_string_tuple(value)
  ```

- [ ] **Step 5: Add migration for source classification and context table**
  ```sql
  ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check;
  ALTER TABLE news_sources
    ADD CONSTRAINT news_sources_provider_type_check
    CHECK (provider_type IN (
      'rss','atom','json_feed','cryptopanic','openbb','telegram_public',
      'twitter_profile','twitter_thread_context','reddit','hackernews',
      'github','ossinsight','manual_api'
    ));
  ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_source_role_check;
  ALTER TABLE news_sources
    ADD CONSTRAINT news_sources_source_role_check
    CHECK (source_role IN (
      'official_exchange','official_regulator','official_protocol','official_issuer',
      'specialist_media','aggregator','social','community','developer_signal','observed_source'
    ));
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS coverage_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS asset_universe_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS authority_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS fetch_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS context_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS cost_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS source_quality_status TEXT NOT NULL DEFAULT 'unknown';
  ```

- [ ] **Step 6: Extend repository reconciliation**
  ```python
  "coverage_tags_json": _json(list(source.coverage_tags)),
  "asset_universe_json": _json(list(source.asset_universe)),
  "authority_scope_json": _json(source.authority_scope),
  "fetch_policy_json": _json(source.fetch_policy),
  "context_policy_json": _json(source.context_policy),
  "cost_policy_json": _json(source.cost_policy),
  ```
  The upsert must preserve `source_quality_status` on updates; only inserts use `unknown`.

- [ ] **Step 7: Run classification checks**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_source_classification.py tests/unit/test_settings.py tests/integration/domains/news_intel/test_news_source_classification_repository.py -q
  ```
  Expected: settings accept classification fields, migration-backed repository tests persist and reload JSON fields, existing RSS/CryptoPanic settings still pass.

- [ ] **Step 8: Commit**
  ```bash
  git add src/gmgn_twitter_intel/domains/news_intel/types src/gmgn_twitter_intel/platform/config/settings.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/platform/db/alembic/versions tests/unit tests/integration
  git commit -m "feat(news): add source classification schema"
  ```

## Task 2: Context Items As Facts

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/services/news_item_brief_input.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/types/news_item_brief.py`
- Test: `tests/integration/domains/news_intel/test_news_context_items_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_input.py`

- [ ] **Step 1: Add failing repository test**
  ```python
  def test_context_items_are_persisted_without_changing_news_item_body(news_repository, seeded_news_item):
      news_repository.upsert_news_context_item(
          context_item_id="ctx-1",
          source_id=seeded_news_item["source_id"],
          parent_news_item_id=seeded_news_item["news_item_id"],
          provider_item_id=None,
          context_type="comment",
          author="reader",
          canonical_url="https://example.com/news#comment-1",
          body_text="This is market reaction, not primary evidence.",
          published_at_ms=seeded_news_item["published_at_ms"] + 1,
          engagement_json={"score": 7},
          raw_payload_json={"id": "comment-1"},
          created_at_ms=seeded_news_item["published_at_ms"] + 2,
      )

      detail = news_repository.get_news_item_detail(seeded_news_item["news_item_id"])
      assert detail["item"]["body_text"] == seeded_news_item["body_text"]
      assert detail["context_items"][0]["context_type"] == "comment"
  ```

- [ ] **Step 2: Run context test to verify failure**
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_context_items_repository.py::test_context_items_are_persisted_without_changing_news_item_body -q
  ```
  Expected: fails because repository methods and table do not exist.

- [ ] **Step 3: Add `news_context_items` DDL**
  ```sql
  CREATE TABLE IF NOT EXISTS news_context_items (
    context_item_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
    parent_news_item_id TEXT REFERENCES news_items(news_item_id) ON DELETE CASCADE,
    provider_item_id TEXT REFERENCES news_provider_items(provider_item_id) ON DELETE SET NULL,
    context_type TEXT NOT NULL,
    author TEXT,
    canonical_url TEXT,
    body_text TEXT NOT NULL,
    published_at_ms BIGINT,
    engagement_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at_ms BIGINT NOT NULL,
    CHECK (context_type IN ('comment','reply','discussion','engagement_snapshot','related_post','source_quote'))
  );
  CREATE INDEX IF NOT EXISTS idx_news_context_items_parent ON news_context_items(parent_news_item_id, published_at_ms DESC);
  CREATE INDEX IF NOT EXISTS idx_news_context_items_source ON news_context_items(source_id, published_at_ms DESC);
  ```

- [ ] **Step 4: Add repository methods**
  ```python
  def upsert_news_context_item(self, *, context_item_id: str, source_id: str, parent_news_item_id: str | None, provider_item_id: str | None, context_type: str, author: str | None, canonical_url: str | None, body_text: str, published_at_ms: int | None, engagement_json: Mapping[str, Any], raw_payload_json: Mapping[str, Any], created_at_ms: int, commit: bool = True) -> dict[str, Any]:
      row = self.conn.execute(
          """
          INSERT INTO news_context_items (
            context_item_id, source_id, parent_news_item_id, provider_item_id, context_type,
            author, canonical_url, body_text, published_at_ms, engagement_json, raw_payload_json, created_at_ms
          )
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (context_item_id) DO UPDATE SET
            parent_news_item_id = EXCLUDED.parent_news_item_id,
            context_type = EXCLUDED.context_type,
            author = EXCLUDED.author,
            canonical_url = EXCLUDED.canonical_url,
            body_text = EXCLUDED.body_text,
            published_at_ms = EXCLUDED.published_at_ms,
            engagement_json = EXCLUDED.engagement_json,
            raw_payload_json = EXCLUDED.raw_payload_json
          RETURNING *
          """,
          (context_item_id, source_id, parent_news_item_id, provider_item_id, context_type, author, canonical_url, body_text, published_at_ms, _json(engagement_json), _json(raw_payload_json), created_at_ms),
      ).fetchone()
      if commit:
          self.conn.commit()
      return dict(row)
  ```

- [ ] **Step 5: Add context to item brief packet with hard limits**
  ```python
  MAX_CONTEXT_ITEMS = 8
  MAX_CONTEXT_BODY_CHARS = 500
  refs.extend(f"context:{row.context_item_id}" for row in context_items if row.context_item_id)
  ```
  Context refs may support `market_read_zh`; they must not satisfy accepted fact authority by themselves.

- [ ] **Step 6: Run context checks**
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_context_items_repository.py tests/unit/domains/news_intel/test_news_item_brief_input.py -q
  ```
  Expected: context rows persist independently, detail payloads include bounded context, and packet evidence refs include `context:*`.

- [ ] **Step 7: Commit**
  ```bash
  git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/domains/news_intel/services/news_item_brief_input.py src/gmgn_twitter_intel/domains/news_intel/types/news_item_brief.py tests/integration/domains/news_intel/test_news_context_items_repository.py tests/unit/domains/news_intel/test_news_item_brief_input.py
  git commit -m "feat(news): persist context items for source discussions"
  ```

## Task 3: Provider Registry With RSS/CryptoPanic Compatibility

**Files:**
- Create: `src/gmgn_twitter_intel/domains/news_intel/types/source_provider.py`
- Create: `src/gmgn_twitter_intel/integrations/news_feeds/provider_registry.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/providers.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py`
- Test: `tests/unit/integrations/news_feeds/test_provider_registry.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/unit/test_providers_wiring.py`

- [ ] **Step 1: Add failing registry tests**
  ```python
  def test_provider_registry_routes_rss_and_cryptopanic(fake_rss_provider, fake_cryptopanic_provider):
      registry = NewsSourceProviderRegistry()
      registry.register(fake_rss_provider)
      registry.register(fake_cryptopanic_provider)

      assert registry.provider_for({"provider_type": "rss"}) is fake_rss_provider
      assert registry.provider_for({"provider_type": "cryptopanic"}) is fake_cryptopanic_provider
  ```

- [ ] **Step 2: Run registry test to verify failure**
  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_provider_registry.py::test_provider_registry_routes_rss_and_cryptopanic -q
  ```
  Expected: fails because registry does not exist.

- [ ] **Step 3: Define provider result types**
  ```python
  @dataclass(frozen=True, slots=True)
  class NewsProviderObservation:
      source_item_key: str
      canonical_url: str
      title: str
      summary: str
      body_text: str
      language: str
      published_at_ms: int | None
      raw_payload: dict[str, Any]
      engagement: dict[str, Any] = field(default_factory=dict)
      provider_tags: list[str] = field(default_factory=list)
      original_source_url: str | None = None
      original_source_domain: str | None = None

  @dataclass(frozen=True, slots=True)
  class NewsProviderFetchResult:
      status_code: int
      observations: list[NewsProviderObservation]
      context_observations: list[NewsProviderContextObservation] = field(default_factory=list)
      etag: str | None = None
      last_modified: str | None = None
      next_cursor: dict[str, Any] = field(default_factory=dict)
      not_modified: bool = False
      provider_diagnostics: dict[str, Any] = field(default_factory=dict)
  ```

- [ ] **Step 4: Implement registry**
  ```python
  class NewsSourceProviderRegistry:
      def __init__(self) -> None:
          self._providers: dict[str, NewsSourceProvider] = {}

      def register(self, provider: NewsSourceProvider) -> None:
          self._providers[str(provider.provider_type)] = provider

      def provider_for(self, source: Mapping[str, Any]) -> NewsSourceProvider:
          provider_type = str(source.get("provider_type") or "").strip()
          try:
              return self._providers[provider_type]
          except KeyError as exc:
              raise ValueError(f"unsupported news provider_type: {provider_type}") from exc
  ```

- [ ] **Step 5: Wrap existing RSS/CryptoPanic clients**
  ```python
  class FeedClientSourceProvider:
      provider_type = "rss"

      def fetch(self, *, source: NewsSourceSnapshot, since_ms: int | None, cursor: dict[str, Any], cache: NewsSourceHttpCache, limit: int) -> NewsProviderFetchResult:
          result = self._client.fetch(source.feed_url, etag=cache.etag, last_modified=cache.last_modified, provider_type=source.provider_type, source=source.raw)
          observations = [feed_entry_to_observation(source.source_domain, entry, fetched_at_ms=source.now_ms) for entry in result.entries[:limit]]
          return NewsProviderFetchResult(status_code=result.status_code, observations=observations, etag=result.etag, last_modified=result.last_modified, not_modified=result.not_modified)
  ```
  Atom and JSON feed can register the same implementation under `atom` and `json_feed`.

- [ ] **Step 6: Change `NewsFetchWorker` to depend on registry**
  ```python
  provider = self.source_providers.provider_for(source)
  fetch_result = provider.fetch(
      source=NewsSourceSnapshot.from_row(source, now_ms=now_ms),
      since_ms=_optional_int(source.get("last_success_at_ms")),
      cursor=_json_dict(source.get("fetch_cursor_json")),
      cache=NewsSourceHttpCache(etag=_optional_str(source.get("etag")), last_modified=_optional_str(source.get("last_modified"))),
      limit=int(_json_dict(source.get("fetch_policy_json")).get("max_items") or self._batch_size()),
  )
  ```

- [ ] **Step 7: Run compatibility checks**
  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_providers_wiring.py -q
  ```
  Expected: existing RSS/CryptoPanic worker tests still pass, unknown provider types fail with a compact worker error and fetch-run failure.

- [ ] **Step 8: Commit**
  ```bash
  git add src/gmgn_twitter_intel/domains/news_intel/types/source_provider.py src/gmgn_twitter_intel/domains/news_intel/providers.py src/gmgn_twitter_intel/integrations/news_feeds/provider_registry.py src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_providers_wiring.py
  git commit -m "feat(news): route source fetches through provider registry"
  ```

## Task 4: Fetch Persistence For Observations And Context

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Add failing worker test**
  ```python
  def test_news_fetch_worker_persists_context_observations(fake_provider_registry, db):
      fake_provider_registry.enqueue_context(parent_key="primary-1", context_type="reply", body_text="reaction")
      worker = build_news_fetch_worker_for_test(
          db=db,
          news_settings=news_settings_with_single_due_source(source_id="source-1"),
          source_providers=fake_provider_registry,
      )
      result = worker.run_once_sync(now_ms=1_000)

      assert result.processed == 1
      assert db.scalar("SELECT count(*) FROM news_context_items") == 1
  ```

- [ ] **Step 2: Run worker test to verify failure**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_persists_context_observations -q
  ```
  Expected: fails because `_persist_entries` only handles normalized primary entries.

- [ ] **Step 3: Persist primary observations through existing provider/news tables**
  ```python
  for observation in fetch_result.observations:
      provider = repository.upsert_provider_item(
          source_id=source_id,
          fetch_run_id=fetch_run_id,
          source_item_key=observation.source_item_key,
          canonical_url=observation.canonical_url,
          payload_hash=_payload_hash(observation.raw_payload),
          raw_payload=observation.raw_payload,
          fetched_at_ms=fetched_at_ms,
          commit=False,
      )
      repository.upsert_news_item(
          provider_item_id=provider["provider_item_id"],
          source_id=source_id,
          source_domain=source_domain,
          canonical_url=observation.canonical_url,
          title=observation.title,
          summary=observation.summary,
          body_text=observation.body_text,
          language=observation.language,
          published_at_ms=observation.published_at_ms,
          fetched_at_ms=fetched_at_ms,
          content_hash=content_hash(observation.title, observation.summary, observation.canonical_url, body_text=observation.body_text),
          title_fingerprint=title_fingerprint(observation.title),
          now_ms=fetched_at_ms,
          commit=False,
      )
  ```

- [ ] **Step 4: Persist context observations after parent mapping**
  ```python
  parent_ids_by_source_key[observation.source_item_key] = news["news_item_id"]
  for context in fetch_result.context_observations:
      repository.upsert_news_context_item(
          context_item_id=context.context_item_id,
          source_id=source_id,
          parent_news_item_id=parent_ids_by_source_key.get(context.parent_source_item_key),
          provider_item_id=None,
          context_type=context.context_type,
          author=context.author,
          canonical_url=context.canonical_url,
          body_text=context.body_text,
          published_at_ms=context.published_at_ms,
          engagement_json=context.engagement,
          raw_payload_json=context.raw_payload,
          created_at_ms=fetched_at_ms,
          commit=False,
      )
  ```

- [ ] **Step 5: Run persistence checks**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_context_items_repository.py -q
  ```
  Expected: primary items and context items persist in one success path; provider IO is still outside repository sessions.

- [ ] **Step 6: Commit**
  ```bash
  git add src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_workers.py tests/integration/domains/news_intel
  git commit -m "feat(news): persist provider observations and context"
  ```

## Task 5: Authority-Scope Validation And Content Classes

**Files:**
- Create: `src/gmgn_twitter_intel/domains/news_intel/services/source_authority.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/services/news_fact_candidates.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Test: `tests/unit/domains/news_intel/test_source_authority.py`
- Test: `tests/unit/domains/news_intel/test_news_fact_candidates.py`

- [ ] **Step 1: Add failing authority tests**
  ```python
  def test_official_exchange_accepts_in_scope_listing():
      decision = validate_source_authority(
          source_role="official_exchange",
          authority_scope={"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
          event_type="exchange_listing",
          source_domain="coinbase.com",
          affected_targets=[{"production_eligible": True}],
          realis="actual",
      )

      assert decision.acceptance_allowed is True
      assert decision.rejection_reasons == []

  def test_official_protocol_rejects_out_of_scope_exchange_listing():
      decision = validate_source_authority(
          source_role="official_protocol",
          authority_scope={"event_types": ["protocol_upgrade"], "domains": ["ethereum.org"]},
          event_type="exchange_listing",
          source_domain="ethereum.org",
          affected_targets=[{"production_eligible": True}],
          realis="actual",
      )

      assert decision.acceptance_allowed is False
      assert "source_not_authoritative_for_event_type" in decision.rejection_reasons
  ```

- [ ] **Step 2: Run authority tests to verify failure**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_source_authority.py -q
  ```
  Expected: fails because validator does not exist.

- [ ] **Step 3: Implement authority validator**
  ```python
  ROLE_EVENT_TYPES = {
      "official_exchange": {"exchange_listing", "exchange_delisting", "maintenance", "exchange_incident"},
      "official_regulator": {"regulatory_action", "macro_policy"},
      "official_protocol": {"protocol_upgrade", "security_incident", "governance_tokenomics", "developer_release"},
      "official_issuer": {"etf_fund_flow", "equity_company_event"},
      "developer_signal": {"developer_release", "protocol_upgrade"},
  }

  def validate_source_authority(*, source_role: str, authority_scope: Mapping[str, Any], event_type: str, source_domain: str, affected_targets: list[dict[str, object]], realis: str) -> SourceAuthorityDecision:
      reasons: list[str] = []
      if realis not in {"actual", "scheduled", "official_proposed"}:
          reasons.append("realis_not_acceptance_grade")
      if event_type not in ROLE_EVENT_TYPES.get(source_role, set()):
          reasons.append("source_not_authoritative_for_event_type")
      allowed_domains = {str(value).lower() for value in authority_scope.get("domains", [])}
      if allowed_domains and source_domain.lower() not in allowed_domains:
          reasons.append("source_domain_out_of_authority_scope")
      if not any(bool(target.get("production_eligible")) for target in affected_targets):
          reasons.append("target_identity_not_production_eligible")
      return SourceAuthorityDecision(acceptance_allowed=not reasons, rejection_reasons=reasons)
  ```

- [ ] **Step 4: Pass source classification into item processing**
  ```python
  candidates = build_fact_candidates(
      news_item_id=news_item_id,
      source_role=_text(item_payload, "source_role") or "observed_source",
      source_domain=_text(item_payload, "source_domain"),
      authority_scope=_json_dict(item_payload.get("authority_scope_json")),
      title=_text(item_payload, "title"),
      summary=_text(item_payload, "summary"),
      body_text=_text(item_payload, "body_text"),
      token_mentions=mentions,
      now_ms=now,
  )
  ```

- [ ] **Step 5: Normalize event class names**
  ```python
  _EVENT_PATTERNS = (
      ("exchange_listing", re.compile(r"\b(?:lists?|listing|goes live|launches trading)\b", re.IGNORECASE)),
      ("exchange_delisting", re.compile(r"\b(?:delists?|delisting|suspend trading)\b", re.IGNORECASE)),
      ("security_incident", re.compile(r"\b(?:hack|hacked|exploit|exploited|drained)\b", re.IGNORECASE)),
      ("regulatory_action", re.compile(r"\b(?:sec|cftc|regulator|court|lawsuit|settlement|approval|approved)\b", re.IGNORECASE)),
      ("etf_fund_flow", re.compile(r"\bETF\b|\bexchange-traded fund\b|\b(?:inflow|outflow|net flow)\b", re.IGNORECASE)),
      ("governance_tokenomics", re.compile(r"\bunlock\b|\bgovernance\b|\bproposal\b", re.IGNORECASE)),
      ("protocol_upgrade", re.compile(r"\b(?:upgrade|mainnet|hard fork)\b", re.IGNORECASE)),
  )
  ```

- [ ] **Step 6: Run fact validation checks**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_source_authority.py tests/unit/domains/news_intel/test_news_fact_candidates.py tests/unit/domains/news_intel/test_news_workers.py -q
  ```
  Expected: specialist media and aggregators remain `attention`; official in-scope events can become `accepted`; out-of-scope official events stay `attention` with authority rejection reasons.

- [ ] **Step 7: Commit**
  ```bash
  git add src/gmgn_twitter_intel/domains/news_intel/services/source_authority.py src/gmgn_twitter_intel/domains/news_intel/services/news_fact_candidates.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_authority.py tests/unit/domains/news_intel/test_news_fact_candidates.py tests/unit/domains/news_intel/test_news_workers.py
  git commit -m "feat(news): validate fact candidates by authority scope"
  ```

## Task 6: Source Quality Read Model And Worker

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py`
- Create: `src/gmgn_twitter_intel/domains/news_intel/services/source_quality_projection.py`
- Create: `src/gmgn_twitter_intel/domains/news_intel/runtime/news_source_quality_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_factories/news_intel.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Test: `tests/unit/domains/news_intel/test_source_quality_projection.py`
- Test: `tests/unit/test_worker_settings.py`
- Test: `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Test: `tests/integration/domains/news_intel/test_news_source_quality_repository.py`

- [ ] **Step 1: Add failing source-quality tests**
  ```python
  def test_source_quality_score_is_deterministic():
      row = build_source_quality_row(
          source_id="coindesk",
          window="24h",
          computed_at_ms=1_000,
          metrics={
              "fetch_success_rate": 1.0,
              "process_success_rate": 1.0,
              "resolved_token_rate": 0.8,
              "brief_ready_rate": 0.5,
              "duplicate_rate": 0.2,
              "normalized_freshness": 0.9,
              "useful_fact_or_context_rate": 0.6,
          },
      )

      assert row["quality_score"] == 84.0
      assert row["projection_version"]
  ```

- [ ] **Step 2: Run source-quality tests to verify failure**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py -q
  ```
  Expected: fails because projection functions do not exist.

- [ ] **Step 3: Add `news_source_quality_rows` DDL**
  ```sql
  CREATE TABLE IF NOT EXISTS news_source_quality_rows (
    row_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
    window TEXT NOT NULL,
    computed_at_ms BIGINT NOT NULL,
    fetch_success_rate DOUBLE PRECISION,
    items_fetched INTEGER NOT NULL DEFAULT 0,
    items_inserted INTEGER NOT NULL DEFAULT 0,
    duplicate_rate DOUBLE PRECISION,
    process_success_rate DOUBLE PRECISION,
    resolved_token_rate DOUBLE PRECISION,
    attention_rate DOUBLE PRECISION,
    accepted_fact_rate DOUBLE PRECISION,
    brief_ready_rate DOUBLE PRECISION,
    median_lag_ms BIGINT,
    quality_score DOUBLE PRECISION,
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    projection_version TEXT NOT NULL,
    UNIQUE (source_id, window)
  );
  CREATE INDEX IF NOT EXISTS idx_news_source_quality_source_window ON news_source_quality_rows(source_id, window);
  ```

- [ ] **Step 4: Implement score formula as pure function**
  ```python
  def quality_score(metrics: Mapping[str, float]) -> float:
      score = (
          25 * metrics.get("fetch_success_rate", 0.0)
          + 15 * metrics.get("process_success_rate", 0.0)
          + 15 * metrics.get("resolved_token_rate", 0.0)
          + 15 * metrics.get("brief_ready_rate", 0.0)
          + 10 * (1 - metrics.get("duplicate_rate", 1.0))
          + 10 * metrics.get("normalized_freshness", 0.0)
          + 10 * metrics.get("useful_fact_or_context_rate", 0.0)
      )
      return round(max(0.0, min(100.0, score)), 2)
  ```

- [ ] **Step 5: Add repository aggregate/read/write methods**
  ```python
  def list_source_quality_inputs(self, *, window_ms: int, now_ms: int) -> list[dict[str, Any]]:
      window_start_ms = int(now_ms) - int(window_ms)
      rows = self.conn.execute(
          """
          SELECT
            sources.source_id,
            COUNT(fetch_runs.fetch_run_id)::int AS fetch_run_count,
            COUNT(fetch_runs.fetch_run_id) FILTER (WHERE fetch_runs.status = 'success')::int AS fetch_success_count,
            COALESCE(SUM(fetch_runs.fetched_count), 0)::int AS items_fetched,
            COALESCE(SUM(fetch_runs.inserted_count), 0)::int AS items_inserted,
            COALESCE(SUM(fetch_runs.duplicate_count), 0)::int AS items_duplicate,
            COUNT(items.news_item_id)::int AS item_count,
            COUNT(items.news_item_id) FILTER (WHERE items.lifecycle_status = 'processed')::int AS processed_item_count,
            COUNT(mentions.mention_id) FILTER (WHERE mentions.resolution_status IN ('exact_address', 'known_symbol', 'unique_by_context'))::int AS resolved_mention_count,
            COUNT(mentions.mention_id)::int AS mention_count,
            COUNT(facts.fact_candidate_id) FILTER (WHERE facts.validation_status = 'attention')::int AS attention_fact_count,
            COUNT(facts.fact_candidate_id) FILTER (WHERE facts.validation_status = 'accepted')::int AS accepted_fact_count,
            COUNT(facts.fact_candidate_id)::int AS fact_count,
            COUNT(briefs.news_item_id) FILTER (WHERE briefs.status = 'ready')::int AS ready_brief_count
          FROM news_sources AS sources
          LEFT JOIN news_fetch_runs AS fetch_runs
            ON fetch_runs.source_id = sources.source_id
           AND fetch_runs.started_at_ms >= %s
          LEFT JOIN news_items AS items
            ON items.source_id = sources.source_id
           AND items.published_at_ms >= %s
          LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
          LEFT JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
          LEFT JOIN news_item_agent_briefs AS briefs ON briefs.news_item_id = items.news_item_id
          GROUP BY sources.source_id
          """,
          (window_start_ms, window_start_ms),
      ).fetchall()
      return [dict(row) for row in rows]

  def replace_source_quality_rows(self, *, rows: Sequence[Mapping[str, Any]], commit: bool = True) -> None:
      for row in rows:
          self.conn.execute(
              """
              INSERT INTO news_source_quality_rows (
                row_id, source_id, window, computed_at_ms, fetch_success_rate,
                items_fetched, items_inserted, duplicate_rate, process_success_rate,
                resolved_token_rate, attention_rate, accepted_fact_rate, brief_ready_rate,
                median_lag_ms, quality_score, diagnostics_json, projection_version
              )
              VALUES (
                %(row_id)s, %(source_id)s, %(window)s, %(computed_at_ms)s, %(fetch_success_rate)s,
                %(items_fetched)s, %(items_inserted)s, %(duplicate_rate)s, %(process_success_rate)s,
                %(resolved_token_rate)s, %(attention_rate)s, %(accepted_fact_rate)s, %(brief_ready_rate)s,
                %(median_lag_ms)s, %(quality_score)s, %(diagnostics_json)s, %(projection_version)s
              )
              ON CONFLICT (source_id, window) DO UPDATE SET
                computed_at_ms = EXCLUDED.computed_at_ms,
                fetch_success_rate = EXCLUDED.fetch_success_rate,
                items_fetched = EXCLUDED.items_fetched,
                items_inserted = EXCLUDED.items_inserted,
                duplicate_rate = EXCLUDED.duplicate_rate,
                process_success_rate = EXCLUDED.process_success_rate,
                resolved_token_rate = EXCLUDED.resolved_token_rate,
                attention_rate = EXCLUDED.attention_rate,
                accepted_fact_rate = EXCLUDED.accepted_fact_rate,
                brief_ready_rate = EXCLUDED.brief_ready_rate,
                median_lag_ms = EXCLUDED.median_lag_ms,
                quality_score = EXCLUDED.quality_score,
                diagnostics_json = EXCLUDED.diagnostics_json,
                projection_version = EXCLUDED.projection_version
              """,
              _source_quality_payload(row),
          )
      if commit:
          self.conn.commit()
  ```

- [ ] **Step 6: Wire worker settings and registry**
  ```python
  class NewsSourceQualityProjectionWorkerSettings(PerWorkerSettings):
      interval_seconds: float = 60
      batch_size: int = 100
      advisory_lock_key: int = 2026052201
      wakes_on: tuple[str, ...] = ("news_item_written", "news_item_processed", "news_story_updated", "news_item_brief_updated")
  ```
  Add worker registry entry, factory construction, and architecture single-writer allowlist for `news_source_quality_rows`.

- [ ] **Step 7: Run worker/read-model checks**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/integration/domains/news_intel/test_news_source_quality_repository.py -q
  ```
  Expected: quality rows rebuild from facts/control rows, worker has unique advisory lock, architecture test lists exactly one runtime writer.

- [ ] **Step 8: Commit**
  ```bash
  git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py src/gmgn_twitter_intel/domains/news_intel/services/source_quality_projection.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_source_quality_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/platform/config/settings.py src/gmgn_twitter_intel/app/runtime/worker_registry.py src/gmgn_twitter_intel/app/runtime/worker_factories/news_intel.py tests/architecture/test_worker_runtime_contracts.py tests/unit tests/integration
  git commit -m "feat(news): add source quality projection"
  ```

## Task 7: API, Page Projection, Docs, And Operational Config

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_news.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_api_news_contract.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Add failing API filter tests**
  ```python
  def test_news_list_accepts_source_classification_filters(client):
      response = client.get("/api/news?provider_type=rss&source_role=specialist_media&trust_tier=standard&coverage_tag=crypto_market&content_class=regulatory_action")

      assert response.status_code == 200
      assert response.json()["items"] == []
  ```

- [ ] **Step 2: Run API filter test to verify failure**
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py::test_news_list_accepts_source_classification_filters -q
  ```
  Expected: fails because route/query model does not accept classification filters.

- [ ] **Step 3: Extend repository filters**
  ```sql
  if provider_type:
      filters.append("source_json ->> 'provider_type' = %s")
      filter_params.append(provider_type)
  if source_role:
      filters.append("source_json ->> 'source_role' = %s")
      filter_params.append(source_role)
  if coverage_tag:
      filters.append("source_json -> 'coverage_tags' ? %s")
      filter_params.append(coverage_tag)
  if content_class:
      filters.append("fact_lanes_json::text ILIKE %s")
      filter_params.append(f"%{content_class}%")
  ```

- [ ] **Step 4: Extend compact source payload**
  ```python
  {
      "source_id": item.get("source_id"),
      "provider_type": item.get("provider_type"),
      "source_domain": item.get("source_domain"),
      "source_name": item.get("source_name"),
      "source_role": item.get("source_role"),
      "trust_tier": item.get("trust_tier"),
      "coverage_tags": _json_list(item.get("coverage_tags_json")),
      "source_quality_status": item.get("source_quality_status"),
  }
  ```

- [ ] **Step 5: Extend source status payload**
  ```python
  {
      "source_id": row["source_id"],
      "provider_type": row["provider_type"],
      "source_role": row["source_role"],
      "trust_tier": row["trust_tier"],
      "coverage_tags": _json_list(row["coverage_tags_json"]),
      "quality": _latest_quality_payload(row),
      "item_count": row["item_count"],
      "enabled": row["enabled"],
  }
  ```

- [ ] **Step 6: Update docs and example config**
  ```yaml
  news_intel:
    sources:
      - source_id: coinbase-announcements
        provider_type: rss
        feed_url: "https://example.com/feed.xml"
        source_domain: coinbase.com
        source_name: Coinbase Announcements
        source_role: official_exchange
        trust_tier: official
        coverage_tags: ["crypto_exchange", "exchange_listing"]
        authority_scope:
          event_types: ["exchange_listing", "exchange_delisting", "maintenance"]
          domains: ["coinbase.com"]
        fetch_policy:
          max_items: 50
        context_policy:
          fetch_discussion: false
        cost_policy:
          class: free
  ```
  Also ensure example `workers.news_page_projection.wakes_on` includes `news_item_brief_updated`.

- [ ] **Step 7: Run API/docs-adjacent checks**
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_repository.py -q
  uv run pytest tests/architecture -q
  ```
  Expected: API filters are read-only, source payloads include classification, and architecture tests pass.

- [ ] **Step 8: Commit**
  ```bash
  git add src/gmgn_twitter_intel/app/surfaces/api/routes_news.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py docs config.example.yaml tests/unit tests/integration
  git commit -m "feat(news): expose source classification and quality"
  ```

## Task 8: Provider Wave With Disabled Defaults

**Files:**
- Create: `src/gmgn_twitter_intel/integrations/news_feeds/openbb_provider.py`
- Create: `src/gmgn_twitter_intel/integrations/news_feeds/telegram_public_provider.py`
- Create: `src/gmgn_twitter_intel/integrations/news_feeds/github_provider.py`
- Create: `src/gmgn_twitter_intel/integrations/news_feeds/community_provider.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py`
- Test: `tests/unit/integrations/news_feeds/test_openbb_provider.py`
- Test: `tests/unit/integrations/news_feeds/test_telegram_public_provider.py`
- Test: `tests/unit/integrations/news_feeds/test_github_provider.py`
- Test: `tests/unit/integrations/news_feeds/test_community_provider.py`

- [ ] **Step 1: Add fake-provider contract tests**
  ```python
  def assert_provider_result_contract(result):
      assert result.status_code in {200, 304}
      assert isinstance(result.observations, list)
      for observation in result.observations:
          assert observation.source_item_key
          assert observation.canonical_url
          assert observation.title
          assert isinstance(observation.raw_payload, dict)
  ```

- [ ] **Step 2: OpenBB provider test with fake SDK rows**
  ```python
  def test_openbb_provider_maps_company_news(fake_openbb_client):
      fake_openbb_client.rows = [{"id": "n1", "url": "https://example.com/n1", "title": "NVDA earnings", "published": 1_000, "symbols": ["NVDA"]}]
      result = OpenBBNewsProvider(client=fake_openbb_client).fetch(source=openbb_source_snapshot("NVDA"), since_ms=None, cursor={}, cache=empty_cache(), limit=10)

      assert result.observations[0].provider_tags == ["NVDA"]
      assert result.observations[0].raw_payload["symbols"] == ["NVDA"]
  ```

- [ ] **Step 3: Telegram provider test with fake public rows**
  ```python
  def test_telegram_public_provider_maps_messages_as_observations(fake_telegram_client):
      fake_telegram_client.messages = [{"id": "42", "url": "https://t.me/binance/42", "text": "Binance will list ABC", "date_ms": 1_000}]
      result = TelegramPublicNewsProvider(client=fake_telegram_client).fetch(source=telegram_source_snapshot("binance"), since_ms=None, cursor={}, cache=empty_cache(), limit=10)

      assert result.observations[0].source_item_key == "telegram:binance:42"
      assert result.observations[0].canonical_url.endswith("/42")
  ```

- [ ] **Step 4: GitHub provider test with fake release rows**
  ```python
  def test_github_provider_maps_releases(fake_github_client):
      fake_github_client.releases = [{"id": 7, "html_url": "https://github.com/org/repo/releases/tag/v1", "name": "v1", "body": "Mainnet upgrade"}]
      result = GitHubNewsProvider(client=fake_github_client).fetch(source=github_source_snapshot("org/repo"), since_ms=None, cursor={}, cache=empty_cache(), limit=10)

      assert result.observations[0].source_item_key == "github:org/repo:release:7"
      assert "developer_release" in result.observations[0].provider_tags
  ```

- [ ] **Step 5: Community provider test for context-only comments**
  ```python
  def test_community_provider_maps_comments_to_context(fake_reddit_client):
      fake_reddit_client.posts = [{"id": "p1", "url": "https://reddit.com/r/x/p1", "title": "ABC listing rumor", "text": "rumor"}]
      fake_reddit_client.comments = [{"id": "c1", "post_id": "p1", "body": "source?", "score": 12}]
      result = RedditNewsProvider(client=fake_reddit_client).fetch(source=reddit_source_snapshot(), since_ms=None, cursor={}, cache=empty_cache(), limit=10)

      assert result.observations[0].source_item_key == "reddit:p1"
      assert result.context_observations[0].context_type == "comment"
  ```

- [ ] **Step 6: Register providers but keep configs disabled by default**
  ```python
  registry.register(OpenBBNewsProvider.from_settings(settings))
  registry.register(TelegramPublicNewsProvider.from_settings(settings))
  registry.register(GitHubNewsProvider.from_settings(settings))
  registry.register(RedditNewsProvider.from_settings(settings))
  registry.register(HackerNewsProvider.from_settings(settings))
  ```
  Default config examples must be commented examples or disabled entries; active runtime config remains operator-owned in `~/.gmgn-twitter-intel/`.

- [ ] **Step 7: Run provider wave checks**
  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_openbb_provider.py tests/unit/integrations/news_feeds/test_telegram_public_provider.py tests/unit/integrations/news_feeds/test_github_provider.py tests/unit/integrations/news_feeds/test_community_provider.py tests/unit/integrations/news_feeds/test_provider_registry.py -q
  ```
  Expected: fake clients prove mapping, optional dependencies are lazy, no real network is used in unit tests.

- [ ] **Step 8: Commit**
  ```bash
  git add src/gmgn_twitter_intel/integrations/news_feeds src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py tests/unit/integrations/news_feeds
  git commit -m "feat(news): add disabled multi-source provider adapters"
  ```

## Task 9: Final Verification

- [ ] **Step 1: Run backend quality gates**
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  uv run pytest tests/unit/domains/news_intel -q
  uv run pytest tests/unit/integrations/news_feeds -q
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_providers_wiring.py tests/unit/test_api_news_contract.py -q
  uv run pytest tests/integration/domains/news_intel -q
  ```
  Expected: all selected backend tests pass.

- [ ] **Step 2: Run forbidden-boundary scans**
  ```bash
  rg -n "token_radar_rows|pulse_candidates|market_ticks" src/gmgn_twitter_intel/domains/news_intel src/gmgn_twitter_intel/app/surfaces/api/routes_news.py
  ```
  Expected: no News-domain writes to Token Radar, Pulse, or market tick tables.

- [ ] **Step 3: Run provider IO boundary scan**
  ```bash
  rg -n "FeedClient|Cryptopanic|OpenBB|Telegram|Reddit|HackerNews|GitHub" src/gmgn_twitter_intel/app/surfaces/api src/gmgn_twitter_intel/domains/news_intel/services
  ```
  Expected: no API route imports provider adapters; domain services may reference provider-neutral types only.

- [ ] **Step 4: Verify real config paths without exposing secrets**
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: report only the resolved config paths, enabled booleans, and source/worker counts.

- [ ] **Step 5: Commit docs/verification updates**
  ```bash
  git add docs/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md config.example.yaml
  git commit -m "docs(news): document source-chain classification"
  ```

## Acceptance Checklist

- [ ] Existing RSS/CryptoPanic ingestion works unchanged through the provider registry.
- [ ] New source classification fields are accepted by settings, persisted in DB, and visible in source status.
- [ ] `community` and `developer_signal` are valid source roles with explicit constraints.
- [ ] Context/comments/replies persist as `news_context_items` and do not mutate `news_items.body_text`.
- [ ] Specialist media, aggregators, social, and community sources cannot create `accepted` facts by role alone.
- [ ] Official sources require matching event type, domain/account/repo scope, production target identity, required slots, and acceptance-grade realis.
- [ ] `news_source_quality_rows` is rebuildable, deterministic, and has exactly one runtime writer.
- [ ] API routes remain read-only and do not import provider adapters or agent runners.
- [ ] `news_page_projection` wakes on `news_item_brief_updated` in defaults and example config.
- [ ] No News Intel code writes Token Radar, Pulse, or market fact tables.

## Execution Recommendation

Use subagent-driven execution for the foundation branch. The clean task split is:

1. Task 1 and Task 2 together: schema/config/repository facts.
2. Task 3 and Task 4 together: provider registry plus fetch persistence.
3. Task 5 alone: authority validation.
4. Task 6 alone: source quality worker/read model.
5. Task 7 alone: API/docs/ops contract.
6. Task 8 as one provider family per branch when foundation is green.
