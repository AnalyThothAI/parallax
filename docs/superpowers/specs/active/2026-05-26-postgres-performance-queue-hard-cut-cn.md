# Spec — PostgreSQL Performance And Queue Backlog Hard Cut

**Status**: Draft
**Date**: 2026-05-26
**Owner**: Codex
**Related**:
- `docs/generated/postgres-observability/postgres-production-performance-analysis-2026-05-26-cn.md`
- `docs/superpowers/plans/active/2026-05-26-postgres-performance-queue-hard-cut-plan-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-performance-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`

## Background

The production Docker PostgreSQL instance is live traffic, not a disposable
fixture. Current observability is already wired into the compose runtime:
PostgreSQL loads `pg_stat_statements`, `powa`, `pg_stat_kcache`,
`pg_qualstats`, and `pg_wait_sampling` through `shared_preload_libraries` in
`compose.yaml:11`, and logs slow statements, lock waits, checkpoints,
temporary files, and autovacuum events in `compose.yaml:31`. PoWA Web and
pgBadger are defined as first-class services in `compose.yaml:124` and
`compose.yaml:140`.

Queue health is now exposed by runtime code rather than hand-written SQL.
`app.runtime.queue_health` declares status queue semantics for
`enrichment_jobs`, `pulse_agent_jobs`, `event_anchor_backfill_jobs`, and
`token_mention_semantics` in
`src/gmgn_twitter_intel/app/runtime/queue_health.py:24`, aggregates per-worker
and per-lane queue state in
`src/gmgn_twitter_intel/app/runtime/queue_health.py:56`, and reads dirty target
tables through a read-only summary query in
`src/gmgn_twitter_intel/app/runtime/queue_health.py:148`.

The current production performance analysis found that PostgreSQL is under real
pressure from a small number of query shapes, not from a general database
outage. The largest query is Token Radar rank-set loading. The implementation
still reads `SELECT *` from `token_radar_target_features` for every rank-set in
`src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:649`.
The service then applies cross-section normalization in
`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:245`
and writes current/history/audit read models. The rank algorithm currently
requires factor families and cohort metadata from the factor snapshot, as shown
by `TokenRadarProjection._apply_cross_section(...)` in
`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:566`.

`token_intent_lookup_keys` has a direct missing-index problem. The write path
deletes by `intent_id` in
`src/gmgn_twitter_intel/domains/token_intel/repositories/token_intent_lookup_repository.py:20`,
while the existing schema only provides the primary key `(lookup_key,
intent_id)` and a lookup-key index. Production `EXPLAIN` showed a sequential
scan for this delete.

Event-anchor cleanup still scans both the job table and fact table when marking
already-ready jobs done. The current query lives in
`src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:102`.
Projection stale-run cleanup is similarly high-frequency and filters
`status='running'` without a matching partial index in
`src/gmgn_twitter_intel/domains/token_intel/repositories/projection_repository.py:136`.

Macro read paths still do request-time dedupe and windowing over
`macro_observations` in
`src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:139`.
This is currently visible as a high mean-time query with temporary block writes.

`resolution_refresh` consumes `token_discovery_dirty_lookup_keys` through a
bounded `FOR UPDATE SKIP LOCKED` claim in
`src/gmgn_twitter_intel/domains/asset_market/repositories/discovery_repository.py:196`.
Queue health now shows this table with long due age and very high attempt
counts, which means retry policy and poison-key handling are incomplete even
though the claim mechanism itself is bounded.

## Problem

The system is operational, but production PostgreSQL is doing unnecessary work
on every live cycle: repeated wide rank-set reads, missing-index deletes,
cleanup scans that do not match existing indexes, request-time macro dedupe, and
queues that keep retrying or retaining terminal failures without an explicit
operator path. This creates CPU, I/O, WAL, vacuum, and queue-backlog pressure
while `readyz` can still be green.

## First principles

1. Runtime workers claim bounded control-plane work. They do not prove
   correctness by scanning broad fact/read-model tables during idle loops.
2. Business facts remain append-only or owner-written truth. Performance fixes
   must not introduce alternate truth, compatibility tables, or duplicate
   writers.
3. PostgreSQL production changes use observable, reversible mechanics:
   concurrent indexes for live tables, before/after `EXPLAIN (ANALYZE,
   BUFFERS)`, `pg_stat_statements` deltas, pgBadger log review, and PoWA
   snapshots.
4. Queue terminal states must be explicit. A row is either active retryable
   work, running work, terminal evidence, or archived operator history. It must
   not remain an ambiguous active queue row forever.

## Goals

- G1. Remove the hot `SELECT * FROM token_radar_target_features ... ORDER BY`
  query from the Top 10 `pg_stat_statements` total time list after one live
  observation window.
- G2. Make `DELETE FROM token_intent_lookup_keys WHERE intent_id = ...` use an
  `intent_id`-prefix index, with no sequential scan in `EXPLAIN`.
- G3. Make event-anchor ready cleanup stop scanning both
  `event_anchor_backfill_jobs` and `enriched_events` in the normal worker loop.
- G4. Make projection stale-run cleanup use a `status='running'` partial index
  or run on a bounded cadence that is not called for every rank-set refresh.
- G5. Reduce `token_discovery_dirty_lookup_keys` active due backlog and cap
  poison-key retries by moving exhausted keys into explicit terminal evidence.
- G6. Make Pulse, enrichment, mention semantics, and event-anchor terminal rows
  operator-actionable through one production ops path: inspect, retry,
  quarantine, or archive with an operator reason.
- G7. Make PoWA useful for trend analysis: current snapshots and coalesced
  history must both have data for the local server.
- G8. Preserve current product semantics: Token Radar ranking, current rows,
  rank history, snapshot audit, macro payloads, and queue business outcomes do
  not get compatibility branches or legacy fallbacks.

## Non-goals

- N1. Do not add feature flags, compatibility config, or dual old/new SQL
  paths.
- N2. Do not lower worker count or increase intervals as the main fix.
- N3. Do not delete business facts to make metrics green.
- N4. Do not reset production `pg_stat_statements` unless an operator explicitly
  approves it for a measurement window.
- N5. Do not drop `idx_scan=0` indexes in this work. Unused-index cleanup needs
  its own retention and rare-query review.
- N6. Do not introduce a lane supervisor in this phase. Queue health and
  PostgreSQL query pressure are the immediate production risks.

## Target Architecture

Token Radar rank refresh is split into a narrow ranking input path and a
selected-row payload path. The normal rank cycle no longer loads every JSONB
payload for every target. It ranks from compact scalar input and loads
`factor_snapshot_json` only for rows that will be published to current/history
read models. The existing wide feature table remains the owned feature store,
but the runtime hot path no longer uses `SELECT *` from it.

PostgreSQL storage is tuned for the query contracts the service actually runs:
lookup-key replacement has an `intent_id` index, rank-set ordering has a
matching index or narrow input table, ready event-anchor cleanup has either
edge-driven state transitions or matching partial indexes, and projection stale
cleanup has a running-only partial index.

Queue health remains read-only, but terminal row semantics become explicit.
Workers may retry active rows within a declared budget. After the budget is
exhausted, a worker writes terminal evidence and removes the row from active
claim eligibility. Operators can inspect and resolve terminal rows through a
single ops command that requires `--execute` and a reason.

PoWA becomes a trend tool rather than a "installed but empty" component. The
repository database keeps coalesced statement history, and pgBadger remains the
log-driven report for lock waits, deadlocks, checkpoints, temp files, and slow
statements.

## Conceptual Data Flow

```text
facts/control rows
  -> worker claim
  -> narrow PostgreSQL read path
  -> bounded write transaction
  -> queue_health + pg_stat_statements + pgBadger + PoWA
```

Changed arrows:

- Token Radar rank refresh changes from "load all feature rows as wide JSONB"
  to "rank compact inputs, then hydrate selected rows".
- Event-anchor cleanup changes from "scan jobs plus enriched events every loop"
  to "state transition at write edge or indexed bounded cleanup".
- Discovery refresh changes from "retry indefinitely in active dirty queue" to
  "retry budget, terminal evidence, operator action".
- Macro read path changes from "HTTP request dedupe over facts" to "read a
  projected/deduped read model once that projection exists".

## Core Models

`Rank Input`

- One row per `(projection_version, window, scope, lane, target_type_key,
  identity_id)`.
- Contains only scalar fields needed to rank: target identity, latest event
  time, raw family scores, weights, cohort counters, cohort booleans, current
  rank score, payload hash, and updated time.
- Does not duplicate product explanation JSON.

`Terminal Queue Evidence`

- One row per terminal queue decision.
- Contains worker name, source queue table, stable target key, final status,
  attempt count, final error/reason, payload hash when available, first seen,
  last attempted, terminalized time, and optional operator resolution.
- Terminal evidence is not active work and is not claimed by workers.

`PoWA Trend State`

- Local PoWA server entry with non-disabled frequency and retention.
- Current snapshot tables and coalesced history tables both contain rows.

## Interface Contracts

`/readyz`

- Continues to return service readiness.
- Queue backlog alone does not make readiness false.
- Queue table unavailable, manifest queue mismatch, or queue-health query
  failure is a readiness contract failure.
- Response includes per-worker and per-lane `queue_health`.

`gmgn-twitter-intel ops queue ...`

- New production operator surface for queue terminal handling.
- Inspect is read-only by default.
- Retry, quarantine, archive, or discard require `--execute` and an operator
  reason.
- Commands never print secrets and never mutate business fact tables.

PoWA and pgBadger

- pgBadger report generation remains `scripts/pgbadger_report.sh`.
- PoWA must expose both current snapshot and coalesced history for the local
  server.

## Acceptance Criteria

- AC1. WHEN Token Radar refreshes a rank set under live data THEN
  `pg_stat_statements` SHALL no longer show the old `SELECT * FROM
  token_radar_target_features ... ORDER BY lane DESC, rank_score DESC ...` in
  the Top 10 by total time after one observation window.
- AC2. WHEN `EXPLAIN (ANALYZE, BUFFERS)` is run for
  `DELETE FROM token_intent_lookup_keys WHERE intent_id = ...` THEN PostgreSQL
  SHALL use an `intent_id`-prefix index and SHALL NOT use a sequential scan.
- AC3. WHEN event-anchor cleanup runs with no ready rows THEN it SHALL complete
  through indexed or edge-driven work and SHALL NOT seq-scan both
  `event_anchor_backfill_jobs` and `enriched_events`.
- AC4. WHEN projection stale cleanup runs THEN it SHALL use a running-only
  partial index or a bounded cadence, and the query SHALL drop out of the Top 10
  `pg_stat_statements` total time list.
- AC5. WHEN `resolution_refresh` hits exhausted lookup keys THEN the system
  SHALL terminalize them into evidence and remove them from active due claims
  instead of increasing attempt counts indefinitely.
- AC6. WHEN `/readyz` is called THEN it SHALL expose queue health for all
  manifest queue tables and SHALL fail readiness only for contract/availability
  failures, not for ordinary backlog.
- AC7. WHEN pgBadger is run THEN it SHALL generate a report from the mounted
  production PostgreSQL logs.
- AC8. WHEN PoWA has run for at least one configured interval THEN
  `powa_statements_history_current` and `powa_statements_history` SHALL both
  contain local-server statement data.
- AC9. WHEN tests search for deleted compatibility paths THEN there SHALL be no
  old wide-rank compatibility method, feature flag, or fallback config.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Concurrent index creation still adds I/O load | High | Use `CREATE INDEX CONCURRENTLY`, one migration, off-peak rollout, and pgBadger/PoWA observation. |
| Narrow rank input drifts from factor snapshot semantics | High | Derive rank input from the same feature upsert payload in the same transaction and add parity tests against current ranking results. |
| Terminalizing queue rows hides real data loss | High | Terminal evidence is durable, inspectable, and requires explicit retry/archive workflows. Active queue rows are not silently discarded. |
| Readyz fails due to transient observability query errors | Medium | Readiness fails only on queue contract/availability failure after the adapter cannot read required tables; backlog is informational. |
| PoWA retention creates extra storage pressure | Medium | Set bounded retention and verify repository size. |
| Macro read-model materialization expands scope | Medium | Keep macro materialization as a separate phase after P0/P1 SQL fixes if the initial plan grows too large. |

## Evolution Path

After this hard cut, the next step is not a lane supervisor. The next useful
expansion is a small SLO dashboard fed by the already exposed queue health and
PostgreSQL observations:

- queue active depth, due depth, terminal count, and oldest due age by worker;
- Top SQL total time and mean time from `pg_stat_statements`;
- pgBadger lock/deadlock/checkpoint/temp-file counts;
- PoWA trend panels for query deltas.

Only after those signals are stable should we consider a lane supervisor that
changes runtime concurrency.

## Alternatives Considered

- Add a bigger Postgres instance or more shared buffers first. Rejected because
  the current evidence shows avoidable query shapes and queue retries; scaling
  hardware would preserve the root cause.
- Add a config flag for "old rank SQL" vs "new rank SQL". Rejected because this
  project is in hard-cut mode and dual paths would double test and ops burden.
- Only add indexes and keep the wide Token Radar rank query. Rejected because
  it may reduce sort cost but still loads wide JSONB for every candidate on
  every rank cycle.
- Make `/readyz` fail whenever backlog exists. Rejected because backlog is an
  operational SLO signal, not necessarily an app readiness failure. Restarting
  the app on backlog can make recovery worse.
- Delete terminal failed rows from queue tables without evidence. Rejected
  because it destroys the audit trail needed to understand poison work.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use production-safe migrations, no compatibility flags, no old SQL fallback, no secret printing, no broad idle scans. |
| Ask first | Resetting production statistics, dropping suspected unused indexes, deleting or archiving terminal queue evidence in bulk. |
| Never | Mutate business fact tables from ops queue cleanup, hide backlog by suppressing metrics, or use worker-count changes as the primary fix. |
