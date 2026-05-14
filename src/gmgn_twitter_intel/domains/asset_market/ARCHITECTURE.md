# Asset Market Architecture

> **Scope.** Owns asset identity evidence, the `MarketObservation` fact
> model, anchor / live / profile / discovery workers, and the live
> observation write budget. Global package boundaries live in
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
| Event anchor observation | `services/anchor_price_observation.py`, `runtime/anchor_price_worker.py` | `price_observations(observation_kind='event_anchor')` | One `event_anchor` row per resolution (`source_resolution_id` is unique on the `event_anchor` partition). Anchor describes the event-time observation; it is never overwritten by live data. |
| Live decision-latest observation | `runtime/live_price_gateway.py`, `services/live_observation_policy.py` | `price_observations(observation_kind='decision_latest')` | Raw provider frames update an in-process cache. Only frames that pass `should_persist_live_observation` become facts. `provider_state_change` after reconnect is a `first_seen`-equivalent trigger. |
| Asset profile refresh | `runtime/asset_profile_refresh_worker.py`, `services/asset_profile_refresh.py`, `repositories/asset_profile_repository.py` | `asset_profiles` | Resolved DEX assets are enriched through the GMGN exact-token profile role. Profile facts are asset-level current facts and never resolver evidence, ranking factors, or `factor_snapshot_json` fields. |
| Resolution refresh and discovery | `runtime/resolution_refresh_worker.py`, `repositories/discovery_repository.py` | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | Recent NIL / AMBIGUOUS lookup keys are refreshed through OKX DEX, then affected intents are reprocessed. Successful refresh emits `resolution_updated` so downstream readers wake; the worker itself does not run inline Token Radar projection. |
| CEX route sync | `services/asset_market_sync.py` | `cex_tokens`, `price_feeds` | Maintains token/feed routing without refreshing prices. |
| US equity symbol sync | `services/us_equity_symbol_sync.py` | `registry_assets` (MarketInstrument rows) | Confirms US equity symbols so the deterministic resolver can elevate them above DEX same-symbol assets. |

## MarketObservation Schema

`domains/asset_market/types/market_observation.py` defines the cross-domain
market fact contract. All providers normalise into these frozen value
types before any persistence call.

- `MarketTargetRef(target_type, target_id)` — the resolved target the
  observation belongs to. `target_type` is `Asset` or `CexToken`.
- `MarketObservation` — single market sample, with `observed_at_ms`,
  `received_at_ms`, `source`, `provider`, `pricefeed_id`, `price_usd`,
  `price_quote`, `quote_symbol`, `price_basis`, `market_cap_usd`,
  `liquidity_usd`, `holders`, `volume_24h_usd`, `open_interest_usd`, and
  `raw_payload_hash`. The dataclass intentionally does not carry the raw
  payload; `raw_payload_hash` is the audit anchor.
- `MarketReadiness(anchor_status, latest_status, dex_floor_status,
  missing_fields, stale_fields)` — derived per-target readiness facts
  surfaced through `factor_snapshot.market.readiness`.
- `MarketContext(event_anchor, decision_latest, readiness)` — the public
  market shape. Token Radar projection emits one `MarketContext` per row;
  the API and frontend consume it as-is.

## Material Observation Persistence Policy

`services/live_observation_policy.should_persist_live_observation` is the
single decision point for whether a live frame becomes a fact. It returns
`LiveObservationPersistDecision(should_persist, reason)` where `reason` is
one of:

| Reason | Trigger |
|--------|---------|
| `first_seen` | No previous persisted `decision_latest` exists for `(target_type, target_id, provider, pricefeed_id)`. |
| `heartbeat` | `now_ms - previous.observed_at_ms ≥ live_observation_heartbeat_seconds * 1000` (default `60s`). |
| `significant_price_change` | `abs(new_price - last_price) / last_price ≥ live_observation_min_price_change_pct` (default `0.005`). |
| `gate_field_change` | One of `holders`, `liquidity_usd`, `market_cap_usd`, `volume_24h_usd`, `open_interest_usd` changes missing/present status, or a DEX floor threshold is crossed. |
| `provider_state_change` | Stream reconnect/recover. The first fresh frame after recovery is persisted. |

Non-material reasons are `debounced` (inside
`live_observation_min_write_interval_seconds`, default `5s`) and
`not_material`. Debounce is an extra guard, not the correctness rule.

Write budget target: `100 targets × 5 fps × 10 min → ≤ 1500 persisted
rows`. Enforced by
`tests/benchmark/test_live_observation_write_budget.py`.

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
| `market_observation_written` | `AnchorPriceWorker`, `LivePriceGateway` (after persisted material observation only) | `TokenRadarProjectionWorker` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` |

Wake mechanics live in `app/runtime/wake_bus.py` (`WakeBus` for emit,
`WakeListener` for receive). Asset Market workers receive a `WakeBus`
instance by injection; they never call `pg_notify` directly. See
`../../../../docs/WORKERS.md` for the cross-domain inventory.

## Hard Boundaries

- Provider raw frames never reach `factor_snapshot_json`. Token Radar
  projection reads `price_observations`, not provider clients.
- Identity evidence and asset identity selection never feed scoring
  families. They are gates and `data_health` inputs only.
- `LivePriceGateway` may fan out raw frames to WS for debug/recent
  display, but Token Radar business cache patches use the persisted
  `decision_latest` shape only.
- CLI ops commands may instantiate concrete provider clients for explicit
  operator commands; service runtime wiring stays centralised in
  `app/runtime/providers_wiring.py`.
- LLM enrichment may label watched social events, but token identity
  resolution stays deterministic and does not call an LLM in the hot
  path.

## Update Triggers

Update this file in the same change as any of:

- `MarketObservation` / `MarketContext` / `MarketReadiness` schema.
- A new persistence trigger or threshold default in the live observation
  policy.
- A new market `MarketCapability` value or `ProviderHealth` field.
- A worker gaining or losing a wake-in or wake-out channel.
- Asset identity evidence kinds or the policy that selects current
  identity.
- Discovery admission, retained candidate, or reprocess behaviour visible
  to Token Radar.
