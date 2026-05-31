# Spec — PostgreSQL Runtime Root Cause Hard Cut

**Status**: Draft
**Date**: 2026-05-26
**Owner**: Codex
**Related**:
- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/generated/postgres-observability/postgres-production-performance-analysis-2026-05-26-cn.md`
- `docs/generated/postgres-observability/worker-architecture-audit-2026-05-26.md`
- `docs/generated/postgres-observability/worker-contract-spec-review-2026-05-26-cn.md`
- `docs/superpowers/specs/active/2026-05-26-postgres-performance-queue-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-26-postgres-performance-queue-hard-cut-plan-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`

## Background

The service is explicitly PostgreSQL-first Kappa/CQRS. `docs/ARCHITECTURE.md:62`
defines the Kappa/CQRS invariants; `docs/ARCHITECTURE.md:68` lists material
fact tables and separates control-plane worker state; `docs/ARCHITECTURE.md:104`
states that each derived read model has exactly one runtime writer. This hard
cut must strengthen those invariants rather than adding alternate truth,
compatibility readers, or hidden catch-up loops.

The first 2026-05-26 PostgreSQL hard cut removed the old wide Token Radar
rank-set read, added queue terminal evidence, and exposed backlog through
`/readyz`. The current follow-up diagnosis shows the bottleneck moved rather
than disappeared. `TokenRadarProjection.score_target_window(...)` calls
`TokenRadarTargetFeatureQuery.source_rows(...)` once per target/window/scope in
`src/parallax/domains/token_intel/services/token_radar_projection.py:244`.
That source query starts with `WITH source_intents AS MATERIALIZED` in
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:26`
and later performs lateral price-feed and enriched-event joins in
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:193`
and `src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:238`.

The rank publish path now correctly refuses stale compact rank inputs. The
guard is in
`src/parallax/domains/token_intel/services/token_radar_projection.py:459`;
when stale rows exist, it raises
`token_radar_rank_inputs_require_full_rebuild` at
`src/parallax/domains/token_intel/services/token_radar_projection.py:472`.
The current runtime problem is ordering: dirty targets are still claimed in
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:99`,
then expensive source hydration runs, and only later does rank publish fail
because the global rebuild prerequisite is still unmet. Failed dirty targets
are rescheduled by
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:660`,
so attempts keep growing while no read model is published.

Queue terminal evidence is now first-class. `terminalize_source_row(...)` writes
`worker_queue_terminal_events` in
`src/parallax/app/runtime/queue_terminal.py:20`, and
`inspect_terminal_events(...)` reads unresolved terminal evidence in
`src/parallax/app/runtime/queue_terminal.py:136`. Queue health is
filled from runtime manifests by
`src/parallax/app/runtime/queue_health.py:156`. The current backlog is
therefore visible, but several terminal classes still need root fixes:
provider `522`, no quote, no market data, stale TTL, and retry-budget
exhaustion.

Pulse has a concrete state-machine edge case. `claim_due_job(...)` only reclaims
stale `running` rows while `attempt_count < max_attempts` in
`src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:139`;
a row that is `running` and already at `attempt_count=max_attempts` can remain
running forever unless a separate cleanup path terminalizes it.

Macro reads still compute deduped latest observations at request/read time.
`latest_observations(...)` uses `row_number() OVER (...)` over
`macro_observations` in
`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:91`.
`observations_for_concepts(...)` performs request-time dedupe and series ranking
over `macro_observations` in
`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:139`.
This is visible in `pg_stat_statements` as temp-block writes.

The previous migration hygiene is uneven. Revision `20260526_0099` includes an
invalid concurrent-index check in
`src/parallax/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py:208`
and analyzes hot changed tables in
`src/parallax/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py:259`.
Revision `20260526_0100` creates concurrent indexes and analyzes
`worker_queue_terminal_events` in
`src/parallax/platform/db/alembic/versions/20260526_0100_worker_queue_terminal_events.py:74`,
but does not mirror the invalid-index assertion.

Fresh live evidence from 2026-05-26 18:15 Asia/Shanghai:

```text
/readyz ok=true
identity_market_fact: blocked, queue_depth=28, unresolved_terminal=3174
projection: degraded, queue_depth=696, failed=686, max_attempt=60
agent: blocked, queue_depth=29, running=1, unresolved_terminal=2038

token_radar_target_features:
  legacy_needs_rebuild:      16,292
  token-radar-rank-input-v1:    951

token_radar_dirty_targets:
  resolution_refresh:          402 total, 312 due, max_attempt=59
  market_tick_current_changed: 188 total, 171 due, max_attempt=59
  ingest_resolution:           106 total,  93 due, max_attempt=60
  sample error: token_radar_rank_inputs_require_full_rebuild

Top SQL:
  WITH source_intents AS MATERIALIZED (...)
  calls=3,601, total_exec_time=26,361ms, shared_blks_read=228,404,
  temp_blks_written=2,155

Macro request-time dedupe:
  calls=12, mean_exec_time=181.629ms, temp_blks_written=7,729
```

## Problem

The current production shape does too much work before it can know the work is
publishable. Token Radar dirty targets can run expensive per-target source
hydration and then fail at a global rebuild gate. Macro read paths still sort
and dedupe fact windows at request time. Some worker queues distinguish active
work from terminal evidence, but stale-running and no-start backpressure edges
still leak attempts or running rows. PostgreSQL observability is now good enough
to see the problem, but the system still lacks a hard-cut target where normal
runtime cost is proportional to claimed work and every terminal state is either
operator-actionable or removed from active work.

## First Principles

1. **Facts remain truth.** Performance work must not mutate or delete business
   facts to hide cost.
2. **Read models are owned outputs.** Every derived read model has one runtime
   writer and must be rebuildable from facts.
3. **Control-plane work must be bounded.** A worker may claim dirty targets,
   jobs, leases, or small scheduler partitions; it must not perform broad fact
   discovery in the no-work path.
4. **Prerequisites gate before expensive work.** Global preconditions such as
   rank-input rebuild completion must be checked before dirty-target claim and
   source hydration.
5. **Terminal is not active.** A row is active retryable work, running work, or
   terminal evidence with an operator path. It cannot be all three.
6. **PostgreSQL evidence wins.** Success is proved with `pg_stat_statements`,
   `EXPLAIN (ANALYZE, BUFFERS)`, queue tables, `/readyz`, and migration checks,
   not intuition.
7. **Hard cut, no compatibility.** Once the new path exists, old runtime SQL,
   broad scans, dual readers, fallback branches, and feature-flagged legacy
   modes are deleted.

## Goals

- G1. Complete Token Radar compact rank-input migration so active publishable
  rows have `rank_input_version='token-radar-rank-input-v1'`, no active window
  fails with `token_radar_rank_inputs_require_full_rebuild`, and stale legacy
  rows are not ranked or used as fallback input.
- G2. Replace per-target Token Radar source hydration with a batch projection
  input contract keyed by the claimed dirty-target set. Runtime projection must
  not execute the old `WITH source_intents AS MATERIALIZED` single-target query.
- G3. Gate Token Radar dirty-target processing before claim when rank-input
  rebuild is incomplete. The worker must skip with a clear status and avoid
  increasing dirty-target `attempt_count` while the global precondition is
  unmet.
- G4. Remove request-time macro dedupe over `macro_observations` from API/read
  repositories. Macro endpoints must read projected latest/history rows or
  bounded projection snapshots.
- G5. Terminalize or release stale-running Pulse jobs deterministically,
  including rows already at `attempt_count=max_attempts`.
- G6. Normalize provider/backpressure terminal reasons so queue health and ops
  inspection show reason buckets such as `llm_provider_522`, `provider_no_quote`,
  `no_market_data`, `stale_window_ttl`, `provider_unavailable`, `timeout`, and
  `retry_budget_exhausted`.
- G7. Ensure no-start provider backpressure does not burn domain retry budgets.
  Circuit-open/capacity-denied paths must release or reschedule active rows
  without counting as provider execution attempts.
- G8. Make queue-health/status queries use queue/control/terminal tables with
  matching indexes. They must not repeatedly scan large terminal source tables
  such as historical `done` rows to derive blocked counts.
- G9. Bring PostgreSQL maintenance hygiene to the same standard across the
  change: every concurrent index migration validates `pg_index.indisvalid`, and
  changed hot tables are analyzed after backfill/drain.
- G10. Define a live verification window where Top SQL, queue health, and table
  statistics show the hard cut worked without resetting production
  `pg_stat_statements` unless explicitly approved.

## Non-goals

- N1. Do not change Token Radar scoring formulas, Pulse prompts, LLM schemas, or
  product thresholds unless a separate product spec approves it.
- N2. Do not add a cache, Redis, Kafka, Celery, or Temporal to route around the
  PostgreSQL-first architecture.
- N3. Do not hide unresolved terminal evidence from `/readyz` or status output.
- N4. Do not lower worker count, lengthen intervals, or disable workers as the
  main fix.
- N5. Do not delete facts, audit rows, rank history, or terminal evidence to
  make counts look green.
- N6. Do not reset `pg_stat_statements` as part of automated verification.
  Deltas must be measured by snapshots unless an operator explicitly approves a
  reset for a controlled window.
- N7. Do not preserve old runtime query paths behind feature flags,
  environment toggles, "legacy" repository methods, compatibility readers,
  fallback branches, or low-frequency safety scans.
- N8. Do not build a broad worker supervisor in this spec. This work fixes the
  observed Token Radar, Macro, queue terminal, and PostgreSQL hygiene roots.

## Target Architecture

Token Radar runtime has two distinct stages:

1. **Rebuild gate and compact rank-input readiness.** Before dirty targets are
   claimed, the worker verifies that the rank-input contract is ready for every
   publishable window/scope it will refresh. If not ready, it records coverage
   and returns a skipped/precondition status without claiming or incrementing
   attempts.
2. **Batch source projection.** Claimed dirty targets are passed as a bounded
   input set. The projection reads current resolutions, events, market context,
   semantic context, and enrichment capture for the whole claimed set, not one
   target at a time. It hydrates only events that survive target/window/scope
   filtering and writes target features plus compact rank inputs through the
   Token Radar owner path.

The old single-target `source_rows()` runtime API is removed or converted into
a non-executable test fixture only if an architecture test proves no runtime
code can import it. The preferred target is deletion, not quarantine.

Macro gets a projected read model for deduped latest/history rows. Request
paths no longer run `row_number() OVER (...)` against `macro_observations`.
`macro_observations` remains the fact table and `MacroViewProjectionWorker`
remains the owner of macro product state unless the plan introduces a new macro
read model with an explicit single writer.

Queue terminal evidence becomes the source for blocked/terminal counts and
reason buckets. Source queue tables remain owner-state tables for active work,
but historical terminal rows are not repeatedly scanned from each source table
when `worker_queue_terminal_events` already stores terminal decisions.

Worker state machines follow this lifecycle:

```text
due control row
  -> claim with lease/running token
  -> reserve provider/agent capacity when needed
  -> execute deterministic/provider work
  -> owner transaction writes facts/read models/audit
  -> mark done, retryable, released due to no-start backpressure, or terminal
  -> terminal evidence is resolved only through operator action
```

PostgreSQL migrations follow one live-table pattern: bounded backfill, analyze,
concurrent index, invalid-index check, and post-drain analyze. There is no
separate "best effort" migration style for observability tables.

## Conceptual Data Flow

```text
facts
  -> owner writes dirty targets/jobs in same transaction
  -> worker precondition gate
  -> claim bounded control rows
  -> batch source payload load by claimed keys
  -> owner writes read models / terminal evidence
  -> /readyz + ops + pg_stat_statements + PoWA expose the result
```

Changed arrows:

- Token Radar changes from target-by-target source hydration to claimed-set
  batch projection input.
- Token Radar rebuild readiness moves before dirty-target claim.
- Macro reads move from fact dedupe at request time to projected read-model
  reads.
- Pulse stale-running cleanup moves into normal claim/maintenance lifecycle
  instead of depending on an uncalled side path.
- Queue health reads terminal evidence from `worker_queue_terminal_events`
  instead of repeatedly rediscovering terminal backlog from historical source
  tables.

## Core Models

`Token Radar Projection Batch Input`

- Keyed by `(target_type_key, identity_id, window, scope, dirty_reason,
  payload_hash)`.
- Contains only claimed targets and the source event ids/watermarks required to
  bound source hydration.
- The batch query returns the same semantic source row contract currently used
  by factor projection, but it returns rows for many claimed targets in one
  bounded execution.
- Runtime does not expose a single-target compatibility function.

`Rank Input Readiness`

- Per `(projection_version, window, scope)` readiness state.
- `ready` means all active publishable target feature rows in that rank set have
  the current rank-input version and non-null required scalar rank fields.
- `blocked` means the worker may report coverage and skip, but cannot claim
  dirty targets or increment attempts.

`Macro Latest Observation Read Model`

- Derived from `macro_observations`.
- Owns deduped latest observation per concept and bounded history needed by API
  reads.
- Has one writer and is rebuildable from `macro_observations`.
- Request paths treat missing projection as stale/unready state, not a reason
  to fall back to fact-window dedupe.

`Queue Terminal Reason Bucket`

- Normalized reason derived from terminal evidence.
- Examples: `llm_provider_522`, `provider_no_quote`, `no_market_data`,
  `stale_window_ttl`, `provider_unavailable`, `timeout`,
  `retry_budget_exhausted`.
- Used by `/readyz`, status, ops inspection, and reports.
- Does not replace full `final_reason`; it makes high-cardinality errors
  aggregateable.

## Interface Contracts

`/readyz`

- Keeps `ok=true` when the process is serving and queue pressure is known.
- Shows lane and worker queue health with active, running, blocked, terminal,
  unresolved terminal, and reason-bucket aggregates.
- Does not hide terminal backlog or projection precondition skips.
- Marks readiness false only for contract failures such as unavailable queue
  tables, manifest mismatches, DB liveness failure, or migration mismatch.

`parallax ops queue-inspect`

- Remains read-only by default.
- Supports filtering by worker, source table, terminal status, and normalized
  reason bucket.
- Shows enough source-row identity for an operator to decide retry/archive/
  quarantine without raw secret leakage.

`parallax ops queue-resolve`

- Requires `--execute` plus an operator reason.
- Uses owner repository transitions for retry.
- Never updates source queue tables by ad hoc SQL.

`parallax ops rebuild-token-radar-rank-inputs`

- Is the only accepted path to finish compact rank-input migration.
- Writes through the Token Radar owner path.
- Has progress output that can be checked without reading JSON payloads.

Macro HTTP APIs

- Preserve public payload shape unless a separate Macro product spec changes
  it.
- Must not run request-time fact-window dedupe over `macro_observations`.
- If projected macro read model is stale or missing, return explicit stale or
  partial projection metadata rather than executing the old query as fallback.

## Acceptance Criteria

- AC1. WHEN Docker runtime is started on Alembic head THEN `/readyz` SHALL
  return `ok=true`, `migration_version=20260526_0100` or newer, and no queue
  table availability or manifest mismatch failures.
- AC2. WHEN `ops rebuild-token-radar-rank-inputs --execute` completes THEN
  `SELECT rank_input_version, count(*) FROM token_radar_target_features GROUP BY
  1` SHALL show zero active publishable rows with `legacy_needs_rebuild`.
- AC3. WHEN Token Radar projection runs for at least two hot cycles after AC2
  THEN `token_radar_dirty_targets.last_error` SHALL contain zero rows equal to
  `token_radar_rank_inputs_require_full_rebuild`, and max attempt count for
  newly touched dirty targets SHALL NOT increase because of rebuild
  precondition failure.
- AC4. WHEN comparing `pg_stat_statements` snapshots before and after a
  10-minute live projection window THEN delta calls for the normalized old
  `WITH source_intents AS MATERIALIZED` Token Radar single-target query SHALL be
  zero.
- AC5. WHEN a representative Token Radar projection batch is explained with
  `EXPLAIN (ANALYZE, BUFFERS)` THEN the plan SHALL use the claimed target input
  set, avoid per-target nested execution of the whole source hydration query,
  and stay within the plan/buffer thresholds documented in the implementation
  plan.
- AC6. WHEN architecture tests scan runtime code THEN there SHALL be no
  executable call path from `TokenRadarProjection.score_target_window(...)` to a
  single-target `source_rows()` compatibility function.
- AC7. WHEN Macro API/read tests call latest/history endpoints THEN no runtime
  query SHALL execute `row_number() OVER` over `macro_observations`; reads SHALL
  use projected rows or return explicit stale/partial projection metadata.
- AC8. WHEN comparing `pg_stat_statements` snapshots around Macro API smoke
  calls THEN delta calls for request-time `WITH deduped AS (...) FROM
  macro_observations` queries SHALL be zero.
- AC9. WHEN Pulse has a `running` job older than the configured running timeout
  and `attempt_count >= max_attempts` THEN the next worker maintenance/claim
  cycle SHALL terminalize or release it deterministically; no such row may
  remain running beyond one cycle.
- AC10. WHEN provider capacity is denied before an LLM/provider request starts
  THEN the worker SHALL reschedule/release the row without increasing provider
  attempt count or writing terminal evidence.
- AC11. WHEN provider execution returns terminal errors such as Cloudflare
  `522`, no quote, no market data, stale TTL, or timeout THEN
  `worker_queue_terminal_events` SHALL store both full `final_reason` and a
  queryable normalized reason bucket.
- AC12. WHEN `/readyz` and CLI status summarize queues THEN terminal/backlog
  counts SHALL be derived from indexed queue/control/terminal evidence and SHALL
  not require repeated scans of large historical terminal source-table states.
- AC13. WHEN any new migration creates indexes concurrently THEN it SHALL also
  assert that the created indexes are valid before success is claimed.
- AC14. WHEN the drain/rebuild wave finishes THEN changed hot tables SHALL have
  fresh analyze timestamps, no invalid indexes, and `pg_stat_user_tables`
  estimates close enough to actual counts for the thresholds documented in the
  plan.
- AC15. WHEN `rg` scans the implementation after merge THEN no legacy fallback
  names, old query strings, feature flags, compatibility branches, or dual-read
  paths banned by this spec SHALL remain outside architecture tests that assert
  their absence.
- AC16. WHEN final verification is recorded THEN it SHALL include
  `make check-all`, Docker `/readyz`, `docker compose ps --all`,
  `pg_stat_activity` blocker check, `pg_stat_statements` before/after deltas,
  invalid-index check, terminal reason-bucket aggregation, and table statistics
  for the hot tables named in this spec.

## Verification Matrix

| Target | Required Check |
| --- | --- |
| Runtime config | `uv run parallax config` reports operator-owned config and workers paths under `~/.parallax/`, with secrets redacted. |
| Docker health | `docker compose ps --all` shows app/postgres healthy and migrate exited 0. |
| Readiness | `curl -sS http://127.0.0.1:8765/readyz` shows `ok=true` and no contract-failure reasons. |
| Blockers | `pg_stat_activity` and `pg_blocking_pids(...)` show no unexpected blockers or persistent `idle in transaction`. |
| Token Radar rebuild | SQL proves zero active publishable `legacy_needs_rebuild` rows and zero rebuild-gate dirty target errors. |
| Token Radar SQL | `pg_stat_statements` delta proves zero calls to the old `WITH source_intents AS MATERIALIZED` query; `EXPLAIN` proves batched claimed-set plan. |
| Macro read path | API smoke plus `pg_stat_statements` delta proves no request-time macro dedupe query. |
| Pulse stale running | SQL over `pulse_agent_jobs WHERE status='running'` proves no row older than running timeout with exhausted attempts. |
| Terminal buckets | SQL over `worker_queue_terminal_events` aggregates by normalized bucket and matches `/readyz`/CLI counts. |
| Provider no-start | Tests prove circuit-open/capacity-denied paths do not burn attempts. |
| Migrations | `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid` returns zero rows. |
| Table stats | `pg_stat_user_tables` for `token_radar_target_features`, `token_intent_lookup_keys`, `token_intent_resolutions`, `event_anchor_backfill_jobs`, and `pulse_agent_runs` shows fresh analyze after drain. |
| Static no-compat | `rg` checks prove old function names, old SQL strings, compatibility flags, and fallback branches are absent from runtime code. |

## Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Batch Token Radar source query changes factor inputs. | High | Keep output contract identical; add golden tests comparing old fixture rows to new batch rows before deleting old runtime path. |
| Removing macro fallback exposes stale projections. | Medium | Return explicit stale/partial metadata and add ops rebuild command; do not silently recompute from facts on request path. |
| Terminal reason bucketing hides details. | Medium | Store bucket in addition to full `final_reason`; never replace raw terminal evidence. |
| Analyze during heavy rewrite gives unstable stats. | Medium | Run final `VACUUM (ANALYZE)` / `ANALYZE` after drain, then verify actual counts versus estimates. |
| Source query index guesses add write overhead. | Medium | Require `EXPLAIN (ANALYZE, BUFFERS)` before adding indexes; concurrent indexes only; invalid-index assertion required. |
| No compatibility path makes rollback harder. | Medium | Rollback is previous deployment plus owner-path rebuild/repair commands, not runtime dual reads. |
| Provider outage persists after DB fixes. | Medium | Queue reason buckets separate provider terminal causes from DB pressure; do not retry terminal rows automatically while circuit is open. |

## Evolution Path

After this hard cut, a later spec can decide whether to introduce a broader
worker lane supervisor. That future work should consume the same queue-health,
terminal reason, and PostgreSQL evidence produced here; it should not re-open
old broad-scan compatibility paths. A separate retention spec should handle
large append-only partitions such as Token Radar audit/history and market ticks.

## Alternatives Considered

- **Keep old `source_rows()` and add indexes only.** Rejected because the root
  cost is target-by-target source reconstruction plus rollout ordering. Indexes
  may help the plan, but they do not fix work that runs before publishability is
  known.
- **Reset `pg_stat_statements` and tune by fresh totals only.** Rejected because
  production stats are evidence. Deltas from snapshots are enough and avoid
  erasing operator context.
- **Return to runtime broad scans as safety net.** Rejected because this is the
  failure class the project has been hard-cutting away from. Missed enqueue
  repair belongs to bounded ops commands.
- **Add Redis or an external queue.** Rejected because the current architecture
  is one PostgreSQL store. The problem is not that PostgreSQL cannot model the
  queue; it is that some runtime paths still do unbounded work or preserve stale
  states.
- **Keep request-time macro dedupe while increasing `work_mem`.** Rejected
  because the query belongs in projection/read-model ownership. `work_mem` would
  treat the symptom and preserve the CQRS smell.
- **Automatically retry all terminal evidence after provider recovery.**
  Rejected because terminal rows require operator intent. Some reasons are
  business terminal states such as no quote or no market data, not transient
  failures.

## Boundaries

| Class | Behaviour |
| --- | --- |
| Always | Check global rebuild prerequisites before expensive runtime work; claim bounded control rows before payload hydration; write terminal evidence through owner transitions; prove performance with PostgreSQL evidence. |
| Ask first | Resetting `pg_stat_statements`; executing destructive retention/drop-partition commands; archiving or retrying large terminal batches; changing public API payloads. |
| Never | Keep old SQL behind flags; run dual old/new readers; mutate facts to hide backlog; use ad hoc SQL to repair terminal rows; make `/readyz` green by suppressing known queue evidence; introduce a second queue/database for this fix. |
