# Plan — US Stocks Main Nav Radar

**Date**: 2026-05-12
**Status**: Completed
**Spec**: `docs/superpowers/specs/active/2026-05-12-us-stocks-main-nav-radar-cn.md`
**Branch**: `codex/us-stocks-main-nav-radar`
**Worktree**: `.worktrees/us-stocks-main-nav-radar`

## Goal

把美股作为独立主导航视图接入现有 GMGN 社交流：`MarketInstrument` 只进入股票雷达，不进入 crypto Token Radar。Token Radar 的市场展示规则同时硬切为：链上 token 有市值时用市值，CEX token 继续用当前默认价格。

不保留兼容性代码，不做旧 payload fallback，不把 stocks 塞进 token detail drawer。

## Current Baseline

- `make check` 在新 worktree 的基线已经失败，原因是 3 个既有文件需要格式化：`src/parallax/app/runtime/app.py`、`src/parallax/domains/token_intel/read_models/asset_flow_service.py`、`tests/integration/test_resolution_refresh_worker.py`。
- `/api/token-radar` 只读 `AssetFlowService`，而 `TokenRadarSourceQuery` 已经把 `MarketInstrument` 排除在 token radar 投影之外。
- US equity universe、`MarketInstrument` resolver、marketlane quote 能力已经存在。

## Task 1 — Backend Read Model

Create `StocksRadarService` for current `MarketInstrument` + `CONFIRMED_US_EQUITY` rows.

Implementation:
- Add `src/parallax/domains/token_intel/read_models/stocks_radar_service.py`.
- Query `events -> token_intents -> token_intent_resolutions -> us_equity_symbols`.
- Filter:
  - `token_intent_resolutions.is_current = true`
  - resolver policy equals `TOKEN_RADAR_RESOLVER_POLICY_VERSION`
  - `target_type = 'MarketInstrument'`
  - `resolution_status = 'NON_CRYPTO'`
  - `reason_codes_json @> '["CONFIRMED_US_EQUITY"]'`
  - `us_equity_symbols.status = 'active'`
  - same `window` and `scope` semantics as `/api/token-radar`
- Aggregate per ticker:
  - mentions
  - unique authors
  - watched mentions
  - latest seen timestamp
  - latest event id, author, text
  - source event ids
- Sort by mentions desc, watched mentions desc, latest seen desc, symbol asc.

Tests:
- Add unit coverage for aggregation shape and MarketInstrument-only filtering.
- Add quote failure coverage at service level.

## Task 2 — Marketlane Quote Adapter

Add a narrow adapter instead of shelling out.

Implementation:
- Add `src/parallax/integrations/marketlane/quote_provider.py`.
- Provide an async `quote(symbol)` method backed by `marketlane.client.AsyncMarketlaneClient`.
- Package `marketlane-cli` from `https://github.com/AnalyThothAI/marketlane-cli` through `uv`, not from a local filesystem path.
- Add short in-process TTL caching and per-symbol timeout.
- Normalize output into:
  - `status`
  - `price`
  - `reference_close_price`
  - `change_pct`
  - `asof`
  - `provider`
  - `provider_symbol`
  - `latency_class`
  - `error`

Tests:
- Fake quote provider in service tests.
- No subprocess-based compatibility path.

## Task 3 — API + Runtime Wiring

Expose authenticated `GET /api/stocks-radar`.

Implementation:
- Add marketlane config to settings under `providers.marketlane`.
- Wire `runtime.stock_quote_provider` only from the new provider config.
- Add `/api/stocks-radar` beside `/api/token-radar`.
- Return HTTP 200 with per-row quote status even when some quotes fail.
- Add `/stocks` to frontend static fallback routes.

Tests:
- Integration test for `/api/stocks-radar?window=1h&scope=all`.
- Verify returned rows are `MarketInstrument`.
- Verify crypto `Asset`/`CexToken` rows are excluded.
- Verify one quote failure does not fail the whole response.

## Task 4 — Token Radar Market Display Rule

Hard-cut frontend mapper/display semantics.

Implementation:
- In `web/src/lib/tokenRadar.ts`, classify target type before assigning `market.market_cap`.
- For `CexToken`, always set display market cap to `null`.
- For chain `Asset`, keep usable `live_market.market_cap_usd`.
- Leave backend crypto scoring/projection untouched.

Tests:
- Update/add frontend tests proving:
  - CEX row with price and market cap renders price primary.
  - DEX/chain asset row with market cap renders market cap primary.

## Task 5 — Frontend Main Nav Stocks Page

Add `/stocks` as a real main navigation page.

Implementation:
- Add API client/hook for `/api/stocks-radar`.
- Add `StocksRadarPage` with scan-friendly table:
  - symbol
  - company/security name
  - mentions
  - authors
  - watched mentions
  - latest author/time/text
  - price
  - percent change
  - quote status/freshness/provider
- Add `US Stocks` to the left main nav in `CockpitLayout`.
- Hide token detail drawer on `/stocks`; do not create fake token selection.
- Reuse global window/scope controls.

Tests:
- Component test for stock rows and quote unavailable state.
- Routing test or layout assertion for `/stocks` nav selection.

## Task 6 — Contracts, Formatting, Verification

Implementation:
- Update docs/contracts only where public API surface requires it.
- Regenerate OpenAPI/types if the repo has an established command.
- Format the touched backend and existing baseline-drift files.

Verification commands:
- `uv run pytest tests/test_stocks_radar_service.py`
- `uv run pytest tests/integration/test_api_http.py`
- `npm test -- --run` in `web`
- `npm run build` in `web`
- `make check`

Completion gate:
- All new tests pass.
- Full repo check passes or any remaining failure is documented with exact command/output.
- No compatibility paths remain for old stock routing, subprocess quote lookup, or local `marketlane-cli` source paths.

## Completion Notes

- Added `/api/stocks-radar`, `StocksRadarService`, and `StocksRadarQuery` for `MarketInstrument` + `CONFIRMED_US_EQUITY` flow.
- Wired Marketlane through `providers.marketlane`, packaged from GitHub via `tool.uv.sources`, with no local source path.
- Added `/stocks` as a main navigation route and a dedicated `US Stocks` page.
- Hard-cut Token Radar display so CEX rows do not expose market cap as the primary market metric while chain assets still can.
- Regenerated OpenAPI/types and updated public contract docs.
- Verified with `make check`, targeted API/frontend tests, `npm run build`, Marketlane quote smoke test, and local browser QA.
