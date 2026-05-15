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
collector, anchor_price, live_price_gateway, resolution_refresh,
asset_profile_refresh, token_capture_tier, token_radar_projection,
pulse_candidate, enrichment, handle_summary, harness_ops,
notification_rule, notification_delivery
-->

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `collector` (`CollectorService`) | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
| `anchor_price` (`AnchorPriceWorker`) | `asset_market` | `domains/asset_market/runtime/anchor_price_worker.py` | pending intents, anchor providers | `price_observations(kind='event_anchor')` | poll | `market_observation_written` | `interval_seconds` |
| `live_price_gateway` (`LivePriceGateway`) | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | OKX DEX WS, OKX CEX quote | `price_observations(kind='decision_latest')` (only when `should_persist_live_observation` returns `True`) | provider-driven (WS + poll) | `market_observation_written` (on persisted observation only) | continuous WS + provider poll |
| `resolution_refresh` (`ResolutionRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | NIL / AMBIGUOUS lookup keys, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | poll | `resolution_updated` | `interval_seconds` |
| `asset_profile_refresh` (`AssetProfileRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | resolved DEX assets due for refresh, GMGN exact-token profile | `asset_profiles` | poll | none | `interval_seconds` |
| `token_capture_tier` (`TokenCaptureTierWorker`) | `asset_market` | `domains/asset_market/runtime/token_capture_tier_worker.py` | active Token Radar live market targets | `token_capture_tier` | poll | none | `interval_seconds` |
| `token_radar_projection` (`TokenRadarProjectionWorker`) | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | facts via `token_radar_source_query`, `price_observations`, `asset_identity_current` | `token_radar_rows`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_observation_written`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `pulse_candidate` (`PulseCandidateWorker`) | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `token_radar_rows` latest per target/window/scope, gate fields, route policy | `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_agent_runs`, `pulse_agent_run_steps` | `token_radar_updated` | none | `interval_seconds` |
| `enrichment` (`EnrichmentWorker`) | `social_enrichment` | `domains/social_enrichment/runtime/enrichment_worker.py` | watched events queue, OpenAI Agents enrichment | enrichment label rows, `model_run` audit, outbound watchlist summary enqueue hook | poll | none | `interval_seconds` |
| `handle_summary` (`HandleSummaryWorker`) | `watchlist_intel` | `domains/watchlist_intel/runtime/handle_summary_worker.py` | due `watchlist_handle_summary_jobs`, handle signal events | `watchlist_handle_summaries`, `watchlist_handle_summary_runs`, job status | poll | none | `interval_seconds` |
| `harness_ops` (`HarnessOpsWorker`) | `closed_loop_harness` | `domains/closed_loop_harness/runtime/harness_ops_worker.py` | due signal seeds, market observations | `asset_signal_snapshots`, `asset_signal_outcomes`, `pulse_playbook_snapshots`, `pulse_playbook_outcomes` | poll | none | `interval_seconds` |
| `notification_rule` (`NotificationWorker`) | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | notification rule evaluations | poll | none | `interval_seconds` |
| `notification_delivery` (`NotificationDeliveryWorker`) | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending deliveries | delivery rows | poll | none | `interval_seconds` |

`IngestService` is documented here because every other worker depends
on the facts its transaction writes (`events`, `event_entities`,
`token_evidence`, `token_intents`, `token_intent_lookup_keys`,
`token_intent_resolutions`, `registry_assets`,
`asset_identity_evidence`, `asset_identity_current`). It is a
transactional service called by `collector`, not a long-running worker
and not a `WorkerBase` subclass.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_observation_written` | `AnchorPriceWorker`, `LivePriceGateway` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `PulseCandidateWorker` | `{window, scope}` |

Wake payloads are hints; consumers re-read DB on wake. `DBPoolBundle`
owns wake emission and listener construction through its wake pool.
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
