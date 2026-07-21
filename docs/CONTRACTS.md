# Public Contracts

Parallax exposes one configuration contract, one HTTP/WebSocket service, and one CLI. This document records stable behavior; generated OpenAPI is authoritative for exact HTTP fields.

There are no compatibility aliases for retired products, tables, worker names, routes, or response fields. A behavior change updates source, tests, generated contracts, and this document in the same change.

## Runtime configuration

The active operator-owned files are:

- `~/.parallax/config.yaml` for application, PostgreSQL, providers, credentials, notifications, API, and public WebSocket settings.
- `~/.parallax/workers.yaml` for worker enablement, cadence, batch/lease/timeout settings, and agent-runtime policy.

Repository examples, fixtures, `.env` files, and generated docs are not runtime configuration. `uv run parallax config` reports the effective paths and redacted settings. Unknown settings or worker keys fail validation.

`app/runtime/worker_manifest.py` owns the worker inventory and writer/queue declarations. The current keys are:

```text
collector
token_capture_tier
market_tick_stream
market_tick_poll
event_anchor_backfill
live_price_gateway
resolution_refresh
asset_profile_refresh
market_tick_current_projection
token_radar_projection
macro_sync
token_image_mirror
token_profile_current
news_fetch
news_item_process
news_story_brief
news_page_projection
macro_view_projection
notification_rule
notification_delivery
```

`workers.yaml`, `WorkersSettings`, factories, status output, and this manifest must use these exact names. Item-level News brief, News source-quality projection, CEX OI board, Macro daily brief, Narrative, Account Quality, and generic projection-ledger workers are retired.

## HTTP

The service exposes `/healthz`, `/readyz`, `/metrics`, `/ws`, static frontend assets, and `/api/*`.

- `/healthz` is process liveness.
- `/readyz` checks PostgreSQL reachability, schema compatibility, and core composition only. It does not inspect providers, queues, or business freshness.
- `/api/status` returns current runtime state under `workers` and lane aggregates under `worker_lanes`. Queue rows are not fetched on this hot status path.
- `/api/ops/diagnostics` and `/api/ops/queues/{queue_name}` are authenticated, on-demand operational reads.
- Read endpoints do not call providers, execute models, mutate facts, or rebuild projections.

API responses use a typed envelope:

```json
{"ok": true, "data": {}}
```

Errors use `ok: false` with a stable error code. Pydantic response models generate `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts`; frontend code consumes those generated types.

### Endpoint families

| Family | Routes | Source of data |
|---|---|---|
| Bootstrap/status | `/api/bootstrap`, `/api/status` | runtime composition and worker status |
| Events | `/api/recent`, `/api/events/by-ids` | persisted event/evidence facts |
| Watchlist | `/api/watchlist/handles/overview`, `/api/watchlist/handle/{handle}/overview`, `/api/watchlist/handle/{handle}/timeline` | Evidence queries; no separate Watchlist domain |
| Search/case | `/api/search`, `/api/search/inspect`, `/api/token-case`, `/api/target-posts`, `/api/target-social-timeline` | Evidence, identity facts, and current Token Radar rows |
| Radar/market | `/api/token-radar`, `/api/stocks-radar`, `/api/live-market` | stable current read models and bounded cache state |
| Macro | `/api/macro`, `/api/macro/assets/correlation`, `/api/macro/series`, `/api/macro/modules/{module_id}` | current Macro snapshots and compact series |
| News | `/api/news`, `/api/news/items/{id}`, `/api/news/facts/{id}`, `/api/news/sources/status` | current News page/story projections and fetch-source state |
| Notifications | account alerts, notification list/summary/delivery audit, and read commands under `/api` | notification facts and external-delivery ledger |
| Operations | `/api/ops/diagnostics`, `/api/ops/queues/{queue_name}` | bounded on-demand operational queries |
| Images | `/api/token-images/{image_id}` | ready mirrored assets under the operator cache root |

There is no CEX OI/detail product API. Generic exchange facts and provider adapters remain internal inputs to supported products.

### Token Radar

`/api/token-radar` serves `token_radar_current_rows` selected by stable product/window keys. It never falls back to historical runs, source-event dirty rows, or provider calls. `narrative_admission` is a deterministic property derived from the selected current row; it is not backed by a Narrative table, worker, or fallback.

### News

`/api/news` serves `news_page_rows`; item and fact detail routes require a current projected object. Raw provider items do not synthesize a missing public row.

The only model-generated current product object is the story brief. Its stable identity is `story_brief_key`; run rows remain audit evidence. Item briefs and source-quality projections are not fallback paths. Source health is derived from `news_sources` plus fetch history. A deterministic terminal fetch failure is scoped to `config_payload_hash` and becomes eligible again only when that configuration identity changes.

### Macro

Macro routes serve a current snapshot plus bounded compact series. `macro_observations` are the source facts. The snapshot owns `assets_brief_json` and one `module_views_json` object for every catalog module. `/api/macro/modules/{module_id}` returns that projected object directly; it performs no observation query, module build, provider call, or News join. There is no separate daily-brief projection. Series rows expose concept/date/value/source/unit/frequency/data-quality and whitelisted event metadata only. Missing data is represented explicitly rather than filled from a compatibility payload.

### Notifications

Notifications are durable facts. Read commands update persisted read state. External delivery uses `notification_deliveries` as an auditable side-effect ledger with compare-and-set state transitions; API responses never infer successful delivery from a provider call alone.

### Token images

`/api/token-images/{image_id}` accepts only the persisted lowercase SHA-256 URL identity. Only `ready` assets whose relative path resolves under `~/.parallax/cache/token-images` are served. Missing rows/files, malformed IDs, absolute paths, and traversal attempts return `404`. Provider URLs are never accepted as a proxy input.

## WebSocket

Clients connect to `/ws`, authenticate, then subscribe:

```json
{"type":"auth","token":"..."}
{"type":"subscribe","handles":[],"cas":[],"symbols":[],"market_targets":[],"replay":100}
```

The total filter count and replay count are bounded. Replay is a PostgreSQL read-side query with batched hydration, not one query per event or filter. Push message families are `event`, `notification`, and `live_market_update`.

`NOTIFY` only reduces latency. Disconnects and missed notifications are recovered by bounded database catch-up; provider frames are never emitted as business facts before persistence.

## CLI

`uv run parallax --help` is the exact CLI source of truth. Stable top-level families are:

- service/config: `serve`, `init`, `config`;
- database: `db migrate|health|audit|query-audit`;
- Macro: `macro import-bundle|sync|status`;
- read models: `recent`, `search`, `asset-flow`, `account-alerts`, `notification-deliveries`;
- maintenance: `ops ...` for explicit repair, rebuild, queue inspection/resolution, and diagnostics.

Mutating maintenance commands require an explicit execution flag where the parser offers a dry-run mode. They operate from persisted facts and stable target keys. A rebuild does not create an alternate generation/run identity or make a provider response the source of truth.

One-shot worker commands call the same application composition and `WorkerBase` lifecycle as the service. Their `data` object reports `worker_name`, `processed`, `failed`, `dead`, `skipped`, and `notes`; commands that enqueue repair targets first also include `preparation`. The CLI does not construct workers, resolve advisory-lock keys, or own provider/database cleanup.

Queue resolution is auditable: retry mutates the source queue and resolves terminal evidence in one transaction; quarantine/archive resolves the terminal row without pretending the source work succeeded.

## Contract change discipline

For a public contract change:

1. change the owning domain/application behavior;
2. add a behavior or contract test;
3. update Pydantic/OpenAPI/frontend types when the HTTP shape changes;
4. update this document and the relevant domain architecture map;
5. remove the old name/path instead of adding an alias or dual read/write.

Historical dated audits explain why a hard cut happened; they are not a second runtime specification.
