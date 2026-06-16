# Workers

> **Scope.** Canonical cross-domain worker inventory and runtime
> ownership map. For a beginner-friendly flow, debugging guide, and
> layered state-machine explanation, read `WORKER_FLOW.md` first. Domain
> stage maps live in each domain's `ARCHITECTURE.md`; operational
> invariants live in `RELIABILITY.md`; package boundaries live in
> `ARCHITECTURE.md`.

This service is PostgreSQL-first. Workers do not pass business truth to
each other through in-memory messages. They persist facts or rebuild read
models, optionally emit a wake hint, and downstream workers re-read the
database.

## Runtime Contract

`src/parallax/app/runtime/worker_manifest.py` is the worker
contract source of truth. A worker exists only if its manifest entry exists;
the inventory below, `WorkersSettings`, worker factories, scheduler priority,
queue-depth ownership, `/readyz`, `/api/status`, and `ops worker-status` are
all checked against that manifest. `workers.yaml` is runtime knobs only: it may
set enabled state, cadence, leases, attempts, timeouts, wake hints, and agent
lane budgets, but it does not define the worker inventory.

Every long-running worker listed here is a `WorkerBase` subclass.
`runtime.bootstrap()` builds the process runtime:

```text
settings + WorkerManifest v1 + workers.yaml
  -> DBPoolBundle
  -> provider wiring
  -> domain worker factories
  -> canonical worker map
  -> WorkerScheduler
```

`WorkerScheduler` is the only runtime owner that starts, stops, closes,
and reports worker tasks. `WorkerBase` owns the common loop:

```text
run()
  -> optional advisory lock
  -> run_once()
  -> WorkerResult/status
  -> wait interval_seconds or wake hint
  -> backoff on failure
```

Correctness must not depend on `NOTIFY` delivery. Every listener has a
bounded `interval_seconds` loop from `workers.yaml`, but that loop must
claim durable queues or read bounded read models. It must not run broad
fact-table scans when the dirty queue is empty.

Workers marked `uses_provider_io=True` in `WorkerManifest v1` are the complete
set of upstream provider/subprocess/file IO lanes:

<!-- provider-io-worker-keys:
collector, market_tick_stream, market_tick_poll, event_anchor_backfill,
resolution_refresh, asset_profile_refresh, token_image_mirror,
news_fetch, cex_oi_radar_board, macro_sync
-->

## Worker Best Practices

Use this checklist when adding or changing a worker. These rules are the
operational version of the Kappa/CQRS contract:

- Start from the manifest. A worker key, lane, kind, queue ownership, read
  model ownership, wake channels, and start priority are product architecture,
  not local implementation details. `workers.yaml` may tune runtime behavior,
  but it must not create aliases or hidden workers.
- Claim or reserve before doing expensive work. Dirty-target and job workers
  claim bounded rows first; LLM workers reserve agent capacity before claiming
  business targets. No-start backpressure does not burn attempts or write
  business run ledgers.
- Release reserved agent capacity through the gateway's synchronous resource
  accounting callback. `AgentCapacityReservation.release()` may be awaited by
  workers, but the internal release callback must return `None`; awaitable
  release results are malformed execution-plane wiring.
- Keep runtime loops proportional to changed targets. An idle worker should
  observe queue depth and return. It should not scan historical facts,
  read-model history, or provider history to discover work while idle.
- Keep provider IO outside DB sessions. Load the minimal input packet, close
  the worker session, call the provider/subprocess/filesystem/network, then
  persist the result in a new worker session.
- Make current read models compact and stable. Current rows are keyed by
  product/window/scope/target identity, not by run, generation, attempt,
  timestamp, or UUID ids. Publication state may describe freshness; it must
  not make old generations part of the serving identity. Unchanged projections
  write zero serving rows.
- Treat status as production code. `status_payload()`, custom
  `_queue_depth()` hooks, queue health, `/readyz`, `/api/status`, and
  `ops worker-status` are part of the runtime contract. Queue-depth hooks must
  be read-only and callable with no required arguments from
  `WorkerBase.status_payload()`. `WorkerScheduler` reads worker
  `status_payload()` directly for lifecycle and health decisions; a missing,
  raising, or non-object status payload is a runtime wiring failure, not an
  empty status. Unhealthy reason details such as `last_error`,
  `unavailable_reason`, and hard-timeout markers also come from that payload,
  not from direct worker attribute fallback. API helper paths that need worker liveness or the
  `live_price_gateway` object must also read the scheduler's canonical worker
  map and direct `status_payload()` contracts; they must not probe runtime
  fields, swallow hook errors, or unwrap ad-hoc worker aliases.
  PostgreSQL readiness uses the same production-contract rule: liveness probes
  commit successful probe SQL and roll back failed probe SQL through the formal
  connection methods; missing cleanup methods are malformed DB wiring, not
  optional fake-connection compatibility. Inner write guards also read
  `conn.info.transaction_status` directly; fake sessions that omit psycopg
  transaction-status evidence fail as malformed wiring rather than passing the
  transaction check.
- Test the concrete provider wrapper, not only fakes. If a worker depends on
  a provider protocol method, the runtime wrapper must implement that protocol
  directly and have a wiring test for the exact methods used.
- Keep provider-dependent worker state honest. When a worker is enabled in
  `workers.yaml` but its required provider dependency is absent, the factory
  must construct an `unavailable` worker with a redacted missing-provider
  reason. It must not construct a `disabled` worker, because `disabled`
  means operator intent and is ignored by readiness.
- Treat `WiredProviders` domain roots as formal composition contracts. Worker
  factories read roots such as `ctx.providers.news_intel` and
  `ctx.providers.cex_market_intel` directly; a missing domain bundle is
  malformed runtime wiring, not an empty provider set. Once the domain bundle
  exists, missing concrete providers may surface as `unavailable` workers.
- Runtime status surfaces use the same composition-root boundary. `/readyz`
  and ops diagnostics read `runtime.providers.asset_market` directly; missing
  provider domain bundles are malformed runtime wiring, while `None` concrete
  provider handles inside the bundle can still report disabled/disconnected
  IO state.
- Asset Market provider health is a required field on the formal provider
  bundle. Ops diagnostics reads
  `runtime.providers.asset_market.provider_health` directly; a missing health
  field is malformed bundle wiring, not an empty provider inventory.
- Asset Market worker factories read required provider-bundle fields directly:
  `cex_market`, `dex_quote_market`, `dex_profile_sources`,
  `dex_discovery_market`, and `stream_dex_market`. Missing fields are malformed
  bundle wiring; present fields with `None` values are the only supported way
  to surface enabled provider workers as unavailable.
- Asset Market startup failure cleanup also treats `OkxProviderBundle` fields
  as formal wiring. If the bundle object exists, cleanup reads
  `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` directly;
  missing fields are cleanup failure notes on the original startup error, not
  optional absent-provider state.
- Configured concrete providers must satisfy the protocols they are wired for.
  A configured GMGN DEX provider is required to expose `token_quotes(...)` and
  `token_profile(...)`; wiring must fail malformed provider objects instead of
  using optional method probes that silently route quote reads to OKX or drop
  the GMGN profile source.
- CEX Market Intel and News Intel worker factories follow the same rule for
  `oi_market`, `coinglass_derivatives`, `feed_client`, and `brief_provider`.
  Missing fields are malformed bundle wiring; `None` field values are concrete
  provider unavailability inside an otherwise valid bundle.
- CEX Market Intel provider wiring and `CexOiRadarBoardWorker` use the formal
  `settings.workers.cex_oi_radar_board` block. Wiring reads `enabled` and
  `coinglass_enrichment_limit` directly; the worker reads statement timeout,
  batch size, universe limit, period, and CoinGlass limits directly. Missing
  fields or missing OI provider objects are malformed runtime configuration,
  not disabled/enrichment-off compatibility defaults.
- Worker factory sentinel helpers read `settings.workers.<name>` directly.
  Missing worker settings blocks are malformed runtime configuration, not an
  enabled default or synthetic sentinel settings object.
  Enabled-state changes for disabled or intentionally-not-started sentinel
  workers clone the formal Pydantic worker settings through
  `model_copy(update={"enabled": ...})`; factories must not dump arbitrary
  objects, inspect `__dict__`, or synthesize `SimpleNamespace` settings.
- CLI ops one-shot worker commands use the same formal settings model. Temporary
  overrides such as `batch_size` are applied through
  `settings.workers.<name>.model_copy(update=...)`; ops code must not rebuild
  worker settings from `model_dump`, `vars(...)`, `__dict__`, or
  `SimpleNamespace(**...)`.
- `DBPoolBundle` wake listener sizing follows the same configuration contract:
  it walks manifest-declared wake listeners and reads each worker settings block
  directly. Missing `settings.workers` or missing wake worker settings is a
  configuration error, not an empty wake-listener set.
- Runtime News provider-contract status reads
  `runtime.settings.news_intel.sources` directly. Missing News Intel settings
  support is malformed runtime configuration, not an empty configured-source
  set.
- Ops diagnostics config/watchlist sections read `runtime.settings` and the
  required settings fields directly. Missing settings support is malformed
  runtime configuration, not empty config, false configured-provider flags, or
  an idle watchlist.
- Ops diagnostics queue summaries read `runtime.db.api_pool.connection()`
  directly. Missing DB/API pool connection support is malformed runtime
  wiring, not an empty manifest queue summary.
- Worker queue-health enrichment also constructs
  `runtime.db.api_pool.connection()` directly. Missing connection support is
  malformed runtime wiring; only real context-enter/query failures become
  queue-health unavailable state.
- Runtime readiness keeps no unused notification-summary helper that catches
  repository errors and returns `{}`. Notification status belongs to the
  notification route/worker contracts that own those reads.
- Collector diagnostics use the formal collector status contract directly:
  `runtime.collector.status.to_dict()` must return a mapping, and
  `runtime.collector.upstream_client` is read directly. Missing collector
  status support is runtime wiring failure, not empty diagnostics.
- Collector snapshot-gate timeout is read from the formal
  `settings.workers.collector.snapshot_timeout_seconds` field. A missing field
  is malformed worker settings, not permission for `CollectorService` to use a
  hard-coded 0.5-second default.
- `MarketTickPollWorker` receives the formal `settings.workers.market_tick_poll`
  object and the Asset Market provider bundle from the worker factory. It reads
  `settings.batch_size`, `settings.concurrency`,
  `providers.dex_quote_market`, and `providers.cex_market` directly. Missing
  provider-bundle fields are malformed runtime wiring; present `None` provider
  handles are the only supported unavailable-provider state. It must not keep
  constructor defaults, individual quote-provider arguments, optional provider
  field probes, or `SimpleNamespace` settings synthesis for tests or legacy
  callers.
- `MarketTickStreamWorker` receives the formal
  `settings.workers.market_tick_stream` object, DB pool bundle, configured
  stream provider, and wake emitter from the worker factory. It reads
  `settings.subscription_limit` and `settings.stream_cycle_seconds` directly,
  and it must not keep constructor defaults, `db` / `wake_bus` aliases,
  interval/limit overrides, or `SimpleNamespace` settings synthesis for tests
  or legacy callers.
- `MarketTickCurrentProjectionWorker` receives the formal
  `settings.workers.market_tick_current_projection` object from the worker
  factory. It reads `settings.statement_timeout_seconds`,
  `settings.batch_size`, `settings.lease_ms`, and `settings.retry_ms` directly
  for dirty-target claim, projection sessions, and retry scheduling instead of
  using runtime default constants or settings fallback probes.
- `TokenCaptureTierWorker` receives the formal
  `settings.workers.token_capture_tier` object and DB pool bundle from the
  worker factory. It reads `settings.batch_size`, `settings.ws_limit`,
  `settings.poll_limit`, and `settings.lease_ms` directly, and it must not keep
  constructor defaults, `db` aliases, interval overrides, or
  `SimpleNamespace` settings synthesis for tests or legacy callers.
- `EventAnchorBackfillWorker` receives the formal
  `settings.workers.event_anchor_backfill` object, DB pool bundle, Asset Market
  provider bundle or explicitly injected capture service, and wake emitter from
  the worker factory. It reads `settings.batch_size`, `settings.concurrency`,
  `settings.max_attempts`, `settings.lease_ms`, `settings.min_age_ms`,
  `settings.active_window_ms`, `settings.max_anchor_lag_ms`, and
  `settings.statement_timeout_seconds` directly, and it must not keep
  constructor defaults, `db` / `wake_bus` aliases, individual provider handles,
  interval overrides, or `SimpleNamespace` settings synthesis for tests or
  legacy callers.
- `NewsPageProjectionWorker` receives the formal
  `settings.workers.news_page_projection` object from the worker factory. It
  reads `settings.statement_timeout_seconds`, `settings.batch_size`,
  `settings.lease_ms`, and `settings.retry_ms` directly for worker sessions,
  dirty-target claim, and error retry scheduling instead of using runtime
  default values or settings fallback probes.
- `TokenProfileCurrentWorker` receives the formal
  `settings.workers.token_profile_current` object from the worker factory. It
  reads `settings.statement_timeout_seconds`, `settings.batch_size`,
  `settings.lease_ms`, and `settings.retry_ms` directly, and its rebuild helper
  requires the caller to pass limit, lease owner, lease, and retry settings
  explicitly instead of using worker-local default constants.
- `TokenImageMirrorWorker` receives the formal
  `settings.workers.token_image_mirror` object from the worker factory. It
  reads `settings.statement_timeout_seconds`, `settings.batch_size`,
  `settings.lease_ms`, and `settings.retry_ms` directly for dirty-source
  claim, terminal image writes, image asset retry scheduling, and dirty-source
  retry scheduling; it must not keep worker-local or service-local retry
  defaults or settings fallback probes.
- `TokenRadarProjectionWorker` receives the formal
  `settings.workers.token_radar_projection` object from the worker factory. It
  reads `settings.statement_timeout_seconds`, `settings.batch_size`,
  `settings.lease_ms`, and `settings.retry_ms` directly for worker sessions,
  dirty target/source claim leases, and dirty error retry scheduling. The
  projection service requires those lease/retry values as explicit call
  arguments and must not keep service-local dirty queue policy constants.
- `AssetProfileRefreshWorker` receives the formal
  `settings.workers.asset_profile_refresh` object from the worker factory. It
  reads `settings.statement_timeout_seconds`, `settings.batch_size`,
  `settings.lease_ms`, `settings.provider_retry_ms`,
  `settings.ready_refresh_ms`, `settings.missing_refresh_ms`, and
  `settings.error_refresh_ms` directly for provider-scoped target claim,
  profile writes, provider-block retry scheduling, and ready/missing/error
  source-cache refresh scheduling; it must not keep worker-local defaults,
  repository refresh constants, service-local refresh policy, or settings
  fallback probes.
- `ResolutionRefreshWorker` receives the formal
  `settings.workers.resolution_refresh` object, DB pool bundle, configured
  discovery provider, and wake emitter from the worker factory. It reads
  `settings.chain_ids`, `settings.max_attempts`, `settings.batch_size`, and
  `settings.reprocess_limit` directly, and it must not keep constructor chain
  overrides, unused quote-provider parameters, `wake_bus` aliases, or settings
  fallback probes. Affected-intent reprocess uses the named
  `TOKEN_REPROCESS_WINDOW` policy plus the formal `reprocess_limit`; token
  reprocess/rebuild helpers require callers to pass window and limits
  explicitly and do not expose `DEFAULT_REPROCESS_*` compatibility constants.
- Keep public reads honest. API, WebSocket, CLI, and frontend paths read facts
  or read models and expose missing/degraded states. They do not run repair
  cleanup, call providers, resurrect removed aliases, or reconstruct old
  payload shapes.
- Hard-cut old runtime paths. Migrations, completed specs, and ops notes may
  mention history; runtime code must not keep fallback readers, dual writers,
  compatibility settings, or shadow queues for removed behavior.

## Truth Categories

Review workers by separating four categories:

| Category | Meaning | Examples | Rule |
|----------|---------|----------|------|
| Facts | Business observations and decisions that should be replayable | `events`, `token_intent_resolutions`, `asset_identity_evidence`, `asset_identity_current`, `market_ticks`, `enriched_events`, Pulse audit rows | Facts are product truth. |
| Read models | Rebuildable projections for reads and product workflows | `market_tick_current`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_first_seen`, `token_profile_current`, `pulse_candidates`, `watchlist_handle_signal_stats`, watchlist summaries | Exactly one runtime writer. |
| Control plane | Scheduling, retry, lease, budget, and queue state | `event_anchor_backfill_jobs`, `market_tick_current_dirty_targets`, `token_radar_dirty_targets`, `token_discovery_dirty_lookup_keys`, `macro_projection_dirty_targets`, projection dirty targets, `pulse_trigger_dirty_targets`, `narrative_admission_dirty_targets`, `token_profile_current_dirty_targets`, `token_image_source_dirty_targets`, `asset_profile_refresh_targets`, `token_capture_tier_dirty_targets`, `pulse_agent_jobs`, `notification_deliveries` | Never treat job state as product truth. |
| Cache/fan-out | Process-local convenience state | `LivePriceGateway` latest cache and WebSocket fan-out | Cache is presentation-only unless persisted as facts. |
| Local media mirrors | Rebuildable local copies of provider media | `token_image_assets` plus files under `cache/token-images` | Public image URLs must come from ready local rows, never provider URLs. |

`app/runtime/job_queue.py` is descriptor-only ops metadata for the allowlisted
queue tables that diagnostics may read. It must not define a generic queue
executor, backoff policy, lease generator, claim/finalize/reclaim DML helper, or
`RETURNING *` mutation path for `pulse_agent_jobs` or `notification_deliveries`;
the owning domain repositories and workers remain the only runtime writers for
those control-plane tables.

The most common architecture bug is mixing these categories. For
example, a job queue row can explain why work has not finished, but it
cannot become the public market context for a token.

## Canonical Flow

The main chain is:

```text
collector
  -> IngestService transaction
  -> token_capture_tier
  -> market_tick_stream / market_tick_poll / event_anchor_backfill
  -> resolution_refresh and profile refresh lanes
  -> token_image_mirror
  -> token_radar_projection
  -> narrative_admission
  -> macro_sync / macro_view_projection / macro_daily_brief_projection
  -> pulse_candidate / notifications / API / WebSocket / CLI
```

`IngestService` is not a long-running worker, but it is listed in this
document because every downstream worker depends on the facts it writes.
Collector bootstrap must construct it from the formal `RepositorySession`
shape. Core fact/control repositories such as token evidence, token intents,
intent resolutions, discovery, market ticks, enriched events, event-anchor
jobs, and `token_radar_source_dirty_events` are required dependencies, not
constructor fallbacks or optional compatibility hooks.
Macro Intel has a normal fact-ingest worker. `macro_sync` claims bounded
sync windows, runs the packaged `macrodata` executable outside DB
transactions, writes `macro_observations`, `macro_import_runs`, and
sync control/audit rows, then wakes the macro view projection as a hint.
`MacroSyncWorker` and `MacroSyncService` read source/bundle, enqueue windows,
claim lease, retry delay, session timeout, and batch size from the formal
`macro_sync` worker settings; they do not keep old constructor `wake_bus`
aliases or per-field runtime defaults.
FRED key lookup is also a formal root-settings contract: settings owns the
default env name, and `macrodata_fred_api_key_env: null` or blank disables env
lookup instead of letting worker/runtime code restore `FINANCE_FRED_API_KEY`.
`MacroViewProjectionWorker` reads statement timeout, claim batch, lease,
retry, lookback, and per-series bounds only from the formal
`macro_view_projection` worker settings; history-quality lower bounds are a
settings-schema contract, not runtime fallback constants.
The current `macro_view_snapshots` JSON sections are formal projection output:
the repository requires `panels_json`, `indicators_json`, `triggers_json`,
`data_gaps_json`, `source_coverage_json`, `features_json`, `chain_json`,
`scenario_json`, and `scorecard_json` before payload hash or SQL, so missing
writer sections are not laundered into empty objects or arrays.
When `macro_view_projection` publishes a changed current snapshot, it wakes
`macro_daily_brief_projection`, which reads the current macro projection and
writes the stable `assets_today` daily-brief read model for the operator console. The
`macro import-bundle` CLI is offline replay/seed only; because it still writes
`macro_observations`, `macro_import_runs`, and projection dirty targets, it
must use the formal `RepositorySession.unit_of_work` / `require_transaction`
contract rather than raw connection transaction fallback.
Macro observation series refresh publishes current rows and publication state in
one connection transaction; missing connection transaction support is a
repository/session contract failure before current-row delete/insert SQL.
Macro projection dirty-target repository-owned claim/done/error mutations also
require connection transaction support before `macro_projection_dirty_targets`
SQL; the worker path keeps those writes caller-owned with `commit=False` inside
`RepositorySession.transaction`.

Narrative bulk LLM analysis has been removed from the runtime inventory.
`narrative_admission` remains as a deterministic, DB-backed admission read
model writer. Token Radar may enqueue `narrative_admission_dirty_targets`
when that worker is enabled. There is no `mention_semantics`,
`token_discussion_digest`, narrative LLM provider, or narrative bulk gate in
the active worker harness. Historical semantic/digest tables may still be read
by public surfaces as legacy context, but no current worker writes them.

## Worker Inventory

<!-- worker-inventory-keys:
collector, token_capture_tier, market_tick_stream, market_tick_poll, market_tick_current_projection,
event_anchor_backfill, live_price_gateway, resolution_refresh,
asset_profile_refresh, token_image_mirror, token_radar_projection, token_profile_current,
narrative_admission,
news_fetch, news_item_process,
news_item_brief, news_page_projection, news_source_quality_projection,
cex_oi_radar_board, macro_sync, macro_view_projection, macro_daily_brief_projection,
pulse_candidate, notification_rule,
notification_delivery
-->

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `collector` (`CollectorService`) | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | `raw_frames` input observations through `EvidenceRepository`; normalized events through `IngestService`; watched-account `account_token_alerts`; repository-owned raw-frame, event-entity, and account-token-alert writes require connection transaction with no manual commit fallback; raw-frame/event/entity insert state or counts and account-token-alert insert state require PostgreSQL single-row `cursor.rowcount` evidence | provider-driven (WS) | none | continuous WS |
| `token_capture_tier` (`TokenCaptureTierWorker`) | `asset_market` | `domains/asset_market/runtime/token_capture_tier_worker.py` | due `token_capture_tier_dirty_targets`; bounded ranked live-market target set | `token_capture_tier`; dirty rank-set enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from row-level `source_max_received_at_ms`, legacy `source_watermark_ms`, `0`, or runtime `now_ms`; dirty target claim/done state inside `RepositorySession.transaction`; repository-owned dirty target enqueue/claim/done mutations require connection transaction with no manual commit fallback; tier upsert changed booleans, tier demotion, and dirty-target enqueue/done changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed capture-tier work; tier `RETURNING true AS changed` rowcount must match returned-row presence before worker `rows_written` is reported | poll | none | `interval_seconds` |
| `market_tick_stream` (`MarketTickStreamWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_stream_worker.py` | `token_capture_tier(tier=1)`, OKX DEX WS | `market_ticks(source_tier='tier1_ws')` | provider-driven (WS) | `market_tick_written` | bounded stream cycle |
| `market_tick_poll` (`MarketTickPollWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_poll_worker.py` | `token_capture_tier(tier=2)`, OKX DEX and Binance USD-M CEX REST quotes | `market_ticks(source_tier='tier2_poll')` | poll | `market_tick_written` | `interval_seconds` |
| `market_tick_current_projection` (`MarketTickCurrentProjectionWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_current_projection_worker.py` | due `market_tick_current_dirty_targets`, append-only `market_ticks` | `market_tick_current`, `token_radar_dirty_targets` for changed market current rows; dirty-target repository-owned enqueue/claim/done/error mutations require connection transaction with no manual commit fallback; done/error completion keys require positive claimed-row `attempt_count` with no zero-attempt fallback; enqueue and done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed market-current targets or candidate dirty width; repository-owned current-row `RETURNING true AS changed` booleans require rowcount evidence matching returned-row presence before downstream dirty enqueue or wake decisions are reported | `market_tick_written` | `market_tick_current_updated` after successful current changes | `interval_seconds` |
| `event_anchor_backfill` (`EventAnchorBackfillWorker`) | `asset_market` | `domains/asset_market/runtime/event_anchor_backfill_worker.py` | due `event_anchor_backfill_jobs`, event-adjacent `market_ticks`, quote providers inside the lag budget | `market_ticks`, narrow `enriched_events` lifecycle transition, `event_anchor_backfill_jobs` status; stale cleanup shares worker-session `unit_of_work` for job/enriched-event terminal writes, repository terminal paths require connection transaction for job/terminal-ledger writes with no `nullcontext` fallback, temporary retry / done / terminal guards require positive claimed-row `attempt_count` with no zero-attempt fallback, and job `UPDATE ... RETURNING` claim/cleanup/retry/reconcile/done/terminal/reschedule paths require cursor rowcount evidence matching returned rows before rows, counts, terminal ledger writes, or booleans are reported | poll | `market_tick_written` | `interval_seconds` |
| `live_price_gateway` (`LivePriceGateway`) | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | bounded live target rows from `token_capture_tier`, latest `market_ticks` per target within `target_ttl_seconds` | in-process latest cache and WebSocket fan-out only; formal settings provide `target_limit` and `target_ttl_seconds` with no provider/interval constructor fallback | poll | none | `interval_seconds` |
| `resolution_refresh` (`ResolutionRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | due `token_discovery_dirty_lookup_keys`, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results`, queue completion/reschedule state; lookup claim lease, running timeout, hot not-found retry cadence, claim batch, retry budget, and reprocess limit come from formal `settings.workers.resolution_refresh`; affected-intent reprocess enqueues Token Radar source-dirty rows only from formal `TokenIntentResolutionDecision` results and fails loose resolver decision objects before dirty enqueue; due work is consumed only through `claim_due_lookup_keys(...)`, not a read-only due-list repository helper; DiscoveryRepository repository-owned enqueue/claim/done/reschedule/start/finish/fail mutations require connection transaction with no manual commit fallback and receive due/claim/start timing explicitly rather than using repository-local policy constants; lookup queue enqueue/done/reschedule changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed lookup work; lookup claim done/reschedule/terminal completion keys and worker retry-budget decisions require positive claimed-row `attempt_count` with no zero-attempt fallback, and completion keys also require non-empty claimed-row `lease_owner` plus claimed `payload_hash`; lookup running/finish/fail/claim completion writes require `RepositorySession.transaction`; repository-owned registry asset and asset identity evidence/current writes require connection transaction, and asset_identity_current `RETURNING true AS changed` booleans require rowcount evidence matching returned-row presence before `rows_written` is reported; terminal lookup-claim delete and terminal-ledger writes require connection transaction with no `nullcontext` / manual commit fallback, terminal-ledger payload hashes must come from the deleted queue source row without empty-string fallback, and terminal delete rowcount must match returned deleted lookup rows before terminal counts or ledger rows are reported | poll | `resolution_updated` | `interval_seconds` |
| `asset_profile_refresh` (`AssetProfileRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | due `asset_profile_refresh_targets`, configured DEX profile sources | `asset_profiles`, refresh target state, `token_profile_current_dirty_targets` when source facts change; refresh-target enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from source-cache `updated_at_ms` or runtime `now_ms`; Token Profile Current dirty enqueue uses the claimed source watermark and must not repair missing source watermarks with runtime `now_ms`; ready/missing/error source-cache refresh and target reschedule cadences come from formal `settings.workers.asset_profile_refresh` and are passed explicitly into service/repository calls; refresh-target repository-owned enqueue/claim/reschedule/error mutations require connection transaction with no manual commit fallback; reschedule/error completion keys require positive claimed-row `attempt_count` with no zero-attempt fallback; reschedule/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed refresh targets; repository-owned `asset_profiles` ready/status writes require connection transaction with no manual commit fallback; worker profile writes use session transaction with `commit=False` | poll | none | `interval_seconds` |
| `token_image_mirror` (`TokenImageMirrorWorker`) | `asset_market` | `domains/asset_market/runtime/token_image_mirror_worker.py` | due `token_image_source_dirty_targets` only; it does not scan source tables | `token_image_assets`, local cache files, `token_profile_current_dirty_targets` on terminal image changes; profile-current dirty enqueue uses the claimed image-source watermark and must not repair missing source watermarks with runtime `now_ms`; dirty-source enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from target-level `observed_at_ms`, source-row `updated_at_ms`, or runtime `now_ms`; dirty-source repository-owned enqueue/claim/done/error mutations require connection transaction with no manual commit fallback; done/error completion keys require positive claimed-row `attempt_count`, non-empty claimed-row `lease_owner`, claimed `payload_hash`, and claimed `source_url_hash`; completion must not rederive `source_url_hash` from `source_url`; done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed image-source targets; repository-owned image lifecycle writes require connection transaction with no manual commit fallback and require PostgreSQL single-row `cursor.rowcount` evidence, while pending/ready `RETURNING` paths must match rowcount with returned-row presence; worker terminal image writes use session transaction with `commit=False`; image asset and dirty-source retry cadence both come from formal `settings.workers.token_image_mirror.retry_ms`, dirty-source retry budget comes from formal `settings.workers.token_image_mirror.max_attempts`, and exhausted dirty-source claims are deleted and terminalized in `worker_queue_terminal_events` rather than re-admitted indefinitely | poll | none | `interval_seconds` |
| `token_radar_projection` (`TokenRadarProjectionWorker`) | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | `token_radar_source_dirty_events`, `token_radar_dirty_targets`; compact `token_radar_rank_source_events` rank-source edges | `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_first_seen`, `projection_runs`, `projection_offsets`, `token_score_evaluations`; after dirty claims are acquired, edge/feature changes, rank publication attempts, and dirty done/error terminalization run inside one explicit connection transaction; repository-owned rank-source edge population/prune writes require connection transaction before SQL and query helpers do not own commits; repository-owned serving publication/target-feature/first-seen/failure writes require connection transaction before SQL; projection-private cache retention for target-feature and rank-source rows is a bounded worker maintenance lane outside rank publication; repository-owned projection offset/run/dirty-range control-plane writes require connection transaction before SQL, ordinary offset/run/dirty enqueue and finish mutations require exactly one PostgreSQL `cursor.rowcount`, projection-run `start_run` uses `INSERT ... RETURNING *` without `run_by_id` readback proof, projection-run stale-running cleanup counts require PostgreSQL `cursor.rowcount` evidence, dirty-range `UPDATE ... RETURNING` claims require cursor rowcount to match returned claimed rows, and projection-run/dirty-range diagnostic reads require explicit caller limits with no repository-local `20`/`50` defaults; rank-set publication uses compact rank inputs and `_compact_rank_key`, with no retired `_rank_key`, invalid-snapshot demotion, or `raw_alpha_score` fallback compatibility path; repository-owned score-evaluation single/batch upserts require connection transaction before SQL, batch per-row writes use `commit=False` inside that transaction, and score evaluation consumes only formal v3 `factor_snapshot_json` with required `composite.rank_score`, settlement-local formal `Asset` / `CexToken` `subject.target_type` plus `subject.target_id`, Asset `subject.chain` / `subject.address`, CEX `subject.provider` / `subject.native_market_id`, `provenance.computed_at_ms`, and family diagnostics from `families.*.score` instead of counting malformed snapshots as `0-19` bucket samples, accepting direct market-tick subject types `chain_token` / `cex_symbol`, repairing Asset market identity from `chain_id` / `asset_address` aliases, repairing subject identity from current-row aliases or `market.decision_latest`, using `instrument` aliases or epoch-zero settlement time, or reading family IC/coverage from `composite.family_scores`; downstream dirty-target enqueue to Pulse, Narrative Admission, Token Profile Current, and Token Capture Tier uses required direct session repositories without optional probes; worker windows, scopes, venues, hot windows, batch size, cold interval, private-cache retention, and statement timeout come from formal `token_radar_projection` settings, projection service window math requires those valid windows without `1h`/`24h` fallbacks, and downstream wakes use `wake_emitter` with no old `wake_bus` alias | `market_tick_current_updated`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `token_profile_current` (`TokenProfileCurrentWorker`) | `asset_market` | `domains/asset_market/runtime/token_profile_current_worker.py` | due profile dirty targets; exact profile/evidence sources through `RepositorySession.source_query`, full `token_image_assets` states, existing image dirty targets | `token_profile_current`, `token_image_source_dirty_targets`; dirty-target enqueue requires mapping-shaped targets with positive producer-supplied `source_watermark_ms` and must not repair missing watermarks from `computed_at_ms`, `updated_at_ms`, tuple target identity, or runtime `now_ms`; image-source admission for Token Image Mirror requires positive source-row `observed_at_ms` and must not repair image-source dirty watermarks from `updated_at_ms` or runtime `now_ms`; dirty-target repository-owned claim/done/error mutations require connection transaction with no manual commit fallback; done/error completion keys require positive claimed-row `attempt_count` with no zero-attempt fallback; done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed profile-current targets; repository-owned current-row upserts require connection transaction with no manual commit fallback, require formal `quality_flags_json` and `source_payload_json` row fields without legacy `quality_flags` / `source_payload` aliases, and RETURNING changed booleans require rowcount evidence matching returned-row presence before worker `rows_written` is reported | poll | none | `interval_seconds` |
| `narrative_admission` (`NarrativeAdmissionWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/narrative_admission_worker.py` | due `narrative_admission_dirty_targets`; target-scoped Radar rows, `events`, current `token_intent_resolutions` | `narrative_admissions`; dirty-target claim/done/error and admission upsert/stale writes are caller-owned inside `RepositorySession.transaction`, and repository-owned dirty-target/admission mutations require connection transaction with no manual commit fallback; dirty done/error/reschedule completion keys require positive claimed-row `attempt_count` with no zero-attempt fallback, and dirty/admission changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-row or zero-admission accounting; worker session timeout, admission/source limits, lease, retry, and deterministic rank thresholds come from formal `narrative_admission` settings with no second-level `lease_seconds` / `error_retry_seconds` fallback, no service-local threshold defaults, and no carry-forward TTL compatibility | `token_radar_updated`, `resolution_updated` | none | `interval_seconds`; wake-in only, no wake emitter |
| `news_fetch` (`NewsFetchWorker`) | `news_intel` | `domains/news_intel/runtime/news_fetch_worker.py` | configured `news_intel.sources` with source classification/policy, due `news_sources`, RSS/Atom/CryptoPanic feeds, OpenNews REST `/open/news_search` catch-up | `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items`; configured-source `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned source row before inserted/updated source rows are reported; provider-item `INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned provider-item row before inserted/updated provider observations are reported; canonical item `INSERT INTO news_items ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned `news_items` row before observation edges, remap cleanup, or affected-item accounting use the canonical `news_item_id`; observation-edge `INSERT INTO news_item_observation_edges ... ON CONFLICT` upserts require rowcount=1 before provider-article remap, material duplicate remap, summary refresh, or affected-item accounting treats the provider observation as linked; observation summary `UPDATE news_items ... RETURNING items.*` refreshes require rowcount=1 with a returned current item row before affected-item accounting uses refreshed source/provider-article aggregates, while old zero-edge cleanup accepts rowcount=0/no row only as explicit optional cleanup state and never fallback `SELECT` readback; due-source `UPDATE news_sources ... RETURNING sources.*` claim results require cursor rowcount matching returned claim rows before provider fetch work; fetch-run start requires rowcount=1 for the `news_fetch_runs` running-row insert and matching `news_sources.last_fetch_at_ms` update before a run id is returned; fetch-run `UPDATE news_fetch_runs ... RETURNING *` finalization requires rowcount=1 with a returned run row before `news_sources` status changes or finalized run rows are returned; semantic page dirty work from repository `affected_news_item_ids`; source-refresh work; worker sessions, due-source batch, source-claim lease, feed fetch limit, provider requirement, configured-source contract, and item/page dirty wake emitter read formal `news_fetch` settings/wiring directly | poll | `news_item_written` | `interval_seconds`; no agent admission; missing affected-set evidence fails closed |
| `news_item_process` (`NewsItemProcessWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_process_worker.py` | unprocessed `news_items`, token identity interfaces, bounded same-item/story admission context read back from PostgreSQL after deterministic fact writes | `news_item_entities`, `news_token_mentions`, `news_fact_candidates`, `news_items.content_class/content_tags_json/content_classification_json`, `news_items.market_scope_json`, `news_items.story_identity_json`, `news_items.agent_admission_*`; provider-article duplicate lookup uses normalized `news_item_observation_edges.provider_article_key` joins, not JSONB array expansion over `provider_article_keys_json`; entity, token mention, fact candidate, current market scope, story identity, and agent admission writes require formal domain result objects with no dict/alias/default or object-reflection write payload fallback; semantic page work and optional item-brief work after provider-rating-gated market-wide agent admission; claimed item rows require positive `processing_attempts` and non-empty `processing_lease_owner`; worker sessions, claim batch, lease, max attempts, retry cadence, and processed-item wake emitter read formal `news_item_process` settings/wiring directly | `news_item_written` | `news_item_processed` | `interval_seconds` |
| `news_item_brief` (`NewsItemBriefWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_brief_worker.py` | semantic item-brief work; processed `news_items`, formal `NewsItemBriefEntityLane` / token / fact input-packet rows, current brief state, and current `agent_admission` after reserving `news.item_brief`; stale targets are re-admitted and low/missing provider-rating rows are policy-skipped before model execution | `news_item_agent_runs`, `news_item_agent_briefs`, refreshed `news_items.agent_admission_*`; semantic page work; `news_item_agent_runs` insert and `news_item_agent_briefs` current upsert require rowcount=1 with a returned row before audit/current state or page dirty accounting is reported; schema-version cleanup of current `news_item_agent_briefs` rows through `DELETE ... RETURNING news_item_id` requires cursor rowcount to match returned ids before stale-brief cleanup accounting is reported; reusable completed/failed run paths require non-empty persisted `news_item_agent_runs.run_id` before current-brief restore or failed-current write; validation/audit/admission/entity-lane support consumes formal contracts without object-reflection fallback; worker sessions, claim batch, lease, retry cadence, backpressure cooldown, provider requirement, and brief-updated wake emitter read formal `news_item_brief` settings/wiring directly | `news_item_processed` | `news_item_brief_updated` | `interval_seconds`; no-start backpressure claims nothing and writes no run ledger |
| `news_page_projection` (`NewsPageProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_page_projection_worker.py` | semantic page reprojection work; target-scoped `news_items`, `news_token_mentions`, `news_fact_candidates`, current brief state, and agent admission state | `news_page_rows`; worker sessions, claim batch, lease, and retry cadence read formal `news_page_projection` settings directly; page-row JSON sections are required writer output before payload hash or SQL; `RETURNING (xmax = 0)` upserts require rowcount/returned-row consistency before inserted/updated/unchanged accounting; constructor has no wake emitter because this projection writes rows but emits no downstream wake | `news_item_written`, `news_item_processed`, `news_item_brief_updated`, `news_page_dirty` | none | `interval_seconds` |
| `news_source_quality_projection` (`NewsSourceQualityProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_source_quality_projection_worker.py` | semantic source-quality refresh/window work; target-scoped `news_sources`, `news_fetch_runs`, `news_items`, `news_token_mentions`, `news_fact_candidates`, `news_item_agent_briefs` by source/window | `news_source_quality_rows`, `news_sources.source_quality_status`; worker sessions, claim batch, lease, retry cadence, and windows read formal `news_source_quality_projection` settings directly | `news_item_written` | `news_page_dirty` only when compact source status changes | `interval_seconds`; unchanged compact source status emits no downstream wake |
| `cex_oi_radar_board` (`CexOiRadarBoardWorker`) | `cex_market_intel` | `domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py` | Binance-backed `price_feeds`, Binance USD-M ticker/premium/OI history, bounded CoinGlass enrichment when available | `cex_oi_radar_rows`, `cex_oi_radar_publication_state`, `cex_detail_snapshots`; selected universe routes require non-empty `native_market_id` and `base_symbol` before Binance provider IO, so malformed route identity records a failed attempt instead of a skipped symbol, empty-base row, or successful empty board; Binance OI provider wiring maps formal integration DTO fields into domain provider DTOs, and Binance provider ticker/funding/OI history objects must expose the formal provider DTO fields; malformed integration/provider objects fail before scoring instead of becoming empty board metrics; board/detail/attempt-state writes use `RepositorySession.transaction`, and repository-owned CEX read-model commits require connection transaction with no manual commit fallback; board current identity requires non-empty `period`, `target_id`, and `native_market_id` before board key construction, row-id hashing, payload hash, or upsert; board payload hashes use provider-observed market freshness only, so computed fallback observed timestamps and successful empty-board attempt times are attempt/publication metadata rather than serving-row content signatures; board delete/upsert write accounting requires real `cursor.rowcount` evidence and treats missing or invalid rowcount as malformed driver/wiring state rather than a default zero- or one-row write; derivative-series history upserts skip unchanged overlapping provider-history conflict rows with `IS DISTINCT FROM` and required `cursor.rowcount` evidence instead of unconditional updates, treat missing or invalid rowcount as malformed driver/wiring state rather than a default write count, require non-empty provider, exchange, native-market, metric, and period identity before hash or SQL so empty text cannot become a PostgreSQL business key, and require mapping-shaped point `raw_payload` before JSONB SQL so missing provider evidence cannot become `{}`; detail snapshot `snapshot_id`, `target_type`, `target_id`, `exchange`, and `native_market_id` are formal serving identity fields required before builder output, payload hash, or upsert with no skipped empty market row, `cex_token:unknown`, `CexToken`, or `binance` fallback; detail snapshot level bands require formal `kind` and numeric `price` before source refs or snapshot payload are built, with no default `level` kind or skipped missing-price band; present detail/enrichment `degraded_reasons` require list-shaped non-empty strings, with no scalar-string, mapping, non-string item, or blank-item coercion; detail snapshot upsert write accounting requires real `cursor.rowcount` evidence and treats missing or invalid rowcount as malformed driver/wiring state rather than a default no-op write; detail snapshot exchange is an explicit worker/provider input, so the builder does not restore missing exchange through local Binance snapshot ids or source refs; detail snapshot read methods require non-empty target or market query identity before SQL; Token Case/Search Inspect missing-detail blocks do not synthesize `snapshot_id` or `exchange` because those fields belong only to persisted detail rows; provider, period, build-limit, enrichment, level-band, and execution budgets come from formal settings/wiring with no worker-local or service-local defaults | poll | none | `interval_seconds`; current board row ids are stable by provider/exchange/period/target |
| `macro_sync` (`MacroSyncWorker`) | `macro_intel` | `domains/macro_intel/runtime/macro_sync_worker.py` | due `macro_sync_windows`; packaged `macrodata` history bundle after claim | `macro_observations`, `macro_import_runs`, `macro_sync_windows`, `macro_sync_runs`; retry-budget decisions require claimed-window `attempt_count` and `max_attempts` with no default fallback; sync-window enqueue/claim `RETURNING` paths require PostgreSQL rowcount evidence matching returned-row presence before enqueued, no-work, or claimed-window state is reported; sync-window terminal/retry/failure and `macro_sync_state` repair accounting requires PostgreSQL single-row `cursor.rowcount` evidence and fails on missing, invalid, or multi-row counts instead of default zero/one-row accounting | poll | `macro_observations_imported` | claims one bounded window; idle cycles do no provider IO and no broad fact scan |
| `macro_view_projection` (`MacroViewProjectionWorker`) | `macro_intel` | `domains/macro_intel/runtime/macro_view_projection_worker.py` | due `macro_projection_dirty_targets`; then exact `macro_observations` history and `macro_observation_series_rows` current projection | `macro_observation_series_rows`, `macro_view_snapshots`, `macro_observation_series_publication_state`; dirty-target claim, projection writes, and done/error state run through `RepositorySession.transaction` with post-commit wake only; repository-owned dirty-target claim/done/error mutations require connection transaction with no manual commit fallback; dirty-target enqueue/done/error and current-series delete/upsert counts require PostgreSQL `cursor.rowcount` evidence instead of default zero/one/length accounting; existing current-series rows must carry non-empty `payload_hash` before change/unchanged comparison; `macro_view_snapshots` `RETURNING true AS changed` rowcount must match returned-row presence before changed booleans or downstream wake counts are reported | `macro_observations_imported` | `macro_view_snapshot_updated` | `interval_seconds`; formal settings own statement timeout, batch, lease, retry, lookback, and per-series bounds; no dirty target means no broad fact scan; unchanged signatures write zero serving rows and emit no downstream wake |
| `macro_daily_brief_projection` (`MacroDailyBriefProjectionWorker`) | `macro_intel` | `domains/macro_intel/runtime/macro_daily_brief_projection_worker.py` | current `macro_view_snapshots` and current macro series rows | `macro_daily_briefs`; session timeout reads formal `macro_daily_brief_projection` settings directly; `macro_daily_briefs` `RETURNING true AS changed` rowcount must match returned-row presence before worker `rows_written` is reported | `macro_view_snapshot_updated` | none | daily `interval_seconds`; deterministic `assets_today` row writes zero serving rows when payload hash is unchanged |
| `pulse_candidate` (`PulseCandidateWorker`) | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | due `pulse_trigger_dirty_targets`; exact Token Radar current row and evidence context for Pulse `1h`/`4h` horizons | read models: `pulse_candidate_edge_state`, `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_playbook_snapshots`; control/audit: `pulse_agent_jobs`, run-budget tables, `pulse_agent_runs`, `pulse_agent_run_steps`, runtime-version and eval tables; trigger done/error/reschedule completion keys and exit-suppression `trigger_signature` require claimed-row `payload_hash`, trigger completion and agent job run-id/audit/retry/release decisions require positive claimed-row `attempt_count`, and trigger completion plus stale agent-run cleanup changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-row accounting; agent run/step/runtime/eval audit, evidence packet upsert/run-link, public candidate upsert/hide, admission edge/budget, and playbook snapshot/outcome `RETURNING` writes validate cursor rowcount against returned-row presence, with unchanged candidate/playbook projections reported as rowcount=0/no-row instead of fallback `SELECT`; `max_attempts` is passed explicitly from formal worker settings at enqueue and required for retry/dead classification; evidence packet market-fact freshness comes from formal `evidence_market_freshness_ms`, not builder/repository defaults; timeline context receives explicit worker target `window`/`scope` and rejects malformed values instead of restoring `1h`/`all`; admission failure-circuit and timeline-debounce policy comes from formal `pulse_candidate` settings, not `PulseAdmissionPolicy` defaults | `token_radar_updated` | none | `interval_seconds` |
| `notification_rule` (`NotificationWorker`) | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | `notifications` facts and `notification_deliveries` control rows written inside the worker-session `unit_of_work`; insert results use formal `NotificationInsertOutcome`; `INSERT ... DO NOTHING` state classification for notification facts and insert-only delivery control rows requires PostgreSQL single-row `cursor.rowcount` evidence, and missing or invalid rowcount is malformed driver/wiring state rather than a created/existing decision; aggregated external deliveries use required requeue contract, and requeue `RETURNING *` outcomes require rowcount/returned-row consistency before reactivated delivery rows are reported; external delivery `max_attempts` comes from formal `settings.workers.notification_delivery.max_attempts` through the runtime factory, not a rule-worker constructor default; Signal Pulse notification query window/scope/status defaults, Signal Pulse page budget, candidate query limit, watched-account activity window, News high-signal recency window, and News high-signal overscan budgets live only in `settings.notifications`; watched-account activity passes its configured `since_ms` window into `EvidenceRepository.recent_events(...)` so PostgreSQL filters `events.received_at_ms` before the service shapes candidates; watched-account token alerts pass the worker evaluation `now_ms` through `AccountAlertService.account_alerts(...)` to `SignalRepository.account_alerts(...)`, so alert windows share the same rule-evaluation clock and do not fall back to repository wall time; Signal Pulse notification candidate discovery uses the dedicated `PulseReadRepository.list_signal_pulse_notification_candidates(...)` keyset/window query with per-scope/status budget, not public-list cursor pagination or one `list_candidates(...)` query per scope/status/page; non-Signal rules accept delivery settings only; rule evaluation receives explicit worker `now_ms` and the rule engine must not read wall-clock time; worker batch limit and session timeout read formal `notification_rule` settings directly | poll | none | `interval_seconds` |
| `notification_delivery` (`NotificationDeliveryWorker`) | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending `notification_deliveries` | `notification_deliveries` side-effect/control ledger; claim/pre-flight/log-complete/external complete/fail state transitions use `RepositorySession.transaction` with external IO outside DB transactions; claim `RETURNING *` outcomes require PostgreSQL rowcount/returned-row consistency before no-delivery or claimed-delivery state is reported; repository-owned enqueue/requeue commits require connection transactions; batch limit and session timeout read formal `notification_delivery` settings directly | poll | none | `interval_seconds` |

`macro_sync` queue state is a persisted control-plane read over
`macro_sync_windows`. `MacroSyncService.enqueue_due_windows(...)` calls the
formal `macro_sync_queue_summary(...)` repository method directly after
enqueueing due windows; missing method support is session wiring failure, not
an empty queue summary.
Failure retry-budget classification reads the claimed `macro_sync_windows`
`attempt_count` and `max_attempts` directly. Missing or non-positive values are a
malformed claim-window contract, not permission to classify the run through
first-attempt defaults.

Asset Market Binance CEX route sync is ops-only maintenance, but its
dry-run/execute plan counts are still PostgreSQL read contracts. The service
must call `RegistryRepository.binance_usdt_perp_sync_plan_counts(...)`
directly; missing support is a repository/session wiring failure, not an
input-count estimate of inserts or deletes.

`pulse_candidate` owns public Pulse row visibility transitions. If the
low-information gate invalidates a previously public candidate, the worker must
call `hide_public_candidate_for_low_information`; missing repository support is
a dirty-trigger failure/retry and must not be treated as "nothing to hide".
`pulse_candidate` and its job service read windows, scopes, queue limits, agent
job budgets, dirty-trigger lease/retry intervals, target/candidate edge budgets,
failure-circuit threshold/reasons, timeline-debounce policy, stale running-job
timeout and terminalization batch size, trigger/gate thresholds, and session timeout directly from formal
`workers.pulse_candidate` settings; missing settings, DB bundle, or decision
client support is a construction/runtime contract failure, not a worker-local,
repository-local, or policy-service default fallback.
Dirty-trigger admission and capacity checks read `pulse_agent_jobs`,
`pulse_candidate_edge_state`, recent-failure counts, pending job counts, and
queue depth through the formal Pulse repositories. Missing repository support
is a dirty-trigger failure/retry, not empty job, edge, capacity, or queue state.
Claimed dirty-trigger `window` and `scope` values must match formal
`workers.pulse_candidate` settings before exact Token Radar or timeline reads;
malformed dimensions fail the dirty trigger for retry instead of being widened
to all-public evidence.
Existing failed `pulse_agent_jobs` rows must expose formal `attempt_count` and
`max_attempts` values before admission policy can classify them as retryable;
malformed attempt state is a dirty-trigger failure/retry, not a policy-local
default.
Pulse dirty-trigger claim, admission/edge/public visibility writes, job enqueue,
and dirty target done/error updates run through `RepositorySession.transaction`;
missing session transaction support is a runtime contract failure before
claim/write, not a raw connection transaction fallback.
Pulse admission edge-state and candidate edge-budget `RETURNING` writes require
PostgreSQL `cursor.rowcount` evidence matching returned-row presence before edge
rows, optional state rows, or budget booleans are reported; missing, invalid, or
mismatched rowcount is malformed repository/driver state, not a returned-row
success signal.
Pulse dirty-trigger done/error/reschedule changed-row counts require PostgreSQL
`cursor.rowcount`; missing or invalid rowcount is malformed repository/driver
state, not zero changed dirty-trigger work.
Pulse agent job execution writes the agent run ledger, deterministic eval,
candidate/playbook rows, admission edge state, and job terminal state through
`RepositorySession.transaction`; missing session transaction support is a
runtime contract failure before writes, not a `nullcontext` or raw connection
transaction fallback.
The same execution path requires the claimed `pulse_agent_jobs.attempt_count`
before run-id and agent-audit construction; malformed job claims fail before the
pipeline enters repository state. Failure, timeout cancellation, provider
cooldown, and backpressure release also require the claimed attempt for CAS, and
failure retry/dead classification requires `max_attempts`.
Pulse job terminal/dead transitions in `PulseJobsRepository` write
`pulse_agent_jobs` state and `worker_queue_terminal_events` evidence in the
same connection transaction. Missing connection transaction support fails before
job-state or terminal-ledger SQL, not through `nullcontext` or manual commit
compatibility. Batch terminal/dead transitions that use `UPDATE ... RETURNING`
must validate PostgreSQL `cursor.rowcount` and require it to match returned rows
before terminal ledger writes; missing, invalid, or mismatched rowcount is
malformed repository/driver state, not a returned-row-count terminalized-job
result.
Pulse job enqueue, success marking, running-job release, and stale agent-run
cleanup also use a connection transaction when the repository owns the commit.
Missing connection transaction support fails before job/run SQL, not through
manual `self.conn.commit()` compatibility.
Stale agent-run cleanup changed-row counts require PostgreSQL
`cursor.rowcount`; missing or invalid rowcount is malformed repository/driver
state, not zero stale `pulse_agent_runs` work.
`PulseJobsRepository.enqueue_job(...)` requires explicit `max_attempts`; the
worker passes `settings.workers.pulse_candidate.max_attempts` into the row, and
the repository must not keep a local fallback retry-budget default.
Pulse stale running-job timeout is owned by
`settings.workers.pulse_candidate.job_running_timeout_ms` and is passed into
`PulseJobsRepository` at repository-session construction. `PulseJobsRepository`
must not retain a local timeout default, and other Pulse repositories must not
carry unused running-timeout state.
Pulse stale exhausted running-job terminalization batch size is owned by
`settings.workers.pulse_candidate.stale_running_terminalization_batch_size`; the
worker passes it into `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`
explicitly, and the repository must not keep a local `limit` default.
Pulse agent write repositories for run/step/eval, evidence packet, candidate,
playbook, and ordinary admission edge/budget mutations use the shared connection
transaction when they own the commit. Missing connection transaction support
fails before agent write SQL; runtime code must not fall back to manual
`self.conn.commit()` compatibility. The evidence packet upsert validates
PostgreSQL `cursor.rowcount=1` with a returned packet row; the separate
`pulse_agent_runs` run-link `UPDATE` also validates rowcount=1 before the agent
run is trusted to reference the packet id/hash.
Pulse evidence packet construction reads source events, enriched events, market
facts, identity facts, and current discussion digest through the formal evidence
source repository contract. Missing source methods are repository/session wiring
failures before a sealed packet exists, not empty evidence or missing digest
data. The packet builder and evidence source repository consume the formal
`PulseCandidateContext` dataclass directly; dict/SimpleNamespace-like context
fallbacks are not part of the runtime contract. Market-fact freshness for the
sealed packet comes from formal
`settings.workers.pulse_candidate.evidence_market_freshness_ms` and the job
run's explicit `now_ms`; the builder and evidence source repository must not
retain local freshness defaults or default-to-current-clock compatibility.
The evidence completeness gate consumes the formal `PulseEvidencePacket`
directly; dict/object reflection, arbitrary `model_dump`, `__dict__`, or
`vars()` compatibility is not part of the worker contract.
The claim evidence verifier consumes the same formal packet and the strict
`FinalDecision` model directly; dict/object final-decision reflection is outside
the worker contract.
The Pulse decision stage builder consumes formal `PulseEvidencePacket` and
`EvidenceCompletenessGateResult` models. JSON context at the model-execution
adapter boundary must be re-validated into those models before the domain
runtime builds prompt input.
Pulse stage-output normalization consumes the formal sealed packet directly
when repairing model event-id fields; dict packet or dict/object evidence-ref
compatibility is malformed adapter wiring, not a supported output shape.
Pulse deterministic eval reads eval-case JSON but must re-validate the embedded
packet into `PulseEvidencePacket` before allowed-ref grading. Partial dict
packets are malformed eval artefacts, not valid evidence.
Pulse request-audit hashes and trace packet/gate metadata are also derived from
a validated `context["evidence_packet"]` and formal
`EvidenceCompletenessGateResult`; top-level `evidence_packet_hash` fallbacks and
raw gate dict payloads are outside the runtime contract.
The runtime manifest must contribute a non-empty `runtime_version` to the same
audit ledger; missing runtime versions fail before agent run metadata is built.
Agent run identity fields (`run_id`, `job_id`, model, artifact hash, workflow,
agent) are also required before request-audit metadata is built; empty identity
strings fail instead of becoming audit placeholders.
The runtime manifest model and artifact hash must match the request-audit model
and artifact hash before the agent run ledger is built.
Claimed `pulse_agent_jobs` rows must provide non-empty `job_id`,
`trigger_signature`, and `timeline_signature` plus a positive `attempt_count`
before Pulse run-id construction or job-service repository sessions. Empty
segments are malformed queue state, not compatibility placeholders.
The Pulse job service writes `pulse_agent_runs` identity from the validated
request-audit payload directly. Missing or mismatched backend, workflow, agent,
artifact, prompt/schema, input hash, trace metadata, runtime version, or
runtime hash is a worker contract failure, not a defaultable ledger field.
Pulse stage audit construction consumes formal `AgentExecutionResult` and
`AgentExecutionRequestAudit` / `AgentExecutionResultAudit` contracts only.
Loose gateway objects or reflective audit attributes fail before run-step audit
rows are produced.
Pulse `AgentStageSpec` construction validates request-audit trace `run_id` and
stage packet group identity before gateway request audit/model execution.
Missing trace metadata or missing packet group identity is malformed runtime
output, not a fallback to the pipeline `run_id`.
Pulse workflow identity is validated when the model-execution adapter is
constructed. Omitted workflow input uses the canonical Pulse workflow constant;
explicit blank or `None` workflow input is malformed wiring, not a defaultable
identity.
No-start provider backpressure/cooldown is driven only by formal
`AgentExecutionError.error_class` and `execution_started=False`; loose audit
dicts or alias exception fields are not job release contracts.
Worker hard-timeout cleanup reads execution-started state only from formal
`AgentExecutionCancelled` or the job service's `run_started` flag. Loose
cancellation audit dicts are not retry/dead classification contracts.
The recommendation clipper, write gate, and cost guard read formal
`PulseGateResult`, `EvidenceCompletenessGateResult`,
`ClaimEvidenceVerificationResult`, and `PulseSourceQualityDecision` fields
directly; malformed gate objects are contract failures, not complete/public or
valid defaults.
Pulse job run-outcome classification also reads the formal
`ClaimEvidenceVerificationResult` directly; unknown-ref outcomes cannot depend
on an optional verifier object fallback.
Signal Pulse public health reads persisted candidate/freshness state through
the formal `PulseReadRepository.freshness_health(...)` contract. Missing method
support is route/session wiring failure; the read service must not probe
`repository.conn`, instantiate the freshness query service directly, or return
empty health for a missing repository contract.
Signal Pulse public list width is the same kind of read boundary:
`SignalPulseService` passes `limit` explicitly into
`PulseReadRepository.list_candidates(...)`, and the repository must not keep a
local `limit=50` default.
Signal Pulse notification candidate discovery is a worker-side read boundary,
not a reuse of public-list cursor pagination. `NotificationRuleEngine` calls
`PulseReadRepository.list_signal_pulse_notification_candidates(...)` once per
evaluation with the configured window, scopes, statuses, and per-scope/status
budget. That repository method materializes scopes/statuses as PostgreSQL
keysets and uses a window rank per scope/status bucket; the rule engine must
not loop over `list_candidates(...)` pages to discover notification work.
Pulse trigger dirty-target repository enqueue, claim, done, error, and
reschedule mutations use the shared connection transaction when the repository
owns the commit. Missing connection transaction support fails before
`pulse_trigger_dirty_targets` SQL, not through manual `self.conn.commit()`
compatibility.
Pulse trigger dirty-target done/error/reschedule write accounting requires real
PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails before
changed-row counts are returned.
Pulse admission claims in `PulseAdmissionRepository` write edge observation,
suppression/admission state, and target/candidate run-budget rows in the same
connection transaction. Missing connection transaction support fails before edge
or budget SQL, not through `nullcontext` compatibility.

`news_page_projection` and `news_source_quality_projection` claim dirty
targets, write their read models, enqueue downstream page dirty work, and mark
dirty targets done/error through `RepositorySession.transaction`; missing
session transaction support is a runtime contract failure before claim/write,
not a `nullcontext` or raw connection transaction fallback.
When News projection dirty targets are terminalized, claimed-row delete and the
`worker_queue_terminal_events` ledger write share a connection transaction;
missing connection transaction support fails before delete/ledger SQL and must
not be treated as a `nullcontext` or manual commit compatibility path.
News projection dirty-target enqueue, claim, done, and error mutations also use
the connection transaction when the repository owns the commit. Missing
connection transaction support fails before `news_projection_dirty_targets` SQL,
not through manual `self.conn.commit()` compatibility.
News projection dirty-target claim rows from `UPDATE
news_projection_dirty_targets ... RETURNING news_projection_dirty_targets.*`
must validate PostgreSQL `cursor.rowcount` against returned rows before
page/source-quality workers treat targets as leased work.
News projection dirty-target completion keys for done, error, delete, and
terminalization must preserve the claimed row's `attempt_count`; missing or
invalid attempt state fails before transaction entry or SQL instead of being
restored to `attempt_count=0`.
News projection dirty-target enqueue and done/error changed-row counts require
PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails before
the repository reports queue enqueue, completion, or retry work. Enqueue paths
must not report candidate `len(records)` as write evidence.
News projection terminal delete paths validate PostgreSQL `cursor.rowcount`
before writing `worker_queue_terminal_events`; rowcount must match returned
deleted rows, and missing, invalid, or mismatched rowcount fails before terminal
counts or terminal ledger rows are reported.

`news_fetch`, `news_item_process`, and `news_item_brief` write News facts,
agent admission/current brief state, run ledgers, projection dirty work, and
claim/failure state through `RepositorySession.transaction`; missing session
transaction support is a runtime contract failure before reconcile, claim, or
write, not a raw connection transaction fallback.
Fresh item-brief ledger/current writes require PostgreSQL single-row
`RETURNING` evidence: `news_item_agent_runs` insert and
`news_item_agent_briefs` current upsert must both have rowcount=1 with a
returned row before page dirty fan-out, audit/current write counts, or
publication eligibility are reported.
When `news_item_brief` reuses an existing completed or failed
`news_item_agent_runs` row, the row must carry a non-empty `run_id` before it can
restore `news_item_agent_briefs` or failed-current state; missing run identity
fails the dirty target rather than falling through to another model execution.
Completed-run validation uses the formal `NewsItemBriefValidationResult`;
provider failure audit uses formal `AgentExecutionRequestAudit` or
`AgentExecutionResultAudit`; market-wide agent admission uses formal
`NewsItemAgentAdmission`. Runtime object reflection, `model_dump` probing, and
`__slots__` fallbacks are not item-brief compatibility surfaces.
Item-brief source-backed entity/domain support reads formal
`NewsItemBriefEntityLane` fields directly from the input packet; it must not
accept loose entity-like objects or recover missing lane fields with
`getattr(..., fallback)`.
The underlying `NewsRepository` default write path follows the same hard cut:
repository-owned source/fetch/provider item/canonical item/deterministic fact,
agent run/brief, source-quality, and page-row mutations must enter a callable
connection transaction before SQL. Worker code passes `commit=False` inside the
outer session transaction instead of relying on repository-owned commits.
NewsRepository changed-row accounting for item lifecycle, source-quality status,
source disable, and page-row mutations requires PostgreSQL `cursor.rowcount`;
missing or invalid rowcount fails before the repository reports zero changed News
work. Configured-source `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *`
upserts must prove rowcount=1 with a returned source row before inserted/updated
source rows are reported. Source disable `UPDATE news_sources ... RETURNING *`
paths must also prove cursor rowcount matches returned disabled rows before
source reconcile or disable counts are reported. Page-row
`RETURNING (xmax = 0)` upserts must prove
rowcount=0/no row for unchanged projections or rowcount=1/row for changed
serving rows. Fetch-run start must prove rowcount=1 for both the
`news_fetch_runs` running-row insert and matching `news_sources.last_fetch_at_ms`
update before returning run ids, and fetch-run
`UPDATE news_fetch_runs ... RETURNING *` finalization must prove rowcount=1 with
a returned run row before `news_sources` status is updated or finalized run rows
are returned. Canonical provider-article/material duplicate edge-remap CTEs must
prove cursor rowcount matches returned old item-id rows before old-item summary
cleanup, dirty-target remap, or affected-item accounting uses those ids.
Canonical edge-remap cleanup zero-edge old `news_items` deletes
must likewise prove `DELETE ... RETURNING` cursor rowcount matches returned
deleted rows before cleanup booleans are reported. Observation summary
`UPDATE news_items ... RETURNING items.*` refreshes must prove rowcount=1 with a
returned current item row before affected-item accounting uses refreshed
source/provider-article aggregates; old zero-edge cleanup paths may observe
rowcount=0/no row only as explicit optional cleanup state, never by fallback
`SELECT` readback.
Old-item representative reselection `UPDATE news_items ... RETURNING items.*`
uses the same optional single-row evidence: rowcount=0/no row is only an
explicit no-representative-edge cleanup result, and rowcount=1/row is the only
valid representative fact refresh before item-scoped derived facts are cleared
or affected-item accounting continues.
`news_item_process` claims `news_items` through `UPDATE news_items ...
RETURNING items.*`; cursor rowcount must match returned claim rows before the
worker treats items as leased for deterministic entity, token, fact, content,
story, admission, retry, terminal, or dirty-target writes.

`notification_rule` writes `notifications` facts and
`notification_deliveries` control rows inside the worker-session
`unit_of_work`; a session that omits `unit_of_work` is a runtime contract
failure, not a reason to manually commit a repository connection.
`NotificationWorker` owns the evaluation timestamp and passes explicit `now_ms`
to `NotificationRuleEngine.evaluate(...)`. The rule engine must not keep a
service-local current-clock fallback.
Notification query windows and overscan budgets are likewise settings-owned:
watched-account activity recency, Signal Pulse page budget, News high-signal
recency, minimum News overscan limit, and News overscan multiplier are read from
`settings.notifications`, not module constants in the rule engine.
External delivery retry budget is owned by
`settings.workers.notification_delivery.max_attempts`; the runtime factory must
pass it into `NotificationWorker`, and direct constructor callers must provide an
explicit value rather than relying on a worker-local default.
It uses insert-only `enqueue_delivery` for newly created notification rows.
Aggregated `news_high_signal` rows that are eligible for external push must
call `enqueue_or_requeue_delivery` so failed/dead `notification_deliveries`
rows can become pending again. A repository/session that lacks that method is a
contract failure; runtime code must not fall back to insert-only enqueue and
silently leave failed deliveries inactive.
Notification fact insertion and insert-only delivery enqueue also treat
`cursor.rowcount` as execution evidence: `0` means an existing/conflicting row
only when PostgreSQL reports that single-row result. Missing, boolean, negative,
multi-row, or otherwise invalid rowcount is malformed repository/driver state,
not a notification-created or delivery-existing decision.
Aggregating an existing notification fact through `UPDATE notifications` is
stricter: `rowcount=1` is the only valid aggregate update result, and missing,
zero, multi-row, or otherwise invalid rowcount fails before `aggregated=True` or
external delivery requeue state is reported.
Notification read-marker writes to `notification_reads` also require real
`cursor.rowcount` evidence. `mark_read` uses single-row evidence, and
`mark_all_read` / `mark_author_read` report bulk counts only when the
`INSERT ... SELECT ... RETURNING` cursor rowcount matches the returned rows,
not from a preselected list length.
When `NotificationRepository` owns a commit outside the worker UoW, notification
fact insertion/aggregation, read-marker writes, and delivery enqueue/requeue
must enter a callable connection transaction before touching `notifications`,
`notification_reads`, or `notification_deliveries`. Missing transaction support
fails before SQL and must not degrade to naked `self.conn.commit()`,
`nullcontext`, or optional transaction probing.
`notification_delivery` claims one pending delivery and records local
validation failures inside `RepositorySession.transaction`. Apprise/PushDeer
provider IO runs after the claim transaction has closed, and delivered/failed
state is recorded in a fresh session transaction. Worker code must not call
`repos.notifications.conn.commit()` directly or let repository-owned delivery
commits replace the worker-session transaction boundary.
Delivery stale-running timeout and terminalization batch size are owned by
`settings.workers.notification_delivery.running_timeout_ms` and
`settings.workers.notification_delivery.stale_running_terminalization_batch_size`.
`DBPoolBundle` passes both into `NotificationRepository` at repository-session
construction; repository code must not keep a local delivery timeout or cleanup
batch default.
Delivery failure/dead-state classification uses the persisted
`notification_deliveries.attempt_count` and `max_attempts` contract directly.
Malformed or missing attempt fields fail as
`notification_delivery_attempt_contract_required` before repository SQL or
worker failure-outcome classification; runtime code must not restore missing
attempt state with local defaults.

## News Provider Operations

News runtime provider support is intentionally smaller than the source
classification vocabulary. The supported provider types are `rss`, `atom`,
`json_feed`, `cryptopanic`, and `opennews`. OpenNews is REST-only inside
`news_fetch`: bounded `/open/news_search` pages catch up by source cursor,
persist provider observations, and merge article facts through deterministic
canonical identity. Public URLs admitted by `public_url_identity_policy` are
hard item identity; generic/homepage/live/feed/preview URLs remain raw/provider
evidence. OpenNews missing-link observations may attach through bounded
material title identity before falling back to provider article id. Short-lived
OpenNews WebSocket subscribe cycles, hybrid fetch mode, and WebSocket policy
keys are rejected rather than kept as compatibility paths. The OpenNews REST
poster is the formal async HTTP contract; `news_fetch` awaits it directly and
does not accept synchronous poster results through `inspect.isawaitable(...)`
or conditional await fallback. The synchronous worker bridge receives and
closes the concrete REST coroutine directly when rejecting active-event-loop
misuse; it must not probe arbitrary awaitables for an optional `close()` method.
OpenNews REST scan budgets are formal source/worker policy: page size comes
from source `rest_limit` or the `news_fetch` fetch limit, page count comes from
source `max_rest_pages`, and overlap comes from source `rest_overlap_ms` or the
durable cursor `overlap_ms`. The integration client must fail missing policy
instead of supplying local page, limit, max-page, or overlap defaults.
`/api/news/sources/status` reports:

- `provider_capabilities.supported_provider_types`
- `provider_capabilities.configured_provider_types`
- `provider_capabilities.unsupported_configured_provider_types`
- `source_hygiene` warnings for unsupported providers, missing coverage tags,
  and degraded/failing source health

`supported_provider_types` comes from the static runtime provider-type
contract, not from the live provider object or a private provider registry.
The route is a read-only diagnostics surface over persisted source state plus
that static contract. The same rule applies to `news_fetch` startup contract
validation and `/api/status` `news_provider_contract`: provider objects fetch
observations; they do not own provider-type capability discovery. The schema
side of that validation comes from `news_sources` database constraint
introspection, not from Python provider-type enums.

Safe operator checklist:

```bash
uv run parallax config
curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
  http://127.0.0.1:8765/api/news/sources/status | jq '.data.provider_capabilities'
```

Only report config paths and booleans from `parallax config`; never
copy provider credentials, cookies, tokens, proxy URLs, or API keys into logs or
docs.
Staged provider waves are:

1. Enable `cryptopanic` when credentials exist, as aggregator/specialist media.
2. Enable `opennews` when `news_intel.opennews.api_token` exists and explicit
   `opennews://subscribe` sources are intentionally enabled. Production crypto
   news coverage is split by provider engine into `opennews-news`,
   `opennews-listing`, and `opennews-onchain`; do not mix OpenNews `market`
   engine rows into the News tape. Use only REST policy keys such as
   `engineTypes`, `hasCoin`, `coins`, `rest_limit`, `max_rest_pages`, and
   `rest_overlap_ms`; `rest_limit`, `max_rest_pages`, and `rest_overlap_ms`
   are required for source-owned OpenNews scan policy. Removed WebSocket keys
   such as `fetch_mode`, `wss_url`,
   `stream_timeout_seconds`, `max_messages`, and `connect_timeout_seconds`
   hard-fail configuration.
3. Add official regulator, exchange, protocol, and issuer RSS/manual API feeds.
4. Add OpenBB/macro/equity adapters only behind explicit ownership boundaries.
5. Add social/community/developer primary-item sources only behind a fresh
   spec; replies, comments, and threads are not a current News storage surface.

## Narrative Intel Hard-Cut Ownership

`narrative_admissions.source_event_ids_json` is the source-set truth for
Narrative Intelligence. Current runtime health expands admitted source sets
from that read model. Existing `token_mention_semantics` and
`token_discussion_digests` rows are legacy read context only; they cannot define
current source volume and no active worker refreshes them. The same event may
count once per current admission/window/scope.

Token Radar remains the scanner. Realtime Narrative Intelligence now writes
only admissions. Public reads may compose historical digest context with the
current admission frontier, but missing or stale legacy digest state must be
reported explicitly instead of triggering an LLM repair path. Token Radar rows
must carry formal `target_type` and `target_id` identity before Narrative
hydration looks up a historical digest; legacy `type` / `id` aliases are not a
runtime read-model compatibility surface.

Writer ownership is narrow: `NarrativeAdmissionWorker` writes
`narrative_admissions`. The former `MentionSemanticsWorker`,
`TokenDiscussionDigestWorker`, narrative LLM provider, narrative prompt files,
and `ops rebuild-narrative-intel` command are removed rather than retained as
disabled compatibility surfaces. HTTP routes and normal worker loops must not
call narrative cleanup or provider paths.
`NarrativeAdmissionWorker` is wake-in only: it listens for
`token_radar_updated` and `resolution_updated`, writes no downstream wake, and
therefore has no `wake_bus` or `wake_emitter` constructor path. Admission limit,
source-set limit, dirty-target lease, retry delay, rank thresholds, and worker
session statement timeout are formal `settings.workers.narrative_admission`
fields. Runtime code must not keep legacy `lease_seconds` /
`error_retry_seconds` compatibility, service-local rank-threshold defaults, or
carry-forward TTL compatibility.
Claimed narrative dirty-target `window` and `scope` values must match formal
worker settings before admission-target or source-set reads; malformed
dimensions fail through dirty-target retry instead of being widened to
all-public or restored to a 24h source window.
Narrative dirty-target done/error/reschedule changed-row counts require
PostgreSQL `cursor.rowcount`; missing or invalid rowcount is malformed
repository/driver state, not zero changed dirty-target work.
Repository-owned `narrative_admissions` upsert and stale-target delete paths
require a callable connection transaction before serving-row SQL; missing
transaction support is a contract failure, not permission to use optional commit
probing or a naked `self.conn.commit()`.
Their returned write counts also require PostgreSQL `cursor.rowcount`; missing
or invalid rowcount is malformed repository/driver state, not zero changed
admission work.

This is a hard cut with no runtime compatibility. Removed settings, source-age
prune behavior, stale digest fallbacks, and old public digest reasons are not
kept as aliases. Public digest missing state is reported through
`discussion_digest.currentness.display_status`: `current`, `updating`, `stale`,
`not_ready`, `out_of_frontier`, or `unsupported_window`. Token Radar API
composition passes the formal nested `target` object into narrative hydration;
it does not synthesize temporary top-level target identity fields.

## Token Radar And Watchlist Maintenance Ownership

`TokenRadarProjectionWorker` is the only runtime writer for
`token_radar_current_rows`, `token_radar_publication_state`, and
`token_radar_target_first_seen`. Token Radar online serving is
`token_radar_current_rows` plus `token_radar_publication_state`. `fresh` is
allowed only when publication state is `ready` and the product/window current
rows are available; an explicitly empty ready publication is fresh with zero
rows. Failed latest attempts serve previous rows as `stale` or no rows as
`failed`. `current_generation_id` remains attempt audit metadata, not an online
serving join key. The compact first-seen read model preserves `listed_at_ms`
while current rows stay small. First-seen upsert accounting requires PostgreSQL
`cursor.rowcount`; candidate `len(records)` is not serving read-model write
evidence.
Serving identity is explicit: target-feature and current-row publication require
`target_type_key` plus `identity_id` before hashing or SQL writes, and unresolved
attention rows use stable lookup-key identity such as `LookupKey/symbol:...`
from formal resolution `lookup_keys_json` instead of `intent_id` or
`display_symbol`. Projection-private target-feature rows missing formal
`target_type_key` or `identity_id` fail before current-row construction instead
of becoming empty serving keys. Target-feature row-id dimensions
(`projection_version`, `window`, `scope`, `lane`), latest event time, and
mapping-shaped factor snapshot payload are also required before current-row
construction; missing private-cache control fields fail instead of becoming
empty row-id segments, `attention` defaults, zero source frontiers, or empty
factor payloads. Current-row `created_at_ms` derives from formal
`last_scored_at_ms`, not target-feature `updated_at_ms` or the runtime wall
clock. Rank-set selection requires formal latest event time and known lane
before window filtering and resolved/attention selection, so malformed rank
inputs cannot disappear as expired or lane-less work. Compact rank inputs also
require `raw_composite_score` and `gates_max_decision`, and ranked rows require
`rank_score` and `recommended_decision`, so missing score/gate/decision fields
cannot become `0.0` or `discard` rank facts. Ranked current-row patching also
requires formal `normalization_status`, `cohort_status`, `cohort_size`,
`cohort_in_cohort`, `cohort_metadata`, complete per-family `factor_ranks`,
`alpha_rank`, `rank`, `rank_score`, `recommended_decision`, and
`latest_event_received_at_ms`; malformed ranked metadata fails before
current-row / `factor_snapshot_json` mutation instead of being repaired to
`no_signal`, `not_ranked`, false cohort membership, empty or incomplete rank
maps, alpha rank `None`, rank `0`, or source watermark `0`. Family rank values
must be `None` or bounded `0..1` ranks. Target-feature cache
writes require formal `lane`, `source_max_received_at_ms`,
`source_event_ids_json`, `created_at_ms`, and `factor_snapshot_json` before
payload hash or SQL, not repository defaults from `attention`,
`computed_at_ms`, empty provenance arrays, or empty factor payloads. They also
require `factor_snapshot_json.composite.rank_score`,
`factor_snapshot_json.composite.recommended_decision`, and
`factor_snapshot_json.gates.max_decision`; missing score or decision output is
not repaired to `0.0` or `discard`. Downstream Pulse Trigger, Narrative
Admission, and Token Profile Current dirty targets derive `source_watermark_ms`
only from positive current-row `source_max_received_at_ms`; malformed source
watermarks fail closed instead of using `computed_at_ms` or projection runtime
time. Current-row delete/upsert,
target-feature write/delete, and target-feature retention write counts require
real PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails as
repository/driver contract drift instead of becoming default zero- or one-row
accounting. Token Radar current-row
`resolution_json` preserves the selected resolution row's non-empty status plus
list-shaped reason/candidate/lookup arrays; malformed resolution fields fail
before publication instead of being repaired to `NIL` or empty arrays.
High-confidence `EXACT` / `UNIQUE_BY_CONTEXT` resolution rows must carry
formal `Asset` or `CexToken` target identity before resolved-lane publication;
malformed target identity fails instead of being downgraded into attention.
Resolved `Asset` target payloads also require formal `asset_identity_current`
explanation fields: non-empty `asset_identity_confidence`, list-shaped
`asset_identity_reason_codes`, and non-negative integer
`asset_identity_conflict_count`; the projection must not turn missing
identity-current evidence into empty reasons or zero conflicts.
Rank-source repair targets, latest-market-context input/output rows,
affected-target output rows, and projection source request target lists also
require formal `target_type_key` plus `identity_id`; legacy `target_type` /
`target_id` aliases fail before edge repair, market-context SQL/result mapping,
source request generation, or target-feature delete/upsert instead of becoming
empty repair work.
Token Radar has no runtime hard-reset command. Legacy derived-storage removal
belongs to migrations, and online repair is handled by the domain projection
path plus explicit Token Radar dirty-target enqueue.
`token_radar_dirty_targets` preserves independent source, market, and repair
dirty kinds. Source-dirty and repair work may rebuild source edges;
market-only work reuses stable `token_radar_rank_source_events` rows and
refreshes only latest market context plus scoring output. Source-edge writes
use content hashes, so unchanged source packets do not rewrite the source-edge
table or downstream current rows.
After due source-event or target dirty work is claimed, Token Radar dirty
projection processing enters one explicit connection transaction before source
edge writes, target-feature writes/deletes, rank-set publication attempts, and
dirty queue done/error terminalization. Worker-level lease claims may be
committed before the processing phase, but the processing/publish/terminal-state
chain is not an autocommit sequence. With PostgreSQL `autocommit=True`,
`commit=False` is only a caller-owned boundary inside that explicit transaction.
Dirty claim width, rank publish width, lease identity, claim lease, and error
retry intervals are runtime worker policy:
`TokenRadarProjectionWorker` reads `settings.workers.token_radar_projection`
`limit`, `lease_ms`, and `retry_ms`, derives `rank_limit` from the same bounded
worker batch policy, uses its canonical worker name as `lease_owner`, and passes
all of them into
`TokenRadarProjection.rebuild_dirty_targets(...)`; the projection service does
not define independent dirty queue or rank-publication defaults.
Private cache retention for `token_radar_target_features` and
`token_radar_rank_source_events` is also owned by `TokenRadarProjectionWorker`.
It is controlled by formal `private_cache_retention_enabled` and
`private_cache_retention_ms` worker settings and executes through bounded
repository prune calls outside rank publication, so `refresh_rank_set` stays
publication-only.
`token_radar_source_dirty_events` is also a required projection input queue:
ingest and resolution reprocess enqueue resolved source-event edges, and
`TokenRadarProjectionWorker` claims that queue on every pass. Missing repository
contract fails closed instead of being interpreted as an empty source queue.
Both enqueue paths consume formal `TokenIntentResolutionDecision` results;
dict-like or loose resolver decision objects are malformed fact-boundary state,
not empty source-dirty work.
Target/source dirty claim completion keys preserve the formal claim-row
contract: target dirty identity is `target_type_key` plus `identity_id`, source
dirty identity is `projection_version` plus `source_event_id` plus
`target_type_key` plus `identity_id`, `attempt_count` must be present and
positive, `lease_owner` must be non-empty, and `payload_hash` must be present
before projection performs rank-source population, source projection, or dirty
done/error completion.
Malformed claims fail as
`token_radar_dirty_claim_identity_contract_required` /
`token_radar_source_dirty_claim_identity_contract_required` /
`token_radar_dirty_claim_attempt_contract_required` /
`token_radar_dirty_claim_lease_owner_contract_required` /
`token_radar_dirty_claim_payload_hash_contract_required`, not as
`attempt_count=0`, empty-owner, or empty-payload completion tokens.
The underlying `token_radar_dirty_targets` and
`token_radar_source_dirty_events` repository completion helpers keep the same
contract for direct repository callers: done/error keys must carry a positive
claimed-row `attempt_count`, non-empty claimed-row `lease_owner`, and claimed
`payload_hash`; they must not restore missing attempts, owners, or payload
hashes through `key.get("attempt_count") or 0`, `key.get("lease_owner") or ""`,
or `key.get("payload_hash") or ""`.
Downstream dirty-target fan-out to Pulse, Narrative Admission, and Token Profile
Current compares previous/current Token Radar rows through required row
`payload_hash` values; missing payload hashes fail before skip decisions instead
of being treated as equal empty signatures.
The worker runtime contract is the formal `settings.workers.token_radar_projection`
object plus DB bundle, optional wake waiter, and optional `wake_emitter`.
Windows, scopes, venues, hot-window cadence, dirty-target batch size, cold
interval, and PostgreSQL statement timeout are direct settings reads. The worker
does not keep product default tuples, local batch/cold-interval fallback values,
or a legacy `wake_bus` constructor alias.
Target/source dirty queue enqueue counts require PostgreSQL `cursor.rowcount`
evidence. Generic dirty enqueue paths must not report candidate `len(records)`
as changed-row counts because conflicts or unchanged rows can make candidate
width diverge from actual queue mutations.
Repository-owned rank-source edge population and prune writes require a callable
connection transaction before `token_radar_rank_source_events` SQL. The
rank-source query helper executes SQL only and does not own commits; dirty
projection paths keep those writes caller-owned inside the explicit projection
transaction. Edge population changed counts require explicit SQL aggregate
count rows, and prune changed counts require PostgreSQL `cursor.rowcount`;
missing or invalid mutation-count evidence is malformed query/driver state, not
default zero-edge accounting.
Repository-owned Token Factor Evaluation single and batch upserts require a
callable connection transaction before `token_score_evaluations` SQL. Batch
upserts keep each row write caller-owned with `commit=False` inside that outer
repository transaction. Evaluation diagnostics read family IC/coverage from the
formal v3 `families.*.score` blocks and do not use `composite.family_scores` as
a compatibility source. Score-evaluation settlement subject `target_type` must
be formal `Asset` or `CexToken`; direct market-tick target types `chain_token`
and `cex_symbol` are not settlement subjects. Asset score-evaluation settlement
requires subject-owned `chain` and `address`; `chain_id` and `asset_address`
are not fallback identity sources. CEX score-evaluation settlement requires
subject-owned `provider` and `native_market_id`; market context is not a
fallback identity source.
Watched-account token alerts are produced by ingest after deterministic
resolution and first-seen checks. Ingest writes `account_token_alerts` with
`commit=False` inside `EvidenceRepository.unit_of_work`; repository-owned alert
inserts require a callable connection transaction before SQL and cannot fall
back to manual `self.conn.commit()`. `INSERT ... DO NOTHING` alert-created vs
existing-row classification requires PostgreSQL single-row `cursor.rowcount`
evidence; missing, boolean, negative, multi-row, or otherwise invalid rowcount
is malformed repository/driver state, not an alert state.
Token intent rebuild and resolution reprocess entrypoints enter
`RepositorySession.transaction` before rewriting token evidence/intents,
lookup keys, resolution rows, discovery lookup dirty rows, identity evidence,
or Token Radar source-dirty rows. Missing session transaction support fails
before rebuild/reprocess writes; runtime code must not replace that boundary
with direct `repos.conn.commit()`. `TokenIntentResolver` has no commit flag and
does not commit resolution rows itself; persistence belongs to the caller-owned
session transaction.
Repository-owned token fact writes enforce the same lower-level contract:
`TokenEvidenceRepository`, `TokenIntentRepository`,
`TokenIntentLookupRepository`, and `IntentResolutionRepository` require callable
connection transactions before token evidence, intent/evidence-link,
lookup-key, or resolution SQL. `IntentResolutionRepository` enters the
transaction before `pg_advisory_xact_lock`, so current-resolution serialization
cannot run on a no-transaction fake or autocommit-only path.
Those repositories also require PostgreSQL `cursor.rowcount` evidence before
returning or accounting token facts. Evidence/intent/resolution upserts use
`RETURNING *` with rowcount=1; intent-evidence `ON CONFLICT DO NOTHING` links
are valid only as rowcount 0/1; lookup-key replacement deletes require real
non-negative rowcount and each replacement upsert requires rowcount=1. Missing
or invalid rowcount is malformed repository/driver state, not a successful
write proven by fallback `SELECT`.
When the source dirty repository owns a commit, enqueue, claim, done, and error
mutations enter the connection transaction first. Missing connection transaction
support fails before `token_radar_source_dirty_events` SQL, not through manual
`self.conn.commit()` compatibility.
When the target dirty repository owns a commit, target enqueue, market enqueue,
claim, recent-resolved catch-up enqueue, market-current enqueue, done, and error
mutations enter the connection transaction first. Missing connection transaction
support fails before `token_radar_dirty_targets` SQL, not through manual
`self.conn.commit()` compatibility.
Target/source dirty queue mutation paths that return changed-row counts require
real PostgreSQL `cursor.rowcount` evidence for enqueue, completion, retry, and
catch-up accounting; missing or invalid rowcount is malformed repository/driver
state, not default zero-row queue work.

Watchlist overview has no current runtime writer; it is a public read path over
durable `events` plus token-resolution facts. The API read config owns the
public overview window and sample budgets. `WatchlistIntelRepository` requires
explicit `source_limit` and `cluster_limit`, computes window metrics through
bounded aggregate SQL, and loads only a bounded source-event sample before token
resolution fan-out and cluster construction. The repository must not keep a
hidden `limit=500` default or an unbounded per-handle event scan.

## IngestService Boundary

`IngestService` writes the first durable facts in a single transaction:
`events`, `event_entities`, `token_evidence`, `token_intents`,
`token_intent_lookup_keys`, `token_intent_resolutions`,
`registry_assets`, `asset_identity_evidence`,
`asset_identity_current`, `market_ticks`, and `enriched_events`. Repository-owned
raw-frame input observation, event-entity fact edge, token evidence,
intent/evidence-link, lookup-key, current resolution, registry asset, and asset
identity evidence/current mutations require a callable connection transaction
before SQL; asset_identity_current `RETURNING true AS changed` booleans require
PostgreSQL rowcount evidence matching returned-row presence before
`rows_written` is reported; token evidence, intent, lookup-key, evidence-link,
and current-resolution facts require the token fact repository rowcount
contracts described above before returned rows or rewrite accounting are trusted;
ingest keeps them caller-owned inside its unit of work.
`RegistryRepository` also requires connection transaction support before
repository-owned CEX token, price-feed, and US equity symbol mutations; those
required upserts must return through `RETURNING` rowcount=1 plus a returned row,
not post-write readback.
Resolved source-event edges enqueue `token_radar_source_dirty_events` in the
same transaction from formal `TokenIntentResolutionDecision` results only; that
repository contract is required and must not be treated as an optional
compatibility hook, and dict/object decision fallbacks are not ingest contracts.
`IngestService` does not construct missing repositories from `evidence.conn`;
missing repository-session fields are runtime wiring errors that must fail
before facts or control rows are written.

Inline event capture writes Tier 3 `market_ticks(source_tier='tier3_inline')`
and matching `enriched_events`. When an event anchor cannot be attached
from a fresh existing tick, ingest writes an `enriched_events` pending
fact and enqueues `event_anchor_backfill_jobs` control-plane work.
The pending job active window is an explicit runtime setting:
`_PooledIngestStore` and `IngestService` receive
`settings.workers.event_anchor_backfill.active_window_ms` from the
composition root. They must not keep a service-local `300_000` millisecond
default or any other ingest-layer fallback for event-anchor lifetime.
Later event-anchor backfill attach/terminal lifecycle writes classify
`enriched_events` state changes from PostgreSQL single-row `cursor.rowcount`
evidence; missing, boolean, negative, multi-row, or otherwise invalid rowcount
is malformed repository/driver state, not a pending-anchor no-op.

`IngestService` is transactional. It is called by `collector`; it is not
a `WorkerBase` subclass and does not get a `workers.yaml` key.

## Market Capture Lanes

Market capture has several lanes by design. This does not violate the
single-writer rule because `market_ticks` is an append-only fact table,
not a read model. Shared market tick fact inserts classify created versus
deduped ticks only from PostgreSQL cursor rowcount evidence matching
`RETURNING tick_id` row presence; returned-row presence alone is not execution
evidence.

- `token_capture_tier` writes the rebuildable control projection that
  assigns active targets to Tier 1 stream, Tier 2 poll, or Tier 3
  inline-only capture. Dirty target claim, tier row write/demotion, and dirty
  target done state must share `RepositorySession.transaction`; missing session
  transaction support fails before claim/write, not through manual commit
  compatibility. Tier upsert changed booleans require PostgreSQL rowcount
  evidence matching `RETURNING` row presence before worker `rows_written` is
  reported.
- `market_tick_stream` owns Tier 1 OKX DEX WebSocket capture. It accepts
  only `chain_token` targets from `token_capture_tier(tier=1)`. Each bounded
  stream cycle closes the async price iterator through direct `aclose()`;
  iterators without `aclose()` are malformed stream contracts, not no-op
  cleanup-compatible objects.
- `market_tick_poll` owns Tier 2 REST capture for DEX and CEX targets.
  It is the steady-state REST quote worker.
- `market_tick_current_projection` is the single runtime writer for
  `market_tick_current`. It claims durable dirty targets, selects the
  latest append-only tick by `(observed_at_ms, received_at_ms, tick_id)`,
  and enqueues Token Radar market dirty work only when the visible
  current row changes. Current-row changed booleans require PostgreSQL
  rowcount evidence matching `RETURNING` row presence before downstream dirty
  enqueue or wake decisions are reported.
- `market_tick_current_dirty_targets` enqueue, claim, done, and error
  mutations use the connection transaction when the repository owns commit.
  Missing connection transaction support fails before queue SQL, not through
  manual `self.conn.commit()` compatibility.
- `event_anchor_backfill` owns short-lived event-anchor catch-up. It
  consumes `event_anchor_backfill_jobs`, attaches a persisted nearby tick
  first, calls providers only inside the configured lag budget, and then
  terminalizes work. Stale cleanup must use worker-session `unit_of_work`;
  missing UoW support is a runtime contract failure before terminal writes, not
  a manual commit fallback. Repository terminal paths require a connection
  transaction before writing `event_anchor_backfill_jobs` terminal state or the
  worker terminal ledger; missing transaction support is not a `nullcontext`
  compatibility path. Temporary retry, done, and terminal guards require the
  positive `attempt_count` returned by claim; missing attempt state is malformed
  worker state, not attempt zero. `enriched_events` attach and terminal
  lifecycle writes require PostgreSQL single-row `cursor.rowcount` evidence, so
  malformed driver evidence cannot be classified as no changed anchor row.
- Queue Terminal operator actions over `worker_queue_terminal_events` are
  platform control-plane transitions. Retry/archive/quarantine resolution uses
  `SELECT ... FOR UPDATE` and must run with a callable connection transaction;
  missing transaction support fails before row-lock or operator-action SQL, not
  through `nullcontext` or manual commit compatibility. Platform terminal ledger
  source-row writes also use the same connection transaction when
  `terminalize_source_row(..., commit=True)` owns the commit; they must not
  fall back to naked `conn.commit()`. Terminal ledger `INSERT ... ON CONFLICT
  ... RETURNING *` writes and operator-action `UPDATE ... RETURNING *` writes
  require PostgreSQL cursor rowcount evidence that is valid 0/1 and matches
  returned-row presence before terminal rows, operator payloads, or retry
  transitions are reported.
  `terminalize_source_row(...)` writes terminal evidence only from formal source
  row fields: explicit `attempt_count` is a caller-owned override, otherwise the
  source row must expose a non-negative `attempt_count`; existing terminal rows
  and generation queries must expose a positive `terminal_generation`. Missing
  attempt or generation state is a platform contract failure, not a default of
  `0` or `1`. Repository callers that pass deleted/returned queue rows into the
  terminal ledger must not pre-convert missing `attempt_count` to an explicit
  `0` override.
- Queue Terminal retry transitions requeue target work only through formal
  session repositories (`discovery`, `event_anchor_jobs`, or `pulse_jobs`).
  Missing retry repository support rolls back the terminal action and is not an
  optional queue capability discovered by repository probing.
- `resolution_refresh` terminalizes exhausted lookup claims by deleting
  claimed `token_discovery_dirty_lookup_keys` rows and writing terminal ledger
  evidence in the same connection transaction. Missing connection transaction
  support fails before delete or ledger SQL; runtime code must not fall back to
  `nullcontext` or manual commit compatibility. The terminal event payload hash
  is read from the deleted queue source row; missing or blank source payload hash
  is malformed terminal evidence and fails before ledger SQL. Terminal delete
  rowcount must match returned deleted lookup rows before terminal counts or
  `worker_queue_terminal_events` rows are reported.
- `DiscoveryRepository` ordinary repository-owned lookup queue/result
  mutations - enqueue, claim, done, reschedule, start, finish, and fail - also
  require a callable connection transaction before SQL. They are the
  `resolution_refresh` control-plane state machine, not isolated convenience
  commits, so missing transaction support fails before queue/result writes.
  Due-lookup claim rowcount must match returned claim rows; start/fail result
  writes require `RETURNING *` rowcount=1 with a row, and finish writes require
  rowcount=1 before running/found/error result state is reported.
- `resolution_refresh` worker state transitions for lookup running, finish,
  fail, and claim completion use `RepositorySession.transaction`. Provider IO
  remains outside the transaction, but state writes must not fall back to direct
  `repos.conn.commit()` or raw connection transactions. Retry-budget decisions
  use the claimed row `attempt_count` directly and must not treat missing
  attempt state as zero attempts.
- Token intent rebuild/reprocess rewrites token facts, lookup keys, resolution
  rows, discovery dirty lookup rows, identity evidence, and Token Radar
  source-dirty rows inside `RepositorySession.transaction`. Missing session
  transaction support fails before SQL, not through direct `repos.conn.commit()`.
  Resolution reprocess batches selected intent evidence through the intent
  keyset; it must not query token evidence once per reprocessed intent.
  Resolution reprocess source-dirty enqueue reads formal
  `TokenIntentResolutionDecision` fields directly; object-reflection
  compatibility for resolver decisions is not part of the worker contract.
- News projection terminalization deletes claimed `news_projection_dirty_targets`
  rows and writes terminal ledger evidence in the same connection transaction.
  Missing connection transaction support fails before delete/ledger SQL; runtime
  code must not fall back to `nullcontext` or manual commit compatibility.
- `pulse_candidate` terminalizes stale, exhausted, failed, and timeout-cancelled
  `pulse_agent_jobs` rows by writing job terminal/dead state and
  `worker_queue_terminal_events` evidence in the same connection transaction.
  Stale exhausted running-job terminalization uses the formal
  `settings.workers.pulse_candidate.stale_running_terminalization_batch_size`
  budget rather than a repository-local batch default. Missing connection
  transaction support fails before job or ledger SQL; runtime code must not fall
  back to `nullcontext` or manual commit compatibility.
- `pulse_candidate` job enqueue, success marking, running-job release, and stale
  agent-run cleanup use a connection transaction when the repository owns the
  commit. Missing connection transaction support fails before job/run SQL;
  runtime code must not fall back to manual `self.conn.commit()` compatibility.
  Single-row `pulse_agent_jobs` `RETURNING` mutations validate cursor rowcount
  against returned-row presence before job state, retry/dead classification, or
  terminal ledger effects are reported.
- `pulse_candidate` admission claims update `pulse_candidate_edge_state`,
  `pulse_target_run_budget`, and `pulse_candidate_run_budget` in one connection
  transaction. Missing connection transaction support fails before edge or budget
  SQL; runtime code must not fall back to `nullcontext` compatibility.
- `macro_view_projection` publishes changed `macro_observation_series_rows`
  current rows, the current `macro_view_snapshots` row, and dirty-target done
  state in one `RepositorySession.transaction`. Missing session transaction
  support fails before dirty-target claim. Failure after claim rolls back
  partial projection writes before retry state is recorded, and
  `macro_view_snapshot_updated` is emitted only after the transaction exits.
  The repository-level current-row refresh still requires connection
  transaction support before current-row delete/insert or publication-state SQL;
  runtime code must not fall back to `nullcontext` compatibility. Existing
  current-series rows use `payload_hash` as the required change signature; a
  missing hash fails before delete/insert instead of comparing as an empty
  signature.
- `live_price_gateway` reads latest persisted `market_ticks` and fans out
  WebSocket updates. It does not call upstream price providers and never
  writes market facts. Target selection and tick freshness bounds come from
  `settings.workers.live_price_gateway.target_limit` and
  `target_ttl_seconds`, not worker-local constants or constructor overrides.
  The fan-out publisher is the formal async WebSocket hub `publish(payload)`
  contract; synchronous callback results are malformed runtime wiring and must
  not be accepted through `inspect.isawaitable(...)` fallback.
- `collector` receives GMGN DirectWS frames through the formal async
  `CollectorService.handle_frame(...)` contract. The DirectWS adapter awaits
  that handler directly; synchronous frame callbacks are malformed runtime
  wiring and must not be accepted through conditional await fallback.

## Worker Manifest Runtime Boundary

Worker manifests declare the durable contract: inputs, owned fact/control
tables, read-model identities, provider IO, wakes, and advisory locks. Runtime
code must follow those declarations directly; there is no partial runtime
contract object or constructor-time contract injection.

Claim-driven workers keep the order explicit in their own `run_once` flow:

```text
claim due control rows -> load bounded payload -> provider IO outside DB session -> persist terminal/result rows
```

Provider IO must happen outside DB sessions and transactions. Projection and
terminal writes use fresh worker sessions or transactions owned by the worker
that owns the manifest entry. Architecture tests verify manifest identities,
dirty-target ownership, provider-IO classification, and the absence of hidden
worker lifecycle allowlists.

Configured streaming providers must expose `connection_state_payload()` as a
runtime contract, not as optional diagnostics. Worker degraded notes, readiness,
ops diagnostics, and provider adapters call that hook directly. A missing hook
or non-object payload is reported as failed provider state so wiring errors do
not masquerade as disabled/configured connections.

Account-quality backfill is ops-only maintenance, not a manifest worker. It is
still the single writer for `account_profiles`, `account_token_call_stats`, and
`account_quality_snapshots` derived from upstream facts, so its batch reads and
writes must share one callable connection transaction. Missing transaction
support fails before backfill SQL; it must not fall back to a naked
`conn.commit()` on an autocommit connection. `AccountQualityRepository`
repository-owned profile, directory-entry, token-call-stat, and snapshot writes
require the same callable connection transaction before SQL. Backfill and GMGN
directory sync keep repository writes caller-owned inside their outer
transaction. The backfill `limit` is an explicit CLI/caller budget, not a
service-local default.
directory sync keep repository calls caller-owned with `commit=False` inside
their outer maintenance transaction.

Asset Market route/profile/symbol sync services are also maintenance write
paths, not request-time read helpers. Binance route/profile and Nasdaq Trader
symbol provider reads happen outside DB transactions; the resulting
`cex_tokens`, `price_feeds`, `cex_token_profiles`, and equity symbol registry
writes share a callable connection transaction. Missing transaction support
fails before registry/profile writes rather than falling back to a naked
`conn.commit()`. Binance CEX profile provider output is a formal mapping record
with required `base_symbol`, `provider`, `symbol`, `logo_url`, `source_ref`, and
mapping-shaped `raw_payload`; object-attribute reflection, missing-provider
defaults, symbol-from-base fallbacks, and empty raw-payload defaults are
malformed provider output rather than a runtime compatibility lane. The
underlying `RegistryRepository` route/feed/symbol mutation
defaults and `CexTokenProfileRepository` source-cache mutation defaults enforce
the same connection-transaction contract before SQL when the repository owns the
commit. `RegistryRepository` route/feed/symbol upserts also require
`RETURNING *` rowcount=1 plus a returned row before facts are returned, so
fallback readback cannot stand in for PostgreSQL write evidence.
`CexTokenProfileRepository` also validates optional single-row
`RETURNING` rowcount evidence for `cex_token_profiles`: rowcount=0/no row is the
only valid no-existing-token outcome, rowcount=1/row is the only valid write
outcome, and mismatches fail before rows are reported. US equity symbol deactivation changed-row counts from
`UPDATE ... RETURNING symbol` require cursor rowcount evidence and matching
returned symbols; missing, invalid, or mismatched rowcount is malformed
repository/driver state, not a returned-symbol count.

CLI ops repair/sync commands are not worker loops, but execute-mode writes use
the same PostgreSQL boundary. Token Radar dirty repair, token-capture-tier
rank-set repair, News canonical rebuild enqueue, and GMGN directory sync enter a
callable connection transaction before mutating queues or account directory
rows. Token-capture-tier rank-set repair windows must be explicit valid windows;
helpers must not restore malformed windows to `24h`. Dry-runs stay read-only;
News projection dirty repair reads only the item key/watermark/admission-status
columns needed for page/brief dirty enqueue, and source-quality-only repair
does not scan `news_items`.
GMGN directory provider iteration is completed before DB writes begin. Ops commands that instantiate one-shot workers still use
the runtime lifecycle root: temporary DB bundles close via `db.aclose()`, and
manually acquired advisory locks release via the formal `release()` contract.
One-shot asset-market workers that wire providers locally close the whole
provider bundle through `AssetMarketProviders.aclose()`; they must not duplicate
provider-field ownership or optional `close()` probing in the CLI surface.
One-shot worker commands read `settings.workers.<name>` directly for worker
timeouts and advisory lock keys. Missing worker settings blocks are malformed
runtime configuration, not CLI-local defaults. One-shot commands that construct
a worker acquire the advisory key from the worker's `_advisory_lock_key()`
method, not a CLI fallback to `SINGLE_WRITER_KEY`.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker`, `EventAnchorBackfillWorker` | `MarketTickCurrentProjectionWorker` | `{target_type, target_id}` |
| `market_tick_current_updated` | `MarketTickCurrentProjectionWorker` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `NarrativeAdmissionWorker`, `PulseCandidateWorker` | `{window, scope}` |
| `news_item_written` | `NewsFetchWorker` | `NewsItemProcessWorker`, `NewsPageProjectionWorker` | `{source_id, count}` |
| `news_item_processed` | `NewsItemProcessWorker` | `NewsItemBriefWorker`, `NewsPageProjectionWorker` | `{count}` |
| `news_item_brief_updated` | `NewsItemBriefWorker` | `NewsPageProjectionWorker` | `{count}` |
Wake payloads are hints only. Consumers re-read DB on wake and catch up
on their configured cadence. `DBPoolBundle` owns wake emission and
listener construction through `wake_emitter()` and `wake_listener()`.
Domain workers never call `pg_notify` directly. Wake connections must expose
callable `commit`; listeners must also expose callable `notifies`. Missing
wake-pool connection support is a runtime contract failure, not a silent
local-wait fallback. When a worker receives an injected wake object and a wake
is due, the required `notify_*` or `wake()` method is part of that runtime
contract; a malformed injected object must fail visibly rather than becoming a
silent missed hint. A missing wake object may still mean no low-latency hint,
with interval catch-up preserving correctness.
Wake emitters also require the formal wake-pool connection context factory:
`WakeBus` enters the returned context before `pg_notify` and commits the
checked-out connection. A raw connection returned from the factory is malformed
runtime wiring, not a compatibility lane.
The wake pool size is derived from `worker_manifest.py` wake listeners plus
their formal `settings.workers.<name>` blocks. Missing runtime settings shape
must fail as configuration wiring, rather than shrinking the wake pool to the
minimum as if no listeners existed.

Adding a wake channel requires all of these in one change:

- emitter call through `WakeBus`;
- listener `wakes_on` entry in `workers.yaml`;
- a bounded `interval_seconds` catch-up path;
- a row in this table;
- tests for missed-wake recovery when practical.

## Lifecycle And Supervision

- `WorkerBase` owns the common run loop, timeout/backoff handling,
  `run_once()` execution, advisory lock acquisition, status payloads,
  queue-depth hooks, pool-wait metrics, and close semantics.
- Single-writer advisory lock handles must be the formal
  `DBPoolBundle.acquire_advisory_lock_connection()` shape. `WorkerBase`
  releases them through required `release()` support and does not fall back to
  `close()`-only handles.
  When a worker declares `SINGLE_WRITER_KEY`, `WorkerBase._advisory_lock_key()`
  reads the formal `settings.workers.<name>.advisory_lock_key` field; missing
  settings are malformed runtime configuration, not permission to fall back to
  the class constant.
- `runtime.bootstrap()` constructs `Runtime.workers` from `WorkerManifest v1`
  factory ownership and replaces unavailable or disabled workers with disabled
  `WorkerBase` placeholders so status payloads always contain the same keys.
  If startup fails after the `DBPoolBundle` is created, bootstrap unwinds
  through `db.aclose()` rather than closing individual pool attributes.
  During `DBPoolBundle.create()` itself, partial pool cleanup calls formal
  synchronous pool `close()` directly and records cleanup failures on the
  original create exception. Runtime shutdown keeps the same underlying pool
  contract: `DBPoolBundle.aclose()` is awaitable by its owner, but each pool
  `close()` must return `None`; awaitable close results are malformed wiring.
  Checked-out worker/advisory-lock connections that must be discarded are
  closed directly and returned through `pool.putconn(conn)`; private pool
  discard hooks are not compatibility contracts.
- Injected wake waiters expose `wake()`, `async_wait(...)`, and synchronous
  `close() -> None` directly. WorkerBase must not accept awaitable or non-None
  close results as alternate wake-waiter lifecycle shapes.
- `WorkerScheduler.start()` starts enabled workers in manifest priority
  order. `WorkerScheduler.stop()` awaits worker `stop()`, waits for tasks,
  cancels stragglers, awaits worker `aclose()`, and awaits the `DBPoolBundle`
  through direct `db.aclose()`. Synchronous or non-awaitable lifecycle hook
  results are malformed runtime wiring. The bundle owns individual pool close
  order and requires synchronous pool `close() -> None`; the scheduler must
  not use `_maybe_await(...)`, `inspect.isawaitable(...)`, or probe
  `api_pool`, `worker_pool`, `lock_pool`, `tool_pool`, or `wake_pool` as
  shutdown compatibility fallback.
  Scheduler liveness and startability are derived from direct
  `status_payload()` calls, including unhealthy reason details, so disabled
  and unavailable placeholders must be proper `WorkerBase` instances rather
  than ad hoc objects with partial status attributes. API dependency helpers read worker objects through
  `runtime.scheduler.workers` and validate scheduler/worker status payload
  shapes before answering liveness or returning a worker object for a route.
- Worker timeout settings are layered. `soft_timeout_seconds` is an
  overrun signal owned by `WorkerBase`; it records active task age and
  keeps waiting for the same `run_once()` task. `hard_timeout_seconds`
  is a cooperative cancellation boundary; the worker cancels, awaits
  cleanup, and only then may start another `run_once()`. Agent lane
  `timeout_seconds` is a provider execution boundary inside
  `AgentExecutionGateway`. `statement_timeout_seconds` is the final SQL
  guard for synchronous DB work.
- `WorkerBase` does not provide hidden defaults for core worker cadence or
  retry behavior. It reads `settings.enabled`, `settings.interval_seconds`, and
  `settings.backoff.base_ms/max_ms` directly; malformed worker settings fail
  visibly instead of becoming enabled workers with local 5-second intervals or
  1s/60s backoff defaults.
- Wake waiters use a dedicated single-thread executor for PostgreSQL
  `LISTEN` waits and are closed through `WorkerBase.aclose()`. They do
  not share the event loop default executor with other `to_thread` work. A
  missing `wake_waiter` means local interval sleep only; an injected waiter must
  expose `wake()`, `async_wait(...)`, and synchronous `close() -> None` directly
  rather than being treated as an optional-shape compatibility object or
  awaited close result.
- WebSocket fan-out is presentation-only and bounded per client. A slow
  subscriber can be dropped, but it must not block worker publish paths
  or other subscribers. Public replay has the same bounded-read contract:
  replay count, subscription filter cardinality, and per-filter token replay
  query budgets are capped before API-pool PostgreSQL reads begin; token-filter
  replay uses one PostgreSQL keyset/window query for the selected `cas` and
  `symbols`, then replay payload hydration batches projected event payload
  reads for the page.
- Non-continuous workers must have a finite `hard_timeout_seconds`.
  `collector` is the only zero-hard-timeout worker because it is a
  continuous stream lifecycle with its own snapshot gate and watchdog.
  Its injected upstream client must expose `aclose()` as the formal
  lifecycle contract; shutdown does not accept `close()` fallback.
  Its GMGN DirectWS frame handler is the collector's async `handle_frame(...)`
  contract and must not accept synchronous callback fallback.
  Provider bundle shutdown is rooted at `WiredProviders.aclose()`;
  bootstrap/runtime cleanup must not recursively scan provider object
  graphs or provider-bundle gateway aliases for close methods.
  Worker-owned provider handles use the provider protocol's lifecycle method
  directly, such as Pulse `decision_client.aclose()` and News fetch
  `feed_client.close()`, without cross-shape fallback.
  Market stream iterator cleanup follows the same rule for the per-cycle
  iterator returned by `iter_price_info().__aiter__()`: direct `aclose()`,
  no optional async-close probing.
- `/readyz`, `/api/status`, and `ops worker-status` expose worker state
  under `workers` and lane aggregate state under `worker_lanes`. `workers`
  is keyed by manifest worker name; `worker_lanes` is keyed by manifest lane
  (`ingest`, `identity_market_fact`, `projection`, `agent`, `notification`,
  `maintenance_cache`). `collector.details` carries collector counters,
  including `snapshot_gate_outcomes`; `snapshot_gate` is a global health field
  copied from those counters.
- Queue observability is owned by `app.runtime.queue_health`. It reads only
  manifest-declared dirty target, job, delivery, and status queue tables and
  emits per-worker and per-lane `queue_health` with status, due/running/failed
  and blocked counts, oldest due/running ages, and max attempts. It is not a
  supervisor and does not mutate queue rows.
- Runtime knobs live in `~/.parallax/workers.yaml`. The
  application/provider config in `config.yaml` must not contain worker
  interval, batch, concurrency, lease, max-attempt, soft/hard timeout,
  advisory lock, or wake-channel settings.

## Agent Execution Plane

LLM-backed workers use one shared `AgentExecutionGateway` per process.
The gateway is an operational control plane only: it owns lane bulkheads,
request/result audit envelopes, timeout, circuit breaker, structured JSON
object execution, application-side validation, and ops status. It does
not claim domain jobs, write domain queues, or persist product read
models.

The low-level `LLMGateway` is transport-only. It owns redacted LiteLLM
configuration, shared model policy, and lifecycle cleanup. Concrete provider
calls live in `integrations/model_execution`; gateway objects do not construct
provider SDK clients or expose worker/stage execution limits.

Current lanes are configured under `workers.agent_runtime` in
`workers.yaml`. `agent_runtime.defaults.model` is the single global
agent model default; any lane can override `model` locally and otherwise
inherits that default. Current lanes are `pulse.decision` and
`news.item_brief`. News fact candidates are deterministic outputs of
`news_item_process`, not a separate LLM lane. Attempt-burning workers reserve
capacity before claiming DB work:

Provider wiring for a known lane reads the formal lane settings directly.
The Pulse decision provider takes its pipeline timeout from
`workers.agent_runtime.lanes["pulse.decision"].timeout_seconds`; a missing
lane or missing timeout is malformed runtime configuration, not a local
120-second fallback. The low-level `LiteLLMPulseDecisionClient` does not
expose a provider timeout budget; only the provider adapter may surface the
configured lane timeout to domain orchestration.

`agent_runtime.defaults.model` and lane `model` select the registered model
capability profile. The profile owns provider family, client-validation
retry count, and provider request options such as DeepSeek thinking-mode
disablement. Structured output has a single runtime path: provider JSON
object mode plus application-side Pydantic validation. Lane overrides may
set `provider_family` and `client_validation_retries` for an unregistered
or experimental model; they merge with the registered profile when the
model is known. Example DeepSeek lane override:

```yaml
agent_runtime:
  lanes:
    pulse.decision:
      model: deepseek-v4-flash
```

Repository defaults keep lane controls separate from the model choice: all
agent lanes inherit `agent_runtime.defaults.model` unless an operator
intentionally overrides a lane. The production default is DeepSeek:

```yaml
agent_runtime:
  defaults:
    model: deepseek-v4-flash
    provider_family: deepseek
  lanes:
    pulse.decision:
      priority: high
```

- `pulse_candidate` reserves `pulse.decision` before `pulse_agent_jobs`
  claim. The decision reservation owns the global slot and lane bulkhead
  for the single `pulse_decision` provider call.
- Signal Pulse builds a domain-owned cost guard after evidence packet
  construction and before LLM execution. Evidence-hard-blocked jobs finish
  with deterministic audit only; source-quality-hidden and non-public paths skip
  LLM execution; public trade/watch candidates run the single decision stage.
- `news_item_brief` reserves `news.item_brief` before claiming a brief dirty
  target. No-start backpressure does not claim, burn attempts, or write an
  agent run ledger; provider-started validation failures write
  `execution_started=true`.

`news_item_process` computes deterministic entities, token mentions, fact
candidates, content class, market scope, and story identity, persists them, and
then reads the agent-admission context back through the News repository. Missing
or incomplete context is a repository/transaction contract failure and must fail
closed through the item-process retry/terminal path; worker-memory fallback
context is not a runtime compatibility surface. News page and item-brief dirty
enqueue must also pass raw item ids through
`repos.news.servable_news_item_ids(...)`; a missing servable filter contract
fails closed instead of enqueueing raw ids.

If reservation is denied, the worker records `agent_backpressure_*` in its
iteration notes and does not claim a job, so no-start backpressure does not
burn attempts or write business run ledgers. Batch LLM workers must reserve
explicit `rate_units` before claim and must cap the claim limit to the actual
`reservation.rate_units` returned by the gateway. A worker that can still
observe a provider no-start exception after claim must release/reschedule the
dirty row without writing a business run ledger and without counting it as a
provider attempt.

Lane `priority` is an operator-facing policy label used in diagnostics
and incident triage. It is not a strict scheduler; fairness still comes
from explicit global concurrency, lane bulkheads, RPM limits, and domain
queue cadence.

## Layered State Machines

Worker bugs often look confusing because several state machines are
visible at once:

- provider connection state describes upstream IO health;
- collector snapshot-gate counters describe frame completeness;
- fact lifecycle describes durable observations;
- control-plane job status describes scheduling and retries;
- projection status describes read-model freshness;
- business decision state describes product output and audit results.

These layers are allowed to coexist. They conflict only if one layer
tries to answer another layer's question. See `WORKER_FLOW.md` for the
full state-machine map and debugging playbook.

## Adding A Worker

When introducing a new worker, do all of the following in the same
change:

1. Implement the worker as a `WorkerBase` subclass with a canonical
   `name`, typed worker settings, injected `DBPoolBundle`, telemetry,
   and any narrow provider protocols it needs. Put business work in
   `run_once()`.
2. Add a `WorkerManifest` entry with lane, kind, class path, start priority,
   input/ordering contracts, write ownership, idempotency evidence, side-effect
   ledgers when applicable, queue-depth table when applicable, and wake
   channels. If the worker performs upstream provider, subprocess, filesystem,
   or network IO, set `uses_provider_io=True` and update this file's
   `provider-io-worker-keys` marker. Add a matching `WorkersSettings` field and
   default `workers.yaml` block, then construct the worker in the owning domain factory under
   `app/runtime/worker_factories/`.
3. Add a row to this file's worker inventory.
4. Add or update the wake channels table here if the worker introduces a
   channel, and add its `wakes_on` list to `workers.yaml` when it listens
   for wake hints.
5. Document the worker in the owning domain's `ARCHITECTURE.md` stage
   map.
6. If the worker writes a new derived table, declare its lifecycle class
   (`current`, `private_cache`, `control_ledger`, or `audit_fact`) and name
   its single writer in `ARCHITECTURE.md`. Current read models must use stable
   product/window keys, not run/generation/attempt/timestamp/UUID identity, and
   unchanged projections must write zero serving rows. Worker-owned projection
   services must receive claim width, publish width, lease timing, retry timing,
   and lease owner explicitly from the worker/settings boundary; services must
   not keep hidden batch-size or synthetic-owner defaults.
7. Extend architecture guards so `WorkerBase`, `WorkerManifest`,
   `WorkersSettings`, the default `workers.yaml`, and this file's
   `worker-inventory-keys` marker stay in lockstep.

## Update Triggers

Update this file in the same change as any of:

- A new worker class or removal of an existing one.
- A worker gaining or losing a wake-in or wake-out channel.
- A worker gaining or losing upstream provider/subprocess/file IO.
- A provider IO worker lifecycle contract changing, including collector
  upstream `aclose()` ownership.
- Provider bundle cleanup ownership moving between `WiredProviders`,
  runtime gateway roots, or worker-owned provider handles.
- CLI ops one-shot asset-market provider bundle cleanup ownership moving away
  from `AssetMarketProviders.aclose()`.
- Worker-owned provider lifecycle contracts changing, including async
  decision clients or synchronous News source providers.
- Market stream iterator lifecycle contracts changing, including per-cycle
  async iterator `aclose()` ownership.
- Provider wiring wrapper or startup partial-cleanup lifecycle contracts
  changing, including fallback/serialized provider `close()` ownership.
- `DBPoolBundle.create()` pool construction or partial-pool cleanup lifecycle
  contracts changing.
- DBPoolBundle worker/advisory-lock connection discard lifecycle contracts
  changing.
- A change to a catch-up cadence default.
- A worker moving between domains.
- A new `NOTIFY` channel name or hint payload shape.
- A read model gaining a new runtime writer or losing its declared writer.
- A control-plane table becoming part of a worker's scheduling contract.
