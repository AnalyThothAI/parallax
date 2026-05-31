# Spec — Kappa/CQRS Runtime Integrity Hard Cut

**Status**: Implemented locally and merged
**Date**: 2026-05-25
**Owner**: Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/superpowers/plans/active/2026-05-23-token-case-read-path-latency-root-fix-plan-cn.md`
- `docs/superpowers/specs/active/2026-05-24-projection-dirty-target-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-24-okx-ws-and-projection-churn-root-fix-cn.md`

## Background

The project already documents the right architecture: PostgreSQL facts are the
business truth, derived read models are rebuildable, each read model has one
runtime writer, and `NOTIFY` is only a wake hint.

The current implementation has drifted in five places:

1. `commit=False` is used as if it creates an atomic unit, but all pool
   connections are `autocommit=True`.
2. `market_tick_current` is consumed like a derived read model, but is written
   implicitly by every market tick writer through `MarketTickRepository`.
3. Some API read paths call provider adapters directly.
4. Runtime compatibility residue still exists in Token Radar scoring and in
   architecture guard naming.
5. `resolution_refresh` discovers lookup work by scanning recent token facts on
   every interval instead of claiming durable lookup-key work.

Four read-only explorer agents independently confirmed these points on
2026-05-25:

- Transaction chain: `autocommit=True` plus `commit=False` causes half-written
  market tick, event-anchor, Token Radar, and pre-ingest registry state.
- Market chain: `market_tick_current` has no declared owner, no explicit rebuild
  command, and Token Radar still has runtime catch-up scans.
- Read path: Token Case/Search/Social Timeline candle enrichment and
  `/stocks-radar` still call providers from HTTP handlers; WebSocket replay does
  synchronous DB work in an async handler.
- Legacy/guard scan: Token Radar factor scoring still falls back to
  `intent_confidence` / `confidence`; architecture tests miss
  `market_tick_current` ownership and atomic rollback behavior.

## Current Evidence

### Transaction Boundary Drift

`create_pool()` sets `"autocommit": True` in
`src/parallax/platform/db/postgres_client.py:59`, while
`DBPoolBundle.worker_session()` yields repositories without entering
`conn.transaction()` in
`src/parallax/app/runtime/db_pool_bundle.py:121`.

That means repository calls such as `commit=False` skip explicit `commit()`, but
the SQL statement has already committed unless the caller is inside
`RepositorySession.unit_of_work()`.

Known affected chains:

- Market tick workers insert `market_ticks` / `market_tick_current`, then enqueue
  Token Radar dirty targets as a later statement in
  `market_tick_stream_worker.py:192` and `market_tick_poll_worker.py:251`.
- `EventAnchorBackfillWorker._persist()` inserts ticks, attaches
  `enriched_events`, marks jobs, then enqueues dirty targets in
  `event_anchor_backfill_worker.py:330`.
- `TokenRadarProjection` leases dirty targets, writes target features, publishes
  rank rows, writes audit/history, advances offsets, and marks queue state across
  many autocommitted statements.
- `IngestService.commit_prepared_event()` is transactional, but
  `prepare_registry_for_resolution()` runs before it and writes
  `registry_assets` in `ingest_service.py:103` and `bootstrap.py:250`.

### Market Current Ownership Drift

`market_tick_current` is created as a latest-per-target mutable table in
`20260523_0090_token_radar_postgres_hard_cut.py:188`. It is upserted inside
`MarketTickRepository._insert_tick_returning_id()` at
`market_tick_repository.py:120`, from the same CTE that inserts `market_ticks`.

The table is not listed as a fact in `docs/ARCHITECTURE.md:61`, is not covered by
`SINGLE_WRITER_READ_MODELS` in
`tests/architecture/test_worker_runtime_contracts.py:202`, and has no explicit
rebuild command from append-only `market_ticks`.

Token Radar reads it as the latest market source in
`token_radar_target_feature_query.py:265`, so stale or partially missing
`market_tick_current` is product-visible.

### Read Path Provider IO

`routes_search.py:253` constructs `MarketCandlesService` from runtime providers.
`MarketCandlesService` calls `cex_market.candles(...)` at
`market_candles_service.py:31` and `dex_candle_market.token_candles(...)` at
`market_candles_service.py:50`.

`routes_radar.py:51` constructs `StocksRadarService` with
`runtime.stock_quote_provider`; `stocks_radar_service.py:89` calls
`quote_provider.quote(...)` from the request path.

These are CQRS read surfaces. They must read persisted facts/read models only.

### Resolution Refresh Runtime Scan

`ResolutionRefreshWorker._run_refresh_once()` computes a recent window and calls
`repos.discovery.due_lookup_keys(...)` at `resolution_refresh_worker.py:76`.
When the max configured Token Radar window is `24h`, the due query scans a 24h
slice of token facts.

`DiscoveryRepository.due_lookup_keys()` discovers work by joining
`token_intent_lookup_keys`, `token_intents`, `events`, and
`token_intent_resolutions` at `discovery_repository.py:28`. This is not business
truth; it is runtime insurance against missed lookup enqueue. It has the same
architectural problem as Token Radar catch-up: normal worker loops repeatedly
scan facts to prove there is no missed derived work.

The write side then starts a lookup, calls the provider, persists discovery
results and identity facts, reprocesses recent intents for the lookup key, and
enqueues Token Radar dirty targets. Those writes are mostly idempotent, but they
still create periodic write amplification when nothing materially changed.

### WebSocket Blocking And Backpressure Drift

`PublicWebSocketHub._handle_client_message()` is async but calls synchronous
`_replay_events()` directly at `ws.py:111`. `_replay_events()` opens a repository
session and then does N+1 payload reads at `ws.py:115` and `ws.py:168`.

`PublicWebSocketHub.publish()` awaits each client `send_text()` sequentially at
`ws.py:44`. A slow client can delay worker publication for all clients.

### Compatibility Residue

`token_radar_feature_builder.py:324` documents
`intent_confidence` as a legacy numeric shadow, and line 330 falls back to
`row.get("intent_confidence") or row.get("confidence")`.

The hard-cut architecture scan currently fails on non-runtime test helper names
containing `price_observations`, and it still does not guard transaction
atomicity or provider-free read models.

## Problem

The service can pass many architecture tests while still violating the deeper
Kappa/CQRS runtime contract:

- A fact and the control row that wakes its projection can commit separately.
- A derived read model can be hidden inside a fact repository instead of owning
  its projection and rebuild path.
- Read endpoints can block on provider IO.
- Fallback fields can silently preserve old scoring semantics.

This creates correctness gaps, backlog amplification, and ambiguous ownership.

## First Principles

1. **Facts are the only business truth.** `market_ticks`, `events`,
   `token_intents`, `token_intent_resolutions`, `enriched_events`, and other
   fact tables must be enough to rebuild every derived product view.
2. **Transactions are use-case boundaries.** Repositories execute SQL; services
   and workers own atomic units. `commit=False` is not a correctness primitive.
3. **Current tables are read models unless explicitly documented otherwise.**
   A latest-row table derived from append-only facts must have one owner and a
   rebuild command.
4. **Read surfaces are provider-free.** HTTP, WebSocket replay, and CLI read
   commands can read DB and process-local cache, but cannot call provider
   adapters.
5. **Wake is a hint.** Correctness requires durable dirty targets or durable
   scheduled work. A missed `NOTIFY` cannot be the reason a projection stalls.
6. **No compatibility code.** Hard cuts delete old runtime behavior. Missing
   new facts produce explicit unavailable/data-health states, not old-field
   fallback.

## Goals

- G1. All multi-table write use cases enter an explicit transaction boundary,
  and tests prove rollback on injected failures.
- G2. Repository-level `commit` flags stop being used as atomicity semantics in
  runtime write paths.
- G3. Market tick writers append only `market_ticks` plus durable
  `market_tick_current_dirty_targets` in the same transaction.
- G4. `market_tick_current` becomes an explicit rebuildable read model with one
  runtime writer: `MarketTickCurrentProjectionWorker`.
- G5. Token Radar market dirtiness is produced by the market current projection
  owner when the visible latest tick changes.
- G6. Token Radar runtime workers claim durable dirty targets only; broad
  catch-up scans move to explicit ops repair commands.
- G7. API read services and WebSocket replay do not call providers.
- G8. WebSocket publication has a bounded per-client backpressure policy.
- G9. Token Radar removes `intent_confidence` / `confidence` fallback scoring.
- G10. `resolution_refresh` claims durable lookup-key dirty targets only; broad
  fact scans move to explicit ops repair commands.
- G11. Resolution refresh lookup result persistence, identity writes, intent
  reprocess, and Token Radar dirty enqueue run in explicit transaction units.
- G12. Architecture tests cover transaction atomicity expectations,
  `market_tick_current` ownership/rebuildability, provider-free read paths, and
  no runtime compatibility fallback.

## Non-goals

- N1. Do not change Token Radar scoring formulas except removing legacy fallback
  inputs and making missing status explicit.
- N2. Do not add a dual-write or dual-read compatibility period.
- N3. Do not preserve old runtime catch-up scans behind config.
- N4. Do not add a provider fallback in API routes to keep candles or quotes
  "fresh".
- N5. Do not make `NOTIFY` durable delivery. Durable state remains PostgreSQL
  rows.
- N6. Do not redesign Equity/News dirty-target hard cuts here. This spec borrows
  the same principle but focuses on Token/Asset/Runtime integrity.

## Target Architecture

### Transaction Ownership

`DBPoolBundle` exposes explicit write boundaries:

```text
worker_session(name)       -> read or single-statement use
worker_transaction(name)   -> multi-table write use case
api_session()              -> synchronous HTTP DB reads
api_transaction(name)      -> rare API writes such as notification ack
```

Runtime write services use `worker_transaction()` for:

- event ingest commit bundle
- market tick append plus current-dirty enqueue
- event-anchor backfill outcome persistence
- Token Radar feature/publish/queue state
- read-model projection publish units

Repositories no longer decide transaction scope. Existing `commit` parameters
are removed from hot paths or ignored only after all callers are migrated; no
new repository method accepts `commit`.

### Market Tick Current Projection

`market_ticks` remains append-only fact storage. Market tick writers do not
upsert `market_tick_current`.

```text
MarketTickStreamWorker / MarketTickPollWorker / IngestService / EventAnchorBackfillWorker
  -> worker_transaction
  -> INSERT market_ticks
  -> UPSERT market_tick_current_dirty_targets(target_type, target_id, source_watermark_ms)
  -> COMMIT
  -> NOTIFY market_tick_written

MarketTickCurrentProjectionWorker
  -> claim market_tick_current_dirty_targets
  -> SELECT latest tick for each target from market_ticks
  -> UPSERT market_tick_current only if visible current changed
  -> enqueue token_radar_dirty_targets for changed market targets
  -> COMMIT
  -> NOTIFY token_radar_updated
```

`market_tick_current` has an ops rebuild command:

```bash
uv run parallax ops rebuild-market-tick-current --dry-run
uv run parallax ops rebuild-market-tick-current --execute
```

The rebuild truncates and derives the table from `market_ticks` using stable
ordering:

```text
observed_at_ms DESC, received_at_ms DESC, tick_id DESC
```

### Token Radar Dirty Target Runtime

Token Radar workers claim `token_radar_dirty_targets` and do not scan facts in
normal runtime when the queue is empty. Coverage repair becomes explicit ops:

```bash
uv run parallax ops enqueue-token-radar-dirty-targets --source events --since-ms ...
uv run parallax ops enqueue-token-radar-dirty-targets --source market-current --since-ms ...
```

Projection publication runs inside explicit transactions. Queue mark-done and
visible read-model mutation cannot split.

Batching is allowed and preferred: claims for the same `(window, scope)` can be
loaded with a `VALUES` target set instead of one query per target/window.

### Resolution Refresh Dirty Queue

`resolution_refresh` moves from runtime fact scans to a durable lookup-key queue:

```text
IngestService / TokenIntentResolver / repair ops
  -> enqueue token_resolution_refresh_dirty_targets(provider, lookup_key, lookup_type)

ResolutionRefreshWorker
  -> claim due lookup keys
  -> start lookup attempt
  -> release DB connection
  -> call provider
  -> worker_transaction
      -> finish lookup result
      -> persist registry_assets / asset_identity_evidence / asset_identity_current
      -> reprocess intents for claimed lookup keys only
      -> enqueue token_radar_dirty_targets for changed targets
      -> mark lookup dirty target done or retry
  -> notify resolution_updated only after commit
```

Queue producers:

- token intent lookup-key creation enqueues lookup targets when the current
  resolution is missing, `NIL`, or `AMBIGUOUS`;
- any resolution replacement to `NIL` or `AMBIGUOUS` enqueues the affected lookup
  key;
- provider-result changes re-enqueue affected lookup keys for reprocess inside
  the same transaction;
- explicit ops repair can enqueue lookup keys from recent facts during rollout or
  maintenance.

Normal runtime never calls `DiscoveryRepository.due_lookup_keys()` or an
equivalent `events + token_intents + token_intent_lookup_keys +
token_intent_resolutions` scan. That discovery path is deleted from runtime or
moved behind an ops-only repair command.

### Provider-Free Read Surfaces

Token Case, Search Inspect, Target Social Timeline, and Stocks Radar read from
persisted facts/read models only.

Market candle display uses one of:

- local bucketing from persisted `market_ticks`, or
- a worker-owned persisted candle snapshot read model.

Stock quote display uses worker-owned persisted quote snapshots. If no snapshot
exists, the response returns an explicit unavailable state from DB, not a
request-time provider call.

### WebSocket Replay And Publication

Subscribe replay is a bounded DB read that does not block the event loop. The
implementation can use a sync helper in `asyncio.to_thread` or a future async DB
repository, but it cannot run synchronous DB loops directly in the async handler.

Replay payloads are batched by event ids to avoid per-event repository reads.

Live publication enqueues into a bounded per-client outbound queue. Each client
has one writer task. Slow clients are closed or have non-critical messages
dropped according to a documented policy. Worker publish calls return after
enqueueing; they do not await client network writes.

### Hard-Cut Guard Rails

Architecture tests enforce:

- no provider adapters under API/read-model paths
- no `intent_confidence` / `confidence` scoring fallback
- no runtime `getattr(..., None)` skip for required dirty-target repositories
- `market_tick_current` has exactly one runtime writer
- `market_tick_current` has a rebuild command from `market_ticks`
- projection workers do not call runtime broad catch-up scans
- `resolution_refresh` does not call runtime broad lookup-key discovery scans
- transaction rollback tests exist for market tick, event-anchor, ingest, and
  Token Radar publish chains

## Acceptance Criteria

- AC1. Injecting an exception after tick insert but before dirty enqueue leaves
  no committed partial market current work.
- AC2. Injecting an exception during event-anchor backfill persistence leaves
  no split tick/enriched/job/dirty state.
- AC3. Ingest pre-resolution registry writes do not commit before the event
  transaction, or the pre-resolution step is read-only.
- AC4. `MarketTickRepository` no longer writes `market_tick_current`.
- AC5. `MarketTickCurrentProjectionWorker` is the only runtime writer of
  `market_tick_current`.
- AC6. `ops rebuild-market-tick-current --execute` recreates the same current
  rows from `market_ticks`.
- AC7. Token Radar worker with empty dirty queue returns `claimed=0` and does
  not call event/resolution broad catch-up scans.
- AC8. Token Radar publish cannot expose current rows without matching
  rank/audit/coverage/dirty-target state.
- AC9. `/api/token-case`, `/api/search/inspect`, `/api/target-social-timeline`,
  and `/api/stocks-radar` pass poison-provider tests.
- AC10. WebSocket subscribe replay does not block the event loop and does not
  perform N+1 repository calls per event.
- AC11. A slow WebSocket client does not block publication to other clients.
- AC12. `token_radar_feature_builder` no longer reads `intent_confidence` or
  `confidence`.
- AC13. `resolution_refresh` with an empty lookup-key dirty queue returns
  `claimed=0` and does not scan `events`, `token_intents`,
  `token_intent_lookup_keys`, or `token_intent_resolutions`.
- AC14. When an intent is written with a symbol/address lookup key and unresolved
  or ambiguous resolution state, the same transaction enqueues
  `token_resolution_refresh_dirty_targets`.
- AC15. When resolution refresh provider results change candidates, lookup
  result persistence, identity writes, intent reprocess, and Token Radar dirty
  enqueue commit atomically.
- AC16. The hard-cut architecture test suite is green, including the old
  `price_observations` string scan after test helper renames.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Moving `market_tick_current` to a projection adds latency | High | Wake current projection immediately on tick commits; keep interval catch-up tight; expose queue depth and lag |
| Missing current-dirty enqueue causes stale latest market | High | Transaction fault tests plus ops repair command from `market_ticks` |
| Removing Token Radar runtime scans misses old unqueued rows | Medium | One-shot repair enqueue command during rollout; no hot-path fallback |
| Removing resolution refresh runtime scans misses old unqueued lookup keys | Medium | One-shot lookup repair enqueue command during rollout; enqueue tests on intent/resolution writes |
| Provider-free API loses candle/quote freshness until workers catch up | Medium | Return explicit persisted snapshot freshness/unavailable fields |
| Transaction refactor touches many hot paths | High | Slice by use case with failure-injection tests before implementation |
| WS queues can drop useful messages | Medium | Drop only replaceable live updates; close clients for reliable replay/event channels |

## Rollout

This is a hard cut. Rollout order:

1. Land tests and transaction primitives.
2. Migrate market tick persistence and current projection.
3. Rebuild `market_tick_current` from facts.
4. Enqueue Token Radar dirty targets from market current and recent events.
5. Remove runtime scans/fallbacks.
6. Remove request-time providers.
7. Verify live config with `uv run parallax config`; report paths only,
   no secrets.

Rollback is previous app revision plus database restore or a forward repair
command. Do not add runtime compatibility branches.

## Implementation Result

Implemented on branch `codex/kappa-cqrs-runtime-integrity-hard-cut` and merged
to `main` on 2026-05-25.

The shipped hard cut removes runtime broad catch-up scans from Token Radar,
moves resolution refresh to durable lookup-key dirty targets, cuts
provider-backed API/read paths, bounds WebSocket fan-out, and gives wake
listeners a dedicated executor with worker lifecycle cleanup. Architecture tests
now guard those contracts.
