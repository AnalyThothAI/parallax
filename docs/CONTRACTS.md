# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a versioned spec under `docs/superpowers/specs/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config (`~/.gmgn-twitter-intel/config.yaml`)

The only application config source.

- `handles` — watched Twitter handles.
- `ws_token` — public WebSocket API token.
- `api` — FastAPI bind address and replay settings.
- `storage.postgres` — DSN, password file, pool, timeout.
- `llm.api_key` / `llm.model` — optional, for watched-account social-event extraction.
- `llm.pulse_agent_*` — optional Signal Pulse decision worker config. Current gate knobs are:
  `pulse_agent_trigger_min_rank_score`, `pulse_agent_gate_trade_candidate_min`,
  `pulse_agent_gate_token_watch_min`,
  `pulse_agent_gate_high_info_rejection_min`, and
  `pulse_agent_gate_high_conviction_min`. Older heat / quality / propagation /
  tradeability / timing Pulse threshold keys are rejected.
- Optional market-related groups (OKX, GMGN OpenAPI, Marketlane) for identity
  discovery, route sync, anchor-price lookup, the process-local live price
  gateway, and request-time US equity quote snapshots.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N,"market_targets":[{"target_type":"Asset","target_id":"..."}]}`
- Push payloads include `event`, `entities`, `alerts`, `enrichment`, harness
  updates after store commit, and `live_market_update` messages for subscribed
  market targets.

## HTTP

`/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema.
FastAPI response models are the source for generated frontend types:
`make regen-contract` updates `docs/generated/openapi.json` and
`web/src/lib/types/openapi.ts`. Frontend code consumes those generated types via
`@lib/types`; do not reintroduce handwritten `web/src/api/types.ts` or
`web/src/api/client.ts` contract surfaces.

Token Radar market contract:

- `/api/token-radar` rows expose a single `market` block from
  `factor_snapshot_json`. The block contains `event_anchor`, `decision_latest`,
  and `readiness`.
- `/api/token-radar` rows may expose a `radar` block with projection-row
  metadata for UI sorting and audit display: `lane`, `rank`, `listed_at_ms`,
  `computed_at_ms`, and `source_max_received_at_ms`. `listed_at_ms` is derived
  from retained `token_radar_rows` history for the same projection window,
  scope, target type, and target id; it is presentation metadata, not an alpha
  factor.
- `market.event_anchor` is the event-time observation for the social signal.
  It may be `null` when a provider could not establish an event-time price.
- `market.decision_latest` is the latest material market observation available
  to ranking, UI, and Signal Pulse. Provider raw frames are not public facts and
  are not serialized into Token Radar rows unless they became material
  observations.
- `market.readiness` carries `anchor_status`, `latest_status`,
  `dex_floor_status`, `missing_fields`, and `stale_fields`. Consumers must treat
  missing, stale, or below-floor market state as data health / gate context, not
  as positive alpha.
- `/api/token-radar` rows do not expose old top-level `anchor_price`,
  `live_market`, or `current_market` fields. Readers must not reconstruct those
  fields from factor families, process-local caches, or provider refresh rows.
- `/api/live-market?target_type=Asset|CexToken&target_id=...` returns the latest
  material `market.decision_latest` shape when available, or
  `{"target_type":"...","target_id":"...","status":"unsupported|missing"}`
  when live pricing is unavailable for that process/target.
- `/ws` live market messages use `type="live_market_update"` and carry a
  material `market.decision_latest` payload shape for subscribed market targets.
  Clients patch the Token Radar row's `market.decision_latest`; they do not patch
  old top-level `live_market`.
- GMGN social payload token snapshots are identity evidence only. The normalized
  token snapshot carries address / chain / symbol metadata. Embedded price /
  market-cap values are not written during ingest; `event_anchor` observations
  are written by the anchor worker using provider payloads or delayed lookup.
- Resolved DEX asset rows may expose a top-level `profile` block. Profile facts
  come from the persisted `asset_profiles` read model, not request-time provider
  calls and not `factor_snapshot_json`. `profile.status` is one of `ready`,
  `pending`, `missing`, `unsupported`, or `error`. A `ready` block contains
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
  - `data.token_result`: target, `target-social-timeline`, `target-posts`,
    matched radar row when available, profile block when the selected target is
    a resolved DEX asset, market overlay, and `agent_brief`.
  - `data.topic_result`: 24h search items, post/author summary, and
    `agent_brief`.
  - `data.ambiguous_result`: candidates plus topic evidence; callers must not
    silently pick a token.
- `agent_brief.schema_version` is `search_agent_brief_v1`. The brief has three
  product sections: project/topic summary, propagation, and bull/bear views.
  It is deterministic in the first release and must cite visible evidence ids.
- Market overlay is enriched by the asset-market layer when provider candles
  are available:
  - `price_series_type = "ohlc"` with `candle_status = "ready"`,
    `candle_source`, `candle_bar`, and `candles[]` rows shaped as
    `{time_ms, open, high, low, close, volume, volume_quote, volume_usd,
    confirmed}`.
  - `price_series_type = "anchor_line"` with `candle_status` such as
    `unsupported`, `missing_market_id`, `missing_identity`, `empty`, or
    `error` when provider OHLC cannot be fetched.
  - The UI must never synthesize candlesticks from sparse message-anchor
    prices.
- `token_result.profile` uses the same `TokenProfileBlock` contract as
  `/api/token-radar` rows. Search Inspect continues to return timeline, posts,
  market overlay, and deterministic brief when profile facts are pending,
  missing, or errored.

## CLI

`gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups. The
`--help` output is the source of truth — do not enumerate verbs in this
document. `ops refresh-asset-profiles` is the one-shot operator path for due
GMGN exact-token profile refreshes; it returns an explicit skipped result when
the GMGN profile provider is not configured.

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
  "stage_count": 3,
  "summary_zh": "社交热度有效，但 DEX floor 仍需继续确认。",
  "invalidation_conditions": ["decision_latest 失效或 liquidity 跌破 floor"],
  "residual_risks": ["单一 KOL 驱动，缺少多源确认"],
  "evidence_event_ids": ["event-1"]
}
```

Default Signal Pulse listings hide rows where
`decision.recommendation = "abstain"`. Abstain is decision semantics, not a
`pulse_status`.

Current factor snapshots use `schema_version =
"token_factor_snapshot_v3_social_attention"` only. Runtime readers reject old
v1/v2 shapes and reject legacy gate blocks. The v3 contract separates:

- `subject`: deterministic identity and target-market facts.
- `gates`: high-alert eligibility, maximum decision, blocked reasons, and risk
  reasons. Identity, market freshness, CEX native-market identity, DEX holder /
  liquidity / market-cap floors, and data availability live here or in
  `data_health`; they do not score alpha.
- `market`: explicit market context with `event_anchor`, `decision_latest`, and
  `readiness`. It remains context/gate input, not an alpha family.
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
