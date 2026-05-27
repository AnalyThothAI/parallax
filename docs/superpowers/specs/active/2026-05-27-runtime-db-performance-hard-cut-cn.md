# Spec - Runtime DB Performance Hard Cut

**Status**: Draft
**Date**: 2026-05-27
**Owner**: Codex with Qinghuan
**Priority**: P0 Token Radar correctness, P1 Token Radar cache lifecycle, P2 Macro projection IO
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/superpowers/specs/active/2026-05-27-token-radar-kiss-current-row-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-27-macro-sync-worker-hard-cut-cn.md`

## Background

Live diagnostics after the Token Radar refactor showed that the realtime path is
mostly healthy: container health is good, migrations are current, events and
market ticks are flowing with second-level freshness, Token Radar dirty targets
clear, and unchanged current-row publication no longer writes rows. The
remaining issues are narrower and should be handled as one hard-cut performance
spec rather than three separate feature specs.

Token Radar has one serving read model and two private caches. Architecture says
`token_radar_current_rows` plus `token_radar_publication_state` are the online
serving surface, while `token_radar_target_features` is projection-private and
`token_radar_rank_source_events` is lazy evidence/detail
(`docs/ARCHITECTURE.md:106`). `token_radar_projection` is the single writer for
those tables (`src/gmgn_twitter_intel/app/runtime/worker_manifest.py:241`).

The P0 bug is at the rank-publication boundary. `_project_group()` correctly
uses only rows inside the scoring window and returns `None` when no window rows
exist (`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:1068`).
But current publication ranks every cached feature for a window/scope:
`_rank_current_rows()` calls `list_rank_inputs_for_rank_set()` without `now_ms`
or a cutoff (`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:440`),
and the repository query filters only by projection version, window, and scope
(`src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:565`).
Those old features become current rows because current-row payloads copy
`latest_event_received_at_ms` into `source_max_received_at_ms`
(`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:1716`).
Live checks showed `5m/all` publishing many rows outside the five-minute window
while the API still reported publication status `fresh`.

The P1 cache issue is lifecycle, not serving correctness. P0 can make stale
features ineligible, but expired rows can still accumulate in
`token_radar_target_features` and `token_radar_rank_source_events`. The existing
rank-source cleanup only deletes stale edges for requested targets inside the
current analysis window
(`src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py:775`).
It does not bound old short-window cache. During subagent analysis, an attempted
read-only prune plan accidentally executed a `DELETE` through
`EXPLAIN ANALYZE`, removing `5m/all` projection-private cache older than
`3 * 5m`: 12,121 `token_radar_rank_source_events` rows and 1,170
`token_radar_target_features` rows. It did not touch `token_radar_current_rows`
or `token_radar_publication_state`.

The P2 database bottleneck is Macro, not Token Radar. `MacroViewProjectionWorker`
runs `refresh_observation_series_rows()` every cycle
(`src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py:33`).
That method creates a timestamp/UUID generation on every run
(`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:590`,
`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:1022`)
and inserts the same selected series into `macro_observation_series_rows` with a
primary key that includes `generation_id`
(`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:642`,
`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:679`).
Cleanup deletes only 10,000 rows per run from superseded generations
(`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:772`).
Live DB evidence showed tens of millions of hidden generation rows and roughly
100GB-class storage across heap and indexes, while the active pointer had only
115 rows.

## Problem

The realtime chain is no longer broadly overloaded, but it still has three
hard-cut performance defects: Token Radar can publish window-expired rows as
fresh, Token Radar private caches do not have a bounded lifecycle, and Macro
projection rewrites duplicated generations until it becomes the dominant
PostgreSQL IO and storage bottleneck.

## First Principles

1. PostgreSQL facts are business truth; derived read models and private caches
   must be rebuildable.
2. Online current rows must be honest. A row outside its advertised window is
   not degraded current data; it is not current.
3. Cache deletion belongs to the projection owner, not API/CLI/repair readers.
4. Unchanged source facts must not rewrite large read models.
5. This is a hard cut: no compatibility reader, no legacy fallback, no old
   timestamp/UUID generation branch.

## Goals

- G1. Eliminate stale Token Radar current rows for every published
  `(projection_version, window, scope)`.
- G2. Bound Token Radar projection-private cache so rank input and lazy evidence
  do not grow without retention.
- G3. Stop Macro from duplicating projected observation rows on unchanged steady
  runs.
- G4. Reclaim or replace existing Macro 100GB-class projection bloat through a
  planned migration/table-swap path.
- G5. Preserve realtime health: no broad fact catch-up in Token Radar hot paths,
  no provider calls in API routes, and no direct TTL deletes from current rows.

## Non-goals

- N1. This work does not change Token Radar scoring, factor weights, market
  provider coverage, or UI presentation.
- N2. This work does not change Macro fact ingestion or macro scoring.
- N3. This work does not build historical leaderboard or macro-generation audit
  products.
- N4. This work does not keep compatibility code for stale Token Radar readers
  or old Macro physical generations.
- N5. This work does not prune material facts such as `events`,
  `token_intents`, `market_ticks`, or `macro_observations`.

## Target Architecture

### P0 - Token Radar Window Freshness

Current publication computes a window cutoff from publication time and window
size. Rank input retrieval only returns `token_radar_target_features` rows whose
`latest_event_received_at_ms` is inside that window. Ranking, generation hashing,
current-row replacement, and downstream dirty-target enqueueing operate only on
eligible rows.

If no eligible rows exist, the system publishes a successful empty generation.
It never keeps old rows just to avoid an empty leaderboard.

### P1 - Token Radar Cache Retention

`TokenRadarProjection.refresh_rank_set()` owns private-cache lifecycle for the
same `(projection_version, window, scope)` it is about to publish. It computes a
retention cutoff, defaulting to `computed_at_ms - 3 * WINDOW_MS[window]`, and
prunes:

- `token_radar_target_features.latest_event_received_at_ms < retention_cutoff`
- `token_radar_rank_source_events.event_received_at_ms < retention_cutoff`

Pruning does not touch `token_radar_current_rows`,
`token_radar_publication_state`, or `token_radar_target_first_seen`. Current rows
can shrink only through `publish_current_generation()`.

### P2 - Macro Projection IO

Macro projected series becomes current-only or content-stable. Before rewriting
series rows, the repository computes a deterministic source signature over the
selected source facts, projection version, lookback, and limit. If the signature
is unchanged, the worker returns `unchanged` and writes zero series rows.

If the signature changed, the repository stages selected rows, validates the
staged set, replaces the current projection rows in one transaction, and updates
a compact publication state. Runtime no longer writes or cleans superseded
timestamp/UUID physical generations. Existing bloat is removed by a hard-cut
migration or table swap, not by relying on steady-state batch deletes.

## Conceptual Data Flow

```text
Token facts/private cache
  -> P0 window-eligible rank inputs
  -> P1 bounded cache lifecycle
  -> current Token Radar generation
  -> API / CLI / Pulse / notifications

Macro facts
  -> source signature
  -> unchanged skip OR staged compact replacement
  -> current macro series rows
  -> macro snapshot
  -> API / web
```

## Acceptance Criteria

- AC1. WHEN Token Radar publishes a current generation, THEN every current row
  SHALL have `source_max_received_at_ms >= published_at_ms - WINDOW_MS[window]`.
- AC2. WHEN cached Token Radar features are older than the requested window,
  THEN the next due publication SHALL exclude them even if no dirty target was
  claimed.
- AC3. WHEN all Token Radar rank inputs are outside the current window, THEN the
  system SHALL publish a `ready` empty generation rather than retaining old rows.
- AC4. WHEN Token Radar cache retention runs, THEN it SHALL prune only
  projection-private cache for the matching projection/window/scope and SHALL
  NOT directly delete current rows, publication state, first-seen rows, or facts.
- AC5. WHEN Token Radar windows have refreshed after rollout, THEN diagnostics
  SHALL show zero stale current rows and cache rows older than retention trending
  to zero.
- AC6. WHEN Macro projection runs twice with unchanged selected facts, THEN the
  second run SHALL write zero `macro_observation_series_rows`.
- AC7. WHEN Macro selected facts change, THEN projection SHALL stage and replace
  the compact current series without creating a timestamp/UUID physical
  generation.
- AC8. WHEN Macro storage cleanup is complete, THEN
  `macro_observation_series_rows` SHALL be bounded by active concept count and
  `limit_per_series`, not by worker run count.
- AC9. WHEN implementation is reviewed, THEN no compatibility reader, legacy
  stale fallback, or old Macro generation branch SHALL remain.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Token Radar short windows show fewer or zero rows. | Medium | Empty fresh is correct; stale rows are not current data. |
| Rank exits create a one-time downstream dirty queue wave. | Medium | Use existing publish callback and verify Pulse/Profile/Narrative queue depth. |
| Token Radar cache prune creates dead tuples. | Medium | Verify `n_dead_tup`; run `VACUUM (ANALYZE)` as rollout ops if needed. |
| Macro table swap creates a read gap. | High | Stage replacement first, stop projection briefly, swap in one short transaction, verify before dropping old storage. |
| Macro source signature misses meaningful changes. | High | Tests mutate selected row identity, value, source metadata, and freshness fields. |

## Alternatives Considered

- Keep three specs - rejected because these are priorities in one runtime DB
  optimization pass, and splitting made the workflow heavier than the change.
- API-side Token Radar filtering - rejected because the read model and
  downstream consumers would still be wrong.
- Token Radar expiry sweeper - rejected because time passing should not create a
  broad synthetic dirty-target scan.
- Increase Macro cleanup batch size - rejected because it chases write
  amplification instead of removing timestamp/UUID generation duplication.
- Batched delete only for Macro bloat - rejected because it creates WAL and
  leaves heap/index bloat unless followed by a table rewrite or swap.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | P0/P1/P2 are implemented under one performance hard-cut effort. |
| Always | Current rows and facts are protected from TTL-style deletes. |
| Always | Unchanged Macro facts produce no series-row rewrite. |
| Ask first | Accepting a brief Macro read gap for the fastest truncate/rebuild path. |
| Never | Add compatibility code for expired Token Radar cache or old Macro generations. |
| Never | Treat publication `ready` as permission to serve rows outside their window. |
