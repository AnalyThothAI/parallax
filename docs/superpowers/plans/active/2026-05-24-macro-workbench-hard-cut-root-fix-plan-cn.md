# Macro Workbench Hard-Cut Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut `/macro` from a debug-like module shell into a readable macro terminal backed by real history readiness, semantic backend contracts, and non-compat frontend rendering.

**Architecture:** Replace `macro_regime_v3` / `macro_module_view_v1` with `macro_regime_v4` / `macro_module_view_v2`. Keep PostgreSQL facts and the existing import/projection path, but make history coverage part of readiness and make module payloads display-ready. Delete old frontend assumptions rather than supporting both old and new shapes.

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL, psycopg JSONB, `macrodata-cli` v0.1.5, React 19, Vite, TypeScript, React Query, `lightweight-charts`, TanStack Table, lucide-react.

**Execution status (2026-05-24):** Tasks 1-7 are implemented. Task 8 targeted backend, frontend, responsive, and browser-smoke gates pass; repository-wide `make check-all` is blocked by unrelated pre-existing formatting debt in 66 files outside this macro hard-cut scope. Evidence is recorded in `docs/superpowers/plans/active/2026-05-24-macro-workbench-hard-cut-root-fix-verification.md`.

---

## Hard-Cut Decisions

- [ ] Update `MACRO_VIEW_PROJECTION_VERSION` to `macro_regime_v4` and `MACRO_MODULE_VIEW_VERSION` to `macro_module_view_v2`.
- [ ] Do not read, render, or test old `macro_regime_v3` / `macro_module_view_v1` payloads after the cut.
- [ ] Do not add compatibility adapters in React. Test fixtures move to v2 shape in one edit.
- [ ] Do not keep visible raw concept keys, raw gap codes, or JSON provenance as fallback UI.
- [ ] Do not add provider IO inside `/api/macro*`; history arrives through `macrodata-cli` JSON imported into `macro_observations`.

## File Responsibility Map

- `src/gmgn_twitter_intel/domains/macro_intel/_constants.py`: projection/module version constants, concept metadata, history thresholds.
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_feature_engine.py`: concept history metrics, readiness, score participation, human labels.
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_regime_engine.py`: v4 snapshot status and source coverage.
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_catalog.py`: module questions, required concepts, chart/table specs, page labels.
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py`: v2 module payload builder.
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_series_view.py`: chart hydration with point-count gaps.
- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`: concept history counts for CLI/status diagnostics.
- `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py`: hard-cut API responses.
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py`: status/backfill diagnostics.
- `web/src/features/macro/model/*`: v2 labels, value formatting, chart/table models.
- `web/src/features/macro/ui/pages/*`: user-facing page grammar.
- `web/src/features/macro/ui/charts/*`: insufficient-history and missing chart states.
- `web/src/features/macro/ui/tables/*`: display-ready table rendering, no JSON dumps.
- `web/src/features/macro/ui/shell/*`: terminal-grade page header/nav/status.
- `docs/ARCHITECTURE.md`, `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/SETUP.md`: hard-cut contract and operations docs.

## Task 1 - Backend History Readiness Diagnostics

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/_constants.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py`
- Modify: `tests/unit/test_cli_macro_commands.py`
- Test: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

**Steps:**
- [ ] Add hard-cut constants:
  - `MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v4"`
  - `MACRO_MODULE_VIEW_VERSION = "macro_module_view_v2"`
  - `MACRO_MIN_CHART_POINTS = 2`
  - `MACRO_REQUIRED_DELTA_POINTS = {"5d": 6, "20d": 21, "60d": 61}`
  - `MACRO_REQUIRED_STAT_POINTS = 126`
- [ ] Add concept metadata in `_constants.py` keyed by canonical concept, for example:
  - `asset:spx`: label `标普500`, short label `SPX`, unit label `点`
  - `rates:dgs10`: label `10年期美债收益率`, short label `10Y`, unit label `%`
  - `liquidity:tga`: label `财政部现金账户`, short label `TGA`, unit label `百万美元`
  - `credit:hy_oas`: label `高收益债 OAS`, short label `HY OAS`, unit label `%`
  - `vol:vix`: label `VIX`, short label `VIX`, unit label `点`
- [ ] Add `MacroIntelRepository.concept_history_counts(concept_keys, lookback_days)` returning rows with `concept_key`, `points`, `latest_observed_at`, `oldest_observed_at`, and `sources`.
- [ ] Extend `macro status` output with `history_ready`, `history_coverage`, and `concepts_below_min_history`.
- [ ] Update CLI tests so one-point fixtures report `history_ready=false` and list the concept below minimum history.

**Tests:**
```bash
uv run pytest tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_migration_contract.py -q
uv run ruff check src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py tests/unit/test_cli_macro_commands.py
```

**Commit checkpoint:** `macro history readiness diagnostics`

## Task 2 - Projection V4 Feature And Status Semantics

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_feature_engine.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_regime_engine.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_feature_engine.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`

**Steps:**
- [ ] Write failing tests where each required concept has only one observation and `build_macro_view_snapshot()` returns `status="partial"` with `history_coverage_ratio < 1`.
- [ ] Add feature fields: `concept_key`, `label`, `short_label`, `description`, `unit_label`, `history_points`, `history_windows`, `score_participation`, `source`, and semantic `data_gaps`.
- [ ] Replace string-only gaps such as `insufficient_history:60d` with structured gaps:
  - `{"code":"insufficient_history_60d","label":"历史样本不足：无法计算 60 日变化","severity":"warning","score_participation":false}`
- [ ] Keep raw codes available only inside structured gap `code`; UI receives labels.
- [ ] Make snapshot status derive from latest coverage, history coverage, freshness, and data quality.
- [ ] Update worker notes to report `projection_version=macro_regime_v4`, `status`, `history_coverage_ratio`, and `data_gap_count`.

**Tests:**
```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_feature_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py -q
uv run mypy src/gmgn_twitter_intel/domains/macro_intel
```

**Commit checkpoint:** `macro regime v4 readiness`

## Task 3 - Module View V2 Backend Contract

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_catalog.py`
- Replace: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_series_view.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
- Replace assertions in: `tests/unit/domains/macro_intel/test_macro_module_views.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_series_view.py`

**Steps:**
- [ ] Replace module config titles from English labels (`Rates`, `Liquidity`) to display-ready Chinese titles and page questions.
- [ ] Build v2 `snapshot` with `title`, `subtitle`, `question`, `status_label`, `asof_label`, and `computed_at_label`.
- [ ] Build v2 `tiles` with labels and display metadata; remove duplicate `label=concept_key`.
- [ ] Build a single `primary_chart` field instead of a generic first chart list for main pages.
- [ ] Build typed tables with `columns` and `rows`; rows carry `display_value` and `sort_value`.
- [ ] Build `read` with `headline`, `regime_label`, `confidence_label`, `crypto_read`, and `token_impact`.
- [ ] Build `evidence` with separate arrays: `confirmations`, `contradictions`, `watch_triggers`, `invalidations`.
- [ ] Build `provenance` as compact rows, not nested JSON.
- [ ] Build `data_gaps` as structured localized objects.
- [ ] Make `assets/crypto-derivatives` return CEX missing/degraded rows when the CEX board is disabled or empty.

**Tests:**
```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py -q
uv run ruff check src/gmgn_twitter_intel/domains/macro_intel tests/unit/domains/macro_intel
```

**Commit checkpoint:** `macro module view v2 contract`

## Task 4 - API Contracts, OpenAPI, And Docs

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py`
- Modify: `tests/unit/test_api_macro_contract.py`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- Regenerate: `docs/generated/openapi.json`
- Regenerate: `web/src/lib/types/openapi.ts`
- Modify if generated facade needs it: `web/src/lib/types/frontend-contracts.ts`

**Steps:**
- [ ] Update `/api/macro` tests to expect `macro_regime_v4`, history coverage, structured gaps, and partial status for single-point data.
- [ ] Update `/api/macro/modules/{module_id}` tests to expect `macro_module_view_v2` and no raw table/provenance JSON.
- [ ] Update `/api/macro/series` tests so single-point series returns an explicit insufficient-history gap and multi-point series returns usable points.
- [ ] Regenerate OpenAPI and frontend types with the repository command used for contract generation.
- [ ] Update contracts to state there is no v3/v1 compatibility path.
- [ ] Update architecture docs with the history import path and v4 readiness rules.

**Tests:**
```bash
uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel -q
uv run ruff check src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py tests/unit/test_api_macro_contract.py
cd web && npm run generate:types
```

**Commit checkpoint:** `macro hard cut api contracts`

## Task 5 - Frontend Models And Fixtures Hard Cut

**Files:**
- Replace v1 fixtures in: `web/tests/fixtures/macroFixture.ts`
- Modify: `web/src/features/macro/model/macroPageViewModel.ts`
- Modify: `web/src/features/macro/model/macroModulePageModel.ts`
- Modify: `web/src/features/macro/model/macroChartModel.ts`
- Modify: `web/src/features/macro/model/macroTableColumns.ts`
- Modify tests:
  - `web/tests/unit/features/macro/model/macroChartModel.test.ts`
  - `web/tests/unit/features/macro/model/macroTableColumns.test.ts`
  - `web/tests/component/features/macro/MacroCharts.test.tsx`
  - `web/tests/component/features/macro/MacroDataTable.test.tsx`

**Steps:**
- [ ] Rewrite fixtures to v2 shape only; remove all `projection_version: "macro_module_view_v1"` data.
- [ ] Make label helpers consume backend display labels first and fail tests if visible text falls back to canonical concept keys.
- [ ] Make table model consume backend `columns` and `display_value`; stop deriving user-facing column names from arbitrary row object keys.
- [ ] Make chart model require at least `MACRO_MIN_CHART_POINTS` points for drawable series.
- [ ] Add tests asserting `asset:spx`, `rates:dgs10`, `insufficient_history:60d`, and JSON strings are absent from rendered user-facing text.

**Tests:**
```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroDataTable.test.tsx
cd web && npm run typecheck
```

**Commit checkpoint:** `macro frontend v2 models`

## Task 6 - Frontend Page Grammar And Visual Hard Cut

**Files:**
- Modify: `web/src/features/macro/MacroWorkbenchRoute.tsx`
- Modify: `web/src/features/macro/ui/shell/MacroShell.tsx`
- Modify: `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
- Modify: `web/src/features/macro/ui/shell/macroShell.css`
- Replace: `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
- Modify page wrappers under: `web/src/features/macro/ui/pages/`
- Modify: `web/src/features/macro/ui/pages/macroPages.css`
- Modify: `web/src/features/macro/ui/charts/MacroTimeSeriesChart.tsx`
- Modify: `web/src/features/macro/ui/charts/MacroNormalizedReturnChart.tsx`
- Modify: `web/src/features/macro/ui/charts/MacroYieldCurveChart.tsx`
- Modify: `web/src/features/macro/ui/charts/macroCharts.css`
- Modify: `web/src/features/macro/ui/tables/MacroDataTable.tsx`
- Modify: `web/src/features/macro/ui/tables/MacroSourceTable.tsx`
- Modify: `web/src/features/macro/ui/tables/macroTables.css`
- Modify tests:
  - `web/tests/component/features/macro/MacroModulePages.test.tsx`
  - `web/tests/component/features/macro/MacroShell.test.tsx`
  - `web/tests/routes/macro.route.test.tsx`

**Steps:**
- [ ] Remove the top-level duplicate `h1`/debug route title if it creates redundant hierarchy inside the shell.
- [ ] Render page header with module question, status label, as-of, history readiness, and compact gap strip.
- [ ] Render KPI strip with human labels and observed dates.
- [ ] Render current read as headline + regime + confidence + crypto read/token impact when present.
- [ ] Render evidence as four distinct sections: confirmations, contradictions, watch triggers, invalidations.
- [ ] Render provenance as source-quality rows with source, latest observed, freshness, quality, and score participation.
- [ ] Render chart insufficient-history state when series point count is below threshold.
- [ ] Keep CSS under `app.features`, feature-prefixed selectors, no retired CSS buckets, no nested UI cards.
- [ ] Add responsive checks for 390px and 834px route shells in existing route tests or Playwright golden paths.

**Tests:**
```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/routes/macro.route.test.tsx
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run build
```

**Commit checkpoint:** `macro terminal page grammar`

## Task 7 - Operations Documentation And Real-Data Verification Path

**Files:**
- Modify: `docs/SETUP.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/TESTING.md`
- Create after implementation: `docs/superpowers/plans/active/2026-05-24-macro-workbench-hard-cut-root-fix-verification.md`

**Steps:**
- [ ] Document that real-data debugging starts with `uv run gmgn-twitter-intel config` and only reports redacted paths/booleans.
- [ ] Document history backfill:
  ```bash
  uv run macrodata bundle history macro-core --start YYYY-MM-DD --end YYYY-MM-DD \
    | uv run gmgn-twitter-intel macro import-bundle --stdin
  uv run gmgn-twitter-intel macro project-once
  uv run gmgn-twitter-intel macro status
  ```
- [ ] Document FRED public CSV timeout and optional FRED API key as source health, not a frontend issue.
- [ ] Record expected good status: history coverage above threshold and no required concept below minimum history for pages claimed `ready`.
- [ ] Add verification notes for `/macro`, `/macro/assets`, `/macro/rates`, `/macro/fed`, `/macro/liquidity`, `/macro/volatility`, `/macro/credit`, and `/macro/assets/crypto-derivatives`.

**Tests:**
```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel db health
uv run gmgn-twitter-intel macro status
```

**Commit checkpoint:** `macro hard cut ops docs`

## Task 8 - Final Gates

**Files:**
- Verification artifact from Task 7.
- Any generated files from contract/type generation.

**Steps:**
- [ ] Run backend unit tests for Macro and API:
  ```bash
  uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py -q
  ```
- [ ] Run backend lint/type checks:
  ```bash
  uv run ruff check src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py
  uv run mypy src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py
  ```
- [ ] Run frontend focused tests:
  ```bash
  cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/routes/macro.route.test.tsx
  cd web && npm run lint
  cd web && npm run typecheck
  cd web && npm run build
  ```
- [ ] Start the app locally and verify no visible raw debug terms on Macro routes:
  - `asset:spx`
  - `rates:dgs10`
  - `insufficient_history:`
  - `{"run_id"`
  - `macro_module_view_v1`
- [ ] Run `make check-all` before declaring implementation complete.
- [ ] Record full outputs, skipped tests, coverage, e2e golden path status, residual risks, and screenshots in the verification artifact.

**Commit checkpoint:** `verify macro hard cut`

## Rollout Notes

- Existing `macro_regime_v3` snapshots may remain in the database for audit, but runtime constants must no longer select them.
- Existing frontend bundles and fixtures must be updated atomically with the API contract. There is no compatibility window.
- If history backfill cannot complete because FRED public CSV times out and no API key is configured, the correct product state is `partial` with source-health gaps, not frontend fallback.
