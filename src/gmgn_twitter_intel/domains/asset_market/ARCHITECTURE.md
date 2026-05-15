# Asset Market Architecture

> **Scope.** Owns asset identity evidence, the `MarketTick` fact
> model, capture-tier / stream / poll market workers, cache-only live
> market fan-out, profile refresh, and discovery workers. Global package boundaries live in
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
| Event market capture | `services/event_market_capture.py`, ingest runtime | `market_ticks(source_tier='tier3_inline')`, `enriched_events` | Ingest captures the event-adjacent market sample outside the DB transaction, then commits event facts and tick facts together. |
| Market capture tier projection | `runtime/token_capture_tier_worker.py`, `repositories/token_capture_tier_repository.py` | `token_capture_tier` | Active Token Radar targets are ranked into stream, poll, or inline-only capture tiers. This table is a rebuildable control plane, not a market fact. |
| Tier 1 market stream | `runtime/market_tick_stream_worker.py` | `market_ticks(source_tier='tier1_ws')` | Stream targets come from `token_capture_tier(tier=1)`. Provider IO never holds a DB session. |
| Tier 2 market poll | `runtime/market_tick_poll_worker.py` | `market_ticks(source_tier='tier2_poll')` | Poll targets come from `token_capture_tier(tier=2)`. DEX and CEX provider calls run outside DB sessions. |
| Live market fan-out | `runtime/live_price_gateway.py` | in-process cache only | Raw provider frames update process-local latest state and WebSocket subscribers. The gateway does not write market facts. |
| Asset profile refresh | `runtime/asset_profile_refresh_worker.py`, `services/asset_profile_refresh.py`, `repositories/asset_profile_repository.py` | `asset_profiles` | Resolved DEX assets are enriched through the GMGN exact-token profile role. Profile facts are asset-level current facts and never resolver evidence, ranking factors, or `factor_snapshot_json` fields. |
| Resolution refresh and discovery | `runtime/resolution_refresh_worker.py`, `repositories/discovery_repository.py` | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | Recent NIL / AMBIGUOUS lookup keys are refreshed through OKX DEX, then affected intents are reprocessed. Successful refresh emits `resolution_updated` so downstream readers wake; the worker itself does not run inline Token Radar projection. |
| CEX route sync | `services/asset_market_sync.py` | `cex_tokens`, `price_feeds` | Maintains token/feed routing without refreshing prices. |
| US equity symbol sync | `services/us_equity_symbol_sync.py` | `registry_assets` (MarketInstrument rows) | Confirms US equity symbols so the deterministic resolver can elevate them above DEX same-symbol assets. |

## MarketTick Schema

`domains/asset_market/types/market_tick.py` defines the cross-domain
market fact contract. All providers normalise into this frozen value
type before any persistence call.

- `target_type` is `chain_token` or `cex_symbol`.
- `target_id` is the deterministic market target key, such as
  `solana:<address>` or `okx:<symbol>-USDT`.
- `source_tier` records whether the sample came from Tier 1 stream,
  Tier 2 poll, or inline event capture.
- `source_provider` records the concrete provider path, such as
  `okx_dex_ws`, `okx_dex_rest`, or `okx_cex_rest`.
- Numeric market fields are optional except `price_usd`, which must be a
  positive finite decimal.
- `raw_payload_json` stores the provider payload needed for audit without
  making provider frames the business fact.

## Capture Roles

- Inline event capture answers "what market sample was observed close to
  this event commit?"
- Tier 1 stream capture keeps the hottest live targets fresh with OKX DEX
  WebSocket samples.
- Tier 2 poll capture keeps the broader active set fresh through OKX DEX
  and CEX quote providers.
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

Concrete provider clients (OKX CEX, OKX DEX, OKX DEX WS, GMGN OpenAPI,
GMGN direct WS, Marketlane) are wired in
`app/runtime/providers_wiring.py`. Asset Market services and workers
receive provider protocols by injection and may not import
`integrations/*`.

## Wake Channels

| Channel | Emitter | Listener |
|---------|---------|----------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker` | `TokenRadarProjectionWorker` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` |

Wake mechanics are composed in `app/runtime/bootstrap.py` through
`DBPoolBundle.wake_emitter()` and `wake_listener()`. Asset Market
workers receive wake dependencies by injection; they never call
`pg_notify` directly. See `../../../../docs/WORKERS.md` for the
cross-domain inventory.

## Hard Boundaries

- Provider raw frames never reach `factor_snapshot_json`. Token Radar
  projection reads `market_ticks` and `enriched_events`, not provider clients.
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
