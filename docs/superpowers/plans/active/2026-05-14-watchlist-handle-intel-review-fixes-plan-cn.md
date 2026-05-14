# Watchlist Handle Intel Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the review gaps in the Watchlist handle-intel implementation so the spec's timeline, summary, worker, API, and UI loop is production-ready.

**Architecture:** Keep the current `watchlist_intel` domain boundary, but tighten the public contract to match the spec. The backend owns cursor validation, indexed reads, summary state, lease-safe job completion, and failed run audit; the frontend consumes that contract via React Query infinite pagination without compatibility shims.

**Tech Stack:** Python 3, FastAPI, psycopg/PostgreSQL, Alembic, pytest, React, TypeScript, TanStack Query, Vitest, Playwright.

---

## File Structure

- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/types/__init__.py`: strict cursor validation.
- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/repositories/watchlist_intel_repository.py`: expression-index-friendly timeline SQL, token resolutions, lease-token completion/failure, failed run audit helpers.
- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_service.py`: spec summary fields and lease-aware summarize/complete.
- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`: true concurrent worker loops, provider timeout, failed run recording.
- Modify `src/gmgn_twitter_intel/platform/db/alembic/versions/20260514_0045_watchlist_handle_intel.py`: add `lease_token` and expression index on `lower(author_handle)`.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/http.py`: `asyncio.to_thread` boundary and `Query(default=30, ge=1, le=100)` timeline contract.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`, `web/src/lib/types/frontend-contracts.ts`, and regenerated `web/src/lib/types/openapi.ts`: summary status/stale/pending and timeline `token_resolutions`.
- Modify `src/gmgn_twitter_intel/app/runtime/app.py`: readiness/watchdog naming and worker concurrency wiring.
- Restore/modify `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/generated/db-schema.md`, `docs/generated/openapi.json`, and `config.example.yaml`.
- Modify `web/src/features/watchlist/api/useHandleTimelineQuery.ts`: `useInfiniteQuery` with cursor `pageParam`.
- Modify `web/src/features/watchlist/ui/WatchlistPage.tsx` and `watchlist.css`: append pages, load-more button, not-ready/stale states.
- Add/modify tests under `tests/unit/domains/watchlist_intel/`, `tests/integration/watchlist/`, `tests/integration/test_api_health.py`, and `web/tests/component/features/watchlist/`.

### Task 1: Backend Contract Tests

**Files:**
- Modify: `tests/unit/domains/watchlist_intel/test_cursor.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_api.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_repository.py`

- [ ] **Step 1: Write failing cursor boundary test**

Add a case asserting `decode_watchlist_timeline_cursor(encode_watchlist_timeline_cursor(received_at_ms=0, event_id="event-1"))` raises `WatchlistTimelineCursorError`.

- [ ] **Step 2: Write failing summary not-ready/stale API tests**

In `test_watchlist_intel_api.py`, fake no stored summary and a pending job. Assert `/summary` returns `status: "not_ready"`, `pending_recompute: true`, and no empty fake summary. Add a stored old summary case asserting `is_stale: true`.

- [ ] **Step 3: Write failing timeline limit contract tests**

Assert `/timeline?limit=0` returns 422 and default limit is `30`.

- [ ] **Step 4: Write failing repository shape/performance tests**

Add an integration test that timeline items include `token_resolutions`. Add an EXPLAIN test that the timeline query uses `idx_events_author_received_event_lower_desc`.

- [ ] **Step 5: Run the red tests**

Run:

```bash
uv run pytest tests/unit/domains/watchlist_intel/test_cursor.py tests/integration/watchlist/test_watchlist_intel_api.py tests/integration/watchlist/test_watchlist_intel_repository.py -q
```

Expected: failures for cursor zero acceptance, missing summary status fields, limit contract, token resolutions, and index name.

### Task 2: Worker Reliability Tests

**Files:**
- Create: `tests/unit/domains/watchlist_intel/test_handle_summary_worker.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_repository.py`
- Modify: `tests/integration/test_api_health.py`

- [ ] **Step 1: Write failing lease-owner tests**

Claim the same job twice after lease expiry; assert completing the old claim does not delete or overwrite the newer claim. Assert completing the current claim succeeds.

- [ ] **Step 2: Write failing failed-run audit test**

Use a provider that raises. Assert `watchlist_handle_summary_runs` gets a `status="failed"` row with the error and request context.

- [ ] **Step 3: Write failing concurrency test**

Create two due jobs and a provider that waits on an event. Run one `process_due_jobs_once_async()` with concurrency `2`; assert both provider calls enter before either completes.

- [ ] **Step 4: Write failing watchdog test**

In API health tests, set `watchlist_handle_summary_worker` present and its task stopped. Assert `_watchdog_unhealthy_reasons` includes `watchlist_handle_summary_worker_stopped`.

- [ ] **Step 5: Run the red tests**

Run:

```bash
uv run pytest tests/unit/domains/watchlist_intel/test_handle_summary_worker.py tests/integration/watchlist/test_watchlist_intel_repository.py tests/integration/test_api_health.py::test_watchdog_flags_stopped_watchlist_handle_summary_worker -q
```

Expected: failures for lease token absence, no failed run, sequential worker behavior, and missing watchdog reason.

### Task 3: Backend Implementation

**Files:**
- Modify the backend files listed above.

- [ ] **Step 1: Add lease token to migration and repository**

Add `lease_token TEXT`, set it on claim using a deterministic opaque token, and require `WHERE handle = %s AND lease_token = %s AND status = 'running'` for complete/fail.

- [ ] **Step 2: Fix timeline query and index**

Change the migration index to:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_author_received_event_lower_desc
  ON events(lower(author_handle), received_at_ms DESC, event_id DESC)
```

Keep timeline filtering as `lower(e.author_handle) = %s`, and add `token_resolutions` from `token_intent_resolutions` for each event.

- [ ] **Step 3: Align summary contract**

Return `status`, `is_stale`, and `pending_recompute` from the read service. Use `status="not_ready"` when no summary row exists and `status="ready"` otherwise.

- [ ] **Step 4: Move API reads off the event loop**

Wrap new watchlist API DB reads with `await asyncio.to_thread(...)`. Set timeline limit as `Query(default=30, ge=1, le=100)`.

- [ ] **Step 5: Implement true worker concurrency and failed audit**

Rename internal `batch_size` semantics to concurrency, run claimed jobs with `asyncio.gather`, bound provider calls with `asyncio.wait_for`, and insert failed run rows before marking jobs failed.

- [ ] **Step 6: Run backend green tests**

Run the Task 1 and Task 2 commands until they pass.

### Task 4: Frontend Infinite Timeline

**Files:**
- Modify: `web/src/features/watchlist/api/useHandleTimelineQuery.ts`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify: `web/src/features/watchlist/ui/watchlist.css`
- Create: `web/tests/component/features/watchlist/useHandleTimelineQuery.test.tsx`
- Create: `web/tests/component/features/watchlist/WatchlistPage.test.tsx`

- [ ] **Step 1: Write failing hook test**

Mock `global.fetch`, render the hook, call `fetchNextPage()`, and assert the second request includes `cursor=cursor-1`.

- [ ] **Step 2: Write failing UI test**

Render `WatchlistPage` with mocked API pages. Assert first page items render, the `Load more` button appears, clicking it appends the second page, and scope switch resets to the new scope.

- [ ] **Step 3: Run red frontend tests**

Run:

```bash
npm test -- --run tests/component/features/watchlist/useHandleTimelineQuery.test.tsx tests/component/features/watchlist/WatchlistPage.test.tsx
```

Expected: failure because current hook is `useQuery` and UI has no load-more control.

- [ ] **Step 4: Implement `useInfiniteQuery` and UI append**

Use `getNextPageParam: (last) => last.data.next_cursor ?? undefined`, keep 15s polling only on the first page, flatten pages in UI, and render a stable icon+text `Load more` button.

- [ ] **Step 5: Run green frontend tests**

Run the Task 4 command until it passes.

### Task 5: Docs, Config, Generated Contracts

**Files:**
- Restore/modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `config.example.yaml`
- Regenerate: `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`
- Modify: `docs/generated/db-schema.md`

- [ ] **Step 1: Restore worker governance**

Restore `docs/WORKERS.md` from `origin/main` and add a `HandleSummaryWorker` row.

- [ ] **Step 2: Fix config example**

Revert unrelated `pulse_agent_trigger_min_rank_score` change and add `watchlist_handle_summary_*` knobs under `llm`.

- [ ] **Step 3: Regenerate public contracts**

Run:

```bash
make regen-contract
```

Expected: OpenAPI and frontend generated types reflect `status`, `is_stale`, `pending_recompute`, `token_resolutions`, and timeline limit constraints.

- [ ] **Step 4: Update db schema doc**

Regenerate if the local migrated DB is available; otherwise manually align only the new watchlist tables/indexes with the migration and note no unrelated schema drift.

### Task 6: Final Verification and Review

**Files:** no new implementation files.

- [ ] **Step 1: Run targeted backend verification**

```bash
uv run pytest tests/unit/test_settings.py tests/unit/domains/watchlist_intel/test_cursor.py tests/unit/domains/watchlist_intel/test_handle_summary_worker.py tests/integration/watchlist/test_watchlist_intel_api.py tests/integration/watchlist/test_watchlist_intel_repository.py tests/integration/test_enrichment_worker.py::test_enrichment_worker_enqueues_watchlist_summary_job_in_completion_transaction tests/integration/test_api_health.py::test_watchdog_flags_stopped_watchlist_handle_summary_worker tests/architecture/test_src_domain_architecture.py -q
```

- [ ] **Step 2: Run static checks**

```bash
uv run ruff check src/gmgn_twitter_intel/domains/watchlist_intel src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py src/gmgn_twitter_intel/app/runtime src/gmgn_twitter_intel/app/surfaces/api src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py tests/unit/domains/watchlist_intel tests/integration/watchlist tests/integration/test_enrichment_worker.py tests/integration/test_api_health.py tests/unit/test_settings.py tests/architecture/test_src_domain_architecture.py
uv run mypy src/gmgn_twitter_intel/domains/watchlist_intel src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py
```

- [ ] **Step 3: Run frontend verification**

```bash
cd web
npm test -- --run tests/unit/features/watchlist/model/watchlistRows.test.ts tests/unit/features/watchlist/model/watchlistCase.test.ts tests/routes/watchlist.route.test.tsx tests/component/features/watchlist/useHandleTimelineQuery.test.tsx tests/component/features/watchlist/WatchlistPage.test.tsx
npm run format:check
npm run lint
npm run build
```

- [ ] **Step 4: Browser QA**

Start the local frontend with mocked API data, inspect desktop and mobile viewports, and verify no horizontal overflow, no topbar overlap, and load-more appends items without layout shift.

- [ ] **Step 5: Request independent review again**

Spawn a fresh read-only review agent against the same spec and current working tree. Target score: no Critical issues, production readiness at least 8/10, overall completion at least 85/100.
