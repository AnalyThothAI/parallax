# Workers

> **Scope.** Cross-domain runtime worker inventory: each long-running
> worker's fact writes, wake-in and wake-out channels, and catch-up
> cadence. Domain stage maps live in each domain's `ARCHITECTURE.md`;
> operational invariants live in `RELIABILITY.md`; the architecture
> invariants this inventory implements live in `ARCHITECTURE.md`.

Every long-running worker listed here is a `WorkerBase` subclass.
`app/runtime/bootstrap.py` builds the canonical runtime worker registry
from `worker_registry.py`, `workers.yaml`, providers, and `DBPoolBundle`.
`WorkerScheduler` is the only runtime owner that starts, stops, closes,
and reports worker tasks. Worker correctness must not depend on `NOTIFY`
delivery — every listener has a bounded `interval_seconds` catch-up from
`workers.yaml`.

## Worker Inventory

<!-- worker-inventory-keys:
collector, token_capture_tier, market_tick_stream, market_tick_poll,
event_anchor_backfill, live_price_gateway, resolution_refresh,
asset_profile_refresh, token_radar_projection, token_profile_current,
pulse_candidate, enrichment, handle_summary, harness_ops,
notification_rule, notification_delivery
-->

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `collector` (`CollectorService`) | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
| `token_capture_tier` (`TokenCaptureTierWorker`) | `asset_market` | `domains/asset_market/runtime/token_capture_tier_worker.py` | active Token Radar live market targets | `token_capture_tier` | poll | none | `interval_seconds` |
| `market_tick_stream` (`MarketTickStreamWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_stream_worker.py` | `token_capture_tier(tier=1)`, OKX DEX WS | `market_ticks(source_tier='tier1_ws')` | provider-driven (WS) | `market_tick_written` | bounded stream cycle |
| `market_tick_poll` (`MarketTickPollWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_poll_worker.py` | `token_capture_tier(tier=2)`, OKX DEX/CEX REST quotes | `market_ticks(source_tier='tier2_poll')` | poll | `market_tick_written` | `interval_seconds` |
| `event_anchor_backfill` (`EventAnchorBackfillWorker`) | `asset_market` | `domains/asset_market/runtime/event_anchor_backfill_worker.py` | `enriched_events` pending rows | `market_ticks`, `enriched_events` async backfill transition | poll | `market_tick_written` | `interval_seconds` |
| `live_price_gateway` (`LivePriceGateway`) | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | latest `market_ticks` per target | in-process latest cache and WebSocket fan-out only | poll | none | `interval_seconds` |
| `resolution_refresh` (`ResolutionRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | NIL / AMBIGUOUS lookup keys, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | poll | `resolution_updated` | `interval_seconds` |
| `asset_profile_refresh` (`AssetProfileRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | resolved DEX assets due for refresh, GMGN exact-token profile | `asset_profiles` | poll | none | `interval_seconds` |
| `token_radar_projection` (`TokenRadarProjectionWorker`) | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | facts via `token_radar_source_query`, `market_ticks`, `enriched_events`, `asset_identity_current` | `token_radar_rows`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_tick_written`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `token_profile_current` (`TokenProfileCurrentWorker`) | `asset_market` | `domains/asset_market/runtime/token_profile_current_worker.py` | `asset_profiles`, exact GMGN stream evidence, exact OKX DEX evidence, current Radar targets | `token_profile_current` | poll | none | `interval_seconds` |
| `pulse_candidate` (`PulseCandidateWorker`) | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `token_radar_rows` latest per target/window/scope, gate fields, route policy | `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_agent_runs`, `pulse_agent_run_steps` | `token_radar_updated` | none | `interval_seconds` |
| `enrichment` (`EnrichmentWorker`) | `social_enrichment` | `domains/social_enrichment/runtime/enrichment_worker.py` | watched events queue, OpenAI Agents enrichment | enrichment label rows, `model_run` audit, outbound watchlist summary enqueue hook | poll | none | `interval_seconds` |
| `handle_summary` (`HandleSummaryWorker`) | `watchlist_intel` | `domains/watchlist_intel/runtime/handle_summary_worker.py` | due `watchlist_handle_summary_jobs`, handle signal events | `watchlist_handle_summaries`, `watchlist_handle_summary_runs`, job status | poll | none | `interval_seconds` |
| `harness_ops` (`HarnessOpsWorker`) | `closed_loop_harness` | `domains/closed_loop_harness/runtime/harness_ops_worker.py` | due `harness_snapshots`, entry/exit `market_ticks` looked up via `registry_assets.chain_token_market_target(...)` | `harness_snapshots.outcome_status`, `harness_outcomes`, `harness_credits`, `harness_weights` | poll | none | `interval_seconds` |
| `notification_rule` (`NotificationWorker`) | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | notification rule evaluations | poll | none | `interval_seconds` |
| `notification_delivery` (`NotificationDeliveryWorker`) | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending deliveries | delivery rows | poll | none | `interval_seconds` |

`IngestService` is documented here because every other worker depends
on the facts its transaction writes (`events`, `event_entities`,
`token_evidence`, `token_intents`, `token_intent_lookup_keys`,
`token_intent_resolutions`, `registry_assets`,
`asset_identity_evidence`, `asset_identity_current`, `market_ticks`,
and `enriched_events`). Inline event capture writes Tier 3
`market_ticks(source_tier='tier3_inline')` and enriched event rows in
the ingest transaction. It is a
transactional service called by `collector`, not a long-running worker
and not a `WorkerBase` subclass.

## Tier and Lane Boundaries

The market-data lanes carry strict ownership rules. The full upstream
provider map lives in `ARCHITECTURE.md` (Market Data Provider Matrix);
the runtime invariants are:

- `market_tick_stream` accepts only Tier 1 `chain_token` rows from
  `token_capture_tier`. CEX symbols never enter Tier 1, and no other
  worker subscribes to the OKX DEX WebSocket.
- `market_tick_poll` owns CEX quotes (`OKX CEX REST`, no fallback) and
  Tier 2 DEX quotes (`GMGN OpenAPI REST` primary, `OKX DEX REST`
  fallback). It is the only worker that calls the CEX quote provider in
  the steady-state poll path.
- `event_anchor_backfill` shares the Tier 2 provider stack but writes
  `market_ticks` and the narrow `enriched_events` async-backfill
  transition for events whose ingest path found no fresh tick. It is the
  only worker permitted to update `enriched_events` after the ingest
  transaction.
- `live_price_gateway` reads the latest `market_ticks` fan-out per
  target. It does not own an upstream WebSocket or REST client and never
  writes `market_ticks`.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker`, `EventAnchorBackfillWorker` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `PulseCandidateWorker` | `{window, scope}` |

Wake payloads are hints; consumers re-read DB on wake and catch up on
their configured `interval_seconds` cadence. `market_tick_written`
only wakes the projection; persisted `market_ticks` remain the source
of correctness. `DBPoolBundle` owns wake emission and listener
construction through its wake pool.
Adding a new channel means adding the emitter call, listing the channel
in the listening worker's `workers.yaml` `wakes_on`, and preserving the
worker's bounded catch-up loop.

## Lifecycle and Supervision

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
- Domain workers never call `pg_notify` directly and never own raw pool
  lifecycle. They use `DBPoolBundle.worker_session()`,
  `wake_emitter()`, and `wake_listener()` through injected runtime
  dependencies.
- Runtime knobs live in `~/.gmgn-twitter-intel/workers.yaml`. The
  application/provider config in `config.yaml` must not contain worker
  interval, batch, concurrency, lease, max-attempt, timeout, advisory
  lock, or wake-channel settings.

## Adding a Worker

When introducing a new worker, do all of the following in the same
change:

1. Implement the worker as a `WorkerBase` subclass with a canonical
   `name`, typed worker settings, injected `DBPoolBundle`, telemetry,
   and any narrow provider protocols it needs. Put business work in
   `run_once()`.
2. Add the canonical key and class path to
   `app/runtime/worker_registry.py`, add a matching
   `WorkersSettings` field and default `workers.yaml` block, and
   construct the worker in `app/runtime/bootstrap.py`.
3. Add a row to this file's worker inventory.
4. Add or update the wake channels table here if the worker introduces
   a channel, and add its `wakes_on` list to `workers.yaml` when it
   listens for wake hints.
5. Document the worker in the owning domain's `ARCHITECTURE.md` Stage
   Map.
6. If the worker writes a new derived table, declare it as a read model
   and name its single writer (`Architecture Invariants` #4 in
   `ARCHITECTURE.md`).
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
