# News Intel Kappa/CQRS Production Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented in `codex/news-intel-kappa-cqrs`, pending final review
**Date:** 2026-05-19
**Owning spec:** `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`
**Worktree:** `.worktrees/news-intel-kappa-cqrs/`
**Branch:** `codex/news-intel-kappa-cqrs`

**Goal:** Build a production-grade, independent News Intel page and backend loop inside `parallax`: fetch configured news feeds, persist raw/normalized news facts, extract token mentions, resolve identity through existing production interfaces, group stories deterministically, emit auditable fact candidates, and serve a rebuildable News page read model without touching Token Radar.

**Architecture:** Add a new `domains/news_intel` bounded context. PostgreSQL material facts are the only truth; `news_story_groups` and `news_page_rows` are rebuildable read models with single runtime writers. Workers use `LISTEN/NOTIFY` only as wake hints and always retain interval catch-up. The first cut avoids embedding/vector DB and avoids LLM truth: deterministic extraction and validation come first; future LLM fact extraction plugs into `news_fact_candidates` as candidate-only.

**Tech Stack:** Python 3.13, FastAPI, psycopg3, Alembic, PostgreSQL FTS/`pg_trgm`, `feedparser`, existing `eth-utils`/`solders` entity extraction primitives, React, TypeScript, TanStack Query, Vitest, pytest, ruff.

---

## Pre-flight

- [ ] Confirm spec approval for `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`.
- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/news-intel-kappa-cqrs -b codex/news-intel-kappa-cqrs main
  ```
- [ ] Verify worktree:
  ```bash
  cd .worktrees/news-intel-kappa-cqrs
  git branch --show-current
  git status --short
  git worktree list
  ```
  Expected: branch is `codex/news-intel-kappa-cqrs`; status is clean except generated lockfile changes after dependency install.
- [ ] Confirm real runtime config paths before any live-data debugging:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Do not print secrets.
- [ ] Baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  cd web && npm test -- --run
  ```
  Expected: pass, or record unrelated baseline failures before editing.

Known-failing baseline tests: none expected. If local Postgres/testcontainers cannot run, record the environment gap and run integration/e2e in the normal CI-capable environment before merge.

---

## Pre-implementation Simulation

On 2026-05-19, a local RSS simulation was run with `uv run --with feedparser python ...` using two in-memory RSS fetches:

- First fetch parsed two RSS entries and produced two `inserted` raw news items.
- Source reconciliation created the configured `example-rss` source before due-source work.
- Second fetch reused the same GUIDs and produced two `updated` rows, not duplicates.
- Canonicalization removed `utm_*` tracking while preserving meaningful query params.
- The simulated visible rows had lifecycle `raw`, confirming the minimal path can support “先看到新闻” before token/story/fact processing.

This simulation proves the V1 access shape is technically viable for RSS/Atom ingestion, but it is not a substitute for the repository, worker, API, and frontend tests below.

---

## Release Shape

Ship this as one branch with staged internal commits. The first working milestone is raw news visible; later commits add token/story/fact layers without changing the public route shape.

1. **Foundation commit:** dependency, config, architecture guards, empty domain skeleton.
2. **Storage commit:** Alembic migration, repositories, integration tests, raw news query.
3. **Fetch/API commit:** feed parser/client, `news_fetch` worker, source reconciliation, minimal raw `/api/news` rows.
4. **Processing commit:** entity/token mention extraction and identity status.
5. **Story/fact commit:** story grouping and deterministic fact candidates.
6. **Projection/API commit:** `news_page_rows`, API routes, bounded frontend polling. No news-specific SSE in V1.
7. **Frontend commit:** `/news` route and independent page.
8. **Docs/verification commit:** architecture docs, contracts, generated OpenAPI/types, verification artefact.

Do not merge a backend-only API shape that the frontend cannot render. Do not expose Token Radar integration in this branch.

---

## Core Design Decisions

- [ ] `news_intel` is a new domain, not part of `token_intel`. It owns news ingestion and news lifecycle; `token_intel` owns token identity and Token Radar.
- [ ] Use `feedparser` for RSS/Atom parsing. Do not write a custom XML parser.
- [ ] Do not add `trafilatura` or a full crawler in this cut. V1 stores feed title/summary/link and optional feed content; full article extraction is a later spec because it adds robots/crawl/backoff/copyright concerns.
- [ ] No embedding/vector DB. Use exact URL/content hash/title fingerprint plus Postgres `pg_trgm`/lexical/token overlap.
- [ ] LLM fact extraction is not part of V1. `news_fact_candidates` is designed to support a later LLM candidate producer, but V1 uses deterministic high-precision rules only.
- [ ] `news_story_groups` is a rebuildable read model written only by `NewsStoryProjectionWorker`.
- [ ] `news_page_rows` is a rebuildable read model written only by `NewsPageProjectionWorker`.
- [ ] HTTP handlers are read-only. They do not fetch feeds, resolve tokens, extract entities, group stories, or run fact validation.
- [ ] `unknown_attention` is a first-class lane. It is visible, not silently dropped, but it is not accepted fact identity.
- [ ] Configured sources are reconciled into `news_sources` by `news_fetch` before due-source claim. `config.yaml` is operator intent; DB rows are worker control-plane state.
- [ ] Provider IO never happens while holding a DB session or transaction. Workers snapshot due source rows, close the worker session, call the provider, then persist results in a new worker session.
- [ ] Fetch runs are control-plane audit rows, not product truth. Provider/news item facts may link to a fetch run for diagnostics, but deleting or pruning `news_fetch_runs` must never cascade-delete `news_provider_items`, `news_items`, or downstream facts.
- [ ] `news_fact_candidates` does not reference rebuildable story tables. Story association is derived through `news_story_members` in query/read-model code.
- [ ] `accepted` fact candidates require production-eligible target identity, required slots, acceptable realis, and authoritative source role. Specialist media and aggregators produce `attention` unless a later spec adds corroboration.
- [ ] `news_page_rows` replacement deletes rows in the projection scope before upsert, so truncation/rebuild and source removal cannot leave stale UI rows.
- [ ] `news_fetch` updates `etag`/`last_modified` only inside the same successful persistence path as provider/news items and fetch-run success; cache state must not be committed before item persistence.
- [ ] `news_page_projection` claims missing/stale/projection-version-mismatch rows, so a truncated read model is rebuilt progressively across batches.
- [ ] `news_item` content changes include body text in the content hash and clear stale story membership/page rows, forcing updated articles back through processing and grouping.
- [ ] News downstream workers listen on their `wakes_on` channels and also carry advisory lock keys so single-writer read-model ownership survives multi-instance deployments.

---

## File Structure

### Create

- `src/parallax/domains/news_intel/__init__.py`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `src/parallax/domains/news_intel/_constants.py`
- `src/parallax/domains/news_intel/providers.py`
- `src/parallax/domains/news_intel/interfaces.py`
- `src/parallax/domains/news_intel/types.py`
- `src/parallax/domains/news_intel/services/text_normalization.py`
- `src/parallax/domains/news_intel/services/feed_item_normalizer.py`
- `src/parallax/domains/news_intel/services/news_entity_extraction.py`
- `src/parallax/domains/news_intel/services/news_token_mentions.py`
- `src/parallax/domains/news_intel/services/news_story_grouping.py`
- `src/parallax/domains/news_intel/services/news_fact_candidates.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/domains/news_intel/repositories/__init__.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/queries/__init__.py`
- `src/parallax/domains/news_intel/queries/news_page_query.py`
- `src/parallax/domains/news_intel/runtime/__init__.py`
- `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- `src/parallax/domains/news_intel/runtime/news_story_projection_worker.py`
- `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- `src/parallax/integrations/news_feeds/__init__.py`
- `src/parallax/integrations/news_feeds/feed_client.py`
- `src/parallax/app/runtime/worker_factories/news_intel.py`
- `src/parallax/app/surfaces/api/routes_news.py`
- `src/parallax/platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py`
- `tests/architecture/test_news_intel_boundaries.py`
- `tests/unit/domains/news_intel/test_text_normalization.py`
- `tests/unit/domains/news_intel/test_feed_item_normalizer.py`
- `tests/unit/domains/news_intel/test_news_entity_extraction.py`
- `tests/unit/domains/news_intel/test_news_token_mentions.py`
- `tests/unit/domains/news_intel/test_news_story_grouping.py`
- `tests/unit/domains/news_intel/test_news_fact_candidates.py`
- `tests/unit/domains/news_intel/test_news_page_projection.py`
- `tests/unit/domains/news_intel/test_news_workers.py`
- `tests/integration/domains/news_intel/test_news_repository.py`
- `tests/unit/test_api_news_contract.py`
- `web/src/features/news/index.ts`
- `web/src/features/news/useNewsPage.ts`
- `web/src/features/news/NewsPage.tsx`
- `web/src/routes/news.route.tsx`
- `web/src/shared/model/newsIntel.ts`
- `web/tests/unit/features/news/useNewsPage.test.ts`
- `web/tests/component/features/news/NewsPage.test.tsx`

### Modify

- `pyproject.toml`
- `uv.lock`
- `src/parallax/platform/config/settings.py`
- `src/parallax/app/runtime/worker_registry.py`
- `src/parallax/app/runtime/worker_factories/__init__.py`
- `src/parallax/app/runtime/bootstrap.py`
- `src/parallax/app/runtime/wake_bus.py`
- `src/parallax/app/runtime/repository_session.py`
- `src/parallax/app/surfaces/api/http.py`
- `src/parallax/app/surfaces/api/schemas.py`
- `src/parallax/domains/token_intel/interfaces.py`
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `docs/generated/openapi.json`
- `web/src/app/AppRoutes.tsx`
- `web/src/routes/AppRoutes.tsx`
- `web/src/shared/routing/paths.ts`
- `web/src/lib/api/client.ts`
- `web/src/lib/types/openapi.ts`
- `web/src/lib/types/frontend-contracts.ts`
- `web/src/lib/types/index.ts`

### Explicitly Do Not Modify

- `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/parallax/domains/token_intel/services/token_radar_projection.py`
- `src/parallax/domains/pulse_lab/*`
- `src/parallax/domains/asset_market/runtime/market_tick_*`

If implementation appears to require edits there, stop and revisit the spec.

---

## Storage / Migration

Create Alembic revision `20260519_0064_news_intel_kappa_cqrs.py` after the current head. Confirm the current head before coding:

```bash
uv run alembic heads
```

### Tables

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS news_sources (
  source_id TEXT PRIMARY KEY,
  provider_type TEXT NOT NULL,
  feed_url TEXT NOT NULL,
  source_domain TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_role TEXT NOT NULL DEFAULT 'observed_source',
  trust_tier TEXT NOT NULL DEFAULT 'standard',
  managed_by_config BOOLEAN NOT NULL DEFAULT TRUE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  refresh_interval_seconds INTEGER NOT NULL DEFAULT 300,
  etag TEXT,
  last_modified TEXT,
  last_fetch_at_ms BIGINT,
  last_success_at_ms BIGINT,
  next_fetch_after_ms BIGINT NOT NULL DEFAULT 0,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  CHECK (provider_type IN ('rss', 'atom', 'json_feed')),
  CHECK (source_role IN ('official_exchange', 'official_regulator', 'official_protocol', 'official_issuer', 'specialist_media', 'aggregator', 'social', 'observed_source')),
  CHECK (trust_tier IN ('official', 'high', 'standard', 'low'))
);

CREATE TABLE IF NOT EXISTS news_fetch_runs (
  fetch_run_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
  started_at_ms BIGINT NOT NULL,
  finished_at_ms BIGINT NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  error TEXT,
  extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (status IN ('running', 'success', 'failed'))
);

CREATE TABLE IF NOT EXISTS news_provider_items (
  provider_item_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
  fetch_run_id TEXT REFERENCES news_fetch_runs(fetch_run_id) ON DELETE SET NULL,
  source_item_key TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  raw_payload_json JSONB NOT NULL,
  fetched_at_ms BIGINT NOT NULL,
  UNIQUE (source_id, source_item_key)
);

CREATE TABLE IF NOT EXISTS news_items (
  news_item_id TEXT PRIMARY KEY,
  provider_item_id TEXT NOT NULL REFERENCES news_provider_items(provider_item_id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
  source_domain TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  body_text TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT 'en',
  published_at_ms BIGINT NOT NULL,
  fetched_at_ms BIGINT NOT NULL,
  content_hash TEXT NOT NULL,
  title_fingerprint TEXT NOT NULL,
  lifecycle_status TEXT NOT NULL DEFAULT 'raw',
  processing_attempts INTEGER NOT NULL DEFAULT 0,
  processing_error TEXT,
  processed_at_ms BIGINT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed'))
);

CREATE INDEX IF NOT EXISTS idx_news_items_source_time ON news_items(source_id, published_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_url ON news_items(canonical_url);
CREATE INDEX IF NOT EXISTS idx_news_items_content_hash ON news_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_news_items_title_trgm ON news_items USING GIN (title gin_trgm_ops);

CREATE TABLE IF NOT EXISTS news_item_entities (
  entity_id TEXT PRIMARY KEY,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  span_start INTEGER NOT NULL,
  span_end INTEGER NOT NULL,
  text_surface TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  extraction_policy_version TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_news_item_entities_identity
  ON news_item_entities(news_item_id, entity_type, normalized_value, COALESCE(chain, ''), span_start, span_end);

CREATE TABLE IF NOT EXISTS news_token_mentions (
  mention_id TEXT PRIMARY KEY,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  entity_id TEXT REFERENCES news_item_entities(entity_id) ON DELETE SET NULL,
  observed_symbol TEXT,
  chain_id TEXT,
  address TEXT,
  resolution_status TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  display_symbol TEXT,
  display_name TEXT,
  reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  candidate_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_strength TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  created_at_ms BIGINT NOT NULL,
  CHECK (resolution_status IN ('exact_address', 'known_symbol', 'unique_by_context', 'ambiguous_symbol', 'unknown_attention', 'non_crypto', 'nil')),
  CHECK (evidence_strength IN ('strong', 'medium', 'weak'))
);

CREATE INDEX IF NOT EXISTS idx_news_token_mentions_item ON news_token_mentions(news_item_id);
CREATE INDEX IF NOT EXISTS idx_news_token_mentions_target ON news_token_mentions(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_news_token_mentions_status ON news_token_mentions(resolution_status);

CREATE TABLE IF NOT EXISTS news_story_groups (
  story_id TEXT PRIMARY KEY,
  policy_version TEXT NOT NULL,
  representative_title TEXT NOT NULL,
  canonical_url TEXT,
  first_seen_at_ms BIGINT NOT NULL,
  latest_seen_at_ms BIGINT NOT NULL,
  source_count INTEGER NOT NULL DEFAULT 0,
  item_count INTEGER NOT NULL DEFAULT 0,
  token_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  CHECK (status IN ('active', 'stale'))
);

CREATE TABLE IF NOT EXISTS news_story_members (
  story_id TEXT NOT NULL REFERENCES news_story_groups(story_id) ON DELETE CASCADE,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  match_reason TEXT NOT NULL,
  match_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY (story_id, news_item_id),
  CHECK (relation IN ('representative', 'same_story'))
);

CREATE INDEX IF NOT EXISTS idx_news_story_groups_latest ON news_story_groups(latest_seen_at_ms DESC);

CREATE TABLE IF NOT EXISTS news_fact_candidates (
  fact_candidate_id TEXT PRIMARY KEY,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  claim TEXT NOT NULL,
  realis TEXT NOT NULL,
  evidence_quote TEXT NOT NULL,
  evidence_span_start INTEGER NOT NULL,
  evidence_span_end INTEGER NOT NULL,
  source_role TEXT NOT NULL,
  required_slots_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  affected_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  validation_status TEXT NOT NULL,
  rejection_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  extraction_method TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  CHECK (realis IN ('actual', 'scheduled', 'official_proposed', 'reported_claim', 'opinion', 'rumor', 'generic', 'stale')),
  CHECK (validation_status IN ('accepted', 'rejected', 'attention'))
);

CREATE INDEX IF NOT EXISTS idx_news_fact_candidates_item ON news_fact_candidates(news_item_id);
CREATE INDEX IF NOT EXISTS idx_news_fact_candidates_status ON news_fact_candidates(validation_status);

CREATE TABLE IF NOT EXISTS news_page_rows (
  row_id TEXT PRIMARY KEY,
  news_item_id TEXT NOT NULL REFERENCES news_items(news_item_id) ON DELETE CASCADE,
  story_id TEXT,
  latest_at_ms BIGINT NOT NULL,
  lifecycle_status TEXT NOT NULL,
  headline TEXT NOT NULL,
  summary TEXT NOT NULL,
  source_domain TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  token_lanes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  fact_lanes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  story_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  computed_at_ms BIGINT NOT NULL,
  projection_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_page_rows_latest ON news_page_rows(latest_at_ms DESC, row_id DESC);
CREATE INDEX IF NOT EXISTS idx_news_page_rows_source ON news_page_rows(source_domain, latest_at_ms DESC);
```

### Downgrade

Drop in reverse dependency order:

```sql
DROP TABLE IF EXISTS news_page_rows;
DROP TABLE IF EXISTS news_fact_candidates;
DROP TABLE IF EXISTS news_story_members;
DROP TABLE IF EXISTS news_story_groups;
DROP TABLE IF EXISTS news_token_mentions;
DROP TABLE IF EXISTS news_item_entities;
DROP TABLE IF EXISTS news_items;
DROP TABLE IF EXISTS news_provider_items;
DROP TABLE IF EXISTS news_fetch_runs;
DROP TABLE IF EXISTS news_sources;
```

Do not drop `pg_trgm`; it is already used by search v2.

---

## Task 1: Dependency, Domain Skeleton, And Architecture Guards

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/parallax/domains/news_intel/*`
- Create: `tests/architecture/test_news_intel_boundaries.py`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Add `feedparser` dependency**

Add to `pyproject.toml`:

```toml
"feedparser>=6.0,<7.0",
```

Run:

```bash
uv lock
```

Expected: `uv.lock` updates with `feedparser` and transitive dependencies.

- [ ] **Step 2: Create domain skeleton**

Create empty package files:

```text
src/parallax/domains/news_intel/__init__.py
src/parallax/domains/news_intel/repositories/__init__.py
src/parallax/domains/news_intel/queries/__init__.py
src/parallax/domains/news_intel/runtime/__init__.py
```

Create `src/parallax/domains/news_intel/_constants.py`:

```python
NEWS_ENTITY_POLICY_VERSION = "news_entity_extraction_v1"
NEWS_TOKEN_MENTION_POLICY_VERSION = "news_token_mentions_v1"
NEWS_STORY_POLICY_VERSION = "news_story_grouping_v1"
NEWS_FACT_POLICY_VERSION = "news_fact_candidates_v1"
NEWS_PAGE_PROJECTION_VERSION = "news_page_rows_v1"
```

- [ ] **Step 3: Create domain architecture doc**

Create `src/parallax/domains/news_intel/ARCHITECTURE.md` with:

```markdown
# News Intel Architecture

News Intel owns configured news source ingestion, raw news item facts, deterministic entity/token mention extraction, deterministic story grouping, fact candidates, and the independent News page read model.

It does not write Token Radar, Pulse, market ticks, or token identity facts. Token identity is read through domain interfaces only. `news_story_groups` and `news_page_rows` are rebuildable read models with single runtime writers.

## Stage Map

| Stage | Owner | Writes | Invariant |
|-------|-------|--------|-----------|
| Fetch | `runtime/news_fetch_worker.py` | `news_fetch_runs`, `news_provider_items`, `news_items`, `news_sources` fetch state | Raw provider payload is preserved; provider item identity is idempotent. |
| Item processing | `runtime/news_item_process_worker.py` | `news_item_entities`, `news_token_mentions`, `news_fact_candidates` | Token identity is deterministic and candidates keep rejection reasons. |
| Story projection | `runtime/news_story_projection_worker.py` | `news_story_groups`, `news_story_members` | Story grouping is deterministic and stores match reasons. |
| Page projection | `runtime/news_page_projection_worker.py` | `news_page_rows` | Page rows are rebuildable and contain no hidden inference. |
| API/UI | `app/surfaces/api/routes_news.py`, `web/src/features/news` | none | Read-only surfaces. |

## Boundaries

- News workers never write `token_radar_rows`, Pulse tables, or market tick facts.
- API handlers never fetch feeds, resolve tokens, group stories, or extract facts.
- Unknown or ambiguous symbols stay visible in attention lanes and never become accepted fact identity.
```

- [ ] **Step 4: Add architecture boundary tests**

Create `tests/architecture/test_news_intel_boundaries.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEWS_SRC = ROOT / "src/parallax/domains/news_intel"


def _py_files() -> list[Path]:
    return [path for path in NEWS_SRC.rglob("*.py") if "__pycache__" not in path.parts]


def test_news_intel_does_not_import_token_radar_or_pulse_runtime() -> None:
    forbidden = (
        "domains.token_intel.runtime",
        "domains.token_intel.services.token_radar_projection",
        "domains.pulse_lab",
        "domains.asset_market.runtime.market_tick",
    )
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path} imports forbidden runtime dependency {needle}"


def test_news_intel_does_not_write_token_radar_or_pulse_tables() -> None:
    forbidden_sql = ("token_radar_rows", "pulse_candidates", "market_ticks")
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_sql:
            assert needle not in text, f"{path} mentions forbidden table {needle}"


def test_news_api_route_is_read_only() -> None:
    route = ROOT / "src/parallax/app/surfaces/api/routes_news.py"
    if not route.exists():
        return
    text = route.read_text(encoding="utf-8")
    forbidden = ("NewsFetchWorker", "NewsItemProcessWorker", "feedparser", "resolve(", "extract_")
    for needle in forbidden:
        assert needle not in text, f"routes_news.py must not run write-side work: {needle}"
```

Run:

```bash
uv run pytest tests/architecture/test_news_intel_boundaries.py -q
```

Expected: pass after skeleton exists.

- [ ] **Step 5: Update global architecture docs**

Modify `docs/ARCHITECTURE.md`:

- Add `domains/news_intel` to the top data-flow diagram after `ingestion/evidence` as an independent external-news lane.
- Add a domain table row: `domains/news_intel/` owns configured news source ingestion, news item facts, token mention observations, story grouping, fact candidates, and News page read model.
- Add `news_page_rows` and `news_story_groups` to the single-writer invariant list only as derived read models with named writers.

Run:

```bash
uv run pytest tests/architecture/test_news_intel_boundaries.py tests/architecture/test_src_domain_architecture.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/parallax/domains/news_intel docs/ARCHITECTURE.md tests/architecture/test_news_intel_boundaries.py
git commit -m "docs: add news intel domain skeleton"
```

---

## Task 2: Storage Migration And Repository

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py`
- Create: `src/parallax/domains/news_intel/types.py`
- Create: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Write failing repository integration tests**

Create `tests/integration/domains/news_intel/test_news_repository.py`:

```python
from __future__ import annotations

from parallax.domains.news_intel.repositories.news_repository import NewsRepository


def test_news_repository_upserts_source_and_item(pg_conn) -> None:
    repo = NewsRepository(pg_conn)
    now = 1_800_000_000_000

    repo.upsert_source(
        source_id="src-coindesk",
        provider_type="rss",
        feed_url="https://example.test/feed.xml",
        source_domain="example.test",
        source_name="Example",
        source_role="specialist_media",
        trust_tier="standard",
        refresh_interval_seconds=300,
        now_ms=now,
    )
    run_id = repo.start_fetch_run(source_id="src-coindesk", started_at_ms=now)
    provider_item_id = repo.upsert_provider_item(
        source_id="src-coindesk",
        fetch_run_id=run_id,
        source_item_key="guid-1",
        canonical_url="https://example.test/a",
        payload_hash="hash-1",
        raw_payload={"title": "Coinbase lists NEWX"},
        fetched_at_ms=now,
    )
    repo.upsert_news_item(
        news_item_id="news-1",
        provider_item_id=provider_item_id,
        source_id="src-coindesk",
        source_domain="example.test",
        canonical_url="https://example.test/a",
        title="Coinbase lists NEWX",
        summary="",
        body_text="",
        language="en",
        published_at_ms=now,
        fetched_at_ms=now,
        content_hash="content-1",
        title_fingerprint="coinbase lists newx",
        now_ms=now,
    )

    rows = repo.list_page_source_items(limit=10)
    assert rows[0]["news_item_id"] == "news-1"
    assert rows[0]["lifecycle_status"] == "raw"


def test_news_repository_rebuilds_page_rows(pg_conn) -> None:
    repo = NewsRepository(pg_conn)
    now = 1_800_000_000_000
    repo.upsert_source(
        source_id="src",
        provider_type="rss",
        feed_url="https://example.test/feed.xml",
        source_domain="example.test",
        source_name="Example",
        source_role="specialist_media",
        trust_tier="standard",
        refresh_interval_seconds=300,
        now_ms=now,
    )
    run_id = repo.start_fetch_run(source_id="src", started_at_ms=now)
    provider_item_id = repo.upsert_provider_item(
        source_id="src",
        fetch_run_id=run_id,
        source_item_key="guid-1",
        canonical_url="https://example.test/a",
        payload_hash="hash",
        raw_payload={"title": "Bitcoin ETF inflow"},
        fetched_at_ms=now,
    )
    repo.upsert_news_item(
        news_item_id="news-1",
        provider_item_id=provider_item_id,
        source_id="src",
        source_domain="example.test",
        canonical_url="https://example.test/a",
        title="Bitcoin ETF inflow",
        summary="ETF flow improved",
        body_text="",
        language="en",
        published_at_ms=now,
        fetched_at_ms=now,
        content_hash="content",
        title_fingerprint="bitcoin etf inflow",
        now_ms=now,
    )
    repo.replace_page_rows_for_items(
        news_item_ids=["news-1"],
        rows=[
            {
                "row_id": "row-news-1",
                "news_item_id": "news-1",
                "story_id": None,
                "latest_at_ms": now,
                "lifecycle_status": "raw",
                "headline": "Bitcoin ETF inflow",
                "summary": "ETF flow improved",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/a",
                "token_lanes": [],
                "fact_lanes": [],
                "story": {},
                "source": {"source_id": "src"},
                "computed_at_ms": now,
                "projection_version": "news_page_rows_v1",
            }
        ]
    )

    page = repo.list_news_page_rows(limit=10)
    assert page[0]["row_id"] == "row-news-1"
    assert page[0]["headline"] == "Bitcoin ETF inflow"
```

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: fail because migration/repository do not exist.

- [ ] **Step 2: Add migration**

Create the Alembic file with the SQL in the Storage / Migration section. Use SQLAlchemy `op.execute(...)` blocks matching existing migrations.

Run:

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: fail because repository methods do not exist.

- [ ] **Step 3: Add repository types**

Create `src/parallax/domains/news_intel/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsSourceConfig:
    source_id: str
    provider_type: str
    feed_url: str
    source_domain: str
    source_name: str
    source_role: str = "observed_source"
    trust_tier: str = "standard"
    enabled: bool = True
    refresh_interval_seconds: int = 300


@dataclass(frozen=True, slots=True)
class NormalizedNewsItem:
    source_item_key: str
    canonical_url: str
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    raw_payload: dict[str, Any]
```

- [ ] **Step 4: Implement `NewsRepository`**

Create `src/parallax/domains/news_intel/repositories/news_repository.py` with methods used in tests:

```python
from __future__ import annotations

import hashlib
import asyncio
import json
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


class NewsRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def upsert_source(
        self,
        *,
        source_id: str,
        provider_type: str,
        feed_url: str,
        source_domain: str,
        source_name: str,
        source_role: str,
        trust_tier: str,
        refresh_interval_seconds: int,
        now_ms: int,
        enabled: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO news_sources (
              source_id, provider_type, feed_url, source_domain, source_name, source_role,
              trust_tier, managed_by_config, enabled, refresh_interval_seconds, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
              provider_type = EXCLUDED.provider_type,
              feed_url = EXCLUDED.feed_url,
              source_domain = EXCLUDED.source_domain,
              source_name = EXCLUDED.source_name,
              source_role = EXCLUDED.source_role,
              trust_tier = EXCLUDED.trust_tier,
              managed_by_config = TRUE,
              enabled = EXCLUDED.enabled,
              refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            (
                source_id,
                provider_type,
                feed_url,
                source_domain,
                source_name,
                source_role,
                trust_tier,
                bool(enabled),
                int(refresh_interval_seconds),
                int(now_ms),
                int(now_ms),
            ),
        )

    def start_fetch_run(self, *, source_id: str, started_at_ms: int) -> str:
        fetch_run_id = _stable_id("news-fetch-run", source_id, str(started_at_ms))
        self.conn.execute(
            """
            INSERT INTO news_fetch_runs (fetch_run_id, source_id, started_at_ms, status)
            VALUES (%s, %s, %s, 'running')
            ON CONFLICT (fetch_run_id) DO NOTHING
            """,
            (fetch_run_id, source_id, int(started_at_ms)),
        )
        return fetch_run_id

    def finish_fetch_run(
        self,
        *,
        fetch_run_id: str,
        finished_at_ms: int,
        status: str,
        fetched_count: int = 0,
        inserted_count: int = 0,
        updated_count: int = 0,
        duplicate_count: int = 0,
        http_status: int | None = None,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_fetch_runs
               SET finished_at_ms = %s,
                   status = %s,
                   fetched_count = %s,
                   inserted_count = %s,
                   updated_count = %s,
                   duplicate_count = %s,
                   http_status = %s,
                   error = %s,
                   extra_json = %s::jsonb
             WHERE fetch_run_id = %s
            """,
            (
                int(finished_at_ms),
                status,
                int(fetched_count),
                int(inserted_count),
                int(updated_count),
                int(duplicate_count),
                http_status,
                error,
                json.dumps(extra or {}, sort_keys=True),
                fetch_run_id,
            ),
        )

    def upsert_provider_item(
        self,
        *,
        source_id: str,
        fetch_run_id: str,
        source_item_key: str,
        canonical_url: str,
        payload_hash: str,
        raw_payload: dict[str, Any],
        fetched_at_ms: int,
    ) -> str:
        provider_item_id = _stable_id("news-provider-item", source_id, source_item_key)
        self.conn.execute(
            """
            INSERT INTO news_provider_items (
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_id, source_item_key) DO UPDATE SET
              fetch_run_id = EXCLUDED.fetch_run_id,
              canonical_url = EXCLUDED.canonical_url,
              payload_hash = EXCLUDED.payload_hash,
              raw_payload_json = EXCLUDED.raw_payload_json,
              fetched_at_ms = EXCLUDED.fetched_at_ms
            """,
            (
                provider_item_id,
                source_id,
                fetch_run_id,
                source_item_key,
                canonical_url,
                payload_hash,
                json.dumps(raw_payload, sort_keys=True),
                int(fetched_at_ms),
            ),
        )
        return provider_item_id

    def upsert_news_item(
        self,
        *,
        news_item_id: str,
        provider_item_id: str,
        source_id: str,
        source_domain: str,
        canonical_url: str,
        title: str,
        summary: str,
        body_text: str,
        language: str,
        published_at_ms: int,
        fetched_at_ms: int,
        content_hash: str,
        title_fingerprint: str,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO news_items (
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, summary, body_text, language, published_at_ms, fetched_at_ms,
              content_hash, title_fingerprint, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (news_item_id) DO UPDATE SET
              canonical_url = EXCLUDED.canonical_url,
              title = EXCLUDED.title,
              summary = EXCLUDED.summary,
              body_text = EXCLUDED.body_text,
              language = EXCLUDED.language,
              published_at_ms = EXCLUDED.published_at_ms,
              fetched_at_ms = EXCLUDED.fetched_at_ms,
              content_hash = EXCLUDED.content_hash,
              title_fingerprint = EXCLUDED.title_fingerprint,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            (
                news_item_id,
                provider_item_id,
                source_id,
                source_domain,
                canonical_url,
                title,
                summary,
                body_text,
                language,
                int(published_at_ms),
                int(fetched_at_ms),
                content_hash,
                title_fingerprint,
                int(now_ms),
                int(now_ms),
            ),
        )

    def list_page_source_items(self, *, limit: int) -> list[dict[str, Any]]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                  FROM news_items
              ORDER BY published_at_ms DESC, news_item_id DESC
                 LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            return list(cur.fetchall())

    def replace_page_rows_for_items(self, *, news_item_ids: list[str], rows: list[dict[str, Any]]) -> None:
        if news_item_ids:
            placeholders = ",".join("%s" for _ in news_item_ids)
            self.conn.execute(
                f"DELETE FROM news_page_rows WHERE news_item_id IN ({placeholders})",
                [str(item) for item in news_item_ids],
            )
        if not rows:
            return
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO news_page_rows (
                  row_id, news_item_id, story_id, latest_at_ms, lifecycle_status,
                  headline, summary, source_domain, canonical_url, token_lanes_json,
                  fact_lanes_json, story_json, source_json, computed_at_ms, projection_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (row_id) DO UPDATE SET
                  latest_at_ms = EXCLUDED.latest_at_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  source_domain = EXCLUDED.source_domain,
                  canonical_url = EXCLUDED.canonical_url,
                  token_lanes_json = EXCLUDED.token_lanes_json,
                  fact_lanes_json = EXCLUDED.fact_lanes_json,
                  story_json = EXCLUDED.story_json,
                  source_json = EXCLUDED.source_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                (
                    row["row_id"],
                    row["news_item_id"],
                    row.get("story_id"),
                    int(row["latest_at_ms"]),
                    row["lifecycle_status"],
                    row["headline"],
                    row["summary"],
                    row["source_domain"],
                    row["canonical_url"],
                    json.dumps(row.get("token_lanes") or [], sort_keys=True),
                    json.dumps(row.get("fact_lanes") or [], sort_keys=True),
                    json.dumps(row.get("story") or {}, sort_keys=True),
                    json.dumps(row.get("source") or {}, sort_keys=True),
                    int(row["computed_at_ms"]),
                    row["projection_version"],
                ),
            )

    def list_news_page_rows(self, *, limit: int) -> list[dict[str, Any]]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                  FROM news_page_rows
              ORDER BY latest_at_ms DESC, row_id DESC
                 LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            return list(cur.fetchall())


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Extend repository session**

Modify `src/parallax/app/runtime/repository_session.py` to add `NewsRepository` as a normal `RepositorySession` dataclass field. Do not add a method property; the current session is a frozen dataclass and repositories are constructed in `repositories_for_connection`.

```python
from parallax.domains.news_intel.repositories.news_repository import NewsRepository


@dataclass(frozen=True, slots=True)
class RepositorySession:
    ...
    news: NewsRepository


def repositories_for_connection(conn: Any) -> RepositorySession:
    return RepositorySession(
        ...
        news=NewsRepository(conn),
    )
```

Use the exact class/session style already present in the file.

- [ ] **Step 6: Run migration/repository tests**

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -q
uv run pytest tests/unit/test_postgres_schema_runtime.py tests/unit/test_worker_settings.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/parallax/platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py src/parallax/domains/news_intel/types.py src/parallax/domains/news_intel/repositories src/parallax/app/runtime/repository_session.py tests/integration/domains/news_intel/test_news_repository.py
git commit -m "feat: add news intel storage foundation"
```

---

## Task 3: Feed Client And Normalization

**Files:**
- Create: `src/parallax/integrations/news_feeds/feed_client.py`
- Create: `src/parallax/domains/news_intel/services/text_normalization.py`
- Create: `src/parallax/domains/news_intel/services/feed_item_normalizer.py`
- Test: `tests/unit/domains/news_intel/test_text_normalization.py`
- Test: `tests/unit/domains/news_intel/test_feed_item_normalizer.py`

- [ ] **Step 1: Write failing text normalization tests**

Create `tests/unit/domains/news_intel/test_text_normalization.py`:

```python
from parallax.domains.news_intel.services.text_normalization import (
    canonicalize_url,
    clean_news_text,
    content_hash,
    title_fingerprint,
)


def test_clean_news_text_strips_html_boilerplate_and_urls() -> None:
    raw = "<p>Bitcoin ETF sees inflow.</p><p>Read more: https://example.test/a</p>"
    assert clean_news_text(raw) == "Bitcoin ETF sees inflow."


def test_canonicalize_url_removes_tracking_and_trailing_slash() -> None:
    assert (
        canonicalize_url("HTTPS://Example.Test/a/?utm_source=x&b=2&a=1")
        == "https://example.test/a?a=1&b=2"
    )


def test_title_fingerprint_normalizes_case_and_punctuation() -> None:
    assert title_fingerprint(" Coinbase lists NEWX! ") == "coinbase lists newx"


def test_content_hash_is_stable() -> None:
    assert content_hash(title="A", summary="B", canonical_url="https://x") == content_hash(
        title=" A ", summary="B", canonical_url="https://x"
    )
```

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_text_normalization.py -q
```

Expected: fail.

- [ ] **Step 2: Implement text normalization**

Create `src/parallax/domains/news_intel/services/text_normalization.py`:

```python
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_HTML_BREAK_RE = re.compile(r"(?is)</?(?:p|div|li|ul|ol|blockquote|h[1-6]|br)[^>]*>")
_HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_BOILERPLATE_TAIL_RE = re.compile(
    r"\b(?:Related|More News|Read more|Continue reading|Sign up|Subscribe|Follow us|Watch live|Click here)\b\s*:?.*$",
    re.IGNORECASE,
)


def clean_news_text(value: object, *, max_chars: int = 4000) -> str:
    text = html.unescape(str(value or ""))
    if not text.strip():
        return ""
    text = _HTML_BREAK_RE.sub("\n", text)
    text = _HTML_TAG_RE.sub(" ", text)
    segments: list[str] = []
    for raw_segment in re.split(r"[\r\n]+", text):
        segment = _normalize_space(_URL_RE.sub("", _BOILERPLATE_TAIL_RE.sub("", raw_segment)))
        if segment:
            segments.append(segment)
    cleaned = _normalize_space(" ".join(segments))
    return cleaned[:max(1, int(max_chars))].strip()


def canonicalize_url(url: object) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    filtered = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not key.lower().startswith("utm_")
    ]
    filtered.sort(key=lambda item: (item[0], item[1]))
    return urlunsplit((scheme, netloc, path, urlencode(filtered, doseq=True), ""))


def title_fingerprint(title: object) -> str:
    return re.sub(r"\W+", " ", str(title or "").casefold()).strip()


def content_hash(*, title: str, summary: str, canonical_url: str) -> str:
    base = "|".join(
        (
            title_fingerprint(title),
            title_fingerprint(summary),
            canonicalize_url(canonical_url),
        )
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _normalize_space(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()
```

- [ ] **Step 3: Write failing feed normalizer tests**

Create `tests/unit/domains/news_intel/test_feed_item_normalizer.py`:

```python
from parallax.domains.news_intel.services.feed_item_normalizer import normalize_feed_entry


def test_normalize_feed_entry_uses_guid_or_link_as_source_key() -> None:
    row = normalize_feed_entry(
        source_domain="example.test",
        entry={
            "id": "guid-1",
            "link": "https://example.test/a?utm_source=x",
            "title": "<b>Coinbase lists NEWX</b>",
            "summary": "Trading starts today.",
            "published_parsed": (2026, 5, 19, 1, 2, 3, 0, 0, 0),
        },
        fetched_at_ms=1_800_000_000_000,
    )
    assert row.source_item_key == "guid-1"
    assert row.canonical_url == "https://example.test/a"
    assert row.title == "Coinbase lists NEWX"
    assert row.published_at_ms > 0


def test_normalize_feed_entry_rejects_missing_title_or_url() -> None:
    assert normalize_feed_entry(source_domain="example.test", entry={"title": ""}, fetched_at_ms=1) is None
```

- [ ] **Step 4: Implement feed normalizer**

Create `src/parallax/domains/news_intel/services/feed_item_normalizer.py`:

```python
from __future__ import annotations

import calendar
from typing import Any

from parallax.domains.news_intel.types import NormalizedNewsItem

from .text_normalization import canonicalize_url, clean_news_text


def normalize_feed_entry(
    *,
    source_domain: str,
    entry: dict[str, Any],
    fetched_at_ms: int,
) -> NormalizedNewsItem | None:
    title = clean_news_text(entry.get("title"), max_chars=300)
    canonical_url = canonicalize_url(entry.get("link") or entry.get("href") or "")
    if not title or not canonical_url:
        return None
    source_item_key = str(entry.get("id") or entry.get("guid") or canonical_url).strip()
    if not source_item_key:
        return None
    summary = clean_news_text(entry.get("summary") or entry.get("description") or "", max_chars=900)
    body_text = clean_news_text(_content_value(entry), max_chars=4000)
    published_at_ms = _published_ms(entry, fallback_ms=fetched_at_ms)
    return NormalizedNewsItem(
        source_item_key=source_item_key,
        canonical_url=canonical_url,
        title=title,
        summary=summary,
        body_text=body_text,
        language=str(entry.get("language") or "en").strip().lower() or "en",
        published_at_ms=published_at_ms,
        raw_payload=dict(entry),
    )


def _content_value(entry: dict[str, Any]) -> object:
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return first.get("value") or ""
    return entry.get("content") or ""


def _published_ms(entry: dict[str, Any], *, fallback_ms: int) -> int:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return int(calendar.timegm(parsed[:9]) * 1000)
    return int(fallback_ms)
```

- [ ] **Step 5: Add feed client**

Create `src/parallax/integrations/news_feeds/feed_client.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import feedparser
import httpx


@dataclass(frozen=True, slots=True)
class FeedFetchResult:
    status_code: int
    entries: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool = False


class NewsFeedClient:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = float(timeout_seconds)

    def fetch(self, *, url: str, etag: str | None = None, last_modified: str | None = None) -> FeedFetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
        if response.status_code == 304:
            return FeedFetchResult(
                status_code=response.status_code,
                entries=[],
                etag=response.headers.get("etag") or etag,
                last_modified=response.headers.get("last-modified") or last_modified,
                not_modified=True,
            )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        entries = [dict(entry) for entry in parsed.entries]
        return FeedFetchResult(
            status_code=response.status_code,
            entries=entries,
            etag=response.headers.get("etag") or getattr(parsed, "etag", None),
            last_modified=response.headers.get("last-modified") or getattr(parsed, "modified", None),
            not_modified=False,
        )
```

- [ ] **Step 6: Run focused tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_text_normalization.py tests/unit/domains/news_intel/test_feed_item_normalizer.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/parallax/integrations/news_feeds src/parallax/domains/news_intel/services/text_normalization.py src/parallax/domains/news_intel/services/feed_item_normalizer.py tests/unit/domains/news_intel/test_text_normalization.py tests/unit/domains/news_intel/test_feed_item_normalizer.py
git commit -m "feat: add news feed parsing and normalization"
```

---

## Task 4: News Fetch Worker And Config

**Files:**
- Modify: `src/parallax/platform/config/settings.py`
- Create: `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- Create: `src/parallax/app/runtime/worker_factories/news_intel.py`
- Modify: `src/parallax/app/runtime/worker_registry.py`
- Modify: `src/parallax/app/runtime/worker_factories/__init__.py`
- Modify: `src/parallax/app/runtime/bootstrap.py`
- Modify: `src/parallax/domains/news_intel/queries/news_page_query.py`
- Create: `src/parallax/app/surfaces/api/routes_news.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/unit/test_worker_settings.py`
- Test: `tests/unit/test_api_news_contract.py`

- [ ] **Step 1: Write failing worker setting test**

Extend `tests/unit/test_worker_settings.py`:

```python
def test_news_workers_have_defaults() -> None:
    from parallax.platform.config.settings import WorkersSettings

    settings = WorkersSettings()
    assert settings.news_fetch.interval_seconds > 0
    assert settings.news_item_process.wakes_on == ("news_item_written",)
    assert "news_story_updated" in settings.news_page_projection.wakes_on
```

Run:

```bash
uv run pytest tests/unit/test_worker_settings.py::test_news_workers_have_defaults -q
```

Expected: fail.

- [ ] **Step 2: Add worker settings and news source config**

Modify `settings.py`:

```python
class NewsSourceSettings(BaseModel):
    source_id: str
    provider_type: str = "rss"
    feed_url: str
    source_domain: str
    source_name: str
    source_role: str = "observed_source"
    trust_tier: str = "standard"
    enabled: bool = True
    refresh_interval_seconds: int = Field(default=300, ge=30)


class NewsIntelSettings(BaseModel):
    enabled: bool = False
    sources: tuple[NewsSourceSettings, ...] = ()

    @field_validator("sources", mode="before")
    @classmethod
    def parse_sources(cls, value: Any) -> tuple[NewsSourceSettings, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        return (value,)


class NewsFetchWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    timeout_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=10, ge=1)
    advisory_lock_key: int = 2026051901


class NewsItemProcessWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=30.0, ge=0)
    timeout_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    advisory_lock_key: int = 2026051902
    wakes_on: tuple[str, ...] = ("news_item_written",)

    @field_validator("wakes_on", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class NewsStoryProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=45.0, ge=0)
    timeout_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=200, ge=1)
    advisory_lock_key: int = 2026051903
    wakes_on: tuple[str, ...] = ("news_item_processed",)

    @field_validator("wakes_on", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class NewsPageProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=30.0, ge=0)
    timeout_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=500, ge=1)
    advisory_lock_key: int = 2026051904
    wakes_on: tuple[str, ...] = ("news_item_written", "news_item_processed", "news_story_updated")

    @field_validator("wakes_on", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))
```

Add to `Settings`:

```python
news_intel: NewsIntelSettings = Field(default_factory=NewsIntelSettings)
```

Add to `WorkersSettings`:

```python
news_fetch: NewsFetchWorkerSettings = Field(default_factory=NewsFetchWorkerSettings)
news_item_process: NewsItemProcessWorkerSettings = Field(default_factory=NewsItemProcessWorkerSettings)
news_story_projection: NewsStoryProjectionWorkerSettings = Field(default_factory=NewsStoryProjectionWorkerSettings)
news_page_projection: NewsPageProjectionWorkerSettings = Field(default_factory=NewsPageProjectionWorkerSettings)
```

Add default YAML blocks in `default_workers_yaml()`.

- [ ] **Step 3: Add source reconciliation contract**

`news_fetch` must call a repository method before claiming due work:

```python
def reconcile_configured_sources(self, *, sources: tuple[NewsSourceConfig, ...], now_ms: int) -> None:
    configured_ids = {source.source_id for source in sources}
    for source in sources:
        self.upsert_source(
            source_id=source.source_id,
            provider_type=source.provider_type,
            feed_url=source.feed_url,
            source_domain=source.source_domain,
            source_name=source.source_name,
            source_role=source.source_role,
            trust_tier=source.trust_tier,
            refresh_interval_seconds=source.refresh_interval_seconds,
            enabled=source.enabled,
            now_ms=now_ms,
        )
    self.disable_unconfigured_sources(configured_source_ids=sorted(configured_ids), now_ms=now_ms)
```

`disable_unconfigured_sources` must run `UPDATE news_sources SET enabled=false, updated_at_ms=%s WHERE managed_by_config=true AND NOT (source_id = ANY(%s))` so manually inserted audit/source rows are not unexpectedly disabled. Do not delete source rows; old fetch/item rows remain audit history. Add a focused repository test:

```python
def test_reconcile_configured_sources_disables_removed_sources(pg_conn) -> None:
    repo = NewsRepository(pg_conn)
    repo.reconcile_configured_sources(sources=(_source("a"), _source("b")), now_ms=100)
    repo.reconcile_configured_sources(sources=(_source("a"),), now_ms=200)
    assert {row["source_id"]: row["enabled"] for row in repo.list_sources_for_status()} == {"a": True, "b": False}


def _source(source_id: str) -> NewsSourceConfig:
    return NewsSourceConfig(
        source_id=source_id,
        provider_type="rss",
        feed_url=f"https://example.test/{source_id}.xml",
        source_domain="example.test",
        source_name=source_id.upper(),
        source_role="specialist_media",
        trust_tier="standard",
        enabled=True,
        refresh_interval_seconds=300,
    )
```

- [ ] **Step 4: Extend `WakeBus`**

Modify `src/parallax/app/runtime/wake_bus.py`:

```python
def notify_news_item_written(self, *, source_id: str, count: int) -> None:
    self._notify("news_item_written", {"source_id": str(source_id), "count": int(count)})


def notify_news_item_processed(self, *, count: int) -> None:
    self._notify("news_item_processed", {"count": int(count)})


def notify_news_story_updated(self, *, count: int) -> None:
    self._notify("news_story_updated", {"count": int(count)})
```

- [ ] **Step 5: Write failing fetch worker unit test**

Create `tests/unit/domains/news_intel/test_news_workers.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from parallax.domains.news_intel.types import NewsSourceConfig


@dataclass
class FakeFeedClient:
    entries: list[dict]

    def fetch(self, *, url: str, etag: str | None = None, last_modified: str | None = None):
        return type(
            "Result",
            (),
            {
                "status_code": 200,
                "entries": self.entries,
                "etag": "e1",
                "last_modified": None,
                "not_modified": False,
            },
        )()


class FakeRepo:
    def __init__(self) -> None:
        self.sources = []
        self.items = []
        self.finished = []

    def reconcile_configured_sources(self, *, sources, now_ms: int):
        self.sources.extend(sources)

    def due_sources(self, *, limit: int, now_ms: int):
        return [
            {
                "source_id": "src",
                "provider_type": "rss",
                "feed_url": "https://example.test/feed.xml",
                "source_domain": "example.test",
                "source_name": "Example",
                "source_role": "specialist_media",
                "trust_tier": "standard",
                "etag": None,
                "last_modified": None,
            }
        ]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int) -> str:
        return "run-1"

    def upsert_provider_item(self, **kwargs):
        return "provider-item-1"

    def upsert_news_item(self, **kwargs):
        self.items.append(kwargs)

    def finish_fetch_run(self, **kwargs):
        self.finished.append(kwargs)

    def mark_source_success(self, **kwargs):
        pass


def test_news_fetch_worker_persists_feed_items() -> None:
    repo = FakeRepo()
    worker = NewsFetchWorker(
        name="news_fetch",
        settings=SimpleNamespace(enabled=True, interval_seconds=60.0, timeout_seconds=30.0),
        db=None,
        telemetry=None,
        repository_session=lambda: FakeSession(repo),
        configured_sources=(NewsSourceConfig(
            source_id="src",
            provider_type="rss",
            feed_url="https://example.test/feed.xml",
            source_domain="example.test",
            source_name="Example",
            source_role="specialist_media",
            trust_tier="standard",
            enabled=True,
            refresh_interval_seconds=300,
        ),),
        feed_client=FakeFeedClient(
            entries=[
                {
                    "id": "guid-1",
                    "link": "https://example.test/a",
                    "title": "Coinbase lists NEWX",
                    "summary": "Trading starts today.",
                }
            ]
        ),
        wake_bus=None,
        batch_size=10,
        clock_ms=lambda: 1_800_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.processed == 1
    assert repo.sources
    assert repo.items[0]["title"] == "Coinbase lists NEWX"
    assert repo.finished[0]["status"] == "success"


class FakeSession:
    def __init__(self, repo: FakeRepo) -> None:
        self.news = repo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 6: Implement `NewsFetchWorker`**

Create `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.services.feed_item_normalizer import normalize_feed_entry
from parallax.domains.news_intel.services.text_normalization import content_hash, title_fingerprint


class NewsFetchWorker(WorkerBase):
    name = "news_fetch"

    def __init__(
        self,
        *,
        repository_session,
        configured_sources,
        feed_client,
        wake_bus,
        batch_size: int,
        clock_ms: Callable[[], int],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.repository_session = repository_session
        self.configured_sources = tuple(configured_sources or ())
        self.feed_client = feed_client
        self.wake_bus = wake_bus
        self.batch_size = max(1, int(batch_size))
        self.clock_ms = clock_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self) -> WorkerResult:
        now_ms = int(self.clock_ms())
        processed = 0
        with self.repository_session() as repos:
            repos.news.reconcile_configured_sources(sources=self.configured_sources, now_ms=now_ms)
            due_sources = list(repos.news.due_sources(limit=self.batch_size, now_ms=now_ms))
        for source in due_sources:
            processed += self._fetch_source(source=source, now_ms=now_ms)
        return WorkerResult(processed=processed, details={"sources_checked": processed})

    def _fetch_source(self, *, source: dict, now_ms: int) -> int:
        source_id = str(source["source_id"])
        with self.repository_session() as repos:
            run_id = repos.news.start_fetch_run(source_id=source_id, started_at_ms=now_ms)
        inserted = 0
        try:
            result = self.feed_client.fetch(
                url=str(source["feed_url"]),
                etag=source.get("etag"),
                last_modified=source.get("last_modified"),
            )
            for entry in result.entries:
                item = normalize_feed_entry(
                    source_domain=str(source["source_domain"]),
                    entry=entry,
                    fetched_at_ms=now_ms,
                )
                if item is None:
                    continue
                payload_hash = _json_hash(item.raw_payload)
                news_item_id = _stable_id("news-item", source_id, item.source_item_key)
                with self.repository_session() as repos:
                    provider_item_id = repos.news.upsert_provider_item(
                        source_id=source_id,
                        fetch_run_id=run_id,
                        source_item_key=item.source_item_key,
                        canonical_url=item.canonical_url,
                        payload_hash=payload_hash,
                        raw_payload=item.raw_payload,
                        fetched_at_ms=now_ms,
                    )
                    repos.news.upsert_news_item(
                        news_item_id=news_item_id,
                        provider_item_id=provider_item_id,
                        source_id=source_id,
                        source_domain=str(source["source_domain"]),
                        canonical_url=item.canonical_url,
                        title=item.title,
                        summary=item.summary,
                        body_text=item.body_text,
                        language=item.language,
                        published_at_ms=item.published_at_ms,
                        fetched_at_ms=now_ms,
                        content_hash=content_hash(
                            title=item.title,
                            summary=item.summary or item.body_text,
                            canonical_url=item.canonical_url,
                        ),
                        title_fingerprint=title_fingerprint(item.title),
                        now_ms=now_ms,
                    )
                inserted += 1
            with self.repository_session() as repos:
                repos.news.finish_fetch_run(
                    fetch_run_id=run_id,
                    finished_at_ms=now_ms,
                    status="success",
                    fetched_count=len(result.entries),
                    inserted_count=inserted,
                    http_status=result.status_code,
                )
                repos.news.mark_source_success(
                    source_id=source_id,
                    etag=result.etag,
                    last_modified=result.last_modified,
                    next_fetch_after_ms=now_ms + int(source.get("refresh_interval_seconds") or 300) * 1000,
                    now_ms=now_ms,
                )
            if inserted and self.wake_bus is not None:
                self.wake_bus.notify_news_item_written(source_id=source_id, count=inserted)
            return inserted
        except Exception as exc:
            with self.repository_session() as repos:
                repos.news.finish_fetch_run(
                    fetch_run_id=run_id,
                    finished_at_ms=now_ms,
                    status="failed",
                    error=str(exc),
                )
                repos.news.mark_source_failure(source_id=source_id, error=str(exc), now_ms=now_ms)
            return 0


def _json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

Add missing repository methods: `reconcile_configured_sources`, `disable_unconfigured_sources`, `due_sources`, `mark_source_success`, `mark_source_failure`, and `list_sources_for_status`.

- [ ] **Step 7: Register worker and factory**

Modify `worker_registry.py`:

```python
"news_fetch": "parallax.domains.news_intel.runtime.news_fetch_worker.NewsFetchWorker",
"news_item_process": "parallax.domains.news_intel.runtime.news_item_process_worker.NewsItemProcessWorker",
"news_story_projection": "parallax.domains.news_intel.runtime.news_story_projection_worker.NewsStoryProjectionWorker",
"news_page_projection": "parallax.domains.news_intel.runtime.news_page_projection_worker.NewsPageProjectionWorker",
```

Assign priorities after `collector` and before token projections:

```python
"news_fetch": 15,
"news_item_process": 16,
"news_story_projection": 17,
"news_page_projection": 18,
```

Create `worker_factories/news_intel.py` with `WORKER_KEYS = frozenset({"news_fetch", "news_item_process", "news_story_projection", "news_page_projection"})`. Add it to `worker_factory_specs()` as `WorkerFactorySpec("news_intel.py", NEWS_INTEL_KEYS, construct_news_intel_workers)`; otherwise canonical worker ownership validation will fail after registry keys are added.

The factory builds enabled workers only when `settings.news_intel.enabled` is true; otherwise return `{}` and let `construct_workers()` keep the canonical disabled workers. In this task also create minimal importable worker classes for `NewsItemProcessWorker`, `NewsStoryProjectionWorker`, and `NewsPageProjectionWorker` whose `run_once` methods return `WorkerResult(skipped=1, notes={"reason": "not_implemented_yet"})`; Tasks 5, 6, and 8 replace those bodies with production logic. This keeps `test_worker_runtime_contracts.py` green after worker registry entries are added.

Import `time` in the factory and construct `NewsFetchWorker` with:

```python
NewsFetchWorker(
    name="news_fetch",
    settings=workers.news_fetch,
    db=ctx.db,
    telemetry=ctx.telemetry,
    repository_session=lambda: ctx.db.worker_session("news_fetch"),
    configured_sources=tuple(ctx.settings.news_intel.sources),
    feed_client=NewsFeedClient(timeout_seconds=workers.news_fetch.timeout_seconds),
    wake_bus=ctx.wake_bus,
    batch_size=workers.news_fetch.batch_size,
    clock_ms=lambda: int(time.time() * 1000),
)
```

- [ ] **Step 8: Add minimal raw `/api/news` query and route**

Raw news visibility is the first product milestone. In this task, create the API route with only the list endpoint and a query implementation that reads from `news_page_rows` when rows exist, otherwise falls back to raw `news_items` with stable response shape:

```python
class NewsPageQuery:
    def __init__(self, repository: NewsRepository) -> None:
        self.repository = repository

    def list_news(self, *, limit: int, cursor: str | None = None, status: str | None = None, **filters) -> dict:
        rows = self.repository.list_news_page_rows(limit=limit, cursor=cursor, status=status, **filters)
        if rows:
            return {"items": rows, "next_cursor": _next_cursor(rows)}
        return {
            "items": [_raw_news_row(row) for row in self.repository.list_page_source_items(limit=limit)],
            "next_cursor": None,
        }
```

`routes_news.py` should expose `GET /api/news` now and defer item/story/fact detail endpoints to Task 9. This avoids a backend branch where news is fetched but not visible.

- [ ] **Step 9: Run tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/unit/test_api_news_contract.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add src/parallax/platform/config/settings.py src/parallax/app/runtime src/parallax/app/surfaces/api/routes_news.py src/parallax/app/surfaces/api/http.py src/parallax/domains/news_intel/runtime src/parallax/domains/news_intel/queries/news_page_query.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_worker_settings.py tests/unit/test_api_news_contract.py
git commit -m "feat: add news fetch worker"
```

---

## Task 5: Entity Extraction And Token Mention Resolution

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_entity_extraction.py`
- Create: `src/parallax/domains/news_intel/services/news_token_mentions.py`
- Create: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/token_intel/interfaces.py`
- Test: `tests/unit/domains/news_intel/test_news_entity_extraction.py`
- Test: `tests/unit/domains/news_intel/test_news_token_mentions.py`

- [ ] **Step 1: Write failing entity extraction tests**

Create `tests/unit/domains/news_intel/test_news_entity_extraction.py`:

```python
from parallax.domains.news_intel.services.news_entity_extraction import extract_news_entities


def test_extract_news_entities_reuses_span_aware_address_and_symbol_extraction() -> None:
    entities = extract_news_entities(
        news_item_id="news-1",
        title="New token $NEWX launches on Base",
        summary="CA 0x0000000000000000000000000000000000000000 on Base",
        body_text="",
        now_ms=1,
    )

    types = {entity.entity_type for entity in entities}
    assert "symbol" in types
    assert "ca" in types
    assert all(entity.news_item_id == "news-1" for entity in entities)
```

- [ ] **Step 2: Implement entity extraction wrapper**

Create `news_entity_extraction.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from parallax.domains.evidence.interfaces import TextSurface, extract_entities_from_surfaces
from parallax.domains.news_intel._constants import NEWS_ENTITY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class NewsEntity:
    entity_id: str
    news_item_id: str
    entity_type: str
    raw_value: str
    normalized_value: str
    chain: str | None
    span_start: int
    span_end: int
    text_surface: str
    confidence: float
    extraction_policy_version: str
    created_at_ms: int


def extract_news_entities(
    *,
    news_item_id: str,
    title: str,
    summary: str,
    body_text: str,
    now_ms: int,
) -> list[NewsEntity]:
    surfaces = [
        TextSurface("title", title),
        TextSurface("summary", summary),
        TextSurface("body", body_text),
    ]
    out: list[NewsEntity] = []
    for entity in extract_entities_from_surfaces(surfaces):
        out.append(
            NewsEntity(
                entity_id=_stable_id(
                    "news-entity",
                    news_item_id,
                    entity.entity_type,
                    entity.normalized_value,
                    entity.chain or "",
                    entity.text_surface,
                    str(entity.span_start),
                    str(entity.span_end),
                ),
                news_item_id=news_item_id,
                entity_type=entity.entity_type,
                raw_value=entity.raw_value,
                normalized_value=entity.normalized_value,
                chain=entity.chain,
                span_start=entity.span_start,
                span_end=entity.span_end,
                text_surface=entity.text_surface,
                confidence=entity.confidence,
                extraction_policy_version=NEWS_ENTITY_POLICY_VERSION,
                created_at_ms=int(now_ms),
            )
        )
    return out


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Add token identity read interface**

Modify `src/parallax/domains/token_intel/interfaces.py` to expose a narrow read-only protocol/value for News:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenIdentityLookupResult:
    resolution_status: str
    target_type: str | None
    target_id: str | None
    display_symbol: str | None
    display_name: str | None
    reason_codes: list[str]
    candidate_targets: list[dict[str, object]]


class TokenIdentityLookup(Protocol):
    def resolve_address(self, *, chain_id: str | None, address: str) -> TokenIdentityLookupResult: ...
    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult: ...
```

If `interfaces.py` already has equivalent protocols after recent work, reuse those names instead of duplicating. Keep implementation in existing query/repository classes; News imports only the protocol. The concrete adapter should wrap existing resolver/search primitives (`DeterministicTokenResolver`, `SearchEventsQuery`, or repository methods already used by search), normalize chain aliases such as `base -> eip155:8453`, and must not create new token identity policy inside `news_intel`.

- [ ] **Step 4: Write failing token mention tests**

Create `tests/unit/domains/news_intel/test_news_token_mentions.py`:

```python
from parallax.domains.news_intel.services.news_entity_extraction import NewsEntity
from parallax.domains.news_intel.services.news_token_mentions import build_news_token_mentions
from parallax.domains.token_intel.interfaces import TokenIdentityLookupResult


class FakeLookup:
    def resolve_address(self, *, chain_id: str | None, address: str):
        return TokenIdentityLookupResult(
            resolution_status="EXACT",
            target_type="Asset",
            target_id="asset:base:0x0",
            display_symbol="NEWX",
            display_name="NewX",
            reason_codes=["CHAIN_ADDRESS_EXACT"],
            candidate_targets=[],
        )

    def resolve_symbol(self, *, symbol: str):
        return TokenIdentityLookupResult(
            resolution_status="NIL",
            target_type=None,
            target_id=None,
            display_symbol=symbol,
            display_name=None,
            reason_codes=["SYMBOL_NOT_IN_REGISTRY"],
            candidate_targets=[],
        )


def test_address_mentions_become_exact_address() -> None:
    mentions = build_news_token_mentions(
        news_item_id="news-1",
        entities=[
            NewsEntity(
                entity_id="e1",
                news_item_id="news-1",
                entity_type="ca",
                raw_value="0x0000000000000000000000000000000000000000",
                normalized_value="0x0000000000000000000000000000000000000000",
                chain="base",
                span_start=0,
                span_end=42,
                text_surface="summary",
                confidence=1.0,
                extraction_policy_version="v",
                created_at_ms=1,
            )
        ],
        identity_lookup=FakeLookup(),
        now_ms=1,
    )
    assert mentions[0].resolution_status == "exact_address"
    assert mentions[0].target_id == "asset:base:0x0"


def test_unknown_symbol_goes_to_attention_lane() -> None:
    mentions = build_news_token_mentions(
        news_item_id="news-1",
        entities=[
            NewsEntity(
                entity_id="e1",
                news_item_id="news-1",
                entity_type="symbol",
                raw_value="$NEWX",
                normalized_value="NEWX",
                chain=None,
                span_start=0,
                span_end=5,
                text_surface="title",
                confidence=0.8,
                extraction_policy_version="v",
                created_at_ms=1,
            )
        ],
        identity_lookup=FakeLookup(),
        now_ms=1,
    )
    assert mentions[0].resolution_status == "unknown_attention"
    assert mentions[0].target_id is None
```

- [ ] **Step 5: Implement token mention builder**

Create `news_token_mentions.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from parallax.domains.news_intel._constants import NEWS_TOKEN_MENTION_POLICY_VERSION
from parallax.domains.news_intel.services.news_entity_extraction import NewsEntity
from parallax.domains.token_intel.interfaces import TokenIdentityLookup


@dataclass(frozen=True, slots=True)
class NewsTokenMention:
    mention_id: str
    news_item_id: str
    entity_id: str | None
    observed_symbol: str | None
    chain_id: str | None
    address: str | None
    resolution_status: str
    target_type: str | None
    target_id: str | None
    display_symbol: str | None
    display_name: str | None
    reason_codes: list[str]
    candidate_targets: list[dict[str, object]]
    evidence_strength: str
    confidence: float
    created_at_ms: int


def build_news_token_mentions(
    *,
    news_item_id: str,
    entities: list[NewsEntity],
    identity_lookup: TokenIdentityLookup,
    now_ms: int,
) -> list[NewsTokenMention]:
    mentions: list[NewsTokenMention] = []
    for entity in entities:
        if entity.entity_type == "ca":
            result = identity_lookup.resolve_address(chain_id=entity.chain, address=entity.normalized_value)
            status = _status_from_identity(result.resolution_status, address=True)
            mentions.append(
                _mention(
                    news_item_id=news_item_id,
                    entity=entity,
                    observed_symbol=result.display_symbol,
                    chain_id=entity.chain,
                    address=entity.normalized_value,
                    status=status,
                    result=result,
                    evidence_strength="strong",
                    now_ms=now_ms,
                )
            )
        elif entity.entity_type == "symbol":
            symbol = entity.normalized_value.upper()
            result = identity_lookup.resolve_symbol(symbol=symbol)
            status = _status_from_identity(result.resolution_status, address=False)
            mentions.append(
                _mention(
                    news_item_id=news_item_id,
                    entity=entity,
                    observed_symbol=symbol,
                    chain_id=None,
                    address=None,
                    status=status,
                    result=result,
                    evidence_strength="medium",
                    now_ms=now_ms,
                )
            )
    return _dedupe(mentions)


def _status_from_identity(status: str, *, address: bool) -> str:
    normalized = str(status or "").upper()
    if address and normalized in {"EXACT", "UNIQUE_BY_CONTEXT"}:
        return "exact_address"
    if normalized == "EXACT":
        return "known_symbol"
    if normalized == "UNIQUE_BY_CONTEXT":
        return "unique_by_context"
    if normalized == "AMBIGUOUS":
        return "ambiguous_symbol"
    if normalized == "NON_CRYPTO":
        return "non_crypto"
    if normalized == "NIL":
        return "unknown_attention"
    return "nil"


def _mention(
    *,
    news_item_id: str,
    entity: NewsEntity,
    observed_symbol: str | None,
    chain_id: str | None,
    address: str | None,
    status: str,
    result,
    evidence_strength: str,
    now_ms: int,
) -> NewsTokenMention:
    return NewsTokenMention(
        mention_id=_stable_id("news-token-mention", news_item_id, entity.entity_id, status),
        news_item_id=news_item_id,
        entity_id=entity.entity_id,
        observed_symbol=observed_symbol,
        chain_id=chain_id,
        address=address,
        resolution_status=status,
        target_type=result.target_type,
        target_id=result.target_id,
        display_symbol=result.display_symbol,
        display_name=result.display_name,
        reason_codes=list(result.reason_codes),
        candidate_targets=list(result.candidate_targets),
        evidence_strength=evidence_strength,
        confidence=entity.confidence,
        created_at_ms=int(now_ms),
    )


def _dedupe(items: list[NewsTokenMention]) -> list[NewsTokenMention]:
    out: list[NewsTokenMention] = []
    seen: set[str] = set()
    for item in items:
        if item.mention_id in seen:
            continue
        seen.add(item.mention_id)
        out.append(item)
    return out


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 6: Add item process worker**

Create `news_item_process_worker.py` that:

1. Claims/list pending raw `news_items`.
2. Calls `extract_news_entities`.
3. Calls `build_news_token_mentions`.
4. Writes entities and mentions through `NewsRepository`.
5. Calls deterministic fact candidate service from Task 7 when present; until Task 7, writes no candidates.
6. Marks item `processed` or `process_failed`.
7. Emits `wake_bus.notify_news_item_processed(count=processed)`.

Add repository methods:

- `list_unprocessed_items(limit, now_ms)`
- `replace_item_entities(news_item_id, entities)`
- `replace_token_mentions(news_item_id, mentions)`
- `mark_item_processed(news_item_id, processed_at_ms)`
- `mark_item_process_failed(news_item_id, error, now_ms)`

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_entity_extraction.py tests/unit/domains/news_intel/test_news_token_mentions.py tests/unit/domains/news_intel/test_news_workers.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/parallax/domains/news_intel/services/news_entity_extraction.py src/parallax/domains/news_intel/services/news_token_mentions.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py src/parallax/domains/token_intel/interfaces.py tests/unit/domains/news_intel/test_news_entity_extraction.py tests/unit/domains/news_intel/test_news_token_mentions.py tests/unit/domains/news_intel/test_news_workers.py
git commit -m "feat: add news entity and token mention processing"
```

---

## Task 6: Deterministic Story Grouping

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_story_grouping.py`
- Create: `src/parallax/domains/news_intel/runtime/news_story_projection_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_story_grouping.py`

- [ ] **Step 1: Write failing grouping tests**

Create `tests/unit/domains/news_intel/test_news_story_grouping.py`:

```python
from parallax.domains.news_intel.services.news_story_grouping import choose_story_assignment


def test_story_grouping_accepts_same_canonical_url() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/a",
            "content_hash": "h2",
            "title_fingerprint": "bitcoin etf inflow update",
            "published_at_ms": 1000,
            "token_targets": ["CexToken:BTC"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "representative_title": "Bitcoin ETF inflow",
                "latest_seen_at_ms": 900,
                "token_targets": ["CexToken:BTC"],
            }
        ],
    )
    assert assignment.story_id == "s1"
    assert assignment.match_reason == "same_canonical_url"


def test_story_grouping_rejects_title_only_similarity_without_token_overlap() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/b",
            "content_hash": "h2",
            "title_fingerprint": "coinbase lists new token",
            "published_at_ms": 1000,
            "token_targets": ["symbol:NEWX"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "representative_title": "Coinbase lists old token",
                "latest_seen_at_ms": 900,
                "token_targets": ["symbol:OLDX"],
            }
        ],
    )
    assert assignment.story_id is None
    assert assignment.match_reason == "new_story"
```

- [ ] **Step 2: Implement grouping policy**

Create `news_story_grouping.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from parallax.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class StoryAssignment:
    story_id: str | None
    relation: str
    match_reason: str
    match_score: float


def choose_story_assignment(*, item: dict, candidates: list[dict]) -> StoryAssignment:
    for candidate in candidates:
        if item.get("canonical_url") and item.get("canonical_url") == candidate.get("canonical_url"):
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_canonical_url", 1.0)
        if item.get("content_hash") and item.get("content_hash") == candidate.get("content_hash"):
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_content_hash", 1.0)

    best: StoryAssignment | None = None
    for candidate in candidates:
        score = _lexical_score(str(item.get("title_fingerprint") or ""), str(candidate.get("representative_title") or ""))
        token_overlap = bool(set(item.get("token_targets") or []) & set(candidate.get("token_targets") or []))
        time_close = abs(int(item.get("published_at_ms") or 0) - int(candidate.get("latest_seen_at_ms") or 0)) <= 6 * 60 * 60 * 1000
        if score >= 0.72 and token_overlap and time_close:
            candidate_assignment = StoryAssignment(str(candidate["story_id"]), "same_story", "title_token_time_overlap", score)
            if best is None or candidate_assignment.match_score > best.match_score:
                best = candidate_assignment
    if best is not None:
        return best
    return StoryAssignment(None, "representative", "new_story", 0.0)


def new_story_id(*, news_item_id: str) -> str:
    return hashlib.sha256(f"news-story|{NEWS_STORY_POLICY_VERSION}|{news_item_id}".encode("utf-8")).hexdigest()


def _lexical_score(left: str, right: str) -> float:
    left_tokens = {token for token in left.lower().split() if token}
    right_tokens = {token for token in right.lower().split() if token}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(min(len(left_tokens), len(right_tokens)))
```

Use Postgres `pg_trgm` in repository candidate lookup, but keep final policy deterministic in Python so it is unit-testable.

- [ ] **Step 3: Implement story projection worker**

Create `news_story_projection_worker.py`:

```python
from __future__ import annotations

from collections.abc import Callable

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION
from parallax.domains.news_intel.services.news_story_grouping import choose_story_assignment, new_story_id


class NewsStoryProjectionWorker(WorkerBase):
    name = "news_story_projection"

    def __init__(self, *, repository, wake_bus, batch_size: int, clock_ms: Callable[[], int], **kwargs) -> None:
        super().__init__(**kwargs)
        self.repository = repository
        self.wake_bus = wake_bus
        self.batch_size = max(1, int(batch_size))
        self.clock_ms = clock_ms

    async def run_once(self) -> WorkerResult:
        now_ms = int(self.clock_ms())
        processed = 0
        for item in self.repository.list_items_missing_story(limit=self.batch_size):
            candidates = self.repository.find_story_candidates_for_item(item)
            assignment = choose_story_assignment(item=item, candidates=candidates)
            if assignment.story_id is None:
                story_id = new_story_id(news_item_id=str(item["news_item_id"]))
                self.repository.create_story_from_item(
                    story_id=story_id,
                    item=item,
                    policy_version=NEWS_STORY_POLICY_VERSION,
                    now_ms=now_ms,
                )
                relation = "representative"
            else:
                story_id = assignment.story_id
                relation = assignment.relation
                self.repository.refresh_story_from_member(story_id=story_id, item=item, now_ms=now_ms)
            self.repository.add_story_member(
                story_id=story_id,
                news_item_id=str(item["news_item_id"]),
                relation=relation,
                match_reason=assignment.match_reason,
                match_score=assignment.match_score,
                now_ms=now_ms,
            )
            processed += 1
        if processed and self.wake_bus is not None:
            self.wake_bus.notify_news_story_updated(count=processed)
        return WorkerResult(processed=processed, details={"policy_version": NEWS_STORY_POLICY_VERSION})
```

Add repository methods named above. Candidate lookup should:

- Check same canonical URL and content hash first.
- Then use a bounded recent window and title trigram similarity.
- Include token target arrays from `news_token_mentions`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py tests/unit/domains/news_intel/test_news_workers.py tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/parallax/domains/news_intel/services/news_story_grouping.py src/parallax/domains/news_intel/runtime/news_story_projection_worker.py tests/unit/domains/news_intel/test_news_story_grouping.py tests/unit/domains/news_intel/test_news_workers.py
git commit -m "feat: add deterministic news story projection"
```

---

## Task 7: Deterministic Fact Candidates

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_fact_candidates.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_fact_candidates.py`

- [ ] **Step 1: Write failing fact candidate tests**

Create `tests/unit/domains/news_intel/test_news_fact_candidates.py`:

```python
from parallax.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from parallax.domains.news_intel.services.news_token_mentions import NewsTokenMention


def _mention(status: str = "known_symbol") -> NewsTokenMention:
    return NewsTokenMention(
        mention_id="m1",
        news_item_id="news-1",
        entity_id="e1",
        observed_symbol="BTC",
        chain_id=None,
        address=None,
        resolution_status=status,
        target_type="CexToken" if status != "unknown_attention" else None,
        target_id="cex:BTC" if status != "unknown_attention" else None,
        display_symbol="BTC",
        display_name="Bitcoin",
        reason_codes=[],
        candidate_targets=[],
        evidence_strength="medium",
        confidence=0.8,
        created_at_ms=1,
    )


def test_official_listing_candidate_can_be_accepted() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_exchange",
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].event_type == "listing"
    assert candidates[0].validation_status == "accepted"


def test_specialist_media_listing_stays_attention_until_corroborated() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="specialist_media",
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "source_not_authoritative_for_acceptance" in candidates[0].rejection_reasons


def test_unknown_symbol_candidate_goes_attention_not_accepted() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="specialist_media",
        title="Coinbase lists NEWX for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("unknown_attention")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "target_identity_not_production_eligible" in candidates[0].rejection_reasons
```

- [ ] **Step 2: Implement deterministic candidates**

Create `news_fact_candidates.py`:

```python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from parallax.domains.news_intel._constants import NEWS_FACT_POLICY_VERSION
from parallax.domains.news_intel.services.news_token_mentions import NewsTokenMention

_EVENT_PATTERNS = (
    ("listing", re.compile(r"\b(?:lists?|listing|goes live|launches trading)\b", re.IGNORECASE)),
    ("delisting", re.compile(r"\b(?:delists?|delisting|suspend trading)\b", re.IGNORECASE)),
    ("hack", re.compile(r"\b(?:hack|hacked|exploit|exploited|drained)\b", re.IGNORECASE)),
    ("regulatory", re.compile(r"\b(?:sec|cftc|regulator|court|lawsuit|settlement|approval|approved)\b", re.IGNORECASE)),
    ("etf", re.compile(r"\bETF\b|\bexchange-traded fund\b", re.IGNORECASE)),
    ("fund_flow", re.compile(r"\b(?:inflow|outflow|net flow|whale|accumulat)\b", re.IGNORECASE)),
    ("unlock", re.compile(r"\bunlock\b", re.IGNORECASE)),
    ("protocol_upgrade", re.compile(r"\b(?:upgrade|mainnet|hard fork)\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class NewsFactCandidate:
    fact_candidate_id: str
    news_item_id: str
    event_type: str
    claim: str
    realis: str
    evidence_quote: str
    evidence_span_start: int
    evidence_span_end: int
    source_role: str
    required_slots: dict[str, bool]
    affected_targets: list[dict[str, object]]
    validation_status: str
    rejection_reasons: list[str]
    extraction_method: str
    policy_version: str
    created_at_ms: int
    updated_at_ms: int


def build_fact_candidates(
    *,
    news_item_id: str,
    source_role: str,
    title: str,
    summary: str,
    body_text: str,
    token_mentions: list[NewsTokenMention],
    now_ms: int,
) -> list[NewsFactCandidate]:
    text = " ".join(part for part in (title, summary, body_text) if part).strip()
    if not text:
        return []
    candidates: list[NewsFactCandidate] = []
    for event_type, pattern in _EVENT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        targets = _affected_targets(token_mentions)
        slots = _required_slots(event_type=event_type, targets=targets, text=text)
        rejection_reasons = _rejection_reasons(
            targets=targets,
            slots=slots,
            realis="reported_claim",
            source_role=source_role,
        )
        status = "accepted" if not rejection_reasons else "attention"
        candidates.append(
            NewsFactCandidate(
                fact_candidate_id=_stable_id("news-fact", news_item_id, event_type, str(match.start())),
                news_item_id=news_item_id,
                event_type=event_type,
                claim=title[:240],
                realis="reported_claim",
                evidence_quote=text[max(0, match.start() - 80) : min(len(text), match.end() + 160)].strip()[:240],
                evidence_span_start=max(0, match.start() - 80),
                evidence_span_end=min(len(text), match.end() + 160),
                source_role=source_role,
                required_slots=slots,
                affected_targets=targets,
                validation_status=status,
                rejection_reasons=rejection_reasons,
                extraction_method="deterministic_rules_v1",
                policy_version=NEWS_FACT_POLICY_VERSION,
                created_at_ms=int(now_ms),
                updated_at_ms=int(now_ms),
            )
        )
    return candidates[:3]


def _affected_targets(mentions: list[NewsTokenMention]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for mention in mentions:
        out.append(
            {
                "resolution_status": mention.resolution_status,
                "target_type": mention.target_type,
                "target_id": mention.target_id,
                "display_symbol": mention.display_symbol or mention.observed_symbol,
                "evidence_strength": mention.evidence_strength,
            }
        )
    return out


def _required_slots(*, event_type: str, targets: list[dict[str, object]], text: str) -> dict[str, bool]:
    has_target = any(target.get("target_id") for target in targets)
    if event_type in {"listing", "delisting"}:
        return {"asset": has_target, "venue": bool(re.search(r"\b(?:coinbase|binance|kraken|okx|bybit)\b", text, re.IGNORECASE))}
    if event_type == "hack":
        return {"asset_or_protocol": bool(targets), "incident": True}
    if event_type == "regulatory":
        return {"actor": bool(re.search(r"\b(?:sec|cftc|court|regulator|treasury)\b", text, re.IGNORECASE)), "action": True}
    return {"asset": has_target}


_ACCEPTING_SOURCE_ROLES = {"official_exchange", "official_regulator", "official_protocol", "official_issuer"}


def _rejection_reasons(
    *,
    targets: list[dict[str, object]],
    slots: dict[str, bool],
    realis: str,
    source_role: str,
) -> list[str]:
    reasons: list[str] = []
    if not any(target.get("target_id") for target in targets):
        reasons.append("target_identity_not_production_eligible")
    for slot, present in slots.items():
        if not present:
            reasons.append(f"missing_slot:{slot}")
    if realis not in {"actual", "scheduled", "official_proposed", "reported_claim"}:
        reasons.append("non_actionable_realis")
    if source_role not in _ACCEPTING_SOURCE_ROLES:
        reasons.append("source_not_authoritative_for_acceptance")
    return reasons


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Wire into item process worker**

After token mentions are built, call `build_fact_candidates(...)` and repository method `replace_fact_candidates(news_item_id, candidates)`.

Add repository method:

- `replace_fact_candidates(news_item_id, candidates)`

Do not write `story_id` into `news_fact_candidates`; the table intentionally references only `news_items`. Story association is derived by query/page projection through `news_story_members`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_fact_candidates.py tests/unit/domains/news_intel/test_news_workers.py tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/parallax/domains/news_intel/services/news_fact_candidates.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py tests/unit/domains/news_intel/test_news_fact_candidates.py
git commit -m "feat: add deterministic news fact candidates"
```

---

## Task 8: News Page Projection And Query Service

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Create: `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- Create: `src/parallax/domains/news_intel/queries/news_page_query.py`
- Create: `src/parallax/domains/news_intel/interfaces.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`

- [ ] **Step 1: Write failing projection test**

Create `tests/unit/domains/news_intel/test_news_page_projection.py`:

```python
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row


def test_build_news_page_row_includes_token_and_fact_lanes() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        story={"story_id": "story-1", "item_count": 2, "source_count": 1},
        token_mentions=[
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
                "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
            }
        ],
        fact_candidates=[
            {
                "event_type": "listing",
                "validation_status": "attention",
                "rejection_reasons_json": ["target_identity_not_production_eligible"],
            }
        ],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "attention"
    assert row["token_lanes"][0]["lane"] == "attention"
    assert row["fact_lanes"][0]["status"] == "attention"
```

- [ ] **Step 2: Implement page projection service**

Create `news_page_projection.py`:

```python
from __future__ import annotations

import hashlib
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION


def build_news_page_row(
    *,
    item: dict[str, Any],
    story: dict[str, Any] | None,
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    computed_at_ms: int,
) -> dict[str, Any]:
    token_lanes = [_token_lane(row) for row in token_mentions]
    fact_lanes = [_fact_lane(row) for row in fact_candidates]
    lifecycle = _lifecycle(item=item, token_lanes=token_lanes, fact_lanes=fact_lanes)
    news_item_id = str(item["news_item_id"])
    return {
        "row_id": _stable_id("news-page-row", news_item_id),
        "news_item_id": news_item_id,
        "story_id": (story or {}).get("story_id"),
        "latest_at_ms": int(item.get("published_at_ms") or item.get("fetched_at_ms") or computed_at_ms),
        "lifecycle_status": lifecycle,
        "headline": str(item.get("title") or ""),
        "summary": str(item.get("summary") or ""),
        "source_domain": str(item.get("source_domain") or ""),
        "canonical_url": str(item.get("canonical_url") or ""),
        "token_lanes": token_lanes,
        "fact_lanes": fact_lanes,
        "story": story or {},
        "source": {"source_domain": str(item.get("source_domain") or "")},
        "computed_at_ms": int(computed_at_ms),
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _token_lane(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("resolution_status") or "")
    lane = "resolved" if status in {"exact_address", "known_symbol", "unique_by_context"} else "attention"
    return {
        "lane": lane,
        "resolution_status": status,
        "symbol": row.get("display_symbol") or row.get("observed_symbol"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "reason_codes": row.get("reason_codes_json") or [],
    }


def _fact_lane(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": row.get("event_type"),
        "status": row.get("validation_status"),
        "rejection_reasons": row.get("rejection_reasons_json") or [],
    }


def _lifecycle(*, item: dict[str, Any], token_lanes: list[dict[str, Any]], fact_lanes: list[dict[str, Any]]) -> str:
    if any(row.get("status") == "accepted" for row in fact_lanes):
        return "accepted"
    if any(row.get("status") == "attention" for row in fact_lanes) or any(row.get("lane") == "attention" for row in token_lanes):
        return "attention"
    if fact_lanes:
        return "fact_candidate"
    if token_lanes:
        return "entity_extracted"
    return str(item.get("lifecycle_status") or "raw")


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Implement page projection worker**

Create `news_page_projection_worker.py` that:

1. Reads recent items needing page refresh via repository.
2. Builds rows with `build_news_page_row`.
3. Calls `replace_page_rows_for_items(news_item_ids=[...], rows=[...])` so stale rows for refreshed items are removed before upsert.
4. Returns `WorkerResult(processed=count)`.

Add repository method `list_items_for_page_projection(limit)` returning item, story, token_mentions, fact_candidates grouped by item.

- [ ] **Step 4: Implement query interface**

Create `interfaces.py`:

```python
from __future__ import annotations

from typing import Protocol


class NewsReadModel(Protocol):
    def list_news(self, *, limit: int, cursor: str | None = None, status: str | None = None) -> dict: ...
    def get_item(self, *, news_item_id: str) -> dict | None: ...
    def get_story(self, *, story_id: str) -> dict | None: ...
    def get_fact(self, *, fact_candidate_id: str) -> dict | None: ...
    def source_status(self) -> list[dict]: ...
```

Extend `queries/news_page_query.py` with methods:

- `list_news(limit, cursor, status, lane, source, target, q)`
- `get_item(news_item_id)`
- `get_story(story_id)`
- `get_fact(fact_candidate_id)`
- `source_status()`

Use repository/query SQL only inside this query module.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_repository.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py src/parallax/domains/news_intel/queries/news_page_query.py src/parallax/domains/news_intel/interfaces.py tests/unit/domains/news_intel/test_news_page_projection.py
git commit -m "feat: add news page projection read model"
```

---

## Task 9: API Routes And Contracts

**Files:**
- Modify: `src/parallax/app/surfaces/api/routes_news.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Test: `tests/unit/test_api_news_contract.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Write failing API contract tests**

Create `tests/unit/test_api_news_contract.py`:

```python
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api import routes_news
from parallax.app.surfaces.api.http import create_api_router


class FakeNewsReadModel:
    def list_news(self, **kwargs):
        return {
            "items": [
                {
                    "row_id": "row-1",
                    "news_item_id": "news-1",
                    "headline": "Coinbase lists NEWX",
                    "lifecycle_status": "attention",
                    "token_lanes": [{"lane": "attention", "symbol": "NEWX"}],
                    "fact_lanes": [],
                }
            ],
            "next_cursor": None,
        }

    def get_item(self, *, news_item_id: str):
        return {"news_item_id": news_item_id}

    def get_story(self, *, story_id: str):
        return {"story_id": story_id}

    def get_fact(self, *, fact_candidate_id: str):
        return {"fact_candidate_id": fact_candidate_id}

    def source_status(self):
        return []


def test_news_route_returns_lifecycle_rows(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime()
    monkeypatch.setattr(routes_news, "_news_read_model", lambda _repos: FakeNewsReadModel())

    client = TestClient(app)
    response = client.get("/api/news?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    row = payload["data"]["items"][0]
    assert row["lifecycle_status"] == "attention"
    assert row["token_lanes"][0]["symbol"] == "NEWX"


class FakeRuntime:
    settings = SimpleNamespace(ws_token="")

    @contextmanager
    def repositories(self):
        yield SimpleNamespace(news=object())
```

- [ ] **Step 2: Add route implementation**

Create `routes_news.py`:

```python
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _limit
from parallax.domains.news_intel.queries.news_page_query import NewsPageQuery

router = APIRouter()


@router.get("/news", response_model=api_schemas.ApiEnvelope[api_schemas.NewsListData])
def list_news(
    request: Request,
    limit: Annotated[int, Query()] = 100,
    cursor: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "",
    lane: Annotated[str, Query()] = "",
    source: Annotated[str, Query()] = "",
    target: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _news_read_model(repos).list_news(
            limit=_limit(limit, maximum=500),
            cursor=cursor or None,
            status=status or None,
            lane=lane or None,
            source=source or None,
            target=target or None,
            q=q or None,
        )
    return _json({"ok": True, "data": data})


@router.get("/news/items/{news_item_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsItemData])
def get_news_item(request: Request, news_item_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_item(news_item_id=news_item_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_item_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/stories/{story_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsStoryData])
def get_news_story(request: Request, story_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_story(story_id=story_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_story_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/facts/{fact_candidate_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsFactData])
def get_news_fact(request: Request, fact_candidate_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_fact(fact_candidate_id=fact_candidate_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_fact_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/sources/status", response_model=api_schemas.ApiEnvelope[api_schemas.NewsSourcesStatusData])
def get_news_source_status(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = {"sources": _news_read_model(repos).source_status()}
    return _json({"ok": True, "data": data})


def _news_read_model(repos: Any) -> NewsPageQuery:
    return NewsPageQuery(repository=repos.news)
```

If Task 4 already registered the list route, this task extends `routes_news.py` with item/story/fact/source-status endpoints; it must not create a second router or duplicate `/api/news`.
Do not add a new API dependency injection style; follow current route modules by using `_authenticated_runtime(request)` and constructing read models from `runtime.repositories()`.

- [ ] **Step 3: Add OpenAPI schema/type shape**

If this project uses Pydantic response models in `schemas.py`, add:

- `NewsRow`
- `NewsListResponse`
- `NewsTokenLane`
- `NewsFactLane`
- `NewsSourceStatus`

If current API routes return plain dicts for dynamic payloads, keep dict route return and let OpenAPI infer minimally. Do not overbuild schema classes if existing route style avoids them.

- [ ] **Step 4: Run API tests**

```bash
uv run pytest tests/unit/test_api_news_contract.py tests/integration/test_api_http.py -q
```

Expected: pass.

- [ ] **Step 5: Regenerate OpenAPI/types**

Use the repo's existing generated-doc command. If no command is documented, inspect `tests/contract/test_openapi_drift.py` and run the matching script. Expected outputs:

```text
docs/generated/openapi.json updated
web/src/lib/types/openapi.ts updated
```

- [ ] **Step 6: Commit**

```bash
git add src/parallax/app/surfaces/api/routes_news.py src/parallax/app/surfaces/api/http.py src/parallax/app/surfaces/api/schemas.py tests/unit/test_api_news_contract.py tests/integration/test_api_http.py docs/generated/openapi.json web/src/lib/types/openapi.ts
git commit -m "feat: add news intel API routes"
```

---

## Task 10: Frontend Independent News Page

**Files:**
- Create: `web/src/features/news/index.ts`
- Create: `web/src/features/news/useNewsPage.ts`
- Create: `web/src/features/news/NewsPage.tsx`
- Create: `web/src/routes/news.route.tsx`
- Create: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/app/AppRoutes.tsx`
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/shared/routing/paths.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Test: `web/tests/unit/features/news/useNewsPage.test.ts`
- Test: `web/tests/component/features/news/NewsPage.test.tsx`

- [ ] **Step 1: Write failing frontend model test**

Create `web/tests/unit/features/news/useNewsPage.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { newsLifecycleLabel, newsTokenLaneLabel } from "../../../src/shared/model/newsIntel";

describe("newsIntel model", () => {
  it("labels attention lifecycle explicitly", () => {
    expect(newsLifecycleLabel("attention")).toBe("Attention");
  });

  it("labels unknown token lane without pretending it is resolved", () => {
    expect(newsTokenLaneLabel({ lane: "attention", resolution_status: "unknown_attention", symbol: "NEWX" })).toBe(
      "NEWX · attention",
    );
  });
});
```

- [ ] **Step 2: Implement shared model**

Create `web/src/shared/model/newsIntel.ts`:

```ts
export type NewsTokenLane = {
  lane: "resolved" | "attention" | string;
  resolution_status?: string;
  symbol?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  reason_codes?: string[];
};

export type NewsFactLane = {
  event_type?: string | null;
  status?: "accepted" | "rejected" | "attention" | string;
  rejection_reasons?: string[];
};

export type NewsRow = {
  row_id: string;
  news_item_id: string;
  story_id?: string | null;
  latest_at_ms?: number;
  lifecycle_status: string;
  headline: string;
  summary?: string;
  source_domain?: string;
  canonical_url?: string;
  token_lanes?: NewsTokenLane[];
  fact_lanes?: NewsFactLane[];
};

export const newsLifecycleLabel = (status: string): string => {
  const labels: Record<string, string> = {
    raw: "Raw",
    processed: "Processed",
    entity_extracted: "Entities",
    fact_candidate: "Fact",
    accepted: "Accepted",
    rejected: "Rejected",
    attention: "Attention",
  };
  return labels[status] ?? status;
};

export const newsTokenLaneLabel = (lane: NewsTokenLane): string => {
  const symbol = lane.symbol || "Unknown";
  return `${symbol} · ${lane.lane}`;
};
```

- [ ] **Step 3: Add API client method**

Modify `web/src/lib/api/client.ts`:

```ts
export const fetchNewsRows = async (params: { limit?: number; cursor?: string | null; status?: string | null }) => {
  const response = await getApi<{ items: NewsRow[]; next_cursor?: string | null }>("/api/news", {
    params: {
      limit: params.limit,
      cursor: params.cursor,
      status: params.status,
    },
  });
  return response.data;
};
```

Use the existing `getApi` client style and import `NewsRow` from the shared model or generated type alias. Do not introduce a parallel `apiGet` helper.

- [ ] **Step 4: Implement route hook**

Create `web/src/features/news/useNewsPage.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchNewsRows } from "../../lib/api/client";
import { queryKeys } from "../../shared/query/queryKeys";

export const useNewsPage = () => {
  return useQuery({
    queryKey: queryKeys.newsRows({ limit: 100 }),
    queryFn: () => fetchNewsRows({ limit: 100 }),
    staleTime: 15_000,
  });
};
```

Add `queryKeys.newsRows(...)` in `web/src/shared/query/queryKeys.ts`.

- [ ] **Step 5: Implement News page UI**

Create `web/src/features/news/NewsPage.tsx`:

```tsx
import { newsLifecycleLabel, newsTokenLaneLabel } from "../../shared/model/newsIntel";
import { RemoteState } from "../../shared/ui/RemoteState";
import { useNewsPage } from "./useNewsPage";

export const NewsPage = () => {
  const query = useNewsPage();

  return (
    <main className="obsidian-page">
      <section className="obsidian-toolbar">
        <h1>News</h1>
      </section>
      <RemoteState query={query}>
        {(data) => (
          <section className="news-tape" aria-label="News tape">
            {data.items.map((row) => (
              <article className="news-row" key={row.row_id}>
                <div className="news-row__meta">
                  <span>{row.source_domain}</span>
                  <span>{newsLifecycleLabel(row.lifecycle_status)}</span>
                </div>
                <h2>{row.headline}</h2>
                {row.summary ? <p>{row.summary}</p> : null}
                <div className="news-row__lanes">
                  {(row.token_lanes || []).map((lane, index) => (
                    <span className={`news-chip news-chip--${lane.lane}`} key={`${row.row_id}-token-${index}`}>
                      {newsTokenLaneLabel(lane)}
                    </span>
                  ))}
                  {(row.fact_lanes || []).map((lane, index) => (
                    <span className={`news-chip news-chip--${lane.status}`} key={`${row.row_id}-fact-${index}`}>
                      {lane.event_type || "fact"} · {lane.status}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </section>
        )}
      </RemoteState>
    </main>
  );
};
```

Use existing visual system classes where possible. Keep layout dense and operational; do not make a marketing landing page.

- [ ] **Step 6: Add route**

Create `web/src/routes/news.route.tsx`:

```tsx
import { NewsPage } from "../features/news/NewsPage";

export const NewsRoute = () => <NewsPage />;
```

Modify app route registration to add `/news`. Add path constant:

```ts
news: "/news",
```

If there is a top nav/sidebar, add a `News` nav item without disrupting existing Token Radar defaults.

- [ ] **Step 7: Add component tests**

Create `web/tests/component/features/news/NewsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { NewsPage } from "../../../../src/features/news/NewsPage";

vi.mock("../../../../src/lib/api/client", () => ({
  fetchNewsRows: async () => ({
    items: [
      {
        row_id: "row-1",
        news_item_id: "news-1",
        lifecycle_status: "attention",
        headline: "Coinbase lists NEWX",
        summary: "Trading starts today",
        source_domain: "example.test",
        token_lanes: [{ lane: "attention", resolution_status: "unknown_attention", symbol: "NEWX" }],
        fact_lanes: [{ event_type: "listing", status: "attention" }],
      },
    ],
    next_cursor: null,
  }),
}));

describe("NewsPage", () => {
  it("renders news lifecycle and attention lanes", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NewsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Coinbase lists NEWX")).toBeInTheDocument();
    expect(screen.getByText("Attention")).toBeInTheDocument();
    expect(screen.getByText("NEWX · attention")).toBeInTheDocument();
  });
});
```

- [ ] **Step 8: Run frontend tests**

```bash
cd web
npm test -- --run web/tests/unit/features/news/useNewsPage.test.ts web/tests/component/features/news/NewsPage.test.tsx
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add web/src/features/news web/src/routes/news.route.tsx web/src/shared/model/newsIntel.ts web/src/app/AppRoutes.tsx web/src/routes/AppRoutes.tsx web/src/shared/routing/paths.ts web/src/lib/api/client.ts web/src/shared/query/queryKeys.ts web/tests/unit/features/news/useNewsPage.test.ts web/tests/component/features/news/NewsPage.test.tsx
git commit -m "feat: add independent news page"
```

---

## Task 11: Worker Inventory, Contracts, And Docs

**Files:**
- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md`
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Test: `tests/architecture/test_worker_runtime_contracts.py`
- Test: `tests/contract/test_openapi_drift.py`

- [ ] **Step 1: Update worker inventory**

Modify `docs/WORKERS.md`:

- Add worker inventory keys: `news_fetch`, `news_item_process`, `news_story_projection`, `news_page_projection`.
- Add rows:
  - `news_fetch`: reads configured news feed sources; writes `news_fetch_runs`, `news_provider_items`, `news_items`, `news_sources` fetch state; wake-out `news_item_written`; catch-up `interval_seconds`.
  - `news_item_process`: reads raw `news_items`, token identity interfaces; writes `news_item_entities`, `news_token_mentions`, `news_fact_candidates`; wake-in `news_item_written`; wake-out `news_item_processed`.
  - `news_story_projection`: reads news item/entity/token/fact rows; writes `news_story_groups`, `news_story_members`; wake-in `news_item_processed`; wake-out `news_story_updated`.
  - `news_page_projection`: reads news facts/story groups; writes `news_page_rows`; wake-in `news_item_written`, `news_item_processed`, `news_story_updated`; no wake-out.
- Add wake channel rows for `news_item_written`, `news_item_processed`, `news_story_updated`.

- [ ] **Step 2: Update contracts**

Modify `docs/CONTRACTS.md`:

Add API contracts for:

```text
GET /api/news
GET /api/news/items/{news_item_id}
GET /api/news/stories/{story_id}
GET /api/news/facts/{fact_candidate_id}
GET /api/news/sources/status
```

Document filters, lifecycle status, attention lane semantics, and no Token Radar coupling.

- [ ] **Step 3: Update frontend docs**

Modify `docs/FRONTEND.md`:

- Add `/news` as an operational News page.
- State the first viewport is a dense news tape, not a landing page.
- State UI does not infer token identity or fact status; it renders API lifecycle.

- [ ] **Step 4: Run docs/contract tests**

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/contract/test_openapi_drift.py tests/unit/test_docs_generated.py -q
```

Expected: pass after generated OpenAPI/types are updated.

- [ ] **Step 5: Commit**

```bash
git add docs/WORKERS.md docs/WORKER_FLOW.md docs/CONTRACTS.md docs/FRONTEND.md src/parallax/domains/news_intel/ARCHITECTURE.md docs/generated/openapi.json web/src/lib/types/openapi.ts
git commit -m "docs: document news intel runtime and contracts"
```

---

## Task 12: End-to-End Verification

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-19-news-intel-kappa-cqrs-verification-cn.md`

- [ ] **Step 1: Run backend focused checks**

```bash
uv run ruff check .
uv run pytest tests/unit/domains/news_intel tests/integration/domains/news_intel tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_boundaries.py -q
```

Expected: pass.

- [ ] **Step 2: Run worker/runtime guard checks**

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
```

Expected: pass.

- [ ] **Step 3: Run frontend focused checks**

```bash
cd web
npm test -- --run web/tests/unit/features/news/useNewsPage.test.ts web/tests/component/features/news/NewsPage.test.tsx
```

Expected: pass.

- [ ] **Step 4: Run full project check**

```bash
make check-all
```

Expected: exit code 0. Paste full output into verification artefact.

- [ ] **Step 5: Manual smoke with local server**

Start server with real config:

```bash
uv run parallax serve
```

Open:

```text
http://127.0.0.1:<port>/news
```

Verify:

- `/news` renders without Token Radar data.
- `/api/news` returns rows after worker runs or fixture-seeded DB.
- Attention lane is visible for unknown symbols.
- Source status endpoint shows fetch state.

Record commands and screenshots/notes in verification artefact.

- [ ] **Step 6: Write verification document**

Create `docs/superpowers/plans/active/2026-05-19-news-intel-kappa-cqrs-verification-cn.md` with:

- Spec compliance table for AC1-AC10.
- Full `make check-all` output.
- Coverage/skipped tests/E2E sections following `docs/superpowers/_templates/verification-template.md`.
- Diff summary.
- Risks observed and follow-ups.

- [ ] **Step 7: Final commit**

```bash
git add docs/superpowers/plans/active/2026-05-19-news-intel-kappa-cqrs-verification-cn.md
git commit -m "test: verify news intel production loop"
```

---

## PR Breakdown

One PR is recommended because API, worker registry, docs, and frontend route should land coherently. Internal commits remain reviewable:

1. `docs: add news intel domain skeleton`
2. `feat: add news intel storage foundation`
3. `feat: add news feed parsing and normalization`
4. `feat: add news fetch worker`
5. `feat: add news entity and token mention processing`
6. `feat: add deterministic news story projection`
7. `feat: add deterministic news fact candidates`
8. `feat: add news page projection read model`
9. `feat: add news intel API routes`
10. `feat: add independent news page`
11. `docs: document news intel runtime and contracts`
12. `test: verify news intel production loop`

If the PR becomes too large during implementation, split only at safe boundaries:

- PR A: backend raw news visible (`news_sources` through `/api/news` raw rows).
- PR B: token/story/fact lifecycle and page projection.
- PR C: frontend page and docs.

Do not merge PR B before PR A. Do not merge PR C before `/api/news` contract is stable.

---

## Rollout Order

1. Deploy migration.
2. Add `news_intel.enabled: false` default.
3. Deploy code with workers registered but disabled by config.
4. Configure a small allowlist of sources in `~/.parallax/config.yaml`.
5. Enable `news_fetch`, `news_item_process`, `news_story_projection`, `news_page_projection` via existing worker defaults.
6. Observe `/api/news/sources/status` and worker status for one refresh interval.
7. Open `/news` and verify raw rows, attention lane, story grouping, and fact candidate display.
8. Only after News page is stable, write a separate spec for any Token Radar integration.

Example config block:

```yaml
news_intel:
  enabled: true
  sources:
    - source_id: coindesk-rss
      provider_type: rss
      feed_url: https://www.coindesk.com/arc/outboundfeeds/rss/
      source_domain: coindesk.com
      source_name: CoinDesk
      source_role: specialist_media
      trust_tier: standard
      enabled: true
      refresh_interval_seconds: 300
```

---

## Rollback

1. Set `news_intel.enabled: false` in runtime config.
2. Stop/restart service so News workers are disabled.
3. Keep tables for audit; do not drop tables during emergency rollback.
4. If migration itself must roll back in a maintenance window, run Alembic downgrade for revision `20260519_0064`.
5. Remove `/news` nav entry only if the API route is unavailable; otherwise page can show empty/disabled state.

Data written to News tables does not affect Token Radar, Pulse, market ticks, or existing event ingestion, so rollback is low blast-radius.

---

## Acceptance Test Commands

- **AC1 raw visible**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_persists_feed_items -q
  uv run pytest tests/unit/test_api_news_contract.py::test_news_route_returns_lifecycle_rows -q
  ```

- **AC2 address mention identity**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_token_mentions.py::test_address_mentions_become_exact_address -q
  ```

- **AC3 unknown symbol attention**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_token_mentions.py::test_unknown_symbol_goes_to_attention_lane tests/unit/domains/news_intel/test_news_fact_candidates.py::test_unknown_symbol_candidate_goes_attention_not_accepted -q
  ```

- **AC4 exact story grouping**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py::test_story_grouping_accepts_same_canonical_url -q
  ```

- **AC5 no title-only overmerge**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py::test_story_grouping_rejects_title_only_similarity_without_token_overlap -q
  ```

- **AC6 fact rejection reasons**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_fact_candidates.py -q
  ```

- **AC7 rebuildable page rows**
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_news_repository_rebuilds_page_rows -q
  ```

- **AC8 missed wake safe**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py -q
  ```
  Add a test case during Task 4/8 that runs each worker with no wake object and confirms interval/manual `run_once` catches up.

- **AC9 no forbidden writes**
  ```bash
  uv run pytest tests/architecture/test_news_intel_boundaries.py -q
  ```

- **AC10 frontend page**
  ```bash
  cd web
  npm test -- --run web/tests/component/features/news/NewsPage.test.tsx
  ```

---

## Verification

Full verification must be recorded in:

`docs/superpowers/plans/active/2026-05-19-news-intel-kappa-cqrs-verification-cn.md`

Before declaring implementation complete, the verification artefact must include:

- Full `make check-all` output and exit code 0.
- Coverage section.
- Skipped tests section.
- E2E golden path section.
- Manual `/news` smoke notes.
- Diff summary grouped by backend, frontend, docs.
- Any deviations from this plan or the spec.
