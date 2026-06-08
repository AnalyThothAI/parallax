# Spec - Macro Freshness Worker + Page Root Fix

Status: In Progress
Date: 2026-05-31
Owner: Qinghuan / Codex
Worktree: `.worktrees/macro-freshness-root-fix`
Branch: `codex/macro-freshness-root-fix`

## One-Line Goal

Macro must recover current facts first, keep overlap sync windows idempotent, and make stale macro data obvious on the page instead of letting a January snapshot look like an actively updated desk page.

## Background

Macro is a Kappa/CQRS slice: `macro_observations` are business facts, `macro_sync_windows` drive provider ingestion, and `macro_view_projection` rebuilds serving views from those facts. The macro sync worker is the only writer for the sync queue and macro facts.

Current code paths:

- `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py:24` reads `macro_observations` max `observed_at` and enqueues missing gap windows.
- `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py:71` always enqueues a steady overlap window.
- `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py:107` includes the interval bucket in `steady_overlap:<bucket_ms>`, so the same date window receives a new sync identity every interval.
- `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:244` dedupes only on `(source_name, bundle_name, window_start, window_end, trigger_reason)`, which means bucketed steady overlap windows do not coalesce.
- `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:309` claims due work by `priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id ASC`; it does not prefer the freshest `window_end`.
- `src/parallax/domains/macro_intel/runtime/macro_sync_worker.py:34` enqueues due windows and runs one claimed window per `run_once`.
- `web/src/features/macro/MacroWorkbenchRoute.tsx:75` renders the module shell with generic status items, but no first-screen stale-data callout.
- `web/src/features/macro/ui/shell/MacroShell.tsx:24` has one header/content slot and can host a route-level stale banner without recomputing macro scores.

Runtime evidence gathered on 2026-05-31:

- Host CLI config reports `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml`; the live container reports `/root/.parallax/config.yaml` and `/root/.parallax/workers.yaml`. Both point at the same Postgres state.
- `macro_sync.enabled=true`, `macro_view_projection.enabled=true`, and the Ops page shows both workers running in the service process.
- `cex_oi_radar_board.enabled=false`, so the crypto derivatives board cannot match TimSun's CEX forward radar until operator config enables that worker.
- `uv run parallax macro status` and the live container status both show `facts_max_observed_at=2026-01-16`, latest snapshot `asof_date=2026-01-16`, `status=stale`, and `sync_queue.open_count=34 / due_count=34`.
- `projection_behind_facts=false`, so the projection worker is not the freshness bottleneck. The facts are stale.
- `macro_sync_windows` has successful recent runs and no provider failure cluster, but open windows include 34 pending/due rows with current gaps still pending. Many duplicate `steady_overlap:*` windows cover `2026-05-24` through `2026-05-31` with different trigger reasons.

## Problem

The operator sees a macro page that is months behind TimSun and reads it as "worker did not run." The deeper problem is that the worker is running but the queue lets freshness-critical windows wait behind historical/randomly ordered backlog, and repeated steady-overlap identities keep adding work. The page then displays stale macro facts as ordinary module content, so the product makes the failure harder to notice and debug.

## First Principles

- Material facts are the only business truth. A page fix must not fabricate macro state from charts, labels, or external comparison pages.
- Derived read models are rebuildable and may be stale independently, so diagnosis must separate fact freshness from projection lag.
- Sync windows are control-plane work items. Their identity must be stable enough to coalesce unchanged work, and their claim order must reflect product freshness before historical completeness.

## Goals

- G1. Current gap windows ending closest to `now` are claimed before older historical gap windows when priorities are otherwise equal.
- G2. The steady overlap window for a given source, bundle, date range, and reason is stable across worker interval buckets, so repeated worker ticks coalesce instead of creating a new queue row.
- G3. Explicit operator sync uses a stable semantic reason (`operator_sync`) and relies on enqueue reactivation, not timestamp identities.
- G4. Existing pending/retryable `steady_overlap:<bucket>` queue rows are removed by migration rather than kept alive by runtime compatibility code.
- G5. A single macro worker cycle can drain a small bounded number of due windows when backlog exists, using the existing `batch_size` setting capped at 5 provider windows per cycle and without hiding provider failures.
- G6. Macro module pages show a first-screen stale-data alert when the backend payload reports stale or partial data with stale/latest gaps, while keeping all scoring and labels backend-owned.
- G7. Tests cover the queue ordering, overlap identity, operator identity, worker multi-claim behavior, migration cleanup, and page stale alert.

## Non-goals

- This work does not add ETF, CFTC, GEX, options, or TimSun-specific data products.
- This work does not enable `cex_oi_radar_board`; that is operator runtime config, not a code default change.
- This work does not rewrite the macro module catalog or invent missing macro facts in the frontend.
- This work does not mutate live production DB rows outside migrations and normal worker execution.

## Target Architecture

After this change, macro sync has three recovery properties:

- enqueue remains cheap and idempotent for steady overlap;
- claim order is freshness-aware, so the newest gap window repairs the serving page first;
- worker `batch_size` bounds how many windows a cycle can run, preserving provider pressure limits while preventing a 15-minute interval from becoming the minimum unit of backlog recovery.

The frontend keeps rendering `macro_module_view_v3` directly, but the shell receives a `freshnessAlert` derived from existing backend payload fields. It gives the operator an immediate explanation: data is stale, the as-of date is old, and the page is waiting for macro sync facts rather than projection.

## Conceptual Data Flow

```text
macro_sync_windows -> MacroSyncWorker -> macrodata-cli -> macro_observations
        |                                                   |
        | freshness-aware claim + bounded drain              v
        +------------------------------------------> macro_view_projection -> /api/macro/modules -> MacroShell stale alert
```

Changed arrows:

- `macro_sync_windows -> MacroSyncWorker`: claim order prefers latest `window_end` within priority, and each cycle can process more than one window up to `batch_size`.
- `MacroShell stale alert`: the page surfaces backend currentness/data-health signals without deriving any new market read.

## Core Models

- Sync window identity: `source_name`, `bundle_name`, `window_start`, `window_end`, `trigger_reason`. `trigger_reason` for steady overlap is a semantic reason, not a time bucket.
- Re-claimable semantic reasons: `steady_overlap` and `operator_sync` may reactivate terminal sync-window rows in `enqueue_macro_sync_window`; `gap` and `bootstrap` terminal rows remain terminal.
- Freshness alert: a view-only shell model with `title`, `detail`, and `items`. It is derived from `snapshot.status`, `snapshot.asof_*`, and `data_health` gap labels/codes.

## Interface Contracts

- No HTTP or WebSocket schema change is required.
- The macro worker continues using `workers.macro_sync.batch_size`. For this worker it now means max claimed provider windows per run cycle, bounded to at least 1 and capped at 5.
- `parallax macro sync` still runs an explicit window, but it no longer mints timestamp-based sync-window identities.
- Existing CLI `parallax macro status` remains the diagnostic source for fact/projection/queue state.

## Acceptance Criteria

- AC1. WHEN multiple due gap windows have the same priority THEN `claim_macro_sync_window` SHALL prefer the row with the newest `window_end` before older windows.
- AC2. WHEN `ensure_due_macro_sync_windows` runs multiple times inside different interval buckets for the same steady date range THEN it SHALL use the same `steady_overlap` trigger reason.
- AC3. WHEN `parallax macro sync` enqueues the same explicit date window repeatedly THEN it SHALL use the same `operator_sync` trigger reason and rely on queue reactivation.
- AC4. WHEN migration `20260531_0136` runs THEN pending/retryable `steady_overlap:<bucket>` rows SHALL be deleted and the due index SHALL include `window_end DESC`.
- AC5. WHEN `MacroSyncWorker` has `batch_size=3` and three claimable windows return success THEN one `run_once_sync` SHALL perform three provider calls and report three processed windows.
- AC6. WHEN a module payload is stale or has a `stale_latest:*` data gap THEN the macro shell SHALL render a visible `宏观数据滞后` status region before module content.
- AC7. WHEN a module payload is fresh/ok THEN the stale alert SHALL not render.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Provider pressure increases if `batch_size` is very high | Medium | Bound the worker loop by `batch_size` and cap it at 5; existing configs can lower it without code changes. |
| Historical backfill takes longer because current windows win first | Low | This is intentional product priority; older windows remain due and will drain after freshness recovers. |
| Existing duplicate `steady_overlap:*` rows remain in the DB | Low | Migration deletes pending/retryable bucketed overlap rows; runtime no longer creates bucketed reasons. |
| UI alert repeats information from data-health panels | Low | First-screen alert is intentionally operational; detailed data-health remains in module content. |

## Evolution Path

The next expansion is an Ops-facing macro freshness card that joins worker status, sync queue depth, latest run, facts max observed date, and projection lag in one place. That should read from existing status endpoints rather than pushing worker diagnostics into every module payload.

## Alternatives Considered

- Run explicit CLI sync for `2026-05-21..2026-05-31` only. Rejected because it repairs today's DB once but leaves queue ordering and duplicate overlap identities broken.
- Add a new "freshness" table or worker. Rejected because the current sync control plane already owns the lifecycle; the failure is ordering/idempotency, not missing ownership.
- Patch the frontend to hide stale dates. Rejected because the page must surface data truth, not mask it.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve backend-owned macro facts, render stale status when backend says stale, and process newest due sync windows first. |
| Ask first | Enabling paid/third-party workers such as CEX OI radar, or running destructive queue cleanup against live DB. |
| Never | Fabricate macro data in the frontend, print secrets from runtime configs, or reset operator-owned runtime files. |
