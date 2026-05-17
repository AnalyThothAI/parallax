# Event Anchor Backfill Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple event-anchor facts from worker queue state so Token Radar no longer gets stuck behind permanent `pending_backfill` rows.

**Architecture:** `market_ticks` remains append-only market truth. `enriched_events` keeps only event-anchor fact lifecycle: pending, ready, or terminal unavailable. A new `event_anchor_backfill_jobs` control-plane table owns retry, due-time, attempts, active window, and terminal job state.

**Tech Stack:** Python, psycopg/PostgreSQL, Alembic migrations, pytest.

---

### Task 1: Lock The Queue/Facts Boundary With Tests

**Files:**
- Modify: `tests/unit/test_event_anchor_backfill_worker.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`
- Create: `tests/unit/test_event_anchor_backfill_job_repository.py`

- [ ] **Step 1: Add worker tests that prove stale pending rows are expired and unavailable rows do not stay queued**

Expected behavior:
- Worker lists jobs from `event_anchor_backfill_jobs`, not directly from `enriched_events`.
- Expired jobs transition `enriched_events` to `capture_method='unavailable', capture_reason='backfill_expired'`.
- `provider_no_quote` transitions to terminal unavailable immediately.
- `rate_limited` is rescheduled only while attempts and active window remain.

- [ ] **Step 2: Add schema tests for the new control-plane table and narrow trigger**

Expected behavior:
- `event_anchor_backfill_jobs` exists.
- It has a due index for `status='pending'`.
- The trigger permits only `pending_backfill -> async_backfill` and `pending_backfill -> terminal unavailable`.
- Other `enriched_events` updates still raise `market facts are append-only`.

- [ ] **Step 3: Run targeted tests and confirm RED**

Run:
```bash
uv run pytest tests/unit/test_event_anchor_backfill_worker.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected:
- Fails because repository/session/job table/trigger behavior does not exist yet.

### Task 2: Add The Event-Anchor Job Control Plane

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/bootstrap.py`

- [ ] **Step 1: Create repository methods**

Repository methods:
- `enqueue_for_capture(capture, active_window_ms)`
- `list_due(limit, now_ms, min_age_ms)`
- `list_expired(limit, now_ms)`
- `mark_done(event_id, intent_id, now_ms)`
- `mark_terminal(event_id, intent_id, status, reason, now_ms)`
- `reschedule(event_id, intent_id, reason, now_ms, next_run_at_ms)`

- [ ] **Step 2: Wire the repository into repository sessions**

`RepositorySession` gets `event_anchor_jobs`, and `repositories_for_connection()` constructs it.

- [ ] **Step 3: Enqueue jobs during ingest**

When ingest writes an `EnrichedEventCapture` with `capture_method='unavailable'` and `capture_reason='pending_backfill'`, it also inserts one job with `active_until_ms = created_at_ms + active_window_ms`.

### Task 3: Make Worker Consume Jobs, Not Facts

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/enriched_event_repository.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`

- [ ] **Step 1: Add explicit runtime knobs**

Settings:
- `active_window_ms=300000`
- `max_anchor_lag_ms=60000`

- [ ] **Step 2: Add nearest event tick lookup**

`MarketTickRepository.nearest_around(target_type, target_id, at_ms, max_lag_ms)` returns the nearest persisted tick inside `[event_ms - max_lag_ms, event_ms + max_lag_ms]`.

- [ ] **Step 3: Update worker flow**

Worker flow:
1. Expire stale jobs and mark corresponding `enriched_events` terminal `backfill_expired`.
2. List due jobs.
3. Attach an existing nearest tick first.
4. Call provider only when the event is still within `max_anchor_lag_ms`.
5. On success, insert tick, attach capture, mark job `done`, emit wake.
6. On terminal provider miss, mark enriched event terminal and job `failed`.
7. On temporary rate limit, reschedule or terminal-fail if attempts/window are exhausted.

### Task 4: Add Hard-Cut Migration

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0060_event_anchor_backfill_jobs.py`

- [ ] **Step 1: Create job table and indexes**

Create `event_anchor_backfill_jobs` with primary key `(event_id, intent_id)`, status check, target fields, active window fields, attempts, and timestamps.

- [ ] **Step 2: Replace trigger**

Allow only:
- pending event anchor becomes `tier3_inline/async_backfill` with non-null tick.
- pending event anchor becomes terminal unavailable with null tick.

- [ ] **Step 3: Migrate existing rows**

Expire existing `pending_backfill` rows older than five minutes. Insert jobs only for still-fresh `pending_backfill` rows.

### Task 5: Documentation And Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

- [ ] **Step 1: Document the new boundary**

Docs must state that `event_anchor_backfill_jobs` is control plane, while `enriched_events` is event-anchor fact lifecycle.

- [ ] **Step 2: Run targeted verification**

Run:
```bash
uv run pytest tests/unit/test_event_anchor_backfill_worker.py tests/unit/test_event_anchor_backfill_job_repository.py tests/integration/test_postgres_schema_runtime.py -q
```

- [ ] **Step 3: Run architecture/unit smoke**

Run:
```bash
uv run pytest tests/unit/test_postgres_schema.py tests/architecture/test_event_anchor_capture_redesign_contracts.py -q
```
