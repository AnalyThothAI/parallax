# Spec — Kappa/CQRS Worker Root Fix

**Status**: Approved  
**Date**: 2026-06-03  
**Owner**: Qinghuan / Codex  
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/superpowers/specs/completed/2026-05-26-runtime-performance-architecture-root-fix-cn.md`
- `docs/superpowers/specs/completed/2026-05-27-macro-sync-worker-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-06-01-news-intel-kiss-simplification-cn.md`

## Background

Parallax is a Kappa/CQRS system: material facts in PostgreSQL are product truth, derived current read models are rebuildable, and worker `NOTIFY` events are wake hints rather than truth. The project router states that read models must have exactly one runtime writer, stable product/window keys, no run/generation/timestamp identity, and unchanged projections must write zero serving rows (`AGENTS.md:9`). `docs/ARCHITECTURE.md` defines single-writer read model ownership (`docs/ARCHITECTURE.md:120`) and makes current rows rebuildable from facts (`docs/ARCHITECTURE.md:101`). `docs/WORKERS.md` requires workers to claim bounded work first, avoid broad fact scans on idle cycles, keep provider IO outside DB sessions, write zero serving rows for unchanged projections, test concrete provider wrappers, and expose production-grade status (`docs/WORKERS.md:49`, `docs/WORKERS.md:63`, `docs/WORKERS.md:70`, `docs/WORKERS.md:73`, `docs/WORKERS.md:78`, `docs/WORKERS.md:83`).

The runtime inventory is centralized in `WorkerManifest`. The manifest declares `cex_oi_radar_board` as the single writer for `cex_oi_radar_publication_state`, `cex_oi_radar_rows`, and `cex_detail_snapshots`, and declares `cex_detail_snapshots` identity as `(exchange, native_market_id)` (`src/parallax/app/runtime/worker_manifest.py:470`, `src/parallax/app/runtime/worker_manifest.py:496`). The worker factory injects `ctx.providers.asset_market.cex_market` into `CexOiRadarBoardWorker` (`src/parallax/app/runtime/worker_factories/cex_market_intel.py:13`, `src/parallax/app/runtime/worker_factories/cex_market_intel.py:23`). The injected Binance wrapper only exposes `tickers`, `ticker`, `candles`, and `close` (`src/parallax/app/runtime/provider_wiring/binance.py:51`), while the CEX builder calls raw Binance client methods `ticker_24hr`, `premium_index`, and `open_interest_hist` (`src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py:17`, `src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py:27`). The same factory imports `CoinglassClient` directly from a third-party package instead of through a Parallax provider adapter (`src/parallax/app/runtime/worker_factories/cex_market_intel.py:29`).

The CEX board itself has a board-level payload hash gate before it rewrites board rows (`src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:68`, `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:82`). But the worker upserts detail snapshots before that gate (`src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py:136`, `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py:142`), and `CexDetailSnapshotRepository` always updates current rows, including `computed_at_ms`, on conflict (`src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:21`, `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:35`).

`news_item_process` loads candidate `news_items` with `FOR UPDATE SKIP LOCKED` and increments `processing_attempts`, but it does not persist a `processing` status, lease owner, or retry due timestamp (`src/parallax/domains/news_intel/repositories/news_repository.py:1674`, `src/parallax/domains/news_intel/repositories/news_repository.py:1689`). Failed items are marked `process_failed` (`src/parallax/domains/news_intel/repositories/news_repository.py:1923`), and the same loader immediately selects `process_failed` rows again (`src/parallax/domains/news_intel/repositories/news_repository.py:1680`).

`token_capture_tier` is represented as a dirty-target worker. The worker consumes `token_capture_tier_dirty_targets` and returns idle when no claim exists (`src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:69`, `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:87`). The repository exposes `enqueue_global()` (`src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:11`), but current source search found no production caller. Token Radar rank-change side effects enqueue pulse, narrative, and profile work, but not capture tier work (`src/parallax/domains/token_intel/services/token_radar_projection.py:754`).

Token Radar current rows keep a `generation_id`, but the repository compares stable signatures and returns `rows_written=0` when the incoming current set is unchanged (`src/parallax/domains/token_intel/repositories/token_radar_repository.py:176`, `src/parallax/domains/token_intel/repositories/token_radar_repository.py:192`). That is acceptable lifecycle metadata, not identity. The risk is elsewhere: target-scoped rank-source repair populates edges for requested targets without a received-time bound (`src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:743`, `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:794`), while downstream rank source reads are bounded by `analysis_since_ms` and `now_ms` (`src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:386`).

Narrative current read models have unchanged-write drift. `narrative_admissions` conflict updates always rewrite fields including `last_seen_at_ms` and `updated_at_ms` (`src/parallax/domains/narrative_intel/repositories/narrative_repository.py:116`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py:132`). Discussion digest replacement deletes the current digest scope and inserts a new current row (`src/parallax/domains/narrative_intel/repositories/narrative_repository.py:1450`), while the current lookup only treats `status='ready'` rows as reusable current digests (`src/parallax/domains/narrative_intel/repositories/narrative_repository.py:1561`).

Runtime status also has a truthfulness gap. Worker construction pre-populates every manifest worker with `_DisabledWorker` and forces settings `enabled=False` when a concrete factory does not return the worker (`src/parallax/app/runtime/worker_factories/__init__.py:64`, `src/parallax/app/runtime/worker_factories/__init__.py:94`). Scheduler health then skips disabled workers (`src/parallax/app/runtime/worker_scheduler.py:90`). This makes "configured enabled but unavailable because provider/feature dependency is missing" indistinguishable from "intentionally disabled".

`WorkerBase` owns the common worker loop, but `LivePriceGateway` overrides `run()` (`src/parallax/domains/asset_market/runtime/live_price_gateway.py:102`). Architecture tests allowlist that exception (`tests/architecture/test_worker_runtime_contracts.py:254`). `WorkerSpace` and manifest-derived contracts exist, but they are only applied on a small subset of workers, leaving a complex partial abstraction rather than a system-wide runtime contract.

## Problem

The current architecture has the right Kappa/CQRS skeleton, but several hot paths have drifted away from its own invariants. Some workers consume provider objects that do not match their concrete runtime shape, some current read models write serving rows on unchanged input, some control queues have consumers without producers, and some worker status surfaces hide misconfiguration. This creates operational risk and cognitive load: future fixes are likely to add shims, allowlists, and extra worker paths instead of reducing the system to clear facts, bounded control-plane work, single-writer projections, and honest status.

## First principles

1. Facts are business truth; provider raw frames, dirty targets, leases, publication attempts, generation ids, wake notifications, and runtime status are control-plane or lifecycle state. No root fix may promote control-plane state into product identity.
2. Every runtime worker has one reason to exist: ingest facts, advance fact lifecycle, project a current read model, perform an audited agent side effect, fan out a cache, or deliver notifications. A worker that mixes those roles must be split or have responsibilities removed.
3. Current read models are compact and stable. If the product-visible payload for a stable key has not changed, the projection writes zero serving rows.
4. Provider boundaries are explicit. Domain workers consume Parallax provider protocols or domain-specific adapters, never raw third-party clients.
5. Hard-cut beats compatibility. This work removes broken paths, stale schema, obsolete docs, special allowlists, and partial abstractions instead of preserving old and new runtime behavior side by side.
6. Business continuity is protected by preserving material facts, public surface semantics, and rebuildability. Derived read models and control-plane queues may be dropped, rebuilt, or re-enqueued when the hard cut requires it.

## Goals

- G1. Real runtime provider wiring and unit tests use the same provider protocol shape for every worker that performs provider IO.
- G2. Every current read model writer has a payload-hash or semantic equality gate that returns `rows_written=0` and performs no serving-row update when input is unchanged.
- G3. Every job or dirty-target worker persists a bounded claim before expensive CPU, provider IO, model IO, or projection work, and has bounded retry/terminal behavior.
- G4. Every dirty-target table declared in `WorkerManifest` has at least one production producer, one production consumer, and architecture tests that prove both exist.
- G5. No worker performs broad fact-table repair or history scans on an empty dirty queue. Catch-up is bounded by explicit time windows, target claims, or persisted watermarks.
- G6. Effective runtime status distinguishes intentionally disabled workers from enabled-but-unavailable workers.
- G7. Partial runtime abstractions are either applied consistently or removed. The target design must reduce cognitive surface area rather than add another compatibility layer.
- G8. Public HTTP, WebSocket, and CLI surfaces keep their business semantics while reporting pending/degraded/unavailable runtime states honestly.
- G9. Existing material facts remain valid across the hard cut. Derived read models, publication state, and control-plane rows can be rebuilt from facts.
- G10. Large modules touched by this work move toward single responsibility by extracting cohesive responsibilities, not by creating generic `utils`, `helpers`, or compatibility wrappers.

## Non-goals

- N1. This spec does not redesign the React console or frontend CSS.
- N2. This spec does not introduce a new database store, message broker, runtime scheduler, provider framework, or background worker family.
- N3. This spec does not preserve broken provider protocols, legacy current-row identities, old dirty-target names, or stale read-model columns for compatibility.
- N4. This spec does not remove audit ledgers, provider observation facts, material entity/resolution facts, or append-only market ticks.
- N5. This spec does not make optional LLM stages part of required ingestion or deterministic processing.
- N6. This spec does not require a whole-repository file split before business fixes ship. File decomposition is required only where it removes responsibility mixing in the paths being fixed.

## Target architecture

### Runtime contract

`WorkerManifest` remains the single inventory of worker ownership. Its contracts become testable facts rather than aspirational metadata:

- each declared dirty-target table has producer and consumer checks;
- each declared current read model has exactly one manifest writer and an unchanged-write test;
- each worker with `uses_provider_io=True` receives a concrete Parallax adapter that satisfies the domain protocol used by the worker;
- each enabled worker has an effective status: `running`, `stopped`, `disabled`, `intentionally_not_started`, `degraded`, or `unavailable`, where `unavailable` includes missing required provider adapters, missing required optional packages, or disabled upstream feature gates.

The hard cut removes the pattern where a configured-enabled worker silently becomes `_DisabledWorker`. A worker that is configured enabled but cannot be constructed is surfaced as unavailable with a redacted reason. Intentionally disabled workers remain disabled and do not affect readiness. Runtime entrypoints that intentionally suppress a worker family, such as collector suppression in status-only CLI commands, are reported separately as intentionally not started, not as provider/config failures.

### Provider adapters

Provider wiring owns third-party clients. Domain services and workers consume stable Parallax protocols:

```text
settings -> provider_wiring -> Parallax adapter protocol -> worker/service
```

CEX OI Radar receives a CEX derivatives/OI adapter that exposes exactly the operations the worker needs: 24h ticker snapshot, premium/funding snapshot, open-interest history, and close. The existing generic `CexMarketProvider` remains for quote/candle use only; it is not reused for OI radar when its protocol is too narrow.

CoinGlass enrichment receives the same treatment: optional third-party availability is resolved in provider wiring, not in the worker factory. Missing CoinGlass support becomes `unavailable` or `degraded enrichment`, not an implicit `None` from a raw import.

### Current read model publication

Every current read model writer follows the same conceptual flow:

```text
load stable-key current payload
build incoming stable-key payload
compare product-visible payload hash
if unchanged:
  record attempt/control metadata only when needed
  write zero serving rows
else:
  upsert/delete serving rows for the changed stable keys
  update publication/control metadata
```

Timestamp-only changes, attempt ids, run ids, generated ids, `computed_at_ms`, and `updated_at_ms` do not count as product-visible payload changes. They may be recorded in publication state or audit ledgers, not used to force serving row churn.

CEX detail snapshots, narrative admissions, discussion digests, news item briefs, macro/current projections, token/profile/capture current rows, and source quality rows all use this rule. Tables that are intentionally append-only audit ledgers are named and documented as ledgers rather than current read models.

### Claim and retry

Every worker that processes jobs or dirty targets claims persisted work before doing expensive work. The claim record includes lease owner, lease deadline, attempt count, due timestamp, and terminal state or max-attempt policy. This includes `news_item_process`, even though it operates on `news_items` rather than a separate dirty table.

Failure handling is explicit:

```text
pending -> leased/running -> done
pending -> leased/running -> retryable with next_due_at_ms
pending -> leased/running -> terminal_failed after max attempts
```

The system no longer treats `failed` as immediately equivalent to `pending`. Poison inputs cool down and eventually terminalize without hot-looping.

### Dirty-target ownership

Dirty-target tables are not allowed to be decorative. Each table has a named producer, consumer, and reason vocabulary. `token_capture_tier_dirty_targets` is produced by Token Radar publication changes that affect live-market rank membership and by any explicit repair command that rebuilds capture tiers. Its payload identity is a rank-set fingerprint, not a timestamp or source watermark alone. If a table has no production producer after the hard cut, it is dropped and the worker is removed from manifest instead of being kept as an idle compatibility artifact.

### Bounded repair and catch-up

Repair paths are first-class and bounded. A worker may catch up missed wakes by reading a persisted dirty queue, an explicit time window, or a small set of stable target identities. It may not use target repair as a disguise for scanning all history when the live projection only consumes a recent window.

Token Radar rank-source edge repair must align its write window with the downstream analysis window plus a small configured safety margin. Macro sync window generation must use stored sync control state or indexed watermarks rather than doing broad fact aggregation on every idle cycle. Source quality and watchlist summaries must be explicit projections or explicit request-time reads, not stale documentation halfway between the two.

### Runtime abstraction simplification

`WorkerBase` owns lifecycle, timeouts, telemetry, wake waits, and status. Worker-specific code owns only one `run_once` responsibility. Long-running exceptions such as `LivePriceGateway.run()` are either expressed through a supported `WorkerBase` extension point or removed from the normal worker manifest and documented as cache fanout.

`WorkerSpace` is not kept as a partial compatibility layer. The implementation plan must choose one hard-cut direction:

- remove `WorkerSpace` from runtime paths and replace its guarantees with manifest-derived architecture tests plus explicit repository/service calls; or
- apply it consistently to all workers that claim/write/read under manifest contracts.

The preferred KISS direction is removal unless the plan proves consistent adoption is smaller and clearer.

### Single-responsibility module boundaries

Root fixes should extract cohesive responsibilities where current files are too broad:

- provider adapters live in provider wiring or integrations, not worker factories;
- dirty-target semantic scheduling lives in small domain scheduling modules, not scattered string literals;
- claim/retry repositories are separated from public read queries;
- current read model publishers are separated from audit ledger writers;
- ops commands delegate to domain services rather than owning business logic.

This work must not introduce generic `common`, `utils`, or compatibility modules. New names must describe the bounded context responsibility.

## Conceptual data flow

```text
provider source
  -> provider adapter
  -> fact ingest / fact lifecycle worker
  -> material fact tables
  -> dirty target / bounded catch-up
  -> current read model writer
  -> API / WS / CLI / console

agent candidate
  -> reserve model capacity
  -> persist claim
  -> provider/model IO outside DB transaction
  -> audit ledger + current read model
  -> dirty target for downstream projection
```

Changed arrows:

- CEX OI Radar no longer receives a generic market provider or raw third-party client.
- Token Radar publication changes explicitly dirty capture tier when live-market membership can change.
- News item processing claims `news_items` durably before deterministic extraction.
- Narrative and CEX current projections compare product payload before serving-row writes.
- Runtime construction reports unavailable enabled workers instead of mutating them into disabled sentinels.

## Core models

- **Material fact**: durable business input or derived material fact. Examples: `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, `news_items`, `macro_observations`.
- **Current read model**: rebuildable serving row keyed by stable product/window identity. It may contain timestamps as payload metadata, but timestamps cannot be the reason an unchanged row is rewritten.
- **Audit ledger**: append-only operational or agent evidence. It can use run ids, attempt ids, model run ids, and timestamps because it is history, not current identity.
- **Dirty target**: durable control-plane request for bounded projection work. It has producer ownership, consumer ownership, reason vocabulary, lease state, and retry policy.
- **Provider adapter**: Parallax-owned boundary object that normalizes third-party clients into domain protocols.
- **Effective worker status**: runtime truth derived from config, provider availability, construction result, scheduler state, and latest worker status.

## Interface contracts

Public business surfaces remain stable:

- HTTP routes keep returning current read models and diagnostics, not provider calls or repair side effects.
- WebSocket pushes remain hints/fanout of committed state, not a source of product truth.
- CLI ops commands may trigger explicit repairs or backfills, but they must report target counts, bounded windows, and whether work was enqueued, skipped, or unavailable.
- `/readyz` and runtime status distinguish disabled, intentionally-not-started, unavailable, stopped, running, degraded, and failing workers without exposing secrets.

Provider and worker contracts change internally:

- Worker factories no longer import raw third-party clients.
- Missing optional provider packages are reported as unavailable/degraded capability.
- Tests use concrete Parallax adapters for runtime wiring checks, not only fakes shaped like the worker's private assumptions.

## Acceptance criteria

- AC1. WHEN `cex_oi_radar_board` is enabled with Binance configured THEN the concrete injected provider SHALL implement every method the worker path calls, and a concrete-wrapper test SHALL fail if the wiring regresses.
- AC2. WHEN CoinGlass enrichment is enabled but the adapter or dependency is unavailable THEN runtime status SHALL report the CEX worker or enrichment capability as unavailable/degraded with a redacted reason, not silently construct a raw-client `None` path.
- AC3. WHEN a current CEX board payload is unchanged THEN `cex_detail_snapshots`, `cex_oi_radar_rows`, and CEX publication serving rows SHALL write zero serving rows.
- AC4. WHEN `news_item_process` claims an item THEN the claim SHALL persist lease owner, lease deadline, attempt count, and non-pending lifecycle before extraction begins.
- AC5. WHEN news item processing fails THEN the item SHALL become retryable only after `next_due_at_ms`, and SHALL terminalize or stop requeueing after configured max attempts. Existing `processed` rows with empty classification SHALL be backfilled or repaired before the old compatibility predicate is removed.
- AC6. WHEN Token Radar publishes a current set that changes live-market rank membership, rank score, quality, current row payload hash, generation identity, or exited set THEN `token_capture_tier_dirty_targets` SHALL receive bounded work with a rank-set fingerprint for the affected rank set.
- AC7. WHEN no Token Radar live-market membership changed THEN capture tier projection SHALL not run or report rows written.
- AC8. WHEN Token Radar target-source edge repair runs for target identities THEN it SHALL bound source event reads and stale-edge deletion by the downstream analysis window plus configured safety margin.
- AC9. WHEN `narrative_admissions` input source fingerprint and product payload are unchanged THEN the worker SHALL write zero serving rows while preserving any required control metadata outside the serving payload.
- AC10. WHEN discussion digest status remains non-ready for the same target/window/scope and semantic coverage has not changed THEN the worker SHALL not delete/reinsert or timestamp-rewrite the current digest row.
- AC11. WHEN a worker is configured enabled but cannot be constructed because provider config, optional dependency, or feature gate is missing THEN runtime status SHALL mark it `unavailable`, not `disabled`; WHEN a runtime entrypoint intentionally does not start a worker family THEN runtime status SHALL mark it intentionally not started rather than unavailable.
- AC12. WHEN a worker is intentionally disabled in `workers.yaml` THEN runtime status SHALL mark it `disabled` and readiness SHALL ignore it.
- AC13. WHEN architecture tests inspect manifest dirty-target tables THEN every table SHALL have at least one production producer and exactly the expected production consumer(s).
- AC14. WHEN architecture tests inspect manifest current read models THEN every current read model SHALL have one runtime writer and an unchanged-write test or publisher-level guard.
- AC15. WHEN provider IO, model IO, subprocess IO, or external publishing occurs THEN it SHALL happen outside DB transactions and after persisted claim/capacity reservation where applicable.
- AC16. WHEN a worker has no work due THEN it SHALL not perform provider IO, model IO, or broad fact-table scans.
- AC17. WHEN `WorkerBase` lifecycle tests run THEN no manifest worker SHALL override `run()` through an allowlist; long-running cache fanout must use a supported base extension point or live outside the manifest worker loop.
- AC18. WHEN the hard cut completes THEN no runtime compatibility shim, dual old/new provider path, legacy dirty-target alias, WorkerSpace partial runtime path, old News claim API, or stale schema column remains solely to support pre-cut behavior.
- AC19. WHEN docs are updated THEN `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, and domain `ARCHITECTURE.md` files SHALL agree on worker inventory, fact/read-model ownership, and removed watchlist/account-quality behavior.
- AC20. WHEN `make check-all` runs after implementation THEN architecture tests SHALL cover provider wiring, worker availability status, dirty-target producer/consumer ownership, zero-write current models, claim-before-work, and no idle broad scans.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Hard-cut migration drops derived rows and temporarily empties a page/board. | High | Only derived read models/control-plane rows are hard-cut; facts remain. Re-enqueue rebuild targets during migration or startup verification. |
| Removing compatibility code exposes stale callers that depended on broken paths. | Medium | Treat failures as desired signal; tests and CLI help must be updated in the same plan slice. |
| Provider adapter rewrite changes CEX output semantics. | High | Golden tests compare normalized adapter output from concrete Binance wrapper against current fake expectations. |
| Zero-write gates accidentally suppress legitimate timestamp freshness. | Medium | Product-visible freshness is included only when it is serving payload; attempt/control timestamps move to publication state or audit ledgers. |
| Durable news claims strand items after worker crash. | Medium | Lease expiry returns running rows to retryable state; terminalization is explicit after max attempts. |
| Token Radar repair window is too narrow and misses older evidence still needed by product windows. | Medium | Repair window is derived from the maximum configured analysis window plus safety margin, and tests cover boundary events. |
| Worker unavailable status makes readiness fail for deployments with optional providers disabled by config. | Medium | Only configured-enabled missing dependencies are unavailable; intentionally disabled workers are ignored by readiness. |
| Splitting large modules becomes a broad refactor. | Medium | Splits are scoped to touched responsibilities and verified through behavior tests, not style-only file churn. |

## Evolution path

After this root fix, future architecture work should move in smaller slices:

1. Convert remaining large repositories into bounded repositories only when a behavior change touches that responsibility.
2. Add a manifest-derived architecture dashboard that shows worker, dirty-target, read-model, and provider capability health.
3. Expand zero-write publisher helpers only after repeated local gates prove the abstraction removes code rather than hiding it.
4. Treat new workers as last resort: first ask whether the work is an existing fact ingest, lifecycle, projection, agent, notification, or cache responsibility.

## Alternatives considered

- Keep compatibility shims around provider protocols — rejected because the CEX bug exists precisely because fake/runtime shapes diverged. A shim would preserve ambiguity rather than remove it.
- Add more worker allowlists — rejected because allowlists hide architecture drift. Root fix requires either a supported lifecycle extension point or removal from the manifest loop.
- Introduce a new global projection framework — rejected because the system already has manifest contracts, repositories, and publisher helpers. The problem is inconsistent enforcement, not missing framework surface.
- Make all read models append-only generations — rejected because Parallax current read models are serving projections with stable product/window keys. Generations may exist as publication metadata but not serving identity.
- Collapse optional agent workers into deterministic workers — rejected because agent IO has different cost, timeout, audit, and capacity semantics. Optional LLM stages must remain isolated from required fact flow.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve material facts; remove broken runtime paths; report unavailable enabled workers honestly; enforce zero-write current projections; keep provider IO behind Parallax adapters; use hard-cut migrations for derived/control-plane state. |
| Ask first | Public API field removals, production data backfills that touch material facts, dropping a worker entirely when product ownership is ambiguous, or changing operator-owned `~/.parallax/` config semantics. |
| Never | Keep old and new worker paths side by side; keep raw third-party clients in worker factories; use timestamp/run/generation identity for current serving rows; hide missing dependencies as disabled workers; fix idle broad scans by adding bigger pools or longer timeouts. |
