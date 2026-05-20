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

Every long-running worker listed here is a `WorkerBase` subclass.
`runtime.bootstrap()` builds the process runtime:

```text
settings + workers.yaml
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
bounded `interval_seconds` catch-up from `workers.yaml`.

## Truth Categories

Review workers by separating four categories:

| Category | Meaning | Examples | Rule |
|----------|---------|----------|------|
| Facts | Business observations and decisions that should be replayable | `events`, `token_intent_resolutions`, `asset_identity_evidence`, `asset_identity_current`, `market_ticks`, `enriched_events`, Pulse audit rows | Facts are product truth. |
| Read models | Rebuildable projections for reads and product workflows | `token_radar_rows`, `token_profile_current`, `pulse_candidates`, watchlist summaries | Exactly one runtime writer. |
| Control plane | Scheduling, retry, lease, budget, and queue state | `event_anchor_backfill_jobs`, `pulse_agent_jobs`, notification deliveries | Never treat job state as product truth. |
| Cache/fan-out | Process-local convenience state | `LivePriceGateway` latest cache and WebSocket fan-out | Cache is presentation-only unless persisted as facts. |

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
  -> token_radar_projection
  -> narrative_admission
  -> mention_semantics / token_discussion_digest
  -> pulse_candidate / notifications / API / WebSocket / CLI
```

`IngestService` is not a long-running worker, but it is listed in this
document because every downstream worker depends on the facts it writes.

## Worker Inventory

<!-- worker-inventory-keys:
collector, token_capture_tier, market_tick_stream, market_tick_poll,
event_anchor_backfill, live_price_gateway, resolution_refresh,
asset_profile_refresh, token_radar_projection, token_profile_current,
narrative_admission, mention_semantics, token_discussion_digest,
news_fetch, news_item_process, news_story_projection,
news_item_brief, news_page_projection,
pulse_candidate, enrichment, handle_summary, notification_rule,
notification_delivery
-->

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `collector` (`CollectorService`) | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
| `token_capture_tier` (`TokenCaptureTierWorker`) | `asset_market` | `domains/asset_market/runtime/token_capture_tier_worker.py` | active Token Radar live market targets | `token_capture_tier` | poll | none | `interval_seconds` |
| `market_tick_stream` (`MarketTickStreamWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_stream_worker.py` | `token_capture_tier(tier=1)`, OKX DEX WS | `market_ticks(source_tier='tier1_ws')` | provider-driven (WS) | `market_tick_written` | bounded stream cycle |
| `market_tick_poll` (`MarketTickPollWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_poll_worker.py` | `token_capture_tier(tier=2)`, OKX DEX/CEX REST quotes | `market_ticks(source_tier='tier2_poll')` | poll | `market_tick_written` | `interval_seconds` |
| `event_anchor_backfill` (`EventAnchorBackfillWorker`) | `asset_market` | `domains/asset_market/runtime/event_anchor_backfill_worker.py` | due `event_anchor_backfill_jobs`, event-adjacent `market_ticks`, quote providers inside the lag budget | `market_ticks`, narrow `enriched_events` lifecycle transition, `event_anchor_backfill_jobs` status | poll | `market_tick_written` | `interval_seconds` |
| `live_price_gateway` (`LivePriceGateway`) | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | latest `market_ticks` per target | in-process latest cache and WebSocket fan-out only | poll | none | `interval_seconds` |
| `resolution_refresh` (`ResolutionRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | NIL / AMBIGUOUS lookup keys, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | poll | `resolution_updated` | `interval_seconds` |
| `asset_profile_refresh` (`AssetProfileRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | resolved DEX assets due for refresh, configured DEX profile sources | `asset_profiles` | poll | none | `interval_seconds` |
| `token_radar_projection` (`TokenRadarProjectionWorker`) | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | facts via `token_radar_source_query`, `market_ticks`, `enriched_events`, `asset_identity_current` | `token_radar_rows`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_tick_written`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `token_profile_current` (`TokenProfileCurrentWorker`) | `asset_market` | `domains/asset_market/runtime/token_profile_current_worker.py` | `asset_profiles`, `cex_token_profiles`, exact GMGN stream evidence, exact OKX DEX evidence, current Radar targets | `token_profile_current` | poll | none | `interval_seconds` |
| `narrative_admission` (`NarrativeAdmissionWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/narrative_admission_worker.py` | latest ready `token_radar_rows` frontier, `events`, current `token_intent_resolutions` | `narrative_admissions` | `token_radar_updated`, `resolution_updated` | none | `interval_seconds` |
| `mention_semantics` (`MentionSemanticsWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/mention_semantics_worker.py` | due `narrative_admissions` source sets, `events`, queued semantics | `token_mention_semantics`, `narrative_model_runs` | `token_radar_updated`, `resolution_updated` | `narrative_semantics_updated` | `interval_seconds` |
| `token_discussion_digest` (`TokenDiscussionDigestWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/token_discussion_digest_worker.py` | `narrative_admissions`, `token_mention_semantics`, market/profile facts | `token_discussion_digests`, `narrative_model_runs` | `token_radar_updated`, `narrative_semantics_updated`, `market_tick_written` | none | `interval_seconds` |
| `news_fetch` (`NewsFetchWorker`) | `news_intel` | `domains/news_intel/runtime/news_fetch_worker.py` | configured `news_intel.sources`, due `news_sources`, RSS/Atom feeds | `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items` | poll | `news_item_written` | `interval_seconds` |
| `news_item_process` (`NewsItemProcessWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_process_worker.py` | unprocessed `news_items`, token identity interfaces | `news_item_entities`, `news_token_mentions`, `news_fact_candidates` | `news_item_written` | `news_item_processed` | `interval_seconds` |
| `news_story_projection` (`NewsStoryProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_story_projection_worker.py` | `news_items`, `news_item_entities`, `news_token_mentions`, `news_fact_candidates` | `news_story_groups`, `news_story_members` | `news_item_processed` | `news_story_updated` | `interval_seconds` |
| `news_item_brief` (`NewsItemBriefWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_brief_worker.py` | processed `news_items`, `news_story_groups`, current brief state | `news_item_agent_runs`, `news_item_agent_briefs` | `news_item_processed`, `news_story_updated` | `news_item_brief_updated` | `interval_seconds` |
| `news_page_projection` (`NewsPageProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_page_projection_worker.py` | `news_items`, `news_item_entities`, `news_token_mentions`, `news_fact_candidates`, `news_story_groups`, `news_story_members` | `news_page_rows` | `news_item_written`, `news_item_processed`, `news_story_updated`, `news_item_brief_updated` | none | `interval_seconds` |
| `pulse_candidate` (`PulseCandidateWorker`) | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `token_radar_rows` latest per target/window/scope for Pulse `1h`/`4h` horizons, gate fields, route policy, source-quality policy | `pulse_agent_jobs`, `pulse_candidate_edge_state`, `pulse_candidate_run_budget`, `pulse_target_run_budget`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_agent_runtime_versions`, `pulse_agent_eval_cases`, `pulse_agent_eval_results`, `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_playbook_snapshots` | `token_radar_updated` | none | `interval_seconds` |
| `enrichment` (`EnrichmentWorker`) | `social_enrichment` | `domains/social_enrichment/runtime/enrichment_worker.py` | watched events queue, OpenAI Agents enrichment | enrichment label rows, `model_run` audit, outbound watchlist summary enqueue hook | poll | none | `interval_seconds` |
| `handle_summary` (`HandleSummaryWorker`) | `watchlist_intel` | `domains/watchlist_intel/runtime/handle_summary_worker.py` | due `watchlist_handle_summary_jobs`, handle signal events | `watchlist_handle_summaries`, `watchlist_handle_summary_runs`, job status | poll | none | `interval_seconds` |
| `notification_rule` (`NotificationWorker`) | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | notification rule evaluations | poll | none | `interval_seconds` |
| `notification_delivery` (`NotificationDeliveryWorker`) | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending deliveries | delivery rows | poll | none | `interval_seconds` |

## Narrative Intel Hard-Cut Ownership

`narrative_admissions.source_event_ids_json` is the source-set truth for
Narrative Intelligence. Health, digest completeness, public currentness, and
semantics queue depth must expand admitted source sets first; existing
`token_mention_semantics` rows cannot define source volume by themselves. The
same event may count once per current admission/window/scope, but duplicate
semantic fingerprints for one admission-source row still count as one covered
source row.

Writer ownership remains narrow: `NarrativeAdmissionWorker` writes
`narrative_admissions`, `MentionSemanticsWorker` writes
`token_mention_semantics`, and `TokenDiscussionDigestWorker` writes
`token_discussion_digests`. `ops rebuild-narrative-intel` has the only
maintenance writer exception: while it holds the narrative worker advisory
locks, it may run hard-cut cleanup that deletes obsolete queued/retryable/stale
semantics and marks suppressed or fingerprint-mismatched current digests stale.
HTTP routes and normal worker loops must not call that cleanup path.

This is a hard cut with no runtime compatibility. Removed settings, source-age
prune behavior, stale digest fallbacks, and old public digest reasons are not
kept as aliases. Public digest missing state is reported through
`digest_not_ready`, `digest_stale`, or `not_in_current_frontier`; LLM cycle
backpressure is reported as `llm_cycle_budget_exhausted` or
`llm_failure_budget_exhausted`.

## IngestService Boundary

`IngestService` writes the first durable facts in a single transaction:
`events`, `event_entities`, `token_evidence`, `token_intents`,
`token_intent_lookup_keys`, `token_intent_resolutions`,
`registry_assets`, `asset_identity_evidence`,
`asset_identity_current`, `market_ticks`, and `enriched_events`.

Inline event capture writes Tier 3 `market_ticks(source_tier='tier3_inline')`
and matching `enriched_events`. When an event anchor cannot be attached
from a fresh existing tick, ingest writes an `enriched_events` pending
fact and enqueues `event_anchor_backfill_jobs` control-plane work.

`IngestService` is transactional. It is called by `collector`; it is not
a `WorkerBase` subclass and does not get a `workers.yaml` key.

## Market Capture Lanes

Market capture has several lanes by design. This does not violate the
single-writer rule because `market_ticks` is an append-only fact table,
not a read model.

- `token_capture_tier` writes the rebuildable control projection that
  assigns active targets to Tier 1 stream, Tier 2 poll, or Tier 3
  inline-only capture.
- `market_tick_stream` owns Tier 1 OKX DEX WebSocket capture. It accepts
  only `chain_token` targets from `token_capture_tier(tier=1)`.
- `market_tick_poll` owns Tier 2 REST capture for DEX and CEX targets.
  It is the steady-state REST quote worker.
- `event_anchor_backfill` owns short-lived event-anchor catch-up. It
  consumes `event_anchor_backfill_jobs`, attaches a persisted nearby tick
  first, calls providers only inside the configured lag budget, and then
  terminalizes work.
- `live_price_gateway` reads latest persisted `market_ticks` and fans out
  WebSocket updates. It does not call upstream price providers and never
  writes market facts.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker`, `EventAnchorBackfillWorker` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `MentionSemanticsWorker`, `TokenDiscussionDigestWorker`, `PulseCandidateWorker` | `{window, scope}` |
| `narrative_semantics_updated` | `MentionSemanticsWorker` | `TokenDiscussionDigestWorker` | `{window, scope, target_count}` |
| `news_item_written` | `NewsFetchWorker` | `NewsItemProcessWorker`, `NewsPageProjectionWorker` | `{source_id, count}` |
| `news_item_processed` | `NewsItemProcessWorker` | `NewsStoryProjectionWorker`, `NewsItemBriefWorker`, `NewsPageProjectionWorker` | `{count}` |
| `news_story_updated` | `NewsStoryProjectionWorker` | `NewsItemBriefWorker`, `NewsPageProjectionWorker` | `{count}` |
| `news_item_brief_updated` | `NewsItemBriefWorker` | `NewsPageProjectionWorker` | `{count}` |

Wake payloads are hints only. Consumers re-read DB on wake and catch up
on their configured cadence. `DBPoolBundle` owns wake emission and
listener construction through `wake_emitter()` and `wake_listener()`.
Domain workers never call `pg_notify` directly.

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
- `runtime.bootstrap()` constructs `Runtime.workers` from the canonical
  registry and replaces unavailable or disabled workers with disabled
  `WorkerBase` placeholders so status payloads always contain the same
  keys.
- `WorkerScheduler.start()` starts enabled workers in registry priority
  order. `WorkerScheduler.stop()` calls `stop()`, waits for tasks,
  cancels stragglers, calls `aclose()`, and closes the `DBPoolBundle`.
- `/readyz`, `/api/status`, and `ops worker-status` expose worker state
  only under the `workers` map. `collector.details` carries collector
  counters, including `snapshot_gate_outcomes`; `snapshot_gate` is a
  global health field copied from those counters.
- Runtime knobs live in `~/.gmgn-twitter-intel/workers.yaml`. The
  application/provider config in `config.yaml` must not contain worker
  interval, batch, concurrency, lease, max-attempt, timeout, advisory
  lock, or wake-channel settings.

## Agent Execution Plane

LLM-backed workers use one shared `AgentExecutionGateway` per process.
The gateway is an operational control plane only: it owns OpenAI Agents
SDK execution, lane bulkheads, request/result audit envelopes, timeout,
circuit breaker, safety-net fallback, and ops status. It does not claim
domain jobs, write domain queues, or persist product read models.

The low-level `LLMGateway` is transport-only. It owns OpenAI client
construction, trace export configuration, and cleanup. It does not expose
worker/stage execution limits.

Current lanes are configured under `workers.agent_runtime` in
`workers.yaml`. `agent_runtime.defaults.model` is the single global
agent model default; any lane can override `model` locally and otherwise
inherits that default. Current lanes are `pulse.pipeline`, `pulse.signal_analyst`,
`pulse.bear_case`, `pulse.risk_portfolio_judge`,
`narrative.mention_semantics`, `narrative.discussion_digest`,
`social.event_enrichment`, `watchlist.handle_summary`,
`news.fact_candidate`, and `news.item_brief`. Attempt-burning workers
reserve capacity before claiming DB work:

- `pulse_candidate` reserves `pulse.pipeline` before `pulse_agent_jobs`
  claim. The pipeline reservation owns the parent global slot for the
  full decision run; child stages reuse that parent global slot and
  acquire only their stage lane bulkhead (`pulse.signal_analyst`,
  `pulse.bear_case`, or `pulse.risk_portfolio_judge`).
- `enrichment` reserves `social.event_enrichment` before claiming
  enrichment jobs and passes that reservation into the actual stage.
- `handle_summary` reserves `watchlist.handle_summary` before claiming
  summary jobs and passes that reservation into the actual stage.
- `news_item_brief` selects a processed news item, writes no-start
  backpressure as `execution_started=false`, and executes the single-item
  brief only through `AgentExecutionGateway` lane `news.item_brief`.

If reservation is denied, the worker records
`agent_backpressure_capacity_denied` in its iteration notes and does not
claim a job, so no-start backpressure does not burn attempts. Workers
that discover no-start backpressure after claiming must release or
reschedule without charging the claim as a provider attempt. Narrative
workers currently rely on provider-stage reservations because their claim
semantics do not burn attempts before model execution in the same way.

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
2. Add the canonical key and class path to
   `app/runtime/worker_registry.py`, add a matching
   `WorkersSettings` field and default `workers.yaml` block, and
   construct the worker in the owning domain factory under
   `app/runtime/worker_factories/`.
3. Add a row to this file's worker inventory.
4. Add or update the wake channels table here if the worker introduces a
   channel, and add its `wakes_on` list to `workers.yaml` when it listens
   for wake hints.
5. Document the worker in the owning domain's `ARCHITECTURE.md` stage
   map.
6. If the worker writes a new derived table, declare it as a read model
   and name its single writer in `ARCHITECTURE.md`.
7. Extend architecture guards so `WorkerBase`, `worker_registry.py`,
   `WorkersSettings`, the default `workers.yaml`, and this file's
   `worker-inventory-keys` marker stay in lockstep.

## Update Triggers

Update this file in the same change as any of:

- A new worker class or removal of an existing one.
- A worker gaining or losing a wake-in or wake-out channel.
- A change to a catch-up cadence default.
- A worker moving between domains.
- A new `NOTIFY` channel name or hint payload shape.
- A read model gaining a new runtime writer or losing its declared writer.
- A control-plane table becoming part of a worker's scheduling contract.
