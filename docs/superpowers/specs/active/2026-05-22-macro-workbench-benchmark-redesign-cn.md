# Spec — Macro Workbench Benchmark Redesign

**Status**: Approved
**Date**: 2026-05-22
**Owner**: Codex
**Related**:
- Benchmark: https://timsun.net/assets/equities
- Benchmark: https://timsun.net/assets/bonds
- Benchmark: https://timsun.net/assets/commodities
- Benchmark: https://timsun.net/assets/fx
- Benchmark: https://timsun.net/rates/
- Benchmark: https://timsun.net/fed/
- Benchmark: https://timsun.net/liquidity/
- Existing spec context: `docs/superpowers/specs/active/2026-05-21-macro-regime-70.md`
- Existing spec context: `docs/superpowers/specs/active/2026-05-21-macro-worker.md`
- Implementation plan: `docs/superpowers/plans/active/2026-05-22-macro-workbench-benchmark-redesign-plan-cn.md`

## Background

`gmgn-twitter-intel` already has a Macro Intel domain, but it is a first-generation macro state view rather than a benchmark-quality macro terminal. The current durable flow is:

```text
macrodata bundle macro-core
  -> gmgn-twitter-intel macro import-bundle
  -> macro_observations / macro_import_runs
  -> MacroViewProjectionWorker
  -> macro_view_snapshots
  -> /api/macro
  -> web /macro
```

Grounding in current code and docs:

- Macro facts and projections are documented in `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md:11`: `macro_observations` is the fact table, `macro_import_runs` is import audit, and `macro_view_snapshots` is the rebuildable read model written only by `MacroViewProjectionWorker`.
- System architecture documents the macro import and projection path in `docs/ARCHITECTURE.md:24`.
- `src/gmgn_twitter_intel/domains/macro_intel/_constants.py:7` maps provider series into canonical concepts such as liquidity, rates, Fed corridor, credit, volatility, assets, commodities, FX, crypto, and positioning.
- `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py:24` exposes `/api/macro` as a read-only latest-snapshot endpoint.
- `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py:32` exposes `/api/macro/assets/correlation`, currently computed at request time from `macro_observations`.
- `docs/FRONTEND.md:65` states that `/macro` renders deterministic Macro Intel state from `/api/macro` and must not recompute macro scoring in the frontend.
- `web/src/routes/AppRoutes.tsx:271` mounts `/macro/*` inside the cockpit shell.
- `web/src/routes/macro.route.tsx:4` routes `/macro`, `/macro/:moduleId`, `/macro/:moduleId/:sectionId`, and `/macro/assets/correlation`.
- `web/src/features/macro/MacroPage.tsx:46` defines the existing macro module ids: `overview`, `assets`, `rates`, `fed`, `liquidity`, `economy`, `volatility`, and `credit`.
- `web/src/features/macro/MacroPage.tsx:96` hard-codes module metadata, feature keys, secondaries, copy, and missing topics in the same file as rendering.
- `web/src/features/macro/MacroPage.tsx:466` implements the main page in a single large component file.
- `web/src/features/macro/MacroAssetCorrelationPage.tsx:24` implements the only truly separate macro detail route today.
- `web/package.json:21` includes `@tanstack/react-query`, `@tanstack/react-table`, Radix Tabs, `lightweight-charts`, and `lucide-react`; Macro currently uses React Query, Radix Tabs, lightweight single-series charts, and mostly hand-built tables/lists.

Benchmark research on 2026-05-22 found that `timsun.net` has a much clearer macro information architecture:

- Big top-level groups: Market Overview, Assets, Rates, Fed, Liquidity, Economy, Volatility, Credit, News, Reports.
- Assets has dedicated pages for equities, ETFs, options/GEX, CFTC positioning, bonds, commodities, FX, crypto, and crypto derivatives.
- Rates has dedicated pages for Fed funds, yield curve, auctions, real rates, and expectations.
- Fed has FOMC statements, speeches, announcements, and hawkish/dovish tracking.
- Liquidity has transmission chain, balance sheet, operations, RRP/TGA, reserves, global dollar, and subsurface flows.

The benchmark pages share a stable grammar: breadcrumb, H1, KPI tiles, chart panels with legends and units, mature tables/rankings, data source and last-updated state, AI/readout sections, validation/trigger/invalidator blocks, and links to deeper second-level pages.

## Problem

The current Macro page is hard to understand because it compresses too many macro domains into one route-owned page, uses tabs as a substitute for real second-level pages, mixes product copy/config/rendering/chart/table logic in one large file, and lacks mature page-specific chart and table contracts. Users comparing it to `timsun.net` see a large gap: the benchmark has clear pages for equities, bonds, commodities, FX, rates/Fed, and liquidity, while our page reads like a dense internal state dump instead of an actionable macro intelligence map for crypto/Twitter/token decisions.

## First Principles

1. **Facts stay in PostgreSQL; read models are rebuildable.** Macro observations are product facts; page state must come from facts or read models, not from provider raw frames or API-time side effects. This follows the Kappa/CQRS invariant in `docs/ARCHITECTURE.md:51` and the macro ownership table in `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md:11`.
2. **The frontend presents macro conclusions, it does not invent them.** Regime, score, confirmations, contradictions, triggers, and gaps must come from `/api/macro` or future macro module endpoints. Frontend view models may group and format; they must not re-score macro state. This follows `docs/FRONTEND.md:65`.
3. **Each meaningful macro page needs a first-class contract.** A benchmark-quality equities, rates, Fed, or liquidity page should not be only a slice of one generic JSON object. Page-specific series, tables, tiles, explanations, provenance, and data gaps need stable contracts that are testable, documented, and generated into frontend types per `docs/CONTRACTS.md`.
4. **Crypto relevance is the differentiator.** We should not clone a generic US macro site. The product must explain how assets, rates, Fed, and liquidity affect BTC/ETH, crypto derivatives, GMGN token radar, CEX leverage, and Twitter narrative propagation.

## Goals

- G1. Create a macro information architecture with real second-level routes for `overview`, `assets/equities`, `assets/bonds`, `assets/commodities`, `assets/fx`, `assets/crypto`, `assets/crypto-derivatives`, `rates`, `fed`, `liquidity`, `volatility`, and `credit`.
- G2. Replace the single dense Macro page experience with a repeatable page grammar: page header, KPI strip, primary chart area, supporting table, current read, validation/contradiction/trigger cards, provenance, and data gaps.
- G3. Make mature chart and table primitives first-class in Macro: multi-series charts, yield curve chart, normalized asset performance chart, correlation heatmap, time-series sparkline cards, and TanStack-backed data tables.
- G4. Preserve current Macro truth boundaries: no provider IO in API handlers, no frontend macro scoring, no scoring from stale/missing data.
- G5. Add page-level API/read-model contracts that can support benchmark-quality pages without duplicating logic in the frontend.
- G6. Make Phase 1 shippable from existing concepts, while explicitly marking Phase 2/3 data that requires new facts or upstream macrodata bundle expansion.
- G7. Surface every widget's `source`, `observed_at`, `freshness`, `data_quality`, and `score_participation` so stale or proxy data cannot silently drive conclusions.
- G8. Connect macro to the rest of this product: each macro page should expose a `crypto_read` and `token_impact` section when the backend has sufficient evidence.

## Non-Goals

- N1. Do not scrape, copy, or depend on `timsun.net`; it is a benchmark, not a dependency.
- N2. Do not replace Token Radar, Stocks Radar, News, Watchlist, or Pulse in this spec.
- N3. Do not add direct FRED, Treasury, Cboe, CFTC, OKX, Binance, Deribit, or ETF provider calls inside HTTP request handlers.
- N4. Do not require all benchmark data to exist in Phase 1. Missing CPI/NFP/ISM, full Fed speech scoring, options/GEX, ETF flows, and crypto options data must render as explicit data gaps until facts exist.
- N5. Do not make the frontend compute regime, score, probability, confidence, confirmation strength, or trade-map recommendations.
- N6. Do not redesign the global cockpit shell beyond the Macro route navigation needs.

## Target Architecture

### Product Navigation

Macro becomes a page family under `/macro`:

| Route | Purpose | Phase |
|-------|---------|-------|
| `/macro` | Market overview: regime, transmission chain, cross-asset confirmation, top triggers, crypto/token impact | Phase 1 |
| `/macro/assets` | Assets landing: equities, bonds, commodities, FX, crypto, correlation summary | Phase 1 |
| `/macro/assets/equities` | Equity leadership, breadth proxies, SPX/QQQ/IWM performance, crypto risk-on read | Phase 1 |
| `/macro/assets/bonds` | TLT/IEF/HYG/LQD performance, credit confirmation, duration stress | Phase 1 |
| `/macro/assets/commodities` | GLD/USO/WTI commodity beta, inflation shock read | Phase 1 |
| `/macro/assets/fx` | DXY/broad dollar, USD pressure, crypto dollar-liquidity read | Phase 1 |
| `/macro/assets/crypto` | BTC/ETH macro beta, correlation, risk-on/risk-off confirmation | Phase 1 |
| `/macro/assets/correlation` | Cross-asset rolling correlation heatmap and strongest pair tables | Phase 1 hardening |
| `/macro/rates` | Rates landing: curve, real rates, breakevens, policy path read | Phase 1 |
| `/macro/rates/yield-curve` | Curve shape, 2Y/5Y/10Y/30Y, 10Y-2Y, 10Y-3M | Phase 1 |
| `/macro/rates/real-rates` | Real yield and breakeven decomposition | Phase 1 |
| `/macro/fed` | Fed corridor, target band, EFFR/IORB/SOFR, meeting/speech gaps | Phase 1/2 |
| `/macro/liquidity` | Net liquidity stack, Fed assets, RRP, TGA, reserves, SOFR-IORB | Phase 1 |
| `/macro/liquidity/transmission-chain` | Funding stress chain and crypto impact path | Phase 1/2 |
| `/macro/volatility` | VIX and cross-vol proxy, missing MOVE/VIX term structure gaps | Phase 1 |
| `/macro/credit` | HY/IG OAS, HYG/LQD confirmation, private credit/CDS gaps | Phase 1 |
| `/macro/crypto-derivatives` | BTC/ETH funding, OI, basis, options/skew, ETF flows | Phase 2/3 |

The nav should be explicit and page-owned, not hidden as a generic tab set. Desktop may use a macro-local side nav plus page-local section nav; tablet/mobile should use compact route navigation that remains reachable without horizontal overflow.

### Page Grammar

Every macro second-level page follows the same readable structure:

1. **Page header**
   - Title, subtitle, breadcrumb, as-of, freshness badge.
   - One-sentence "what this page answers".
2. **KPI strip**
   - 3 to 6 normalized metric cards.
   - Each card includes value, unit, change, observed date, source, status.
3. **Primary chart block**
   - The chart most suited to the domain:
     - Assets: normalized multi-series return chart.
     - Equities: SPX/QQQ/IWM relative leadership plus breadth proxy when available.
     - Bonds: duration/credit ETF chart.
     - Commodities: GLD/USO/WTI chart.
     - FX: DXY/broad dollar chart.
     - Rates: yield curve and rate-history chart.
     - Fed: corridor band chart.
     - Liquidity: stacked/liquidity components chart.
     - Credit: HY/IG OAS plus HYG/LQD confirmation chart.
   - Chart includes legend, unit-aware axes, tooltip, range controls, and empty/stale states.
4. **Supporting table**
   - TanStack-backed where data is tabular.
   - Sortable columns, stable widths, sticky headers for dense tables, accessible row/column labels.
5. **Current read**
   - Backend-provided conclusion, confidence, confirmations, contradictions, invalidators.
   - Separate "crypto read" and "token impact" where available.
6. **Validation and trigger blocks**
   - Confirmations, contradictions, watch triggers, invalidation triggers.
   - No frontend inference beyond formatting backend-provided data.
7. **Provenance and gaps**
   - Data source, last observed, import run, freshness, staleness, missing concepts.
   - Explicit `score_participation=false` for stale/proxy/insufficient data.
8. **Drill links**
   - Links to related macro pages and downstream product pages such as Stocks, Token Radar, CEX radar, News, and Token Case where contracts exist.

### Backend Read Models

Phase 1 can start by extending `macro_view_snapshots` payloads, but the target shape should not stay a monolith. The design should converge on page-level macro module snapshots:

- `macro_view_snapshots`: overview and global state.
- `macro_module_snapshots`: rebuildable page/module state for `assets/equities`, `rates/yield-curve`, `liquidity`, etc.
- `macro_asset_correlation_snapshots`: rebuildable rolling correlation payload so `/api/macro/assets/correlation` does not recompute user-facing state at request time.

All read models must be written by exactly one runtime writer:

- Option A: extend `MacroViewProjectionWorker` to write all macro module snapshots in one transaction.
- Option B: add one new `MacroModuleProjectionWorker` that writes `macro_module_snapshots` and correlation snapshots.

The implementation plan should decide between these based on blast radius. The spec preference is Option B if module projection grows beyond simple reshaping, because page snapshots will become large and domain-specific.

### Frontend Structure

Macro frontend should be split by responsibility:

- `web/src/features/macro/api/`: React Query hooks for `/api/macro`, `/api/macro/modules/{module_id}`, `/api/macro/series`, and `/api/macro/assets/correlation`.
- `web/src/features/macro/model/`: route definitions, module catalog, page view-model formatting, chart series mapping, table column definitions.
- `web/src/features/macro/ui/shell/`: Macro route shell, local nav, breadcrumb, page header.
- `web/src/features/macro/ui/charts/`: chart primitives around `lightweight-charts` or a selected stronger chart library if the implementation plan justifies one.
- `web/src/features/macro/ui/tables/`: TanStack-backed tables for metrics, ranking, correlation, source coverage.
- `web/src/features/macro/ui/pages/`: page components for overview, assets, equities, bonds, commodities, FX, crypto, rates, Fed, liquidity, volatility, credit.
- `web/src/features/macro/macro.css`: route-level layout only; component-level CSS should move to CSS Modules or smaller owner CSS files so the current 1000+ line CSS file is reduced over time.

`MacroPage.tsx` should stop being the owner of module config, chart implementation, table rendering, and all page sections.

## Conceptual Data Flow

```text
macrodata-cli bundle
  -> gmgn macro import-bundle
  -> macro_observations + macro_import_runs
  -> Macro module projection
  -> macro_view_snapshots + macro_module_snapshots + macro_asset_correlation_snapshots
  -> /api/macro + /api/macro/modules/{module_id} + /api/macro/assets/correlation
  -> web macro route pages
  -> downstream drill links: stocks, news, cex, token radar, token case
```

Changed arrows:

- `Macro module projection -> macro_module_snapshots` is new. It exists because page-specific charts/tables/provenance should be deterministic, testable, and not rebuilt in React.
- `/api/macro/modules/{module_id}` is new. It prevents `/api/macro` from becoming a giant untyped payload and gives each second-level page a contract.
- `macro_asset_correlation_snapshots` is new or deferred Phase 1 hardening. The current request-time computation is acceptable for early exploration but should not remain the benchmark-quality contract.

## Core Models

### Macro Module Snapshot

Represents one page-level deterministic projection.

Fields:

- `snapshot_id`: stable id for the projection run and module.
- `projection_version`: immutable version, e.g. `macro_module_v1`.
- `module_id`: canonical route id, e.g. `assets/equities`, `rates/yield-curve`, `liquidity`.
- `asof_date`: date the page claims to represent.
- `status`: `ready | partial | stale | missing`.
- `headline_read`: one backend-provided sentence.
- `crypto_read`: optional backend-provided crypto-specific read.
- `token_impact`: optional list of narrative or token sensitivity notes.
- `tiles`: ordered KPI cards.
- `charts`: ordered chart payloads.
- `tables`: ordered table payloads.
- `confirmations`: evidence supporting the page read.
- `contradictions`: evidence against it.
- `watch_triggers`: future conditions that upgrade/downgrade the read.
- `invalidations`: conditions that invalidate the read.
- `data_gaps`: explicit gaps.
- `provenance`: import run, source counts, freshness, score participation.
- `computed_at_ms`: projection time.

Invariant: `status != ready` when required concepts are missing or stale beyond the page's freshness threshold.

### Macro Chart Payload

Semantic chart model, not a chart-library config dump.

Fields:

- `chart_id`
- `title`
- `description`
- `chart_type`: `line | multi_line | normalized_return | yield_curve | band | heatmap | stacked_area`
- `unit`
- `series`
- `annotations`
- `range_controls`
- `empty_state`

Invariant: each series has `concept_key`, `label`, `points`, `source`, `observed_range`, and `data_quality`.

### Macro Table Payload

Semantic table model.

Fields:

- `table_id`
- `title`
- `description`
- `columns`
- `rows`
- `default_sort`
- `row_groups`
- `empty_state`

Invariant: numeric cells carry raw values plus display metadata; frontend sorting uses raw values.

### Macro Evidence Item

Shared shape for confirmations, contradictions, triggers, and invalidations.

Fields:

- `code`
- `label`
- `description`
- `severity`
- `concept_keys`
- `observed_at`
- `source`
- `score_participation`
- `route_targets`

Invariant: stale or proxy-only evidence may display but must set `score_participation=false`.

## Interface Contracts

### `GET /api/macro`

Purpose: total macro overview.

Semantics:

- Continues to return current global snapshot and `data_gaps`.
- Adds or aligns top-level module summaries if the backend has module snapshots.
- Does not return every page's full chart/table payload.
- Missing snapshot remains a successful `ok: true` response with `snapshot: null` and explicit gap.

### `GET /api/macro/modules/{module_id}`

Purpose: second-level macro page data.

Supported `module_id` values:

- `overview`
- `assets`
- `assets/equities`
- `assets/bonds`
- `assets/commodities`
- `assets/fx`
- `assets/crypto`
- `assets/crypto-derivatives`
- `rates`
- `rates/yield-curve`
- `rates/real-rates`
- `fed`
- `liquidity`
- `liquidity/transmission-chain`
- `volatility`
- `credit`

Response:

- `snapshot`: module snapshot summary.
- `tiles`: KPI tiles.
- `charts`: semantic chart payloads.
- `tables`: semantic table payloads.
- `current_read`: headline, confidence, crypto read, token impact.
- `signals`: confirmations, contradictions, watch triggers, invalidations.
- `provenance`: source, import, freshness, score participation.
- `data_gaps`: required and optional gaps.

Errors:

- Unsupported module id returns `400 unsupported_macro_module`.
- Auth failure follows existing API auth behavior.
- Missing module snapshot returns `ok: true` with `status=missing` and explicit data gap, not 5xx.

Idempotency:

- Read-only; no provider IO; no projection rebuild.

### `GET /api/macro/series`

Purpose: reusable read-only time-series endpoint for chart drilldown and debug.

Inputs:

- `concept_keys`: comma-separated canonical concept keys only.
- `window`: bounded values such as `20d`, `60d`, `120d`, `1y`, `3y`.

Response:

- Concept-keyed series with points, source, freshness, quality, unit, and data gaps.

Errors:

- Provider series keys such as `yahoo:SPY` or `fred:DGS10` are rejected; public callers use canonical concepts only.

### `GET /api/macro/assets/correlation`

Purpose: cross-asset rolling correlation detail.

Semantics:

- Keeps `window=20d|60d|120d`.
- Continues to reject provider series keys.
- Target state reads a projection snapshot rather than computing public state on every request.
- Includes `asof_date`, `sample_size`, `start_date`, `end_date`, `source`, and gap reasons.

## Page-Specific Requirements

### Overview

Phase 1 must show:

- Regime headline and confidence.
- Transmission chain summary.
- Cross-asset confirmation.
- Top confirmations/contradictions/triggers.
- Global data quality and gaps.
- Crypto/token impact strip.

### Assets Landing

Phase 1 must show:

- Performance tiles for SPY/QQQ/IWM/TLT/HYG/LQD/GLD/USO/DXY/BTC/ETH when present.
- Cross-asset normalized return chart.
- Correlation summary linking to `/macro/assets/correlation`.
- Page cards for equities, bonds, commodities, FX, crypto, and crypto derivatives.

### Equities

Phase 1 must show:

- SPX, SPY, QQQ, IWM tiles.
- Normalized performance chart.
- Leadership/breadth table using existing available concepts.
- Current read that explicitly labels missing benchmark-only data such as analyst targets, 50DMA/200DMA breadth, options/GEX, and CFTC positioning if not available.
- Crypto read explaining whether equity risk appetite confirms BTC/ETH beta.

### Bonds

Phase 1 must show:

- TLT, HYG, LQD tiles.
- Duration vs credit ETF chart.
- Credit confirmation table.
- Links to rates and credit pages.

### Commodities

Phase 1 must show:

- GLD, USO, WTI tiles where available.
- Commodity/inflation-beta chart.
- Inflation shock read and crypto implication.

### FX

Phase 1 must show:

- DXY and broad-dollar tiles where available.
- Dollar pressure chart.
- USD risk read for BTC/ETH and high-beta token risk.

### Rates

Phase 1 must show:

- 2Y, 5Y, 10Y, 30Y, 10Y-2Y, 10Y-3M, 10Y real yield, breakeven tiles.
- Yield curve chart.
- Rate-history chart.
- Real-rate and breakeven decomposition.

### Fed

Phase 1 must show:

- Target lower/upper, EFFR, IORB, SOFR tiles.
- Fed corridor chart.
- SOFR-IORB stress read.
- Missing FOMC statements, speeches, meeting calendar, and hawkish/dovish data as explicit gaps until facts exist.

### Liquidity

Phase 1 must show:

- Fed assets, RRP, TGA, reserves, net liquidity, SOFR-IORB tiles.
- Liquidity stack chart.
- Transmission chain summary.
- Crypto/token impact section for liquidity-sensitive narratives.

### Volatility

Phase 1 must show:

- VIX tile and VIX chart.
- Cross-check with HY OAS and rates.
- Explicit missing gaps for VIX9D/VIX3M/MOVE/IV-vs-RV/GEX until supported.

### Credit

Phase 1 must show:

- HY OAS, IG OAS, HYG, LQD tiles.
- Credit stress chart.
- Confirmation/contradiction table against equities and crypto beta.
- Explicit missing gaps for CDX/CDS/private-credit proxies until supported.

### Crypto Derivatives

Phase 2/3 target:

- BTC/ETH spot, funding, OI, basis, options skew, liquidation/positioning, ETF flows.
- Two-horizon read: `0-24h` and `1-7d`.
- Data quality gating: stale/proxy data displays but does not score.
- Integration with existing CEX market intelligence read models where appropriate.

## Acceptance Criteria

- AC1. WHEN a user hard-loads `/macro` THEN the system SHALL render an overview page with regime, chain summary, top signals, provenance, data gaps, and links to major macro sections.
- AC2. WHEN a user hard-loads `/macro/assets/equities`, `/macro/assets/bonds`, `/macro/assets/commodities`, `/macro/assets/fx`, `/macro/rates`, `/macro/fed`, and `/macro/liquidity` THEN each route SHALL render a distinct page title, KPI strip, primary chart, supporting table or source/gap table, current read, and provenance.
- AC3. WHEN a page lacks required concepts THEN the API SHALL return `ok: true` with page `status=partial|missing` and explicit `data_gaps`, and the frontend SHALL render those gaps without inventing substitute conclusions.
- AC4. WHEN a macro chart renders more than one series THEN it SHALL show legend, unit-aware y-axis or labels, tooltip/crosshair, as-of context, and stable empty/stale states.
- AC5. WHEN a macro table renders more than 10 rows or sortable numeric data THEN it SHALL use a table abstraction with raw-value sorting, stable column widths, accessible headers, and no layout shift on mobile.
- AC6. WHEN `/api/macro/modules/{module_id}` is called with an unsupported id THEN the API SHALL return a typed `unsupported_macro_module` bad-request error.
- AC7. WHEN a public API receives provider series keys such as `fred:DGS10` or `yahoo:SPY` in module/series/correlation inputs THEN it SHALL reject them and require canonical concept keys.
- AC8. WHEN data is stale or proxy-only THEN the payload SHALL include `score_participation=false` for the affected evidence/widget and the frontend SHALL label it as not participating in score.
- AC9. WHEN implementation is complete THEN `MacroPage.tsx` SHALL no longer own all module catalog, page rendering, charts, tables, and formatting in one file; Macro UI must be decomposed into route shell, pages, chart primitives, table primitives, and model helpers.
- AC10. WHEN frontend tests run THEN they SHALL cover hard reloads for the new second-level macro routes and verify that frontend renders backend-provided gaps and signals rather than recomputing macro conclusions.
- AC11. WHEN backend tests run THEN they SHALL cover empty snapshot, partial coverage, stale series, invalid window, unsupported module id, unsupported concept key, and no provider IO in request handlers.
- AC12. WHEN mobile golden-path e2e runs at 390px and 430px THEN Macro top-level and second-level navigation SHALL remain reachable, text SHALL not overlap, and route content SHALL not be hidden behind shell navigation.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Recreating benchmark scope too broadly | High | Phase 1 uses existing concepts; Phase 2/3 only adds missing facts after separate specs. |
| Frontend starts recomputing macro decisions | High | Backend module snapshots own reads/signals; tests assert payload-driven rendering. |
| `/api/macro` becomes an unbounded mega-payload | Medium | Add module endpoint and keep overview compact. |
| Request-time correlation stays expensive or inconsistent | Medium | Move correlation to projection snapshot or set explicit bounded query limits until migrated. |
| Page count grows without data quality | High | Each page must show provenance, freshness, and score participation. |
| Chart library mismatch | Medium | Start with existing `lightweight-charts`; plan may introduce a richer chart library only with explicit trade-off and bundle impact. |
| CSS grows worse | Medium | Split page/component styles and keep route-level CSS small; add architecture tests if needed. |
| Macro page duplicates Stocks/CEX pages | Medium | Macro pages explain macro context and link out; they do not replace dedicated stock/token/cex scanners. |

## Evolution Path

Phase 1 should deliver navigation clarity and mature presentation from existing macro concepts. Phase 2 can add missing macro facts and page contracts: economic calendar, FOMC text/speech scoring, auction facts, VIX term structure, MOVE proxy, CFTC positioning, options/GEX, ETF flows, and crypto derivatives. Phase 3 can build macro-to-token sensitivity models that join macro module snapshots with Token Radar, CEX OI radar, news, and Twitter narrative epochs.

Avoid foreclosing:

- Multiple macro providers per concept with source priority.
- Snapshot backtesting and historical page replay.
- Asset/narrative sensitivity maps.
- LLM-generated summaries that are audit-backed by deterministic evidence refs.

## Alternatives Considered

- **Keep one `/macro` page and improve styling only.** Rejected because the benchmark gap is information architecture and page-level clarity, not just visual polish.
- **Build everything in frontend from `/api/macro`.** Rejected because it violates the frontend no-rescoring/no-inference boundary and makes page behavior hard to test.
- **Add direct provider calls in API handlers.** Rejected because it violates Kappa/CQRS and creates nondeterministic request-time product truth.
- **Clone the benchmark IA exactly.** Rejected because this product needs a crypto/Twitter/GMGN bridge, not a generic US macro research portal.
- **Introduce a new charting library immediately.** Deferred. Existing `lightweight-charts` may handle Phase 1 line/area needs; a richer library should be chosen in the plan only if heatmap/yield-curve/band charts cannot be cleanly implemented.
- **Create one worker per page.** Rejected for Phase 1 because it increases operational surface. Prefer one macro module projection writer unless page refresh cadences diverge materially.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use canonical macro concepts in public contracts; show source/freshness/gaps; keep API handlers read-only; make major macro sections reachable by direct URL. |
| Ask first | Adding new provider dependencies, introducing a new charting library, adding a new runtime worker, or changing macro scoring semantics. |
| Never | Scrape benchmark pages, print secrets, fetch macro providers in request handlers, let frontend invent macro score/regime, or silently score stale/proxy data. |

## Proposed Implementation Slices

1. **IA and frontend decomposition.** Split Macro route shell, module catalog, page components, chart primitives, and table primitives while preserving current `/api/macro` data.
2. **Phase 1 page routes from existing concepts.** Implement assets, equities, bonds, commodities, FX, rates, Fed, liquidity, volatility, credit pages with clear gaps.
3. **Backend module contract.** Add `/api/macro/modules/{module_id}` and typed response models; initially project from existing snapshot/observations.
4. **Projected page snapshots.** Add `macro_module_snapshots` if contract grows beyond request-time assembly.
5. **Correlation hardening.** Move correlation into a projected snapshot or explicitly keep it bounded with tests until a projection exists.
6. **Crypto/Twitter bridge.** Add `crypto_read` and `token_impact` sections backed by deterministic evidence, then link out to CEX/Token Radar/News surfaces.

## Review Decisions

- Phase 1 includes `/macro/assets/crypto-derivatives` as a partial page. It may read compact persisted CEX read models when available, but it must show explicit gaps for basis, ETF flows, and options/Greeks data until separate facts exist.
- Phase 1A should not add `macro_module_snapshots` or a new worker. It should add deterministic `/api/macro/modules/{module_id}` and `/api/macro/series` views assembled from existing `macro_view_snapshots`, `macro_observations`, and bounded CEX read models. Phase 1B can add `macro_module_snapshots` and `MacroModuleProjectionWorker` after the payload shape is stable.
- Phase 1 should keep existing `lightweight-charts` and use TanStack Table. Heatmaps can be accessible table/grid components. Do not add a new charting library unless Phase 1A proves a concrete limitation.
- First implementation should prioritize backend module contracts plus frontend route shell/components. Do not build a purely visual page that forces frontend-derived macro conclusions.
- Economic calendar, Fed documents, and auction feeds should be specified as `macrodata-cli` expansion work. CEX perpetual derivatives stay with `coinglass-cli`/`cex_market_intel`; Deribit/Greeks.live options should use a future pinned `greeks-cli` integration and dedicated options snapshots.
