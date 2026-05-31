# Macro Workbench Benchmark Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/macro` 从一个拥挤状态页升级成 benchmark-quality 宏观 workbench：清晰二级页面、后端页面契约、成熟图表/表格、明确数据缺口，并把经济日历、Fed 文本、CEX 永续和 Deribit/Greeks.live 期权的数据源路线讲清楚。

**Architecture:** Phase 1A 先不新增 DB 表和 worker，用现有 `macro_view_snapshots` + `macro_observations` + bounded CEX read models 组装只读 module payload；Phase 1B 在 payload 变大、请求时组装成本变高或需要历史回放时，再物化 `macro_module_snapshots` 和 `MacroModuleProjectionWorker`。HTTP 不做 provider IO；前端只渲染 backend-provided module payload，不计算 regime、score、confirmation、trigger 或 macro conclusion。

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Alembic, psycopg JSONB, existing worker scheduler, `macrodata-cli` `v0.1.5`, pinned `coinglass-cli`, future pinned `greeks-cli`, React 19, Vite, TypeScript, React Query, `lightweight-charts`, TanStack Table, lucide-react.

---

## Source-Galaxy Decisions

- [ ] **经济日历和 Fed 文本走 `macrodata-cli` 增强。**
  - `macrodata-cli` 已是 JSON-first public macro data CLI/MCP，当前覆盖 FRED、NY Fed SOFR、Treasury Fiscal DTS operating cash balance、`rates-core`、`liquidity-core`。
  - 新上游 bundle 建议：`calendar-core`、`fed-text-core`、`auctions-core`。
  - `parallax` 只导入 normalized facts；Fed hawkish/dovish scoring 属于产品解释逻辑，放在本 repo 的 derived fact/read model，不放进 source CLI。
- [ ] **经济日历目标事实。**
  - `macro_calendar_events`
  - 字段：`event_id`, `source_name`, `event_type`, `title`, `scheduled_at`, `period`, `importance`, `actual_value`, `prior_value`, `consensus_value`, `surprise_value`, `unit`, `release_status`, `source_url`, `raw_payload_json`, `ingested_at_ms`
  - 官方/公开源没有 consensus 时存 `null`，并输出 `calendar_consensus_unavailable` gap；不抓随机日历站。
- [ ] **Fed 文本目标事实。**
  - `macro_policy_documents`
  - 字段：`document_id`, `source_name`, `document_type`, `title`, `published_at`, `speaker`, `meeting_date`, `source_url`, `text_hash`, `raw_text_json`, `raw_payload_json`, `ingested_at_ms`
  - `macro_policy_text_scores`
  - 字段：`document_id`, `scoring_version`, `hawkish_score`, `dovish_score`, `policy_topics_json`, `evidence_refs_json`, `score_participation`, `computed_at_ms`
- [ ] **CEX 永续衍生品直接用现有 `coinglass-cli` 链路，但只走 worker/read model。**
  - 当前 repo 已 pin `coinglass-cli`，并在 `cex_market_intel` worker 侧写入 `cex_oi_radar_rows`、`cex_detail_snapshots`、`cex_derivative_series`。
  - Macro `crypto-derivatives` 页读 `repos.cex_oi_radar.latest_board(limit=...)` 和必要的 `cex_detail_snapshots`；不在 `/api/macro/*` 调 CoinGlass 或 import `coinglass_cli`。
  - 可展示字段：OI、1h/4h/24h OI delta、funding、volume、mark price、CVD、long/short、top trader、liquidation level bands、`coinglass_status`、`degraded_reasons`、`observed_at_ms`、`computed_at_ms`。
- [ ] **Deribit/Greeks.live 期权用 `greeks-cli`，但作为 Phase 2/3 独立 options route。**
  - 公开 README 在 2026-05-22 确认 `greeks-cli` 覆盖 BTC/ETH/SOL ATM IV、IV history、skew、RV/HV、term structure、flows、OI、max pain、VRP。
  - 新 facts 建议：`crypto_options_snapshots` 或 `crypto_options_surface_snapshots`，字段覆盖 `atm_iv_json`, `skew_json`, `term_structure_json`, `flows_json`, `oi_stats_json`, `max_pain_json`, `vrp_json`, `data_quality`, `source_refs_json`, `computed_at_ms`。
  - 不把 CoinGlass/Binance/Greeks.live 塞进 `macrodata-cli`；它们属于 CEX/crypto derivatives domain，不是 official macro provider domain。

---

## Phase 1A Implementation Tasks

### Task 1 - Backend Module Catalog And View Services

**Owner:** backend agent

**Files:**
- `src/parallax/domains/macro_intel/_constants.py`
- `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- `src/parallax/domains/macro_intel/services/macro_module_views.py`
- `src/parallax/domains/macro_intel/services/macro_series_view.py`
- `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
- `tests/unit/domains/macro_intel/test_macro_module_views.py`
- `tests/unit/domains/macro_intel/test_macro_series_view.py`

**Steps:**
- [ ] Add `MACRO_MODULE_VIEW_VERSION = "macro_module_view_v1"`.
- [ ] Define supported module ids:
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
- [ ] For each module, define `title`, `route_path`, `required_concepts`, `optional_concepts`, `chart_specs`, `table_specs`, `gap_codes`, and `related_routes`.
- [ ] Build `build_macro_module_view(module_id, snapshot, observations, latest_import_run, cex_board=None)` with this payload:
  - `snapshot`
  - `tiles`
  - `charts`
  - `tables`
  - `current_read`
  - `signals`
  - `provenance`
  - `data_gaps`
  - `related_routes`
- [ ] Keep the service deterministic: no SQL, no provider clients, no scoring beyond selecting backend-provided `scenario`, `chain`, `features`, `indicators`.
- [ ] Add explicit gaps:
  - `fed_calendar_missing`, `fed_speeches_missing`, `fed_statement_text_missing`
  - `equity_breadth_missing`, `equity_options_gex_missing`
  - `move_index_missing`, `vix_term_structure_missing`, `options_iv_rv_missing`
  - `crypto_options_missing`, `basis_missing`, `etf_flows_missing`
- [ ] Build `build_macro_series_view(concept_keys, observations, window)` using canonical concepts only.
- [ ] Reject provider keys such as `fred:DGS10`, `yahoo:SPY`, and `coinglass:BTC`.

**Tests:**
```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py
uv run ruff check src/parallax/domains/macro_intel tests/unit/domains/macro_intel
uv run mypy src/parallax/domains/macro_intel
```

**Commit checkpoint:** `macro module view services`

### Task 2 - Backend HTTP Contracts

**Owner:** backend/API agent

**Files:**
- `src/parallax/app/surfaces/api/routes_macro.py`
- `tests/unit/test_api_macro_contract.py`
- `docs/CONTRACTS.md`
- `docs/generated/openapi.json`
- `web/src/lib/types/openapi.ts`
- `web/src/lib/types/frontend-contracts.ts`

**Steps:**
- [ ] Add `GET /api/macro/modules/{module_id:path}` after the concrete `/api/macro/assets/correlation` route.
  - Unsupported module id returns `400 unsupported_macro_module`.
  - Missing global macro snapshot returns `ok: true` with `status = "missing"` and gap `macro_view_snapshot_missing`.
  - `assets/crypto-derivatives` may include a compact CEX board section from `repos.cex_oi_radar.latest_board(limit=20)`; it must include `coinglass_status` and degradation metadata.
- [ ] Add `GET /api/macro/series`.
  - Query params: `concept_keys`, `window`.
  - Supported windows: `20d`, `60d`, `120d`, `1y`, `3y`.
  - Reject unknown concepts and provider keys.
  - Use existing `repos.macro_intel.observations_for_concepts(...)` with bounded lookback and limit.
- [ ] Extend `GET /api/macro` only with compact module summaries if cheap; do not return all charts/tables.
- [ ] Keep `/api/macro/assets/correlation` bounded and unchanged except documentation/tests.
- [ ] Regenerate OpenAPI and frontend types with existing repo commands.

**Tests:**
```bash
uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py
uv run ruff check src/parallax/app/surfaces/api/routes_macro.py tests/unit/test_api_macro_contract.py
cd web && npm run generate:types
```

**Commit checkpoint:** `macro module api contracts`

### Task 3 - Frontend Route Catalog And Workbench Shell

**Owner:** frontend agent

**Files:**
- `web/src/routes/macro.route.tsx`
- `web/src/features/macro/index.ts`
- `web/src/features/macro/api/useMacroModuleQuery.ts`
- `web/src/features/macro/api/useMacroSeriesQuery.ts`
- `web/src/features/macro/model/macroRoutes.ts`
- `web/src/features/macro/model/macroPageViewModel.ts`
- `web/src/features/macro/ui/shell/MacroShell.tsx`
- `web/src/features/macro/ui/shell/MacroBreadcrumb.tsx`
- `web/src/features/macro/ui/shell/MacroLocalNav.tsx`
- `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
- `web/src/features/macro/ui/shell/macroShell.css`
- `web/src/features/macro/MacroPage.tsx`
- `web/tests/unit/features/macro/model/macroRoutes.test.ts`
- `web/tests/component/features/macro/MacroShell.test.tsx`
- `web/tests/routes/macro.route.test.tsx`
- `web/tests/fixtures/macroFixture.ts`

**Steps:**
- [ ] Move route/module IA out of `MacroPage.tsx` into `macroRoutes.ts`.
- [ ] Parse real nested routes:
  - `/macro`
  - `/macro/assets`
  - `/macro/assets/equities`
  - `/macro/assets/bonds`
  - `/macro/assets/commodities`
  - `/macro/assets/fx`
  - `/macro/assets/crypto`
  - `/macro/assets/correlation`
  - `/macro/rates`
  - `/macro/rates/yield-curve`
  - `/macro/rates/real-rates`
  - `/macro/fed`
  - `/macro/liquidity`
  - `/macro/liquidity/transmission-chain`
  - `/macro/volatility`
  - `/macro/credit`
  - `/macro/assets/crypto-derivatives`
- [ ] Add `MacroShell` with breadcrumb, local nav, page title, as-of/source state, and responsive mobile nav.
- [ ] Keep `/macro/assets/correlation` as the existing dedicated page.
- [ ] Make `MacroPage.tsx` a thin compatibility wrapper during migration; it should stop owning module catalog, chart implementation, table implementation, and page sections.
- [ ] Centralize Macro fixtures so route/component tests stop duplicating huge payloads.
- [ ] Ensure view-model helpers only format and group backend payloads; no frontend scoring.

**Tests:**
```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/component/features/macro/MacroShell.test.tsx tests/routes/macro.route.test.tsx
cd web && npm run typecheck
cd web && npm run lint
```

**Commit checkpoint:** `macro workbench shell`

### Task 4 - Chart And Table Primitives

**Owner:** frontend agent

**Files:**
- `web/src/features/macro/model/macroChartModel.ts`
- `web/src/features/macro/model/macroTableColumns.ts`
- `web/src/features/macro/ui/charts/MacroTimeSeriesChart.tsx`
- `web/src/features/macro/ui/charts/MacroNormalizedReturnChart.tsx`
- `web/src/features/macro/ui/charts/MacroYieldCurveChart.tsx`
- `web/src/features/macro/ui/charts/MacroHeatmap.tsx`
- `web/src/features/macro/ui/charts/macroCharts.css`
- `web/src/features/macro/ui/tables/MacroDataTable.tsx`
- `web/src/features/macro/ui/tables/MacroCorrelationMatrix.tsx`
- `web/src/features/macro/ui/tables/MacroSourceTable.tsx`
- `web/src/features/macro/ui/tables/macroTables.css`
- `web/tests/unit/features/macro/model/macroChartModel.test.ts`
- `web/tests/unit/features/macro/model/macroTableColumns.test.ts`
- `web/tests/component/features/macro/MacroCharts.test.tsx`
- `web/tests/component/features/macro/MacroDataTable.test.tsx`

**Steps:**
- [ ] Use existing `lightweight-charts` for line, multi-line, normalized return, and yield curve style charts.
- [ ] Implement heatmap as accessible table/grid with raw numeric labels; do not add a new chart library in Phase 1A.
- [ ] Use TanStack Table for metric/source/ranking tables.
- [ ] Add stable empty/stale/loading states that do not resize the layout.
- [ ] Chart/table primitives accept semantic backend payloads, not local concept guesses.
- [ ] Numeric table columns sort by raw values and display formatted values.

**Tests:**
```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroDataTable.test.tsx
cd web && npm run typecheck
cd web && npm run lint
```

**Commit checkpoint:** `macro chart table primitives`

### Task 5 - Phase 1 Pages From Existing Concepts

**Owner:** frontend agent with backend fixture support

**Files:**
- `web/src/features/macro/ui/pages/MacroOverviewPage.tsx`
- `web/src/features/macro/ui/pages/MacroAssetsLandingPage.tsx`
- `web/src/features/macro/ui/pages/MacroAssetClassPage.tsx`
- `web/src/features/macro/ui/pages/MacroRatesPage.tsx`
- `web/src/features/macro/ui/pages/MacroFedPage.tsx`
- `web/src/features/macro/ui/pages/MacroLiquidityPage.tsx`
- `web/src/features/macro/ui/pages/MacroVolatilityPage.tsx`
- `web/src/features/macro/ui/pages/MacroCreditPage.tsx`
- `web/src/features/macro/ui/pages/MacroCryptoDerivativesPage.tsx`
- `web/src/features/macro/ui/pages/macroPages.css`
- `web/tests/component/features/macro/MacroModulePages.test.tsx`
- `web/tests/routes/macro.route.test.tsx`
- `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`
- `web/tests/e2e/support/mockApi.ts`

**Steps:**
- [ ] Implement page grammar for every module: header, KPI strip, primary chart, supporting table, current read, evidence board, provenance, data gaps.
- [ ] Use available concepts:
  - Equities: `asset:spx`, `asset:spy`, `asset:qqq`, `asset:iwm`
  - Bonds: `asset:tlt`, `asset:hyg`, `asset:lqd`, `credit:hy_oas`, `credit:ig_oas`
  - Commodities: `asset:gld`, `asset:uso`, `commodity:wti`
  - FX: `fx:dxy`, `fx:broad_dollar`
  - Crypto: `crypto:btc`, `crypto:eth`
  - Rates: `rates:dgs2`, `rates:dgs5`, `rates:dgs10`, `rates:dgs30`, `rates:10y2y`, `rates:10y3m`, `rates:real_10y`, `inflation:10y_breakeven`
  - Fed: `fed:target_upper`, `fed:target_lower`, `fed:effr`, `fed:iorb`, `liquidity:sofr`
  - Liquidity: `liquidity:fed_assets`, `liquidity:on_rrp`, `liquidity:tga`, `liquidity:reserve_balances`, `liquidity:sofr`
  - Volatility: `vol:vix`
  - Credit: `credit:hy_oas`, `credit:ig_oas`, `asset:hyg`, `asset:lqd`
- [ ] `crypto-derivatives` page shows CEX perp board if present and explicit gaps for basis/options/ETF flows.
- [ ] Update existing asset correlation page to reuse shared table styles where practical.
- [ ] Add mobile cold-load coverage for at least `/macro/assets/equities` at 390px/430px.

**Tests:**
```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run build
```

**Commit checkpoint:** `macro phase one pages`

---

## Phase 1B Hardening Tasks

### Task 6 - Materialized Module Snapshots

**Owner:** backend/runtime agent

**Trigger:** Start this only after Phase 1A proves module payload shape and tests are stable.

**Files:**
- `src/parallax/platform/db/alembic/versions/20260522_0081_macro_module_snapshots.py`
- `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/parallax/domains/macro_intel/runtime/macro_module_projection_worker.py`
- `src/parallax/app/runtime/worker_factories/macro_intel.py`
- `src/parallax/app/runtime/worker_registry.py`
- `src/parallax/platform/config/settings.py`
- `src/parallax/app/surfaces/cli/parser.py`
- `src/parallax/app/surfaces/cli/commands/macro.py`
- `tests/unit/domains/macro_intel/test_macro_module_projection_worker.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/unit/test_cli_macro_commands.py`
- `docs/WORKERS.md`

**Steps:**
- [ ] Add `macro_module_snapshots`.
- [ ] Add `MacroModuleProjectionWorker` as the single writer.
- [ ] Add CLI `macro project-modules-once`.
- [ ] Change `/api/macro/modules/{module_id}` to read latest module snapshot instead of assembling on request.
- [ ] Keep fallback to deterministic request-time assembly only while migration rollout is incomplete; remove fallback after deployment is stable.

**Tests:**
```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_module_projection_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_cli_macro_commands.py tests/architecture/test_worker_runtime_contracts.py
uv run ruff check src/parallax/domains/macro_intel src/parallax/app/runtime src/parallax/app/surfaces/cli tests/unit
```

**Commit checkpoint:** `macro module snapshot hardening`

---

## External Data Expansion Tasks

### Task 7 - Companion Specs For Calendar/Fed Text And Greeks Options

**Owner:** planning agent

**Files:**
- `docs/superpowers/specs/active/2026-05-22-macrodata-calendar-fed-text-expansion-cn.md`
- `docs/superpowers/specs/active/2026-05-22-greeks-cli-crypto-options-integration-cn.md`
- `docs/superpowers/plans/active/2026-05-22-macrodata-calendar-fed-text-expansion-plan-cn.md`
- `docs/superpowers/plans/active/2026-05-22-greeks-cli-crypto-options-integration-plan-cn.md`
- `docs/ARCHITECTURE.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- `src/parallax/domains/cex_market_intel/ARCHITECTURE.md`

**Steps:**
- [ ] Spec `macrodata-cli` calendar/Fed text expansion using official/public sources first.
- [ ] Spec `parallax` import facts for `macro_calendar_events`, `macro_policy_documents`, and `macro_policy_text_scores`.
- [ ] Spec `greeks-cli` pinned dependency and options snapshot worker.
- [ ] Document that CEX perps stay in `cex_market_intel` with `coinglass-cli`; Deribit options use future crypto options snapshots; neither belongs to `macrodata-cli`.

**Tests:**
```bash
uv run pytest tests/architecture
```

**Commit checkpoint:** `macro external data expansion specs`

### Task 8 - Documentation And Final Verification

**Owner:** integration agent

**Files:**
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `docs/WORKERS.md`
- `docs/ARCHITECTURE.md`
- `docs/generated/openapi.json`
- `docs/generated/cli-help.md`
- `docs/superpowers/plans/active/2026-05-22-macro-workbench-benchmark-redesign-verification-cn.md`

**Steps:**
- [ ] Document new Macro routes and endpoint contracts.
- [ ] Document frontend decomposition and no-frontend-scoring invariant.
- [ ] Document `macrodata-cli` / `coinglass-cli` / `greeks-cli` source boundary.
- [ ] Record QA notes for `/macro`, `/macro/assets/equities`, `/macro/assets/bonds`, `/macro/assets/commodities`, `/macro/assets/fx`, `/macro/rates`, `/macro/fed`, `/macro/liquidity`, `/macro/credit`, `/macro/assets/crypto-derivatives`, and `/macro/assets/correlation`.
- [ ] Save verification output in the verification doc.

**Full verification:**
```bash
uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/architecture
uv run ruff check src tests docs
uv run mypy src/parallax/domains/macro_intel src/parallax/app/surfaces/api
cd web && npm test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run build
```

**Commit checkpoint:** `macro workbench verification docs`

---

## Subagent Execution Plan

- [ ] Backend API agent owns Tasks 1-2.
- [ ] Frontend agent owns Tasks 3-5.
- [ ] Runtime hardening agent owns Task 6 only after Phase 1A is merged.
- [ ] Planning/docs agent owns Tasks 7-8.
- [ ] Integration reviewer checks:
  - no provider IO in API handlers
  - no frontend scoring
  - no `coinglass_cli` or `greeks_cli` imports outside runtime acquisition code
  - route hard-load coverage
  - mobile overflow and text overlap

## Acceptance Gates

- [ ] `/macro` and Phase 1 second-level routes hard-load directly.
- [ ] `/api/macro/modules/{module_id}` is the data source for module pages.
- [ ] Unsupported module id returns `unsupported_macro_module`.
- [ ] Provider keys such as `fred:DGS10` and `yahoo:SPY` are rejected in public query params.
- [ ] Stale or proxy data displays with `score_participation=false` or equivalent data-quality metadata.
- [ ] `MacroPage.tsx` no longer owns all IA, charts, tables, and page sections.
- [ ] Chart/table primitives have fixed responsive dimensions and stable empty states.
- [ ] `/macro/assets/crypto-derivatives` clearly separates existing CEX perp data from missing options/basis/ETF-flow data.
- [ ] External specs route calendar/Fed text to `macrodata-cli`, CEX perps to `coinglass-cli`, and Deribit options to `greeks-cli`.

## Rollback Plan

- [ ] Backend routes are additive; `/api/macro` and `/api/macro/assets/correlation` remain live.
- [ ] If `/api/macro/modules/*` has issues, frontend can temporarily route modules to overview with explicit `macro_module_view_unavailable`.
- [ ] Phase 1B worker can be disabled with `workers.macro_module_projection.enabled: false`.
- [ ] External data specs do not change runtime until separate approval.
