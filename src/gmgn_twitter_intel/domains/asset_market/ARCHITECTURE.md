# Asset Market Architecture

> **Scope.** Owns asset identity evidence, the `MarketTick` fact
> model, capture-tier / stream / poll market workers, cache-only live
> market fan-out, profile refresh/current projection, and discovery workers. Global package boundaries live in
> `../../../../docs/ARCHITECTURE.md`; Token Radar projection lives in
> `../token_intel/ARCHITECTURE.md`; public payload shapes live in
> `../../../../docs/CONTRACTS.md`.

Asset Market is the only domain that may call market and identity
providers in the service runtime. It writes the facts that Token Radar
projection and Signal Pulse consume; it does not own ranking, decisions,
or read-model projection.

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Asset identity evidence | `identity_evidence_policy.py`, `repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
| Event market capture | `services/event_market_capture.py`, ingest runtime | `market_ticks(source_tier='tier3_inline')`, `enriched_events`; `event_anchor_backfill_jobs` control rows for missing anchors | Ingest captures an event-adjacent market sample from existing ticks only, then commits event facts and tick facts together. Missing anchors are queued in the control plane, not by scanning fact rows. |
| Event anchor backfill | `runtime/event_anchor_backfill_worker.py`, `repositories/event_anchor_backfill_job_repository.py` | `market_ticks`, narrow `enriched_events` lifecycle updates, `event_anchor_backfill_jobs` control state | Consumes due jobs, first attaches a persisted tick near event time, calls providers only inside the anchor lag budget, and terminalizes expired or unavailable anchors. |
| Market capture tier projection | `runtime/token_capture_tier_worker.py`, `repositories/token_capture_tier_repository.py` | `token_capture_tier` | Active Token Radar targets are ranked into stream, poll, or inline-only capture tiers. This table is a rebuildable control plane, not a market fact. |
| Tier 1 market stream | `runtime/market_tick_stream_worker.py` | `market_ticks(source_tier='tier1_ws')` | Stream targets come from `token_capture_tier(tier=1)`. Provider IO never holds a DB session. |
| Tier 2 market poll | `runtime/market_tick_poll_worker.py` | `market_ticks(source_tier='tier2_poll')` | Poll targets come from `token_capture_tier(tier=2)`. DEX and CEX provider calls run outside DB sessions. |
| Live market fan-out | `runtime/live_price_gateway.py` | in-process cache only | Raw provider frames update process-local latest state and WebSocket subscribers. The gateway does not write market facts. |
| DEX profile source refresh | `runtime/asset_profile_refresh_worker.py`, `services/asset_profile_refresh.py`, `repositories/asset_profile_repository.py` | `asset_profiles` | Resolved DEX assets are enriched through explicit profile sources such as GMGN OpenAPI and Binance Web3. `asset_profiles` is a provider source cache, not the public profile read model. |
| Token image mirror | `runtime/token_image_mirror_worker.py`, `services/token_image_mirror.py`, `repositories/token_image_asset_repository.py`, `queries/token_image_source_query.py` | `token_image_assets`, local files under `cache/token-images` | Provider logo URLs from profile source caches and exact evidence are mirrored into local media. Only ready local rows may become public logo URLs; provider URLs are never served directly. |
| Token profile current projection | `runtime/token_profile_current_worker.py`, `services/token_profile_current_projection.py`, `repositories/token_profile_current_repository.py`, `queries/token_profile_source_query.py` | `token_profile_current` | Public profile/icon facts are projected from persisted GMGN OpenAPI rows, Binance Web3 rows, GMGN stream exact snapshot evidence, OKX DEX exact-address evidence, `cex_token_profiles`, and ready `token_image_assets`. CEX profile absence is explicit `unsupported`; no symbol-only DEX icon matching; no remote logo URL fallback. |
| Resolution refresh and discovery | `runtime/resolution_refresh_worker.py`, `repositories/discovery_repository.py` | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | Recent NIL / AMBIGUOUS lookup keys are refreshed through OKX DEX, then affected intents are reprocessed. Successful refresh emits `resolution_updated` so downstream readers wake; the worker itself does not run inline Token Radar projection. |
| CEX route and profile sync | `services/asset_market_sync.py`, `services/cex_token_profile_sync.py` | `cex_tokens`, `price_feeds`, `cex_token_profiles` | Maintains token/feed routing without refreshing prices. Binance CEX profiles enrich existing routed CEX tokens through a separate source cache; they do not create CEX routes or call providers from public reads. |
| US equity symbol sync | `services/us_equity_symbol_sync.py` | `registry_assets` (MarketInstrument rows) | Confirms US equity symbols so the deterministic resolver can elevate them above DEX same-symbol assets. |

## MarketTick Schema

`domains/asset_market/types/market_tick.py` defines the cross-domain
market fact contract. All providers normalise into this frozen value
type before any persistence call.

- `market_ticks` are append-only provider tick facts. Rows are not updated
  into a current-market table, and provider frames that never become ticks are
  not business facts.
- `target_type` is `chain_token` or `cex_symbol`.
- `target_id` is the deterministic market target key, such as
  `solana:<address>` or `binance:<symbol>USDT`.
- `source_tier` records whether the sample came from Tier 1 stream,
  Tier 2 poll, or inline event capture.
- `source_provider` records the concrete provider path, such as
  `okx_dex_ws`, `okx_dex_rest`, or `binance_cex_rest`.
- Numeric market fields are optional except `price_usd`, which must be a
  positive finite decimal. CEX derivatives scalars such as
  `open_interest_usd` belong on the tick only when normalized as scalar market
  facts for the same instrument/observation.
- CEX liquidation levels / heatmap zones are not tick facts. CoinGlass-derived
  level snapshots should enter through an Asset Market provider + append-only
  derivatives snapshot table with one runtime writer, then be copied into Token
  Case and Pulse evidence packets from persisted facts. Public reads and agents
  must not shell out to CoinGlass directly.
- `raw_payload_json` stores the provider payload needed for audit without
  making provider frames the business fact.

## Capture Roles

- Inline event capture answers "what market sample was observed close to
  this event commit?" It writes Tier 3 ticks and the event projection rows
  committed with `events`.
- Tier 1 stream capture keeps the hottest live targets fresh with OKX DEX
  WebSocket samples. `MarketTickStreamWorker` writes these ticks as
  `market_ticks(source_tier='tier1_ws')`.
- Tier 2 poll capture keeps the broader active set fresh through OKX DEX
  and CEX quote providers. `MarketTickPollWorker` writes these ticks as
  `market_ticks(source_tier='tier2_poll')`.
- `token_capture_tier` is a rebuildable projection with one runtime writer:
  `TokenCaptureTierWorker`.
- LivePriceGateway is presentation-only cache and WebSocket fan-out; it
  is not a fact writer.

## Provider Capability Model

`providers.py` exposes narrow protocols; there is no `MarketDataSource`
god interface.

- `MarketCapability` enum: `QUOTE_CEX`, `QUOTE_DEX_EXACT`, `STREAM_DEX`,
  `SEARCH_DEX`, `PROFILE_DEX_EXACT`, `CANDLES_DEX_EXACT`.
- `ProviderHealth(provider, capabilities, configured, last_error)` —
  health reports the configured capabilities, not every capability the
  provider could theoretically support. Keep health aligned with actual
  wiring.

Concrete provider clients (Binance USD-M CEX, OKX DEX, OKX DEX WS,
GMGN OpenAPI, GMGN direct WS, Marketlane) are wired in
`app/runtime/providers_wiring.py`. Asset Market services and workers
receive provider protocols by injection and may not import
`integrations/*`.

## Wake Channels

| Channel | Emitter | Listener |
|---------|---------|----------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker` | `TokenRadarProjectionWorker` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` |

`market_tick_written` is a wake hint; listeners re-read the database and catch
up by their configured interval. Wake mechanics are composed in
`app/runtime/bootstrap.py` through `DBPoolBundle.wake_emitter()` and
`wake_listener()`. Asset Market workers receive wake dependencies by injection;
they never call `pg_notify` directly. See `../../../../docs/WORKERS.md` for the
cross-domain inventory.

## Hard Boundaries

- Provider raw frames never reach `factor_snapshot_json`. Token Radar
  projection reads `market_ticks` and `enriched_events`, not provider clients.
- `event_anchor_backfill_jobs` is worker control state. Product surfaces and
  Token Radar never read it; they read the terminal or ready event-anchor fact
  in `enriched_events`.
- Identity evidence and asset identity selection never feed scoring
  families. They are gates and `data_health` inputs only.
- `LivePriceGateway` may fan out raw frames to WS for recent display, but
  Token Radar business state comes from persisted market tick facts.
- CLI ops commands may instantiate concrete provider clients for explicit
  operator commands; service runtime wiring stays centralised in
  `app/runtime/providers_wiring.py`.
- LLM enrichment may label watched social events, but token identity
  resolution stays deterministic and does not call an LLM in the hot
  path.
- Provider logo URLs are mirror inputs only. Public profile reads expose
  `identity.logo_url` as `NULL` or `/api/token-images/{image_id}`; no
  frontend or API path may call GMGN, Binance, OKX, or CEX image URLs directly.

## Update Triggers

Update this file in the same change as any of:

- `MarketTick` / market context / market readiness schema.
- A new market tick persistence trigger or capture-tier threshold.
- A new market `MarketCapability` value or `ProviderHealth` field.
- A worker gaining or losing a wake-in or wake-out channel.
- Asset identity evidence kinds or the policy that selects current
  identity.
- Discovery admission, retained candidate, or reprocess behaviour visible
  to Token Radar.
