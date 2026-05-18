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
  default model, Pulse model override, Watchlist handle-summary model
  override, timeout, and tracing/export settings.
- Optional market-related groups (OKX, GMGN OpenAPI, Binance, Marketlane) for
  identity discovery, route sync, profile source refresh, market tick capture,
  cache-only live price fan-out, and request-time US equity quote snapshots.
- `gmgn` — GMGN OpenAPI key/base URL/timeout/cache settings. The exact-token
  profile lane uses this group to write persisted GMGN source
  `asset_profiles` facts, including DEX token `logo_url`.
- `providers.okx` — OKX CEX/DEX REST and DEX WebSocket endpoints plus
  credentials where required by the enabled provider lane.
- `providers.binance` — Binance Web3 metadata and Binance CEX profile endpoint
  settings. Binance DEX metadata writes `asset_profiles`; Binance CEX profiles
  write `cex_token_profiles`.

Worker `enabled`, `interval_seconds`, `batch_size`, `concurrency`,
`lease_ms`, `max_attempts`, advisory-lock, timeout, wake-channel, Pulse
trigger/gate, and Watchlist summary queue/gate settings are rejected from
`config.yaml`.

### Worker Runtime Config (`workers.yaml`)

`workers.yaml` is the only source for worker runtime knobs. It contains
`defaults` plus one block per canonical worker key:

`collector`, `token_capture_tier`, `market_tick_stream`, `market_tick_poll`,
`live_price_gateway`, `resolution_refresh`, `asset_profile_refresh`,
`token_radar_projection`, `token_profile_current`, `pulse_candidate`, `enrichment`,
`handle_summary`, `notification_rule`, and `notification_delivery`.

The schema is `WorkersSettings`; the canonical key list is guarded
against `worker_registry.py` and `docs/WORKERS.md`.

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

- `/readyz` and `/api/status` expose worker state only under
  `data.workers` / `workers` as a map keyed by canonical worker key.
  Old top-level worker sections such as `collector`,
  `token_radar_projection`, or `pulse_candidate` are removed.
- Each worker status contains common `WorkerBase` fields:
  `enabled`, `running`, timestamps, `last_result`, `last_error`,
  `iteration_duration_p99_ms`, `queue_depth`, and `pool_wait_ms_p99`.
- `workers.collector.details` carries collector counters such as
  `frames_received`, `matched_twitter_events`, parse/duplicate counts,
  provider counters, and `snapshot_gate_outcomes`.
- `snapshot_gate` is a global health field copied from collector
  snapshot-gate counters; it is not a worker section.

Token Radar market contract:

- `/api/token-radar` rows expose a single `market` block from
  `factor_snapshot_json`. The block contains `event_anchor`, `decision_latest`,
  and `readiness`.
- `market.event_anchor` and `market.decision_latest` are public response keys
  generated from `enriched_events` and `market_ticks`. They are not internal
  market concepts, DB tables, worker names, or provider runtime semantics.
- `/api/token-radar` rows may expose a `radar` block with projection-row
  metadata for UI sorting and audit display: `lane`, `rank`, `listed_at_ms`,
  `computed_at_ms`, and `source_max_received_at_ms`. `listed_at_ms` is derived
  from retained `token_radar_rows` history for the same projection window,
  scope, target type, and target id; it is presentation metadata, not an alpha
  factor.
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
  `pending`, `missing`, `unsupported`, or `error`. A `ready` block has a usable
  `identity.logo_url` and contains
  `identity` fields (`symbol`, `name`, `logo_url`, `banner_url`,
  `description`), normalized `links` (`website_url`, `twitter_url`,
  `twitter_username`, `telegram_url`, `gmgn_url`, `geckoterminal_url`), and
  provider-attributed `source` metadata. Frontend clients must not derive
  provider URLs from raw payloads; URL normalization is server-side.

US Stocks radar contract:

- `/api/stocks-radar` accepts authenticated `window`, `scope`, and `limit`
  query params with the same validation semantics as `/api/token-radar`.
- Rows are current `MarketInstrument` resolutions with
  `resolution_status = NON_CRYPTO` and `CONFIRMED_US_EQUITY`; `Asset` and
  `CexToken` rows are not part of this response.
- Rows expose social attention facts, latest evidence, source event ids, and a
  request-time `quote` snapshot from Marketlane. Quote lookup is per-row: a quote
  failure returns `quote.status = "unavailable"` and does not fail the whole
  response.

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
    for the selected target. The Search page renders this payload directly and
    must not issue a second `/api/token-case` request for the same result.
  - `data.topic_result`: 24h search items, post/author summary, and
    `agent_brief`.
  - `data.ambiguous_result`: candidates plus topic evidence; callers must not
    silently pick a token.
- `agent_brief.schema_version` is `search_agent_brief_v1`. The brief has three
  product sections: project/topic summary, propagation, and bull/bear views.
  It is deterministic in the first release and must cite visible evidence ids.
- `token_result.profile` uses the same `TokenProfileBlock` contract as
  `/api/token-radar` rows. Search Inspect continues to return timeline, posts,
  live market status, and deterministic brief when profile facts are pending,
  missing, or errored.

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
  - `data.agent_brief`: deterministic `search_agent_brief_v1` project summary,
    propagation read, and bull/bear sections over visible evidence.
  - `data.market_live`: request-time/process-local live market snapshot with
    `status` (`ready`, `live`, `missing`, `unsupported`, `stale`, or `error`),
    provider metadata, and nullable price, market-cap, liquidity, holder, and
    observation fields.
- Token Case responses do not expose Token Radar score audit blocks. Ranking
  facts remain owned by `/api/token-radar`; dossier pages show evidence,
  propagation, profile, and live market readiness.

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
upstream providers.

## Token Radar Factor Snapshot Discipline

`projection_version` and `factor_version` are bumped on any Token Radar factor
or ranking-contract change. Current runtime explanations come from
`factor_snapshot_json`; public Signal Pulse payloads expose `factor_snapshot`,
`decision`, `gate`, and `fact_card`, not old score/thesis JSON fields.
Downstream evaluation services filter by version, otherwise A/B comparisons
silently mix populations. No black-box scores.

Signal Pulse `decision` blocks are the runtime contract for agent output:

```json
{
  "route": "meme",
  "recommendation": "watchlist",
  "confidence": 0.72,
  "abstain_reason": null,
  "stage_count": 2,
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

Decision block field semantics (v2, set in plan 2026-05-16):

- `stage_count` is now `2` for the standard `investigator → decision_maker`
  path and `1` for hard-blocked research-only short-circuits. Older runs
  prior to the v2 hard cut may still report `3` (`analyst / critic /
  judge`); readers must treat the value as opaque and never assume an
  exact stage count.
- `narrative_archetype` is a short (≤ 20 chars) free-text tag the
  DecisionMaker assigns to the run; empty string when no archetype
  applies. Phase 2 may tighten to a Literal enum.
- `narrative_thesis_zh` is a 30–300 char one-paragraph thesis written by
  the DecisionMaker. Required for non-abstain decisions.
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

Default Signal Pulse listings hide rows where
`decision.recommendation = "abstain"`. Abstain is decision semantics, not a
public display bucket.

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

Historical `token_radar_rows` are retained for forward-return settlement.
Latest reads select the newest projection row, while diagnostics and settlement
commands can evaluate older runs by `computed_at_ms` and score version.

Operational commands:

- `gmgn-twitter-intel ops factor-diagnostics` reports current factor score dispersion,
  bucket counts, and rank-score diagnostics.
- `gmgn-twitter-intel ops settle-token-factors` writes point-in-time forward
  return evaluations when sufficient later market observations exist.
- `gmgn-twitter-intel ops audit-token-radar` is v3-only and flags legacy
  snapshots instead of accepting compatibility fallback.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.
