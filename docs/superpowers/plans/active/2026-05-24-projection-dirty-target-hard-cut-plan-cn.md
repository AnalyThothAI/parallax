# Projection Dirty Target Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-24
**Owning spec:** `docs/superpowers/specs/active/2026-05-24-projection-dirty-target-hard-cut-cn.md`
**Recommended worktree:** `.worktrees/projection-dirty-target-hard-cut`
**Recommended branch:** `codex/projection-dirty-target-hard-cut`

**Goal:** Remove scan-based runtime projection discovery from Equity and News and replace it with durable domain-owned dirty targets.

**Architecture:** This is a hard cut. Normal projection workers claim dirty targets and load source payloads by explicit target ids only. Broad coverage scans move to a one-shot repair command and architecture tests prevent reintroducing scan-based projection discovery.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3 repositories, existing worker runtime, pytest architecture tests, Docker Compose live verification.

---

## Hard-Cut Verdict

This plan is only complete if the scan-based runtime paths are removed from normal workers.

- Root fix: fact writers enqueue durable dirty targets in the same DB transaction as source facts.
- Root fix: fact writers enqueue durable dirty targets for both new targets and old targets invalidated by replacement, rejection, deletion, source metadata changes, or time-driven projection transitions.
- Root fix: projection workers claim due targets with leases and project by explicit ids.
- Root fix: no-work projection loops are O(due dirty targets), not O(source facts).
- Root fix: architecture tests fail on new projection workers that discover stale rows through broad scans.
- Not root fix: increasing `interval_seconds`.
- Not root fix: keeping current summary guards as fallback.
- Not root fix: adding a feature flag to choose dirty queue versus legacy scan.

## Pre-flight

- [ ] Confirm active branch and unrelated changes before implementation:
  ```bash
  git status --short
  git branch --show-current
  ```
  Expected: user-owned unrelated files are noted and left untouched.

- [ ] Create an isolated implementation worktree:
  ```bash
  git worktree add .worktrees/projection-dirty-target-hard-cut -b codex/projection-dirty-target-hard-cut main
  cd .worktrees/projection-dirty-target-hard-cut
  git status --short
  ```
  Expected: clean worktree on `codex/projection-dirty-target-hard-cut`.

- [ ] Confirm real runtime config paths before live verification:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`; secret values are not printed.

- [ ] Capture baseline live table counts and worker statuses:
  ```bash
  docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "
  select relname, n_live_tup
  from pg_stat_user_tables
  where relname in (
    '\''equity_company_events'\'', '\''equity_event_page_rows'\'',
    '\''equity_company_timeline_rows'\'', '\''equity_event_alert_candidates'\'',
    '\''news_items'\'', '\''news_page_rows'\'', '\''news_source_quality_rows'\''
  )
  order by relname;"'
  curl -fsS http://localhost:8765/readyz | jq '.workers.equity_event_page_projection, .workers.news_page_projection, .workers.news_source_quality_projection'
  ```
  Expected: counts and worker notes are recorded in the verification artefact.

## File Structure

### Create

- `src/parallax/domains/equity_event_intel/repositories/equity_projection_dirty_target_repository.py`
  Domain-owned enqueue, claim, mark-done, mark-error, queue-depth, and backfill target selection for Equity projection control rows.
- `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
  Domain-owned enqueue, claim, mark-done, mark-error, queue-depth, and backfill target selection for News projection control rows.
- `src/parallax/platform/db/alembic/versions/20260524_0094_projection_dirty_targets_hard_cut.py`
  Creates `equity_event_projection_dirty_targets`, `news_projection_dirty_targets`, News projection payload hash/source watermark columns, and lease/due indexes.
- `src/parallax/app/ops/projection_dirty_targets.py`
  One-shot dry-run/execute command that enqueues dirty targets from existing facts for rollout repair only.
- `tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py`
  Tests coalescing, lease claim, done, error, and queue depth.
- `tests/unit/domains/news_intel/test_news_projection_dirty_target_repository.py`
  Tests coalescing, source/window uniqueness, lease claim, re-enqueue while leased, done, error, and queue depth.
- `tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py`
  Worker tests proving empty queue does not call legacy scan and claimed ids project only target-scoped rows.
- `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`
  Worker tests for News Page and Source Quality dirty-queue execution.
- `tests/architecture/test_projection_worker_idle_cost_contract.py`
  AST-level architecture test banning broad runtime scan discovery in projection workers.

### Modify

- `src/parallax/app/runtime/repository_session.py`
  Add `equity_projection_dirty_targets` and `news_projection_dirty_targets` repository session attributes.
- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
  Delete normal-use scan methods and add target-id payload loaders.
- `src/parallax/domains/equity_event_intel/runtime/equity_event_process_worker.py`
  Enqueue Equity dirty targets after company event, old replaced/rejected event, fact, and document writes.
- `src/parallax/domains/equity_event_intel/runtime/equity_event_story_projection_worker.py`
  Claim story dirty targets and enqueue page/brief targets after story writes.
- `src/parallax/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
  Enqueue page/timeline/alert dirty targets after current brief writes.
- `src/parallax/domains/equity_event_intel/runtime/equity_event_source_reconcile_worker.py`
  Enqueue calendar dirty targets after expected-event reconcile writes and page/timeline/alert/calendar targets after universe metadata changes.
- `src/parallax/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py`
  Replace summary/scan logic with dirty-target claim and target-scoped projection.
- `src/parallax/domains/news_intel/repositories/news_repository.py`
  Delete normal-use page scan method and add target-id payload loaders plus source/window quality input loader.
- `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
  Enqueue News Page, Story, and Source Quality dirty targets after source metadata, provider item, news item, and old replaced item writes.
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
  Enqueue News Page, Story, and Source Quality targets after entity, mention, fact, and classification writes.
- `src/parallax/domains/news_intel/runtime/news_story_projection_worker.py`
  Claim story dirty targets and enqueue page/brief targets after story writes.
- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  Enqueue News Page and Source Quality targets after brief writes.
- `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
  Claim news-item page dirty targets and project by explicit ids.
- `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py`
  Claim source/window dirty targets, aggregate only those targets, reschedule time-driven windows, and enqueue page targets when source quality status changes.
- `tests/architecture/test_worker_runtime_contracts.py`
  Add dirty-target tables to single-writer read/control model ownership if needed.
- `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`
  Document the idle-cost contract and dirty-target control source for projection workers.

### Delete From Normal Runtime

- `EquityEventRepository.page_projection_source_summary`
- `EquityEventRepository.list_events_for_page_projection`
- `EquityEventRepository.list_expected_events_for_calendar_projection`
- `EquityEventRepository.list_inactive_expected_event_ids_for_calendar_projection`
- `NewsRepository.list_items_for_page_projection`
- `NewsRepository.list_source_quality_inputs`
- Any runtime call from projection workers to `list_events_missing_story` or `list_items_missing_story`

If a maintenance command needs broad coverage discovery, it must live under `app/ops`, be manually invoked, and enqueue dirty targets only. Do not add a scheduled audit worker, cron, low-frequency loop, or compatibility runtime scan.

## Storage Design

Add Alembic revision `20260524_0094` after `20260524_0093`.

```sql
CREATE TABLE IF NOT EXISTS equity_event_projection_dirty_targets (
  projection_name TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  dirty_reason TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  source_watermark_ms BIGINT NOT NULL DEFAULT 0,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  first_dirty_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (projection_name, target_kind, target_id),
  CHECK (projection_name IN ('story', 'brief_input', 'page', 'timeline', 'alert', 'calendar')),
  CHECK (target_kind IN ('company_event', 'expected_event', 'company'))
);

CREATE INDEX IF NOT EXISTS idx_equity_projection_dirty_due
  ON equity_event_projection_dirty_targets(due_at_ms, leased_until_ms, priority, updated_at_ms, projection_name, target_kind, target_id);

CREATE INDEX IF NOT EXISTS idx_equity_projection_dirty_lease
  ON equity_event_projection_dirty_targets(leased_until_ms, due_at_ms);
```

```sql
CREATE TABLE IF NOT EXISTS news_projection_dirty_targets (
  projection_name TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  window TEXT NOT NULL DEFAULT '',
  dirty_reason TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  source_watermark_ms BIGINT NOT NULL DEFAULT 0,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  first_dirty_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (projection_name, target_kind, target_id, window),
  CHECK (projection_name IN ('story', 'page', 'source_quality')),
  CHECK (target_kind IN ('news_item', 'source')),
  CHECK (
    (projection_name = 'source_quality' AND target_kind = 'source' AND window <> '')
    OR (projection_name <> 'source_quality' AND target_kind = 'news_item' AND window = '')
  )
);

CREATE INDEX IF NOT EXISTS idx_news_projection_dirty_due
  ON news_projection_dirty_targets(due_at_ms, leased_until_ms, priority, updated_at_ms, projection_name, target_kind, target_id, window);

CREATE INDEX IF NOT EXISTS idx_news_projection_dirty_lease
  ON news_projection_dirty_targets(leased_until_ms, due_at_ms);
```

Add News projection no-op guard columns:

```sql
ALTER TABLE news_page_rows
  ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0;

ALTER TABLE news_source_quality_rows
  ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0;
```

The repository claim query uses `FOR UPDATE SKIP LOCKED` inside an update CTE and returns claimed rows. Claimed rows include a completion token: full target key, `payload_hash`, `lease_owner`, and `attempt_count`. `mark_done` deletes successful dirty rows only when the full completion token still matches. `mark_error` clears the lease and schedules retry only when the full completion token still matches. Missing token fields raise `ValueError`. This prevents an old claim from deleting materially newer dirty work that was re-enqueued while the old lease was active. A pure duplicate enqueue with the same target, reason, payload hash, and source watermark is only a wake hint and should not invalidate the current lease. Dirty-target fallback `payload_hash` excludes queue scheduling/control metadata such as `priority`, `due_at_ms`, lease fields, attempts, errors, and audit timestamps.

## Task 1: Add Dirty Target Storage And Repositories

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260524_0094_projection_dirty_targets_hard_cut.py`
- Create: `src/parallax/domains/equity_event_intel/repositories/equity_projection_dirty_target_repository.py`
- Create: `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_projection_dirty_target_repository.py`

- [ ] **Step 1: Write failing repository tests**
  Add tests that assert:
  - enqueue coalesces duplicate target keys and keeps earliest `first_dirty_at_ms`;
  - claim leases due rows with `lease_owner` and increments `attempt_count`;
  - claimed rows are skipped by a second claimer until lease expiry;
  - re-enqueue while leased changes the row so the old claim token cannot mark it done or errored;
  - mark done deletes rows;
  - mark error stores compact error text and schedules retry;
  - News source-quality uniqueness includes `window`.

- [ ] **Step 2: Run focused tests and confirm repository classes are missing**
  ```bash
  uv run pytest \
    tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py \
    tests/unit/domains/news_intel/test_news_projection_dirty_target_repository.py -q
  ```
  Expected: import failures for the new repositories.

- [ ] **Step 3: Add migration and repository classes**
  Implement the SQL in the Storage Design section. Follow `TokenRadarDirtyTargetRepository` for enqueue/claim semantics, but keep Equity and News repositories domain-owned. Claim completion must be token-matched, not target-key-only.

- [ ] **Step 4: Wire repositories into `RepositorySession`**
  Add constructor imports, dataclass fields, and `repositories_for_connection(...)` instances:
  ```python
  equity_projection_dirty_targets=EquityProjectionDirtyTargetRepository(conn),
  news_projection_dirty_targets=NewsProjectionDirtyTargetRepository(conn),
  ```

- [ ] **Step 5: Run repository tests**
  ```bash
  uv run pytest \
    tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py \
    tests/unit/domains/news_intel/test_news_projection_dirty_target_repository.py -q
  ```
  Expected: all tests pass.

## Task 2: Hard-Cut Equity Page, Calendar, Timeline, Alert Projection

**Files:**
- Modify: `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_source_reconcile_worker.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py`
- Test: existing `tests/unit/domains/equity_event_intel/test_equity_page_projection_worker.py`

- [ ] **Step 1: Add failing worker tests**
  Add tests proving:
  - empty dirty queue returns `claimed=0` and the fake repository raises if `page_projection_source_summary()` or `list_events_for_page_projection()` is called;
  - claimed `company_event` targets call a new payload loader with only claimed ids;
  - claimed `expected_event` targets call calendar loader with only claimed ids;
  - company event processing enqueues calendar dirty targets for matching expected events;
  - expected events schedule `due_at_ms` at the expected event boundary for expected-to-missed projection transitions;
  - universe member changes enqueue page/timeline/alert/calendar targets for existing company events;
  - mark done is called after successful target-scoped writes;
  - mark error is called when payload loading or projection raises.

- [ ] **Step 2: Add target-id payload loaders**
  Replace broad candidate discovery with explicit loaders:
  ```python
  def load_event_page_projection_payloads(self, *, company_event_ids: Sequence[str]) -> list[dict[str, Any]]:
      ...

  def load_expected_calendar_projection_payloads(
      self,
      *,
      expected_event_ids: Sequence[str],
      now_ms: int,
  ) -> list[dict[str, Any]]:
      ...
  ```
  These queries must use `WHERE ... = ANY(%s::text[])` before joining derived payload pieces.

- [ ] **Step 3: Rewrite `EquityEventPageProjectionWorker.run_once_sync`**
  New flow:
  - claim due dirty rows for `projection_name IN ('page', 'timeline', 'alert', 'calendar')`;
  - split claimed rows by `target_kind`;
  - load company-event payloads and expected-event payloads by id;
  - build rows with existing projection services;
  - call existing target-scoped replace methods;
  - delete alert/page/timeline/calendar rows only for claimed targets that are now ineligible;
  - mark successful claim tokens done;
  - mark failed claim tokens retryable.

- [ ] **Step 4: Enqueue dirty targets from Equity source writers**
  Add enqueue calls in the same repository session and transaction:
  - event process writes enqueue `story`, `brief_input`, `page`, `timeline`, `alert`, and matching `calendar` for current and old replaced/rejected `company_event_id` values;
  - brief writes enqueue `page`, `timeline`, and `alert` for `company_event_id`;
  - source reconcile writes enqueue `calendar` for `expected_event_id`;
  - source reconcile writes that change universe company metadata enqueue `page`, `timeline`, `alert`, and `calendar` for existing company events under that company;
  - expected calendar dirty targets whose status can change with time are enqueued with `due_at_ms` equal to the next status boundary, not only `now_ms`.

- [ ] **Step 5: Delete legacy page discovery**
  Remove `page_projection_source_summary()` and `list_events_for_page_projection()` from normal repository code and update tests that referenced `event_scan`.

- [ ] **Step 6: Run Equity focused tests**
  ```bash
  uv run pytest \
    tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py \
    tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py \
    tests/unit/domains/equity_event_intel/test_equity_page_projection_worker.py -q
  ```
  Expected: all tests pass and worker notes contain `claimed`, not `event_scan`.

## Task 3: Hard-Cut Equity Story Projection Discovery

**Files:**
- Modify: `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_story_projection_worker.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_story_projection_dirty_targets.py`

- [ ] **Step 1: Add failing story worker tests**
  Assert empty dirty queue does not call `list_events_missing_story()`, and claimed story targets load events by claimed `company_event_id`.

- [ ] **Step 2: Add `load_events_for_story_projection(company_event_ids)`**
  The loader returns the same event shape used by story grouping, but only for explicit ids.

- [ ] **Step 3: Rewrite story worker to claim `projection_name='story'`**
  The worker claims dirty story rows, loads explicit events, runs existing `choose_story_assignment(...)`, writes story group/member rows, then enqueues downstream `brief_input`, `page`, `timeline`, and `alert` targets.

- [ ] **Step 4: Remove runtime use of `list_events_missing_story()`**
  The method may be deleted if no non-runtime tests need it. If a coverage repair command needs missing-story discovery, implement that query inside `app/ops/projection_dirty_targets.py` and make it enqueue only.

- [ ] **Step 5: Run Equity story tests**
  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_equity_story_projection_dirty_targets.py -q
  ```
  Expected: all tests pass.

## Task 4: Hard-Cut News Page Projection

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`

- [ ] **Step 1: Add failing News Page worker tests**
  Assert empty dirty queue does not call `list_items_for_page_projection()`, and claimed `news_item` ids are the only ids loaded.

- [ ] **Step 2: Add explicit News Page payload loader**
  ```python
  def load_items_for_page_projection(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
      ...
  ```
  The query must filter `news_items.news_item_id = ANY(...)` before joining story, mention, fact, and brief rows.

- [ ] **Step 3: Rewrite `NewsPageProjectionWorker`**
  The worker claims `projection_name='page'`, loads only claimed news items, builds rows with `build_news_page_row(...)`, writes target-scoped rows, marks done/error, and returns notes with `claimed` and `projected`.

- [ ] **Step 4: Enqueue page dirty targets from News source writers**
  Enqueue page targets in the same transaction after:
  - `news_fetch` writes or updates a `news_item`;
  - `news_fetch` reconciles source metadata that changes source fields embedded in existing page rows;
  - `news_fetch` or `upsert_news_item(status="updated")` invalidates old story/page rows for a previously projected item;
  - `news_item_process` replaces entities, token mentions, and fact candidates;
  - `news_item_brief` writes current brief state;
  - `news_source_quality_projection` changes `news_sources.source_quality_status`.

- [ ] **Step 5: Delete legacy News Page discovery and direct page-row deletes**
  Remove normal runtime use of `list_items_for_page_projection()`. Delete the method if no ops-only code needs it. Remove direct source-writer deletes of `news_page_rows`; page projection owns target-scoped replacement/deletion.

- [ ] **Step 6: Run News Page focused tests**
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_projection_dirty_target_repository.py \
    tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q
  ```
  Expected: all tests pass.

## Task 5: Hard-Cut News Story Projection Discovery

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_story_projection_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_story_projection_dirty_targets.py`

- [ ] **Step 1: Add failing story worker tests**
  Assert empty dirty queue does not call `list_items_missing_story()`, and claimed story rows load explicit `news_item_id` values.

- [ ] **Step 2: Add `load_items_for_story_projection(news_item_ids)`**
  Preserve current story grouping input fields and token target aggregation while filtering by explicit ids.

- [ ] **Step 3: Rewrite `NewsStoryProjectionWorker`**
  The worker claims `projection_name='story'`, runs existing `choose_story_assignment(...)`, writes story group/member rows, and enqueues downstream `page` dirty targets.

- [ ] **Step 4: Remove runtime use of `list_items_missing_story()`**
  Keep missing-story discovery only inside the repair command if needed.

- [ ] **Step 5: Run News story tests**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_story_projection_dirty_targets.py -q
  ```
  Expected: all tests pass.

## Task 6: Hard-Cut News Source Quality Projection

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py`

- [ ] **Step 1: Add failing Source Quality tests**
  Assert the worker claims `source_quality` targets by `source_id/window`, does not recompute all sources/windows, and enqueues only changed source/window pairs.

- [ ] **Step 2: Add source/window-scoped input loader**
  ```python
  def list_source_quality_inputs_for_targets(
      self,
      *,
      source_windows: Sequence[tuple[str, str]],
      now_ms: int,
  ) -> list[dict[str, Any]]:
      ...
  ```
  The query must constrain by source id and window label before aggregating item, mention, fact, brief, fetch, and context data.

- [ ] **Step 3: Rewrite `NewsSourceQualityProjectionWorker`**
  The worker claims dirty targets, groups them by window, calls the scoped loader, writes rows with `replace_source_quality_rows(...)`, and marks targets done/error.

- [ ] **Step 4: Enqueue source-quality targets**
  Enqueue configured windows for affected `source_id` after fetch runs, source metadata changes, item processing, fact replacement, and brief writes. The enqueue helper receives `source_quality_windows` from `settings.workers.news_source_quality_projection.windows`; CLI repair reads the same setting through loaded runtime config. Add tests for a custom windows tuple.

- [ ] **Step 4.5: Reschedule time-driven source-quality targets**
  After projecting a source/window pair, compute the next `due_at_ms` for sliding-window expiry and freshness transitions and enqueue the same source/window dirty target for that time. This keeps source quality correct without a scheduled broad scan.

- [ ] **Step 4.6: Enqueue News Page targets when source quality status changes**
  When `replace_source_quality_rows(...)` changes `news_sources.source_quality_status`, enqueue page dirty targets for existing news items from that source. Add a test proving Page rows refresh after status changes.

- [ ] **Step 5: Run Source Quality tests**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py -q
  ```
  Expected: all tests pass.

## Task 7: Add One-Shot Repair Enqueue Command

**Files:**
- Create: `src/parallax/app/ops/projection_dirty_targets.py`
- Modify: CLI registration file that owns `parallax ops` commands
- Test: `tests/unit/test_ops_projection_dirty_targets.py`

- [ ] **Step 1: Add failing CLI tests**
  Assert dry-run reports counts without writing dirty rows, and execute enqueues:
  - Equity company events for story/page/timeline/alert/brief input;
  - Equity expected events for calendar;
  - News items for story/page;
  - News sources for configured source-quality windows;
  - projection-version bump coverage for all affected projection names, implemented as dirty enqueue only.

- [ ] **Step 2: Implement repair command**
  Add:
  ```bash
  uv run parallax ops enqueue-projection-dirty-targets --domain all --dry-run
  uv run parallax ops enqueue-projection-dirty-targets --domain all --execute
  ```
  The command only enqueues dirty targets. It does not write read-model rows.

- [ ] **Step 3: Run CLI tests**
  ```bash
  uv run pytest tests/unit/test_ops_projection_dirty_targets.py -q
  ```
  Expected: all tests pass.

## Task 8: Add Architecture Enforcement

**Files:**
- Create: `tests/architecture/test_projection_worker_idle_cost_contract.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`

- [ ] **Step 1: Add architecture test for forbidden runtime discovery**
  The test parses files under `src/parallax/domains/*/runtime/*projection_worker.py` and fails on calls matching:
  - `list_*_for_*_projection`
  - `list_*_missing_*`
  - `list_source_quality_inputs`
  - `page_projection_source_summary`
  Allow only dirty-target repository calls, explicit target-id payload loaders, and manual `app/ops` modules outside runtime. Prefer an allowlist of runtime projection repository calls over a method-name blacklist so broad scans cannot be reintroduced through renamed methods.

- [ ] **Step 2: Add control-plane ownership contract**
  Do not add dirty-target tables to `SINGLE_WRITER_READ_MODELS`; they intentionally have multiple enqueue writers. Add a separate `CONTROL_PLANE_TABLES` architecture contract that allows explicit source writers to enqueue and allows only the owning projection worker to claim/mark.

- [ ] **Step 3: Document the idle-cost contract**
  Update reliability docs to say projection worker no-work paths must be O(due dirty targets) or O(dirty-target table metadata only), and runtime fact/read-model stale scans are forbidden.

- [ ] **Step 4: Run architecture tests**
  ```bash
  uv run pytest \
    tests/architecture/test_projection_worker_idle_cost_contract.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_worker_inventory_contract.py -q
  ```
  Expected: all tests pass.

## Task 9: Focused Integration And Live Verification

**Files:**
- Test: existing integration tests under `tests/integration/domains/news_intel/`
- Test: existing integration tests under `tests/unit/domains/equity_event_intel/`
- Verification: create `docs/superpowers/plans/active/2026-05-24-projection-dirty-target-hard-cut-verification-cn.md`

- [ ] **Step 1: Run focused backend tests**
  ```bash
  uv run pytest \
    tests/unit/domains/equity_event_intel \
    tests/unit/domains/news_intel \
    tests/unit/test_ops_projection_dirty_targets.py \
    tests/architecture/test_projection_worker_idle_cost_contract.py -q
  ```
  Expected: all focused tests pass.

- [ ] **Step 2: Run lint and type checks**
  ```bash
  uv run ruff check .
  uv run mypy \
    src/parallax/domains/equity_event_intel \
    src/parallax/domains/news_intel \
    src/parallax/app/ops \
    src/parallax/app/surfaces/cli \
    src/parallax/app/runtime/repository_session.py
  ```
  Expected: both commands exit 0.

- [ ] **Step 3: Run full completion gate**
  ```bash
  make check-all
  ```
  Expected: exit 0. Paste full output into the verification artefact.

- [ ] **Step 4: Rebuild and start Docker against real config**
  ```bash
  docker compose build app
  docker compose up -d
  curl -fsS http://localhost:8765/readyz | jq '.ok, .workers.equity_event_page_projection, .workers.news_page_projection, .workers.news_source_quality_projection'
  ```
  Expected: app ready, projection workers healthy, notes show dirty-target claim counts.

- [ ] **Step 5: Verify no broad projection scans are repeating**
  ```bash
  docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  select pid, state, left(query, 220) as query
  from pg_stat_activity
	  where query ilike '\''%list_events_for_page_projection%'\''
	     or query ilike '\''%equity_company_events AS events%equity_event_page_rows%'\''
	     or query ilike '\''%list_expected_events_for_calendar_projection%'\''
	     or query ilike '\''%equity_expected_events AS expected%equity_event_calendar_rows%'\''
	     or query ilike '\''%list_items_for_page_projection%'\''
	     or query ilike '\''%news_items AS items%news_page_rows%'\''
	     or query ilike '\''%list_source_quality_inputs%'\''
	     or query ilike '\''%news_fetch_runs%window_items%'\''
	     or query ilike '\''%list_events_missing_story%'\''
	     or query ilike '\''%list_items_missing_story%'\''
	  order by query_start desc;"'
  ```
  Expected: no repeating runtime projection scan query.

## Rollout Order

1. Stop app workers or deploy code with workers disabled for the projection lanes during migration.
2. Apply Alembic revision `20260524_0094`.
3. Run `parallax ops enqueue-projection-dirty-targets --domain all --execute` once against real config.
4. Start app workers with hard-cut code.
5. Watch `/readyz` until dirty queues drain.
6. Confirm `pg_stat_activity` has no repeating broad projection scans.
7. Record worker p99 and DB CPU evidence in verification.

## Rollback

This is a hard cut and does not preserve runtime compatibility code.

- Before merge: rollback is branch-level revert.
- After merge but before migration: revert the PR.
- After migration: do not restore old scan-based runtime code. Pause affected projection workers, apply a forward fix, run the repair command to enqueue missing dirty targets, and keep read APIs serving the last materialized rows.
- The dirty-target tables are control-plane tables and can remain in the database if a forward fix is preferred.

## Acceptance Test Commands

- AC1, AC3:
  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py -q
  ```
- AC2:
  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_equity_projection_dirty_target_repository.py -q
  ```
- AC4, AC5:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q
  ```
- AC6:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py -q
  ```
- AC7:
  ```bash
  uv run pytest \
    tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py::test_unchanged_payload_does_not_advance_computed_at_ms \
    tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_unchanged_payload_does_not_advance_computed_at_ms \
    tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py::test_unchanged_payload_does_not_advance_computed_at_ms -q
  ```
- AC8:
  ```bash
  uv run pytest tests/architecture/test_projection_worker_idle_cost_contract.py -q
  ```
- AC9:
  ```bash
  uv run pytest tests/unit/test_ops_projection_dirty_targets.py -q
  ```
- AC10:
  ```bash
  docker compose build app
  docker compose up -d
  curl -fsS http://localhost:8765/readyz | jq '.ok, .workers.equity_event_page_projection, .workers.news_page_projection, .workers.news_source_quality_projection'
  ```

## Verification

Create `docs/superpowers/plans/active/2026-05-24-projection-dirty-target-hard-cut-verification-cn.md` before claiming completion. It must include:

- full `make check-all` output;
- focused dirty-target test output;
- Docker rebuild/start output;
- `/readyz` projection worker notes;
- `pg_stat_activity` evidence that broad projection scans are absent;
- residual risks and any follow-up specs.
