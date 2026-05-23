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
   - token_capture_tier ranks active market targets into stream, poll, or inline-only lanes
   - market_tick_stream writes Tier 1 WebSocket market_ticks
   - market_tick_poll writes Tier 2 REST market_ticks
   - event_anchor_backfill finishes short-lived pending event anchors
   - resolution_refresh discovers and reprocesses NIL / AMBIGUOUS lookups
   - asset_profile_refresh writes provider profile source caches
   - token_image_mirror mirrors eligible provider logo URLs into local cached files
   - token_profile_current projects public profile/icon facts from persisted sources and ready local image rows
   - live_price_gateway reads latest market_ticks and fans out cache-only WebSocket updates

4. Token Intel projection
   - token_radar_projection claims token_radar_dirty_targets and reads one target at a time through token_radar_target_feature_query
   - publishes token_radar_target_features, token_radar_current_rows for hot reads, token_radar_rank_history for compact rank history, and token_radar_snapshot_audit for point-in-time factor snapshots
   - emits token_radar_updated as a wake hint

5. Narrative Intelligence read models
   - narrative_admission reads the latest ready Radar frontier and material facts, then writes current source-set admissions
   - mention_semantics claims due semantic rows and labels only source events from current admissions
   - token_discussion_digest evaluates the current admission against the last ready epoch with `NarrativeEpochPolicy`
   - 5m admissions are scanner-only and are scanned/deferred without discussion-digest writes
   - 1h/4h/24h material delta, TTL expiry, or first ready work seals a new digest epoch; non-material delta leaves the last ready snapshot readable
   - emits narrative_semantics_updated only as a wake hint for digest refresh

6. Consumers
   - Pulse reads token_radar_current_rows, gates candidates, runs the agent, and writes audit rows
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

4. Every pending control-plane state needs a terminal path such as
   `done`, `expired`, `failed`, or an explicit abstain decision.

5. Provider IO must not happen while a worker holds a DB session.
   Materialize DB rows, close the session, call the provider, then open a
   new worker session to persist results.

6. Cancellation cleanup is part of the domain state machine. If a
   hard timeout interrupts provider IO after a claim, the worker must
   terminalize or requeue the claim and persist audit evidence before
   re-raising `asyncio.CancelledError`.

7. Public surfaces read read models or query services. They do not call
   providers, perform token resolution, run scoring, or reconstruct old
   fallback payloads.

8. Cache-only state must be labeled cache-only. `LivePriceGateway`
   publishes latest market display updates but does not write market
   facts and must not become a correctness dependency.

## Debug Playbook

Use this order for real-data investigations:

1. Confirm runtime config.
   Run `uv run gmgn-twitter-intel config` and confirm
   `config_path` and `workers_config_path` point at
   `~/.gmgn-twitter-intel/`. Report paths and redacted booleans only.

2. Check worker status.
   Use `/api/status`, `/readyz`, or `ops worker-status`. Look under the
   `workers` map only. Old top-level worker status sections are not part
   of the contract.

3. Identify the missing truth.
   Ask which fact should exist: event, intent, resolution, identity,
   market tick, enriched event, profile source, or audit row.

4. Identify the projection.
   If the fact exists but the UI/API is wrong, inspect the read model:
   `token_radar_current_rows`, `token_radar_rank_history`,
   `token_radar_snapshot_audit`, `token_profile_current`,
   `pulse_candidates`, or the relevant watchlist/notification model.

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

- What is the worker's canonical key in `worker_registry.py`?
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
- Debugging real data from repo fixtures instead of
  `~/.gmgn-twitter-intel/config.yaml` and `workers.yaml`.
- Updating `AGENTS.md` without mirroring `CLAUDE.md`.
