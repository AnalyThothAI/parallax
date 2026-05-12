# GMGN DEX Market Provider Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** split the DEX provider boundary by capability and route resolved DEX asset quote/profile/candle reads through GMGN while preserving OKX discovery search and OKX live stream.

**Architecture:** `asset_market` owns all provider calls. Runtime wires explicit provider roles: OKX discovery, GMGN quote, GMGN candles/profile, OKX DEX stream, OKX CEX. Anchor and Search Intel consume role-specific providers; Token Radar projection and Search read models remain provider-free.

**Tech Stack:** Python 3.13, `httpx`, existing PostgreSQL repositories, `uv run pytest`, existing GMGN OpenAPI client.

---

## Upstream / Downstream Evaluation

### Upstream Producers

| Component | Current role | Change |
|-----------|--------------|--------|
| GMGN public WebSocket ingestion | Produces tweet/event payloads and optional token snapshots. | No market write change. It remains identity evidence only. |
| Deterministic resolver | Emits exact `Asset` targets when address/chain evidence is available. | Its exact `Asset(chain,address)` output becomes the only valid input for GMGN quote/profile/candle calls. |
| Discovery repository | Selects recent NIL/AMBIGUOUS lookup keys. | Still feeds OKX discovery search only. GMGN rank/trending is not used as resolver evidence. |
| OKX DEX REST search | Provides arbitrary symbol/address token candidates. | Becomes `DexTokenDiscoveryProvider`; no quote/candle responsibility. |
| OKX DEX WebSocket | Streams live market updates. | Remains `DexMarketStreamProvider`; no change. |
| GMGN OpenAPI | Currently only normalizes small `/v1/token/info` subset. | Expands to token info fields and token Kline. Used only after exact asset resolution. |

### In-Process Consumers

| Component | Current dependency | Change |
|-----------|--------------------|--------|
| `ResolutionRefreshWorker` | One `dex_market` handles search and post-reprocess anchor. | Accepts `dex_discovery_market` and `dex_quote_market` separately. Search uses OKX; anchor after reprocess uses GMGN if configured. |
| `AnchorPriceWorker` | `dex_market.token_prices(...)`. | Uses `dex_quote_market.token_quotes(...)`, writes GMGN provider attribution and market fields. |
| `MarketCandlesService` | `dex_market.token_candles(...)`, labels `okx_dex_candles`. | Uses `dex_candle_market.token_candles(...)`, labels `gmgn_dex_candles`. |
| `LivePriceGateway` | `stream_dex_market` and CEX polling. | No behavior change; DEX stream remains OKX WS. |
| HTTP Search Inspect overlay | Passes `providers.message_dex_market`. | Passes `providers.dex_candle_market`. |
| CLI `run-resolution-refresh` | Instantiates `OkxDexMarketProvider`. | Instantiates OKX discovery provider and GMGN quote provider when GMGN is configured. |

### Downstream Outputs

| Output | Expected after change |
|--------|-----------------------|
| `price_observations` message anchors | DEX anchors use provider `gmgn_dex_quote` and may include price, market cap, liquidity, holders. CEX anchors remain `okx`. |
| `price_feeds` for DEX anchors | Provider becomes `gmgn_dex_quote` for GMGN anchor feeds. |
| Search Intel `market_overlay` | DEX candles report `candle_source = "gmgn_dex_candles"`. Unsupported/empty/error states remain explicit. |
| Token Radar projection | No direct provider call. It sees improved anchor market fields only through persisted observations/read models. |
| Live WS | DEX live provider remains `okx_dex_ws_price_info`. |

## File-Level Edits

### `src/gmgn_twitter_intel/domains/asset_market/providers.py`

- Replace the monolithic `DexMarketProvider` with role-specific protocols:
  - `DexTokenDiscoveryProvider.search_tokens(...)`
  - `DexTokenQuoteProvider.token_quotes(...)`
  - `DexTokenCandleProvider.token_candles(...)`
  - `DexTokenProfileProvider.token_profile(...)`
- Rename request/result models for quote:
  - `DexTokenQuoteRequest(chain_id, address)`
  - `DexTokenQuote(chain_id, address, observed_at_ms, price_usd, market_cap_usd, liquidity_usd, volume_24h_usd, holders, raw)`
- Add `DexTokenProfile` for website/Twitter/Telegram/logo/banner/pool/security-adjacent raw fields.

### `src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py`

- Extend `GmgnTokenInfo` with richer market/profile fields and add `GmgnTokenKlineCandle`.
- Add `token_kline(chain, address, resolution, limit, now_ms=None)`.
- Map internal domain chains to GMGN chains: `eip155:1 -> eth`, `eip155:56 -> bsc`, `eip155:8453 -> base`, `solana -> sol`.

### `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`

- Rename `OkxDexMarketProvider` to `OkxDexDiscoveryProvider`; it exposes only `search_tokens`.
- Add `GmgnDexMarketProvider`; it exposes `token_quotes`, `token_candles`, and `token_profile`.
- Replace `_SerializedDexMarketProvider` with `_SerializedProvider`.
- Change `AssetMarketProviders` fields to explicit roles: `dex_discovery_market`, `dex_quote_market`, `dex_candle_market`, `dex_profile_market`, `stream_dex_market`.

### Other Runtime Consumers

- `anchor_price_observation.py`: call `token_quotes` and write provider `gmgn_dex_quote` with market fields.
- `anchor_price_worker.py`: accept `dex_quote_market`.
- `resolution_refresh_worker.py`: accept `dex_discovery_market` and `dex_quote_market`; search with OKX, anchor with GMGN.
- `market_candles_service.py`: accept `dex_candle_market`, label DEX candles `gmgn_dex_candles`.
- `app.py`, `http.py`, `cli/main.py`: pass the new role-specific providers.

## TDD Tasks

- [x] Task 1: GMGN parser and provider contracts.
- [x] Task 2: Runtime provider wiring split.
- [x] Task 3: Anchor quote path.
- [x] Task 4: Resolution refresh split.
- [x] Task 5: Search Intel candles.
- [x] Task 6: Verification and docs.

## Acceptance Mapping

| Spec AC | Plan tasks |
|---------|------------|
| AC1 explicit provider roles | Task 1, Task 2 |
| AC2 GMGN DEX anchor quote | Task 1, Task 2, Task 3 |
| AC3 visible GMGN failure, no fallback | Task 2, Task 3, Task 4 |
| AC4 OKX discovery search only | Task 2, Task 4 |
| AC5 GMGN Kline source | Task 1, Task 5 |
| AC6 OKX DEX WS live unchanged | Task 2, Task 4 |
| AC7 no read-model provider calls | Task 4, Task 5 |
| AC8 GMGN profile fields available internally | Task 1, Task 2 |

## Rollback

This is a code-level provider boundary change with no migration. Rollback is reverting this branch. Since no new table or destructive migration is introduced, persisted data remains valid. Any GMGN-written message anchors are provider-attributed as `gmgn_dex_quote`; reverting code does not corrupt them.

## Verification

- `uv run pytest tests/unit/test_gmgn_openapi_client.py tests/unit/test_providers_wiring.py tests/unit/test_anchor_price_observation.py tests/unit/test_market_candles_service.py tests/unit/test_resolution_refresh_worker.py tests/integration/test_resolution_refresh_worker.py tests/integration/test_api_health.py -q`
  - Result: `31 passed, 4 skipped`.
- `uv run ruff check .`
  - Result: `All checks passed!`.
- `make check-all`
  - Result: exit code 0.
  - Static/type/frontend gates: passed.
  - Unit/architecture/contract stage: `483 passed, 6 skipped`.
  - Integration stage: `178 passed, 9 skipped`.
  - E2E stage: `4 passed`.
  - Coverage stage: `744 passed, 14 skipped`; total coverage `81.73%`, required `80.0%`.
