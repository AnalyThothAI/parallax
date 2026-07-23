# Public Contracts

Parallax exposes one configuration contract, one HTTP/WebSocket service, and one CLI. This document records stable behavior; generated OpenAPI is authoritative for exact HTTP fields.

There are no compatibility aliases for retired products, tables, worker names, routes, or response fields. A behavior change updates source, tests, generated contracts, and this document in the same change.

## Runtime configuration

The active operator-owned files are:

- `~/.parallax/config.yaml` for application, PostgreSQL, providers, credentials, notifications, API, and public WebSocket settings.
- `~/.parallax/workers.yaml` for worker enablement, cadence, and batch/lease/timeout settings.

Repository examples, fixtures, `.env` files, and generated docs are not runtime configuration. `uv run parallax config` reports the effective paths and redacted settings. Unknown settings or worker keys fail validation.

The configuration schema uses typed nested models directly
(`storage.postgres`, `api`, `llm`, `gmgn`, `providers.*`, and `upstream`).
Root-level `postgres_*`, `api_*`, provider, LLM, and upstream forwarding
aliases are not part of the configuration contract.

`llm` contains only dormant provider credentials (`api_key` and `base_url`).
The production service has no model policy, model worker, model lane selector,
prompt setting, or model status surface. Those two values are retained only for
the provider-neutral library and are not consumed by bootstrap.

`app/runtime/worker_manifest.py` owns the worker inventory and writer/queue declarations. The current keys are:

```text
collector
market_tick_stream
market_tick_poll
event_anchor_backfill
resolution_refresh
asset_profile_refresh
token_radar_projection
macro_sync
token_image_mirror
token_profile_current
news_fetch
news_item_process
news_page_projection
macro_view_projection
notification_rule
notification_delivery
```

`workers.yaml`, `WorkersSettings`, factories, status output, and this manifest
must use these exact names. Configuration cannot add another worker or derived
product lane.

## HTTP

The service exposes `/healthz`, `/readyz`, `/metrics`, `/ws`, static frontend assets, and `/api/*`.

- `/healthz` is process liveness.
- `/readyz` combines a lightweight PostgreSQL liveness check with the cached startup schema/composition result. It does not inspect providers, queues, or business freshness.
- `/api/status` captures one typed in-memory runtime snapshot for worker status,
  collector details, provider connections, startup/schema state, and the News
  provider contract. It performs no SQL.
- Read endpoints do not call providers, execute models, mutate facts, or rebuild projections.

Status contains no model configuration, model policy, capacity counters,
prompt state, or model-derived business status.

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
| Radar/market | `/api/token-radar`, `/api/stocks-radar`, `/api/live-market` | stable PostgreSQL current read models |
| Macro | `/api/macro/overview`, `/api/macro/cross-asset`, `/api/macro/rates-inflation`, `/api/macro/growth-labor`, `/api/macro/liquidity-funding`, `/api/macro/credit`, `/api/macro/series` | one current six-document Macro snapshot and compact series |
| News | `/api/news`, `/api/news/items/{id}`, `/api/news/facts/{id}`, `/api/news/sources/status` | current fact-only News page projection, persisted News evidence, and fetch-source state |
| Notifications | account alerts, notification list with embedded summary, delivery audit, and read commands under `/api` | notification facts and external-delivery ledger |
| Images | `/api/token-images/{image_id}` | ready mirrored assets under the operator cache root |

There is no CEX OI/detail product API. Generic exchange facts and provider adapters remain internal inputs to supported products.

### Token Radar

`/api/token-radar` serves `token_radar_current_rows` selected by stable
product/window keys. Each public row exposes `factor_snapshot` as the sole
target, market, attention, score, decision, and source-event payload; it does
not duplicate those sections at row level. Factor subjects use exactly
`target_type`, `target_id`, `symbol`, `target_market_type`, `chain`, `address`,
and `pricefeed_id`. The transparent factor families are `social_heat`,
`social_propagation`, and `timing_risk`. `gates`, `normalization`, and
`composite` use their producer-defined fixed fields, and decisions are exactly
`discard`, `watch`, or `high_alert`. The endpoint never falls back to
historical runs, source-event dirty rows, provider calls, identity aliases, or
alternate decision labels.

### News

`/api/news` serves `news_page_rows`; item and fact detail routes require a
current projected object. Raw provider items do not synthesize a missing public
row.

The projected row contains source-backed headline/summary/time/URL, deterministic
story membership, token-resolution lanes, fact-candidate lanes, provider
rating, content classification, source metadata, market scope, dedupe counts,
and projection metadata. It contains no generated thesis, direction,
eligibility, or prose layer. Item detail hydrates persisted source observations,
entities, token mentions, and fact candidates. Source health is derived from
`news_sources` plus fetch history. A deterministic terminal fetch failure is
scoped to `config_payload_hash` and becomes eligible again only when that
configuration identity changes.

Search inspection and Token Case likewise return resolver, identity, current
Radar, market, timeline, and source-post facts only. Removed derived prose and
admission fields are absent, not nullable.

### Macro

Macro exposes exactly six typed page reads and one typed series read:

```text
/api/macro/overview
/api/macro/cross-asset
/api/macro/rates-inflation
/api/macro/growth-labor
/api/macro/liquidity-funding
/api/macro/credit
/api/macro/series
```

No other `/api/macro` path is mounted; unmatched paths return the ordinary
application `404` response.

The six page reads select six JSON documents from the same
`snapshot_key = 'current'` row. They therefore carry identical
`projection_version`, `fact_watermark`, `market_cutoff`, and `computed_at_ms`.
The market cutoff is the latest completed US regular session; the product is a
completed snapshot, not an intraday feed.

Every page includes one strict conclusion, 1–4 week horizon, drivers,
confirmations, contradictions, upgrade/invalidation conditions, evidence
references, freshness, evidence rows, and named unavailable capabilities. Each
evidence row carries value/unit/change/window/observation/frequency/source/series,
freshness, sample range/count, criticality, claim effect, and derivation
metadata when applicable. Critical gaps produce
`conclusion.status = "insufficient_evidence"`; optional gaps produce explicit
degradation. Unsupported capabilities are `not_assessed` and have no numeric
value.

Overview reports `shock_summary.state` as `dominant`,
`no_dominant_shock`, or `insufficient_evidence`; no dominant shock is a valid
result rather than a data failure. It also contains exactly eight ordered
`risk_lanes`: `us_equities`, `long_duration_treasuries`, `credit`, `usd`,
`gold`, `oil`, `crypto`, and `market_volatility`. Every lane contains typed
direction, trend versus the fifth prior completed session, categorical
confidence, summary, drivers, contradiction, invalidation, evidence refs, and
an optional local degradation reason. `key_changes` is bounded to three,
`nearest_catalyst` is at most one normalized official event, and
`core_invalidation` is nullable. There are no holdings, trade, sizing, target,
allocation, probability, continuous-score, or LLM fields.

Cross-asset uses cutoff-aligned returns and actual common samples for
20/60-session correlations. Rates & Inflation
separates nominal tenors, curve slopes, real yields, breakevens, term premium,
funding corridor, releases, and curve shape. Growth & Labor keeps leading and
lagging layers separate. Liquidity & Funding keeps balance-sheet, Treasury
cash, reverse-repo, reserves, accounting proxy, and secured/unsecured funding
separate. Credit exposes aggregate spreads, rating tail, effective yields,
credit supply, realized damage, financial conditions/liquidity, the
Treasury-yield × spread quadrant, and separate stage/direction state.

Official catalysts are limited to the next seven days and include event date,
official time, timezone, source, URL, normalized `event_at_ms` when parsing is
trustworthy, and `today`/`upcoming` status. No consensus, forecast, surprise,
countdown from an unparsed time, or event score is inferred. The series route
reads compact persisted rows and accepts explicit concepts plus one supported
window; it returns exact points, sources, quality, event metadata, and gaps.
Macro reads do not call providers, run projection code, or join another domain.

### Notifications

Notifications are durable facts. `GET /api/notifications` is the sole
list/read-summary query and returns both `items` and `summary`. Read commands
update persisted read state. Only watched-account activity and watched-account
token-alert rules produce candidates. The unique `dedup_key` is the sole dedup
authority; its rule-defined occurrence bucket enforces cooldown. External
delivery uses `notification_deliveries` as an auditable side-effect ledger with
compare-and-set state transitions; API responses never infer successful
delivery from a provider call alone.

### Token images

`/api/token-images/{image_id}` accepts only the persisted lowercase SHA-256 URL identity. Only `ready` assets whose relative path resolves under `~/.parallax/cache/token-images` are served. Missing rows/files, malformed IDs, absolute paths, and traversal attempts return `404`. Provider URLs are never accepted as a proxy input.

## WebSocket

Clients connect to `/ws`, authenticate, then subscribe:

```json
{"type":"auth","token":"..."}
{"type":"subscribe","handles":[],"cas":[{"ca":"0x...","chain":"eip155:1"}],"symbols":[],"market_targets":[],"notifications":false,"replay":100}
```

Authentication accepts exactly `type` and a string `token`. Subscription keys and value shapes are exact: `handles` and `symbols` are string arrays; `cas` contains `{ca, chain?}` objects; `market_targets` contains `{target_type, target_id}` objects; `notifications` is boolean; and `replay` is an integer. Retired `ca`/`tokens` keys, scalar CA values, `address` aliases, extra target keys, and coercible string/number booleans are rejected as `invalid_subscription`. The total filter count and replay count are bounded. Replay is a PostgreSQL read-side query with batched hydration, not one query per event or filter. Push message families are `event`, `notification`, and `live_market_update`.

Worker progress is recovered by bounded database catch-up. Provider frames are never emitted as business facts before persistence.

## CLI

`uv run parallax --help` is the exact CLI source of truth. Stable top-level families are:

- service/config: `serve`, `init`, `config`;
- database: `db migrate|health|audit|query-audit`;
- Macro: `macro import-bundle|sync|status`;
- read models: `recent`, `search`, `asset-flow`, `account-alerts`, `notification-deliveries`;
- maintenance: `ops ...` for explicit repair, rebuild, queue inspection/resolution, and diagnostics.

Mutating maintenance commands require an explicit execution flag where the parser offers a dry-run mode. They operate from persisted facts and stable target keys. A rebuild does not create an alternate generation/run identity or make a provider response the source of truth.

`ops rebuild-market-current --execute` is the bounded, cursor-based repair for reconstructing `market_tick_current` from persisted `market_ticks`. News projection repair uses the single `ops enqueue-projection-dirty-targets` path; there is no parallel canonical-items rebuild command. Token Radar contract and distribution checks use `projection-status`, `validate-projections`, and `factor-diagnostics`; the CLI does not carry a second copy of the factor contract.

One-shot worker commands call the same application composition and `WorkerBase` lifecycle as the service. Their `data` object reports `worker_name`, `processed`, `failed`, `dead`, `skipped`, and `notes`; commands that enqueue repair targets first also include `preparation`. The CLI does not construct workers or own provider/database cleanup.

Queue resolution is auditable: retry mutates the source queue and resolves terminal evidence in one transaction; quarantine/archive resolves the terminal row without pretending the source work succeeded.

## Contract change discipline

For a public contract change:

1. change the owning domain/application behavior;
2. add a behavior or contract test;
3. update Pydantic/OpenAPI/frontend types when the HTTP shape changes;
4. update this document and the relevant domain architecture map;
5. remove the old name/path instead of adding an alias or dual read/write.

Historical dated audits explain why a hard cut happened; they are not a second runtime specification.
