# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a dated SDD feature under `docs/sdd/features/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config Files

The service has two operator-owned YAML files in
`~/.parallax/`.

Runtime config is not loaded from repository fixtures, generated docs, or
repo-local `.env` files. The `config` CLI command is the supported way to
confirm the active `config_path` and `workers_config_path` before any
real-data investigation.

### Application Config (`config.yaml`)

`config.yaml` owns application, provider, credential, and public-surface
settings. It must not contain worker runtime knobs.

- `handles` — watched Twitter handles.
- `ws_token` — public WebSocket API token.
- `api` — FastAPI bind address and replay settings.
- `storage.postgres` — DSN, password file, pool, timeout.
- `llm` — optional LLM provider config: credentials, provider/base URL,
  timeout, and tracing/export settings. It does not own model selection.
- Optional market-related groups (OKX, GMGN OpenAPI, Binance, macrodata-cli) for
  identity discovery, route sync, profile source refresh, market tick capture,
  cache-only live price fan-out, and request-time US equity quote snapshots.
- `gmgn` — GMGN OpenAPI key/base URL/timeout/cache settings. The exact-token
  profile lane uses this group to write persisted GMGN source
  `asset_profiles` facts, including DEX token `logo_url`.
- `providers.okx` — OKX DEX REST and DEX WebSocket endpoints plus credentials
  where required by the enabled DEX provider lane.
- `providers.binance` — Binance Web3 metadata, Binance CEX profile endpoint,
  and Binance USD-M futures settings. Binance DEX metadata writes
  `asset_profiles`; Binance CEX profiles write `cex_token_profiles`; Binance
  USD-M feeds own the CEX route, quote, candle, and OI/radar lane.

Worker `enabled`, `interval_seconds`, `batch_size`, `concurrency`,
`lease_ms`, `max_attempts`, advisory-lock, timeout, wake-channel, Pulse
trigger/gate, and Watchlist summary queue/gate settings are rejected from
`config.yaml`.

### Worker Runtime Config (`workers.yaml`)

`WorkerManifest v1` in `app/runtime/worker_manifest.py` is the only source for
the worker inventory, lane membership, start priority, class path, queue-depth
table, dirty-target consumers, and stable ownership contract. `workers.yaml`
is the only source for worker runtime knobs. It contains `defaults`,
`agent_runtime`, and one block per manifest worker key, in manifest registry
order:

`collector`, `market_tick_stream`, `market_tick_poll`,
`market_tick_current_projection`, `event_anchor_backfill`,
`token_capture_tier`, `live_price_gateway`, `resolution_refresh`,
`asset_profile_refresh`, `token_image_mirror`, `token_profile_current`,
`token_radar_projection`, `narrative_admission`, `news_fetch`, `news_item_process`,
`news_item_brief`, `news_page_projection`, `news_source_quality_projection`,
`cex_oi_radar_board`,
`macro_sync`, `macro_view_projection`, `macro_daily_brief_projection`,
`pulse_candidate`, `notification_rule`, and `notification_delivery`.

The schema is `WorkersSettings`; its worker fields and the generated default
`workers.yaml` must match manifest names exactly. Unknown worker keys hard fail
startup instead of being ignored or aliased.

`workers.agent_runtime` configures the shared agent execution plane. It
contains the global default model, global concurrency/RPM limits, and default
lane policies. Default lane keys are `pulse.decision` and `news.item_brief`.
Each lane may override `model`; otherwise it inherits
`agent_runtime.defaults.model`.

Agent runtime uses one structured-output path: provider JSON object mode
plus application-side Pydantic validation before lightweight domain
validation. There is no provider-enforced schema branch or compatibility
fallback. News item brief domain validation keeps the JSON shape and
unexpected tool-action audit boundary; evidence refs, sparse source text,
and descriptive trading-mechanics language are not publication blockers.
Agent execution audit reports `provider_family`,
`output_strategy=json_object`, and `schema_enforcement=client_validate`
for observability. Lane status and backpressure counters are operational
signals only; they are not product readiness and are not business facts.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N,"market_targets":[{"target_type":"Asset","target_id":"..."}]}`
- Replay is a bounded read-side query: `replay` is capped at 1000, the total
  subscription filter values across `handles`, `cas`, `symbols`, and
  `market_targets` is capped at 50, oversized subscriptions receive
  `{"type":"error","code":"too_many_filters","limit":50}`, and token-filter
  replay divides the total replay budget across the selected `cas`/`symbols`
  inside one PostgreSQL keyset/window query instead of running one
  `recent_events` query per filter. Replay payload hydration batches projected
  entities, alerts, token intents, and public
  event-token resolutions for the page; it must not run per-event projection
  lookups for every replay item.
- Push payloads include `event` messages with `entities`, `alerts`,
  `token_intents`, and `token_resolutions`; `notification` messages when
  notifications are subscribed; `social_event_enrichment_update` messages after
  store commit; and `live_market_update` messages for subscribed market
  targets.
- Event payload `token_resolutions` is the same public event-token projection
  used by `/api/recent`: resolved token target identity plus event-anchored
  `price`. It is not a raw `token_intent_resolutions` row. A selected current
  resolution row must carry non-empty resolution, intent, event, and status
  fields plus list-shaped reason/candidate/lookup arrays; malformed persisted
  rows are projection errors, not empty public arrays.
- The upstream token facts behind `token_intents` and `token_resolutions`
  require PostgreSQL mutation evidence before public read models can trust
  them: token evidence, token intent, and resolution upserts require
  `RETURNING *` with rowcount=1; intent-evidence links allow only explicit
  `ON CONFLICT DO NOTHING` rowcount 0/1; lookup-key replacement deletes require
  real non-negative rowcount and each replacement upsert requires rowcount=1.
  Fallback `SELECT` readback is not write success evidence.
- Event payload `alerts` and `/api/notifications/account-alerts` read
  persisted `account_token_alerts`; the write-side `INSERT ... DO NOTHING`
  state classification for those alerts requires PostgreSQL single-row
  `cursor.rowcount` evidence. Missing or invalid rowcount fails before an alert
  insert is reported as created or existing.

## HTTP

`/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema.
FastAPI response models are the source for generated frontend types:
`make regen-contract` updates `docs/generated/openapi.json` and
`web/src/lib/types/openapi.ts`. Frontend code consumes those generated types via
`@lib/types`; do not reintroduce handwritten `web/src/api/types.ts` or
`web/src/api/client.ts` contract surfaces.

Runtime health/status contract:

- `/readyz` and `/api/status` expose worker state under
  `data.workers` / `workers` as a map keyed by manifest worker name, plus
  lane aggregate state under `data.worker_lanes` / `worker_lanes`.
  Top-level worker sections such as `collector`,
  `token_radar_projection`, or `pulse_candidate` are not part of the contract.
- `worker_lanes` is keyed by manifest lane (`ingest`,
  `identity_market_fact`, `projection`, `agent`, `notification`,
  `maintenance_cache`) and reports enabled/running/failed counts, timeout
  counts, max active age, max iteration p99, summed queue depth, and
  `queue_health` aggregates for manifest-owned queues.
- Each worker status contains common `WorkerBase` fields:
  `enabled`, `running`, timestamps, `last_result`, `last_error`,
  `iteration_duration_p99_ms`, `queue_depth`, `queue_health`, and
  `pool_wait_ms_p99`. `queue_health` is read-only observability for
  manifest-declared job queues, delivery queues, status queues, and dirty
  target tables; it does not change claim/retry semantics.
  `app/runtime/job_queue.py` contributes only descriptor metadata for these
  diagnostics; it is not a generic executor for `pulse_agent_jobs` or
  `notification_deliveries` and must not own claim, finalize, retry, lease, or
  stale-running SQL for those tables.
- `workers.collector.details` carries collector counters such as
  `frames_received`, `matched_twitter_events`, parse/duplicate counts,
  provider counters, and `snapshot_gate_outcomes`.
- `snapshot_gate` is a global health field copied from collector
  snapshot-gate counters; it is not a worker section.
- `agent_execution` is an optional ops-only block copied from
  `AgentExecutionGateway.status_snapshot()`. It exposes global
  concurrency, in-flight counts, lane circuit state, capacity denials,
  circuit-open counts, and timeout counts. Clients must not use this as
  product truth; domain facts and read models remain the source for
  user-facing readiness.
- `/api/ops/diagnostics.agent_execution` is a sanitized ops view of the
  same plane. It exposes policy labels, counters, lane status, and
  aggregate status only; it must not include prompts, inputs, outputs,
  provider secrets, API keys, or tokens. `priority` is an
  operator-facing policy label, not strict scheduling behavior.
- `/readyz` and `/api/status` expose `news_provider_contract` as a News
  provider-type validation payload over configured sources, the live
  `news_sources` database constraint, and the static runtime-supported provider
  types. This status block must not inspect the live provider object, feed
  client, or private provider registry for capability discovery.
Token image contract:

- `/api/token-images/{image_id}` is the only public token image surface.
  `image_id` is the lowercase 64-hex source URL hash stored in
  `token_image_assets`.
- The route serves only `status='ready'` rows whose storage path resolves under
  `~/.parallax/cache/token-images`. Missing rows, failed mirror rows,
  missing files, invalid IDs, absolute paths, and traversal attempts return
  `404`.
- The removed `/api/token-image?url=...` proxy is not a compatibility surface.
  Public clients must not pass provider URLs back to the server for image
  fetching.

News Intel contract:

- `/api/news` is read-only and paginated. Rows come from `news_page_rows` or
  nothing else; handlers do not fetch feeds, run extraction, execute agents,
  rebuild projections, or fall back to raw `news_items`.
- `/api/news/items/{news_item_id}` is the read-only item detail companion for the
  current News page projection. It requires a current-version `news_page_rows`
  row for the item; raw `news_items`, provider observations, agent briefs, and
  agent run audit rows are detail evidence only and must not synthesize a
  public detail when the projection row is absent.
- `/api/news` accepts optional product filters for the current page surface:
  `signal=bullish|bearish|neutral`, `status`, and `q`.
  News rows default to the full projected tape regardless of whether token
  lanes are present. High-signal visibility comes from persisted market scope,
  provider-rating-gated agent admission, and agent brief state; provider rating
  is displayed as evidence and is not a notification publishability signal.
  Signal filtering reads persisted `signal_json`, and
  keyword search scans the deterministic projected `search_text` document on
  `news_page_rows`; it does not call Token Intel search, provider fetches,
  extraction, raw `news_items`, or scattered JSON fallback predicates. See
  `docs/references/NEWS_SEARCH.md` for the News search chain contract.
- News rows are story-shaped. They expose deterministic fields (`headline`,
  `summary`, `source_domain`, `token_lanes`, `fact_lanes`, lifecycle
  metadata), story fields (`representative_news_item_id`, `story_key`,
  `story`), provider token impact rows (`token_impacts`), compact source
  metadata (`provider_type`, `source_role`, `trust_tier`, `coverage_tags`,
  `source_quality_status`), item content classification (`content_class`,
  `content_tags`, `content_classification`), market-scope metadata
  (`market_scope`), market-wide agent admission fields
  (`agent_admission_status`, `agent_admission_reason`, `agent_admission`,
  `agent_representative_news_item_id`), compact `agent_brief`, and
  provider/source metadata. `market_scope` describes likely market
  transmission (`crypto`, `us_equity`, `macro_rates`, `commodities`, `fx`,
  `ai_semiconductors`, `private_company`, `broad_risk`, or `unknown`); it is
  metadata, not a rejection state. Processed market news becomes item-brief
  agent-eligible only when its provider rating has a ready score of at least 80
  and deterministic duplicate, similar-story, source, or operational gates do
  not block it. Provider rating is an LLM budget/freshness gate, not product
  truth and not a push-delivery gate. `signal` is
  an explicit envelope: `signal.display_signal` is the row-level display choice,
  `signal.agent_signal` is the current compact agent/admission signal, and
  `signal.alert_eligibility.in_app_eligible` can be true for in-app high-signal
  output only when the current market-wide agent brief is ready with
  `decision_class=driver|watch` and source/dedup gates pass.
  `signal.alert_eligibility.external_push_ready` requires the same ready,
  publishable current brief plus external channel, summary, semantic-signature,
  and cooldown checks, and
  `external_push_block_reason` explains blocked push delivery. PushDeer
  delivery must not treat provider score alone as a publishable agent brief. A
  ready compact brief may include only sanitized product fields such as
  `summary_zh`, `market_read_zh`, `event_type`, `market_domains`,
  `affected_entities`, `transmission_paths`, bull/bear strengths,
  and evidence/data-gap metadata. Agent run ids, prompt/schema/validator
  versions, hashes, raw requests, raw responses, tool traces, and usage
metadata are audit storage, not public News API fields. `news_item_agent_runs`
inserts and `news_item_agent_briefs` current upserts must have rowcount=1 with
a returned row before the projected page row can depend on that audit/current
brief state. Schema-version cleanup of current `news_item_agent_briefs` rows
through `DELETE ... RETURNING news_item_id` must validate cursor rowcount
against returned ids before stale-brief cleanup accounting is reported. OpenNews provider
rows can carry provider signal and token impact facts without requiring an
  agent brief. OpenNews ingestion is
  REST-only through
  `/open/news_search`; the client merges partial/ready article fragments by
  provider article id so delayed `aiRating.score`, direction, grade, and
  `coins[]` impact scores update the same material facts. Source policy must
  provide REST scan budgets (`rest_limit`, `max_rest_pages`,
  `rest_overlap_ms`) unless the worker fetch limit or durable cursor supplies
  the equivalent runtime boundary.
- `/api/news/sources/status` exposes source classification fields, item counts,
  control-plane fetch status, redacted latest fetch errors,
  `source_quality_status`, provider capability summaries, source hygiene
  warnings, and the latest `news_source_quality_rows` payload when available.
  Source quality may be `unknown`, `stale`, or `degraded`; it does not block
  `/api/news` rows from serving canonical item facts.
  Supported provider types are currently `rss`, `atom`, `json_feed`,
  `cryptopanic`, and `opennews`; this list comes from the static runtime
  provider-type contract, not the per-process provider object. Configured
  unsupported provider types are reported before an operator expects data from
  them. OpenNews credentials live under `news_intel.opennews` in
  operator-owned `config.yaml`; only
  `api_token` and `api_base_url` are accepted. Removed WebSocket settings and
  source policy keys hard-fail configuration instead of becoming compatibility
  behavior. Provider tokens are not exposed through this status route.
- `/api/news/items/{news_item_id}` returns deterministic extraction facts plus
  canonical signal/token-impact facts, story membership, market scope, current
  agent admission, the full current item brief when one exists, and a sanitized
  latest run summary. If only retired brief artifacts exist, the current brief
  is absent or pending; retired agent fields and old research-tool payloads are
  never exposed through the public item-detail contract. The route excludes raw
  provider request/response payloads from the public item-detail contract.
- `news_high_signal` notifications read story-level `news_page_rows` and use
  the projected market-wide `signal.alert_eligibility` envelope. In-app dedup
  and entity identity prefer `news_story:{story_key}`; fallback item identity is
  used only when no story key exists. External pushes continue to require a
  ready, publishable current brief. Aggregated high-signal notifications that
  should reactivate failed/dead external push rows use the
  `notification_deliveries` requeue contract; insert-only delivery enqueue is
  not a compatibility fallback for that path.
- Notification fact insertion and insert-only `notification_deliveries` enqueue
  classify created-vs-existing state only from PostgreSQL single-row
  `cursor.rowcount` evidence. Missing or invalid rowcount fails before the
  repository reports notification creation, aggregation, or delivery enqueue
  state.
- Existing notification aggregation through `UPDATE notifications` requires
  `rowcount=1`; missing, zero, multi-row, or otherwise invalid rowcount fails
  before `NotificationInsertOutcome.aggregated` is reported or delivery requeue
  state can advance.
- `notification_deliveries` requeue and claim paths that use `RETURNING *`
  also require PostgreSQL rowcount evidence to match returned-row presence:
  rowcount=0/no row is the only no-op/no-delivery result, rowcount=1/row is the
  only changed/claimed delivery result, and mismatch fails as malformed
  repository/driver state.
- Notification read-marker writes (`mark_read`, `mark_all_read`,
  `mark_author_read`) also require PostgreSQL `cursor.rowcount` evidence before
  success or changed-row counts are returned. Bulk read-marker counts must come
  from one `INSERT ... SELECT ... RETURNING` result whose rowcount matches the
  returned rows, not from preselected `len(rows)` compatibility accounting.
- The frontend item URL is `/news/items/:newsItemId`; `/news/:newsItemId` is
  not a compatibility route.
- Missing or unavailable brief state is represented as
  `agent_brief.status = pending | disabled | failed | stale | insufficient`;
  `failed` is reserved for schema/provider/unreadable-output failure, not for
  thin evidence or missing `evidence_refs`; sparse but parseable news should
  still return a standard brief with optional `data_gaps`, and a missing brief
  is not a 5xx by itself. Frontend clients must render this state directly and
  must not synthesize Chinese summary, bull/bear thesis, decision class, or
  next-action text from the headline.

Token Radar market contract:

- `/api/token-radar` rows expose a single `market` block from
  `factor_snapshot_json`. The block contains `event_anchor`, `decision_latest`,
  and `readiness`.
- `/api/token-radar` rows expose `discussion_digest` from the persisted
  narrative read model and may expose a read-only public `pulse_overlay`.
  Narrative hydration reads target identity from the row's formal nested
  `target.target_type` / `target.target_id` object; API routes do not synthesize
  temporary top-level target identity fields for hydration.
  Digest status is `ready`, `pending`, `insufficient`,
  `semantic_unavailable`, or `stale`; clients must render data gaps instead of
  recreating narrative text from factor snapshots. A digest may include optional
  compact `processing.backlog` metadata for ops visibility, but `status` and
  `data_gaps` remain the truth for user-facing readiness.
- `discussion_digest.currentness` is required on Token Radar rows. It composes
  the last ready narrative epoch with the current admitted source frontier and
  exposes `display_status` (`current`, `updating`, `stale`, `not_ready`,
  `out_of_frontier`, or `unsupported_window`), ready/current source
  fingerprints, ready/current/delta source counts, delta independent authors,
  last-ready time, next-refresh time, and a public reason. Source fingerprint
  mismatch no longer hides a ready digest by itself; it displays as
  `updating` or `stale` with explicit delta metadata. Realtime narrative digest
  hydration is `1h` only; `5m`, `4h`, and `24h` Radar rows return
  `unsupported_window`, not a pending digest backlog or a reused `1h` digest.
- `market.event_anchor` and `market.decision_latest` are public response keys
  generated from `enriched_events` and `market_ticks`. They are not internal
  market concepts, DB tables, worker names, or provider runtime semantics.
- `/api/token-radar` rows may expose a `radar` block with projection-row
  metadata for UI sorting and audit display: `lane`, `rank`, `listed_at_ms`,
  `computed_at_ms`, and `source_max_received_at_ms`. `listed_at_ms` is served
  from the compact `token_radar_target_first_seen` read model keyed by the same
  projection window, scope, target type, and target identity semantics as
  runtime rows; it is presentation metadata, not an alpha factor.
- `market.event_anchor` is the event-time response object for the social signal.
  It may be `null` when inline capture could not establish an event-adjacent
  tick.
- `market.decision_latest` is the latest response object available to ranking,
  UI, and Signal Pulse from persisted market ticks. Provider raw frames are not
  public facts and are not serialized into Token Radar rows unless they became
  `market_ticks`. Market tick creation/conflict state is classified from
  PostgreSQL rowcount evidence matching `RETURNING tick_id`, not from raw
  provider payloads or returned-row presence alone.
- `market.readiness` carries `anchor_status`, `latest_status`,
  `dex_floor_status`, `missing_fields`, and `stale_fields`. Consumers must treat
  missing, stale, or below-floor market state as data health / gate context, not
  as positive alpha.
- `/api/token-radar` rows do not expose old top-level market payload,
  `live_market`, or `current_market` fields. Readers must not reconstruct those
  fields from factor families, process-local caches, or provider refresh rows.
- `/api/live-market?target_type=Asset|CexToken&target_id=...` returns the latest
  cache-backed `market.decision_latest` response shape when available, or
  `{"target_type":"...","target_id":"...","status":"unsupported|missing"}`
  when live pricing is unavailable for that process/target.
- `/ws` live market messages use `type="live_market_update"` and carry a
  cache-backed `market.decision_latest` payload shape for subscribed market targets.
  Clients patch the Token Radar row's `market.decision_latest`; they do not patch
  old top-level `live_market`. This WebSocket path is presentation fan-out, not
  fact persistence.
- GMGN social payload token snapshots are identity evidence only. The normalized
  token snapshot carries address / chain / symbol metadata. Embedded price /
  market-cap values are not used as market facts by themselves; ingest inline
  capture writes Tier 3 ticks and `enriched_events` rows in the event
  transaction.
- `/api/recent`, WebSocket replay/live event payloads, and watchlist timelines
  expose current `token_resolutions` through the shared event-token projection.
  Public fields are limited to resolution identity, target identity,
  `pricefeed_id`, status/reason arrays, `symbol`, and the standard message
  `price` payload. Internal fact/audit fields such as `identity_status`,
  `confidence`, `record_status`, `is_current`, and market join columns are not
  part of the public contract. For rows selected by the projection, resolution
  identity/status text and `reason_codes_json`, `candidate_ids_json`, and
  `lookup_keys_json` array shapes are required; read paths do not parse JSON
  strings or manufacture empty arrays for malformed current facts.
- Resolved DEX asset rows may expose a top-level `profile` block. Profile facts
  come from the persisted `token_profile_current` read model, not request-time provider
  calls and not `factor_snapshot_json`. `profile.status` is one of `ready`,
  `pending`, `missing`, `unsupported`, or `error`. A `ready` block contains
  `identity` fields (`symbol`, `name`, `logo_url`, `banner_url`,
  `description`), normalized `links` (`website_url`, `twitter_url`,
  `twitter_username`, `telegram_url`, `gmgn_url`, `geckoterminal_url`), and
  provider-attributed `source` metadata. `identity.logo_url` is either `null`
  or a same-origin `/api/token-images/{image_id}` path. Provider logo URLs from
  GMGN, Binance, OKX, or CEX profile sources are retained only as server-side
  mirror inputs and provenance; frontend clients must not derive or render
  provider image URLs from raw payloads. `pending` is a public state for absent
  current rows; a present `token_profile_current` row must expose formal
  current-row fields and must not be repaired into pending or empty source JSON
  by the read path. `logo_mirror_pending` means an image
  dirty target is already pending or in flight. `logo_mirror_unsupported` is
  terminal. `logo_mirror_failed` means the current mirrored asset is in
  error/backoff and may be retried; clients must still render no provider URL.

US Stocks radar contract:

- `/api/stocks-radar` accepts authenticated `window`, `scope`, and `limit`
  query params with the same validation semantics as `/api/token-radar`.
- Rows are current `MarketInstrument` resolutions with
  `resolution_status = NON_CRYPTO` and `CONFIRMED_US_EQUITY`; `Asset` and
  `CexToken` rows are not part of this response.
- Rows expose social attention facts, latest evidence, bounded latest source
  event ids, and a schema-stable `quote` block. The endpoint performs no
  provider IO. Until a persisted US equity quote read model exists, every row reports
  `quote.status = "unavailable"` with
  `quote.error = "quote_read_model_unavailable"`.

Macro contract:

- `/api/macro` is authenticated and read-only. It performs no provider IO;
  it reads the latest `macro_view_snapshots` row written by
  `MacroViewProjectionWorker`. The hard-cut projection is
  `macro_regime_v4`; there is no `macro_regime_v3` compatibility read path.
  The response also includes `currentness`, derived only from PostgreSQL sync
  audit/fact/projection state: latest sync status, fact max observed date,
  projection lag days, and whether projection is behind facts.
- When no snapshot exists, the endpoint returns `ok: true` with
  `data.snapshot = null`, empty `panels`, `indicators`, and `triggers`, plus
  structured `data_gaps` including `macro_view_snapshot_missing`, empty
  `features`, `chain`, `scenario`, and `scorecard`, with
  `source_coverage.observed_concept_count = 0` and
  `source_coverage.required_concept_count` set to the macro-core concept count.
- When a snapshot exists, the response exposes `snapshot` summary fields,
  `panels`, `indicators`, `triggers`, `data_gaps`, `source_coverage`,
  `features`, `chain`, `scenario`, and `scorecard` directly from the read
  model. `features` contains concept-keyed semantic labels, latest value,
  freshness, history point counts, `20d` / `60d` / `252d` history windows,
  deltas, z-score, percentile, score participation, source, quality, and
  structured data gaps. `source_coverage` includes latest and history coverage,
  required/current concept counts, concepts below minimum history, and latest
  observed date. `ready` requires usable current facts and required history
  quality; one-point-per-concept snapshots are `partial`, not `ready`. Clients
  must not recompute regime or score fields locally.
- A macro page may claim `ready` only when the relevant required concepts meet
  the history threshold, `concepts_below_min_history` is empty for that page's
  concept set, and source coverage has no blocking freshness or quality gaps.
  Missing or slow FRED public CSV responses, or a missing optional FRED API key,
  are source-health diagnostics represented as structured data gaps; they are
  not a frontend fallback condition.
- Cross-asset features are canonical concepts. Yahoo-backed bundle members are
  exposed as `asset:spy`, `asset:qqq`, `asset:iwm`, `asset:tlt`, `asset:hyg`,
  `asset:lqd`, `asset:gld`, `asset:uso`, `fx:dxy`, `crypto:btc`, and
  `crypto:eth`; clients must not look up raw provider symbols.
- `/api/macro/modules/{module_id}` is authenticated and read-only. It returns a
  first-class `macro_module_view_v3` page view for the macro workbench module
  catalog. The payload includes `snapshot`, `tiles`, `primary_chart`, `tables`,
  `module_read`, `module_evidence`, `transmission`, `data_health`,
  summarized `provenance`, and `related_routes`. `provenance.currentness`
  exposes latest sync status, `facts_max_observed_at`, `projection_lag_days`,
  and `projection_behind_facts` from PostgreSQL only; it never exposes raw
  provider output or secret values. The retired
  module key `read`, retired module key `evidence`, and retired top-level
  `data_gaps` field are not compatibility surfaces. Frontend module pages
  consume v3 directly and must not recompute scoring, readiness, or module
  reads locally. There is no v1 or v2 compatibility read path.
  The `assets` module may include a persisted `daily_brief` from
  `macro_daily_briefs(brief_key='assets_today')`; an absent row is exposed as
  no daily brief, but a missing repository read method is a server-side contract
  failure rather than a fallback to `null`.
  Supported module ids include `overview`; asset subpages
  (`assets/equities`, `assets/bonds`, `assets/commodities`, `assets/fx`,
  `assets/crypto`, `assets/crypto-derivatives`); rates subpages
  (`rates/fed-funds`, `rates/yield-curve`, `rates/auctions`,
  `rates/real-rates`, `rates/expectations`); Fed subpages
  (`fed/statements`, `fed/speeches`); liquidity subpages
  (`liquidity/transmission-chain`, `liquidity/fed-balance-sheet`,
  `liquidity/operations`, `liquidity/rrp-tga`, `liquidity/reserves`,
  `liquidity/global-dollar`, `liquidity/subsurface`); economy
  subpages (`economy/gdp`, `economy/employment`, `economy/inflation`,
  `economy/consumer`); volatility subpages
  (`volatility/dashboard`, `volatility/vix`); and credit
  subpages (`credit/cds`, `credit/stress`). Unsupported ids return
  `400 {"error":"unsupported_macro_module","field":"module_id"}`.
- The `assets/crypto-derivatives` module may attach a `cex_perp_board` table
  sourced from persisted current rows in `cex_oi_radar_rows` and publication
  state in `cex_oi_radar_publication_state`. Rows are compact display-table
  rows with labeled cells for symbol, open interest, funding, 24h volume, and
  score. Optional richer derivatives facts are exposed only when persisted read
  models add them through the v3 table-cell contract; internal audit and join
  fields such as target ids, pricefeed ids, and score component JSON are not
  part of the macro module contract. Missing board rows are represented by the
  persisted board read returning `status="missing"` and empty rows; a missing
  `cex_oi_radar` repository contract is a server-side failure, not a fallback
  that omits the table.
- `/api/cex/radar-board` reads the same persisted board repository contract.
  The route requires the repository payload to include a formal `rows` list and
  each row to include mapping-shaped `score_components_json`; missing fields
  are server-side read-model contract failures, not empty board or empty score
  explanation defaults.
- `/api/macro/series` is authenticated and read-only. It accepts
  `concept_keys=<comma-separated canonical macro concepts>` and
  `window=20d|60d|120d|1y|3y` and returns grouped observation points for chart
  hydration. Query-token auth uses the shared `token` parameter. Provider-native
  series keys such as `fred:DGS10` or `yahoo:SPY` are rejected; frontend clients
  must request canonical concept keys only. Series with fewer than two usable
  points return `status = "insufficient_history"` plus a structured data gap;
  drawable multi-point series return `status = "ok"` with usable points.

Watchlist handle intel contract:

- `/api/watchlist/handles/overview` is authenticated and returns configured
  handles only. Rows expose persisted handle-level recency and counts:
  `last_source_event_at_ms`, `recent_source_event_count`,
  `recent_signal_event_count`, `total_signal_event_count`, `summary_status`,
  and `summary_is_stale`. This is the cockpit watchlist-row source; clients do
  not derive selected-handle row facts from `/api/recent` or WebSocket replay.
- `/api/watchlist/handle/{handle}/overview` is authenticated. `{handle}` follows
  the same normalization and configured-handle requirement as summary/timeline.
  The endpoint accepts `scope=signal|all` and returns selected-handle metrics,
  `resolved_token_clusters`, `candidate_mention_clusters`,
  `narrative_clusters`, and `risk_notes`. Resolved clusters are built from the
  public event-token projection; candidate clusters come from structured
  extraction candidates and event cashtags that are not resolved targets.
- `/api/watchlist/handle/{handle}/summary` is authenticated. `{handle}` must
  match `^[A-Za-z0-9_.-]{1,64}$` after trimming `@`; unconfigured handles return
  `404 {"error":"handle_not_found"}`. The response exposes `handle`, `status`
  (`ready` or `not_ready`), `generated_at_ms`, `staleness_ms`, `is_stale`,
  `pending_recompute`, total `signal_count`, `input_event_count`,
  `signal_count_at_generation`, `model`, `summary_zh`, and `topics[]`. Topic
  items use `title`, `description`, `event_count`, `top_event_ids`, `symbols`,
  and `confidence`.
- `/api/watchlist/handle/{handle}/timeline` is authenticated and accepts
  `scope=signal|all`, `limit` (default 30, maximum 100), and cursor. `signal`
  returns only events with a persisted `social_event_extraction.is_signal_event
  = true`; `all` returns the source stream for that handle with social-event
  extraction attached when it exists. Invalid limit values return FastAPI 422.
  Invalid cursors return `400 {"error":"invalid_cursor"}`.
- Timeline pages are ordered by `(received_at_ms DESC, event_id DESC)` and use a
  base64url cursor encoding those two fields. Clients must treat the cursor as
  opaque. Timeline items include the source event, optional `social_event`, and
  current `token_resolutions` in the same shape exposed by `/api/recent`.
- The Watchlist page renders `summary_zh` and `social_event.summary_zh` as the
  primary text. Raw tweet text remains available as event detail; frontend code
  must not reconstruct summaries from the original tweet body.
- The canonical frontend Watchlist route state is
  `/watchlist?handle=<handle>&timeline_scope=signal|all`. The live radar
  `scope=matched|all` URL key is ignored by Watchlist timeline state.

Search V2 contract:

- `/api/search` accepts `q`, `limit`, `scope`, `cursor`, and `window`. Search is
  window-scoped; the default window is `24h`. Public API/CLI entrypoints own
  the default `limit`, `scope`, and `window`; the token-intel search read
  service receives those query boundaries explicitly. Malformed API scope values
  return `invalid_scope`; the shared scope validator does not rewrite unknown
  values to `matched`.
- `symbol`, `ca`, `chain`, and `handle` query params are rejected. Callers express
  those searches in `q` as `$BTC`, `eth:0x...`, `0x...`, or `@handle`.
- Responses return `data.query`, `data.page`, `data.target_candidates`, and
  `data.items`. `data.page` contains `returned_count`, `has_more`, and
  `next_cursor`; exact `total_count` is not part of the live search contract.
- Search reads current token targets before lexical/trigram retrieval. It uses
  `token_intent_resolutions`, `cex_tokens`, `registry_assets`, and
  `asset_identity_current`; it does not resolve identity through legacy
  `assets / asset_aliases / asset_venues`.

### Search Intel Inspect

- `/api/search/inspect` accepts `q`, `window`, `scope`, and `limit`.
- Response shape:
  - `data.query.result_kind`: `token_result`, `topic_result`,
    `ambiguous_result`, or `empty_result`.
  - `data.resolver`: confidence, target candidates, selected target when there
    is exactly one resolved target, and deterministic resolver reasons.
  - `data.token_result`: the same token case dossier shape as `/api/token-case`
    for the selected target, including `discussion_digest` and no
    `agent_brief`. The Search page renders this payload directly and must not
    issue a second `/api/token-case` request for the same result. When the
    selected target is `CexToken`, this includes the same persisted
    `cex_detail_snapshots` read contract as `/api/token-case`.
  - `data.topic_result`: 24h search items, post/author summary, and
    `agent_brief`.
  - `data.ambiguous_result`: candidates plus topic evidence; callers must not
    silently pick a token.
- Topic and ambiguous results keep `agent_brief.schema_version =
  search_agent_brief_v1`. The brief has three
  product sections: project/topic summary, propagation, and bull/bear views.
  It is deterministic in the first release and must cite visible evidence ids.
- `token_result.profile` uses the same `TokenProfileBlock` contract as
  `/api/token-radar` rows. Search Inspect continues to return timeline, posts,
  live market status, and discussion digest state when profile facts are
  pending, missing, or errored.

### Token Case Dossier

- `/api/token-case` accepts authenticated `target_type`, `target_id`, `window`,
  `scope`, and `posts_limit`.
- `target_type` supports `Asset` and `CexToken`. Missing or unsupported target
  references return a structured bad request or `target_not_found`.
- `scope` is the Token Case UI contract: `all` for all public mentions and
  `watched` for watched-account mentions. The backend also normalizes
  `matched` to the watched scope for callers that still speak radar/search
  terminology. Unsupported scope values fail with `invalid_scope` before
  timeline/post read services run.
- Response shape:
  - `data.target`: canonical resolved target identity.
  - `data.profile`: persisted token profile block when available, otherwise a
    status block such as `pending`, `missing`, `unsupported`, or `error`.
  - `data.timeline`: target social timeline for the requested window/scope,
    with propagation stages, authors, posts, cascade metadata, and a normalized
    query block. `data.timeline.market_candles` is the market identity and
    candle-readiness payload; clients must not expect a separate legacy market
    payload field.
  - `data.posts`: the initial recent post page for the same target/window/scope.
    Additional pages use `/api/target-posts` with the returned `next_cursor`.
    Token Case and target-post read services receive `window`, `scope`, and
    page limits explicitly from API callers; malformed direct service calls do
    not fall back to `1h` or `all`.
  - `data.discussion_digest`: persisted narrative digest with explicit status,
    required `currentness`, semantic coverage, evidence refs, data gaps, and
    optional compact `processing.backlog`.
  - `data.narrative_delta`: compact UI metadata derived from
    `discussion_digest.currentness`, including display status and source/author
    delta counts.
  - `data.narrative_clusters`: digest cluster summaries when available.
  - `data.pulse_overlay`: optional public Signal Pulse overlay; it is
    display-gated and never changes Radar rank or Token Case narrative.
  - `data.market_live`: persisted latest-market-tick snapshot with `status`
    (`ready`, `missing`, `unsupported`, `stale`, or `error`), provider
    metadata, and nullable price, market-cap, liquidity, open-interest, holder,
    volume, and observation fields. Request handlers do not call market
    providers to fill this block. Missing current tick rows return
    `status = "missing"`; a missing `latest_market_tick` repository method is a
    server-side repository/session contract failure, not a successful missing
    market response.
  - `data.cex_detail`: for `CexToken`, persisted CEX detail state read from
    `cex_detail_snapshots`. Missing snapshot rows return a structured
    `status = "missing"` block; a missing repository method is a server-side
    repository/session contract failure, not a successful no-detail response.
    For non-CEX targets this field is `null`.
- Token Case responses do not expose Token Radar score audit blocks. Ranking
  facts remain owned by `/api/token-radar`; dossier pages show evidence,
  propagation, profile, discussion digest, semantic timeline labels, and live
  market readiness. Canonical token dossiers do not expose `agent_brief`.

## CLI

`parallax <verb>` plus the `db` and `ops` subcommand groups. The
`--help` output is the source of truth — do not enumerate verbs in this
document. `config` prints both `config_path` and `workers_config_path`
and includes the effective `workers` settings loaded from `workers.yaml`.
`ops worker-status` bootstraps the runtime without the upstream
collector and returns the canonical worker map plus queue depths where
queue tables exist. `ops refresh-asset-profiles` is the one-shot
operator path for due DEX profile source refreshes; it returns an explicit
skipped result when no profile source is configured. `ops
sync-binance-cex-profiles` refreshes the Binance CEX profile source cache for
existing routed CEX tokens. Its source-cache writes validate optional single-row
`RETURNING` rowcount evidence: no matching routed token is rowcount=0/no row,
and a refreshed `cex_token_profiles` row is rowcount=1 with a returned row.
`ops rebuild-token-profiles` rebuilds canonical
`token_profile_current` rows from persisted source facts without wiring
upstream providers. Narrative Intelligence no longer exposes
`ops rebuild-narrative-intel`; runtime LLM workers for mention semantics and
discussion digests were hard-cut instead of kept as disabled maintenance
surfaces.
Runtime dirty-target consumers must self-heal from their material fact sources
with bounded catch-up inside their own projection path. There is no generic
runtime-worker repair CLI because such a surface blurs the boundary between
normal runtime and operator maintenance.
Market Tick Current dirty-target enqueue and done/error accounting requires
PostgreSQL `cursor.rowcount` evidence. Missing or invalid rowcount is malformed
repository/driver state, not zero changed market-current work, and enqueue
paths must not report candidate `len(records)` as write evidence.
Pulse trigger dirty-target done/error/reschedule accounting requires PostgreSQL
`cursor.rowcount` evidence. Missing or invalid rowcount is malformed
repository/driver state, not zero changed dirty-trigger work.
Pulse agent run and run-step audit writes that use `RETURNING` require
PostgreSQL `cursor.rowcount` evidence. Required insert/upsert paths must return
exactly one row with rowcount=1; finish paths validate rowcount against returned
row presence after the run existence check. Missing, invalid, or mismatched
rowcount fails before agent audit rows are returned.
Pulse agent runtime-version, eval-case, and eval-result writes that use
`RETURNING` are required single-row audit writes and must fail on missing,
invalid, or mismatched rowcount before eval audit rows are returned.
Pulse evidence packet persistence is a required single-row `RETURNING` write.
`PulseEvidenceRepository.upsert_packet(...)` must validate PostgreSQL
`cursor.rowcount=1` with a returned packet row before updating the associated
`pulse_agent_runs` evidence packet id/hash. The associated
`UPDATE pulse_agent_runs` is a separate required single-row mutation and must
validate rowcount=1 before the run-link is trusted.
Pulse public candidate upsert and low-information hide writes that use
`RETURNING` require PostgreSQL `cursor.rowcount` evidence. Unchanged candidate
upserts and no-op hide attempts are valid only as rowcount=0 with no returned
row; changed candidate writes require rowcount=1 with a returned row. Repository
code must not restore candidate success through fallback `SELECT` or returned-row
presence alone.
Pulse admission edge-state and candidate edge-budget writes that use single-row
`RETURNING` require PostgreSQL `cursor.rowcount` evidence. The rowcount must be
valid 0/1 and match returned-row presence before edge rows, optional state rows,
or budget booleans are reported; missing, invalid, or mismatched rowcount is
malformed repository/driver state, not returned-row success.
Pulse playbook snapshot/outcome writes also require PostgreSQL `cursor.rowcount`
evidence before playbook rows are returned. Snapshot no-change writes are valid
only as rowcount=0 with no row and must not be restored through fallback
`SELECT`; changed snapshot and outcome writes require rowcount=1 with a returned
row.
Pulse stale agent-run timeout cleanup requires PostgreSQL `cursor.rowcount`
evidence. Missing or invalid rowcount fails before the repository reports zero
stale `pulse_agent_runs` updated.
Pulse job terminal/dead batch transitions over `pulse_agent_jobs` use
`UPDATE ... RETURNING` and must validate PostgreSQL `cursor.rowcount` before
terminal ledger writes. The cursor rowcount must match the returned rows;
missing, invalid, or mismatched rowcount is malformed repository/driver state,
not zero or returned-row-count terminalized jobs.
Discovery terminal lookup-claim transitions over `token_discovery_dirty_lookup_keys`
use `DELETE ... RETURNING` and must validate PostgreSQL `cursor.rowcount` before
`worker_queue_terminal_events` writes. The cursor rowcount must match returned
deleted lookup rows; missing, invalid, or mismatched rowcount fails before
terminal counts or terminal ledger rows are reported.
Queue Terminal platform ledger writes over `worker_queue_terminal_events` use
`INSERT ... ON CONFLICT ... RETURNING *` for source-row terminalization and
`UPDATE ... RETURNING *` for operator actions. Both paths must validate
PostgreSQL `cursor.rowcount` as a valid 0/1 value matching returned-row presence
before terminal rows, operator payloads, or retry transitions are reported.
Registry fact upserts in `RegistryRepository` for registry assets, CEX tokens,
price feeds, and US equity symbols require `RETURNING` rowcount=1 plus a
returned row before facts are returned; fallback readback is not execution
evidence. US equity symbol deactivation in `RegistryRepository` follows the same
`UPDATE ... RETURNING symbol` evidence rule: cursor rowcount must match returned
symbols before changed-row counts are reported; missing, invalid, or mismatched
rowcount fails before deactivation counts.
Evidence ingest writes for `raw_frames`, `events`, and `event_entities` require
PostgreSQL single-row `cursor.rowcount` evidence. Missing, boolean, negative,
multi-row, or otherwise invalid rowcount fails before raw-frame/event
created-vs-existing state or inserted-entity counts are returned.
Narrative Admission dirty-target done/error/reschedule accounting follows the
same rule: returned changed-row counts require PostgreSQL `cursor.rowcount`
evidence, and missing or invalid rowcount fails before the repository reports
queue completion or retry work.
Narrative admission serving-row upsert and stale deletion accounting require
the same PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount fails
before the repository reports zero changed admission rows.
News projection dirty-target enqueue and done/error accounting follows the same
rule: returned changed-row counts require PostgreSQL `cursor.rowcount` evidence,
and missing or invalid rowcount fails before the repository reports queue
enqueue, completion, or retry work. Enqueue paths must not report candidate
`len(records)` as write evidence.
Claim paths over `news_projection_dirty_targets` must also validate PostgreSQL
`cursor.rowcount` against returned `RETURNING news_projection_dirty_targets.*`
rows before page/source-quality projection workers treat those rows as leased
targets.
Terminal delete paths over `news_projection_dirty_targets` also validate
PostgreSQL `cursor.rowcount` before `worker_queue_terminal_events` writes. The
cursor rowcount must match returned deleted rows; missing, invalid, or
mismatched rowcount fails before terminal counts or terminal ledger rows are
reported.
NewsRepository item lifecycle, source-quality status, source disable, and page-row
changed-row accounting also require PostgreSQL `cursor.rowcount`; missing or
invalid rowcount fails before the repository reports zero changed News work.
`news_page_rows` upserts through `RETURNING (xmax = 0)` classify inserted,
updated, or unchanged rows only after rowcount is valid 0/1 and matches
returned-row presence; rowcount=0/no row is the only unchanged projection result.
Configured-source upserts that use
`INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` must validate
required rowcount=1 with a returned source row before inserted/updated source
rows are returned. Source disable paths that use
`UPDATE news_sources ... RETURNING *` must also validate that cursor rowcount
matches returned disabled source rows before counts or reconcile rows are
returned. News fetch source claims that use
`UPDATE news_sources ... RETURNING sources.*` must validate that cursor rowcount
matches returned claim rows before due sources are returned to
`NewsFetchWorker`. News fetch-run start must validate rowcount=1 for the
`news_fetch_runs` running-row insert and the matching
`news_sources.last_fetch_at_ms` update before returning a run id. News fetch-run
finalization through
`UPDATE news_fetch_runs ... RETURNING *` must validate required single-row
rowcount/row evidence before `news_sources` status is updated or a finalized
fetch-run row is returned. News provider-item upserts that use
`INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` must validate
rowcount=1 with a returned provider-item row before inserted/updated provider
observations are returned to fetch accounting. Canonical News item upserts that
use `INSERT INTO news_items ... ON CONFLICT ... RETURNING *` must validate
rowcount=1 with a returned `news_items` row before observation edges, canonical
remap cleanup, or affected-item accounting can use the canonical `news_item_id`.
`news_item_observation_edges` upserts must also validate rowcount=1 before
provider-article remap, material duplicate remap, summary refresh, or
affected-item accounting treats the provider observation as linked.
Provider-article and material duplicate edge-remap CTEs must validate cursor
rowcount against returned old item-id rows before old-item summary cleanup,
dirty-target remap, or affected-item accounting uses those ids.
Observation summary `UPDATE news_items ... RETURNING items.*` refreshes must
validate rowcount=1 with a returned current item row before affected-item
accounting uses refreshed source/provider-article aggregates; old zero-edge
cleanup paths may accept rowcount=0/no row only as explicit optional cleanup
state and must not restore state through fallback `SELECT` readback. Old-item
representative reselection
`UPDATE news_items ... RETURNING items.*` uses optional single-row rowcount
evidence as well: rowcount=0/no row is only an explicit no-representative-edge
cleanup result, and rowcount=1/row is the only valid representative fact refresh
before item-scoped derived facts are cleared or affected-item accounting
continues.
`NewsRepository.claim_unprocessed_items(...)` claim rows from `UPDATE
news_items ... RETURNING items.*` must validate cursor rowcount against returned
claim rows before `NewsItemProcessWorker` treats the rows as leased work for
deterministic writes, retry/terminal transitions, or dirty enqueue.
Asset Profile Refresh target reschedule/error accounting follows the same rule:
changed-row counts require PostgreSQL `cursor.rowcount`, and missing or invalid
rowcount fails before the repository reports zero changed refresh-target work.
CEX token profile source-cache writes use optional single-row `RETURNING`
accounting: rowcount=0 must have no returned row, rowcount=1 must have one
returned row, and missing, invalid, multi-row, or mismatched rowcount fails
before source-cache rows are reported.
Token Profile Current dirty-target done/error accounting also follows this
rule: changed-row counts require PostgreSQL `cursor.rowcount`, and missing or
invalid rowcount fails before the repository reports zero changed
profile-current work.
Token Image Source dirty-target done/error accounting follows the same rule:
changed-row counts require PostgreSQL `cursor.rowcount`, and missing or invalid
rowcount fails before the repository reports zero changed image-source work.
Token Image Asset lifecycle writes for local media mirrors also require
PostgreSQL single-row `cursor.rowcount` evidence. Pending and ready paths that
use `RETURNING` must validate rowcount against returned-row presence before
affected counts or ready rows are reported; error and unsupported updates must
reject missing, invalid, or multi-row rowcount before lifecycle results are
accepted.
Token Capture Tier dirty-target enqueue/done accounting follows the same rule:
changed-row counts require PostgreSQL `cursor.rowcount`, and missing or invalid
rowcount fails before the repository reports zero changed capture-tier dirty work.
Token Capture Tier projection demotion accounting also requires PostgreSQL
`cursor.rowcount`; missing or invalid rowcount fails before the repository
reports zero demoted hot rows.
Discovery lookup queue enqueue/done/reschedule accounting requires PostgreSQL
`cursor.rowcount` evidence. Missing or invalid rowcount fails before the
repository reports zero changed lookup work.
Enriched event backfill lifecycle attach/terminal accounting requires
PostgreSQL single-row `cursor.rowcount` evidence. Missing, boolean, negative,
multi-row, or otherwise invalid rowcount fails before the repository reports an
event-anchor lifecycle no-op, attach, or terminal transition.
Macro Intel repository write-count accounting for sync-window completion,
retry, failure, sync-state repair, projection dirty enqueue/done/error, and
observation-series current-row delete/upsert requires PostgreSQL
`cursor.rowcount` evidence. Missing or invalid rowcount fails before the
repository reports zero changed Macro work or fabricated success/length counts;
single-row sync/state paths also reject multi-row rowcount.
Macro sync-window enqueue and claim paths that use `RETURNING` also require
rowcount evidence matching returned-row presence. Enqueue is a required
single-row result; claim/no-work outcomes are valid only as rowcount=0 with no
row or rowcount=1 with the claimed `macro_sync_windows` row.
CEX read-model write-count accounting for OI board delete/upsert, detail
snapshot upsert, and derivative-series upsert requires PostgreSQL
`cursor.rowcount` evidence. Missing, boolean, negative, or non-integer rowcount
fails before the repositories report zero, one, or fabricated CEX serving-row
write counts.

Macro one-shot CLI commands are operator surfaces, not background workers.
`macro sync --bundle macro-core --start <date> --end <date>` delegates to the
same `MacroSyncService` as the `macro_sync` worker and executes one bounded
window. It never writes macro read models directly. `macro import-bundle --file
<json>` or `--stdin` imports a saved macrodata-cli `macro-core` envelope for
offline replay/seed only, records a `macro_import_runs` audit row, and emits the
same persisted-fact wake hint as runtime sync; `macro status` reports migration readiness,
observation/concept counts, history readiness, concepts below minimum history,
sync queue state, fact max observed date, projection lag, the latest snapshot,
and a `macrodata_cli` diagnostic block. That block reports the installed
`macrodata-cli` package version, whether runtime will use a console script or
Python entrypoint fallback, and whether the installed `macro-core` bundle
contains the Parallax-required series. A status can therefore distinguish
provider/key gaps from an old packaged macrodata dependency before operators
debug the page.
Docker builds install the pinned `AnalyThothAI/macrodata-cli` Git dependency.
Runtime sync uses the packaged `macrodata` executable when the console script
is healthy, or the installed Python package entrypoint when the script is
absent or stale. It does not use `uv run macrodata` and does not require a
host-local source checkout.
The child process is bounded by `workers.macro_sync.macrodata_timeout_seconds`
so worker hard-timeout cancellation is not the only stop mechanism.
Docker operators provide a FRED API key either as
`providers.macrodata.fred_api_key` in the operator-owned config file or through
the environment / deployment secret manager named by
`providers.macrodata.fred_api_key_env` (default `FINANCE_FRED_API_KEY`);
config/status payloads contain only env var names and configured booleans. For
an explicit repair sync, operators run:

```bash
uv run parallax macro sync --bundle macro-core --start <YYYY-MM-DD> --end <YYYY-MM-DD>
```

These commands may report partial coverage and data gaps; they must not print
provider secrets, raw WebSocket tokens, or API keys.
Before running them against real data, operators must first run
`uv run parallax config` and confirm the active
`config_path` / `workers_config_path` are the operator-owned files under
`~/.parallax/`.

## Token Radar Factor Snapshot Discipline

`projection_version` and `factor_version` are bumped on any Token Radar factor
or ranking-contract change. Current runtime explanations come from
`factor_snapshot_json`; public Signal Pulse payloads expose `factor_snapshot`,
`decision`, `gate`, and `fact_card`, not old score/thesis JSON fields.
When a `pulse_candidates` row is present and displayable, its public mapper
requires `decision_json` to be mapping-shaped and the public reason/event JSON
fields to be list-shaped; malformed rows fail instead of being repaired into
empty decision text, empty reason arrays, or empty event id arrays.
Downstream evaluation services filter by version, otherwise A/B comparisons
silently mix populations. No black-box scores.

Signal Pulse list/detail endpoints are Pulse-specific, not a generic Token
Radar window mirror:

- `/api/signal-lab/pulse` accepts `window=1h|4h`; missing `window` defaults to
  `4h`. Explicit `5m` and `24h` are rejected with `invalid_window`.
- `visibility=public|hidden` controls the publication lane. Missing
  `visibility` defaults to `public`, which returns only candidates that passed
  public display gates. `visibility=hidden` returns authenticated diagnostic
  rows whose `display_status` starts with `hidden_`; public status filters are
  ignored in this lane. `/api/signal-lab/pulse/{candidate_id}` uses the same
  visibility rule, so hidden detail reads require `visibility=hidden`.
- `scope=all` is the default discovery lane. `scope=matched` is watchlist
  alert/context: it can explain why a watched source matters, but matched or
  watched evidence alone does not bypass independent-source display quality.
  Malformed scope values fail with `invalid_scope` rather than being coerced to
  `matched`.
- `handle=@name` filters by the candidate/job normalized `subject_key` only.
  It does not expand candidate event-id arrays or join back to event authors on
  the public read path.
- The frontend default query is `4h/all`; `1h` is the early-confirmation lane.
  Token Radar may still expose `5m` outside Signal Pulse.
- Public Signal Pulse list/detail payloads do not expose run identity or
  run-step audit fields such as `agent_run_id`, `run_id`, or `stages`. Those
  remain in `pulse_agent_runs` / `pulse_agent_run_steps` for operator replay.
- Public Signal Pulse `health` fields are derived from persisted candidate
  summaries and bounded freshness queries. They do not expose scheduler or
  worker liveness; runtime worker status belongs to `/api/status` and ops
  diagnostics.

Signal Pulse `decision` blocks are the runtime contract for agent output:

```json
{
  "route": "meme",
  "recommendation": "watchlist",
  "confidence": 0.72,
  "abstain_reason": null,
  "stage_count": 3,
  "summary_zh": "社交热度有效，但 DEX floor 仍需继续确认。",
  "narrative_archetype": "kol-ignition",
  "narrative_thesis_zh": "独立作者扩散到第三方 KOL，价格未跟上但叙事处于点火期。",
  "bull_view": {
    "strength": "moderate",
    "thesis_zh": "watched/independent 作者比扩大，叙事尚未饱和。",
    "supporting_event_ids": ["event-1"]
  },
  "bear_view": {
    "strength": "weak",
    "thesis_zh": "DEX 流动性仍在最低阈值附近，扩散后续可能熄火。",
    "supporting_event_ids": ["event-2"]
  },
  "playbook": {
    "has_playbook": true,
    "watch_signals": ["独立作者 4h 仍上升", "DEX 流动性翻倍"],
    "exit_triggers": ["watched-author 比例回落", "DEX 流动性跌破入场水平"],
    "monitoring_horizon": "4h"
  },
  "evidence_event_urls": {"event-1": "https://x.com/foo/status/123"},
  "invalidation_conditions": ["market response stale or liquidity below floor"],
  "residual_risks": ["单一 KOL 驱动，缺少多源确认"],
  "evidence_event_ids": ["event-1"]
}
```

Decision block field semantics:

- `stage_count` is opaque audit metadata. Readers must never infer UI ordering,
  run completeness, or public display state from this number alone. Detailed
  stage order, prompts, responses, latency, and attempts are audit-ledger data,
  not public Signal Pulse contract fields.
- `narrative_archetype` is a short (≤ 20 chars) free-text tag the
  `pulse_decision` stage assigns to the run; empty string when no archetype
  applies. Phase 2 may tighten to a Literal enum.
- `narrative_thesis_zh` is a 30–300 char one-paragraph thesis written by
  the `pulse_decision` stage. Required for non-abstain decisions.
- `bull_view` / `bear_view` are symmetric two-sided opinions
  (`{strength, thesis_zh, supporting_event_ids}`). `strength` is one of
  `absent | weak | moderate | strong`; `absent` requires empty
  `thesis_zh` and empty `supporting_event_ids` so UI can degrade
  deterministically.
- `playbook` carries the monitoring instructions (not order
  instructions): `has_playbook` is `false` for abstain/ignore — in that
  case both `watch_signals` and `exit_triggers` must be empty.
  `monitoring_horizon` is one of `1h | 4h | 24h`. The playbook never
  contains price targets, sizing, stop-loss, take-profit, or any other
  trading execution language; see `RELIABILITY.md` Pulse Agent Audit
  Ledger.
- `evidence_event_urls` is an optional `{event_id: url}` map populated
  for the events listed in `evidence_event_ids` so frontends can
  hyperlink without a separate lookup.
- `high_conviction` decisions additionally require
  `len(evidence_event_ids) >= 3` and both `bull_view.strength` and
  `bear_view.strength` to be `moderate` or `strong`.

Default Signal Pulse listings hide rows where `decision.recommendation =
"abstain"` or `display_status = "hidden_source_quality"`. Abstain is decision
semantics, not a public display bucket; hidden source-quality rows are audit
state for matched/watchlist context that lacks enough independent public
confirmation.

Current factor snapshots use `schema_version =
"token_factor_snapshot_v3_social_attention"` only. Runtime readers reject old
v1/v2 shapes and reject legacy gate blocks. The v3 contract separates:

- `subject`: deterministic identity and target-market facts.
- `gates`: high-alert eligibility, maximum decision, blocked reasons, and risk
  reasons. Identity, market freshness, CEX native-market identity, DEX holder /
  liquidity / market-cap floors, and data availability live here or in
  `data_health`; they do not score alpha.
- `market`: explicit public market context with `event_anchor`,
  `decision_latest`, and `readiness` response keys generated from
  `enriched_events` and `market_ticks`. It remains context/gate input, not an
  alpha family.
- `data_health`: explicit readiness for identity, market, social, and alpha.
- `families`: social attention families only: `social_heat`,
  `social_propagation`, `semantic_catalyst`, and `timing_risk`.
  `timing_risk.weight = 0.0`, so timing contributes risk/gate context without
  positive alpha.
- `normalization`: cohort metadata, per-family cross-section ranks, alpha rank,
  and status.
- `composite`: final rank score, recommended decision, and optional display
  aliases such as `family_scores`; formal family diagnostics come from
  `families.*.score`.
- `provenance`: source event ids and compute time.

`composite.rank_score`, `composite.recommended_decision`, and
`gates.max_decision` are required formal fields. Runtime contracts reject
snapshots missing those fields; Token Radar target-feature cache writes do not
repair missing score or decision output through `0.0` or `discard`.

Token Radar online serving is `token_radar_current_rows` plus
`token_radar_publication_state`. `fresh` is allowed only when publication state
is `ready` and the product/window current rows are available; an explicitly
empty ready publication is fresh with zero rows. Failed latest attempts serve
the previous product/window rows as `stale` or no rows as `failed`.
`current_generation_id` remains attempt audit metadata, not an online serving
join key. Compact first-seen metadata preserves `listed_at_ms`; rank source
edges are lazy evidence/detail, not a current-row fallback. Current-row
`resolution_json` preserves the selected resolution row's non-empty status and
list-shaped reason/candidate/lookup arrays. Unresolved attention identity is
derived from formal `lookup_keys_json`, not from display-symbol reconstruction,
and malformed resolution fields are projection errors rather than empty public
arrays. Projection-private target-feature rows must carry formal
`target_type_key` plus `identity_id` before current-row construction; missing
private-cache identity is a projection error, not an empty serving key. They
must also carry non-empty row-id dimensions (`projection_version`, `window`,
`scope`, `lane`), integer `latest_event_received_at_ms`, and mapping-shaped
`factor_snapshot_json`; missing target-feature control fields are projection
errors, not empty row-id segments, `attention` defaults, zero source frontiers,
or empty factor payloads. Current-row `created_at_ms` uses formal
`last_scored_at_ms`; target-feature `updated_at_ms` and the runtime wall clock
are not compatibility inputs for this public timestamp. Rank-set selection also
requires formal `latest_event_received_at_ms` and a known `lane` before
filtering and resolved/attention picking; malformed rank inputs fail instead of
disappearing as expired or lane-less work. Compact rank inputs also require
`raw_composite_score` and `gates_max_decision`, and ranked rows require
`rank_score` and `recommended_decision`; missing score/gate/decision fields do
not become `0.0` or `discard`. Token Radar projection does not keep retired
snapshot-row rank helpers as compatibility code: rank publication uses compact
rank inputs, not `_rank_key`, `raw_alpha_score` fallback, or invalid-snapshot
demotion. Ranked current-row patching requires formal `normalization_status`,
`cohort_status`, `cohort_size`, `cohort_in_cohort`, `cohort_metadata`, complete
per-family `factor_ranks`, `alpha_rank`, `rank`, `rank_score`,
`recommended_decision`, and `latest_event_received_at_ms`; missing or malformed
ranked metadata fails before current-row / `factor_snapshot_json` mutation
instead of being repaired to `no_signal`, `not_ranked`, false cohort membership,
empty or incomplete rank maps, alpha rank `None`, rank `0`, or source watermark
`0`. Family rank values must be `None` or bounded `0..1` ranks. Target-feature cache writes require
formal `lane`, `source_max_received_at_ms`, `source_event_ids_json`,
`created_at_ms`, and `factor_snapshot_json` before repository payload hashing or
SQL; malformed projection output fails instead of being repaired through
`attention`, `computed_at_ms`, `[]`, or `{}` defaults. The writer also requires
the factor snapshot core fields `composite.rank_score`,
`composite.recommended_decision`, and `gates.max_decision`; malformed scoring
output fails before SQL rather than becoming `0.0` or `discard`.
Token Radar current-row delete/upsert, target-feature write/delete, and
target-feature retention accounting require PostgreSQL `cursor.rowcount`
evidence. Missing, boolean, negative, or non-integer rowcount is malformed
repository/driver state, not a default zero- or one-row write count.
`token_radar_target_first_seen` upsert accounting follows the same rule:
returned first-seen write counts must come from PostgreSQL `cursor.rowcount`,
not projection candidate `len(records)`.
Token Radar target/source dirty queue enqueue, completion, retry, and repair or
catch-up accounting also require PostgreSQL `cursor.rowcount` evidence. Missing,
boolean, negative, or non-integer rowcount fails as malformed repository/driver
state before changed-row counts are returned. Generic target/source dirty enqueue
paths must report PostgreSQL changed-row counts, not candidate `len(records)`
values.
Projection-run stale-running cleanup accounting also requires PostgreSQL
`cursor.rowcount`; missing or invalid rowcount fails before abandoned-run counts
are returned.
Ordinary projection offset, run-ledger, dirty-range enqueue, and finish writes
require exactly one PostgreSQL `cursor.rowcount`; starting a projection run must
come from `INSERT ... RETURNING *` evidence and cannot be proven by fallback
`run_by_id` readback.
Projection dirty-range claims from `UPDATE ... RETURNING` require cursor
rowcount to match returned claimed rows before the projection worker treats the
dirty ranges as leased; rowcount=0 with no rows is the only no-work claim
result.
`token_score_evaluations` uses this same formal v3 factor snapshot contract:
missing `composite.rank_score` fails before score bucket, IC, or coverage
calculation and is not counted as a `0-19` sample. Token Factor Evaluation is a
settlement consumer, so it additionally requires `factor_snapshot_json.subject`
to carry non-empty `target_type` and `target_id` for the sample being settled;
it does not restore those fields from current-row top-level identity. This
consumer rule is separate from the global snapshot shape, where unresolved
attention snapshots may remain valid without a resolved asset id. CEX settlement
targets require subject-owned `provider` and `native_market_id`; the evaluator
does not repair missing CEX subject market identity from `market.decision_latest`
or an `instrument` alias. Settlement subject `target_type` must be formal
`Asset` or `CexToken`; direct market-tick target types `chain_token` and
`cex_symbol` are not settlement subjects and fail before market lookup or bucket
upsert. Asset settlement market identity must come from subject-owned `chain`
and `address`; `chain_id` and `asset_address` aliases are not settlement
identity fallbacks. Settlement time comes from
`factor_snapshot_json.provenance.computed_at_ms`; current-row
top-level `computed_at_ms` and epoch-zero defaults are not compatibility inputs.
Family rank IC and family coverage read the formal `families.*.score` blocks;
`composite.family_scores` is not a diagnostic compatibility source.
High-confidence `EXACT` / `UNIQUE_BY_CONTEXT` resolution rows require
formal `Asset` or `CexToken` target identity before resolved-lane publication;
malformed target identity is not a valid attention fallback.
Resolved `Asset` target payloads require formal `asset_identity_current`
explanation fields: non-empty `asset_identity_confidence`, list-shaped
`asset_identity_reason_codes`, and non-negative integer
`asset_identity_conflict_count`. Missing identity-current evidence is a
projection error, not an empty reason list or zero-conflict default.
Rank-source repair targets, latest-market-context input/output rows,
affected-target output rows, and projection source request target lists require
formal `target_type_key` plus `identity_id`. Legacy `target_type` /
`target_id` aliases are not public or operator-facing repair input at this
boundary, and malformed target payloads fail before rank-source SQL/result
mapping, source request generation, or target-feature delete/upsert instead of
becoming empty work.
Rank-source edge population and prune changed-row counts are also formal
projection evidence: population paths require explicit SQL aggregate count rows,
and prune paths require PostgreSQL `cursor.rowcount`. Missing, boolean,
negative, or non-integer count evidence fails before changed-row counts are
returned instead of becoming zero edge changes.

Operational commands:

- `parallax ops factor-diagnostics` reports current factor score dispersion,
  bucket counts, and rank-score diagnostics.
- `parallax ops settle-token-factors` writes point-in-time forward
  return evaluations when sufficient later market observations exist.
- `parallax ops audit-token-radar` is v3-only and flags legacy
  snapshots instead of accepting compatibility fallback.
- Token Radar has no runtime hard-reset command. Schema retirement belongs to
  migrations; online repair uses `ops enqueue-token-radar-dirty-targets` or the
  projection worker's bounded catch-up from material facts.
- `parallax ops enqueue-token-capture-tier-rank-set` accepts an explicit
  `--window` from the CLI parser choices; helper code resolves that window
  directly and rejects malformed direct-call windows instead of running a `24h`
  repair scan.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.

## Query Boundary Ownership

API routes and CLI parsers own public defaults and validation for `window`,
`scope`, `limit`, and ops repair ranges. Lower layers receive those values
explicitly and fail malformed direct-call input instead of restoring compatible
defaults. This applies to read-model services, runtime diagnostics payloads,
projection helpers, and operator repair helpers.

`/api/ops/diagnostics` keeps the user-facing defaults on the route:
`since_hours=4`, `window=1h`, and `scope=all`. The route validates `window` and
`scope` before calling `ops_diagnostics_payload(...)`; the runtime helper does
not define its own `1h` or `all` fallback.

Signal Pulse public freshness health currently uses a 4h health horizon from
the public read model service. That horizon is passed explicitly into the
repository/service health contract; lower layers do not restore `since_hours=4`
for direct callers.

Macro asset correlation defaults to `window=60d` at the API route. The
correlation builder receives that validated window explicitly and does not
restore a 60d service default for direct callers.
