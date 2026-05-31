# Backend Architecture Audit - 2026-05-16

> Scope: backend architecture, workers, data flow, PostgreSQL model, SQL hot paths, and maturity gaps.
> Method: static code review against current repository state, migrations, architecture docs, worker runtime, repositories, and active backend specs. I did not run production `EXPLAIN ANALYZE` against a loaded database in this audit, so query severity is based on code shape, indexes present in migrations, and expected cardinality.

## Executive Summary

The backend is no longer a toy service. It has a real Kappa/CQRS spine: facts are in PostgreSQL, workers are explicit `WorkerBase` classes, providers are wired through runtime composition, and the new `market_ticks`/`enriched_events` path is a much cleaner model than the older token/price snapshot stack.

The serious issue is that the repository currently has two overlapping asset/market realities:

1. The documented production path says business truth is `events`, `token_intents`, `token_intent_resolutions`, `registry_assets`, `asset_identity_*`, `market_ticks`, and `enriched_events`.
2. Live runtime code still exposes and uses the legacy `assets`, `asset_aliases`, `asset_venues`, and `asset_market_snapshots` repositories for closed-loop harness materialization and settlement.

That makes the architecture docs directionally right but materially overconfident. The current docs state "no runtime compatibility layer" and "every other persisted table is a rebuildable read model"; the code still has legacy asset identity and market snapshot writes in the runtime path. This is the biggest backend architecture risk because it can silently split scoring, harness, and settlement from the newer market fact pipeline.

The second major risk is throughput. Token Radar, capture tier selection, market tick ingestion, and watchlist overview queries are mostly batch/rebuild shaped. That is acceptable at small scale, but several hot paths do repeated lateral lookups, full-window scans, unbounded per-handle scans, row-by-row inserts, and duplicate wake emission. These will become the first scaling cliffs.

The backend is close to a mature event-driven architecture in naming and intent. It is not yet mature in enforcement, query planning discipline, retention/partitioning, single-writer coverage, backlog control, and operational replay tooling.

## Top Findings

### P0 - The Documented Fact Model Does Not Match Live Harness Runtime

`docs/ARCHITECTURE.md` declares the business fact tables as `events`, `event_entities`, `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current`, `market_ticks`, and `enriched_events`. It also says no runtime compatibility layer remains.

Current code contradicts that:

- `RepositorySession` still exposes `assets=AssetRepository(conn)` and `market=MarketRepository(conn)` in every app/worker session.
- `runtime.bootstrap()` still exposes a pooled `AssetRepository`.
- `EnrichmentWorker` calls `HarnessSnapshotBuilder(repos.harness, assets=repos.assets)` after LLM enrichment.
- `HarnessSnapshotBuilder` resolves candidates through `assets.upsert_dex_asset(...)`, `assets.candidates_for_symbol(...)`, and checks market readiness through `assets.market_snapshot_at_or_before(...)`.
- `HarnessOpsWorker` settles snapshots through `assets.market_snapshot_at_or_before(...)`.
- `AssetRepository` writes `assets` and `asset_market_snapshots`, and its market snapshot upsert uses `ON CONFLICT DO UPDATE`, unlike append-only `market_ticks`.

Impact:

- The `closed_loop_harness` can be detached from the new `market_ticks` truth. If no writer keeps `asset_market_snapshots` current, harness seeds stay `market_unavailable` or settle against stale data.
- The same token may have identity in both `registry_assets`/`asset_identity_current` and legacy `assets`/`asset_aliases`, with different lifecycle and confidence semantics.
- The docs tell agents to trust the new fact set, but runtime still mutates a legacy fact set. This is exactly the kind of hidden compatibility layer the docs forbid.

Recommended fix:

- Choose one of two explicit paths:
  - Preferred: migrate closed-loop harness to `registry_assets` + `market_ticks`, then retire `AssetRepository` from runtime sessions.
  - Transitional: document `assets`/`asset_market_snapshots` as a named legacy subsystem with a single owner and a migration deadline. Do not pretend it is gone.
- Add an architecture test that fails if runtime code outside an allowlist references `AssetRepository`, `assets`, `asset_market_snapshots`, or `market_snapshot_at_or_before`.

Evidence:

- `docs/ARCHITECTURE.md:32-68`
- `src/parallax/app/runtime/repository_session.py:42-105`
- `src/parallax/app/runtime/bootstrap.py:161-168`
- `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py:180-207`
- `src/parallax/domains/closed_loop_harness/services/harness_snapshot_builder.py:88-100`
- `src/parallax/domains/closed_loop_harness/services/harness_snapshot_builder.py:215-225`
- `src/parallax/domains/closed_loop_harness/services/harness_snapshot_builder.py:321-346`
- `src/parallax/domains/closed_loop_harness/services/harness_snapshot_builder.py:368-373`
- `src/parallax/domains/closed_loop_harness/services/harness_ops.py:57-128`
- `src/parallax/domains/asset_market/repositories/asset_repository.py:340-380`
- `src/parallax/domains/asset_market/repositories/asset_repository.py:382-451`
- `src/parallax/domains/asset_market/repositories/asset_repository.py:466-497`

### P1 - Price Pipeline Throughput Is Architecturally Correct But Execution Is Backlog-Prone

The current capture architecture is clean on paper:

- Tier 1: `MarketTickStreamWorker` writes WebSocket ticks.
- Tier 2: `MarketTickPollWorker` writes REST quote ticks.
- Tier 3: ingest inline capture writes event-anchored ticks and `enriched_events`.
- `LivePriceGateway` is cache/fan-out only.
- `TokenRadarProjectionWorker` consumes `market_ticks` and `enriched_events`.

But the implementation has several choke points:

- `MarketTickRepository.insert_ticks()` inserts row by row and returns attempted count, not actual inserted count.
- Stream and poll workers emit `market_tick_written` for every materialized tick, including duplicates that hit `ON CONFLICT DO NOTHING`.
- `TokenCaptureTierWorker` upserts hot rows but has no stale demotion/pruning path.
- `token_capture_tier` has only a primary key on `(target_type, target_id)`; workers filter by `tier` and then run a lateral latest tick lookup per row.
- `TokenRadarProjectionWorker` repeatedly rebuilds windows and pulls large source windows through Python grouping.

Impact:

- Duplicate provider frames can create wake amplification without new facts.
- Stale tier rows can keep old targets in stream/poll lanes indefinitely.
- Capture workers spend work on targets that should no longer be hot.
- Token Radar gets woken more often than necessary and then does a relatively heavy full-window scan.

Recommended fix:

- Make market tick insert return actual inserted tick IDs or row count.
- Emit wakes only for inserted ticks, ideally coalesced per `(target_type, target_id)` per worker cycle.
- Add stale demotion/pruning to `token_capture_tier`.
- Add `token_capture_tier(tier, score DESC, updated_at_ms DESC, target_type, target_id)` or a better worker-specific index.
- Split Tier 1 and Tier 2 target queues by provider capability, especially DEX WS vs CEX REST.

Evidence:

- `src/parallax/domains/asset_market/repositories/market_tick_repository.py:28-103`
- `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py:142-156`
- `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py:213-222`
- `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:68-96`
- `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:55-96`
- `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py:61-90`

### P1 - Token Radar Projection Is Full-Window Rebuild, Not Incremental

`TokenRadarProjection.rebuild()` does this per window/scope:

1. Mark coverage as running.
2. Read all source rows from an analysis window.
3. Group rows in Python.
4. Build factor snapshots.
5. Apply cross-section ranking.
6. Delete same computed set and insert rows one by one.

`TokenRadarSourceQuery.source_rows()` materializes a window of events, joins token intents/resolutions, and then runs repeated lateral lookups into `market_ticks`:

- latest tick for each row target
- first tick for each row target
- event capture row for each event/intent/resolution

This is simple and rebuildable, but it is not a scalable projection design once event/intention cardinality rises. The latest/first tick lookups are especially wasteful when many event rows map to the same target: the same latest tick is re-probed for each source row.

Impact:

- Every wake can trigger work proportional to source window size, not proportional to changed targets.
- Market tick cardinality growth makes repeated lateral index probes increasingly expensive.
- The worker can become the dominant database load and delay Pulse.

Recommended fix:

- First optimization: build a `distinct_market_targets` CTE from source rows, fetch latest/first ticks once per target, then join back.
- Add a global index for max observed lookup if keeping `MAX(observed_at_ms)` health checks: `market_ticks(observed_at_ms DESC)`.
- Consider incremental dirty ranges keyed by target and time bucket, then rebuild only affected targets/windows.
- Use batch insert for `token_radar_rows`; row-by-row writes are fine at 100 rows but brittle if limits increase.
- Add an architecture/perf test that asserts projection source query uses target-level tick lookup instead of per-row lateral lookups.

Evidence:

- `src/parallax/domains/token_intel/services/token_radar_projection.py:56-191`
- `src/parallax/domains/token_intel/queries/token_radar_source_query.py:22-36`
- `src/parallax/domains/token_intel/queries/token_radar_source_query.py:123-231`
- `src/parallax/domains/token_intel/queries/token_radar_source_query.py:261-270`
- `src/parallax/domains/token_intel/repositories/token_radar_repository.py:19-93`

### P1 - Watchlist Overview APIs Have Unbounded History Scans

`timeline()` is mostly bounded by limit and cursor, but `handle_overview()` loads all events for a handle since a caller-provided timestamp and then performs token resolution fanout for every loaded event. The `limit` parameter only limits cluster output after all matching events have been fetched.

`handles_overview()` joins configured handles to all historical events for each handle, then computes recent and total counts in one grouped query. For a small watchlist this is tolerable; for a mature service with long retention and high-volume handles, it grows linearly with event history.

`handles_missing_summary_jobs()` has a correlated count subquery for each candidate handle.

Impact:

- API latency becomes a function of historical event volume, not requested page size.
- Token resolution projection can fan out over hundreds or thousands of events in one request.
- Popular handles will dominate API pool time.

Recommended fix:

- Add server-side caps for overview source events or require bounded windows.
- Persist per-handle metrics/read models: latest event, recent count, recent signal count, total signal count.
- Move cluster building to a bounded query or a materialized summary table.
- Add integration tests with synthetic high-volume handles and assert query count/latency shape.

Evidence:

- `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py:383-445`
- `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py:447-481`
- `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py:483-556`
- `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py:558-599`

### P2 - Worker Timeout Handling Does Not Cancel Timed-Out Work

`WorkerBase._run_once_with_timeout()` wraps the worker task in `asyncio.shield()` and `asyncio.wait_for(...)`. On timeout it raises `TimeoutError` but leaves the underlying `run_once` task alive. The outer loop keeps the task reference and will eventually await the same task again, so it avoids duplicate overlapping iterations for that worker. Still, the timed-out task can continue holding DB connections or provider resources after the worker reports failure/backoff.

Impact:

- A timed-out DB query can remain in-flight until database-side `statement_timeout`.
- A stuck provider call in a thread can keep consuming resources.
- Worker status can say failed while previous work is still alive.

Recommended fix:

- Decide if timeout is a hard cancellation or a soft overrun marker.
- If hard: remove `shield`, cancel the task, and make DB/provider calls cancellation-aware where possible.
- If soft: report it explicitly as `overrun` rather than failure, and expose in-flight duration/resource state.

Evidence:

- `src/parallax/app/runtime/worker_base.py:90-131`
- `src/parallax/app/runtime/worker_base.py:177-205`

### P2 - Advisory Locks Consume Worker Pool Connections For Worker Lifetime

Single-writer workers use `WorkerBase.SINGLE_WRITER_KEY`. `WorkerBase` acquires an advisory lock by calling `DBPoolBundle.acquire_advisory_lock_connection(...)`, which checks out a worker-pool connection and keeps it until worker close.

This is a valid pattern, but it means each locked worker permanently reduces `worker_pool` capacity. Today at least `token_capture_tier`, `token_radar_projection`, and `pulse_candidate` use single-writer locks.

Impact:

- With small `postgres_pool_max_size`, the pool can be starved by advisory-lock holders before doing actual worker sessions.
- Pool pressure looks like slow workers, but the real cause is lock-holder connections.

Recommended fix:

- Document pool sizing as `worker_pool >= locked_workers + concurrent_worker_sessions + margin`.
- Consider moving advisory locks to a tiny dedicated lock pool or using transaction-scoped locks around mutation sections where possible.

Evidence:

- `src/parallax/app/runtime/db_pool_bundle.py:31-64`
- `src/parallax/app/runtime/db_pool_bundle.py:124-136`
- `src/parallax/app/runtime/db_pool_bundle.py:160-188`
- `src/parallax/app/runtime/worker_base.py:236-259`
- `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:19-24`
- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:56-62`

### P2 - Single-Writer Contract Is Documented More Broadly Than It Is Tested

The architecture docs declare one writer per read model:

- `token_radar_rows` by `TokenRadarProjectionWorker`
- `token_capture_tier` by `TokenCaptureTierWorker`
- `pulse_candidates`, `pulse_agent_runs`, `pulse_agent_run_steps` by `PulseCandidateWorker`

The architecture test currently enforces the worker registry and DB-session constraints, but its explicit SQL write allowlist covers only `token_radar_rows`.

Impact:

- Future contributors can accidentally add a second writer for `pulse_candidates` or `token_capture_tier` without tripping the same architecture test.
- The most important invariant is not uniformly enforced.

Recommended fix:

- Expand `test_read_model_single_writers()` to include `token_capture_tier`, `pulse_candidates`, `pulse_agent_runs`, and `pulse_agent_run_steps`.
- Add an explicit legacy-table runtime ban or allowlist for `assets`/`asset_market_snapshots`.

Evidence:

- `docs/ARCHITECTURE.md:53-59`
- `tests/architecture/test_worker_runtime_contracts.py:273-284`
- `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:21-53`
- `src/parallax/domains/pulse_lab/repositories/pulse_repository.py:48-135`
- `src/parallax/domains/pulse_lab/repositories/pulse_repository.py:153-195`

### P2 - Public Event Token Projection Uses OR In A Lateral Tick Lookup

`EventTokenProjectionQuery.for_events()` falls back from event capture tick to latest tick using a lateral query with an `OR` over asset and CEX target shapes.

Impact:

- The planner may not use the `(target_type, target_id, observed_at_ms)` index as cleanly as it would with precomputed target fields or two separate lateral joins.
- This is likely acceptable for small `event_ids` batches, but it sits on public API / WebSocket replay paths, so it is worth tightening.

Recommended fix:

- Precompute market target type/id in a CTE, then do one simple lateral lookup.
- Or split asset and CEX latest tick lookups into separate lateral branches and coalesce.

Evidence:

- `src/parallax/domains/token_intel/queries/event_token_projection_query.py:21-126`
- `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py:61-78`

### P2 - Notification Signature Dedupe Uses JSON Extraction Without A Matching Index

Signal Pulse notification dedupe queries:

```sql
WHERE rule_id = %s
  AND payload_json->>'notification_signature' = %s
ORDER BY last_seen_at_ms DESC, created_at_ms DESC
LIMIT 1
FOR UPDATE
```

Existing notification indexes cover rule/time, entity/time, author/time, and source, but not `(rule_id, payload_json->>'notification_signature')`.

Impact:

- As notifications grow, duplicate detection can scan all rows for `rule_id='signal_pulse'` and evaluate JSON extraction.
- `FOR UPDATE` can make this worse under concurrent rule evaluation.

Recommended fix:

- Add an expression index:
  `CREATE INDEX ... ON notifications(rule_id, (payload_json->>'notification_signature'), last_seen_at_ms DESC) WHERE rule_id = 'signal_pulse';`

Evidence:

- `src/parallax/domains/notifications/repositories/notification_repository.py:139-162`
- `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:538-547`

### P3 - Architecture Docs Reference Old Test Paths

`docs/ARCHITECTURE.md` says boundaries are enforced by `tests/test_src_domain_architecture.py` and `tests/test_project_structure.py::test_project_uses_domain_package_src_layout`. The actual files live under `tests/architecture/`.

Impact:

- Minor, but it weakens docs-as-router reliability for new agents.

Recommended fix:

- Update the doc references to `tests/architecture/test_src_domain_architecture.py` and `tests/architecture/test_project_structure.py`.

Evidence:

- `docs/ARCHITECTURE.md:5`
- `tests/architecture/test_src_domain_architecture.py`
- `tests/architecture/test_project_structure.py`

## Actual Backend Data Flow

### Ingestion And Identity

Actual flow in code:

1. `CollectorService` receives GMGN public WebSocket frames.
2. `_PooledIngestStore.ingest_event()` prepares an event.
3. It opens a worker DB session and resolves/prepares registry data.
4. It fetches recent `market_ticks` for each market target.
5. It exits the DB session.
6. It calls `EventMarketCaptureService.capture_for_event(...)` outside the DB session.
7. It opens a new DB session and commits the prepared event, resolutions, `market_ticks`, and `enriched_events`.

This is a good improvement over doing provider IO inside a DB transaction. It also means ingestion has a split phase: the duplicate check and prefetch happen before final commit. The code handles normal duplicates, but the design should be documented as split-phase ingestion, not a single monolithic transaction.

Evidence:

- `src/parallax/app/runtime/bootstrap.py:448-492`

### Market Capture

The new market model is conceptually strong:

- `market_ticks` is append-only.
- `enriched_events` joins an event/intent/resolution to an event-time tick or an unavailable capture.
- `market_ticks` has deterministic dedupe on `(target_type, target_id, source_provider, observed_at_ms)`.
- `market_ticks` and `enriched_events` reject `UPDATE` through triggers.

Weaknesses:

- `market_ticks` is not partitioned. It is a high-ingest time-series table and will grow fastest.
- There is no global index on `observed_at_ms DESC`, but code uses `MAX(observed_at_ms)`.
- The dedupe behavior is not surfaced to workers; workers treat attempted inserts as inserted facts.
- `enriched_events` is append-only/no-update, which is clean, but any async backfill from unavailable to available will require an explicit model decision: new row key, narrow trigger exception, or separate backfill table.

Evidence:

- `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py:20-170`
- `src/parallax/domains/asset_market/repositories/market_tick_repository.py:16-103`

### Token Radar

The Token Radar path is coherent:

- It reads facts and projections through `TokenRadarSourceQuery`.
- It writes `token_radar_rows`, `projection_runs`, offsets, evaluations, and coverage.
- It has a single-writer worker and an advisory lock.
- It emits `token_radar_updated` for Pulse.

The issue is cost model: full-window rebuild + repeated lateral market lookups + Python grouping. This should be treated as a correctness-first v1 implementation that now needs an incremental v2.

### Pulse Lab

Pulse is one of the better modeled domains:

- It has jobs, runs, run steps, candidates, edge state, and budgets.
- It has an advisory single-writer worker.
- It writes audit rows around provider calls.
- It uses wake plus interval catch-up.

Risks:

- Single-writer enforcement is mostly by convention/advisory lock, not broad architecture test coverage.
- Job claim indexes exist and look reasonable, but there is no shared job queue abstraction across all domains. Enrichment, Pulse, watchlist summaries, and notifications each implement their own lease/claim semantics.

Evidence:

- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:115-199`
- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:204-235`
- `src/parallax/domains/pulse_lab/repositories/pulse_repository.py:22-195`
- `src/parallax/platform/db/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py:13-203`
- `src/parallax/platform/db/alembic/versions/20260514_0041_pulse_worker_edge_notifications_hard_cut.py:13-168`

### Closed-Loop Harness

This is the most inconsistent domain relative to the new architecture. It still resolves candidates and market readiness through legacy `AssetRepository` and `asset_market_snapshots`, not through `registry_assets`, `asset_identity_current`, and `market_ticks`.

This makes the harness a parallel subsystem rather than a downstream consumer of the documented fact model.

## Worker Audit

| Worker | Current state | Main risk | Doc accuracy |
|---|---|---|---|
| `collector` | Uses split-phase ingest, provider capture outside DB session, final commit writes facts | Inline provider capture can still block collector path; split transaction needs explicit doc | Mostly accurate, missing split-phase nuance |
| `token_capture_tier` | Single-writer advisory lock; writes hot target tiers | No stale demotion; tier query lacks tier index; CEX/DEX capability split not encoded strongly enough | Directionally accurate |
| `market_tick_stream` | Writes tier1 ticks from DEX stream provider | Rebuild/reconnect/duplicate wake risks; no advisory lock if multi-process | Directionally accurate |
| `market_tick_poll` | Writes tier2 REST ticks | Serial/limited batch shape; duplicate wakes; stale tier rows | Directionally accurate |
| `live_price_gateway` | Intended fan-out/cache only | Must remain read-only; if it opens provider streams separately, ownership gets muddy | Docs state the right invariant |
| `resolution_refresh` | Refreshes unresolved/ambiguous lookup keys and emits wake | Potential provider/API backlog, but conceptually okay | Accurate from reviewed wiring |
| `asset_profile_refresh` | Polls resolved assets for GMGN profiles | Query scans current resolutions/events/radar assets; can become heavy | Accurate |
| `token_radar_projection` | Full rebuild per window/scope; advisory lock; wake in/out | Full-window rebuild cost; repeated market tick lateral lookups; row-by-row writes | Accurate but underplays performance cost |
| `pulse_candidate` | Edge-driven scan + job processing; advisory lock; audit ledger | Single-writer test coverage incomplete; depends on Token Radar freshness | Accurate |
| `enrichment` | Claims jobs, calls LLM, materializes harness | Writes into legacy harness/asset path after enrichment | Docs understate legacy coupling |
| `handle_summary` | Leased job worker with LLM provider | Overview/job queries can scan too much history | Accurate |
| `harness_ops` | Materializes/settles closed-loop snapshots | Reads legacy market snapshots, not `market_ticks` | Misleading: "market facts" is ambiguous/wrong |
| `notification_rule` | Evaluates rules and creates notifications | JSON signature dedupe lacks expression index | Mostly accurate |
| `notification_delivery` | Claims deliveries | Looks conventional | Accurate |

## Database Model Review

### Strong Parts

- The deterministic registry direction is good: `registry_assets`, `cex_tokens`, `price_feeds`, `registry_aliases`, `asset_identity_evidence`, and `asset_identity_current` separate identity evidence from current identity.
- `market_ticks` is a better market fact table than the old price-observation path because target shape and provider tier are explicit.
- `enriched_events` is a useful event-token-market projection. It prevents public payloads from reconstructing event market context ad hoc.
- `pulse_agent_runs` and `pulse_agent_run_steps` provide a replayable agent audit ledger.
- API and worker pools are separated, and wake has a dedicated pool.
- Architecture tests enforce domain boundaries, raw SQL ownership, public event projection shape, and worker inventory.

### Weak Parts

1. Legacy and new asset-market models coexist without a clear boundary.
   - New: `registry_assets`, `asset_identity_*`, `market_ticks`, `enriched_events`.
   - Old/live: `assets`, `asset_aliases`, `asset_venues`, `asset_market_snapshots`.

2. Time-series tables are not partitioned.
   - `market_ticks`, `events`, and model/audit run tables will grow continuously.
   - Mature systems would usually partition or apply retention/rollup policies.

3. Read models have history without retention policy.
   - `token_radar_rows` stores every computed set. That is useful for debugging/listed-at history, but it needs retention or compaction.

4. Some high-cardinality JSON queries lack expression indexes.
   - Notification signature dedupe is the clearest example.

5. Some fields/tables appear to be historical leftovers.
   - `current_market_field_facts` and `token_market_price_baselines` are created by older migrations and have no runtime references outside migrations in current code. If still present in live DB, they should be classified as retired/legacy or dropped in a hard-cut migration.

6. Job queue semantics are duplicated.
   - Pulse, enrichment, watchlist summary, and notification delivery each have custom claim/retry/dead-letter behavior. That is manageable now but will become hard to audit.

## SQL Hot Path Review

### Token Radar Source Query

Risk level: high.

Why:

- Scans a materialized event window.
- Joins all token intents/resolutions in the window.
- Performs latest/first market tick lateral lookups per source row.
- Uses `MAX(decision_time_ms)` and `MAX(observed_at_ms)` health queries without obviously matching global descending indexes.

Recommended SQL shape:

- Stage source rows into a CTE with `market_target_type` and `market_target_id`.
- Build `distinct_market_targets`.
- Join latest tick once per target.
- Join first tick once per target.
- Join back to source rows.

### Capture Tier List Query

Risk level: medium to high.

Why:

- `WHERE token_capture_tier.tier = %(tier)s` has no tier-specific index in the migration.
- It runs a lateral latest tick lookup per tier row.
- It orders by latest tick completeness/freshness and score.

Recommended:

- Add a tier/score/update index.
- Consider storing a current tick-health summary in a read model if latest tick completeness is part of scheduling priority.

### Watchlist Overview

Risk level: high for popular handles.

Why:

- `handle_overview()` has no SQL `LIMIT`; it loads all rows since `since_ms`.
- It resolves tokens for all loaded events.
- `handles_overview()` scans all events for each configured handle to compute total signal count.

Recommended:

- Persist handle metrics.
- Add source-event caps.
- Keep full cluster overview as an async summary job, not synchronous API work.

### Event Token Projection

Risk level: medium.

Why:

- Public payload query uses a lateral latest tick lookup with an `OR`.
- Small batches likely hide the cost today.

Recommended:

- Precompute target shape and do a single indexed lookup.

### Notification Dedupe

Risk level: medium.

Why:

- JSON expression lookup without expression index.

Recommended:

- Add partial expression index by Signal Pulse rule.

## Documentation Accuracy

### Accurate

- The package/domain map is broadly right.
- Worker inventory keys match runtime registry and settings.
- Wake channels and wake-as-hint semantics are represented accurately for Token Radar/Pulse.
- Provider IO is generally kept outside worker DB sessions.
- `market_ticks` and `enriched_events` append-only contract is represented and tested.
- Public event token projection direction is accurate.

### Inaccurate Or Incomplete

- The docs claim runtime compatibility layers are gone, but legacy `AssetRepository` and `asset_market_snapshots` are live.
- The docs call `market_ticks`/`enriched_events` business truth, but harness settlement still reads `asset_market_snapshots`.
- The docs imply all named single-writer read models are equally enforced; tests only explicitly enforce `token_radar_rows`.
- `docs/ARCHITECTURE.md` references old test paths.
- Worker docs say `harness_ops` reads "market facts"; in practice it reads legacy market snapshots. That phrase should be made precise.

## Gap Versus Mature Projects

### 1. Data Ownership Is Close, But Not Fully Hard-Cut

Mature systems make one fact model canonical and force legacy tables behind explicit migration adapters or retired namespaces. This repo has a strong canonical model but still leaves the old asset-market model in runtime sessions.

Target state:

- One asset identity model.
- One market fact model.
- Explicit derived read models.
- Architecture tests banning retired runtime paths.

### 2. Projection Strategy Is Correctness-First, Not Scale-First

Full-window rebuild is fine early. Mature systems eventually add:

- dirty ranges
- target-level incremental recompute
- rollup buckets
- bounded catch-up
- backpressure and lag SLOs
- per-projection query plan baselines

### 3. Time-Series Storage Needs Lifecycle Management

`events`, `market_ticks`, `token_radar_rows`, agent runs, and notification history all grow without a visible retention/partitioning strategy.

Target state:

- partition `market_ticks` by time
- define retention/compaction for `token_radar_rows`
- archive old model run payloads or split large JSON payload storage
- periodic VACUUM/analyze expectations documented

### 4. Operational Backpressure Is Not Yet First-Class

The worker framework exposes status and p99, but the system still lacks strong global rules for:

- worker lag budgets
- queue depth SLOs
- provider circuit breakers
- wake coalescing
- stale target pruning
- retry/dead-letter consistency

### 5. Query Performance Is Not Continuously Tested

There are architecture tests, but not enough query-plan tests. Mature projects often keep:

- seed high-cardinality fixtures
- `EXPLAIN (FORMAT JSON)` assertions for major paths
- max rows read / max nested loop expectations
- regression budgets for p95 query latency

### 6. Job Queue Semantics Are Fragmented

Pulse, watchlist, enrichment, and delivery each implement claim/retry logic. This works, but every new worker must rediscover the same edge cases.

Target state:

- one shared lease/retry/dead-letter helper
- table-specific repositories use the helper
- tests cover stale running, max attempts, lease token mismatch, and idempotent completion once

## Known Blind Spots And Follow-Up Audit Gaps

This audit should not be treated as complete just because it is long. It intentionally leaves several important backend risk areas unresolved.

1. Agent/LLM systems were not deeply audited.
   `pulse_agent_runs`, enrichment LLM calls, and handle summary were reviewed mostly as worker/storage surfaces. This does not evaluate agent reliability, prompt drift, eval coverage, token/cost budgets, provider capacity, or observability. This is the same class of gap as the known `project_agent_spec_corpus_gaps`: eval, cost, observability, and capacity must be audited as first-class backend risks, not as generic worker details.

2. SQL performance claims are not backed by production `EXPLAIN ANALYZE`.
   The suggested `market_ticks(observed_at_ms DESC)` index and other index recommendations are hypotheses from code shape and migration indexes. Before adding them, run the exact production PostgreSQL queries with representative data and compare planner choices, row counts, buffer reads, and timing. The right answer may be a different composite index, query rewrite, or no new index.

3. Frontend-backend contract boundaries were not audited.
   For example, `watchlist` overview currently treats `limit` as a cluster output limit, not a SQL source-row limit. Changing that behavior may be an API contract change and may require frontend copy, pagination, or UX adjustments. Any backend optimization that changes response shape, ordering, truncation semantics, or freshness expectations needs a contract pass.

4. WebSocket replay and public payload behavior were only partially covered.
   The audit called out `EventTokenProjectionQuery`, but it did not inspect collector restart replay behavior, WebSocket reconnect windows, replay dedupe, live-vs-replay ordering, or client-visible gaps around restart and missed wake periods. Those paths need their own reliability review because they are where "facts are correct" can still become "users saw duplicates or missed events."

5. Resolver dominance thresholds were not audited.
   The audit treats `asset_identity_current` as part of the new canonical truth, but it does not analyze whether the resolver is producing enough high-confidence canonical truth. The known `project_resolver_dominance_gap` issue, including the 5,831 `AMBIGUOUS` / roughly 93.7% "no eligible candidate" failure mode, can be hidden by the dual-identity finding. Any refactor that removes legacy `assets` should also revisit dominance thresholds and resolver eligibility, otherwise the system may become architecturally cleaner while still failing to resolve most useful targets.

## Recommended Roadmap

### Phase 0 - Immediate Docs And Guardrails

1. Update `docs/ARCHITECTURE.md` test paths.
2. Update `docs/WORKERS.md` to state whether `harness_ops` reads `market_ticks` or legacy `asset_market_snapshots`.
3. Add architecture tests for single writers across all declared read models.
4. Add a runtime legacy-table allowlist test. If `AssetRepository` remains, force docs to say why.

### Phase 1 - Resolve The Dual Market Model

1. Implement harness market reads on top of `market_ticks`.
2. Map legacy asset IDs to `registry_assets.asset_id`, or migrate harness snapshot `asset` references to the canonical target model.
3. Stop writing `assets` from `HarnessSnapshotBuilder`.
4. Retire `asset_market_snapshots` runtime reads/writes.

### Phase 2 - Fix Capture Throughput

1. Add stale demotion/pruning to `token_capture_tier`.
2. Add tier index and capability-aware tiering.
3. Make market tick insert return actual inserted rows.
4. Emit coalesced wakes only for inserted facts.
5. Decide if event-anchor backfill needs a new worker and a narrow `enriched_events` update model.

### Phase 3 - Optimize Token Radar

1. Replace per-row latest/first tick lateral lookups with target-level CTEs.
2. Add missing global observed-time index if keeping max observed checks.
3. Batch insert `token_radar_rows`.
4. Add retention for old computed sets.
5. Add query plan tests.

### Phase 4 - Move Expensive API Work To Read Models

1. Persist watchlist handle metrics.
2. Bound synchronous overview query work.
3. Keep deep cluster summaries in `watchlist_handle_summaries`.
4. Add expression index for notification signature dedupe.

### Phase 5 - Mature Operations

1. Define per-worker lag SLOs.
2. Add queue depth and stale-running metrics by worker.
3. Add provider circuit breaker state.
4. Document worker pool sizing with advisory lock holders.
5. Add partition/retention policy for `market_ticks` and high-volume audit tables.

## Suggested Concrete Indexes

These should be validated with `EXPLAIN ANALYZE` before applying to production:

```sql
-- Capture workers filter by tier and schedule by score/freshness.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_capture_tier_tier_score_updated
ON token_capture_tier(tier, score DESC, updated_at_ms DESC, target_type, target_id);

-- Projection health asks for MAX(observed_at_ms).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_ticks_observed_desc
ON market_ticks(observed_at_ms DESC, tick_id DESC);

-- Signal Pulse notification duplicate detection.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_pulse_signature
ON notifications(rule_id, (payload_json->>'notification_signature'), last_seen_at_ms DESC, created_at_ms DESC)
WHERE rule_id = 'signal_pulse';

-- Target timeline / search paths often include resolver policy and current target.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_resolutions_current_policy_target
ON token_intent_resolutions(target_type, target_id, resolver_policy_version, decision_time_ms DESC, resolution_id DESC)
WHERE is_current = true;
```

## Final Verdict

The backend has a strong architectural direction and a lot of the right primitives: canonical workers, domain repositories, separated DB pools, wake hints, append-only market facts, and an agent audit ledger. The biggest gap is not intent; it is enforcement and cleanup.

If this service were assessed like a mature production backend, the top condition for "architecture is actually true" would be: remove or explicitly quarantine the legacy `assets`/`asset_market_snapshots` path. After that, the next condition is to make projection and capture throughput proportional to changed targets rather than full windows and duplicate wakes.

Until those are fixed, the current docs should be read as target architecture plus partial implementation, not a fully accurate description of live backend behavior.
