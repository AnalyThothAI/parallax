# Worker Flow

> **Scope.** Beginner-friendly runtime map for worker data flow,
> worker lifecycle, layered state machines, and debugging. The canonical
> worker inventory lives in `WORKERS.md`; package boundaries live in
> `ARCHITECTURE.md`; operational invariants live in `RELIABILITY.md`.

Use this document when a worker problem feels confusing. It explains
which state is truth, which state is scheduling, and which state is only
an IO health signal.

## Mental Model

This service is not a pure message bus. It is a PostgreSQL-first
Kappa/CQRS pipeline:

```text
GMGN public stream
  -> collector receives provider frames
  -> IngestService writes facts in PostgreSQL
  -> market and identity workers refresh more facts
  -> projection workers rebuild read models
  -> API, WebSocket, CLI, Pulse, and notifications read those models
```

The most important rule:

```text
PostgreSQL facts are truth.
Read models are rebuildable views.
NOTIFY is only a wake hint.
Provider frames are inputs, not product facts.
```

When investigating behavior, do not start with the WebSocket payload or
the UI row. Start by asking: which fact table should contain the truth,
which worker writes it, and which read model should project it?

## Primary Runtime Flow

The hot path from one public-stream frame to product output is:

```text
1. CollectorService.handle_frame
   - parses the GMGN frame
   - applies the snapshot gate
   - writes raw_frames through a repository-owned connection transaction
   - calls IngestService for each normalized Twitter event

2. IngestService transaction
   - is constructed from formal `RepositorySession` repositories; missing token evidence, token intent, resolution, discovery, market tick, enriched event, event-anchor job, or source-dirty repositories fail as wiring errors before writes
   - writes events and event_entities
   - repository-owned raw-frame and event-entity writes require connection transaction before SQL; full event ingest keeps entity writes caller-owned inside `EvidenceRepository.unit_of_work`; `raw_frames`, `events`, and `event_entities` `INSERT ... DO NOTHING` state/count classification requires PostgreSQL single-row `cursor.rowcount` evidence instead of bare/default rowcount compatibility
   - extracts token_evidence
   - creates token_intents and lookup keys
   - writes current token_intent_resolutions
   - repository-owned token evidence, intent, lookup-key, and resolution writes require connection transaction before SQL; ingest/rebuild/reprocess paths keep them caller-owned inside `unit_of_work` or `RepositorySession.transaction`
   - token evidence, intent, and resolution upserts require `RETURNING *` plus PostgreSQL rowcount=1 before facts are returned; intent-evidence `ON CONFLICT DO NOTHING` links accept only rowcount 0/1; lookup-key replacement deletes require real non-negative rowcount and each replacement upsert requires rowcount=1 instead of fallback readback
   - writes account_token_alerts for watched-account resolved token mentions; ingest keeps alert writes caller-owned with `commit=False` inside `EvidenceRepository.unit_of_work`, repository-owned alert inserts require connection transaction before SQL, and `INSERT ... DO NOTHING` state classification requires PostgreSQL single-row `cursor.rowcount` evidence instead of bare/default rowcount compatibility
   - enqueues token_radar_source_dirty_events for resolved source-event edges from formal `TokenIntentResolutionDecision` results only; loose or dict-like resolver decisions fail before source-dirty enqueue
   - writes registry_assets and asset_identity_evidence/current
   - repository-owned registry asset, CEX route, price-feed, US equity symbol, and asset identity evidence/current writes require connection transaction before SQL; registry asset/CEX token/price-feed/US equity upserts require `RETURNING` rowcount=1 plus a returned row before facts are returned; asset_identity_current `RETURNING true AS changed` booleans require PostgreSQL rowcount evidence matching returned-row presence before `rows_written` is reported
   - writes inline market_ticks when a fresh event-adjacent tick exists
   - writes enriched_events for the event anchor lifecycle; backfill attach/terminal lifecycle classification requires PostgreSQL single-row `cursor.rowcount` evidence and does not treat missing driver evidence as a no-op
   - enqueues event_anchor_backfill_jobs when the anchor is pending

3. Asset Market workers
   - token_capture_tier commits its `token_capture_tier_dirty_targets` lease claim before ranking active market targets into stream, poll, or inline-only lanes, so projection failure cannot roll back the attempt counter; dirty rank-set enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from row-level `source_max_received_at_ms`, legacy `source_watermark_ms`, `0`, or runtime `now_ms`; tier writes/demotions and dirty target done/error/terminal state share the following `RepositorySession.transaction`, with exhausted attempts copied to `worker_queue_terminal_events`; tier upsert changed booleans, tier demotion, and repository-owned dirty target enqueue/done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-work accounting, and tier `RETURNING true AS changed` rowcount must match returned-row presence before worker `rows_written` is reported
   - market_tick_stream writes Tier 1 WebSocket market_ticks
   - market_tick_poll writes Tier 2 REST market_ticks
   - shared append-only market tick inserts classify created vs duplicate facts
     from PostgreSQL cursor rowcount matching `RETURNING tick_id` row presence,
     not from returned-row presence alone
   - market_tick_current_projection claims `market_tick_current_dirty_targets`, writes `market_tick_current` only when the latest visible tick changes, and enqueues Token Radar market dirty work; repository-owned dirty target enqueue/claim/done/error mutations require connection transaction before queue SQL, done/error completion keys require positive claimed-row `attempt_count` without zero-attempt fallback, retry cadence and retry budget come from formal worker settings, exhausted claims are deleted with `RETURNING queue.*` and terminalized in `worker_queue_terminal_events`, enqueue plus done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-target or candidate-count accounting, and current-row `RETURNING true AS changed` booleans require rowcount evidence matching returned-row presence before downstream dirty enqueue or wake decisions are reported
   - event_anchor_backfill finishes short-lived pending event anchors; temporary retry and terminal/done guards require positive claimed-row `attempt_count` without zero-attempt fallback, `event_anchor_backfill_jobs` `UPDATE ... RETURNING` paths require cursor rowcount evidence matching returned rows before claim results, terminal ledger writes, retry rows, reconcile counts, or booleans are reported, and `enriched_events` attach/terminal lifecycle writes require PostgreSQL single-row `cursor.rowcount` evidence instead of default no-op accounting
   - resolution_refresh discovers and reprocesses NIL / AMBIGUOUS lookups; affected-intent reprocess writes token resolution/lookup/discovery/source-dirty rows inside `RepositorySession.transaction` and only enqueues source-dirty edges from formal `TokenIntentResolutionDecision` results, so loose resolver decision objects fail before dirty enqueue; lookup claim lease, running timeout, hot not-found retry, claim batch, retry budget, and reprocess limit come from `settings.workers.resolution_refresh`; due work is consumed through `claim_due_lookup_keys(...)`, not a read-only due-list repository helper; repository-owned registry asset writes require connection transaction before SQL and `RETURNING` rowcount=1 plus a returned row before facts are returned; DiscoveryRepository repository-owned lookup queue/result enqueue/claim/done/reschedule/start/finish/fail mutations require connection transaction before SQL and receive due/claim/start timing explicitly rather than through repository-local policy constants; lookup queue enqueue/done/reschedule changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-work accounting; lookup claim done/reschedule/terminal completion keys require positive claimed-row `attempt_count` without zero-attempt fallback plus non-empty `lease_owner` and claimed `payload_hash`, and worker retry-budget decisions read the same claimed attempt contract; lookup running/finish/fail/claim completion writes also share `RepositorySession.transaction`, while terminal lookup-claim delete and terminal-ledger writes share a connection transaction and require the deleted source row `payload_hash` without empty-string fallback
   - TokenIntentResolver is deterministic resolver logic only; it has no commit flag and writes resolution rows only through caller-owned repository-session transactions
   - asset_profile_refresh claims provider-scoped `asset_profile_refresh_targets` before provider calls and writes provider profile source caches; ready/missing/error source-cache refresh cadences and matching target reschedule due times come from formal `settings.workers.asset_profile_refresh` and are passed explicitly into worker service/repository calls; refresh-target enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from source-cache `updated_at_ms` or runtime `now_ms`; repository-owned refresh-target enqueue/claim/reschedule/error mutations require connection transaction before queue SQL, reschedule/error completion keys require positive claimed-row `attempt_count` without zero-attempt fallback, reschedule/error changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-target accounting, repository-owned `asset_profiles` ready/status writes require connection transaction before source-cache SQL, and worker profile writes use `RepositorySession.transaction` with `commit=False`
   - asset market route/profile/symbol sync reads providers outside DB transactions; repository-owned registry CEX token, price-feed, and US equity symbol writes require connection transaction before SQL; their upserts require `RETURNING *` rowcount=1 plus a returned row before route/feed/symbol facts are returned; US equity symbol deactivation changed-row counts from `UPDATE ... RETURNING symbol` require cursor rowcount evidence that matches returned symbols
   - token_image_mirror claims `token_image_source_dirty_targets` and mirrors exact provider logo URLs into local cached files; image-source dirty enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from target-level `observed_at_ms`, source-row `updated_at_ms`, or runtime `now_ms`; repository-owned image source dirty enqueue/claim/done/error mutations require connection transaction before queue SQL, done/error completion keys require positive claimed-row `attempt_count`, non-empty claimed-row `lease_owner`, claimed `payload_hash`, and claimed `source_url_hash` without rederiving it from `source_url`, done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-target accounting, repository-owned `token_image_assets` lifecycle writes require connection transaction before image-row SQL and PostgreSQL single-row rowcount evidence, pending/ready image asset RETURNING paths require rowcount to match returned-row presence, worker terminal image writes use `RepositorySession.transaction` with `commit=False`, both dirty-source retry and image-asset retry cadence come from formal worker `retry_ms`, and dirty-source retry budget comes from formal worker `max_attempts` before exhausted claims are deleted and terminalized in `worker_queue_terminal_events`
   - token_profile_current claims `token_profile_current_dirty_targets` and projects public profile/icon facts from exact persisted sources loaded through `RepositorySession.source_query` plus ready local image rows; profile dirty enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from `computed_at_ms`, `updated_at_ms`, tuple target identity, or runtime `now_ms`; image-source admission for Token Image Mirror uses only positive source-row `observed_at_ms` as the image dirty `source_watermark_ms` and does not repair it from `updated_at_ms` or runtime `now_ms`; repository-owned profile dirty claim/done/error mutations require connection transaction before queue SQL, done/error completion keys require positive claimed-row `attempt_count` without zero-attempt fallback, retry cadence and max-attempt budget are formal worker settings, exhausted claims are deleted and terminalized in `worker_queue_terminal_events`, done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-target accounting, repository-owned `token_profile_current` upserts require connection transaction before serving-row SQL, RETURNING changed booleans require rowcount evidence matching returned-row presence, projection/upsert rows use formal `quality_flags_json` and `source_payload_json` storage fields without old `quality_flags` / `source_payload` aliases, and public reads treat malformed present current rows as projection damage instead of downgrading them to pending state or empty JSON
   - live_price_gateway reads `token_capture_tier` control rows and latest market_ticks, then fans out cache-only WebSocket updates

4. Token Intel projection
   - token_radar_projection claims token_radar_dirty_targets and uses bounded interval catch-up
  - it also claims token_radar_source_dirty_events; missing queue repository contracts fail closed rather than being treated as no source work
  - dirty target/source claim width, rank publish width, lease identity, claim lease, error retry interval, and retry budget are formal `settings.workers.token_radar_projection` worker policy; the worker passes `limit`, `rank_limit`, `lease_owner`, `lease_ms`, `retry_ms`, and `max_attempts` explicitly to projection processing, and `TokenRadarProjection` does not keep service-local dirty queue or rank-publication policy constants
  - projection-private cache retention for token_radar_target_features and token_radar_rank_source_events is a bounded `TokenRadarProjectionWorker` maintenance lane controlled by formal `private_cache_retention_enabled` / `private_cache_retention_ms` settings; `refresh_rank_set` does not run retention prune work
  - generic target/source dirty enqueue keys are formal queue commands: generic target dirty enqueue requires `target_type_key` / `identity_id`, and source dirty enqueue requires `source_event_id` / `target_type_key` / `identity_id`; repositories fail alias-only or blank rows before payload hash or queue SQL instead of silently skipping them
  - target/source dirty claim completion keys require formal claimed-row identity before rank-source or projection work: target dirty claims use `target_type_key` / `identity_id`, and source dirty claims use `projection_version` / `source_event_id` / `target_type_key` / `identity_id`
  - target/source dirty claim completion keys also require positive `attempt_count`, non-empty `lease_owner`, and present `payload_hash` from the claimed row before rank-source or projection work; missing claim state fails as malformed instead of producing alias-derived identity, `attempt_count=0`, empty-owner, or empty-payload done/error keys
   - target/source dirty repository done/error completion helpers require the same formal identity, positive claimed-row `attempt_count`, non-empty claimed-row `lease_owner`, and claimed `payload_hash`; they do not restore missing identity, attempts, owners, or payload hashes through `key.get(...)` aliases or empty defaults
   - target/source dirty error completion receives formal `max_attempts` and `worker_name`; claims that reach the retry budget are deleted with `RETURNING queue.*` and written to `worker_queue_terminal_events` in the same projection transaction rather than being rescheduled indefinitely
   - dirty queue enqueue conflict paths reset `attempt_count` only when the effective `payload_hash` / work payload changes; a new work payload must not inherit an old failed retry budget, while same-payload retry scheduling preserves existing attempt accounting
   - downstream dirty fan-out skip decisions for Pulse, Narrative Admission, and Token Profile Current require previous/current Token Radar row `payload_hash`; missing hashes fail instead of comparing as empty signatures
   - source dirty event repository-owned enqueue/claim/done/error mutations require a connection transaction before queue SQL
   - target dirty repository-owned enqueue/market-enqueue/claim/catch-up-enqueue/done/error mutations require a connection transaction before queue SQL
   - target/source dirty queue mutation counts for enqueue, done, error, retry, market-current, and catch-up paths require PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails before the repository reports changed-row counts, and generic dirty enqueue paths must not report input `len(records)` as write evidence
   - downstream dirty-target enqueue for Pulse, Narrative Admission, Token Profile Current, Asset Profile Refresh, and Token Capture Tier uses formal repository-session attributes directly; missing downstream repos fail the projection transaction instead of silently skipping wake/dirty enqueue
   - after due source-event or target dirty claims are acquired, source-edge writes, target-feature writes/deletes, rank-set publication attempts, and dirty queue done/error terminalization share one explicit connection transaction; `commit=False` is not a delayed commit boundary unless that transaction is active
   - source/market/repair dirty kinds decide whether source edges must rebuild or whether existing source edges can be reused
   - it builds compact source edges and projection-private token_radar_target_features from material facts
   - target-feature and current-row identity is formal `target_type_key` plus `identity_id`; projection-private target-feature rows missing formal identity, row-id dimensions (`projection_version`, `window`, `scope`, `lane`), latest event time, `last_scored_at_ms`, or mapping-shaped `factor_snapshot_json` fail before current-row construction instead of becoming empty serving keys, empty row-id segments, `attention` defaults, zero source frontiers, runtime-clock timestamps, or empty factor payloads; rank-set selection also requires formal `latest_event_received_at_ms`, known `lane`, compact `raw_composite_score`, compact `gates_max_decision`, ranked `rank_score`, and ranked `recommended_decision` before filtering/picking rows, so malformed rank inputs cannot disappear as expired or lane-less work and cannot become `0.0`/`discard` rank facts; unresolved attention rows use stable `LookupKey/symbol:...` identity from formal resolution `lookup_keys_json`, never event/intent-scoped or display-symbol fallback
   - ranked current-row patching requires formal ranked metadata (`normalization_status`, `cohort_status`, `cohort_size`, `cohort_in_cohort`, `cohort_metadata`, complete per-family `factor_ranks`, `alpha_rank`, `rank`, `rank_score`, `recommended_decision`, and `latest_event_received_at_ms`) before mutating current rows or `factor_snapshot_json`; malformed rank publication output fails instead of becoming `no_signal`, `not_ranked`, false cohort membership, empty/incomplete rank maps, alpha rank `None`, rank `0`, or source watermark `0`, and family rank values must be `None` or bounded `0..1` ranks
   - target-feature cache writes require formal projection payload fields (`lane`, `source_max_received_at_ms`, `source_event_ids_json`, `created_at_ms`, and `factor_snapshot_json`) before payload hash or SQL; repository code does not repair malformed rows with `attention`, `computed_at_ms`, empty provenance arrays, or empty factor snapshots, and it also requires `factor_snapshot_json.composite.rank_score`, `factor_snapshot_json.composite.recommended_decision`, and `factor_snapshot_json.gates.max_decision` instead of repairing missing score/decision output to `0.0` or `discard`
   - downstream Pulse Trigger, Narrative Admission, Token Profile Current, Asset Profile Refresh, and Token Capture Tier dirty targets derive `source_watermark_ms` only from positive current-row `source_max_received_at_ms`; malformed source watermarks fail closed instead of using `computed_at_ms`, `0`, or projection runtime time. Pulse Trigger and Narrative Admission dirty repositories also require positive producer-supplied watermarks before queue SQL and keep no zero-watermark enqueue compatibility branch
   - Token Radar current-row `resolution_json` preserves the selected resolution row's non-empty status plus list-shaped reason/candidate/lookup arrays; malformed resolution fields fail before publication instead of becoming `NIL` or empty arrays
   - `token_radar_target_first_seen` is the compact first-seen read model for `listed_at_ms`; its upsert changed-row accounting requires PostgreSQL `cursor.rowcount` evidence instead of projection candidate `len(records)`
   - high-confidence `EXACT` / `UNIQUE_BY_CONTEXT` resolution rows must carry formal `Asset` or `CexToken` target identity before resolved-lane publication; malformed target identity fails instead of being downgraded into attention
   - resolved `Asset` target payloads require formal `asset_identity_current` explanation fields: non-empty `asset_identity_confidence`, list-shaped `asset_identity_reason_codes`, and non-negative integer `asset_identity_conflict_count`; missing identity-current evidence fails instead of becoming empty reasons or zero conflicts
   - rank-source repair targets, latest-market-context input/output rows, affected-target output rows, and projection source request target lists require formal `target_type_key` plus `identity_id`; alias-only `target_type` / `target_id` targets fail before edge repair, source request generation, market-context SQL/result mapping, or target-feature delete/upsert instead of being silently skipped or repaired
   - repository-owned rank-source edge population/prune writes require a connection transaction before `token_radar_rank_source_events` SQL; the rank-source query helper executes SQL only and does not own commits, and its mutation counts require explicit SQL aggregate rows or PostgreSQL `cursor.rowcount` instead of default zero-edge accounting
   - market-only work overlays fresh latest market context on stable source packets instead of rehydrating every source event
   - it publishes one stable generation into token_radar_current_rows and token_radar_publication_state for online reads; repository-owned publication/target-feature/first-seen/failure writes require a connection transaction before SQL, publication enters that transaction before `pg_advisory_xact_lock`, and current-row plus target-feature write counts come from required PostgreSQL `cursor.rowcount` evidence rather than default zero/one-row estimates
   - projection_offsets and projection_runs repository-owned control-plane writes require a connection transaction before SQL; publication paths keep them caller-owned inside the explicit projection transaction, ordinary offset/run mutations require exactly one PostgreSQL `cursor.rowcount`, projection-run `start_run` uses `INSERT ... RETURNING *` without `run_by_id` readback proof, and stale-running cleanup accounting requires PostgreSQL `cursor.rowcount` evidence instead of default zero abandoned-run counts
   - projection work comes only from the domain-specific source-event and target dirty queues; there is no generic projection dirty-range queue, and diagnostic reads over projection_runs require explicit caller limits
   - rank-set publication uses compact rank inputs and `_compact_rank_key`; retired snapshot-row sort helpers such as `_rank_key`, invalid-snapshot demotion, and `raw_alpha_score` fallback are not kept as compatibility code
   - emits token_radar_updated as a wake hint

5. Narrative Intelligence read models
   - narrative_admission claims `narrative_admission_dirty_targets`, validates claimed `window`/`scope` against formal worker settings, then reads exact Radar/material facts and writes current source-set admissions; malformed dimensions fail through dirty-target retry instead of widening scope or falling back to 24h; dirty done/error/reschedule completion keys require positive claimed-row `attempt_count` without zero-attempt fallback, done/error/reschedule changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-row accounting, and serving-row admission upsert/stale-delete counts require the same rowcount evidence instead of default zero-admission accounting; admission thresholds come from formal worker settings and the service keeps no carry-forward TTL compatibility
   - the former mention semantics and discussion digest LLM workers are removed from the runtime harness
   - semantic/digest tables and readers are removed; there is no legacy context fallback
   - API routes expose only admission-derived `narrative_admission` status, coverage, and data gaps

6. Consumers
   - Pulse claims `pulse_trigger_dirty_targets`, validates claimed `window`/`scope` against formal worker settings, exact-loads Token Radar rows, gates candidates, runs the agent, and writes audit rows; malformed dimensions fail through dirty-trigger retry instead of becoming all-public timeline reads; trigger done/error/reschedule completion keys require positive claimed-row `attempt_count` without zero-attempt fallback, done/error/reschedule changed-row counts require PostgreSQL `cursor.rowcount` evidence instead of default zero-row accounting, Pulse agent run/step/runtime/eval audit writes, public candidate upsert/hide, admission edge-state, candidate edge-budget, and playbook snapshot `RETURNING` writes require cursor rowcount to match returned-row presence before rows or booleans are reported, unchanged candidate/playbook projections are rowcount=0/no-row rather than fallback `SELECT`, stale `pulse_agent_runs` timeout cleanup counts require the same rowcount evidence instead of default zero-run accounting, and Pulse job terminal/dead `UPDATE ... RETURNING` batches require cursor rowcount to match returned rows before terminal ledger writes; the retired playbook-outcome table/writer is absent and run outcomes stay in the run audit ledger
   - Pulse job enqueue requires the worker to pass formal `settings.workers.pulse_candidate.max_attempts` into `PulseJobsRepository.enqueue_job(...)`; the repository does not own a fallback retry budget
   - Pulse low-information gates hide stale public rows through the Pulse candidates repository; missing hide support fails the dirty trigger
   - Pulse dirty-trigger claim, admission/edge/public visibility writes, job enqueue, and dirty terminal updates share `RepositorySession.transaction`; missing session transaction support fails before claim/write
   - Pulse agent run, eval, candidate, playbook, admission, and job terminal writes share `RepositorySession.transaction`; missing session transaction support fails before writes
   - Pulse evidence packets do not read Narrative admission/digest projections
   - notifications evaluate candidates and enqueue deliveries
   - API / WebSocket / CLI read public read models
   - frontend renders generated contract payloads
```

## Worker Lifecycle

Every long-running worker is a `WorkerBase` subclass and is owned by
`WorkerScheduler`.

```text
runtime.bootstrap()
  -> DBPoolBundle.create()
  -> wire_providers()
  -> construct_workers()
  -> WorkerScheduler.start()
  -> worker.run()
  -> optional advisory lock
  -> run_once()
  -> WorkerResult and status metrics
  -> wait interval_seconds or wake hint
  -> repeat until stop
  -> WorkerScheduler.stop()
  -> await worker.stop(), task cancellation, await worker.aclose(), await DBPoolBundle.aclose()
```

`run_once()` is the business boundary. The common runtime owns looping,
timeouts, backoff, status payloads, advisory locks, and close semantics.
Domain workers should keep external provider IO outside DB sessions and
should use `DBPoolBundle.worker_session()`.
Single-writer workers acquire advisory lock handles from `DBPoolBundle` and
`WorkerBase.aclose()` releases them through the handle's required `release()`
method; `close()`-only lock objects are not a compatibility path.
For workers that declare `SINGLE_WRITER_KEY`, `WorkerBase._advisory_lock_key()`
reads the formal `settings.workers.<name>.advisory_lock_key` field; the class
constant is not a runtime fallback when settings are missing.
`WorkerScheduler.stop()` also treats worker `stop()`, worker `aclose()`, and
`DBPoolBundle.aclose()` as formal async lifecycle contracts: it awaits each one
directly and does not use `_maybe_await(...)` or `inspect.isawaitable(...)`
fallbacks for synchronous hook results.
Injected wake waiters also use direct method contracts: `wake()` wakes,
`async_wait(...)` waits, and synchronous `close() -> None` closes the waiter.
An awaitable close result is malformed wake-waiter wiring.
Ops commands that instantiate a one-shot worker follow the same lifecycle
contracts: close the temporary `DBPoolBundle` through `db.aclose()` and release
manually acquired advisory locks through `release()`. One-shot commands that
wire asset-market providers also close the provider bundle through
`AssetMarketProviders.aclose()`; they do not enumerate provider fields or probe
individual `close()` methods. One-shot commands also read the relevant
`settings.workers.<name>` block directly for statement timeouts, advisory lock
keys, and worker-specific knobs; missing worker settings are malformed runtime
configuration, not permission to synthesize defaults in the CLI surface. When a
one-shot command constructs a worker and needs its single-writer advisory lock
key, it calls the worker's formal `_advisory_lock_key()` method directly; a bare
`SINGLE_WRITER_KEY` attribute is not a separate CLI compatibility contract.
During `DBPoolBundle.create()` itself, partially created pools are cleaned up
through direct synchronous `close()` calls; malformed partial pools are startup
cleanup evidence, not optional close-compatible shapes.
During runtime shutdown, `DBPoolBundle.aclose()` is the async owner boundary but
the pool contract underneath is still synchronous `close() -> None`; awaitable
or non-`None` close results are malformed DB lifecycle wiring.
When worker-session reset or advisory-lock release fails after checkout,
discarding the connection follows the psycopg pool path directly:
`conn.close()` then `pool.putconn(conn)`. Pool-private close-return helpers are
not part of the runtime contract.

Timeout supervision is explicit:

```text
idle
  -> active
  -> soft_timed_out
  -> hard_cancelling
  -> cleanup_persisted
  -> backoff
  -> active
```

`soft_timed_out` means the current `run_once()` exceeded its expected
duration; it is not an interrupt and it must not start overlapping work.
`hard_cancelling` is cooperative cancellation: `WorkerBase` cancels and
awaits the in-flight task. Domain workers then persist their own
`cleanup_persisted` step, such as returning a claimed job to pending,
failing an agent run audit row, or backing off a digest target, before
they re-raise cancellation.

## Why Workers Break

Most worker incidents in this repo have come from one of these boundary
mistakes, not from PostgreSQL or asyncio being mysterious:

- A worker lets control-plane state answer a product question. Queue rows,
  run rows, active-generation pointers, and provider connection state can
  explain work, but they are not public truth.
- A current read model uses run/generation/attempt/timestamp/UUID identity.
  Macro became slow because projection lifecycle identity was modeled as
  ever-growing generations instead of stable series/window keys with a
  compact publication state. The fix is a hard cut to stable current rows:
  unchanged projections write zero serving rows.
- An idle loop discovers work by scanning broad fact/read-model history.
  Runtime loops should claim durable dirty targets, process bounded target
  batches, and stop when the queue is empty. Broad discovery belongs to an
  explicit ops repair command that enqueues dirty targets. Dry-run repair may
  read counts without a transaction, but execute-mode dirty enqueue requires a
  connection transaction before any repair scan or queue write.
- Ops-only read-model maintenance has the same transaction rule when it writes
  product state. `AccountQualityBackfillService` is not a runtime worker, but
  its replay of upstream facts into account profiles, token-call stats, and
  quality snapshots must enter one callable connection transaction before
  backfill reads or writes. A naked `conn.commit()` is not a batch boundary on
  an autocommit PostgreSQL connection. Its `limit` is supplied explicitly by
  the ops command/caller, not by a service-local default. `AccountQualityRepository`
  repository-owned profile, token-call-stat, directory-entry, and snapshot
  writes also require a callable connection transaction before SQL; backfill and
  GMGN directory sync keep those writes caller-owned with `commit=False`.
- Asset Market sync services follow the same split: provider/client reads for
  Binance routes, Binance CEX profiles, and Nasdaq Trader symbol files happen
  outside DB transactions, while registry/profile writes enter one callable
  connection transaction. Repository-owned `cex_token_profiles` source-cache
  writes also require a callable connection transaction before SQL. Binance CEX
  profile sync consumes formal mapping-shaped provider rows with required
  identity, provider, URL, source reference, and raw payload fields; object
  attribute reflection, provider/symbol fallbacks, and `{}` raw-payload defaults
  are malformed provider output, not compatibility. Missing transaction support
  fails before writes, not through naked `conn.commit()` compatibility.
- CLI ops execute commands follow the same rule. Dry-run commands remain
  read-only, but token-radar dirty repair, token-capture-tier rank-set repair,
  News canonical rebuild enqueue, and GMGN directory sync use a callable
  connection transaction for execute-mode writes. GMGN directory client
  iteration is materialized before the DB transaction opens. Token-capture-tier
  rank-set repair windows are resolved through the same explicit window contract
  as projection code; malformed helper inputs fail instead of becoming `24h`
  repair scans.
- A worker writes while holding the wrong boundary open. Provider, publisher,
  wake-wait, file, subprocess, and network IO must run outside DB worker
  sessions; only materialization and persistence belong inside sessions.
- A worker treats the repository-session transaction as optional. Missing
  `unit_of_work`, `transaction`, `require_transaction`, or session query support
  is a runtime contract failure; it must not fall back to `nullcontext`, raw
  `conn.transaction()`, manual commits, or worker-local query construction.
  Repository terminal paths that write control state plus terminal ledgers have
	  the same rule: missing connection `transaction` support fails before writes.
	  Current read-model repository writers that publish rows plus publication state
	  also require the connection transaction before delete/insert/update SQL.
	  Macro current-snapshot JSON sections are formal writer output; missing
	  `panels_json`, `indicators_json`, `triggers_json`, `data_gaps_json`,
	  `source_coverage_json`, `features_json`, `chain_json`, `scenario_json`, or
	  `scorecard_json` must fail before current snapshot payload hash/upsert rather
	  than being restored by repository `{}` or `[]` defaults.
	  CEX board/detail read-model writers apply the same rule to skipped or failed
	  attempt-state updates; empty or all-failed runs are not a side-channel outside
	  `RepositorySession.transaction`. CEX detail writer fields
	  (`target_type`, `target_id`, `exchange`, `native_market_id`) are required
	  before current snapshot construction, payload hash, or upsert;
	  missing native market or target identity must not be hidden as a skipped
	  detail row, `cex_token:unknown`, `CexToken`, or `binance`. The persisted
	  current-row key is `(exchange, native_market_id)`; target identity remains
	  required lookup metadata and no synthetic snapshot identifier is stored.
	  The detail builder receives exchange as an explicit worker/provider input,
	  so it does not own a local `binance` fallback for market identity or source
	  refs.
	  Token Case/Search Inspect may return structured missing CEX detail state,
	  but missing read-model rows must not synthesize `exchange`; that market
	  identity field belongs only to persisted detail snapshots.
	  Detail snapshot read methods require non-empty target or market query
	  identity before SQL, so malformed read keys do not become empty-string
	  PostgreSQL probes.
	  CEX board current identity (`period`, `target_id`, `native_market_id`) is
	  required before board key construction, row-id hashing, payload hash, or
	  upsert; empty strings are malformed writer output, not PostgreSQL-compatible
	  product keys.
	  Binance OI provider wiring must map formal integration DTO fields into the
	  domain provider DTOs, and Binance OI provider sequences must contain those
	  formal provider DTO fields (`symbol`, ticker/funding metrics, and OI
	  history values/timestamps); malformed integration or provider objects are
	  provider-adapter contract failures and must not be converted to empty board
	  metrics through `getattr(..., None)` compatibility.
	  CEX board payload hashes use provider-observed market freshness only; worker
	  computed fallback timestamps and successful empty-board attempt times are
	  attempt/publication metadata, not serving-row content signatures.
	  CEX board delete/upsert write counts must come from PostgreSQL
	  `cursor.rowcount`; missing or invalid rowcount is malformed driver/wiring
	  state, not a repository default write count.
	  CEX detail snapshot upsert write counts follow the same rule; missing or
	  invalid cursor rowcount fails before the repository returns publication
	  counts.
	  Macro sync window terminal/retry/failure, `macro_sync_state` repair,
	  `macro_projection_dirty_targets` enqueue/done/error, and
	  `macro_observation_series_rows` delete/upsert counts likewise require
	  PostgreSQL `cursor.rowcount` evidence. Missing or invalid rowcount is
	  malformed driver/wiring state, not zero Macro work or inferred
	  target/row length success; single-row sync/state writes reject multi-row
	  counts. Macro sync-window enqueue/claim `RETURNING` paths validate
	  rowcount against returned-row presence before reporting enqueued,
	  no-work, or claimed control state. `macro_view_snapshots` uses
	  `projection_version` as its sole current-row key, with no synthetic snapshot
	  identifier. `macro_view_snapshots` and
	  `macro_daily_briefs`
	  `RETURNING true AS changed` writes also require rowcount evidence matching
	  returned-row presence before changed booleans, wakes, or worker
	  `rows_written` are reported.
	  When CEX detail level bands are present, each band must carry formal `kind`
	  and numeric `price`; missing kind cannot default to `level`, and missing
	  price cannot be skipped before source refs or snapshot payload are built.
	  Present CEX detail `degraded_reasons` are likewise a formal string-list
	  contract at the CoinGlass enrichment and detail builder boundaries; scalar
	  strings, mappings, non-string items, and blank items fail instead of being
	  coerced into snapshot reasons.
	  Narrative admission dirty-target queue mutations are also part of the active
	  read-model control plane and require a connection transaction when the
	  repository owns the commit.
	  Narrative admission serving-row upsert and stale-target deletion have the
	  same boundary: repository-owned `narrative_admissions` mutations require a
	  connection transaction before serving-row SQL and must not fall back to
	  optional commit probing.
	  `MacroViewProjectionWorker` adds the worker-session side of the same rule:
	  dirty-target claim, series refresh, snapshot write, and dirty-target
	  terminal state share `RepositorySession.transaction`; downstream wake is
	  emitted only after that transaction exits.
- A worker treats injected wake emitters as optional shapes. Wake hints are not
  truth and a missing wake object can degrade only latency, but an injected
  malformed wake object is a runtime wiring error. Do not probe `notify_*` /
  `wake()` with `getattr(..., None)` and silently drop the hint after committing
  state.
- The common loop treats injected `wake_waiter` objects as optional shapes. A
  missing waiter can fall back to local interval sleep, but an injected waiter
  is the shared runtime contract for stop wake-up, async wait, and close. Do not
  probe `wake()`, `async_wait(...)`, or `close()` and silently degrade when that
  injected object is malformed. Manifest `wakes_on` is the only listener-channel
  source; `workers.yaml` does not accept wake-channel overrides. An interval-only
  worker has no `WakeWaiter` and must not check out a LISTEN connection with an
  empty channel list.
- A worker treats a broad table scan as a queue. Event-anchor catch-up consumes
  `event_anchor_backfill_jobs`; Token Radar consumes dirty targets with dirty
  kind flags. Empty queues mean idle, not "scan the fact table to be sure."
- A status hook is treated as diagnostics-only. `status_payload()`,
  `_queue_depth()`, queue health, `/readyz`, and `ops worker-status` are
  production contracts. Custom queue-depth hooks must be callable by
  `WorkerBase.status_payload()` with no required arguments and must not
  mutate queue state. `WorkerScheduler` must call worker `status_payload()`
  directly and fail visibly when the hook is absent, raises, or returns a
  non-object payload; it must not turn malformed runtime wiring into
  "stopped" or empty status. Unhealthy reason details are derived from the
  same payload rather than direct worker attribute fallback. API dependency
  helpers follow the same rule for worker liveness and route-local worker access: they read
  `runtime.scheduler`, `scheduler.status_payload()`, and direct worker
  `status_payload()` contracts instead of treating bad hooks as
  unsupported routes or stopped workers.
- Agent execution status is a runtime-root contract. `/api/status` and ops
  diagnostics read `runtime.agent_execution_gateway` directly; `None` is
  disabled, but a non-`None` gateway without `status_snapshot()` is unavailable
  runtime wiring, not a disabled gateway or provider-bundle alias fallback.
- DB pool shutdown is a runtime-root contract. `WorkerScheduler.stop()`
  awaits worker `stop()`, worker `aclose()`, and the canonical
  `DBPoolBundle`'s `db.aclose()` directly; the
  bundle owns individual pool close order and error aggregation, and each pool
  closes through synchronous `close() -> None` only. The scheduler must not
  use `_maybe_await(...)`, probe or close `api_pool`, `worker_pool`,
  `lock_pool`, `tool_pool`, or `wake_pool` as partial DB-bundle compatibility
  fallback. Bootstrap failure cleanup uses the same formal `db.aclose()` root
  once the bundle has been created, and records cleanup failure on the
  original startup exception.
- Wake emission is a wake-pool context contract. `WakeBus` must receive the
  formal wake-pool connection context factory, enter that context, and commit
  the checked-out connection after `pg_notify`. A factory returning a raw
  connection is malformed runtime wiring; it must not be treated as a supported
  fallback emitter.
- A worker service treats queue-summary readers as formal contracts. Macro Sync queue
  notes come from persisted `macro_sync_windows` through
  `macro_sync_queue_summary(...)`; missing repository support is session
  wiring failure, not an empty queue-summary state.
  Macro Sync retry-budget decisions also read the claimed window
  `attempt_count` and `max_attempts` directly; malformed claim windows fail before
  retry/final failure classification instead of being restored to first-attempt
  defaults.
- A maintenance service treats plan-count readers as optional. Asset Market
  Binance route dry-run/execute counts must come from persisted registry/feed
  state through `binance_usdt_perp_sync_plan_counts(...)`; missing repository
  support is a wiring failure, not permission to estimate inserts/deletes from
  provider input size.
- A fake provider satisfies tests while the real wrapper misses the domain
  protocol. Workers should depend on narrow provider protocols, and tests
  must exercise the concrete runtime wrapper for every method the worker
  calls, including audit methods.
- An enabled provider worker is marked disabled when the provider is missing.
  `disabled` is operator intent; missing provider wiring is `unavailable`
  status so `/readyz`, `/api/status`, and `ops worker-status` surface the
  broken fact-refresh lane.
- A worker factory treats a missing `WiredProviders` domain bundle as an empty
  provider set. The domain bundle root is the composition contract; missing it
  is malformed runtime wiring. Only concrete providers inside an existing
  bundle can be absent and represented as unavailable worker dependencies.
- A runtime status surface treats a missing provider domain bundle as an empty
  provider inventory. `/readyz` and ops diagnostics are runtime contract
  surfaces too: missing `runtime.providers.asset_market` is malformed runtime
  wiring, while a concrete provider field inside the bundle may be `None` and
  report disabled/disconnected IO state.
- Ops diagnostics treats missing collector status as an empty details object.
  Collector diagnostics are a contract surface: `runtime.collector.status`
  must expose `to_dict()` returning a mapping, and malformed collector status
  support must not be hidden as `{}`.
- Collector snapshot-gate timeout treats missing worker settings as a local
  default. `snapshot_timeout_seconds` belongs to the formal collector worker
  settings block; missing support is malformed worker settings, not a
  0.5-second fallback inside `CollectorService`.
- A market capture worker keeps test-only constructor shortcuts in production.
  `MarketTickPollWorker` is a fact writer and must be constructed from the
  formal `market_tick_poll` settings object plus the Asset Market provider
  bundle; missing settings/provider/DB bundle support is malformed runtime
  wiring, not permission to synthesize `SimpleNamespace` settings or accept
  individual quote-provider handles. The provider bundle fields
  `dex_quote_market` and `cex_market` are also formal fields: a present `None`
  value means that concrete provider is unavailable, while a missing field is
  malformed wiring and must not be hidden by `getattr(..., None)`.
- A capture-tier projection worker keeps local settings defaults in production.
  `TokenCaptureTierWorker` is the single writer for the rebuildable
  `token_capture_tier` control projection and must be constructed from the
  formal `token_capture_tier` settings object plus the DB bundle; missing
  `batch_size`, `ws_limit`, `poll_limit`, or `lease_ms` is malformed worker
  settings, not permission to synthesize defaults or accept constructor
  overrides.
- An event-anchor catch-up worker keeps test-only constructor shortcuts in
  production. `EventAnchorBackfillWorker` owns short-lived
  `event_anchor_backfill_jobs` control-plane catch-up and must be constructed
  from the formal `event_anchor_backfill` settings object plus the DB bundle,
  Asset Market provider bundle or explicit capture service, and wake emitter.
  Missing settings/provider/DB support is malformed runtime wiring, not
  permission to synthesize `SimpleNamespace` settings, accept `db` /
  `wake_bus` aliases, or pass individual `dex_quote_market` / `cex_market`
  handles and per-call limit overrides.
- Collector ingest treats event-anchor pending-job lifetime as a service-local
  default. `_PooledIngestStore`, `_ingest_service_for_repos`, and
  `IngestService` must receive
  `settings.workers.event_anchor_backfill.active_window_ms` explicitly from the
  composition root; a hidden `300_000` ms default would create a second
  lifecycle policy for the same `event_anchor_backfill_jobs` control rows.
- A CLI one-shot worker path clones settings by dumping arbitrary objects.
  Operator commands are still runtime composition paths: batch-size or
  reprocess-limit overrides must clone the formal Pydantic worker settings with
  `model_copy(update=...)`, not rebuild settings from `model_dump`, `vars(...)`,
  `__dict__`, or `SimpleNamespace(**...)`.
- Ops diagnostics treats missing Asset Market `provider_health` as an empty
  inventory. `provider_health` is part of the `AssetMarketProviders` bundle
  contract; malformed provider-bundle wiring must not disappear from operator
  diagnostics as an empty provider list.
- An Asset Market worker factory treats missing provider-bundle fields as
  missing concrete providers. The bundle shape is a runtime contract:
  `cex_market`, `dex_quote_market`, `dex_profile_sources`,
  `dex_discovery_market`, and `stream_dex_market` must exist. Only their
  values may be `None` to express unavailable provider IO.
- Asset Market startup failure cleanup treats missing `OkxProviderBundle`
  fields as absent providers. If an OKX bundle object exists during cleanup,
  `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` are
  formal fields; field absence must be recorded as cleanup failure evidence on
  the original startup error.
- Asset Market provider wiring treats a configured GMGN provider as an optional
  capability bag instead of a concrete protocol contract. If GMGN is configured
  and returns a provider object, missing `token_quotes(...)` or
  `token_profile(...)` is malformed wiring; it must not be hidden by falling
  back to OKX quotes or omitting the GMGN profile source.
- A CEX or News worker factory treats missing provider-bundle fields as
  missing concrete providers. `oi_market`, `coinglass_derivatives`,
  `feed_client`, and `brief_provider` are formal bundle fields; field absence
  is malformed runtime wiring, not provider unavailability.
- CEX provider wiring treats missing `cex_oi_radar_board` worker settings
  fields as defaults. CoinGlass enrichment is gated by the formal
  `settings.workers.cex_oi_radar_board.enabled` and
  `.coinglass_enrichment_limit` fields, and CoinGlass liquidation level-band
  limits come from `.coinglass_level_limit` passed through the worker into the
  enrichment service. The Binance OI builder likewise receives period and build
  limit from the worker's formal settings-derived budget and validates selected
  route `native_market_id` before provider IO. Binance OI wiring then reads
  formal integration DTO fields before returning the domain provider DTOs, and
  the builder reads formal provider DTO fields directly. Absent fields are
  malformed runtime configuration or provider-adapter output, not disabled,
  enrichment-off, default-period, default-limit, default-level, skipped-symbol,
  empty-metric, or empty-board state.
- Model-execution provider wiring treats a missing known agent lane as a local
  timeout default. The Pulse decision provider timeout is
  `workers.agent_runtime.lanes["pulse.decision"].timeout_seconds`; absent lane
  settings are malformed runtime configuration, not a 120-second fallback. The
  low-level Pulse decision client must not expose `timeout_seconds`; otherwise
  it becomes a provider-shaped bypass around the formal lane settings.
- Worker factory missing-worker sentinels treat missing worker settings blocks
  as enabled defaults or synthesize placeholder settings. `settings.workers`
  is the formal runtime configuration contract; absent `settings.workers.<name>`
  means malformed configuration, not an enabled unavailable worker or disabled
  sentinel. A present settings object must also be the formal Pydantic worker
  settings shape when a sentinel flips `enabled`; dumping arbitrary objects or
  `__dict__` into `SimpleNamespace` is compatibility code, not a runtime
  contract.
- WorkerBase treats missing core settings as local defaults. `enabled`,
  `interval_seconds`, and `backoff.base_ms/max_ms` are formal
  `PerWorkerSettings` fields; missing support is malformed worker settings, not
  permission for the base class to invent enabled state, a 5-second interval, or
  1s/60s retry backoff.
- DB pool wake-listener sizing treats missing `settings.workers` or missing
  manifest wake worker settings as zero listeners. Wake pool sizing must follow
  the manifest plus formal worker settings contract; malformed configuration
  should fail visibly instead of silently undersizing `wake_pool`.
- Runtime News provider-contract status treats missing News Intel settings as
  no configured sources. `runtime.settings.news_intel.sources` is a formal
  runtime configuration contract; missing settings shape must not be hidden as
  an empty source set.
- Ops diagnostics treats missing runtime settings as empty config or idle
  watchlist. `runtime.settings` is a formal runtime configuration contract for
  diagnostic config paths, provider configured flags, channels, handles, News
  enabled state, and notification rules; malformed settings support must not
  be hidden as false/empty/idle operator state.
- Signal Pulse notification rules treat missing `window`, `scopes`, or
  `statuses` as service-local defaults. These query dimensions are formal
  `settings.notifications.rules.signal_pulse_candidate` policy; malformed or
  empty settings must fail configuration validation instead of being restored
  inside the rule engine.
- Watched-account and news notification rules accept Signal Pulse-only query
  fields. Non-Signal rules support delivery settings only; unused
  `window`/`scopes`/`statuses` fields must fail config validation instead of
  loading successfully and being ignored by the rule engine.
- Notification rule candidate scans treat query windows and overscan budgets
  as service-local constants. `settings.notifications` owns the formal
  watched-account activity window, Signal Pulse page budget, News high-signal
  recency window, News high-signal query minimum, and News high-signal query
  multiplier; the rule engine must read those fields instead of defining
  policy constants.
- Notification rule evaluation treats missing `now_ms` as current wall clock.
  Candidate generation is a deterministic worker replay step; the worker owns
  the evaluation clock and must pass it explicitly to the rule engine.
- Ops diagnostics treats missing DB/API pool connection support as no queue
  state. Queue summaries are control-plane diagnostics over manifest-owned
  queues and require the formal `runtime.db.api_pool.connection()` contract;
  malformed DB wiring must not be hidden as `queues=[]`. App-runtime queue
  descriptors are read-only metadata for those summaries; queue claim,
  finalize, retry, lease, and stale-running transitions stay in the owning
  domain repositories, not a generic `JobQueue` executor.
- Worker queue-health treats missing DB/API pool connection support as ordinary
  unavailable queue state. Queue health is part of `/readyz`, `/api/status`,
  and ops diagnostics worker status; missing `runtime.db.api_pool.connection`
  is malformed runtime wiring, not a `missing_connection` table-health result.
  Real context-enter/query failures may still surface as unavailable queue
  health because the DB contract exists but the read failed.
- Runtime readiness keeps no unused helper that catches notification repository
  failures and returns `{}`. Dead helpers are compatibility surfaces waiting to
  be reused; notification status lives only on the route/worker contracts that
  own notification reads.
- An agent worker claims business work before reserving execution capacity.
  No-start backpressure must not claim a target, burn an attempt, or write a
  business run ledger. Once provider execution starts, failures are audited
  as provider-started attempts.
- A public route repairs data inline. API, WebSocket, CLI, and frontend paths
  should read facts/read models and expose honest missing/degraded status.
  They must not call providers, cleanup commands, or compatibility readers.

## State Machines

The system has several state machines stacked together. That is normal
for a mature event-processing service. It becomes a problem only when two
state machines claim to be truth for the same thing.

### Provider Connection State

Provider state answers: "Can this process currently talk to the upstream
streaming provider?"

Values are:

```text
disconnected | connecting | authenticating | subscribed | streaming | failed
```

This is IO health only. It must not become token identity, market truth,
or product decision state.

Configured streaming providers expose this state through a required
`connection_state_payload()` runtime hook. Status surfaces and degraded worker
results call the hook directly; missing or malformed hooks are failed provider
state, not a disabled/configured fallback.

The collector's upstream stream client has a separate lifecycle contract:
`UpstreamClientProtocol.aclose()`. Collector shutdown calls that method
directly. `close()`-only clients are runtime wiring errors, not compatible
provider shapes.
GMGN DirectWS frame delivery is equally direct: runtime wiring passes
`CollectorService.handle_frame(...)`, and the adapter awaits that async
contract without accepting synchronous callback results through
`inspect.isawaitable(...)`.

Provider bundle cleanup is also root-owned. Runtime shutdown and bootstrap
failure cleanup call `WiredProviders.aclose()` plus the runtime roots for
agent execution and LLM gateways. They must not recursively scan provider
objects for methods that happen to be named `close` or `aclose`. CLI ops
one-shot asset-market workers follow the same rule for their locally wired
provider bundle by calling `AssetMarketProviders.aclose()` directly.

Worker-owned provider cleanup is protocol-owned. Pulse candidate workers close
decision providers through `aclose()`. News fetch workers close source
providers through synchronous `close()`. A worker must not accept the other
shape or await an unexpected sync-close result.
Market tick stream workers close the per-cycle async iterator returned by
`iter_price_info().__aiter__()` through direct `aclose()`. Missing iterator
`aclose()` is degraded provider/runtime contract evidence, not an optional
no-op close path.

Provider wiring wrappers and startup failure cleanup follow the same rule.
Fallback or serialized provider wrappers call their wrapped provider's formal
`close()` contract directly. Partial wiring cleanup records a cleanup failure
on the original startup exception when a partially created provider is missing
`close()`; it must not skip malformed providers through optional method probes.

### Collector Snapshot Gate

Collector snapshot gate state answers: "Did this GMGN frame look complete
enough to ingest now?"

Counters are:

```text
immediate_complete | debounced_complete | debounced_timeout | non_tw_channel
```

These counters explain ingestion quality. They do not decide whether a
token is real, tradable, or important.

### Fact Lifecycle

Fact lifecycle answers: "What did the system observe and persist?"

Examples:

- `events` records the source event.
- `token_intent_resolutions` records deterministic identity decisions.
- `asset_identity_evidence/current` records identity claims and selected current identity.
- `market_ticks` records append-only market samples. Its insert path treats
  rowcount=1 with a returned `tick_id` as a new fact and rowcount=0 with no row
  as a dedupe conflict; malformed cursor rowcount evidence is repository/driver
  damage, not a business no-op.
- `enriched_events` records event-anchor market context for an event.

Facts are the business source of truth. If public behavior disagrees with
facts, the public behavior is suspect.

### Control-Plane Job State

Control-plane job state answers: "What work is due, retried, done,
expired, or failed?"

Examples:

- `event_anchor_backfill_jobs`
- `pulse_agent_jobs`
- notification delivery rows

These rows schedule work. They are not product facts by themselves.
Product surfaces should not infer token quality from a queue status.
`notification_rule` may create new external delivery rows with
`enqueue_delivery`, but aggregated high-signal notifications that reactivate
failed/dead external deliveries must use `enqueue_or_requeue_delivery`.
Missing requeue support is a repository contract failure, not an insert-only
compatibility path.
`notification_rule` writes rebuildable notification serving rows and delivery control rows inside
the worker-session `unit_of_work`. Missing UoW support is a session contract
failure; runtime code must not fall back to `nullcontext` or manual repository
commit.
`NotificationWorker` consumes `NotificationRepository.insert_notification_with_outcome(...)`
as a formal `NotificationInsertOutcome`. Runtime code must read
`outcome.row`, `outcome.created`, and `outcome.aggregated` directly; a bare row
dict or missing outcome fields are malformed repository contracts, not legacy
shapes to infer from.
Notification serving-row insertion and insert-only delivery enqueue require PostgreSQL
single-row `cursor.rowcount` evidence before created-vs-existing state is
classified. A `0` rowcount can mean conflict/no new row, but missing, boolean,
negative, multi-row, or otherwise invalid rowcount is malformed repository or
driver evidence, not a notification/delivery state.
When an existing notification row is aggregated after an insert conflict, the
subsequent `UPDATE notifications` must prove `rowcount=1`; zero rows, multiple
rows, missing rowcount, or malformed rowcount fail before
`NotificationInsertOutcome.aggregated` or external requeue state is reported.
Notification read-marker writes to `notification_reads` follow the same
execution-evidence rule. `mark_read` is single-row accounting, while
`mark_all_read` and `mark_author_read` must return changed-row counts from a
single PostgreSQL `INSERT ... SELECT ... RETURNING` cursor whose rowcount
matches the returned rows; preselecting unread ids and reporting `len(rows)` is
not valid database write evidence.
Evidence ingest writes follow the same single-row `INSERT ... DO NOTHING`
evidence rule for `raw_frames`, `events`, and `event_entities`: `0` can only
mean conflict/no new row after PostgreSQL reports that rowcount, `1` means a
new raw frame, event, or entity row, and missing, boolean, negative, multi-row,
or otherwise invalid rowcount is a repository/driver contract failure before
fact state or inserted-entity counts are classified.
Watched-account alert insertion uses the same single-row `INSERT ... DO
NOTHING` evidence rule for `account_token_alerts`: `0` can only mean an
existing alert after PostgreSQL reports that rowcount, `1` means a new alert,
and missing, boolean, negative, multi-row, or otherwise invalid rowcount is a
repository/driver contract failure before alert state is classified.
External delivery retry budget is also a formal runtime policy:
`notification_rule` receives `delivery_max_attempts` from
`settings.workers.notification_delivery.max_attempts` through the worker
factory, and the worker constructor must not retain a local default.
Signal Pulse notification candidate selection reads the validated
`signal_pulse_candidate` rule directly. The rule engine must not keep
service-local window/scope/status defaults that can override an empty or
malformed notification config.
Watched-account activity, watched-account token alert, and news high-signal
rules accept only delivery settings such as enabled/channels/cooldown. Signal
Pulse query fields on those rules are rejected before runtime so no ignored
configuration survives into worker execution.
Notification candidate scan policy reads `settings.notifications` directly:
`candidate_limit`, watched-account activity window, Signal Pulse page budget,
News high-signal recency window, News high-signal query minimum, and News
high-signal query multiplier. Invalid zero/negative budgets fail configuration
validation; the rule engine must not hide them behind service-local windows,
page caps, floors, or multipliers.
Watched-account activity must push that configured recency window into
`EvidenceRepository.recent_events(..., since_ms=...)`; filtering stale events
only after a generic recent-events read hides the real SQL predicate from
PostgreSQL and can drop in-window candidates behind out-of-window rows.
Watched-account token alert evaluation uses the same explicit evaluation clock:
`NotificationRuleEngine` passes worker `now_ms` into
`AccountAlertService.account_alerts(...)`, and the service passes it to
`SignalRepository.account_alerts(...)`. The alert window must not be computed
from repository-local wall time during a notification worker cycle.
Signal Pulse notification candidate discovery also has its own repository
boundary. The rule engine passes the configured Signal Pulse window, scopes,
statuses, and per-scope/status budget to
`PulseReadRepository.list_signal_pulse_notification_candidates(...)` once per
evaluation. The repository reads those scopes/statuses as PostgreSQL keysets and
uses a per-bucket window rank. It must not rediscover candidates by looping over
public `list_candidates(...)` cursor pages for each scope/status combination.
Notification rule evaluation receives an explicit `now_ms` from
`NotificationWorker`. The rule engine must not read wall-clock time directly or
accept a missing evaluation timestamp, so retries/replays produce the same
candidate set for the same material facts and settings.
When `NotificationRepository` owns a commit outside that worker UoW,
notification serving-row insertion/aggregation, read-marker writes, and delivery
enqueue/requeue must enter a callable connection transaction before
`notifications`, `notification_reads`, or `notification_deliveries` SQL. Missing
transaction support fails before SQL; it is not a `self.conn.commit()`,
`nullcontext`, or optional-probe compatibility path.
Delivery requeue and claim `RETURNING *` mutations must also validate
PostgreSQL rowcount against returned-row presence: rowcount=0/no row means no
reactivated or claimable delivery, rowcount=1/row means one changed delivery,
and any missing, invalid, multi-row, or mismatched evidence fails before worker
state is reported.
`notification_delivery` writes delivery claim/pre-flight/log-complete and
external complete/fail state transitions inside `RepositorySession.transaction`.
Apprise/PushDeer IO runs outside DB transactions; the worker must not replace
that session boundary with direct `repos.notifications.conn.commit()` or
repository-owned delivery commits.
Delivery stale-running timeout and terminalization batch size are formal
`settings.workers.notification_delivery` policies. Repository sessions pass them
to `NotificationRepository` explicitly; the repository layer must not decide
delivery timeout or cleanup batch defaults on its own.
Delivery retry/dead classification reads persisted `attempt_count` and
`max_attempts` directly from `notification_deliveries`. Missing, malformed,
negative, or non-positive attempt state fails as
`notification_delivery_attempt_contract_required` before SQL or worker outcome
classification; it is not repaired by repository or worker-local defaults.
`macro import-bundle` is offline replay/seed, not a long-running worker, but it
still writes macro facts, import audit rows, and projection dirty targets. It
must use `RepositorySession.unit_of_work` plus `require_transaction`, not raw
connection transaction fallback.
`macro_view_projection` claims `macro_projection_dirty_targets`, refreshes
series rows, writes snapshots, and marks done/error inside
`RepositorySession.transaction`; repository-owned dirty-target claim/done/error
defaults require connection transaction support before queue SQL and never fall
back to manual `self.conn.commit()`. Dirty-target retry cadence and retry
budget come from formal `settings.workers.macro_view_projection.retry_ms` and
`max_attempts`; exhausted claims are deleted with the claimed payload hash and
written to `worker_queue_terminal_events`, where `ops queue-resolve-bucket` can
retry them through the Macro projection dirty-target enqueue path. Existing
`macro_observation_series_rows`
must expose non-empty `payload_hash` values before changed/unchanged comparison;
missing current-row signatures fail before delete/insert instead of being treated
as empty signatures.
`event_anchor_backfill` stale cleanup terminalizes `event_anchor_backfill_jobs`
and matching `enriched_events` lifecycle state inside the worker-session
`unit_of_work`; missing UoW support must fail before cleanup writes, not fall
back to manual repository commit.
Claimed job rows must carry a positive `attempt_count` before temporary retry,
done, or terminal guards run; missing attempt state is malformed job state, not
the first attempt.
Queue Terminal retry of an event-anchor terminal snapshot must restore a
fresh pending job with an active window derived from the persisted source
snapshot, not a one-instant `active_until_ms = now` requeue that immediately
expires again.
`resolution_refresh` terminalizes exhausted `token_discovery_dirty_lookup_keys`
claims by deleting the claimed queue rows and writing `worker_queue_terminal_events`
evidence inside the connection transaction; missing transaction support fails
before delete/ledger SQL, not through `nullcontext` or manual commit.
Provider-unavailable batch handling uses the same retry budget: claimed rows
below budget are rescheduled together, while exhausted claimed rows are deleted
and terminalized instead of cycling in the active lookup queue indefinitely.
Deleted lookup source rows must carry a non-empty `payload_hash` before terminal
ledger evidence is written; missing source payload hashes are malformed queue
snapshots, not empty terminal signatures. Discovery terminal delete paths also
validate PostgreSQL `cursor.rowcount` before terminal ledger writes; rowcount
must match returned deleted lookup rows, and missing, invalid, or mismatched
rowcount fails before terminal counts or `worker_queue_terminal_events` rows are
reported.
DiscoveryRepository ordinary repository-owned lookup queue/result mutations
also require connection transaction support before enqueue, claim, done,
reschedule, start, finish, or fail SQL. These rows are the lookup state machine
that wakes `resolution_refresh`, not compatibility commits around a cache.
Retry-budget decisions use the claimed row `attempt_count` directly; missing
attempt state fails as malformed claim state instead of becoming a zero-attempt
retry.
Its worker runtime also uses `RepositorySession.transaction` for lookup running,
finish, fail, and claim completion state. Provider IO stays outside the
transaction; state-machine writes must not fall back to direct
`repos.conn.commit()`.
Token intent rebuild and resolution reprocess entrypoints also use
`RepositorySession.transaction` for token evidence/intents, lookup keys,
resolution rows, discovery dirty lookup rows, identity evidence, and Token Radar
source-dirty rows. Missing session transaction support fails before SQL, not
through direct `repos.conn.commit()`. These entrypoints also require explicit
window and limit arguments from their CLI/worker caller; service-local
`DEFAULT_REPROCESS_*` values or `WINDOW_MS.get(... fallback ...)` are not a
runtime compatibility surface. Resolution reprocess batches token evidence for
the selected intent keyset through one repository read instead of issuing one
`evidence_for_intent(...)` query per intent.
The underlying token fact repositories follow the same repository-owned commit
rule: token evidence, token intents, lookup-key replacement, and current
resolution writes require a callable connection transaction before SQL. The
resolution repository enters that transaction before its per-intent advisory
transaction lock, so a fake/autocommit connection cannot make the lock look
valid.
`ops enqueue-projection-dirty-targets --execute` writes News projection dirty
targets after broad repair discovery and must enter the connection transaction
before the discovery scan or queue writes. Dry-run remains read-only, but
execute mode must not fall back to `nullcontext`.
`ops queue-resolve --action retry --execute` runs inside the Queue Terminal
operator transaction and requeues target work only through formal retry
repositories (`discovery`, `event_anchor_jobs`, `pulse_jobs`, Token Radar dirty
target/source dirty queues, or image-source dirty queues). Missing repository
support rolls back the terminal action instead of being treated as an optional
queue capability. Queue Terminal source-row ledger writes use the
connection transaction too when `terminalize_source_row(..., commit=True)` owns
the commit; naked `conn.commit()` is not a platform terminalization fallback.
Event-anchor retry uses the terminal source row's persisted active-window span
to set the next `active_until_ms`, so operator retry remains a meaningful
bounded retry instead of an immediate stale-expiry transition.
`ops queue-resolve-bucket` is only a bounded operator-control helper over
unresolved terminal ledger rows selected by worker, source table, and reason
bucket. Dry-run is read-only and execute mode still resolves one terminal event
at a time through the same Queue Terminal state machine; command output reports
counts and error buckets, not terminal ids, target keys, or source snapshots.
Terminal source-row evidence requires a formal attempt/generation contract:
callers may pass explicit `attempt_count`, otherwise the source row must expose a
non-negative `attempt_count`, and any existing terminal generation row must expose
a positive `terminal_generation`. Missing attempt or generation state fails as a
platform contract error rather than being restored to `0` or `1`. Repository
callers must pass deleted/returned source rows through unchanged for attempt
validation instead of converting missing attempts into explicit zero-attempt
overrides.
News projection terminalization deletes claimed `news_projection_dirty_targets`
rows and writes `worker_queue_terminal_events` evidence inside the connection
transaction; missing transaction support fails before delete/ledger SQL, not
through `nullcontext` or manual commit.
News projection dirty-target repository mutations for enqueue, claim, done, and
error use the connection transaction when the repository owns the commit;
missing transaction support fails before queue SQL, not through manual commit.
News projection dirty-target claim rows from `UPDATE
news_projection_dirty_targets ... RETURNING news_projection_dirty_targets.*`
must validate PostgreSQL `cursor.rowcount` against returned rows before
page/source-quality workers treat targets as leased work.
News projection dirty-target done/error/delete/terminalization completion keys
require the claimed row `attempt_count`; malformed completion tokens fail before
transaction entry or SQL instead of matching the queue with a synthesized
`attempt_count=0`.
News projection dirty-target enqueue and done/error changed-row counts require
PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails before
the repository reports queue enqueue, completion, or retry work. Enqueue paths
must not report candidate `len(records)` as write evidence.
News page, item-brief, and source-quality window dirty enqueue also requires a
positive producer-supplied `source_watermark_ms` before queue SQL.
Source-quality `_refresh` targets are source-scoped expansion controls only;
expanded source/window work uses positive `latest_item_published_at_ms` rather
than `0`, `computed_at_ms`, or worker `now_ms`.
News projection terminal delete paths validate PostgreSQL `cursor.rowcount`
before terminal ledger writes; rowcount must match returned deleted rows, and
missing, invalid, or mismatched rowcount fails before terminal counts or
`worker_queue_terminal_events` rows are reported.
News item-brief run reuse has a similar ledger contract:
`news_item_agent_runs.run_id` must be present and non-empty before a completed or
failed run can restore `news_item_agent_briefs` or failed-current state. Missing
run identity fails the dirty target before model execution and must not be
restored to an empty `agent_run_id`.
Fresh `news_item_agent_runs` insert and `news_item_agent_briefs` current upsert
paths require rowcount=1 with a returned row before the worker reports
audit/current writes, queues page dirty work, or exposes publication eligibility.
Schema-version cleanup of current `news_item_agent_briefs` rows through
`DELETE ... RETURNING news_item_id` requires cursor rowcount to match returned
ids before stale-brief cleanup accounting is reported.
News item-brief completed-run validation, provider failure audit, and
market-wide agent admission are formal model contracts. Runtime code must read
`NewsItemBriefValidationResult`, `AgentExecutionRequestAudit` /
`AgentExecutionResultAudit`, and `NewsItemAgentAdmission` directly instead of
probing arbitrary objects for `model_dump`, `__slots__`, or loose attributes.
Item-brief source-backed entity/domain support also consumes formal
`NewsItemBriefEntityLane` packet rows directly; loose entity-like objects and
missing lane-field defaults are not runtime compatibility surfaces.
Pulse job terminal/dead transitions update `pulse_agent_jobs` and write
`worker_queue_terminal_events` evidence inside the connection transaction;
missing transaction support fails before job-state or ledger SQL, not through
`nullcontext` or manual commit.
Pulse job enqueue, success marking, running-job release, and stale agent-run
cleanup use a connection transaction when the repository owns the commit;
missing transaction support fails before job/run SQL, not through manual commit.
Job enqueue also requires an explicit `max_attempts` from the worker/caller; the
repository must not create `pulse_agent_jobs.max_attempts` from a local fallback
because that column is the runtime retry-budget fact for later claim/dead
classification.
Running-job release, timeout cancellation, failure retry/dead classification,
and agent run-id/audit construction require the claimed `pulse_agent_jobs`
`attempt_count`; failure classification also requires `max_attempts`. Missing or
non-positive values are malformed job claims, not zero-attempt compatibility
state.
Pulse agent write repository mutations for run/step/eval, evidence packet,
candidate, playbook, and ordinary admission edge/budget writes use the shared
connection transaction when the repository owns the commit; missing transaction
support fails before agent write SQL, not through manual commit.
The evidence packet upsert itself is a required single-row `RETURNING` write:
the repository validates PostgreSQL `cursor.rowcount=1` and a returned packet
row before updating `pulse_agent_runs.evidence_packet_id/hash`; the run-link
`UPDATE pulse_agent_runs` then separately requires rowcount=1 before packet
persistence is reported.
Pulse evidence packet construction reads source events, enriched events, market
facts, and identity facts through the formal evidence source repository methods.
Missing methods are worker/session wiring failures before the sealed packet is
built, not empty evidence. Narrative projections are not packet inputs.
The builder and source repository consume the formal `PulseCandidateContext`
shape directly; dict/SimpleNamespace context compatibility is outside the
runtime contract. Market-fact freshness is a formal Pulse candidate worker
policy: `PulseCandidateJobService` passes
`settings.workers.pulse_candidate.evidence_market_freshness_ms` and the job
run's `now_ms` into the builder/repository path explicitly. Builder-local
freshness defaults, repository-local `max_age_ms` defaults, or repository
default-current-clock fallbacks are outside the runtime contract.
The EvidenceCompletenessGate consumes the formal `PulseEvidencePacket` model
directly. Arbitrary dict/object reflection is outside the worker contract so a
malformed sealed-packet boundary fails visibly instead of becoming a normal
abstain/partial gate result.
The ClaimEvidenceVerifier also consumes the formal sealed packet and strict
`FinalDecision` model directly. Dict/object final-decision shims are malformed
agent-output wiring, not compatibility input for claim validation.
The Pulse decision stage builder consumes formal `PulseEvidencePacket` and
`EvidenceCompletenessGateResult` models directly. The model-execution adapter
may receive JSON context from the job service, but it must validate that JSON
back into formal models before building the stage spec.
Pulse stage-output normalization consumes that same formal sealed packet before
final decision validation. Dict packets and dict/object evidence refs are
malformed adapter wiring, not compatibility input for event-id normalization.
Pulse deterministic eval reads stored eval-case JSON but re-validates the
embedded evidence packet into `PulseEvidencePacket` before checking allowed
refs. Minimal hash/ref dict packets are malformed eval artefacts, not passing
evidence.
Pulse request-audit construction also re-validates `context["evidence_packet"]`
and consumes formal `EvidenceCompletenessGateResult` before deriving input
hashes or trace packet/gate metadata. Top-level `evidence_packet_hash` and raw
gate dicts are not audit compatibility fallbacks.
The runtime manifest must also expose a non-empty `runtime_version`; missing
runtime versions fail before agent run audit metadata is built.
Agent run identity fields (`run_id`, `job_id`, model, artifact hash, workflow,
agent) must be non-empty before request-audit metadata is built; empty identity
strings are malformed execution lineage.
The runtime manifest model/artifact pair must match the request-audit
model/artifact pair; otherwise runtime hash lineage and run audit lineage would
refer to different executable artifacts.
`PulseCandidateJobService` validates claimed-row `job_id`, `trigger_signature`,
`timeline_signature`, and positive `attempt_count` before run-id construction or
repository sessions. Empty claimed identity segments fail as malformed queue
state instead of becoming audit/run lineage.
`PulseCandidateJobService` persists run ledger identity from the validated
request-audit payload directly. Missing or mismatched backend, workflow, agent,
artifact, prompt/schema, input hash, trace metadata, runtime version, or
runtime hash fails the job path instead of being restored from local constants.
Pulse stage audit construction consumes formal `AgentExecutionResult` and
`AgentExecutionRequestAudit` / `AgentExecutionResultAudit` contracts only.
Loose gateway objects or reflective audit attributes fail before run-step audit
rows are produced.
Pulse `AgentStageSpec` construction also requires request-audit trace metadata
with the same non-empty `run_id` as the current pipeline and a non-empty group
id from the formal stage evidence packet. Missing trace or group identity fails
before gateway request audit/model execution instead of falling back to the
pipeline `run_id`.
Pulse workflow identity is also a constructor contract: omitted input uses the
canonical workflow constant, while explicit blank or `None` values fail as
malformed model-execution wiring.
No-start provider backpressure release uses only formal
`AgentExecutionError.error_class` with `execution_started=False`. Loose
exception audit dicts and alias fields do not control Pulse job cooldown.
Worker hard-timeout cleanup uses formal `AgentExecutionCancelled.execution_started`
when the agent execution plane supplies it; otherwise it falls back to the
worker-local `run_started` state. Loose cancellation audit dicts do not control
timeout retry/dead classification.
The recommendation clipper, write gate, and cost guard consume formal
`PulseGateResult`, `EvidenceCompletenessGateResult`,
`ClaimEvidenceVerificationResult`, and `PulseSourceQualityDecision` fields
directly. Missing or malformed gate objects fail as worker/agent contract
errors rather than being restored to complete/public/valid defaults.
Pulse job run-outcome classification consumes the same formal
`ClaimEvidenceVerificationResult`; it must not split verifier validity into a
bool plus optional object fallback.
Signal Pulse public health uses `PulseReadRepository.freshness_health(...)` as
the formal read contract. Missing support is route/session wiring failure, not
an empty-health state, and the read service must not inspect private repository
connections.
Signal Pulse public list width is likewise a surface-owned read boundary:
callers pass `limit` explicitly into `PulseReadRepository.list_candidates(...)`;
the repository must not retain a hidden `limit=50` default.
Pulse trigger dirty-target repository mutations for enqueue, claim, done, error,
and reschedule use the shared connection transaction when the repository owns
the commit; missing transaction support fails before dirty-target SQL, not
through manual commit.
Pulse trigger dirty-target done/error/reschedule changed-row counts require
PostgreSQL `cursor.rowcount`; missing or invalid rowcount fails before the
repository reports dirty-trigger completion counts.
Pulse admission claims update `pulse_candidate_edge_state`,
`pulse_target_run_budget`, and `pulse_candidate_run_budget` inside the connection
transaction; missing transaction support fails before edge or budget SQL, not
through `nullcontext`.
Pulse dirty-trigger claim lease, capacity retry, error retry, target/candidate
edge budgets, failure-circuit threshold/reasons, and timeline-debounce policy
are runtime policy under `settings.workers.pulse_candidate`; worker code passes
them into repository and admission-policy calls explicitly and must not retain
local magic constants or policy-service defaults.
Pulse exit suppression writes `pulse_candidate_edge_state.trigger_signature` only
from the claimed dirty-trigger `payload_hash`; missing payload hashes fail before
admission writes instead of becoming empty trigger signatures.
Pulse admission policy treats failed `pulse_agent_jobs` retry state as a formal
row contract: `attempt_count` and `max_attempts` must be present and valid before
the job can suppress a new admission as retryable. Missing attempt fields fail
the dirty trigger for retry rather than being restored by policy defaults.
Pulse stale running-job timeout is a worker policy under
`settings.workers.pulse_candidate.job_running_timeout_ms`. Repository sessions
construct `PulseJobsRepository` with that value explicitly; the repository layer
must not invent its own running-timeout default or keep unused timeout state in
unrelated Pulse repositories.
Pulse stale exhausted running-job terminalization width is likewise worker
policy under
`settings.workers.pulse_candidate.stale_running_terminalization_batch_size`.
`PulseCandidateWorker` passes that value into
`PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`
explicitly; the repository layer must not invent its own `limit` default.
`news_fetch`, `news_item_process`, and `news_item_brief` are News writer
workers for provider observations, canonical item facts, agent admission/current
brief state, run ledgers, and projection dirty work. They must use
`RepositorySession.transaction`; missing session transaction support fails before
reconcile, claim, or write. `news_fetch` source-claim lease duration comes from
formal `settings.workers.news_fetch.lease_ms`; `NewsRepository.upsert_source(...)`
must validate required rowcount=1 with a returned source row for
`INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` before inserted or
updated configured sources are reported. `NewsRepository.claim_due_sources` must
not keep a repository-local lease default for worker-owned source claims, and its
`UPDATE news_sources ... RETURNING sources.*` result must validate cursor
rowcount against returned claim rows before provider fetch work starts.
`NewsRepository.start_fetch_run(...)` must validate rowcount=1 for both the
`news_fetch_runs` running-ledger insert and the matching
`news_sources.last_fetch_at_ms` update before returning a run id.
`NewsRepository.finish_fetch_run(...)` must likewise validate required single-row
`UPDATE news_fetch_runs ... RETURNING *` rowcount/row evidence before updating
`news_sources` success/failure state or returning the finalized fetch-run row.
`NewsRepository.upsert_provider_item(...)` must validate required rowcount=1 with
a returned `news_provider_items` row for
`INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` before fetch
accounting reports an inserted or updated provider observation.
`NewsRepository.upsert_canonical_news_item(...)` must validate required
rowcount=1 with a returned `news_items` row for
`INSERT INTO news_items ... ON CONFLICT ... RETURNING *` before observation-edge
writes, canonical remap cleanup, or affected-item accounting use the canonical
`news_item_id`. Its `news_item_observation_edges` upsert must also validate
rowcount=1 before provider-article remap, material duplicate remap, summary
refresh, or affected-item accounting treats the provider observation as linked.
The following observation summary `UPDATE news_items ... RETURNING items.*`
refresh must validate rowcount=1 with a returned current item row before
affected-item accounting uses refreshed source/provider-article aggregates;
old zero-edge cleanup may accept rowcount=0/no row only as explicit optional
cleanup state, never by fallback `SELECT` readback.
Old-item representative reselection through `UPDATE news_items ... RETURNING
items.*` uses optional single-row rowcount evidence too: rowcount=0/no row is an
explicit no-representative-edge cleanup result, while rowcount=1/row is required
before representative facts can drive item-scoped derived-fact cleanup.
`claim_unprocessed_items` must also prove cursor rowcount matches returned claim
rows from `UPDATE news_items ... RETURNING items.*` before
`NewsItemProcessWorker` treats those rows as leased work.
`news_item_process` treats claimed `news_items.processing_attempts` and
`processing_lease_owner` as the processing claim contract. Missing or non-positive
attempts, or a missing lease owner, fail before deterministic fact writes,
retry/terminal failure writes, or downstream dirty enqueue rather than being
restored to attempt 0 or an empty lease owner.
Deterministic entity, token mention, and fact candidate writes must use formal
`NewsEntity`, `NewsTokenMention`, and `NewsFactCandidate` objects. Repository
fact writes must not accept arbitrary object payloads through `model_dump`,
`vars`, `__dict__`, or `__slots__` reflection.
News agent-admission duplicate lookup must use normalized
`news_item_observation_edges.provider_article_key` joins. `provider_article_keys_json`
is compact evidence payload only and must not be expanded with
`jsonb_array_elements_text(...)` in the worker readback hot path.
OpenNews REST catch-up page size, page count, and overlap window must come from
formal source policy, worker fetch limit, or durable cursor state; the
integration client must not invent local `rest_limit`, `max_rest_pages`, or
`rest_overlap_ms` defaults, and source policy must use `rest_overlap_ms` rather
than the cursor-only `overlap_ms` field.
When `NewsRepository` owns a commit outside a worker session, source/fetch,
provider item, canonical item, deterministic item fact, agent run/brief,
source-quality, and page-row mutations require a callable connection transaction
before SQL. Worker paths keep those writes caller-owned with `commit=False`;
repository defaults must not degrade to naked `self.conn.commit()`. NewsRepository
changed-row accounting for item lifecycle, source-quality status, source disable,
and page-row mutations requires PostgreSQL `cursor.rowcount`; missing or invalid
rowcount fails before the repository reports zero changed News work. Source
reconcile `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` upserts
must prove rowcount=1 with a returned source row before inserted/updated source
rows are reported. Source disable `UPDATE news_sources ... RETURNING *` counts
must match returned disabled rows before source reconcile or disable counts are
reported. Provider item `INSERT INTO news_provider_items ... ON CONFLICT ...
RETURNING *` upserts must prove rowcount=1 with a returned provider-item row
before inserted/updated provider observations are reported. Canonical item
`INSERT INTO news_items ... ON CONFLICT ... RETURNING *` upserts must prove
rowcount=1 with a returned `news_items` row before observation edges, canonical
remap cleanup, or affected-item accounting can use the canonical `news_item_id`.
Observation edge `INSERT INTO news_item_observation_edges ... ON CONFLICT`
upserts must prove rowcount=1 before provider-article remap, material duplicate
remap, summary refresh, or affected-item accounting treats the provider
observation as linked to the canonical item.
Provider-article and material duplicate edge-remap CTEs over
`news_item_observation_edges` must prove cursor rowcount matches returned old
item-id rows before old-item summary cleanup, dirty-target remap, or
affected-item accounting uses those ids.
Observation summary `UPDATE news_items ... RETURNING items.*` refreshes must
prove rowcount=1 with a returned current item row before affected-item accounting
uses refreshed source/provider-article aggregates; old zero-edge cleanup paths
may observe rowcount=0/no row only as explicit optional cleanup state, never by
fallback `SELECT` readback.
Old-item representative reselection `UPDATE news_items ... RETURNING items.*`
must validate optional single-row rowcount evidence before clearing item-scoped
derived facts or continuing affected-item accounting.
`news_item_process` claim rows from `UPDATE news_items ... RETURNING items.*`
must validate cursor rowcount against returned rows before deterministic item
processing starts.
Canonical edge-remap cleanup zero-edge old `news_items` deletes must also match `DELETE ...
RETURNING` cursor rowcount to returned rows before cleanup booleans are reported.
Page-row `RETURNING (xmax = 0)` upserts use the same optional single-row proof:
rowcount=0/no row is unchanged, and rowcount=1/row is inserted or updated.
`news_page_rows` JSON sections are also formal page-projection output before
payload hash or SQL: missing `token_lanes`, `fact_lanes`, `story`, `source`,
`signal`, `agent_brief`, `market_scope`, or `agent_admission` fields fail the
write instead of being restored to empty arrays, empty objects, or pending agent
state.
News item detail keeps that contract on the read side. A present current
`news_page_rows` row must supply the public story, market, signal, provider,
content, lane, and admission fields directly; raw `news_items` can hydrate base
item/evidence payloads but cannot repair malformed projected sections.
News page list reads and high-signal notification candidates apply the same
projected-row validation before public/notification shaping, so malformed
`agent_brief_json` cannot be downgraded to pending state and malformed JSONB
sections cannot slip through as unvalidated public payload.

Dirty-target queues such as `market_tick_current_dirty_targets`,
`pulse_trigger_dirty_targets`, `narrative_admission_dirty_targets`,
`token_profile_current_dirty_targets`, `token_image_source_dirty_targets`,
`asset_profile_refresh_targets`, and `token_capture_tier_dirty_targets` are
control-plane rows only. They are repaired through explicit ops commands that
enqueue targets; normal worker loops do not fall back to historical scans when
the queue is empty. `market_tick_current_dirty_targets`,
`token_profile_current_dirty_targets`, and `token_image_source_dirty_targets`
repository-owned enqueue/claim/done/error mutations require a connection
transaction before queue SQL; missing transaction support is not manual commit
compatibility.
`asset_profile_refresh_targets` repository-owned enqueue/claim/reschedule/error
mutations follow the same rule before provider profile refresh queue SQL.
Dirty target done/error or reschedule/error completion keys for
`market_tick_current_dirty_targets`, `token_profile_current_dirty_targets`,
`token_image_source_dirty_targets`, and `asset_profile_refresh_targets` require
the positive `attempt_count`, non-empty `lease_owner`, and `payload_hash`
returned by `claim_due`; malformed completion tokens fail before SQL instead
of being restored to zero attempts, empty owners, or empty payload hashes.
`token_discovery_dirty_lookup_keys`, `narrative_admission_dirty_targets`, and
`pulse_trigger_dirty_targets` follow the same claimed-row attempt/lease-owner/payload-hash contract for
done/error/reschedule or terminal completion.
`token_capture_tier_dirty_targets` repository-owned enqueue/claim/done mutations
require connection transaction before queue SQL, and `token_capture_tier` also
treats dirty target claim, tier projection, and done marking as one
`RepositorySession.transaction`; missing transaction support fails before claim.
`token_capture_tier` tier demotion accounting and dirty-target enqueue/done
changed-row counts require PostgreSQL `cursor.rowcount` evidence; missing or
invalid rowcount is malformed driver/repository state, not zero capture-tier
work.

Worker identity and lane grouping come from `WorkerManifest v1` only.
`workers.yaml` can tune a manifest worker's cadence, lease, timeout, attempt,
batch, wake, and agent budget settings, but it cannot create a worker or alias
an old queue name.

### Narrative Admission State

Narrative admission state answers: "Is this target in the current Narrative
frontier, and how much source coverage supports that admission?"

The only serving source is `narrative_admissions`. Public reads map its current
row to `narrative_admission` with `status` (`admitted`, `suppressed`, or
`missing`), reason, currentness, source/author coverage, computation time, and
explicit data gaps. Unsupported windows use `status=missing` with
`currentness.display_status=unsupported_window`. The API never calls an LLM or
writes Narrative tables. Token Radar API composition passes formal
`target.target_type` / `target.target_id`; old `type` / `id` aliases are not
repaired.

### Projection Freshness State

Projection state answers: "Is a rebuildable read model current enough to
serve?"

Examples:

- `projection_runs`
- `projection_offsets`
- projection coverage rows
- `token_radar_current_rows.computed_at_ms`
- status payload fields such as `last_result` and `last_error`

Projection freshness is a read-model health signal. It should never
rewrite fact meaning.

### Business Decision State

Business decision state answers: "What product decision did a use case
make from facts and projections?"

Examples:

- Token Radar `recommended_decision`
- Pulse `recommendation`
- Pulse abstain decisions
- notification rule evaluations

Business decisions must be replayable from facts, projection inputs, and
audit rows. Pulse decisions are not valid unless the audit ledger rows
exist.

## Non-Conflict Rules

Use these rules when adding or reviewing a worker:

1. One state machine owns one question.
   Provider state owns connectivity; job state owns scheduling; facts own
   observations; read models own presentation-ready projections.

2. A worker may read many tables, but a derived read model has exactly
   one runtime writer.

3. `NOTIFY` payloads are hints. A listener must re-read the database and
   must also run on bounded `interval_seconds` catch-up.

4. Projection workers may claim dirty target control rows and load source
   payloads by explicit ids. They must not scan facts or read models to
   discover stale projection work while idle; manual ops repair commands
   perform broad coverage discovery only by enqueueing dirty targets.

5. Every pending control-plane state needs a terminal path such as
   `done`, `expired`, `failed`, or an explicit abstain decision.

6. Provider IO must not happen while a worker holds a DB session.
   Materialize DB rows, close the session, call the provider, then open a
   new worker session to persist results.
   The worker manifest declares whether a worker performs provider IO; the
   worker implementation enforces the boundary with explicit worker
   session/transaction helpers. A provider call inside a DB session or
   transaction is a bug.

7. Cancellation cleanup is part of the domain state machine. If a
   hard timeout interrupts provider IO after a claim, the worker must
   terminalize or requeue the claim and persist audit evidence before
   re-raising `asyncio.CancelledError`.

8. Operator resolution of `worker_queue_terminal_events` is a platform
   state-machine transition, not a best-effort audit update. It uses
   `SELECT ... FOR UPDATE`, so retry/archive/quarantine actions and registered
   retry transitions must run inside a callable connection transaction. Missing
   transaction support fails before the row-lock read. Source-row terminal
   ledger writes that own commit use the same transaction contract. Terminal
   ledger `INSERT ... ON CONFLICT ... RETURNING *` writes and operator-action
   `UPDATE ... RETURNING *` writes must validate cursor rowcount against
   returned-row presence before terminal rows, operator payloads, or retry
   transitions are reported.

9. Public surfaces read read models or query services. They do not call
   providers, perform token resolution, run scoring, or reconstruct old
   fallback payloads.

10. Cache-only state must be labeled cache-only. `LivePriceGateway`
   publishes latest market display updates but does not write market
   facts and must not become a correctness dependency. Its fan-out path awaits
   the async WebSocket hub `publish(payload)` contract directly and must not
   accept synchronous callback results through `inspect.isawaitable(...)`
   compatibility.

11. Upstream frame delivery must use formal async runtime contracts. GMGN
   DirectWS awaits the collector's `handle_frame(...)` handler directly;
   synchronous frame callbacks are malformed wiring, not test compatibility.

## Debug Playbook

Use this order for real-data investigations:

1. Confirm runtime config.
   Run `uv run parallax config` and confirm
   `config_path` and `workers_config_path` point at
   `~/.parallax/`. Report paths and redacted booleans only.

2. Check worker status.
   Use `/api/status`, `/readyz`, or `ops worker-status`. Look under the
   `workers` map for manifest worker status and `worker_lanes` for lane-level
   enabled/running/failed/timeout counts, summed queue depth, and
   `queue_health`. `queue_health` shows read-only due/running/failed/blocked
   queue counts, source-table terminal statuses, terminal-ledger evidence, and
   oldest due/running age for manifest-owned job, delivery, status, and dirty
   target queues. Missing or malformed required aggregate fields are adapter
   contract failures, never an idle/zero queue. Old top-level worker status
   sections are not part of the contract.

3. Identify the missing truth.
   Ask which fact should exist: event, intent, resolution, identity,
   market tick, enriched event, profile source, or audit row.

4. Identify the projection.
   If the fact exists but the UI/API is wrong, inspect the read model:
   `token_radar_current_rows` plus `token_radar_publication_state`,
   `token_profile_current`, `pulse_candidates`, or the relevant
   watchlist/notification model.

5. Check wake versus catch-up.
   If a wake was missed, the next `interval_seconds` catch-up should
   recover. A missed `NOTIFY` is not a correctness bug unless catch-up is
   also broken or unbounded.

6. Check terminal states.
   Pending forever is a design smell. Find the worker that owns the queue
   and verify it can move rows to `done`, `expired`, `failed`, or abstain.

7. Check provider health last.
   Provider failures explain missing fresh facts, but they should not
   corrupt old facts or erase deterministic identity.

## Worker Review Checklist

For each worker, answer these questions before changing code:

- What is the worker's canonical key in `worker_manifest.py`?
- Is it constructed by the owning domain factory?
- Which settings block in `workers.yaml` controls it?
- Does it inherit `WorkerBase`?
- Does it need an advisory lock because it is a single read-model writer?
- Which fact tables does it read?
- Which fact tables or read models does it write?
- Does it emit or listen to wake hints?
- Can it recover when a wake hint is missed?
- Does every pending job state have a terminal state?
- Does provider IO happen outside DB sessions?
- Is every custom status hook (`_queue_depth()`, details payload, queue
  health) callable from `/readyz` and read-only?
- If the worker calls a provider, does a concrete provider-wrapper test cover
  the exact protocol methods used in runtime?
- If the worker is LLM-backed, does it reserve agent capacity before claiming
  business work?
- If it writes current rows, are row keys stable product/window keys and do
  unchanged projections write zero serving rows?
- If it claims dirty work or publishes rank/current sets, do claim width,
  publish width, lease timing, retry timing, and lease owner come explicitly
  from worker settings rather than service defaults?
- Is the public API reading facts/read models instead of worker internals?
- Is the owning domain `ARCHITECTURE.md` updated?
- Is `docs/WORKERS.md` updated in the same change?

## Mature-System Optimizations

Mature systems with many workers usually do not remove all state
machines. They make the state machines explicit, small, and owned.

Useful patterns for this repo:

- Keep data plane and control plane separate.
  Facts such as `market_ticks` and `enriched_events` are data plane.
  Tables such as `event_anchor_backfill_jobs` are control plane.

- Prefer idempotent projections.
  A projection can run again and replace a read model without inventing
  new product facts.

- Prefer bounded catch-up over delivery assumptions.
  LISTEN/NOTIFY reduces latency but does not replace polling or offsets.

- Make status inspectable by layer.
  A good status payload tells the operator whether provider IO, fact
  persistence, projection, or decision runtime is stale.

- Keep provider adapters narrow.
  Concrete clients translate third-party shapes. Domain workers receive
  typed provider protocols and own product decisions.

- Use stable payload hashes for hot-row idempotency.
  Token Radar source edges, equity provider documents, and equity evidence
  artifacts should not rewrite TOAST-heavy payload rows when the normalized
  payload has not changed.

- Split coordination when a file has too many reasons to change.
  Large projection and agent-runtime files should gradually move toward
  source query, projection service, persistence repository, and runtime
  worker boundaries.

- Delete old runtime paths hard.
  Runtime fallbacks and compatibility overlays create two truths. Specs
  and migrations can mention history; runtime code should not depend on
  old shapes.

## Agent Pitfalls

Avoid these common mistakes:

- Treating `NOTIFY` as a queue.
- Treating a provider frame as a fact before it is persisted.
- Adding a second writer to a read model.
- Fixing an API row by calling a provider from the route.
- Reconstructing market context from worker job state.
- Using queue status as product truth.
- Making run, generation, timestamp, or UUID ids part of current-row identity.
- Letting status or readiness hooks drift from `WorkerBase` call signatures.
- Testing fake providers but not the concrete runtime provider wrapper.
- Debugging real data from repo fixtures instead of
  `~/.parallax/config.yaml` and `workers.yaml`.
- Updating `AGENTS.md` without mirroring `CLAUDE.md`.
