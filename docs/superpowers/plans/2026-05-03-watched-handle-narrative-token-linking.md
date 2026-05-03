# Watched Handle Narrative Token Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert watched-handle narrative statements into auditable token-link signals by using the full stored public stream as post-seed validation, while keeping full-stream monitoring and token-flow independent of LLM.

**Core constraint:** Only configured watched handles create narrative seeds. The full GMGN public stream is used only as deterministic uptake evidence after a seed exists.

**Related spec:** `docs/superpowers/specs/2026-05-03-watched-handle-narrative-token-linking-design.md`

---

## Current Logic Baseline

- `src/gmgn_twitter_intel/pipeline/ingest_service.py`
  - Persists evidence, entities, token mentions, token windows, and watched enrichment jobs in one transaction.
  - Already enqueues enrichment only for `is_watched` events with text.
  - This invariant must remain unchanged.

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
  - Deterministically extracts CA, cashtag, hashtag, mention, URL, and domain.
  - This remains the full-stream hot-path entity layer.

- `src/gmgn_twitter_intel/pipeline/token_identity_resolver.py`
  - Converts deterministic entities and GMGN token payloads into token mentions.
  - This remains the canonical token identity source for linking.

- `src/gmgn_twitter_intel/storage/signal_repository.py`
  - Owns `event_token_mentions`, token windows, account token alerts, and token-flow aggregation.
  - Narrative linking should query these facts rather than duplicate token-flow identity logic.

- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
  - Parses evidence-bound LLM output.
  - Require seed fields in narrative output; old narrative-only shapes are rejected.

- `src/gmgn_twitter_intel/storage/enrichment_repository.py`
  - Owns enrichment jobs, model runs, event enrichments, event narratives, account narrative alerts, and narrative windows.
  - Add seed/link storage here or split to a focused `NarrativeLinkRepository` if the file grows too large.

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
  - Already builds trader-grade token read models with identity, market, flow, source quality, freshness, signal, and evidence.
  - Narrative token-link retrieval should reuse this style and vocabulary.

- `src/gmgn_twitter_intel/api/http.py`, `src/gmgn_twitter_intel/api/ws.py`, `src/gmgn_twitter_intel/cli.py`
  - Expose read models and live updates.
  - Add new surfaces without changing existing response shapes.

- `web/src/App.tsx`, `web/src/api/types.ts`
  - Current cockpit is token-flow first with narrative flow as a side panel.
  - Add narrative badges and frontier panel after backend contracts are stable.

## File Structure

Expected new files:

- `src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py`
- `src/gmgn_twitter_intel/pipeline/narrative_token_linker.py`
- `src/gmgn_twitter_intel/retrieval/narrative_link_service.py`
- `src/gmgn_twitter_intel/retrieval/narrative_link_scoring.py`
- `tests/test_narrative_seed_builder.py`
- `tests/test_narrative_token_linker.py`
- `tests/test_narrative_link_service.py`

Likely modified files:

- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- `src/gmgn_twitter_intel/retrieval/narrative_service.py`
- `src/gmgn_twitter_intel/api/http.py`
- `src/gmgn_twitter_intel/api/ws.py`
- `src/gmgn_twitter_intel/cli.py`
- `src/gmgn_twitter_intel/api/app.py`
- `web/src/api/types.ts`
- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `README.md`

---

## Task 1: Write failing schema and repository tests

**Files:**
- Modify: `tests/test_sqlite_schema.py`
- Modify: `tests/test_enrichment_repository.py`
- Create: `tests/test_narrative_link_repository.py` if repository is split

- [ ] Assert new databases include `narrative_seeds` and `narrative_token_links`.
- [ ] Assert existing enrichment tables are still present.
- [ ] Assert seed insert is idempotent on `(event_id, narrative_label)`.
- [ ] Assert link upsert is idempotent on `(seed_id, token_identity_key, window)`.
- [ ] Assert deleting a seed cascades linked token rows.
- [ ] Assert rows decode JSON fields such as `seed_terms`, `matched_terms`, `reasons`, and `risks`.
- [ ] Run `uv run python -m pytest tests/test_sqlite_schema.py tests/test_enrichment_repository.py tests/test_narrative_link_repository.py -q`.
- [ ] Expected before implementation: failures for missing tables and methods.

## Task 2: Add schema and storage methods

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Modify: `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- Optional create: `src/gmgn_twitter_intel/storage/narrative_link_repository.py`

- [ ] Add `narrative_seeds` table and indexes.
- [ ] Add `narrative_token_links` table and indexes.
- [ ] Bump `SCHEMA_VERSION`.
- [ ] Add methods to insert/upsert seeds, fetch seed by ID/event/label, list recent seeds, upsert token links, list links for seed, and list frontier links.
- [ ] Keep new writes transactional with the existing shared SQLite connection and `RLock`.
- [ ] Keep existing enrichment/narrative product methods separate from the new seed/link methods; do not add legacy aliases or fallback contracts.
- [ ] Run Task 1 tests until green.

## Task 3: Extend LLM narrative parsing into seed-aware output

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- Modify: `tests/test_llm_enrichment.py`
- Create: `tests/test_narrative_seed_builder.py`

- [ ] Extend `NarrativeItem` with required `seed_family`, `trigger_terms`, and `market_interpretation`.
- [ ] Update prompt instructions so narratives describe market-interpretable seeds without inferring hidden tickers.
- [ ] Validate `evidence` by substring containment as today.
- [ ] Normalize and cap `trigger_terms`; reject terms not present in event evidence.
- [ ] Reject model output that lacks the new seed fields.
- [ ] Add tests for seed fields, evidence rejection, term normalization, confidence filtering, and old-shape rejection.
- [ ] Run `uv run python -m pytest tests/test_llm_enrichment.py tests/test_narrative_seed_builder.py -q`.

## Task 4: Build narrative seeds after watched enrichment completes

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py`
- Modify: `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- Modify: `tests/test_enrichment_worker.py`

- [ ] Convert completed watched-account `event_narratives` into `narrative_seeds`.
- [ ] Compute `source_weight` from watched status and available follower count; do not add separate source-tier config in v1.
- [ ] Compute `novelty_status` from prior seeds with same label globally and by author.
- [ ] Ensure only watched events can produce seeds, even if an LLM result somehow exists for an unwatched event.
- [ ] Publish existing `enrichment_update` unchanged.
- [ ] Add worker tests proving a watched enrichment creates seeds and an unwatched/manual enrichment does not.
- [ ] Run `uv run python -m pytest tests/test_enrichment_worker.py tests/test_narrative_seed_builder.py -q`.

## Task 5: Implement deterministic narrative-token linker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/narrative_token_linker.py`
- Create: `src/gmgn_twitter_intel/retrieval/narrative_link_scoring.py`
- Create: `tests/test_narrative_token_linker.py`

- [ ] For each seed, scan `event_token_mentions` after `seed.received_at_ms` within `5m`, `1h`, and `24h` windows.
- [ ] Join candidate mentions to `events` for text and source evidence.
- [ ] Use deterministic link reasons only: `seed_term_and_token_mention`, `seed_symbol_candidate_confirmed`, `name_or_alias_overlap`, and `watched_seed_direct_token`.
- [ ] Reject pure semantic links without text/entity evidence.
- [ ] Reuse token identity status from `event_token_mentions` and canonical token identity maps.
- [ ] Attach market status, market cap, and price change after seed when available from `TokenRepository`.
- [ ] Compute `seed_score`, `diffusion_score`, `token_link_score`, `tradeability_score`, `decision`, `reasons`, and `risks`.
- [ ] Upsert links idempotently.
- [ ] Add tests for direct token mention, later public-stream symbol confirmation, resolved CA ranking, unresolved symbol downgrade, author concentration risk, and no-link cases.
- [ ] Run `uv run python -m pytest tests/test_narrative_token_linker.py tests/test_token_conviction_flow.py -q`.

## Task 6: Wire linker into the async warm path

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `tests/test_enrichment_worker.py`
- Modify: `tests/test_api_health.py`

- [ ] After completing a watched enrichment and writing seeds, run the linker for those seeds inside the warm path.
- [ ] Keep LLM calls outside the DB lock, as today.
- [ ] Keep link writes inside the shared write lock.
- [ ] Add readiness counters for seed and link counts if useful, but do not make lack of links unhealthy.
- [ ] Ensure LLM failures do not affect full-stream ingest or token-flow.
- [ ] Add integration tests proving token-flow continues when enrichment jobs fail or are dead.
- [ ] Run `uv run python -m pytest tests/test_enrichment_worker.py tests/test_api_health.py -q`.

## Task 7: Add retrieval service, HTTP API, and CLI

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/narrative_link_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/narrative_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_api_http.py`
- Modify: `tests/test_project_structure.py`

- [ ] Add `narrative_seeds(window, limit, handles)` read model.
- [ ] Add `narrative_token_flow(seed_id, window, limit)` read model.
- [ ] Add `attention_frontier(window, limit)` read model.
- [ ] Add HTTP endpoints:
  - `/api/narrative-seeds`
  - `/api/narrative-token-flow`
  - `/api/attention-frontier`
- [ ] Add CLI commands:
  - `narrative-seeds`
  - `narrative-token-flow`
  - `attention-frontier`
- [ ] Keep existing `narrative-flow`, `account-narratives`, and `token-flow` outputs unchanged.
- [ ] Add API and CLI tests for empty state, one seed with links, handle filters, and invalid seed ID.
- [ ] Run `uv run python -m pytest tests/test_cli.py tests/test_api_http.py tests/test_project_structure.py -q`.

## Task 8: Add WebSocket link updates

**Files:**
- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Modify: `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- Modify: `tests/test_api_websocket.py`

- [ ] Publish `{"type":"narrative_link_update","seed":...,"links":[...]}` after link commit.
- [ ] Keep existing `event` and `enrichment_update` payloads stable while adding the new `narrative_link_update` payload.
- [ ] Do not require new subscription filters in v1.
- [ ] Ensure replay still returns event payloads with existing enrichment shape.
- [ ] Add WebSocket tests for update shape and existing event-routing behavior.
- [ ] Run `uv run python -m pytest tests/test_api_websocket.py -q`.

## Task 9: Add ops rebuild/backfill command

**Files:**
- Modify: `src/gmgn_twitter_intel/cli.py`
- Create or modify: relevant tests in `tests/test_cli.py`

- [ ] Add `uv run gmgn-twitter-intel ops rebuild-narrative-links --window 1h`.
- [ ] Rebuild seeds from existing `event_narratives` where possible.
- [ ] Rebuild token links idempotently for selected windows.
- [ ] Emit JSON with counts: seeds scanned, links upserted, links skipped, errors.
- [ ] Add tests proving repeated rebuilds do not duplicate rows.
- [ ] Run `uv run python -m pytest tests/test_cli.py -q`.

## Task 10: Update cockpit types and backend-only UI integration

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] Add TypeScript types for narrative seeds, token links, and attention frontier items.
- [ ] Fetch `/api/attention-frontier` and show a compact Narrative Frontier panel.
- [ ] Add narrative badges to token rows when a token has active links.
- [ ] In detail drawer, show seed evidence separately from token-link evidence.
- [ ] Show identity status and market status prominently to avoid implying LLM token recommendations.
- [ ] Add UI tests for seed row rendering, linked token evidence, empty state, and unchanged token-flow rendering.
- [ ] Run web test/build commands from `web/package.json`.

## Task 11: Documentation and operator guidance

**Files:**
- Modify: `README.md`
- Optional modify: `AGENTS.md`

- [ ] Update data-flow diagram to include `Narrative Seed -> Narrative Token Links`.
- [ ] Document that only watched handles create seeds.
- [ ] Document that the full public stream remains deterministic uptake evidence.
- [ ] Add CLI examples for new commands.
- [ ] Add operational notes for LLM-off behavior and rebuild command.
- [ ] Document caveats: `coverage=public_stream`, unresolved symbol risk, no automatic trading.

## Task 12: Final verification

**Files:**
- All touched files.

- [ ] Run `uv run pytest`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run python -m compileall src tests`.
- [ ] Run web tests/build if frontend changed.
- [ ] Smoke test:
  - `/readyz`
  - `/api/token-flow`
  - `/api/narrative-seeds`
  - `/api/narrative-token-flow`
  - `/api/attention-frontier`
  - `gmgn-twitter-intel token-flow`
  - `gmgn-twitter-intel narrative-seeds`
  - `gmgn-twitter-intel attention-frontier`
- [ ] Run one rebuild smoke command against a copied or test SQLite database.

## Acceptance Criteria

- Only watched-handle events create `narrative_seeds`.
- Full-stream ingest, search, deterministic entities, account token alerts, and token-flow still work without LLM.
- Full-stream events are used as post-seed uptake evidence.
- Link creation is deterministic after LLM seed extraction.
- Every token link has evidence, reason, confidence, lag, scores, decision, reasons, and risks.
- Pure LLM inference cannot create a tradable token link without later token evidence.
- Existing API, CLI, and WebSocket product surfaces still work, but no legacy aliases or old-shape parser fallbacks are added.
- Rebuild is idempotent.
- Cockpit presents seed evidence and token-link evidence separately.

## Rollout Notes

- Ship backend storage and read APIs before UI changes.
- Keep the first live rollout read-only and observational.
- Watch query latency for `narrative-token-flow`; add materialized `narrative_link_windows` only if needed.
- Treat `driver/watch/discard` as ranking language, not trade execution language.
- If LLM enrichment is off, all new narrative-link surfaces should return empty data with `ok: true`, while token-flow remains populated.
