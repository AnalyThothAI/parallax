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
   - calls IngestService for each normalized Twitter event

2. IngestService transaction
   - writes events and event_entities
   - extracts token_evidence
   - creates token_intents and lookup keys
   - writes current token_intent_resolutions
   - writes registry_assets and asset_identity_evidence/current
   - writes inline market_ticks when a fresh event-adjacent tick exists
   - writes enriched_events for the event anchor lifecycle
   - enqueues event_anchor_backfill_jobs when the anchor is pending

3. Asset Market workers
   - token_capture_tier claims `token_capture_tier_dirty_targets` before ranking active market targets into stream, poll, or inline-only lanes
   - market_tick_stream writes Tier 1 WebSocket market_ticks
   - market_tick_poll writes Tier 2 REST market_ticks
   - event_anchor_backfill finishes short-lived pending event anchors
   - resolution_refresh discovers and reprocesses NIL / AMBIGUOUS lookups
   - asset_profile_refresh claims provider-scoped `asset_profile_refresh_targets` before provider calls and writes provider profile source caches
   - token_image_mirror claims `token_image_source_dirty_targets` and mirrors exact provider logo URLs into local cached files
   - token_profile_current claims `token_profile_current_dirty_targets` and projects public profile/icon facts from exact persisted sources and ready local image rows
   - live_price_gateway reads `token_capture_tier` control rows and latest market_ticks, then fans out cache-only WebSocket updates

4. Token Intel projection
   - token_radar_projection claims token_radar_dirty_targets and uses bounded interval catch-up
   - source/market/repair dirty kinds decide whether source edges must rebuild or whether existing source edges can be reused
   - it builds compact source edges and projection-private token_radar_target_features from material facts
   - market-only work overlays fresh latest market context on stable source packets instead of rehydrating every source event
   - it publishes one stable generation into token_radar_current_rows and token_radar_publication_state for online reads
   - emits token_radar_updated as a wake hint

5. Narrative Intelligence read models
   - narrative_admission claims `narrative_admission_dirty_targets`, then reads exact Radar/material facts and writes current source-set admissions
   - mention_semantics claims due semantic rows and labels only source events from current admissions
   - token_discussion_digest claims `discussion_digest_dirty_targets` and evaluates the exact current admission against the last ready epoch with `NarrativeEpochPolicy`
   - 5m admissions are scanner-only and are scanned/deferred without discussion-digest writes
   - 1h/4h/24h material delta, TTL expiry, or first ready work seals a new digest epoch; non-material delta leaves the last ready snapshot readable
   - emits narrative_semantics_updated only as a wake hint for digest refresh

6. Consumers
   - Pulse claims `pulse_trigger_dirty_targets`, exact-loads Token Radar rows, gates candidates, runs the agent, and writes audit rows
   - Pulse may include ready discussion digest evidence but never triggers narrative workers
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
  -> worker.stop(), task cancellation, worker.aclose(), DBPoolBundle.aclose()
```

`run_once()` is the business boundary. The common runtime owns looping,
timeouts, backoff, status payloads, advisory locks, and close semantics.
Domain workers should keep external provider IO outside DB sessions and
should use `DBPoolBundle.worker_session()`.

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
  explicit ops repair command that enqueues dirty targets.
- A worker writes while holding the wrong boundary open. Provider, publisher,
  wake-wait, file, subprocess, and network IO must run outside DB worker
  sessions; only materialization and persistence belong inside sessions.
- A worker treats a broad table scan as a queue. Event-anchor catch-up consumes
  `event_anchor_backfill_jobs`; Token Radar consumes dirty targets with dirty
  kind flags. Empty queues mean idle, not "scan the fact table to be sure."
- A status hook is treated as diagnostics-only. `status_payload()`,
  `_queue_depth()`, queue health, `/readyz`, and `ops worker-status` are
  production contracts. Custom queue-depth hooks must be callable by
  `WorkerBase.status_payload()` with no required arguments and must not
  mutate queue state.
- A fake provider satisfies tests while the real wrapper misses the domain
  protocol. Workers should depend on narrow provider protocols, and tests
  must exercise the concrete runtime wrapper for every method the worker
  calls, including audit methods.
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
- `market_ticks` records append-only market samples.
- `enriched_events` records event-anchor market context for an event.

Facts are the business source of truth. If public behavior disagrees with
facts, the public behavior is suspect.

### Control-Plane Job State

Control-plane job state answers: "What work is due, retried, done,
expired, or failed?"

Examples:

- `event_anchor_backfill_jobs`
- `pulse_agent_jobs`
- `watchlist_handle_summary_jobs`
- notification delivery rows

These rows schedule work. They are not product facts by themselves.
Product surfaces should not infer token quality from a queue status.

Dirty-target queues such as `pulse_trigger_dirty_targets`,
`narrative_admission_dirty_targets`, `discussion_digest_dirty_targets`,
`token_profile_current_dirty_targets`, `token_image_source_dirty_targets`,
`asset_profile_refresh_targets`, and `token_capture_tier_dirty_targets` are
control-plane rows only. They are repaired through explicit ops commands that
enqueue targets; normal worker loops do not fall back to historical scans when
the queue is empty.

Worker identity and lane grouping come from `WorkerManifest v1` only.
`workers.yaml` can tune a manifest worker's cadence, lease, timeout, attempt,
batch, wake, and agent budget settings, but it cannot create a worker or alias
an old queue name. For watchlist summaries the queue contract is
`watchlist_handle_summary_jobs`.

### Narrative Currentness State

Narrative digest state answers: "What readable narrative epoch do we have, and
how far is it from the current source frontier?"

The current source frontier is `narrative_admissions`. A ready digest is a
sealed epoch in `token_discussion_digests`. Public reads compose:

```text
last-ready digest + current admission delta -> discussion_digest.currentness
```

`currentness.display_status` is one of `current`, `updating`, `stale`,
`not_ready`, `out_of_frontier`, or `unsupported_window`. New source events do
not blank the narrative. They first become delta; only material delta, epoch
TTL, or first-ready work runs the digest LLM. The API route never calls the LLM
or writes narrative tables.

### Projection Freshness State

Projection state answers: "Is a rebuildable read model current enough to
serve?"

Examples:

- `projection_runs`
- `projection_offsets`
- projection coverage rows
- `token_radar_current_rows.computed_at_ms`
- `token_mention_semantics.computed_at_ms`
- `token_discussion_digests.computed_at_ms`
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
   Workers with `RuntimeWorkerContext` enforce this through explicit
   `claim_session`, `payload_session`, `provider_io`, `persist_session`, and
   `transaction_session` boundaries. A provider call inside a DB session or
   transaction is a bug.

7. Cancellation cleanup is part of the domain state machine. If a
   hard timeout interrupts provider IO after a claim, the worker must
   terminalize or requeue the claim and persist audit evidence before
   re-raising `asyncio.CancelledError`.

8. Public surfaces read read models or query services. They do not call
   providers, perform token resolution, run scoring, or reconstruct old
   fallback payloads.

9. Cache-only state must be labeled cache-only. `LivePriceGateway`
   publishes latest market display updates but does not write market
   facts and must not become a correctness dependency.

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
   queue counts and oldest due/running age for manifest-owned job, delivery,
   status, and dirty target queues. Old top-level worker status sections are
   not part of the contract.

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
