# GMGN DEX Market Provider Split Hard Cut Spec

**Status**: Approved for implementation by user request
**Date**: 2026-05-12
**Owner**: Codex with Qinghuan
**Scope**: 架构 spec；implementation plan 另起一篇
**Related**:

- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`
- `docs/superpowers/specs/active/2026-05-11-token-radar-market-boundary-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`
- `src/parallax/domains/token_intel/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- GMGN Agent API: `https://docs.gmgn.ai/index/gmgn-agent-api`
- OKX Token Search: `https://web3.okx.com/onchainos/dev-docs-v5/dex-api/dex-market-token-search`

## One-line decision

GMGN becomes the exact-address DEX market/profile source for resolved assets. OKX remains the discovery/search provider, CEX provider, and DEX live-stream provider. The implementation is a hard boundary split, not a compatibility wrapper around the current monolithic DEX provider.

## Background

The current runtime wires one OKX DEX market object into multiple responsibilities: sync DEX market, message DEX market, discovery DEX market, and separately OKX DEX WebSocket for stream market. This happens in `_wire_asset_market`, where the same serialized OKX DEX provider is passed to `sync_dex_market`, `message_dex_market`, and `discovery_dex_market`, while `stream_dex_market` is an OKX WS provider (`src/parallax/app/runtime/providers_wiring.py:277`).

The current `DexMarketProvider` protocol combines three different capabilities in one interface: `search_tokens`, `token_prices`, and `token_candles` (`src/parallax/domains/asset_market/providers.py:92`). These are not the same product capability. Search resolves unknown symbols or addresses. Quote refresh observes a known token. Candles hydrate a chart for a known token.

Anchor DEX pricing currently batches `DexTokenPriceRequest` values and calls `dex_market.token_prices` (`src/parallax/domains/asset_market/services/anchor_price_observation.py:97`). The write path then records provider `okx`, writes only `price_usd`, and explicitly leaves `market_cap_usd`, `liquidity_usd`, `volume_24h_usd`, and `holders` as `None` (`src/parallax/domains/asset_market/services/anchor_price_observation.py:164`).

Search Intel chart hydration calls `dex_market.token_candles` for `Asset` overlays and labels the source as `okx_dex_candles` (`src/parallax/domains/asset_market/read_models/market_candles_service.py:42`). This is already an exact-address use case, not a discovery use case.

Live DEX market is stream-shaped. `LivePriceGateway` consumes `DexMarketStreamProvider.stream_price_info` and publishes in-process `live_market_update` payloads (`src/parallax/domains/asset_market/runtime/live_price_gateway.py:211`). GMGN's observed OpenAPI/CLI capabilities are polling-shaped for token info and Kline; they are not a replacement for this stream contract.

The existing GMGN OpenAPI integration only calls `/v1/token/info` and normalizes a small subset of the response: symbol, name, logo, price, previous price, market cap, and raw payload (`src/parallax/integrations/gmgn/openapi_client.py:13`). Live research confirmed the raw response also contains richer exact-token fields such as liquidity, holder count, pool, website, Twitter/X, Telegram, dev/stat/security-style metadata, and GMGN/GeckoTerminal links.

Token Intel architecture already preserves the right direction of dependency. Discovery/reprocess uses OKX DEX for recent NIL/AMBIGUOUS lookup keys, anchor/live market is owned by `asset_market`, Radar projection consumes market facts, and Search read model never performs provider calls (`src/parallax/domains/token_intel/ARCHITECTURE.md:38`). The public contract also states that GMGN social payload token snapshots are identity evidence only, and embedded GMGN price/market-cap values are not written during ingest (`docs/CONTRACTS.md:55`).

## Problem

The current provider boundary forces one external provider object to pretend it can search, quote, candle, and sometimes live-stream. That shape makes it hard to use GMGN where it is stronger, because GMGN is rich for resolved chain+address assets but does not expose an equivalent general `search_tokens(query)` capability in the observed CLI/OpenAPI surface. A wholesale provider replacement would either lose OKX search/live behavior or introduce compatibility shims and fallback branches that hide provider semantics.

## First principles

1. **Capability beats brand**: a provider is wired by the specific capability it can prove, not by a broad `dex_market` label.
2. **Resolved asset first**: GMGN is used only after the system has exact `chain_id + address`. GMGN trending, trenches, or rank data must not resolve symbol-only intents.
3. **Market facts stay in `asset_market`**: `token_intel` and Search consume read models and snapshots; they do not call OKX, GMGN, or any provider.
4. **Hard cut over compatibility**: the design removes the monolithic DEX provider boundary. It does not add `hasattr` checks, legacy adapters, or "try GMGN then silently fallback to OKX" runtime chains.
5. **Failure should be visible**: if GMGN cannot hydrate a resolved asset, the output is `missing`, `unsupported`, `provider_error`, or `rate_limited`, not a value silently borrowed from another provider path.

## Goals

- **G1 Provider capability split**: DEX provider wiring is split into explicit discovery, quote, candle, profile, and stream roles. The old "one DEX provider object owns everything" boundary is removed from runtime composition.
- **G2 GMGN exact asset profile**: for resolved DEX assets, GMGN supplies token identity/profile details that current Token Radar is missing: official website, Twitter/X, Telegram, logo/banner, pool, liquidity, holders, supply, and provider links when present.
- **G3 GMGN exact asset quote**: DEX anchor observations for resolved assets use GMGN token info as the market source and can write price, market cap, liquidity, holders, and raw provenance when those fields are present.
- **G4 GMGN exact asset candles**: Search Intel DEX candle hydration uses GMGN Kline for resolved assets and labels the candle source as GMGN.
- **G5 OKX search preserved**: OKX remains the provider for token name/symbol/contract search during discovery and reprocess. This is an explicit role, not a fallback.
- **G6 OKX live preserved**: OKX DEX WebSocket remains the live stream provider until GMGN exposes and proves an equivalent stream capability.
- **G7 No provider calls from read models**: Search read model, Radar projection, and public API composition continue to consume internal facts only.
- **G8 Provider health is observable**: GMGN quote/profile/candle failures, rate limits, and coverage are surfaced in worker results or health output so missing data is explainable.

## Non-goals

- This spec does not implement the one-click narrative agent. It creates the profile/market substrate that a later narrative agent can consume.
- This spec does not replace OKX token search with GMGN trending/rank/trenches data.
- This spec does not replace OKX CEX universe, CEX ticker, or DEX WebSocket streaming.
- This spec does not let frontend or API handlers call external providers directly.
- This spec does not preserve the old monolithic `DexMarketProvider` as a compatibility interface.
- This spec does not introduce runtime fallback from GMGN quote/candles to OKX quote/candles. Shadow comparison may exist only as an offline verification or operator command, not in the product path.
- This spec does not change tweet ingestion semantics. GMGN social-stream token payload remains identity evidence unless a dedicated market worker fetches GMGN OpenAPI data for a resolved asset.

## Target architecture

The target architecture has small provider roles and one clear owner for each fact.

```mermaid
flowchart TD
  A["Tweet / GMGN public stream"] --> B["token evidence + intents"]
  B --> C["deterministic resolver"]
  C -->|NIL / AMBIGUOUS symbol| D["OKX discovery search"]
  D --> E["asset identity evidence + reprocess"]
  C -->|EXACT Asset(chain,address)| F["GMGN exact asset market/profile"]
  E -->|resolved Asset(chain,address)| F
  F --> G["asset_market observations + profile facts"]
  G --> H["Token Radar scoring input"]
  G --> I["Search Intel market overlay"]
  J["OKX DEX WebSocket"] --> K["LivePriceGateway in-process live market"]
  K --> L["WS live_market_update"]
```

### Provider roles

| Role | Provider | Input | Output | Notes |
|------|----------|-------|--------|-------|
| DEX discovery search | OKX | query + chain set | token candidates | Used only for lookup keys and reprocess. |
| DEX exact quote | GMGN | chain + address | price and market fields | Used for anchor/message market on resolved assets. |
| DEX exact profile | GMGN | chain + address | socials, links, pool, security/risk-adjacent metadata | Stored as provider profile facts, not as resolver guesses. |
| DEX exact candles | GMGN | chain + address + bar/window | OHLCV series | Used by Search Intel overlays. |
| DEX live stream | OKX WS | hot asset targets | live market updates | Remains stream-only and process-local. |
| CEX market | OKX CEX | native market id | ticker/candles/universe | Out of GMGN scope. |

### Ownership boundaries

`asset_market` owns provider calls, market/profile observations, source labels, provider health, and field freshness.

`token_intel` owns evidence, intents, deterministic resolution, scoring, Radar projection, and Pulse/notification inputs. It may read market/profile facts through an internal interface, but it must not invoke providers.

`app/runtime` wires providers by role. There is no generic DEX provider slot. A missing role is a startup/runtime configuration fact, not a reason to branch through a legacy adapter.

`web` and public API receive composed read models. They never receive provider credentials and never choose provider routing.

## Conceptual data flow

```text
symbol-only tweet
  -> token_intel lookup key
  -> OKX discovery search
  -> asset identity evidence
  -> resolver reprocess
  -> resolved Asset(chain,address)
  -> GMGN exact quote/profile/candles

address tweet or GMGN token payload
  -> deterministic exact Asset(chain,address)
  -> GMGN exact quote/profile/candles

hot resolved Asset
  -> OKX DEX WS live stream
  -> in-process live_market_update
```

The new arrow is `resolved Asset -> GMGN exact quote/profile/candles`. It exists because GMGN carries richer exact-token data than the current OKX price path, while still requiring a known chain/address. It does not replace `symbol-only -> OKX discovery search` because GMGN's observed market endpoints are list/rank-oriented, not arbitrary search-oriented.

## Core models

### ResolvedDexAsset

A resolved DEX asset is the only valid input to GMGN exact market/profile calls.

Semantic fields:

- `target_type = Asset`
- internal `target_id`
- canonical `chain_id`
- normalized contract `address`
- display symbol/name from identity current

Invariant: GMGN quote/profile/candle calls require exact `chain_id + address`. Symbol-only inputs are invalid.

### DexTokenMarketSnapshot

An exact-token market snapshot from GMGN.

Semantic fields:

- price in USD
- market cap in USD, direct or derived from price and circulating supply
- liquidity in USD
- holder count
- supply fields
- pool address, quote token, exchange, reserves when present
- observed_at_ms, using fetch time when the provider response has no authoritative observation timestamp
- provider, raw payload hash, raw payload reference

Invariant: a field is written only if GMGN returned it or it is deterministically derived from fields in the same response.

### DexTokenProfileSnapshot

An exact-token profile snapshot from GMGN.

Semantic fields:

- website
- Twitter/X username or URL
- Telegram
- logo and banner
- GMGN URL and third-party links
- description and verification/status fields when present
- dev/stat/security-adjacent fields that are useful for later due diligence

Invariant: profile fields do not resolve a symbol-only token by themselves. They enrich an already resolved asset.

### DexCandleSeries

An exact-token OHLCV series from GMGN Kline.

Semantic fields:

- bar
- ordered candles
- time_ms, open, high, low, close
- volume_usd and token amount when present
- provider and response metadata

Invariant: candle source is explicit. A GMGN candle response is labeled as GMGN, not as generic DEX or OKX.

### ProviderRoleHealth

Per-role provider health.

Semantic fields:

- role name
- provider
- status: `ready`, `missing_config`, `provider_error`, `rate_limited`, `unsupported`
- last success/failure time
- last error class
- optional rate-limit reset time

Invariant: health is role-specific. GMGN quote failure does not imply OKX discovery failure, and OKX search success does not imply GMGN profile readiness.

## Interface contracts

### Anchor DEX observations

When an anchor worker observes a resolved `Asset`, the DEX quote role uses GMGN. The resulting observation uses a GMGN provider label and includes market fields that GMGN returned. If GMGN fails, the observation is not silently completed with OKX price data.

### Search Intel market overlay

When Search Intel enriches an `Asset` overlay with candles, it uses the GMGN candle role. The response exposes `candle_source = "gmgn_dex_candles"` or a clear error/empty/unsupported status. It does not label GMGN candles as OKX candles.

### Discovery and reprocess

When discovery receives a symbol or address lookup key that requires arbitrary search, it uses the OKX discovery role. GMGN trending/trenches/rank outputs may be used only by future research or scan features, not by resolver candidate selection in this spec.

### Live market

When the live gateway needs stream updates for hot DEX assets, it uses OKX DEX WebSocket. GMGN polling does not masquerade as live streaming. If OKX WS is not configured, live DEX status is unsupported or missing.

### Token profile read surface

Public surfaces may expose a token profile block for resolved assets after the profile facts exist. The block is read-only, provider-attributed, and does not block Radar scoring if absent. Narrative generation is explicitly outside this spec.

## Acceptance criteria

- **AC1**. WHEN asset market providers are wired at runtime THEN the system SHALL wire explicit provider roles for discovery, quote, profile, candle, stream, and CEX instead of one monolithic DEX market provider.
- **AC2**. WHEN a resolved DEX `Asset(chain_id,address)` needs an anchor quote THEN the system SHALL fetch exact-token GMGN market data and write provider-attributed market fields returned by GMGN.
- **AC3**. WHEN GMGN quote/profile lookup fails THEN the system SHALL surface a role-specific missing/error/rate-limited status and SHALL NOT silently fallback to OKX quote/candle data in the same product path.
- **AC4**. WHEN a symbol-only or ambiguous token lookup needs discovery THEN the system SHALL use OKX token search and SHALL NOT use GMGN trending/trenches/rank data as resolver evidence.
- **AC5**. WHEN Search Intel requests DEX candles for a resolved asset THEN the system SHALL use GMGN Kline and expose a GMGN candle source label.
- **AC6**. WHEN the live gateway publishes DEX live market updates THEN the system SHALL continue to use OKX DEX WebSocket with explicit OKX stream provider attribution.
- **AC7**. WHEN Token Radar projection or Search read model runs THEN it SHALL NOT perform external provider calls.
- **AC8**. WHEN a resolved asset has GMGN profile fields THEN public/internal read models SHALL be able to expose official links and social handles without reading from GMGN web pages or scraping.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| GMGN exact token info appears single-token oriented, while current OKX price path batches requests. | High | Keep GMGN calls behind bounded worker concurrency, TTL cache, and role health. Do not put GMGN calls in API/read-model hot paths. |
| GMGN does not provide arbitrary token search. | High | Keep OKX as the only discovery search provider in this spec. Make GMGN symbol-only inputs invalid by contract. |
| GMGN response may not include authoritative field-level observed timestamps. | Medium | Use fetch time as `observed_at_ms` and label it as provider fetch time in plan/tests. |
| Removing fallback can reduce market coverage during GMGN outage. | Medium | Prefer honest `provider_error` over mixed-provider facts. Operator health and retry policy make the outage visible. |
| GMGN CLI/OpenAPI field names may drift. | Medium | Add contract tests around captured raw payloads and parser fixtures in the implementation plan. |
| Provider labels can become product-facing confusion. | Low | Use role-specific labels: `gmgn_dex_quote`, `gmgn_dex_profile`, `gmgn_dex_candles`, `okx_dex_search`, `okx_dex_ws`, `okx_cex`. |

## Evolution path

The next natural expansion is a token narrative agent that consumes `DexTokenProfileSnapshot`, recent Twitter/X content, official website text, and recent market/social facts to generate a concise due-diligence narrative. That agent should be a separate spec because it introduces LLM output, source attribution, staleness policy, and user-triggered generation semantics.

If GMGN later exposes a documented arbitrary token search endpoint, it can be evaluated as a new `DexTokenDiscoveryProvider`. That should not require changing quote/profile/candle roles.

If GMGN later exposes a real streaming market feed, it can be evaluated as a `DexMarketStreamProvider`. Polling token info should remain separate from streaming live updates.

## Alternatives considered

- **Wholesale replace OKX with GMGN**: rejected because GMGN's observed surface does not replace OKX arbitrary token search, OKX CEX, or OKX DEX WebSocket live stream.
- **Keep `DexMarketProvider` and add a GMGN adapter with unsupported methods**: rejected because it preserves the current coupling and forces runtime branches around fake capabilities.
- **Runtime fallback chain: GMGN first, OKX second**: rejected for this spec because it hides provider failure and makes observations mix semantics. Explicit roles are clearer.
- **Use GMGN trending/trenches as resolver candidate search**: rejected because rank/list outputs are not arbitrary query search and can worsen same-symbol false positives.
- **Scrape GMGN token pages**: rejected because the CLI/OpenAPI path returns structured data, while web pages are login/session-shaped and brittle.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use GMGN only for exact resolved DEX assets. Use OKX for discovery search, CEX, and DEX live stream. Keep provider calls inside `asset_market` workers/services. |
| Ask first | Exposing GMGN profile fields on public HTTP surfaces, adding narrative generation, or using GMGN rank/trending as a new product scan. |
| Never | Call GMGN or OKX from Token Radar projection/Search read models; resolve symbol-only intents from GMGN trending; add a compatibility shim that makes one provider pretend to support every DEX capability; silently fallback across provider roles. |
