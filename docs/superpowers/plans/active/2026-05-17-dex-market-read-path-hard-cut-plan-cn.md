# DEX Market And Read Path Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate DEX tick degradation and API read-path timeouts by making provider fallback exception-isolated, moving request-time historical lookups into persisted read models, and batching the full recent-event payload read path.

**Architecture:** DEX quote fallback becomes a hard provider boundary: GMGN quote failure cannot prevent OKX quote use. Token Radar `listed_at_ms` becomes a materialized `token_radar_rows` field written by the projection writer, so HTTP reads never scan historical radar rows. `/api/recent` batches token-resolution, entity, signal, token intent, and harness hydration for its event page instead of issuing per-event repository calls. Event token projection uses a requested-event CTE and sargable market-target lookup instead of a long `IN` list and OR-heavy market tick predicate.

**CEX icon addendum:** CEX icons are not a runtime provider fallback. A one-shot ops sync writes static icon facts into existing `cex_tokens` rows only, and `TokenProfileCurrentWorker` remains the sole writer of `token_profile_current`.

**Tech Stack:** Python, FastAPI, PostgreSQL, Alembic, psycopg, pytest, Docker Compose.

---

### Task 1: DEX Quote Provider Exception Isolation

**Files:**
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Test: `tests/unit/test_providers_wiring.py`

- [x] **Step 1: Write the failing test**

Add a unit test proving that a GMGN provider-level exception sends the full request set to OKX fallback and returns OKX quotes.

- [x] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/unit/test_providers_wiring.py::test_asset_market_quote_provider_uses_okx_when_gmgn_primary_raises -q
```

Expected: FAIL because `FallbackDexQuoteProvider.token_quotes()` lets the primary exception escape.

- [x] **Step 3: Implement hard fallback**

Change `FallbackDexQuoteProvider.token_quotes()` so primary exceptions are treated as total primary miss when fallback exists. If fallback is absent, re-raise the primary error. Do not add provider-specific compatibility branches.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_providers_wiring.py::test_asset_market_quote_provider_prefers_gmgn_facts_and_falls_back_to_okx tests/unit/test_providers_wiring.py::test_asset_market_quote_provider_uses_okx_when_gmgn_primary_raises -q
```

Expected: PASS.

### Task 2: Token Radar Materialized Listed Time

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260517_0054_token_radar_materialized_listed_at.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Test: `tests/unit/test_token_radar_repository.py`

- [x] **Step 1: Write failing repository tests**

Add tests requiring `replace_rows()` to persist `listed_at_ms` and `latest_rows()` to read the materialized field without `LEFT JOIN LATERAL` or history scans.

- [x] **Step 2: Run the tests to verify RED**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py::test_replace_rows_insert_materializes_listed_at_ms tests/unit/test_token_radar_repository.py::test_latest_rows_reads_materialized_listed_at_without_history_lateral -q
```

Expected: FAIL because `listed_at_ms` is not inserted and `latest_rows()` still performs request-time historical lookup.

- [x] **Step 3: Add schema and writer logic**

Add `token_radar_rows.listed_at_ms BIGINT`, backfill current latest publication rows from earliest `(projection_version, window, scope, target_type, identity)` history, and keep the identity lookup index for write-side materialization. Update `replace_rows()` to compute listed time once per inserted row from existing rows, defaulting to the current `computed_at_ms` for first appearances.

- [x] **Step 4: Replace latest read SQL**

Remove the `LEFT JOIN LATERAL history` block from `latest_rows()`. The query must only read the latest publication set and return materialized `listed_at_ms`.

- [x] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py -q
```

Expected: PASS.

### Task 3: Recent API Batch Token Resolution

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Test: `tests/unit/test_public_event_token_payloads.py`

- [x] **Step 1: Write failing HTTP payload test**

Add a test proving `_recent_data()` calls `event_tokens.for_events()` once for the returned event page and does not call `for_event()` per item.

- [x] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/unit/test_public_event_token_payloads.py::test_recent_data_batches_projected_event_tokens_for_page -q
```

Expected: FAIL because `_recent_data()` currently calls `_payload_for_event()` per item, and each payload calls `event_tokens.for_event()`.

- [x] **Step 3: Implement batch payload hydration**

Add an internal `_payloads_for_events()` helper that batches token resolutions with `event_tokens.for_events(tuple(event_ids))`, then builds each event payload with its preloaded resolution list. Keep WebSocket single-event payload behavior separate.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_public_event_token_payloads.py -q
```

Expected: PASS.

### Task 4: Event Token Projection Query Hard Cut

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/event_token_projection_query.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260517_0055_public_read_path_indexes.py`
- Test: `tests/unit/test_event_token_projection.py`

- [x] **Step 1: Write failing SQL-shape test**

Add a unit test requiring event token projection to use a requested-event relation and a sargable market-target predicate instead of a long `IN` list and OR-heavy latest tick lookup.

- [x] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/unit/test_event_token_projection.py::test_event_token_projection_uses_sargable_market_target_for_latest_tick -q
```

Expected: FAIL because the query still uses request-time `IN` expansion and OR predicates.

- [x] **Step 3: Implement sargable projection query**

Replace event id expansion with a materialized `requested_events` CTE using `unnest(%s::text[]) WITH ORDINALITY`. Replace the market tick OR predicate with a single `market_target` lateral relation and equality predicates on `(target_type, target_id)`.

- [x] **Step 4: Add production indexes**

Add concurrent indexes for current public token intent resolutions and preferred CEX price feed lookup:

```text
idx_token_intent_resolutions_public_event_current
idx_price_feeds_cex_subject_preferred
```

- [x] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_event_token_projection.py -q
```

Expected: PASS.

### Task 5: Recent API Full Payload Batch Hydration

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/domains/evidence/repositories/entity_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_intent_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/signal_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/closed_loop_harness/repositories/harness_repository.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260517_0056_recent_payload_batch_indexes.py`
- Test: `tests/unit/test_public_event_token_payloads.py`

- [x] **Step 1: Extend failing HTTP payload test**

Require `_recent_data()` to batch entities, alerts, token intents, token resolutions, and harness payloads for the returned event page.

- [x] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/unit/test_public_event_token_payloads.py::test_recent_data_batches_projected_event_tokens_for_page -q
```

Expected: FAIL until the remaining per-event repository calls are removed from the recent list path.

- [x] **Step 3: Add repository batch methods**

Add `entities_for_events()`, `alerts_for_events()`, `intents_for_events()`, and `harness_for_events()` methods that return dictionaries keyed by `event_id`. Keep single-event methods for their existing direct callers.

- [x] **Step 4: Wire the API batch path**

Build all recent event payloads from preloaded maps in `_payloads_for_events()`. The list endpoint must not loop through per-event payload hydration.

- [x] **Step 5: Add production indexes**

Add concurrent indexes for the remaining batch path joins:

```text
idx_attention_seeds_event
idx_event_clusters_event_seen
```

- [x] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_public_event_token_payloads.py -q
```

Expected: PASS.

### Task 6: Integration Verification And Production Rebuild

**Files:**
- Modify only files touched by Tasks 1-5.

- [x] **Step 1: Run focused backend tests**

```bash
uv run pytest tests/unit/test_public_event_token_payloads.py tests/unit/test_event_token_projection.py tests/unit/test_token_radar_repository.py tests/unit/test_providers_wiring.py tests/unit/test_market_tick_poll_worker.py -q
```

- [x] **Step 2: Run migration and projection health checks**

```bash
uv run gmgn-twitter-intel db migrate
docker compose exec -T app gmgn-twitter-intel db health
```

- [x] **Step 3: Rebuild production container**

```bash
docker compose up -d --build
```

- [x] **Step 4: Verify production behavior**

Check:

```bash
curl -fsS http://127.0.0.1:8765/healthz
docker compose exec -T app gmgn-twitter-intel ops projection-status
```

Then confirm `market_tick_poll` inserts DEX ticks when OKX returns quotes even if GMGN is blocked, and confirm `/api/token-radar?window=1h&scope=all&limit=50` no longer performs request-time history scan.

### Results

- Focused backend suite: `61 passed, 4 skipped`; skips are the local PostgreSQL test DB authentication precondition.
- Static checks: `ruff check`, `ruff format --check`, and `compileall` passed.
- Database migration health: production/local database is at `20260517_0056` and reports `ready`.
- Docker rebuild: `docker compose up -d --build` completed and app/postgres are healthy.
- Pressure check:
  - `/api/recent?limit=200&scope=matched` average latency improved from about `1.602s` to `0.748s`.
  - `/api/recent?limit=1000&scope=matched` average latency improved from about `7.574s` to `2.598s`.
  - `/api/token-radar?window=1h&limit=50&scope=all` remains healthy with no request-time history scan.
- Runtime logs after rebuild show no `statement timeout`, `QueryCanceled`, or ASGI exception in the checked window.
- DEX tick freshness is supplied by OKX REST/WS when GMGN quote is unavailable; GMGN no longer blocks fallback execution.

### Task 7: CEX Static Icon Sync Without Runtime Provider

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260517_0057_cex_token_static_icons.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/cex_token_icon_sync.py`
- Create: `src/gmgn_twitter_intel/integrations/binance/cex_icon_client.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_profile_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/token_profile_current_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/token_profile_current_worker.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`

- [x] **Step 1: Write failing tests**

Require CEX token profiles with `cex_tokens.logo_url` to project as ready, and require the icon sync to update existing routed CEX tokens only.

- [x] **Step 2: Implement fact-table sync**

Add `cex_tokens.logo_url`, `logo_source`, and `logo_observed_at_ms`. Add an ops command that syncs Binance symbol-list logo facts into existing CEX tokens without creating new CEX routes.

- [x] **Step 3: Keep one writer for public profile**

Update `TokenProfileCurrentWorker` to read CEX icon facts from `cex_tokens` and project them into `token_profile_current`; no script writes `token_profile_current` directly.

- [x] **Step 4: Verify CEX icon chain**

Run profile projection tests, migration, icon sync, profile rebuild, and API coverage checks.

### CEX Icon Results

- `ops sync-cex-token-icons` read `433` Binance symbol-list icons and updated `242` existing routed `cex_tokens`; missing entries were not inserted as new CEX routes.
- `ops rebuild-token-profiles --limit 1000` produced `50` ready `CexToken` profiles with provider `cex_token_icon_static`.
- `token_profile_current` now has `50/100` CEX profile rows with logos; remaining CEX unsupported rows are symbols not covered by the static crypto icon source, including non-crypto symbols.
- Authenticated API checks after Docker rebuild returned `200` for `/api/recent?limit=200&scope=matched` and `/api/token-radar?window=1h&limit=100&scope=all`.
