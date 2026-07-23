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

Workers recover exclusively from PostgreSQL state through bounded `interval_seconds` catch-up. There is no database wake plane or in-memory correctness dependency.

## Truth and derived state

Material business truth includes:

- Evidence: `raw_frames`, `events`, `event_entities`.
- Identity: `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current`.
- Market: `market_ticks`, `enriched_events`.
- News: `news_provider_items`, `news_items`, story membership/entity/fact edges.
- Macro: `macro_observations`.
- Notification input/output facts: `account_token_alerts`, `notifications`; external delivery state remains in `notification_deliveries`.

Current read models include `token_radar_current_rows`,
`token_profile_current`, `market_tick_current`, `news_page_rows`,
`macro_view_snapshots`, and the compact macro series rows. They have stable
product keys, exactly one runtime writer, and zero writes when their business
payload is unchanged.

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

Provider, subprocess, filesystem, and network I/O stays outside database
transactions. External delivery follows load/claim -> close transaction -> I/O
-> compare-and-set complete/fail.

## Current product projections

### Market Current

`market_tick_current` is a transactionally maintained index over append-only
`market_ticks`: a newly inserted fact, monotonic current advance, and downstream
Radar dirty enqueue share one transaction. It has no projection worker or dirty
queue. Recovery remains CQRS-rebuildable through the explicit bounded
`ops rebuild-market-current` application operation, which scans stable target
keys in the fact tape and uses the same current-write service.

### Token Radar

```text
events + intents + resolutions + market facts
  -> token_radar_dirty_targets
  -> rank source edges + compact target features
  -> token_radar_current_rows + token_radar_publication_state
  -> Radar, search, token case, notifications
```

There is one target queue. Generic projection run/offset ledgers and the
source-event dirty queue are retired. The public row is a transparent
`factor_snapshot` built only from persisted identity, social, and market facts.

### News

```text
configured sources
  -> fetch ledger + provider items + canonical news facts
  -> deterministic item processing
  -> page dirty targets
  -> fact-only page current rows
```

`page` is the only News dirty-target kind. The page projection contains source,
story-membership, entity-resolution, fact-candidate, provider-rating, content,
and market-scope fields already present in PostgreSQL. Source health is current
state on `news_sources`; deterministic terminal failures are tied to
`config_payload_hash` and resume only after the source configuration changes.

### Macro

```text
macro_sync_windows
  -> provider bundle
  -> macro_observations + macro_sync_runs
  -> macro_projection_dirty_targets
  -> compact bounded macro series
  -> one evidence snapshot containing six typed page documents
  -> six page reads + one series read
```

`macro_observations` owns raw provider truth. Compact series rows retain only
concept/date/value/source/unit/frequency/quality plus a small whitelisted event
metadata object. `MacroViewProjectionWorker` builds all six documents in one
transaction and writes the single `snapshot_key = 'current'` row only when the
stable payload changes. The six documents share one projection version, fact
watermark, latest-completed-US-session market cutoff, and computation time.
When no dirty target is due, the worker re-reads persisted compact rows once
per UTC-date/completed-session bucket. This advances freshness and cutoff state
without a database wake plane; repeated work in the same bucket is suppressed,
and an unchanged semantic payload still writes no row.

The fixed pages are Overview, Cross-asset, Rates & Inflation, Growth & Labor,
Liquidity & Funding, and Credit. Their conclusions use explicit evidence,
freshness, rule-hit, confirmation, contradiction, and invalidation contracts.
Critical gaps fail the affected conclusion closed; optional gaps are explicit
degradation. Unsupported capabilities are named `not_assessed` and never
become zeroes, proxies, scores, or process-readiness failures.

### Dormant model-execution library

Provider-neutral structured-JSON execution, capability, hashing, schema, and
usage primitives remain importable as an isolated library. Production
bootstrap, workers, status, operations, domain projections, public contracts,
and the frontend instantiate no model consumer. The library owns no product
queue, table, prompt catalog, or business state.

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
