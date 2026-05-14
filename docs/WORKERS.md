# Workers

> **Scope.** Cross-domain runtime worker inventory: each long-running
> worker's fact writes, wake-in and wake-out channels, and catch-up
> cadence. Domain stage maps live in each domain's `ARCHITECTURE.md`;
> operational invariants live in `RELIABILITY.md`; the architecture
> invariants this inventory implements live in `ARCHITECTURE.md`.

Every worker listed here runs as an `asyncio.create_task` in
`app/runtime/app.py`'s `_start_workers`. Wake mechanics flow through
`app/runtime/wake_bus.py`. Worker correctness must not depend on
`NOTIFY` delivery — every listener has a bounded `interval_seconds`
catch-up.

## Worker Inventory

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `CollectorService` | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
| `IngestService` | `evidence` | `domains/evidence/services/ingest_service.py` | normalised frames | `events`, `event_entities`, `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current` (single transaction) | per-frame call from collector | none | n/a (transactional, not a task) |
| `AnchorPriceWorker` | `asset_market` | `domains/asset_market/runtime/anchor_price_worker.py` | pending intents, anchor providers | `price_observations(kind='event_anchor')` | poll | `market_observation_written` | `interval_seconds` |
| `LivePriceGateway` | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | OKX DEX WS, OKX CEX quote | `price_observations(kind='decision_latest')` (only when `should_persist_live_observation` returns `True`) | provider-driven (WS + poll) | `market_observation_written` (on persisted observation only) | continuous WS + provider poll |
| `ResolutionRefreshWorker` | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | NIL / AMBIGUOUS lookup keys, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | poll | `resolution_updated` | `interval_seconds` |
| `AssetProfileRefreshWorker` | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | resolved DEX assets due for refresh, GMGN exact-token profile | `asset_profiles` | poll | none | `interval_seconds` |
| `TokenRadarProjectionWorker` | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | facts via `token_radar_source_query`, `price_observations`, `asset_identity_current` | `token_radar_rows`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_observation_written`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `PulseCandidateWorker` | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `token_radar_rows` latest per target/window/scope, gate fields, route policy | `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_agent_runs`, `pulse_agent_run_steps` | `token_radar_updated` | none | `interval_seconds` |
| `EnrichmentWorker` | `social_enrichment` | `domains/social_enrichment/runtime/enrichment_worker.py` | watched events queue, OpenAI Agents enrichment | enrichment label rows, `model_run` audit | poll | none | `interval_seconds` |
| `HarnessOpsWorker` | `closed_loop_harness` | `domains/closed_loop_harness/runtime/harness_ops_worker.py` | due signal seeds, market observations | `asset_signal_snapshots`, `asset_signal_outcomes`, `pulse_playbook_snapshots`, `pulse_playbook_outcomes` | poll | none | `interval_seconds` |
| `NotificationWorker` | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | notification rule evaluations | poll | none | `interval_seconds` |
| `NotificationDeliveryWorker` | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending deliveries | delivery rows | poll | none | `interval_seconds` |

`IngestService` is documented here because every other worker depends
on the facts its transaction writes; it is not a long-running task
itself.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_observation_written` | `AnchorPriceWorker`, `LivePriceGateway` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `PulseCandidateWorker` | `{window, scope}` |

Wake payloads are hints; consumers re-read DB on wake. Adding a new
channel means adding a new method to `WakeBus` and a new branch to the
consumer's `WakeListener` invocation.

## Lifecycle and Supervision

- All workers expose `run()` and `stop()`.
- `app/runtime/app.py._start_workers` constructs `WakeBus` and
  `WakeListener` once and injects them into workers that need them.
- Workers are started as `asyncio.create_task(worker.run())`.
- The runtime supervisor task watches worker tasks, logs cancellations,
  and triggers shutdown on unexpected exits.
- On shutdown, the runtime calls `stop()` on each worker, then awaits
  the tasks.
- `WakeBus` and `WakeListener` are the only places that own
  `LISTEN/NOTIFY` mechanics. Domain workers never call `pg_notify`
  directly.
- Catch-up cadence defaults live in `platform/config/settings.py`.

## Adding a Worker

When introducing a new worker, do all of the following in the same
change:

1. Implement the worker class with `run()` / `stop()` and accept the
   domain provider protocols plus an optional `WakeBus` /
   `WakeListener` by injection.
2. Wire it in `app/runtime/app.py`: add a `<name>_worker` and
   `<name>_task` field on the runtime dataclass, construct in the
   wiring section, create the task in `_start_workers`, and cancel in
   the shutdown helper.
3. Add a row to this file's worker inventory.
4. Add or update the wake channels table here if the worker introduces
   a channel.
5. Document the worker in the owning domain's `ARCHITECTURE.md` Stage
   Map.
6. If the worker writes a new derived table, declare it as a read model
   and name its single writer (`Architecture Invariants` #4 in
   `ARCHITECTURE.md`).

## Update Triggers

Update this file in the same change as any of:

- A new worker class or removal of an existing one.
- A worker gaining or losing a wake-in or wake-out channel.
- A change to a catch-up cadence default.
- A worker moving between domains.
- A new `NOTIFY` channel name or hint payload shape.
