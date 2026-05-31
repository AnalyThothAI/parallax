# Spec — Runtime Performance Architecture Root Fix Hard Cut

**Status**: Draft
**Date**: 2026-05-26
**Owner**: Codex
**Related**:
- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/superpowers/specs/active/2026-05-26-postgres-performance-queue-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-26-postgres-runtime-root-cause-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-26-postgres-performance-queue-hard-cut-plan-cn.md`
- `docs/ARCHITECTURE.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`

## Background

The project architecture is already PostgreSQL-first Kappa/CQRS. `AGENTS.md:7`
declares one PostgreSQL store, and `AGENTS.md:9` says material facts are the
only business truth, derived read models are rebuildable, and `NOTIFY` is only
a wake hint. `docs/ARCHITECTURE.md:68` lists the fact tables, control-plane
tables, and rebuildability invariant. `docs/ARCHITECTURE.md:104` requires one
runtime writer per read model. `docs/ARCHITECTURE.md:140` requires every worker
listener to re-read durable DB state through bounded catch-up, not broad fact
scans.

The current local `main` is `871e8ac4 feat: hard cut OpenNews signal news
view`, ahead of `origin/main`. News has already been refactored on `main`:
`src/parallax/integrations/news_feeds/provider_registry.py:10`
declares `opennews` as a supported provider type, and
`src/parallax/integrations/news_feeds/provider_registry.py:203`
registers the OpenNews provider. The fetch worker reconciles configured
sources into `news_sources` before claiming due work in
`src/parallax/domains/news_intel/runtime/news_fetch_worker.py:56`,
then calls `feed_client.fetch(...)` at
`src/parallax/domains/news_intel/runtime/news_fetch_worker.py:123`.
The repository writes configured source metadata through
`src/parallax/domains/news_intel/repositories/news_repository.py:106`.
Revision `20260526_0105` adds `opennews` to the
`news_sources_provider_type_check` constraint and adds provider-signal columns
in
`src/parallax/platform/db/alembic/versions/20260526_0105_opennews_provider_signal.py:32`.

The currently running Docker app was built before that source/schema head was
applied: `/readyz` reported migration `20260526_0104` and failed with
`news_fetch` check-constraint errors for `provider_type=opennews`. This is not
a PostgreSQL performance defect; it is source, config, and schema drift. It
must still be fixed in this hard cut because readiness cannot be green while
runtime config contains a provider type the deployed schema rejects.

Token Radar no longer uses the old single-target source query, but the current
batch hydrate is still the largest live PostgreSQL hotspot. The runtime calls
`TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)` from
`src/parallax/domains/token_intel/services/token_radar_projection.py:125`
and again from
`src/parallax/domains/token_intel/services/token_radar_projection.py:235`.
That batch query is defined in
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:31`
with `TOKEN_RADAR_SOURCE_REQUEST_CHUNK_SIZE = 200` at
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:11`.
The SQL joins request targets to `token_intent_resolutions`, `token_intents`,
and `events` at
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:117`,
filters event time only after reaching `events` at
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:122`,
and then performs account, semantic, asset, price-feed, enriched-event, and
market-current hydration through joins and lateral subqueries ending at
`src/parallax/domains/token_intel/queries/token_radar_target_feature_query.py:328`.

Live `pg_stat_statements` evidence from 2026-05-26:

```text
queryid=-104756196016094635
shape=WITH request_targets AS (...) source_intents AS (...)
calls=616
total_exec_time=175377.43ms
mean_exec_time=284.70ms
max_exec_time=2861.29ms
rows=66304
shared_blks_read=1423148
shared_blk_read_time=145780.48ms
temp_blks_written=544
```

Large table pressure is dominated by width, TOAST, and retention rather than
row count:

```text
token_radar_snapshot_audit_202605  total=6517MB live_rows=7
market_ticks_default               total=2123MB live_rows=2232
events                             total=2002MB live_rows=2738
token_radar_rank_history_202605    total=1062MB live_rows=0
equity_event_evidence_artifacts    total=798MB  heap=2520kB
raw_frames                         total=873MB  live_rows=4900
```

The wait profile matches that storage shape. `pg_wait_sampling_profile` shows
`DataFileRead`, `AioIoCompletion`, and `DataFileWrite` as the top meaningful
waits. Live lock checks showed `idle_in_xact=0`, `lock_waiters=0`, and no
invalid indexes, so the current dominant problem is not lock contention.

Macro already declares the right architecture. `macro_observation_series_rows`
is a read model written only by `MacroViewProjectionWorker` in
`src/parallax/domains/macro_intel/ARCHITECTURE.md:15`, and request
paths must read that projection instead of running window functions over
`macro_observations` according to
`src/parallax/domains/macro_intel/ARCHITECTURE.md:40`. The remaining
runtime issue is the writer implementation:
`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:138`
deletes all `macro_observation_series_rows` for a projection version before
inserting rebuilt rows at
`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:174`.
This creates WAL churn and a transient empty-read risk if the rebuild is
interrupted.

Equity event ingestion has a different root. `EquityEventFetchWorker.run_once`
uses `asyncio.to_thread(...)` at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:49`,
claims multiple due sources at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:55`,
fetches each source synchronously at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:79`,
hydrates every inserted/updated document inline at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:139`,
and loops provider evidence hydration per document at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:272`.
The default batch size is 20 at
`src/parallax/domains/equity_event_intel/runtime/equity_event_fetch_worker.py:386`.
`WorkerBase` soft and hard timeouts apply to the whole `run_once` task in
`src/parallax/app/runtime/worker_base.py:215`, while the underlying
blocking provider work inside `to_thread` is not a cleanly cancellable unit.
Live data showed 41 `equity_event_fetch_runs.status='running'`, with the oldest
older than 4300 minutes.

## Problem

The earlier PostgreSQL and queue hard cuts improved visibility and removed some
legacy paths, but the system still contains four architecture leaks:

1. **Hot projection paths replay wide facts.** Token Radar ranking still
   rehydrates target-event context by joining current resolutions, intents,
   wide events, enrichment, price feeds, and market ticks for every dirty
   target batch. This is a Kappa/CQRS implementation leak: the read model is
   rebuildable, but runtime cost is still proportional to historical facts
   touched by the query rather than to a compact claimed work set.
2. **Hot tables carry cold payload and unbounded history.** Audit, rank history,
   events, raw frames, evidence artifacts, and market ticks store large JSON or
   text payloads in tables that hot queries still touch. PostgreSQL tuning can
   hide some latency, but it cannot make repeated heap/TOAST reads cheap.
3. **Some workers are not bounded state machines.** News source reconciliation,
   equity source fetch, equity evidence hydration, and projection refreshes are
   coupled to broader side effects than a single bounded control row should
   own. This creates soft timeouts, stale-running rows, and readiness failures
   that are not business truth.
4. **Deploy/schema drift can break readiness even when code is correct.**
   `main` supports OpenNews and has migration `0105`, while the live runtime
   still reported `0104`. A PostgreSQL-first system needs a hard gate proving
   runtime config, provider registry, and DB constraints agree after Docker
   rebuild.

So the root cause is partly architectural, but not the high-level architecture.
The PostgreSQL-first Kappa/CQRS model is the right model for this service. The
problem is architecture erosion in implementation: incomplete intermediate read
models, wide hot tables, monolithic worker iterations, and missing deploy-head
validation. This spec is intended to root-fix those causes, not tune around
them.

## First principles

1. **Facts remain truth; hot read models may be narrower than facts.** Fact
   tables listed in `docs/ARCHITECTURE.md:68` remain authoritative. Performance
   fixes may introduce compact read models or edge tables only if they are
   single-writer and rebuildable under `docs/ARCHITECTURE.md:104`.
2. **Runtime cost must be proportional to claimed work.** Workers may process
   bounded dirty targets, jobs, leases, or projection partitions. They must not
   use broad fact discovery or wide hydration as their normal no-work or
   steady-state path.
3. **Schema, provider registry, and operator config are one contract.** If
   runtime config names `opennews`, the provider registry, DB check constraint,
   migrations, and live Alembic head must all accept `opennews`; otherwise the
   system is not ready.
4. **Terminal and stale-running states are explicit evidence.** Active work,
   running work, released work, and terminal evidence are separate lifecycle
   states. A row cannot stay `running` indefinitely after a hard timeout.
5. **No compatibility paths.** Once a hard-cut path exists, old SQL, fallback
   readers, feature flags, and compatibility code are deleted rather than kept
   dormant.

## Goals

- G1. After Docker rebuild and migration, live `/readyz` reports DB migration
  head equal to the latest Alembic revision on `main`, including
  `20260526_0105`; `news_fetch` no longer fails with
  `news_sources_provider_type_check` for `opennews`.
- G2. Token Radar runtime no longer calls
  `TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)` from normal
  projection flow. The old `WITH request_targets AS (...)` query has zero new
  `pg_stat_statements` calls during a controlled live refresh window.
- G3. Token Radar introduces a compact target-event or rank-source edge read
  model whose owner is declared in the token domain architecture. The edge rows
  contain only scalar fields required for ranking and hydration keys; wide
  event text, raw payload, explanation JSON, and audit snapshots are not in the
  hot ranking scan.
- G4. Token Radar projection p95 DB time for one claimed batch is under 100ms
  on the current local live dataset, with no temp block writes in the ranking
  source query and no single Token Radar query occupying more than 10 percent
  of Top SQL total time over the verification window.
- G5. Large hot tables have an explicit hot/cold and retention contract. Current
  runtime queries do not read full JSON/text/audit payloads unless they are
  hydrating selected published rows. Audit/history partitions older than the
  retained hot window are detached/dropped or rewritten through an approved
  maintenance command, not row-deleted in worker loops.
- G6. Macro observation series refresh no longer uses the
  `DELETE all projection_version rows + INSERT all rows` pattern. It writes a
  staged generation and atomically activates it, so request paths never observe
  an empty projection during refresh.
- G7. Equity source fetch and evidence hydration are split. Source fetch claims
  source leases, persists provider/document facts, and enqueues document-level
  evidence jobs. Evidence hydration runs in a separate bounded worker with
  per-document leases, retry budget, terminal evidence, and provider-level
  HTTP/client timeouts.
- G8. Stale `equity_event_fetch_runs.status='running'` rows are reaped or
  terminalized deterministically. After one verification interval, stale
  running fetch runs older than the configured hard timeout equal zero.
- G9. News source reconciliation validates configured provider types before
  attempting DB writes and surfaces unsupported config as a clear readiness or
  startup contract failure. It does not rely on catching a database check
  constraint after partial worker startup.
- G10. The performance score reaches at least 90/100 under the project review
  rubric: readiness healthy, Top SQL without old Token Radar hydrate, no stale
  equity running rows, no lock/idle transaction incident, bounded table
  lifecycle documented, PoWA and pgBadger evidence refreshed.

## Non-goals

- N1. Do not add Redis, Kafka, Celery, Temporal, or another durable execution
  plane. PostgreSQL remains the execution store.
- N2. Do not lower worker count, lengthen intervals, or disable providers as
  the main fix. Temporary throttles may be used only as rollout safety.
- N3. Do not delete business facts, rank history, raw provider facts, or
  terminal evidence to make metrics green.
- N4. Do not preserve old runtime paths behind feature flags, "legacy" methods,
  fallback readers, or compatibility branches.
- N5. Do not redesign the frontend in this spec. UI changes are allowed only
  when needed to expose new ops/readiness evidence.
- N6. Do not change Token Radar scoring semantics, News product semantics,
  Macro regime scoring, or Equity brief prompts unless a separate product spec
  approves the semantics.
- N7. Do not reset production `pg_stat_statements` as the only proof. Use
  before/after snapshots unless the operator explicitly approves a reset window.

## Target architecture

Token Radar runtime becomes a two-level projection:

1. Fact writers and enrichment workers produce or enqueue compact
   target-event/rank-source edges in the same owner transaction that makes the
   facts publishable.
2. `TokenRadarProjectionWorker` claims dirty targets and ranks from the compact
   edge/read-model contract. It hydrates wide payloads only for selected rows
   that will be written to current/history/audit outputs.

The edge/read-model is not a second truth. It is a rebuildable projection over
`events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`,
`enriched_events`, and market-current state. Its single writer is declared in
`src/parallax/domains/token_intel/ARCHITECTURE.md`.

Table storage is split by temperature:

- Hot fact/control/read-model tables keep scalar columns used for filters,
  ordering, ranking, leases, status, and idempotency.
- Cold artifact tables keep raw payload JSON, full text, explanation JSON,
  evidence blobs, and audit snapshots, keyed by stable id plus content hash.
- Time-partitioned audit/history tables have a retention lifecycle that uses
  partition detach/drop or controlled rewrite. Worker loops do not prune large
  history with broad `DELETE`.

Macro keeps its current domain architecture but changes refresh mechanics.
`MacroViewProjectionWorker` writes a new generation of
`macro_observation_series_rows` into a staging/generation contract, validates
coverage, and atomically switches the active generation. Reads continue to use
projected rows and never fall back to raw observations.

News becomes schema-first for provider support. The provider registry,
`SUPPORTED_NEWS_PROVIDER_TYPES`, Alembic check constraint, operator config, and
API diagnostics form one contract. Startup or readiness must identify drift
before `news_fetch` starts writing configured sources. OpenNews provider signal
fields are first-class facts/read-model inputs after migration `0105`; they are
not optional compatibility columns.

Equity event ingestion becomes a pipeline of bounded workers:

- `EquityEventFetchWorker`: claim source, fetch source listing, persist provider
  documents and event documents, enqueue evidence jobs, finish/release source
  run.
- `EquityEventEvidenceHydrationWorker`: claim document evidence jobs with
  `FOR UPDATE SKIP LOCKED`, hydrate one bounded batch, upsert artifacts by
  content hash, terminalize exhausted jobs, and notify projections.
- Existing story/page/brief workers consume document/evidence facts and dirty
  targets as they do today, but no longer depend on source fetch finishing
  evidence hydration inside the same `run_once`.

## Conceptual data flow

```text
provider/config facts
  -> schema/config head check
  -> bounded source/job claim
  -> narrow facts or compact edge rows
  -> single-writer projections
  -> read APIs / ops / readiness
  -> PostgreSQL evidence loop
```

Changed arrows:

- Token Radar changes from "dirty target -> wide source hydrate over facts" to
  "dirty target -> compact target-event edge scan -> selected-row hydrate".
- News changes from "configured provider -> DB constraint failure during worker"
  to "provider config validated against registry and migrated schema before
  source writes".
- Equity changes from "source fetch -> inline document hydration -> finish run"
  to "source fetch -> document facts -> evidence jobs -> independent hydration".
- Macro changes from "delete active projection -> insert rebuild" to "stage new
  generation -> validate -> atomically activate".
- Table lifecycle changes from "large hot tables grow until manual diagnosis"
  to "hot/cold payload split plus partition retention contract".

## Core models

`Token Radar Rank Source Edge`

- One row per publishable target-event-intent-resolution edge.
- Keys: target type, target id, event id, intent id, resolution id, projection
  source version.
- Ranking fields: received time, watched scope, author handle/follower signals,
  semantic hints, identity confidence, current price/tick identifiers, event
  price capture identifiers, source payload hash, updated time.
- Invariants: one runtime writer, rebuildable from facts, no full event text,
  no raw provider payload, no audit snapshot payload.

`Cold Artifact`

- One row per large payload, keyed by owner kind, owner id, artifact kind, and
  content hash.
- Holds raw JSON/text/explanation/audit details used only for selected hydration
  and operator inspection.
- Invariants: content-hash idempotency, no hot query orders or filters on cold
  payload columns.

`Projection Generation`

- Logical generation id or run id for read models that must refresh in bulk.
- Contains projection version, generation id, row count, coverage diagnostics,
  status, created/activated timestamps.
- Invariants: readers use only the active generation; failed generations do not
  remove the previous active generation.

`Equity Evidence Job`

- One row per event document requiring evidence hydration.
- Contains document id, provider document id, source id, content hash, status,
  attempts, lease timestamps, last error, terminal reason, and payload hash.
- Invariants: stale running is reaped, no-start provider backpressure does not
  burn execution attempts, terminal rows leave active claim eligibility.

`Provider Schema Contract`

- The normalized provider types supported by code, Alembic constraints, runtime
  config, and API diagnostics.
- Invariants: unsupported configured provider types fail before source writes;
  supported provider types have corresponding schema and registry support.

## Interface contracts

`/readyz`

- Returns 200 only when DB liveness, migration head, provider/schema contract,
  and worker readiness contracts pass.
- Does not fail solely because ordinary terminal backlog exists, but does fail
  when a manifest queue table is unavailable, a worker has unreaped stale
  running state beyond policy, or configured providers cannot be represented by
  the DB schema.
- Includes enough per-worker evidence to identify `news_fetch` provider/schema
  drift and `equity_event_fetch` timeout/stale-running state without reading
  secrets.

`parallax config`

- Continues to report redacted config paths and enabled provider booleans.
- Must let operators confirm `~/.parallax/config.yaml` and
  `workers.yaml` are the active runtime inputs before diagnosing live data.

`parallax ops ...`

- Adds or extends dry-run-first commands for rebuilding Token Radar rank-source
  edges, refreshing macro projection generations, reaping equity stale-running
  fetch runs, inspecting evidence hydration jobs, and applying audit/history
  retention.
- Mutating commands require `--execute` and an operator reason when they
  terminalize, archive, or drop/rewrite large history.

PostgreSQL observability

- Verification reads `pg_stat_statements`, `pg_stat_kcache`,
  `pg_wait_sampling`, PoWA history, pgBadger report output, table sizes, and
  readiness responses.
- Mutating `EXPLAIN (ANALYZE)` must be wrapped in `BEGIN` and `ROLLBACK`.

## Acceptance criteria

- AC1. WHEN Docker is rebuilt from latest local `main` and migrations run THEN
  `/readyz` SHALL report `migration_version=20260526_0105` or newer and SHALL
  not include a `news_sources_provider_type_check` failure for `opennews`.
- AC2. WHEN runtime config contains a provider type unsupported by code or
  schema THEN startup/readiness SHALL report a provider/schema contract failure
  before `NewsFetchWorker` attempts `upsert_source(...)`.
- AC3. WHEN Token Radar projection processes a live dirty-target batch THEN no
  runtime stack SHALL call
  `TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)`.
- AC4. WHEN `pg_stat_statements` is snapshotted before and after a controlled
  Token Radar refresh THEN the old `WITH request_targets AS (...)` query SHALL
  show zero new calls.
- AC5. WHEN `EXPLAIN (ANALYZE, BUFFERS)` is run on the new Token Radar rank
  source read for a representative batch THEN it SHALL not write temp blocks
  and SHALL keep mean execution under 100ms on the current local live dataset.
- AC6. WHEN ranking requires full row details THEN the system SHALL hydrate only
  selected output rows by stable key plus payload hash, not all candidate
  source rows.
- AC7. WHEN `pg_stat_user_tables` is inspected after retention/rewrite
  maintenance THEN hot runtime tables SHALL have documented retention and no
  active hot query SHALL require scanning cold payload/audit columns.
- AC8. WHEN macro projection refresh is interrupted before activation THEN
  existing active `macro_observation_series_rows` SHALL remain readable and
  non-empty.
- AC9. WHEN macro projection refresh succeeds THEN readers SHALL switch to the
  new generation atomically and previous generation cleanup SHALL be bounded.
- AC10. WHEN `equity_event_fetch` runs for one interval THEN it SHALL finish
  source fetch runs without inline evidence hydration and SHALL not exceed its
  configured soft timeout.
- AC11. WHEN stale equity fetch runs older than the hard timeout exist THEN the
  stale-running reaper SHALL mark or terminalize them deterministically, and a
  later count of stale `running` fetch runs SHALL be zero.
- AC12. WHEN evidence hydration provider calls fail, time out, or return empty
  content THEN document evidence jobs SHALL retry within budget and then become
  terminal evidence, not permanent active/running rows.
- AC13. WHEN `/readyz` is called after the verification window THEN it SHALL be
  200 unless an actual external provider outage is still active and classified
  as a configured readiness blocker.
- AC14. WHEN PoWA and pgBadger are refreshed THEN the verification artifact
  SHALL include PoWA statement/wait history counts, pgBadger report path/size,
  and Top SQL before/after deltas.
- AC15. WHEN architecture tests or repository searches run THEN no deleted
  compatibility methods, old Token Radar hydrate fallback, macro raw-observation
  fallback, or OpenNews schema bypass SHALL remain in executable code.
- AC16. WHEN the work is reviewed against the 100-point performance rubric THEN
  the implementation SHALL score at least 90: 30 points Token Radar hot path,
  20 points storage lifecycle, 20 points worker boundedness, 15 points
  schema/config readiness, 10 points observability proof, 5 points no legacy
  compatibility.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Compact Token Radar edge drifts from fact semantics | High | Build from owner fact transitions, add rebuild command, add parity tests comparing old candidate semantics before deleting old path. |
| Hot/cold split creates an accidental second truth | High | Cold artifacts are payload storage only; ranking/filtering fields stay in owner facts or read models, with one writer declared in architecture docs. |
| Retention maintenance drops useful audit history | High | Mutating retention commands are dry-run first, require `--execute`, print partition/table impact, and never run inside worker loops. |
| Macro generation swap adds complexity | Medium | Use a small generation pointer contract and tests that simulate refresh failure before activation. |
| Equity split creates duplicate document hydration | Medium | Evidence job idempotency uses document id plus content hash and `FOR UPDATE SKIP LOCKED` leases. |
| News schema/config check blocks startup after config typo | Medium | Failure is intentional and explicit; diagnostics list unsupported provider types without secrets. |
| Verification metrics vary with live traffic | Medium | Use before/after snapshots over a controlled window and report deltas rather than absolute cumulative totals only. |

## Evolution path

After this hard cut, the next expansion should be a small production SLO board
fed by the same evidence: readiness status, Top SQL deltas, worker stale-running
counts, terminal queue buckets, table-size budgets, PoWA wait trends, and
pgBadger slow-log regressions. It should not introduce a new scheduler or cache.
If this spec still leaves a domain with broad fact replay in a hot path, that
domain should get its own compact edge/read-model spec using the same pattern.

## Alternatives considered

- **Only add indexes and tune PostgreSQL settings** — rejected because the
  largest cost comes from query shape and wide heap/TOAST reads. Indexes help
  candidate lookup, but they do not make repeated wide hydration or 6GB audit
  partitions cheap.
- **Reduce worker batch sizes and intervals** — rejected as a main fix because
  it lowers pressure by doing less work, not by removing the root cause. Small
  batches may be used temporarily during rollout.
- **Keep old Token Radar hydrate as a fallback** — rejected because fallback
  code would keep the same performance failure reachable and would violate the
  no-compatibility hard-cut requirement.
- **Disable OpenNews in config** — rejected as the final fix now that latest
  `main` supports OpenNews. It is acceptable only as an emergency rollback if
  migration `0105` cannot be deployed.
- **Move queues to an external system** — rejected because the project
  architecture is explicitly one PostgreSQL store and the observed defects are
  implementation leaks, not proof that PostgreSQL cannot own this workload.
- **Run `VACUUM FULL` broadly** — rejected as a default fix because it requires
  intrusive locks and does not address ongoing retention/model shape. Table
  rewrite can be part of an operator-approved maintenance command.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Base work on latest local `main`; treat News/OpenNews schema as in scope; remove old runtime paths after replacement; prove changes with PostgreSQL and readiness evidence. |
| Ask first | Dropping or rewriting large existing audit/history partitions; resetting `pg_stat_statements`; changing product scoring semantics; disabling a live provider as rollback. |
| Never | Hide readiness failures by weakening `/readyz`; delete facts to improve metrics; keep compatibility fallback SQL; introduce a second durable execution plane; print secrets from runtime config. |
