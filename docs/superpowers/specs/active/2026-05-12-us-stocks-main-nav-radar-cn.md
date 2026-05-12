# Spec — US Stocks Main Nav Radar

**Status**: Draft
**Date**: 2026-05-12
**Owner**: Codex
**Related**:
- `docs/superpowers/specs/active/2026-05-12-us-equity-symbol-universe-cn.md`
- `docs/superpowers/specs/active/2026-05-12-token-radar-hot-resolution-market-readiness-cn.md`

## Background

当前主页面的 crypto Token Radar 由 `/api/token-radar` 提供：HTTP 路由读取 window/scope/limit，调用 `AssetFlowService.asset_flow()`，并把结果包成 `targets` 与 `attention` 两条 lane 返回给前端。证据见 `src/gmgn_twitter_intel/app/surfaces/api/http.py:183` 和 `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:20`。

`AssetFlowService` 只读取 token radar 投影，并在有 live market gateway 时把 `live_market` 覆盖到公开行上；公开 payload 的目标来自 factor snapshot subject，未包含股票 instrument 视图。证据见 `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:36`、`src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:44` 和 `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:76`。

前端主导航目前只有 `Live` 和 `Signal Lab` 两个 view；`/search` 是独立 focus route，不在左侧 views 中。证据见 `web/src/components/CockpitLayout.tsx:207` 和 `web/src/app/CockpitApp.tsx:235`。

US equity universe 已经有本地事实表和同步服务：Nasdaq Trader 两个 symbol directory 被解析并写入 `us_equity_symbols`，repository 支持 active ticker upsert/find/deactivate。证据见 `src/gmgn_twitter_intel/domains/asset_market/services/us_equity_symbol_sync.py:10`、`src/gmgn_twitter_intel/domains/asset_market/services/us_equity_symbol_sync.py:48` 和 `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py:164`。

确定性 resolver 已经能把 active US equity ticker 解析成 `MarketInstrument` / `NON_CRYPTO` / `CONFIRMED_US_EQUITY`，而 token radar source query 明确只允许 `Asset` 与 `CexToken` 进入 crypto radar。证据见 `src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py:259` 和 `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:100`。

`marketlane-cli` 已经提供 quote access plane：`AsyncMarketlaneClient.quote()` 通过 market data gateway 取 quote；instrument registry 会为公开 symbol 动态合成 Yahoo-backed instrument，因此 AAPL/RKLB 这类普通 ticker 不需要预先写入 marketlane registry。实现从 `https://github.com/AnalyThothAI/marketlane-cli` 打包安装，不依赖本地源码路径。

Token Radar 前端 mapper 目前把 `live_market.market_cap_usd` 无条件映射到 `item.market.market_cap`，行展示则只要有 `market_cap` 就优先显示市值。证据见 `web/src/lib/tokenRadar.ts:251` 和 `web/src/components/TokenRadarRow.tsx:136`。

## Problem

用户现在有两类不同需求混在一个界面风险里：crypto token radar 应该继续以 DEX/CEX token 作为交易对象，其中链上 token 有市值时用市值表达量级、CEX token 仍用价格；美股 ticker 则已经能被识别为非 crypto instrument，需要一个独立的主导航视图展示 GMGN 流里的股票关注度和 marketlane quote，而不是污染 crypto radar 或 token detail。

## First principles

1. Crypto radar 与 non-crypto instrument 必须保持硬边界。现有 source query 已把 `MarketInstrument` 排除在 `Asset`/`CexToken` token radar 之外，这个边界不能被 UI 新功能绕开。
2. Market data 事实与社交注意力要分层。GMGN events/token intents 负责注意力来源，marketlane 负责股票 quote；股票 quote 不进入 ingest/resolver 热路径。
3. 第一版美股页面不创造新的股票评分体系。除非有经过验证的 score version 和组件拆解，否则只展示可解释的 mention/author/recent-post/quote facts。

## Goals

- G1. WHEN a chain `Asset` row has usable market cap THEN Token Radar market primary SHALL display USD market cap; WHEN a `CexToken` row has both market cap and price THEN it SHALL display the current default price.
- G2. WHEN a GMGN cashtag resolves to active `MarketInstrument` with `CONFIRMED_US_EQUITY` THEN `/stocks` SHALL show it in a main-navigation US Stocks page without adding it to `/api/token-radar`.
- G3. WHEN a displayed stock has a marketlane quote available THEN the page SHALL show price, change versus reference close, as-of/freshness, and provider provenance.
- G4. WHEN marketlane quote is unavailable or slow THEN the page SHALL still show social attention rows with quote status, not fail the whole page.
- G5. WHEN the user changes existing window/scope controls THEN the US Stocks page SHALL respect the same window and scope semantics as the live cockpit.

## Non-goals

- Do not make stocks part of crypto Token Radar ranking or token detail drawer.
- Do not add a new persistent quote table or background stock quote worker in this slice.
- Do not send stock items to OpenAI Agents or create LLM stock theses.
- Do not build a full single-stock research workflow inside this app; marketlane remains the owner of deeper finance producer workflows.
- Do not change cashtag extraction rules.

## Target Architecture

The app gains a third main navigation view, `US Stocks`, backed by a new read model that combines existing social evidence with active `MarketInstrument` resolutions. The read model owns only aggregation of attention facts: mentions in window, unique authors, watched mentions, latest event, and the list of source event ids.

Stock quotes are fetched through a narrow marketlane quote adapter with a short in-process TTL. The adapter normalizes marketlane quote payloads into a small stock quote snapshot for the API. A quote failure becomes per-row quote status and provider error metadata; it does not remove the social row.

The existing crypto Token Radar mapper changes display semantics only: CEX rows keep price-first behavior, DEX rows keep market-cap-first behavior when market cap exists. No backend crypto scoring behavior changes.

## Conceptual Data Flow

```text
GMGN collector -> ingest -> token intent resolver -> token_intent_resolutions
                                             |
                                             +-> MarketInstrument rows -> stocks radar read model -> marketlane quote adapter -> /api/stocks-radar -> /stocks
                                             |
                                             +-> Asset/CexToken rows -> token radar projection -> /api/token-radar -> /
```

The new arrow starts after deterministic resolution because that is where US equity classification becomes authoritative. It does not reuse `AssetFlowService` because that service is intentionally scoped to token radar projections and crypto target lanes.

## Core Models

`StockRadarRow` represents one US equity ticker observed in the selected window. It has a market instrument identity, social attention metrics, latest evidence summary, quote snapshot, and row health. Its invariant is that `target_type` is `MarketInstrument` and the resolution reason includes `CONFIRMED_US_EQUITY`.

`StockQuoteSnapshot` represents marketlane's latest available quote for display. It includes price, reference close, percent change, provider, provider symbol, latency/freshness, as-of timestamp, and an error/status when unavailable. It is not persisted in this slice.

`StocksRadarData` represents the page payload: query metadata, rows, and aggregate health such as returned row count and quote success/error counts.

## Interface Contracts

`GET /api/stocks-radar` accepts the same authenticated request model and `window`, `scope`, and `limit` query semantics as `/api/token-radar`. It returns rows sorted by social attention first, then latest seen time. It can partially succeed: HTTP 200 with per-row quote status is valid when marketlane fails for some symbols. Bad window/scope/limit validation follows existing API conventions.

The web route `/stocks` is a main navigation page. It displays the same global topbar and scope/window controls as the live cockpit, then a stock table optimized for scanning: symbol, company/security name when available, mentions, authors, watched mentions, latest post time/author, price, percent change, quote status, and provider.

No new WebSocket payload is introduced. Stock rows refresh through React Query / API invalidation first; live push integration can be a later extension.

## Acceptance Criteria

- AC1. WHEN a CEX token row has `live_market.market_cap_usd` and `price_usd` THEN Token Radar SHALL render price as its market primary value.
- AC2. WHEN a DEX asset row has `live_market.market_cap_usd` THEN Token Radar SHALL render market cap as its market primary value.
- AC3. WHEN `/api/stocks-radar?window=1h&scope=all` is called after US equity sync and reprocess THEN the response SHALL include `MarketInstrument` rows and SHALL exclude `Asset`/`CexToken` rows.
- AC4. WHEN marketlane quote for a returned stock succeeds THEN the API SHALL include normalized quote price, reference-close change percent, as-of, provider, and freshness metadata.
- AC5. WHEN marketlane quote for one stock fails THEN the API SHALL keep that stock row with quote status `unavailable` and still return other rows.
- AC6. WHEN the user clicks `US Stocks` in the left views rail THEN the app SHALL route to `/stocks` and render the stocks radar page without opening the token detail drawer.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Marketlane import/path coupling breaks local runtime. | Medium | Wrap quote access behind a small adapter and allow an unavailable status instead of hard API failure. |
| Quote fan-out makes `/api/stocks-radar` slow. | Medium | Limit rows, short TTL cache per symbol, and partial results on timeout/error. |
| Stocks are mistaken for crypto opportunities. | High | Keep route/page/read model names explicitly stocks/MarketInstrument and do not feed rows into token radar scoring. |
| CEX rows accidentally switch to market-cap display if upstream adds market cap. | Medium | Test display choice by venue type in the frontend mapper/row rendering. |
| Main layout becomes cramped with a third nav item. | Low | Add one concise rail item; mobile nav can remain focused on live cockpit tasks until a dedicated mobile stocks view is needed. |

## Evolution Path

The next useful expansion is a stock detail route backed by marketlane's `us-single-stock` workflow artifacts and broader quote/bars context. This design leaves room for that by keeping marketlane access behind an adapter and keeping stock identity separate from crypto token identity. A later phase can add WebSocket invalidation or a persisted quote cache if measured API latency requires it.

## Alternatives Considered

- Detail-drawer tab for stocks — rejected because selected-token detail is scoped to `Asset`/`CexToken`; placing stocks there would blur the crypto/non-crypto boundary and require fake token objects.
- Fold stocks into Token Radar ranking — rejected because current token scoring contains DEX/CEX market-health and tradeability gates that do not apply to equities.
- Background stock quote worker plus database table — rejected for this slice because there is no measured need for persisted quotes yet, and marketlane already owns quote acquisition.
- Shell out to `uv run marketlane quote` per row — rejected because subprocess fan-out is slower and more fragile than a narrow Python adapter or equivalent client integration.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Keep `MarketInstrument` out of crypto token radar. |
| Always | Show DEX market cap before price when market cap is available. |
| Always | Show CEX current/default price before any market cap. |
| Always | Return partial stock rows when quote lookup fails. |
| Ask first | Persist stock quotes, add a stock detail route, or introduce stock-specific scoring. |
| Never | Send stock quote fetches through ingest/resolver hot paths. |
| Never | Treat a US equity ticker as an `Asset` or `CexToken` just to fit existing UI types. |
