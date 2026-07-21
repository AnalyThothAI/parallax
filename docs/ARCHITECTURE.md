# Architecture

Parallax is one Python service, one CLI, one React console, and one PostgreSQL database. It follows Kappa/CQRS: material facts are written once, and every operator-facing view is a rebuildable current projection.

## Data flow

```text
providers / public streams
  -> ingestion adapters
  -> PostgreSQL material facts
  -> durable dirty targets or bounded catch-up
  -> single-writer current read models
  -> HTTP / WebSocket / CLI
```

`NOTIFY` is only a latency hint. Correctness comes from PostgreSQL state and each listener's bounded `interval_seconds` catch-up.

## Truth and derived state

Material business truth includes:

- Evidence: `raw_frames`, `events`, `event_entities`.
- Identity: `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current`.
- Market: `market_ticks`, `enriched_events`.
- News: `news_provider_items`, `news_items`, story membership/entity/fact edges.
- Macro: `macro_observations`.
- Notification input/output facts: `account_token_alerts`, `notifications`; external delivery state remains in `notification_deliveries`.

Current read models include `token_radar_current_rows`, `token_profile_current`, `market_tick_current`, `news_page_rows`, `news_story_agent_briefs`, `macro_view_snapshots`, and the compact macro series rows. They have stable product keys, exactly one runtime writer, and zero writes when their business payload is unchanged.

Queues, leases, publication state, sync attempts, provider fetch attempts, and terminal-event rows are control or audit state. They are not alternate business truth.

## Package boundaries

```text
domains/*       business facts, policies, repositories, read models, workers
integrations/*  provider and external-system adapters
platform/*      configuration, PostgreSQL, telemetry, generic worker kernel
app/runtime/*   composition, factories, scheduler, provider wiring
app/operations  authenticated operator application queries/commands
app/surfaces/*  HTTP, WebSocket, and CLI transport adapters
```

Dependency rules:

- Domains do not import `parallax.app`.
- Runtime composition does not import transport surfaces.
- Surfaces may call application/runtime services but do not become business-rule owners.
- Provider objects enter domains through declared protocols or bundles.
- `platform/runtime/worker_base.py` owns the generic loop; domain workers own their queue and state machine.

These rules are enforced by `tests/architecture/test_kiss_runtime_invariants.py`.

## Transaction ownership

Application services and workers own transaction scope. Repository write methods execute SQL on the supplied connection; they do not expose `commit` switches or open implicit transactions.

Important atomic units are:

- event fact, identity resolution, market capture, enriched event, and downstream dirty target;
- Token Radar private edges/features, current rows, publication state, and queue acknowledgement;
- a read-model replacement/current upsert and its queue acknowledgement;
- notification creation and delivery-row activation;
- terminalization or retry transition plus its source queue mutation.

Provider, model, subprocess, filesystem, and network I/O stays outside database transactions. External delivery follows load/claim -> close transaction -> I/O -> compare-and-set complete/fail.

## Current product projections

### Token Radar

```text
events + intents + resolutions + market facts
  -> token_radar_dirty_targets
  -> rank source edges + compact target features
  -> token_radar_current_rows + token_radar_publication_state
  -> Radar, search, token case, notifications
```

There is one target queue. Generic projection run/offset ledgers and the source-event dirty queue are retired. `narrative_admission` is derived directly from the current Radar row; it has no separate domain, table, queue, worker, or fallback.

### News

```text
configured sources
  -> fetch ledger + provider items + canonical news facts
  -> deterministic item processing
  -> story agent current brief
  -> page current rows
```

Only `page` and `story_brief` remain as News dirty-target kinds. Item briefs and source-quality projection lanes are retired. Source health is current state on `news_sources`; deterministic terminal failures are tied to `config_payload_hash` and resume only after the source configuration changes.

### Macro

```text
macro_sync_windows
  -> provider bundle
  -> macro_observations + macro_sync_runs
  -> compact bounded macro series
  -> macro_view_snapshots (including assets_brief_json and module_views_json)
  -> /api/macro
```

`macro_observations` owns raw provider truth. Compact series rows retain only concept/date/value/source/unit/frequency/quality plus a small whitelisted event metadata object. The view writer owns the assets brief and every catalog module payload. Module HTTP requests read `module_views_json` directly; there is no request-time observation scan, News join, second daily-brief projection, or duplicate import ledger.

### Evidence watchlist and account alerts

Watchlist timeline/cluster queries are Evidence read models. The unsupported `signal` scope and fixed-zero signal metrics are removed. `account_token_alerts` remains a real ingest output consumed by notifications; the stale Account Quality scoring/profile control plane is removed.

## Deliberate safety boundary

`events.raw_json` and `events.event_json` are still present because historical events do not yet have a proven one-to-one `raw_frames` source edge and locator. They must not be deleted until new writes persist that edge, historical coverage is verified at 100%, and ambiguous payloads are exported to immutable evidence. No runtime fallback layer should be added in the meantime.

## Authoritative references

- Worker inventory and ownership: `docs/WORKERS.md`
- Worker debugging/state machines: `docs/WORKER_FLOW.md`
- Public surfaces: `docs/CONTRACTS.md`
- Reliability and retention: `docs/RELIABILITY.md`
- PostgreSQL diagnostics: `docs/references/POSTGRES_PERFORMANCE.md`
- Frontend boundaries: `docs/FRONTEND.md`
