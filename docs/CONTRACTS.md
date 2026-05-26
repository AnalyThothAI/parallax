# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a versioned spec under `docs/superpowers/specs/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config Files

The service has two operator-owned YAML files in
`~/.gmgn-twitter-intel/`.

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
is the only source for worker runtime knobs. It contains `defaults`, `agent_runtime`, and one block
per manifest worker key, in manifest start-priority order:

`collector`, `market_tick_stream`, `market_tick_poll`,
`market_tick_current_projection`, `event_anchor_backfill`,
`token_capture_tier`, `live_price_gateway`, `resolution_refresh`,
`asset_profile_refresh`, `token_image_mirror`, `token_profile_current`,
`token_radar_projection`, `narrative_admission`, `mention_semantics`,
`token_discussion_digest`, `news_fetch`, `news_item_process`,
`news_story_projection`, `news_item_brief`, `news_page_projection`,
`news_source_quality_projection`, `equity_event_source_reconcile`,
`equity_event_fetch`, `equity_event_process`,
`equity_event_story_projection`, `equity_event_brief`,
`equity_event_page_projection`, `cex_oi_radar_board`,
`macro_view_projection`, `pulse_candidate`, `enrichment`, `handle_summary`,
`notification_rule`, and `notification_delivery`.

The schema is `WorkersSettings`; its worker fields and the generated default
`workers.yaml` must match manifest names exactly. Unknown worker keys hard fail
startup instead of being ignored or aliased.

`workers.agent_runtime` configures the shared agent execution plane. It
contains the global default model, global concurrency/RPM limits, and
named lane policies for Pulse, Narrative, Social enrichment, Watchlist
summaries, future News fact-candidate extraction, and `news.item_brief`.
Each lane may override `model`; otherwise it inherits
`agent_runtime.defaults.model`.

Agent runtime uses one structured-output path: provider JSON object mode
plus application-side Pydantic validation before domain validation. There
is no provider-enforced schema branch or compatibility fallback. Agent
execution audit reports `provider_family`, `output_strategy=json_object`,
and `schema_enforcement=client_validate` for observability. Lane status
and backpressure counters are operational signals only; they are not
product readiness and are not business facts.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N,"market_targets":[{"target_type":"Asset","target_id":"..."}]}`
- Push payloads include `event`, `entities`, `alerts`, `enrichment`,
  `social_event_enrichment_update` messages after store commit, and
  `live_market_update` messages for subscribed market targets.
- Event payload `token_resolutions` is the same public event-token projection
  used by `/api/recent`: resolved token target identity plus event-anchored
  `price`. It is not a raw `token_intent_resolutions` row.

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
  counts, max active age, max iteration p99, and summed queue depth.
- Each worker status contains common `WorkerBase` fields:
  `enabled`, `running`, timestamps, `last_result`, `last_error`,
  `iteration_duration_p99_ms`, `queue_depth`, and `pool_wait_ms_p99`.
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
- `/api/status/narrative-health` is an authenticated ops read for Narrative
  backlog health. It returns domain-owned aggregates for current admissions
  (`current_admissions`, `suppressed_admissions`, source-event and independent
  author totals), semantic backlog (`current_source_rows`,
  `semantic_rows_for_current_sources`, `missing_semantic_rows`,
  `admissions_with_missing_semantics`, `pending_existing_rows`, `queued`,
  `retryable`, `stale`, `unavailable`, `suppressed_current_digest_count`,
  `stale_fingerprint_current_digest_count`, `oldest_due_age_ms`), recent
  Narrative model-run success/failure/timeout counts, digest status/reason
  counts, and current pending digest count. `semantic_backlog.total_pending` is
  `missing_semantic_rows + queued + retryable + stale`; source rows come from
  admitted `narrative_admissions.source_event_ids_json`, not from existing
  semantics rows alone. API/frontend consumers must use this surface instead of
  writing raw SQL.

Token image contract:

- `/api/token-images/{image_id}` is the only public token image surface.
  `image_id` is the lowercase 64-hex source URL hash stored in
  `token_image_assets`.
- The route serves only `status='ready'` rows whose storage path resolves under
  `~/.gmgn-twitter-intel/cache/token-images`. Missing rows, failed mirror rows,
  missing files, invalid IDs, absolute paths, and traversal attempts return
  `404`.
- The removed `/api/token-image?url=...` proxy is not a compatibility surface.
  Public clients must not pass provider URLs back to the server for image
  fetching.

News Intel contract:

- `/api/news` is read-only and paginated. Rows come from `news_page_rows` or
  the raw visible item fallback only when `include_unprojected=true`; handlers
  do not fetch feeds, run extraction, execute agents, or rebuild projections.
- `/api/news` accepts optional filters including `direction=bullish|bearish`,
  `decision_class`, `provider_type`, `source_role`, `trust_tier`,
  `coverage_tag`, `content_class`, `content_tag`, `status`, and `q`.
  Direction and decision filtering are based only on persisted
  `agent_brief`; source classification filters read persisted `source_json`,
  and content filters read item-level `content_class` /
  `content_tags_json` materialized into `news_page_rows`.
- News rows expose deterministic fields (`headline`, `summary`,
  `source_domain`, `token_lanes`, `fact_lanes`, lifecycle/story metadata) plus
  compact source metadata (`provider_type`, `source_role`, `trust_tier`,
  `coverage_tags`, `source_quality_status`), item content classification
  (`content_class`, `content_tags_json`, `content_classification_json`),
  compact `agent_brief`, `agent_brief_status`, and
  `agent_brief_computed_at_ms`. A ready compact brief
  includes `summary_zh`, `market_read_zh`, `direction`, `decision_class`,
  bull/bear strengths, evidence count/data-gap metadata, run id,
  prompt/schema versions, and hashes when available.
- `/api/news/sources/status` exposes source classification fields, item counts,
  control-plane fetch status, redacted latest fetch errors,
  `source_quality_status`, provider capability summaries, source hygiene
  warnings, and the latest `news_source_quality_rows` payload when available.
  Supported provider types are currently `rss`, `atom`, `json_feed`, and
  `cryptopanic`; configured unsupported provider types are reported before an
  operator expects data from them.
- `/api/news/items/{news_item_id}` returns deterministic extraction facts plus
  the full current item brief and a sanitized latest run summary. It excludes
  raw provider request/response payloads from the public item-detail contract.
- Missing or unavailable brief state is represented as
  `agent_brief.status = pending | disabled | failed | stale | insufficient`;
  it is not a 5xx by itself. Frontend clients must render this state directly
  and must not synthesize Chinese summary, bull/bear thesis, decision class, or
  next-action text from the headline.

Equity Event Intel contract:

- `/api/equity-events*` routes are read-only, event-first surfaces backed by
  current equity event read models. HTTP handlers must not fetch providers,
  import workers, run LLMs, parse filings, or rebuild projections.
- `/api/equity-events` serves `equity_event_page_rows` with stable cursor
  pagination by `(latest_event_at_ms, company_event_id)`. It accepts optional
  `window`, `universe`, `ticker`, `event_type`, `priority`, `source_role`,
  `lifecycle_status`, `brief_status`, `q`, `cursor`, and bounded `limit`
  filters.
- `/api/equity-events/{event_id}` returns the current read-model detail for a
  company event. Missing rows return `404` with `equity_event_not_found`.
  Current brief payloads come only from persisted `equity_event_agent_briefs`;
  handlers must not execute the brief agent or synthesize missing analysis.
- `/api/equity-events/stories/{story_id}` returns the persisted story group and
  its projected event rows. Missing stories return `404` with
  `equity_event_story_not_found`.
- `/api/equity-events/calendar` serves `equity_event_calendar_rows`.
  Query aliases `from` and `to` map to millisecond bounds, with optional
  `universe`, `ticker`, `status`, and `session` filters.
- `/api/equity-events/companies/{ticker}/timeline` serves
  `equity_company_timeline_rows` with stable cursor pagination by
  `(event_time_ms, row_id)`.
- `/api/equity-events/sources/status` exposes sanitized source-row status for
  configured equity sources. `/api/equity-events/summary` returns counts for
  open P0 rows, today rows, pending briefs, and the latest event timestamp.

Token Radar market contract:

- `/api/token-radar` rows expose a single `market` block from
  `factor_snapshot_json`. The block contains `event_anchor`, `decision_latest`,
  and `readiness`.
- `/api/token-radar` rows expose `discussion_digest` from the persisted
  narrative read model and may expose a read-only public `pulse_overlay`.
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
  `updating` or `stale` with explicit delta metadata. `5m` is scanner-only and
  returns `unsupported_window`, not a pending digest backlog.
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
  `market_ticks`.
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
  part of the public contract.
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
  provider image URLs from raw payloads.

US Stocks radar contract:

- `/api/stocks-radar` accepts authenticated `window`, `scope`, and `limit`
  query params with the same validation semantics as `/api/token-radar`.
- Rows are current `MarketInstrument` resolutions with
  `resolution_status = NON_CRYPTO` and `CONFIRMED_US_EQUITY`; `Asset` and
  `CexToken` rows are not part of this response.
- Rows expose social attention facts, latest evidence, source event ids, and a
  request-time `quote` snapshot from macrodata-cli's Yahoo price provider. Quote lookup is per-row: a quote
  failure returns `quote.status = "unavailable"` and does not fail the whole
  response.

Macro contract:

- `/api/macro` is authenticated and read-only. It performs no provider IO;
  it reads the latest `macro_view_snapshots` row written by
  `MacroViewProjectionWorker`. The hard-cut projection is
  `macro_regime_v4`; there is no `macro_regime_v3` compatibility read path.
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
  `section_boards`, summarized `provenance`, and `related_routes`. The retired
  module key `read`, retired module key `evidence`, and retired top-level
  `data_gaps` field are not compatibility surfaces. Frontend module pages
  consume v3 directly and must not recompute scoring, readiness, or module
  reads locally. There is no v1 or v2 compatibility read path.
  Supported module ids include `overview`; `assets` plus asset subpages
  (`assets/equities`, `assets/bonds`, `assets/commodities`, `assets/fx`,
  `assets/crypto`, `assets/crypto-derivatives`); `rates` plus rates subpages
  (`rates/fed-funds`, `rates/yield-curve`, `rates/auctions`,
  `rates/real-rates`, `rates/expectations`); `fed` plus Fed subpages
  (`fed/statements`, `fed/speeches`); `liquidity` plus liquidity subpages
  (`liquidity/transmission-chain`, `liquidity/fed-balance-sheet`,
  `liquidity/operations`, `liquidity/rrp-tga`, `liquidity/reserves`,
  `liquidity/global-dollar`, `liquidity/subsurface`); `economy` plus economy
  subpages (`economy/gdp`, `economy/employment`, `economy/inflation`,
  `economy/consumer`); `volatility` plus volatility subpages
  (`volatility/dashboard`, `volatility/vix`); and `credit` plus credit
  subpages (`credit/cds`, `credit/stress`). Unsupported ids return
  `400 {"error":"unsupported_macro_module","field":"module_id"}`.
- The `assets/crypto-derivatives` module may attach a `cex_perp_board` table
  sourced from persisted `cex_oi_radar_runs` / `cex_oi_radar_rows`. Rows are compact
  display-table rows with labeled cells for symbol, open interest, funding,
  24h volume, and score. Optional richer derivatives facts are exposed only
  when persisted read models add them through the v3 table-cell contract;
  internal audit and join fields such as raw run ids, target ids, pricefeed ids,
  and score component JSON are not part of the macro module contract.
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
  window-scoped; the default window is `24h`.
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
    issue a second `/api/token-case` request for the same result.
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
  terminology.
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
  - `data.discussion_digest`: persisted narrative digest with explicit status,
    required `currentness`, semantic coverage, evidence refs, data gaps, and
    optional compact `processing.backlog`.
  - `data.narrative_delta`: compact UI metadata derived from
    `discussion_digest.currentness`, including display status and source/author
    delta counts.
  - `data.narrative_clusters`: digest cluster summaries when available.
  - `data.pulse_overlay`: optional public Signal Pulse overlay; it is
    display-gated and never changes Radar rank or Token Case narrative.
  - `data.market_live`: request-time/process-local live market snapshot with
    `status` (`ready`, `live`, `missing`, `unsupported`, `stale`, or `error`),
    provider metadata, and nullable price, market-cap, liquidity, open-interest,
    holder, volume, and observation fields.
- Token Case responses do not expose Token Radar score audit blocks. Ranking
  facts remain owned by `/api/token-radar`; dossier pages show evidence,
  propagation, profile, discussion digest, semantic timeline labels, and live
  market readiness. Canonical token dossiers do not expose `agent_brief`.

## CLI

`gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups. The
`--help` output is the source of truth — do not enumerate verbs in this
document. `config` prints both `config_path` and `workers_config_path`
and includes the effective `workers` settings loaded from `workers.yaml`.
`ops worker-status` bootstraps the runtime without the upstream
collector and returns the canonical worker map plus queue depths where
queue tables exist. `ops refresh-asset-profiles` is the one-shot
operator path for due DEX profile source refreshes; it returns an explicit
skipped result when no profile source is configured. `ops
sync-binance-cex-profiles` refreshes the Binance CEX profile source cache for
existing routed CEX tokens. `ops rebuild-token-profiles` rebuilds canonical
`token_profile_current` rows from persisted source facts without wiring
upstream providers. `ops rebuild-narrative-intel` is the formal current
frontier rebuild/drain path for Narrative Intelligence: it runs admission,
cleans stale current-backlog rows, labels semantics, refreshes digests, and
returns `cleanup` plus `final_health` summaries without hand-written SQL or
API-path side effects. Its cleanup phase is an ops maintenance writer
exception that must run while holding the narrative worker advisory locks; it is
not a runtime compatibility layer and is not callable from HTTP routes.
`ops enqueue-runtime-worker-dirty-targets` is the bounded repair surface for
runtime dirty-target consumers. It is dry-run by default, requires an explicit
work selector plus a bounded target/time/source selector, enqueues control rows
only, and never calls providers, agents, worker `run_once()`, or public
read-model writers.

Macro one-shot CLI commands are operator surfaces, not background workers:
`macro import-bundle --file <json>` or `--stdin` imports a macrodata-cli
`macro-core` bundle into `macro_observations` and records a
`macro_import_runs` audit row; `macro project-once` reads persisted
observations, builds the `macro_regime_v4` snapshot, and writes
`macro_view_snapshots`; `macro status` reports migration readiness,
observation/concept counts, history readiness, concepts below minimum history,
the latest import run, and the latest snapshot.
Docker builds install the `AnalyThothAI/macrodata-cli` `v0.1.5` Git dependency,
whose executable is `macrodata`, so remote operators can pipe
`macrodata bundle macro-core --asof <date>` into `macro import-bundle --stdin`
without mounting a local source checkout.
For chart-ready history, operators backfill with:

```bash
macrodata bundle history macro-core --start <YYYY-MM-DD> --end <YYYY-MM-DD> \
  | uv run gmgn-twitter-intel macro import-bundle --stdin
uv run gmgn-twitter-intel macro project-once
```

These commands may report partial coverage and data gaps; they must not print
provider secrets, raw WebSocket tokens, or API keys.
Before running them against real data, operators must first run
`uv run gmgn-twitter-intel config` and confirm the active
`config_path` / `workers_config_path` are the operator-owned files under
`~/.gmgn-twitter-intel/`.

## Token Radar Factor Snapshot Discipline

`projection_version` and `factor_version` are bumped on any Token Radar factor
or ranking-contract change. Current runtime explanations come from
`factor_snapshot_json`; public Signal Pulse payloads expose `factor_snapshot`,
`decision`, `gate`, and `fact_card`, not old score/thesis JSON fields.
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
- The frontend default query is `4h/all`; `1h` is the early-confirmation lane.
  Token Radar may still expose `5m` outside Signal Pulse.

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

Decision block field semantics (research committee hard cut, set in plan
2026-05-20):

- `stage_count` is opaque audit metadata. A standard non-blocked research
  committee run has three LLM committee stages:
  `signal_analyst`, `bear_case`, and `risk_portfolio_judge`. Hard-blocked
  packets may have fewer LLM stages. Readers must never infer UI ordering or
  run completeness from this number alone.
- `narrative_archetype` is a short (≤ 20 chars) free-text tag the
  final `risk_portfolio_judge` assigns to the run; empty string when no archetype
  applies. Phase 2 may tighten to a Literal enum.
- `narrative_thesis_zh` is a 30–300 char one-paragraph thesis written by
  the final `risk_portfolio_judge`. Required for non-abstain decisions.
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
- `composite`: raw alpha score, rank score, family scores, and
  `recommended_decision`.
- `provenance`: source event ids and compute time.

Current Token Radar reads use `token_radar_current_rows`. Lightweight rank
history is stored in `token_radar_rank_history`, while full point-in-time
factor snapshots live only in partitioned `token_radar_snapshot_audit`. Compact
first-seen metadata preserves `listed_at_ms`, and diagnostics/settlement
commands evaluate bounded audit snapshots by `computed_at_ms` and score version.

Operational commands:

- `gmgn-twitter-intel ops factor-diagnostics` reports current factor score dispersion,
  bucket counts, and rank-score diagnostics.
- `gmgn-twitter-intel ops settle-token-factors` writes point-in-time forward
  return evaluations when sufficient later market observations exist.
- `gmgn-twitter-intel ops audit-token-radar` is v3-only and flags legacy
  snapshots instead of accepting compatibility fallback.
- `gmgn-twitter-intel ops reset-token-radar-postgres-hard-cut` is an explicit
  operator maintenance command for dropping legacy Token Radar storage and
  clearing rebuildable Token Radar read models. It never touches material fact
  tables, runtime config, or secrets.
- `gmgn-twitter-intel ops ensure-postgres-partitions --execute` ensures current
  and next month Token Radar rank-history and snapshot-audit partitions.
- `gmgn-twitter-intel ops drop-expired-postgres-partitions --execute` is an
  explicit no-op until partition retention is configured.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.
