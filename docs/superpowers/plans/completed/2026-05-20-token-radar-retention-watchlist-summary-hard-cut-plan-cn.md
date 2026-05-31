# Token Radar Retention and Watchlist Summary Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Superseded for Token Radar storage by `docs/superpowers/plans/active/2026-05-23-token-radar-storage-root-fix-cleanup-plan-cn.md`
**Date:** 2026-05-20
**Owning spec:** Inline operator requirement: prune old `token_radar_rows`, restore `handle_summary`, and remove the root DB bottleneck without breaking live business surfaces.
**Worktree:** `.worktrees/token-radar-retention-watchlist-summary-hard-cut/`
**Branch:** `codex/token-radar-retention-watchlist-summary-hard-cut`

**Goal:** Historical plan. The watchlist-summary portion remains historical context; the Token Radar retention/prune portion is no longer the target architecture. The 2026-05-23 hard cut deletes the legacy Radar table and restarts derived Radar storage from zero instead of keeping retention compatibility.

**Architecture:** Keep Kappa/CQRS boundaries: PostgreSQL fact tables remain the business truth; `token_radar_rows`, `watchlist_handle_summaries`, `watchlist_handle_signal_stats`, and `watchlist_handle_signal_events` are rebuildable read/control models with one runtime writer per model. Before pruning historical radar rows, persist first-seen/listed-at metadata in a compact read model keyed by the same identity semantics as runtime rows (`target_type_key`, `identity_id`). Before re-enabling `handle_summary`, move trigger decisions from historical scans to an indexed, event-idempotent stats ledger updated by enrichment writes and bounded backfill.

**Tech Stack:** Python 3.13, PostgreSQL 18, Alembic, psycopg3, FastAPI, Docker Compose, pytest, ruff.

---

## Scope

- In:
  - Add compact `token_radar_target_first_seen` read model so current/public `listed_at_ms` no longer requires unlimited `token_radar_rows` history.
  - Add bounded Token Radar retention service and `ops prune-token-radar` CLI with dry-run, batch delete, coverage-batch plus actual-latest-batch protection, and run audit.
  - Add `watchlist_handle_signal_stats`, mandatory `watchlist_handle_signal_events`, and normalized handle indexing for signal events.
  - Refactor `handle_summary` reconcile and trigger logic to read stats instead of scanning `events` / `social_event_extractions`.
  - Add batch backfill commands for first-seen and watchlist signal stats.
  - Re-enable `handle_summary` only after stats backfill and runtime verification.
  - Update docs/contracts/tests so future changes cannot reintroduce full-table scans on hot paths.
- Out:
  - Deleting canonical fact tables such as `events`, `token_intents`, `token_intent_resolutions`, `market_ticks`, `enriched_events`, or `social_event_extractions`.
  - Changing Token Radar score math, Pulse decision policy, Narrative digest semantics, or public API response shapes.
  - Archiving old radar history to cold storage in this pass; retention is destructive for historical read-model rows after dry-run confirmation, while facts remain intact.

## Current Evidence

- `token_radar_rows` is a rebuildable read model but currently contains about 15-17 million rows in production and has no retention worker.
- `docs/CONTRACTS.md` says `listed_at_ms` is derived from retained `token_radar_rows` history; this blocks naive deletion unless first-seen is persisted elsewhere.
- `TokenRadarRepository._listed_at_by_identity()` scans historical `token_radar_rows` through `idx_token_radar_rows_listed_lookup`.
- The listed-at identity is not strictly `(target_type, target_id)`: current code uses `COALESCE(target_type, '')` and `COALESCE(target_id, intent_id)`, so unresolved/attention/fallback rows must use the same compact key.
- Several hot consumers still read the actual latest batch from `token_radar_rows`, not only `token_radar_projection_coverage`: `TokenRadarRepository.latest_rows()`, `PulseCandidateWorker.scan_triggers_once()`, and `RegistryRepository.active_live_market_targets()`.
- `TokenFactorEvaluationService` settles forward returns from historical radar rows; current CLI horizons are `15m`, `1h`, `6h`, and `24h`, so `7d + grace` is enough for live settlement.
- Retention will intentionally shorten ad-hoc historical radar evaluation to the retained hot horizon unless a future cold archive/rollup is added. Existing `token_score_evaluations` remain facts of prior evaluation runs.
- `handle_summary` is currently disabled in operator config because `handles_missing_summary_jobs()` repeatedly times out.
- The slow query lives in `WatchlistIntelRepository.handles_missing_summary_jobs()` and uses `lower(coalesce(se.author_handle, e.author_handle, ''))`, joins `events`, and runs a correlated `COUNT(*)`.
- The enrichment write path already knows the current signal/non-signal state for an event, so it must update a per-event ledger and aggregate stats in the same unit of work. Aggregate-only counting is not safe because `social_event_extractions` is upserted by `event_id`.

## Safety Invariants

- Do not prune `token_radar_rows` until `token_radar_target_first_seen` is populated and the latest public Token Radar row still has stable `listed_at_ms`.
- Never delete rows referenced by current `token_radar_projection_coverage` batches or by the actual latest `MAX(computed_at_ms)` batch for any `(projection_version, window, scope)`.
- `token_radar_target_first_seen` must use `target_type_key` and `identity_id`, exactly matching `TokenRadarRepository._identity_key()`, not `target_type,target_id`.
- `watchlist_handle_signal_stats.total_signal_count` must be derived through `watchlist_handle_signal_events(event_id)` idempotency; never increment the aggregate directly from a retryable upsert.
- Keep retention deletion batch-limited, ordered by `(computed_at_ms, row_id)`, and committed per batch.
- Keep `handle_summary.enabled=false` in `~/.parallax/workers.yaml` until the stats read model is backfilled and verified.
- Keep all operational commands safe by default: dry-run unless `--execute` is explicitly provided.
- API verification must cover `/readyz`, `/api/token-radar`, `/api/signal-lab/pulse`, `/api/recent`, `/api/news`, and watchlist overview/summary endpoints.

## File Structure

### Schema and Persistence

- Create `src/parallax/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py`
  - Adds `token_radar_target_first_seen`.
  - Adds `token_radar_retention_runs`.
  - Adds `watchlist_handle_signal_stats`.
  - Adds `watchlist_handle_signal_events` as the idempotency ledger behind stats.
  - Adds `social_event_extractions.normalized_handle`.
  - Adds prune and signal lookup indexes.
- Modify `tests/unit/test_postgres_schema.py`
- Modify `tests/integration/test_postgres_schema_runtime.py`

### Token Radar Retention

- Modify `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
  - Read and write first-seen rows.
  - Preserve current `listed_at_ms` behavior through the new read model.
  - Add prune planning and batch deletion helpers.
- Create `src/parallax/domains/token_intel/services/token_radar_retention.py`
  - Owns dry-run, batch execution, latest-batch protection, grace-window calculation, and run audit.
- Modify `src/parallax/platform/config/settings.py`
  - Add worker/ops defaults for retention days and prune batch size.
- Modify `src/parallax/app/surfaces/cli/parser.py`
  - Add `ops backfill-token-radar-first-seen`.
  - Add `ops prune-token-radar`.
- Modify `src/parallax/app/surfaces/cli/commands/ops.py`
  - Wire the new commands.
- Add tests:
  - `tests/unit/domains/token_intel/test_token_radar_first_seen.py`
  - `tests/unit/domains/token_intel/test_token_radar_retention.py`
  - `tests/integration/test_token_radar_retention_postgres.py`

### Watchlist Summary

- Modify `src/parallax/domains/social_enrichment/repositories/social_event_extraction_repository.py`
  - Store `normalized_handle`.
  - Decode `normalized_handle`.
- Modify `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
  - Update watchlist signal stats after a signal extraction is persisted.
  - Enqueue summary jobs from stats-backed trigger logic only.
- Modify `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
  - Add stats read/write/backfill methods.
  - Replace `handles_missing_summary_jobs()` with stats-only SQL.
  - Replace `count_signal_events_total()` with stats-first lookup.
  - Rewrite `signal_events_for_summary()` to filter by `normalized_handle` and only then join event payloads.
- Modify `src/parallax/domains/watchlist_intel/services/handle_summary_service.py`
  - Use stats-backed counts and keep due-reason behavior unchanged.
- Modify `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
  - Reconcile from stats rows only.
- Modify `src/parallax/app/surfaces/cli/parser.py`
  - Add `ops backfill-watchlist-signal-stats`.
- Modify `src/parallax/app/surfaces/cli/commands/ops.py`
  - Wire the stats backfill command.
- Add tests:
  - `tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py`
  - `tests/unit/domains/watchlist_intel/test_handle_summary_reconcile.py`
  - `tests/unit/test_handle_summary_worker.py`

### Docs and Contracts

- Modify `docs/CONTRACTS.md`
  - Explain that `listed_at_ms` now comes from `token_radar_target_first_seen`, not unbounded `token_radar_rows` history.
- Modify `docs/WORKERS.md`
  - Explain Token Radar retention and handle summary stats ownership.
- Modify `docs/RELIABILITY.md`
  - Add safe prune/backfill operational runbook and backout.
- Modify `docs/TECH_DEBT.md`
  - Close or replace the current retention/watchlist scan debt entries with the new owner/plan.

## Task 1: Pre-flight and Production Baseline

**Files:**
- Read: `docs/ARCHITECTURE.md`
- Read: `docs/CONTRACTS.md`
- Read: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Read: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`

- [ ] **Step 1: Create isolated worktree**

  Run:
  ```bash
  git worktree add .worktrees/token-radar-retention-watchlist-summary-hard-cut -b codex/token-radar-retention-watchlist-summary-hard-cut main
  cd .worktrees/token-radar-retention-watchlist-summary-hard-cut
  git branch --show-current
  git status --short
  ```

  Expected:
  - Branch is `codex/token-radar-retention-watchlist-summary-hard-cut`.
  - Worktree status is clean.

- [ ] **Step 2: Confirm live runtime config paths**

  Run:
  ```bash
  uv run parallax config
  ```

  Expected:
  - `config_path` points at `~/.parallax/config.yaml`.
  - `workers_config_path` points at `~/.parallax/workers.yaml`.
  - Do not print secret values.

- [ ] **Step 3: Capture read API and worker baselines**

  Run with a token read from local config but do not print the token:
  ```bash
  TOKEN=$(uv run python -c 'from parallax.platform.config.settings import load_settings; print(load_settings().ws_token or "")')
  curl -fsS http://127.0.0.1:8765/readyz | jq '{ok,reasons,providers:.provider_states,workers:.workers.handle_summary}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=5' | jq '{ok,items:(.data.targets|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/signal-lab/pulse?window=1h&scope=all&limit=5' | jq '{ok,items:(.data.items|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/recent?limit=5&scope=matched' | jq '{ok,items:(.data.items|length)}'
  ```

  Expected:
  - All APIs return `ok=true`.
  - `handle_summary` may be disabled at this point.

- [ ] **Step 4: Capture DB size estimates without full scans**

  Run:
  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -Atc "
  SELECT relname || '|' || reltuples::bigint
  FROM pg_class
  WHERE relname IN ('token_radar_rows','social_event_extractions','events','watchlist_handle_summaries','watchlist_handle_summary_jobs')
  ORDER BY relname;
  "
  ```

  Expected:
  - Uses planner estimates, not `count(*)` on hot tables.

- [ ] **Step 5: Run focused baseline tests**

  Run:
  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/integration/test_postgres_schema_runtime.py \
    tests/unit/test_cli.py \
    tests/unit/test_worker_settings.py \
    -q
  ```

  Expected:
  - Current baseline passes before implementation.

## Task 2: Add Schema for First-Seen, Retention Audit, and Watchlist Stats

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1: Write schema tests first**

  Add assertions that the migration text contains:
  ```sql
  CREATE TABLE IF NOT EXISTS token_radar_target_first_seen
  CREATE TABLE IF NOT EXISTS token_radar_retention_runs
  CREATE TABLE IF NOT EXISTS watchlist_handle_signal_stats
  CREATE TABLE IF NOT EXISTS watchlist_handle_signal_events
  ALTER TABLE social_event_extractions ADD COLUMN IF NOT EXISTS normalized_handle TEXT
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_prune
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_social_event_extractions_signal_normalized_handle_received
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_events_handle_received
  ```

  Run:
  ```bash
  uv run pytest tests/unit/test_postgres_schema.py -q
  ```

  Expected before implementation:
  - Fails because migration does not exist yet.

- [ ] **Step 2: Create migration**

  Add migration with `revision = "20260520_0069"` and `down_revision = "20260520_0068"`.

  Required DDL:
  ```sql
  ALTER TABLE social_event_extractions
    ADD COLUMN IF NOT EXISTS normalized_handle TEXT;

  CREATE TABLE IF NOT EXISTS token_radar_target_first_seen (
    projection_version TEXT NOT NULL,
    "window" TEXT NOT NULL,
    scope TEXT NOT NULL,
    target_type_key TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    first_seen_ms BIGINT NOT NULL,
    last_seen_ms BIGINT NOT NULL,
    first_row_id TEXT,
    latest_row_id TEXT,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    PRIMARY KEY (projection_version, "window", scope, target_type_key, identity_id)
  );

  CREATE TABLE IF NOT EXISTS token_radar_retention_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    cutoff_ms BIGINT NOT NULL,
    batch_size INTEGER NOT NULL,
    max_batches INTEGER,
    rows_planned BIGINT NOT NULL DEFAULT 0,
    rows_deleted BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT,
    started_at_ms BIGINT NOT NULL,
    finished_at_ms BIGINT,
    created_at_ms BIGINT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS watchlist_handle_signal_stats (
    handle TEXT PRIMARY KEY,
    total_signal_count BIGINT NOT NULL DEFAULT 0,
    latest_signal_at_ms BIGINT,
    latest_signal_event_id TEXT,
    first_signal_at_ms BIGINT,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS watchlist_handle_signal_events (
    event_id TEXT PRIMARY KEY,
    handle TEXT NOT NULL,
    received_at_ms BIGINT NOT NULL,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL
  );
  ```

  Required concurrent indexes:
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_prune
    ON token_radar_rows(computed_at_ms ASC, row_id ASC);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_first_seen_updated
    ON token_radar_target_first_seen(updated_at_ms DESC);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_social_event_extractions_signal_normalized_handle_received
    ON social_event_extractions(normalized_handle, received_at_ms DESC, event_id DESC)
    WHERE is_signal_event = TRUE AND normalized_handle IS NOT NULL;

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_stats_latest
    ON watchlist_handle_signal_stats(latest_signal_at_ms DESC);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_events_handle_received
    ON watchlist_handle_signal_events(handle, received_at_ms DESC, event_id DESC);
  ```

- [ ] **Step 3: Validate migration under PostgreSQL**

  Run:
  ```bash
  uv run pytest tests/integration/test_postgres_schema_runtime.py -q
  ```

  Expected:
  - New tables and indexes exist in the runtime schema.

- [ ] **Step 4: Commit schema foundation**

  Run:
  ```bash
  git add src/parallax/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py
  git commit -m "feat: add retention and watchlist stats schema"
  ```

## Task 3: Make Token Radar Listed-At Independent of Unlimited History

**Files:**
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Add: `tests/unit/domains/token_intel/test_token_radar_first_seen.py`
- Modify: `tests/golden/test_token_radar_corpus.py`
- Modify: `tests/unit/test_token_radar_projection.py` if local tests reference listed-at behavior.

- [ ] **Step 1: Add failing tests for first-seen lookup and upsert**

	  Test cases:
	  - New target with no first-seen row gets `listed_at_ms = computed_at_ms`.
	  - Existing target keeps older `first_seen_ms` even after a newer projection.
	  - Unresolved or attention rows with missing `target_id` use `intent_id` as `identity_id`.
	  - Empty or null `target_type` is stored as `target_type_key = ''`, matching `_identity_key()`.
	  - `upsert_first_seen_batch()` updates `last_seen_ms/latest_row_id` but not `first_seen_ms`.
	  - Empty rows do not query or mutate first-seen tables.

  Run:
  ```bash
  uv run pytest tests/unit/domains/token_intel/test_token_radar_first_seen.py -q
  ```

  Expected before implementation:
  - Fails because first-seen methods do not exist.

- [ ] **Step 2: Implement repository methods**

  Add methods:
  ```python
  def first_seen_by_identity(
      self,
      *,
      projection_version: str,
      window: str,
      scope: str,
      rows: list[dict[str, Any]],
  ) -> dict[tuple[str, str], int]:
      ...

  def upsert_first_seen_batch(
      self,
      *,
      projection_version: str,
      window: str,
      scope: str,
      rows: list[dict[str, Any]],
      computed_at_ms: int,
      commit: bool = True,
  ) -> int:
      ...
  ```

	  Required SQL semantics:
	  ```sql
	  INSERT INTO token_radar_target_first_seen(...)
	  VALUES (...)
	  ON CONFLICT(projection_version, "window", scope, target_type_key, identity_id)
	  DO UPDATE SET
	    first_seen_ms = LEAST(token_radar_target_first_seen.first_seen_ms, excluded.first_seen_ms),
	    last_seen_ms = GREATEST(token_radar_target_first_seen.last_seen_ms, excluded.last_seen_ms),
	    latest_row_id = excluded.latest_row_id,
	    updated_at_ms = excluded.updated_at_ms
	  ```

	  Implementation rules:
	  - Identity key must be the existing `_identity_key(row)` result: `(str(row.get("target_type") or ""), str(row.get("target_id") or row.get("intent_id") or ""))`.
	  - `first_seen_by_identity()` reads `token_radar_target_first_seen` by `(projection_version, window, scope, target_type_key, identity_id)`.
	  - For rows missing in the new table, fall back to the current historical `_listed_at_by_identity()` until the backfill is complete.
	  - Do not write first-seen rows for empty `identity_id`.

- [ ] **Step 3: Update `replace_rows()` listed-at flow**

	  Change `replace_rows()` so it:
	  - Reads first-seen rows before inserting new radar rows.
	  - Uses first-seen values for `listed_at_ms`.
	  - Falls back to `computed_at_ms` for brand-new targets.
	  - Upserts first-seen rows in the same transaction after rows are inserted.
	  - Does not require unlimited history once the compact first-seen row exists.

- [ ] **Step 4: Add backfill helper**

  Add method:
  ```python
  def backfill_first_seen_from_history(
      self,
      *,
      batch_size: int,
      after_key: tuple[str, str, str, str, str] | None = None,
      commit: bool = True,
  ) -> dict[str, Any]:
      ...
  ```

	  It should aggregate existing `token_radar_rows` by `(projection_version, window, scope, COALESCE(target_type, ''), COALESCE(target_id, intent_id))` in batches and upsert compact first-seen records. The first implementation may page by identity key rather than by row offset to avoid unstable large offsets.

- [ ] **Step 5: Run focused tests**

  Run:
  ```bash
  uv run pytest \
    tests/unit/domains/token_intel/test_token_radar_first_seen.py \
    tests/golden/test_token_radar_corpus.py \
    -q
  ```

  Expected:
  - Existing public/golden Token Radar rows keep stable `listed_at_ms`.

- [ ] **Step 6: Commit first-seen write path**

  Run:
  ```bash
  git add src/parallax/domains/token_intel/repositories/token_radar_repository.py tests/unit/domains/token_intel/test_token_radar_first_seen.py tests/golden/test_token_radar_corpus.py
  git commit -m "feat: persist token radar first seen metadata"
  ```

## Task 4: Add Safe Token Radar Retention Service and CLI

**Files:**
- Create: `src/parallax/domains/token_intel/services/token_radar_retention.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `src/parallax/platform/config/settings.py`
- Add: `tests/unit/domains/token_intel/test_token_radar_retention.py`
- Add: `tests/integration/test_token_radar_retention_postgres.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/test_settings.py`

- [ ] **Step 1: Add failing tests for retention safety**

	  Test cases:
	  - Dry-run returns planned rows and deletes zero rows.
	  - Execute deletes only rows older than cutoff.
	  - Execute does not delete rows whose `(projection_version, window, scope, computed_at_ms)` is referenced by latest `token_radar_projection_coverage`.
	  - Execute does not delete rows in the actual `MAX(computed_at_ms)` batch for each `(projection_version, window, scope)`, even if coverage is stale, running, failed, or missing.
	  - Execute refuses `retention_days < 2`.
	  - Batch mode deletes at most `batch_size * max_batches`.
	  - Retention audit row is written with `status='dry_run'`, `status='done'`, or `status='failed'`.

  Run:
  ```bash
  uv run pytest tests/unit/domains/token_intel/test_token_radar_retention.py tests/integration/test_token_radar_retention_postgres.py -q
  ```

  Expected before implementation:
  - Fails because service and CLI do not exist.

- [ ] **Step 2: Implement retention repository helpers**

  Add methods:
  ```python
  def plan_prunable_rows(self, *, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
      ...

  def delete_prunable_rows_batch(self, *, cutoff_ms: int, batch_size: int, commit: bool = True) -> int:
      ...

  def insert_retention_run(self, payload: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
      ...

  def finish_retention_run(self, run_id: str, *, status: str, rows_deleted: int, error: str | None, commit: bool = True) -> None:
      ...
  ```

	  Required victim selection shape:
	  ```sql
	  WITH coverage_batches AS (
	    SELECT projection_version, "window", scope, computed_at_ms
	    FROM token_radar_projection_coverage
	    WHERE computed_at_ms IS NOT NULL
	  ),
	  actual_latest_batches AS (
	    SELECT projection_version, "window", scope, MAX(computed_at_ms) AS computed_at_ms
	    FROM token_radar_rows
	    GROUP BY projection_version, "window", scope
	  ),
	  protected_batches AS (
	    SELECT * FROM coverage_batches
	    UNION
	    SELECT * FROM actual_latest_batches
	  ),
	  victims AS (
	    SELECT rows.row_id
	    FROM token_radar_rows rows
	    WHERE rows.computed_at_ms < %(cutoff_ms)s
	      AND NOT EXISTS (
	        SELECT 1
	        FROM protected_batches current
	        WHERE current.projection_version = rows.projection_version
	          AND current."window" = rows."window"
	          AND current.scope = rows.scope
	          AND current.computed_at_ms = rows.computed_at_ms
      )
    ORDER BY rows.computed_at_ms ASC, rows.row_id ASC
    LIMIT %(batch_size)s
  )
  DELETE FROM token_radar_rows rows
  USING victims
  WHERE rows.row_id = victims.row_id
  RETURNING rows.row_id
  ```

- [ ] **Step 3: Implement `TokenRadarRetentionService`**

	  Required behavior:
	  - `dry_run=True` plans without deleting.
	  - `execute=True` deletes in batches.
	  - `retention_days` default is `7`.
	  - `settlement_grace_days` default is `2`.
	  - Effective cutoff is `now_ms - max(retention_days, settlement_grace_days + 1)`.
	  - Refuse execution when `retention_days < settlement_grace_days + 1`.
	  - Return both `protected_coverage_batches` and `protected_actual_latest_batches`.
	  - Returns JSON:
	    ```json
	    {
	      "mode": "dry_run|execute",
      "retention_days": 7,
      "cutoff_ms": 0,
      "batch_size": 10000,
	      "max_batches": 1,
	      "rows_planned": 0,
	      "rows_deleted": 0,
	      "protected_coverage_batches": 0,
	      "protected_actual_latest_batches": 0
	    }
	    ```

- [ ] **Step 4: Add CLI commands**

  Parser:
  ```bash
  uv run parallax ops backfill-token-radar-first-seen --batch-size 5000 --max-batches 10
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --dry-run
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --execute
  ```

  Requirements:
  - `prune-token-radar` defaults to dry-run if neither `--dry-run` nor `--execute` is passed.
  - `--execute` and `--dry-run` are mutually exclusive.
  - `--max-batches` defaults to `1` for operator safety.

- [ ] **Step 5: Run retention tests**

  Run:
  ```bash
  uv run pytest \
    tests/unit/domains/token_intel/test_token_radar_retention.py \
    tests/integration/test_token_radar_retention_postgres.py \
    tests/unit/test_cli.py \
    tests/unit/test_settings.py \
    -q
  ```

- [ ] **Step 6: Commit retention service**

  Run:
  ```bash
  git add src/parallax/domains/token_intel/services/token_radar_retention.py src/parallax/domains/token_intel/repositories/token_radar_repository.py src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py src/parallax/platform/config/settings.py tests/unit/domains/token_intel/test_token_radar_retention.py tests/integration/test_token_radar_retention_postgres.py tests/unit/test_cli.py tests/unit/test_settings.py
  git commit -m "feat: add safe token radar retention"
  ```

## Task 5: Make Watchlist Summary Stats-Driven

**Files:**
- Modify: `src/parallax/domains/social_enrichment/repositories/social_event_extraction_repository.py`
- Modify: `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
- Modify: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Modify: `src/parallax/domains/watchlist_intel/services/handle_summary_service.py`
- Modify: `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Add: `tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py`
- Add: `tests/unit/domains/watchlist_intel/test_handle_summary_reconcile.py`
- Modify: `tests/unit/test_handle_summary_worker.py`

- [ ] **Step 1: Add failing tests for stats update**

	  Test cases:
	  - Upserting a signal extraction inserts one `watchlist_handle_signal_events` row keyed by `event_id` and increments `watchlist_handle_signal_stats.total_signal_count` once.
	  - Re-upserting the same event does not double count.
	  - Re-upserting the same event with a different normalized handle moves the ledger row, decrements the old handle, and increments the new handle.
	  - Re-upserting the same event as non-signal removes the ledger row and decrements/recomputes the old handle stats.
	  - Latest signal fields update only when the new event is newer.
	  - Non-signal extractions do not increment stats.
	  - Null/empty handles are ignored.

  Run:
  ```bash
  uv run pytest tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py -q
  ```

- [ ] **Step 2: Store `normalized_handle` in social extractions**

  Update `SocialEventExtractionRepository.upsert_extraction()`:
  - Normalize `author_handle` once with `strip().lstrip("@").lower()`.
  - Insert/update both `author_handle` and `normalized_handle`.
  - Prefer `normalized_handle` in `recent()` handle filters.

- [ ] **Step 3: Add stats methods to `WatchlistIntelRepository`**

	  Add:
	  ```python
	  def record_signal_event_state(
	      self,
	      *,
	      handle: str,
	      event_id: str,
	      received_at_ms: int,
      is_signal_event: bool,
      commit: bool = True,
	  ) -> bool:
	      ...

  def signal_stats_for_handle(self, handle: str) -> dict[str, Any] | None:
      ...

	  def backfill_signal_stats_batch(
      self,
      *,
      after_received_at_ms: int | None,
      after_event_id: str | None,
      batch_size: int,
      commit: bool = True,
	  ) -> dict[str, Any]:
	      ...
	  ```

	  Required ledger semantics:
	  - `watchlist_handle_signal_events.event_id` is the idempotency key because `social_event_extractions.event_id` is unique.
	  - If `is_signal_event=True` and no ledger row exists, insert ledger row and increment the handle aggregate.
	  - If `is_signal_event=True` and a ledger row already exists for the same handle, update `received_at_ms` only when needed and recompute latest from the ledger if the timestamp changes.
	  - If `is_signal_event=True` and a ledger row exists for a different handle, move the ledger row, decrement/recompute the old handle, and increment/recompute the new handle.
	  - If `is_signal_event=False`, delete any existing ledger row for the event and decrement/recompute the old handle.
	  - Aggregate `latest_signal_at_ms/latest_signal_event_id/first_signal_at_ms` must be recomputed from `watchlist_handle_signal_events` for any handle whose ledger membership changed.

- [ ] **Step 4: Update enrichment write path**

	  In `EnrichmentWorker._complete_job_sync()`:
	  - Persist social extraction.
	  - Call `repos.watchlist_intel.record_signal_event_state(...)` for every extraction with a non-empty handle, passing the current `result.is_signal_event` value.
	  - Call `WatchlistHandleSummaryService.enqueue_handle_summary_if_due(...)` after stats update.
	  - Keep all three writes in the existing unit of work.

- [ ] **Step 5: Rewrite summary trigger counts**

  Update `WatchlistHandleSummaryService.enqueue_handle_summary_if_due()` and `summary_inputs()` so:
  - `signal_count` comes from `watchlist_handle_signal_stats.total_signal_count`.
  - It never runs `COUNT(*)` against historical `social_event_extractions`.
  - Empty stats returns count `0`.

- [ ] **Step 6: Rewrite `handles_missing_summary_jobs()`**

  Replace the current historical query with stats-only SQL:
  ```sql
  SELECT stats.handle,
         stats.total_signal_count AS signal_count,
         stats.latest_signal_at_ms
  FROM watchlist_handle_signal_stats stats
  LEFT JOIN watchlist_handle_summaries summary
    ON summary.handle = stats.handle
  LEFT JOIN watchlist_handle_summary_jobs job
    ON job.handle = stats.handle
   AND job.status IN ('pending', 'running', 'failed')
  WHERE stats.handle = ANY(%s)
    AND stats.latest_signal_at_ms >= %s
    AND job.handle IS NULL
    AND (
      summary.handle IS NULL
      OR summary.signal_count_at_generation < stats.total_signal_count
    )
  ORDER BY stats.latest_signal_at_ms DESC
  LIMIT %s
  ```

  Add an architecture-style test that the SQL text no longer contains `lower(coalesce(` or a correlated `SELECT COUNT(*)`.

- [ ] **Step 7: Rewrite summary input event lookup**

  `signal_events_for_summary()` should:
  - Filter `social_event_extractions` by `normalized_handle`, `is_signal_event`, and `received_at_ms`.
  - Order by `received_at_ms DESC, event_id DESC`.
  - Limit before joining wider event payload columns.
  - Join `events` only for selected event ids/text fields.

- [ ] **Step 8: Run watchlist tests**

  Run:
  ```bash
  uv run pytest \
    tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py \
    tests/unit/domains/watchlist_intel/test_handle_summary_reconcile.py \
    tests/unit/test_handle_summary_worker.py \
    -q
  ```

- [ ] **Step 9: Commit stats-driven watchlist summary**

  Run:
  ```bash
  git add src/parallax/domains/social_enrichment/repositories/social_event_extraction_repository.py src/parallax/domains/social_enrichment/runtime/enrichment_worker.py src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py src/parallax/domains/watchlist_intel/services/handle_summary_service.py src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py tests/unit/domains/watchlist_intel/test_handle_summary_reconcile.py tests/unit/test_handle_summary_worker.py
  git commit -m "fix: make watchlist summaries stats driven"
  ```

## Task 6: Add Backfill Commands for Safe Production Cutover

**Files:**
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Add: `tests/unit/test_ops_backfill_commands.py`

- [ ] **Step 1: Add CLI contract tests**

  Required commands:
  ```bash
  uv run parallax ops backfill-token-radar-first-seen --batch-size 5000 --max-batches 1
  uv run parallax ops backfill-watchlist-signal-stats --batch-size 5000 --max-batches 1
  ```

  Required JSON fields:
  ```json
  {
    "ok": true,
    "data": {
      "processed": 0,
      "upserted": 0,
      "has_more": false,
      "last_cursor": null
    }
  }
  ```

- [ ] **Step 2: Implement `backfill-token-radar-first-seen`**

  Requirements:
  - Runs in batches.
  - Uses stable identity cursor.
  - Does not hold one transaction across all history.
  - Returns progress for repeatable operator execution.

- [ ] **Step 3: Implement `backfill-watchlist-signal-stats`**

  Requirements:
  - Backfills `normalized_handle` for existing rows using `social_event_extractions.author_handle` first.
  - Only joins `events` for rows where `normalized_handle IS NULL`.
  - Upserts idempotency rows and aggregate stats.
  - Supports `--dry-run`.

- [ ] **Step 4: Run CLI tests**

  Run:
  ```bash
  uv run pytest tests/unit/test_ops_backfill_commands.py tests/unit/test_cli.py -q
  ```

- [ ] **Step 5: Commit backfill commands**

  Run:
  ```bash
  git add src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py src/parallax/domains/token_intel/repositories/token_radar_repository.py tests/unit/test_ops_backfill_commands.py tests/unit/test_cli.py
  git commit -m "feat: add bounded retention backfill commands"
  ```

## Task 7: Update Runtime Config Defaults and Docs

**Files:**
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/TECH_DEBT.md`
- Modify: `tests/unit/test_worker_settings.py`
- Modify: `tests/unit/test_settings.py`

- [ ] **Step 1: Add settings defaults**

  Add defaults:
  ```yaml
  token_radar_projection:
    retention_days: 7
    retention_batch_size: 10000
    retention_settlement_grace_days: 2
  handle_summary:
    enabled: true
    interval_seconds: 30.0
    reconcile_limit: 20
    statement_timeout_seconds: 10.0
    window_days: 3
  ```

  Keep operator-owned `~/.parallax/workers.yaml` unchanged during code implementation; change it only during rollout after verification.

- [ ] **Step 2: Update docs**

  `docs/CONTRACTS.md` must say:
  - `listed_at_ms` is served from compact first-seen read model.
  - `token_radar_rows` history is retained for configured hot settlement window only.

  `docs/WORKERS.md` must say:
  - `token_radar_projection` owns first-seen writes.
  - `ops prune-token-radar` is an operator maintenance writer, not an HTTP/API side effect.
  - `handle_summary` reads `watchlist_handle_signal_stats`.

  `docs/RELIABILITY.md` must include operator commands:
  ```bash
  uv run parallax ops backfill-token-radar-first-seen --batch-size 5000 --max-batches 20
  uv run parallax ops backfill-watchlist-signal-stats --batch-size 5000 --max-batches 20
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --dry-run
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --execute
  ```

- [ ] **Step 3: Run docs/settings tests**

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

- [ ] **Step 4: Commit docs and config defaults**

  Run:
  ```bash
  git add src/parallax/platform/config/settings.py docs/CONTRACTS.md docs/WORKERS.md docs/RELIABILITY.md docs/TECH_DEBT.md tests/unit/test_worker_settings.py tests/unit/test_settings.py
  git commit -m "docs: document bounded radar and watchlist summary ops"
  ```

## Task 8: Full Verification Before Production Rollout

**Files:**
- No production files; verification only.

- [ ] **Step 1: Run focused backend suite**

  Run:
  ```bash
  uv run pytest \
    tests/unit/domains/token_intel/test_token_radar_first_seen.py \
    tests/unit/domains/token_intel/test_token_radar_retention.py \
    tests/integration/test_token_radar_retention_postgres.py \
    tests/unit/domains/watchlist_intel/test_watchlist_signal_stats.py \
    tests/unit/domains/watchlist_intel/test_handle_summary_reconcile.py \
    tests/unit/test_handle_summary_worker.py \
    tests/unit/test_cli.py \
    tests/unit/test_settings.py \
    -q
  ```

- [ ] **Step 2: Run architecture and integration guard tests**

  Run:
  ```bash
  uv run pytest \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_worker_inventory_contract.py \
    tests/integration/test_postgres_schema_runtime.py \
    tests/integration/test_worker_missed_wake_recovery.py \
    -q
  ```

- [ ] **Step 3: Run lint and diff checks**

  Run:
  ```bash
  uv run ruff check src/parallax tests
  git diff --check
  ```

- [ ] **Step 4: Build Docker from the feature branch**

  Run:
  ```bash
  docker compose build app migrate
  ```

  Expected:
  - Build succeeds without changing runtime database state.

## Task 9: Production Rollout Without Business Interruption

**Files:**
- Operator-owned: `~/.parallax/workers.yaml`
- No repository code edits in this task after merge.

- [ ] **Step 1: Merge to main only after tests pass**

  Run:
  ```bash
  git checkout main
  git merge --no-ff codex/token-radar-retention-watchlist-summary-hard-cut -m "merge: token radar retention and watchlist summary hard cut"
  ```

- [ ] **Step 2: Rebuild and migrate**

  Run:
  ```bash
  docker compose up -d --build
  docker compose ps
  curl -fsS http://127.0.0.1:8765/readyz | jq '{ok,reasons,db:.db,providers:.provider_states}'
  ```

  Expected:
  - `migrate` exits successfully.
  - `app` and `postgres` are healthy.
  - GMGN and OKX WS providers stream or subscribe normally.

- [ ] **Step 3: Backfill compact models in bounded batches**

  Run repeatedly until `has_more=false`:
  ```bash
  uv run parallax ops backfill-token-radar-first-seen --batch-size 5000 --max-batches 20
  uv run parallax ops backfill-watchlist-signal-stats --batch-size 5000 --max-batches 20
  ```

  Expected:
  - Each run commits bounded work.
  - API health remains green between runs.

- [ ] **Step 4: Dry-run retention**

  Run:
  ```bash
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --dry-run
  ```

  Expected:
  - Reports planned rows.
  - Deletes zero rows.
  - Reports protected current batches.

- [ ] **Step 5: Execute one prune batch**

  Run:
  ```bash
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 1 --execute
  ```

  Expected:
  - Deletes at most 10,000 rows.
  - `/api/token-radar` still returns `ok=true`.
  - `listed_at_ms` remains present for current rows.

- [ ] **Step 6: Gradually prune remaining old rows**

  Run repeated one-batch commands during low-traffic windows:
  ```bash
  uv run parallax ops prune-token-radar --retention-days 7 --batch-size 10000 --max-batches 5 --execute
  ```

  Stop if:
  - `/readyz` returns `ok=false`.
  - Postgres CPU stays saturated after a batch completes.
  - API latency regresses materially.
  - Logs show lock waits or statement timeouts from retention.

- [ ] **Step 7: Re-enable `handle_summary` after stats verification**

  Edit `~/.parallax/workers.yaml`:
  ```yaml
  handle_summary:
    enabled: true
    interval_seconds: 30.0
    statement_timeout_seconds: 10.0
    reconcile_limit: 20
    window_days: 3
  ```

  Restart app:
  ```bash
  docker compose restart app
  sleep 60
  curl -fsS http://127.0.0.1:8765/readyz | jq '{ok,reasons,handle_summary:.workers.handle_summary}'
  docker compose logs --since=2m app | rg -i "watchlist handle summary reconcile failed|statement timeout|ERROR|Traceback" || true
  ```

  Expected:
  - `handle_summary.enabled=true`.
  - No reconcile statement timeout.
  - Worker result is either `processed`, `skipped`, or agent backpressure, not DB timeout.

- [ ] **Step 8: Verify business surfaces**

  Run:
  ```bash
  TOKEN=$(uv run python -c 'from parallax.platform.config.settings import load_settings; print(load_settings().ws_token or "")')
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=5' | jq '{ok,items:(.data.targets|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/signal-lab/pulse?window=1h&scope=all&limit=5' | jq '{ok,items:(.data.items|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/recent?limit=5&scope=matched' | jq '{ok,items:(.data.items|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/news?limit=5' | jq '{ok,items:(.data.items|length)}'
  curl -fsS -H "Authorization: Bearer ${TOKEN}" 'http://127.0.0.1:8765/api/watchlist/handles/overview' | jq '{ok,items:(.data.items|length)}'
  ```

  Expected:
  - All return `ok=true`.
  - Token Radar latency should remain in the same order as pre-rollout baseline.

## Task 10: Backout and Recovery

**Files:**
- Operator-owned: `~/.parallax/workers.yaml`
- Runtime commands only.

- [ ] **Step 1: Back out handle summary if needed**

  If statement timeouts or DB pressure return, set:
  ```yaml
  handle_summary:
    enabled: false
  ```

  Then:
  ```bash
  docker compose restart app
  ```

  Expected:
  - Main ingest/Token Radar/Pulse paths continue running.

- [ ] **Step 2: Stop retention pruning immediately if needed**

  Retention is operator-triggered, not a continuously running worker. Stop by not invoking `ops prune-token-radar --execute`.

- [ ] **Step 3: Rebuild current Token Radar if current rows are accidentally damaged**

  Run for each public window/scope needed:
  ```bash
  uv run parallax ops rebuild-token-radar --window 1h --scope all --limit 200
  uv run parallax ops rebuild-token-radar --window 1h --scope matched --limit 200
  uv run parallax ops rebuild-token-radar --window 4h --scope all --limit 200
  uv run parallax ops rebuild-token-radar --window 4h --scope matched --limit 200
  ```

  Expected:
  - Current read surfaces recover from facts.
  - Pruned historical batches are not required for current API function.

- [ ] **Step 4: Rebuild compact first-seen/stats models if needed**

  Run:
  ```bash
  uv run parallax ops backfill-token-radar-first-seen --batch-size 5000 --max-batches 20
  uv run parallax ops backfill-watchlist-signal-stats --batch-size 5000 --max-batches 20
  ```

## Acceptance Criteria

- [ ] `token_radar_target_first_seen` is populated and current `/api/token-radar` rows keep `listed_at_ms` after pruning old `token_radar_rows`.
- [ ] `ops prune-token-radar --dry-run` reports candidates without deleting.
- [ ] `ops prune-token-radar --execute` deletes old rows in bounded batches and never deletes current coverage batches or actual latest batches.
- [ ] `handle_summary` can be re-enabled without `watchlist handle summary reconcile failed: statement timeout`.
- [ ] `WatchlistIntelRepository.handles_missing_summary_jobs()` no longer scans `events` or uses `lower(coalesce(...))`.
- [ ] `social_event_extractions` writes `normalized_handle` for new rows.
- [ ] Watchlist signal counts are served from `watchlist_handle_signal_stats` and are idempotently maintained through `watchlist_handle_signal_events.event_id`.
- [ ] `/readyz`, Token Radar, Pulse, Recent, News, and watchlist overview remain healthy after Docker rebuild and runtime rollout.
- [ ] Tests, ruff, and `git diff --check` pass.

## Implementation Notes

- Prefer compact read models over compatibility fallbacks. Once stats are backfilled, do not keep a runtime fallback that silently scans historical `events`.
- Keep CLI ops commands idempotent and restartable.
- Keep prune batch size conservative in production first rollout: start with `10000` rows and one batch.
- Do not run `count(*)` on `token_radar_rows` in production validation; use planner estimates, dry-run plans, and indexed latest/current queries.
- Do not re-enable `handle_summary` before stats backfill completes.
