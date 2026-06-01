# Rates Workbench Clarity Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic rates module pages with a readable rates workbench that answers the policy, curve, auction, real-rate, and expectations questions before showing diagnostics.

**Architecture:** Keep Macro Intel and PostgreSQL projections as the only data truth. The frontend adds a rates-specific presentation adapter and route renderer that consumes `macro_module_view_v3` plus `/api/macro/series`, fixes the yield-curve inline-series contract, and keeps provenance/data health in a secondary diagnostics section. No provider calls, migrations, workers, or new persisted read models are introduced in this plan.

**Tech Stack:** React, TypeScript, existing Macro API hooks, lightweight-charts primitives where already used, SVG for the Fed funds corridor band, TanStack-backed `MacroDataTable`, Vitest, Testing Library, Playwright, frontend architecture harness.

---

**Status**: Draft
**Date**: 2026-06-01
**Owning spec**: `docs/superpowers/specs/active/2026-06-01-rates-workbench-clarity-redesign.md`
**Worktree**: `.worktrees/rates-workbench-clarity-redesign/`
**Branch**: `codex/rates-workbench-clarity-redesign`

## Scope

In scope:

- Rates child routes: `/macro/rates/fed-funds`, `/macro/rates/yield-curve`, `/macro/rates/auctions`, `/macro/rates/real-rates`, `/macro/rates/expectations`.
- Rates-local navigation, market read, fact strip, primary visual, decision support, detail table, and diagnostics hierarchy.
- Yield-curve chart rendering from inline chart `points` when `latest` is absent.
- Proxy-mode copy for Treasury auctions and policy expectations when official feeds are missing.
- Component/unit/e2e coverage and responsive verification for the five rates routes.

Out of scope:

- New Treasury auction importers, Fed funds futures feeds, FOMC probability feeds, database migrations, or worker ownership changes.
- A real `/macro/rates` overview page. The parent alias remains a redirect to `/macro/rates/fed-funds` in this implementation.
- Redesigning non-rates Macro pages.
- Frontend computation of policy probabilities, auction demand labels, macro scores, or trade recommendations.

## Pre-Flight

- [ ] Confirm the approved spec exists and is marked Approved:
  `rg -n "\\*\\*Status\\*\\*: Approved" docs/superpowers/specs/active/2026-06-01-rates-workbench-clarity-redesign.md`
- [ ] Create the implementation worktree from the repository root:
  `git worktree add .worktrees/rates-workbench-clarity-redesign -b codex/rates-workbench-clarity-redesign main`
- [ ] Verify isolation before touching `src/`, `web/src`, or `web/tests`:
  `cd .worktrees/rates-workbench-clarity-redesign && git branch --show-current && git status --short`
- [ ] Read the frontend guardrails inside the worktree:
  `sed -n '1,220p' docs/FRONTEND.md`
- [ ] Capture real-data context without printing secrets:
  `uv run parallax config`
  Expected: reports `config_path` and `workers_config_path` under `~/.parallax/`; no secret values are copied into commits.
- [ ] Capture macro readiness:
  `uv run parallax macro status`
  Expected: records whether rates are `ok`, `partial`, or `missing`; this command is diagnostic evidence, not product UI.

Known-failing baseline tests:

- None expected. If a baseline gate fails before edits, record the exact command, failure, and whether it is unrelated in the verification artifact before continuing.

## File-Level Edits

### Existing Frontend Files

- `web/src/features/macro/model/macroChartModel.ts:138-158`
  - Change `buildMacroYieldCurveModel` so it accepts tenor series where `series.latest` is absent but `series.points` contains usable observations.
  - Add private helpers:
    ```ts
    function latestSeriesNumericValue(series: MacroSemanticRecord): number | null;
    function latestInlinePointValue(series: MacroSemanticRecord): number | null;
    ```
  - Keep `TENOR_YEARS_BY_CONCEPT` as the canonical tenor ordering source.
  - Keep non-tenor spread concepts such as `rates:10y2y` out of the yield-curve point list.

- `web/src/features/macro/ui/pages/MacroMarketBoard.tsx:38-96`
  - Rename the private `PrimaryChart` to an exported `MacroPrimaryChart`.
  - Keep `MacroMarketBoard` behavior unchanged for non-rates pages.
  - Keep chart status formatting local; do not add a new exported status helper.

- `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx:6-20`
  - Import `isRatesModuleId` and `MacroRatesModulePage`.
  - Route rates module ids to `MacroRatesModulePage`.
  - Keep `MacroOverviewModulePage` for overview and `MacroLeafModulePage` for every non-rates leaf module.

- `web/src/features/macro/MacroWorkbenchRoute.tsx:93-110`
  - Import `isRatesModuleId`.
  - For rates modules, set shell eyebrow to `利率工作台` when the backend section is generic.
  - Remove `版本` from rates shell `statusItems`; projection version stays available in diagnostics.
  - Keep non-rates shell header unchanged.

- `web/tests/fixtures/macroFixture.ts:186-267`
  - Extend existing yield-curve fixture so one variant has inline `points` and no `latest`.
  - Add fixtures:
    ```ts
    export function macroFedFundsModuleFixture(): MacroModuleView;
    export function macroAuctionsProxyModuleFixture(): MacroModuleView;
    export function macroAuctionsOfficialModuleFixture(): MacroModuleView;
    export function macroRealRatesModuleFixture(): MacroModuleView;
    export function macroExpectationsProxyModuleFixture(): MacroModuleView;
    export function macroExpectationsOfficialModuleFixture(): MacroModuleView;
    ```
  - Fixtures must use readable labels in primary data and raw gap codes only inside `data_health` records.

- `web/tests/e2e/support/mockApi.ts:1-8` and `web/tests/e2e/support/mockApi.ts:1457-1471`
  - Import the new rates fixtures.
  - Return rates-specific fixture data from `macroModuleData(moduleId)` for the five rates child ids.
  - Keep generic `macroModuleFixture` fallback for other module ids.

- `web/tests/architecture/macroResponsiveHardCut.test.ts:35-51`
  - Add `macroRatesWorkbench.css` to the discovered owner file assertion.
  - Keep the existing breakpoint and letter-spacing contract unchanged.

- `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts:13-57`
  - Keep all five rates routes in the audit route set.
  - Add assertions inside the route loop for rates pages:
    - rates subnav is visible;
    - diagnostics region exists but appears after the primary visual in DOM order;
    - no raw `macro_module_view_v3`, `rates:dgs`, `fomc_probability_feed_missing`, or JSON braces appear in the first viewport text.

### New Frontend Model Files

- Create `web/src/features/macro/model/macroRatesWorkbenchModel.ts`
  - Responsibility: turn `MacroModuleView` into a display-only rates page model without scoring or provider IO.
  - Export:
    ```ts
    export const RATES_MODULE_IDS = [
      "rates/fed-funds",
      "rates/yield-curve",
      "rates/auctions",
      "rates/real-rates",
      "rates/expectations",
    ] as const;

    export type RatesModuleId = (typeof RATES_MODULE_IDS)[number];
    export type RatesReadiness = "ready" | "partial" | "proxy" | "stale" | "missing";

    export type RatesFact = {
      key: string;
      label: string;
      value: string;
      observedAtLabel: string;
      sourceLabel: string | null;
      statusLabel: string | null;
      interpretation: string | null;
    };

    export type RatesGapSummary = {
      key: string;
      label: string;
      severity: "info" | "warning" | "critical";
    };

    export type RatesDecisionGroup = {
      key: "confirmations" | "contradictions" | "watch_triggers" | "invalidations";
      label: string;
      items: Array<{ label: string; detail: string }>;
    };

    export type RatesDetailTable = {
      role: "primary" | "diagnostic";
      table: MacroModuleTable;
    };

    export type RatesWorkbenchView = {
      moduleId: RatesModuleId;
      title: string;
      question: string;
      readiness: RatesReadiness;
      readinessLabel: string;
      marketHeadline: string;
      marketExplanation: string;
      asOfLabel: string;
      facts: RatesFact[];
      missingPrimaryItems: string[];
      proxyNote: string | null;
      chartTitle: string;
      chartNote: string | null;
      decisionGroups: RatesDecisionGroup[];
      detailTables: RatesDetailTable[];
      diagnostics: {
        coverage: RatesGapSummary[];
        sourceMeta: string | null;
        moduleHealthLabel: string;
        globalGapReferenceCount: number;
      };
    };

    export function isRatesModuleId(moduleId: MacroModuleId): moduleId is RatesModuleId;
    export function buildRatesWorkbenchView(module: MacroModuleView, moduleId: RatesModuleId): RatesWorkbenchView;
    export function humanizeRatesConceptKey(conceptKey: string): string;
    export function humanizeRatesGapCode(code: string): string;
    ```
  - Rules:
    - Prefer `module.module_read.headline`, `crypto_read`, and `token_impact` for read text.
    - If official auction or probability feeds are missing, use proxy-mode copy from backend gap labels and the page copy map.
    - Never derive a bullish/bearish rates conclusion from numeric values.
    - Convert concept keys and gap codes to human-readable labels before they reach primary UI.

- Create `web/src/features/macro/model/macroRatesChartModel.ts`
  - Responsibility: build chart-only display models for rates-specific visuals.
  - Export:
    ```ts
    export type RatesCorridorSeriesKey = "target_lower" | "target_upper" | "effr" | "iorb" | "sofr" | "sofr_30d";

    export type RatesCorridorPoint = {
      time: string;
      value: number;
    };

    export type RatesCorridorSeries = {
      key: RatesCorridorSeriesKey;
      label: string;
      unit: string | null;
      latest: number | null;
      points: RatesCorridorPoint[];
    };

    export type RatesCorridorModel = {
      lower: RatesCorridorSeries | null;
      upper: RatesCorridorSeries | null;
      lines: RatesCorridorSeries[];
      missingLabels: string[];
    };

    export function buildRatesCorridorModel(
      chart: MacroModuleChart,
      seriesData?: MacroSeriesData | null,
    ): RatesCorridorModel;
    ```
  - Rules:
    - Use hydrated `/api/macro/series` points when available.
    - Fall back to inline `chart.series[].points`.
    - Fall back to latest tile/chart values for a current-state snapshot.
    - Do not mark the page missing solely because `fed:sofr_30d` is absent.

### New Frontend UI Files

- Create `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`
  - Responsibility: compose the rates workbench hierarchy.
  - Structure:
    ```tsx
    export function MacroRatesModulePage({ module, moduleId, token }: MacroModulePageProps) {
      const ratesModuleId = moduleId as RatesModuleId;
      const view = useMemo(
        () => buildRatesWorkbenchView(module, ratesModuleId),
        [module, ratesModuleId],
      );

      return (
        <MacroPageScaffold label={`${view.title}利率工作台`} pageKind="leaf">
          <MacroRatesSubnav activeModuleId={ratesModuleId} />
          <RatesMarketRead view={view} />
          <RatesFactStrip facts={view.facts} />
          <RatesPrimaryVisual module={module} moduleId={ratesModuleId} token={token} view={view} />
          <RatesDecisionSupport groups={view.decisionGroups} />
          <RatesDetailTables tables={view.detailTables} />
          <RatesDiagnosticsPanel module={module} view={view} />
        </MacroPageScaffold>
      );
    }
    ```

- Create `web/src/features/macro/ui/rates/MacroRatesSubnav.tsx`
  - Responsibility: keep the five rates pages visible as one workbench, including the currently hidden-supported auctions route.
  - Links:
    - `联邦基金` -> `/macro/rates/fed-funds`
    - `收益率曲线` -> `/macro/rates/yield-curve`
    - `国债拍卖` -> `/macro/rates/auctions`
    - `实际利率` -> `/macro/rates/real-rates`
    - `政策预期` -> `/macro/rates/expectations`

- Create `web/src/features/macro/ui/rates/RatesMarketRead.tsx`
  - Responsibility: first product answer.
  - Required visible text patterns:
    - Fed funds: corridor or funding-pressure read, not `partial` alone.
    - Yield curve: available-tenor read plus missing-tenor note.
    - Auctions proxy: `当前为拍卖代理页面`.
    - Expectations proxy: `当前为政策路径代理页面`.

- Create `web/src/features/macro/ui/rates/RatesFactStrip.tsx`
  - Responsibility: dense 3-5 fact tiles with values, as-of/source labels, and status.
  - Use stable dimensions and text overflow rules; do not reuse oversized hero/card typography.

- Create `web/src/features/macro/ui/rates/RatesPrimaryVisual.tsx`
  - Responsibility: route the page to its main visual.
  - Rendering rules:
    - `rates/fed-funds`: use `RatesCorridorChart`.
    - `rates/yield-curve`: use `MacroYieldCurveChart`.
    - `rates/auctions`: show official auction visual/table when official tables exist; otherwise use the proxy chart through `MacroPrimaryChart` and show proxy caveat.
    - `rates/real-rates`: use time-series chart through `MacroPrimaryChart`.
    - `rates/expectations`: show official probability table when official tables exist; otherwise use policy-path proxy chart through `MacroPrimaryChart`.

- Create `web/src/features/macro/ui/rates/RatesCorridorChart.tsx`
  - Responsibility: SVG chart for the Fed target corridor band.
  - Minimum behavior:
    - Draw the target band when both target lower and target upper exist.
    - Draw EFFR, IORB, SOFR, and SOFR 30D lines when available.
    - Render latest-value legend chips.
    - Render a chart note for missing SOFR 30D or FOMC calendar without making the chart empty.
    - Accessible figure name: `联邦基金目标走廊`.

- Create `web/src/features/macro/ui/rates/RatesDecisionSupport.tsx`
  - Responsibility: render confirmations, contradictions, watch triggers, and invalidations as decision groups, not raw evidence buckets.

- Create `web/src/features/macro/ui/rates/RatesDetailTables.tsx`
  - Responsibility: render primary product tables close to the chart; keep availability/proxy tables in diagnostics.
  - Use existing `MacroDataTable`.

- Create `web/src/features/macro/ui/rates/RatesDiagnosticsPanel.tsx`
  - Responsibility: keep provenance/data health inspectable but secondary.
  - Use existing `MacroDataHealthPanel` and `MacroSourceTable`.
  - Region label: `利率数据诊断`.
  - The primary UI must not show projection ids; this panel may show source state and projection health labels.

- Create `web/src/features/macro/ui/rates/macroRatesWorkbench.css`
  - Responsibility: rates-only layout and visual styling under the `.macro-rates-*` namespace.
  - CSS constraints:
    - Put all rules inside `@layer app.features`.
    - Use only allowed media queries:
      `@media (max-width: 767px)`,
      `@media (min-width: 768px) and (max-width: 1279px)`,
      `@media (min-width: 1280px)`.
    - Use `letter-spacing: 0` where letter spacing is set.
    - No `overflow-wrap: anywhere`, no `word-break: break-all`, no retired selectors.
    - No nested card styling; panels sit directly in `MacroPageScaffold`.

### New Tests

- Create `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`
  - Assert `isRatesModuleId` accepts the five rates ids and rejects non-rates ids.
  - Assert auction proxy and expectations proxy copy uses human-readable labels.
  - Assert raw concept keys and raw gap codes are not returned in `marketHeadline`, `marketExplanation`, `facts`, `missingPrimaryItems`, or `chartNote`.
  - Assert official auction/probability fixture tables are selected as primary details when present.

- Create `web/tests/unit/features/macro/model/macroRatesChartModel.test.ts`
  - Assert corridor model maps target lower/upper, EFFR, IORB, SOFR, and SOFR 30D from chart concepts.
  - Assert missing SOFR 30D appears in `missingLabels` but target band and EFFR still renderable.

- Create `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`
  - Assert five rates routes render in workbench order:
    `利率页导航`, `市场解读`, `关键事实`, primary visual, `决策支持`, product details, `利率数据诊断`.
  - Assert diagnostics comes after primary visual.
  - Assert proxy pages are not empty.
  - Assert primary UI does not expose raw concept keys, raw gap codes, `macro_module_view_v3`, source snapshot ids, or JSON blobs.

## Task Checklist

### Task 1: Create Worktree And Baseline

**Files:**
- Read: `docs/FRONTEND.md`
- Read: `docs/TESTING.md`
- Read: `docs/superpowers/specs/active/2026-06-01-rates-workbench-clarity-redesign.md`

- [ ] **Step 1: Create the worktree**
  ```bash
  git worktree add .worktrees/rates-workbench-clarity-redesign -b codex/rates-workbench-clarity-redesign main
  cd .worktrees/rates-workbench-clarity-redesign
  ```
  Expected: branch `codex/rates-workbench-clarity-redesign` exists in the new worktree.

- [ ] **Step 2: Verify clean isolation**
  ```bash
  git branch --show-current
  git status --short
  ```
  Expected: branch prints `codex/rates-workbench-clarity-redesign`; status is empty except for files intentionally copied into the worktree.

- [ ] **Step 3: Run focused baseline**
  ```bash
  cd web
  npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx
  npm run test:architecture
  ```
  Expected: all focused baseline tests pass. Any unrelated failure is copied into the verification artifact before edits continue.

### Task 2: Fix Yield-Curve Inline Point Rendering

**Files:**
- Modify: `web/src/features/macro/model/macroChartModel.ts:138-158`
- Test: `web/tests/unit/features/macro/model/macroChartModel.test.ts:135-156`
- Test: `web/tests/component/features/macro/MacroCharts.test.tsx:139-162`
- Test: `web/tests/component/features/macro/MacroModulePages.test.tsx:183-205`

- [ ] **Step 1: Write the failing unit test**
  Add this test beside the existing yield-curve tenor-order test:
  ```ts
  it("uses the latest inline point when a yield curve series omits latest", () => {
    const chart: MacroModuleChart = {
      id: "yield_curve",
      series: [
        {
          concept_key: "rates:dgs10",
          label: "10Y",
          unit: "percent",
          points: [
            { observed_at: "2026-05-19", value: 4.1 },
            { observed_at: "2026-05-20", value: "4.2" },
          ],
        },
        {
          concept_key: "rates:dgs2",
          label: "2Y",
          unit: "percent",
          points: [{ observed_at: "2026-05-20", value: 3.8 }],
        },
        {
          concept_key: "rates:10y2y",
          label: "10Y-2Y",
          unit: "percent",
          points: [{ observed_at: "2026-05-20", value: 0.4 }],
        },
      ],
    };

    const model = buildMacroYieldCurveModel(chart);

    expect(model.points.map((point) => point.conceptKey)).toEqual(["rates:dgs2", "rates:dgs10"]);
    expect(model.points.map((point) => point.value)).toEqual([3.8, 4.2]);
  });
  ```

- [ ] **Step 2: Run the failing test**
  ```bash
  cd web
  npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts
  ```
  Expected before implementation: the new test fails because `buildMacroYieldCurveModel` reads only `series.latest`.

- [ ] **Step 3: Implement the model fallback**
  Change the value extraction in `buildMacroYieldCurveModel`:
  ```ts
  const value = latestSeriesNumericValue(series);
  ```
  Add helpers in the same file:
  ```ts
  function latestSeriesNumericValue(series: MacroSemanticRecord): number | null {
    return (
      numericValue(series.latest) ??
      numericValue(series.latest_value) ??
      numericValue(series.value) ??
      latestInlinePointValue(series)
    );
  }

  function latestInlinePointValue(series: MacroSemanticRecord): number | null {
    const points = normalizeSeriesPoints(inlineSeriesPoints(series));
    return points.at(-1)?.value ?? null;
  }
  ```

- [ ] **Step 4: Add component regression coverage**
  Add a `MacroYieldCurveChart` component test whose chart has no `latest` fields and does have inline `points`. Expected visible point labels include `2Y3.8%` and `10Y4.2%`.

- [ ] **Step 5: Run focused tests**
  ```bash
  cd web
  npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroModulePages.test.tsx
  ```
  Expected: all pass; yield curve still does not request `/api/macro/series`.

- [ ] **Step 6: Commit**
  ```bash
  git add web/src/features/macro/model/macroChartModel.ts web/tests/unit/features/macro/model/macroChartModel.test.ts web/tests/component/features/macro/MacroCharts.test.tsx
  git commit -m "fix: render yield curves from inline points"
  ```

### Task 3: Add Rates Workbench View Models

**Files:**
- Create: `web/src/features/macro/model/macroRatesWorkbenchModel.ts`
- Create: `web/src/features/macro/model/macroRatesChartModel.ts`
- Test: `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`
- Test: `web/tests/unit/features/macro/model/macroRatesChartModel.test.ts`
- Modify: `web/tests/fixtures/macroFixture.ts:186-267`

- [ ] **Step 1: Add rates fixtures first**
  Add fixtures for Fed funds, auction proxy/official, real rates, and expectations proxy/official. Use these readable labels:
  - Fed funds facts: `目标上限`, `目标下限`, `EFFR`, `IORB`, `SOFR`.
  - Yield curve facts: `2Y`, `5Y`, `10Y`, `30Y`, `10Y-2Y`, `10Y-3M`.
  - Auction proxy facts: `2Y`, `10Y`, `30Y`, `10Y-2Y`.
  - Real rates facts: `10Y real`, `10Y breakeven`, `5y5y forward`.
  - Expectations proxy facts: `目标上限`, `目标下限`, `2Y`, `1Y`, `3M`.

- [ ] **Step 2: Write rates workbench model tests**
  Required assertions:
  ```ts
  expect(isRatesModuleId("rates/fed-funds")).toBe(true);
  expect(isRatesModuleId("assets/equities")).toBe(false);

  const auctions = buildRatesWorkbenchView(
    macroAuctionsProxyModuleFixture(),
    "rates/auctions",
  );
  expect(auctions.readiness).toBe("proxy");
  expect(auctions.marketHeadline).toContain("当前为拍卖代理页面");
  expect(auctions.marketHeadline).not.toContain("treasury_auction_results_missing");
  expect(auctions.marketExplanation).not.toContain("rates:dgs10");

  const expectations = buildRatesWorkbenchView(
    macroExpectationsProxyModuleFixture(),
    "rates/expectations",
  );
  expect(expectations.readiness).toBe("proxy");
  expect(expectations.marketHeadline).toContain("当前为政策路径代理页面");
  expect(expectations.marketHeadline).not.toContain("fomc_probability_feed_missing");
  ```

- [ ] **Step 3: Write official-data precedence tests**
  ```ts
  const officialAuctions = buildRatesWorkbenchView(
    macroAuctionsOfficialModuleFixture(),
    "rates/auctions",
  );
  expect(officialAuctions.readiness).toBe("ready");
  expect(officialAuctions.detailTables[0]?.table.title).toContain("未来拍卖");

  const officialExpectations = buildRatesWorkbenchView(
    macroExpectationsOfficialModuleFixture(),
    "rates/expectations",
  );
  expect(officialExpectations.readiness).toBe("ready");
  expect(officialExpectations.detailTables[0]?.table.title).toContain("会议概率");
  ```

- [ ] **Step 4: Implement `macroRatesWorkbenchModel.ts`**
  Implement the exported types and functions from the file map. The page copy map must include:
  ```ts
  const RATES_PAGE_COPY: Record<RatesModuleId, { title: string; question: string; proxyHeadline?: string }> = {
    "rates/fed-funds": {
      title: "联邦基金与走廊",
      question: "政策走廊是否稳定，隔夜融资是否溢出目标区间？",
    },
    "rates/yield-curve": {
      title: "收益率曲线",
      question: "曲线是在交易衰退压力，还是期限溢价？",
    },
    "rates/auctions": {
      title: "国债拍卖",
      question: "拍卖供给压力是否体现在曲线和长端收益率上？",
      proxyHeadline: "当前为拍卖代理页面：官方拍卖日历和结果尚未入库。",
    },
    "rates/real-rates": {
      title: "实际利率",
      question: "实际利率是在压制估值，还是通胀补偿主导？",
    },
    "rates/expectations": {
      title: "政策预期",
      question: "市场是否在重新定价降息、维持或加息路径？",
      proxyHeadline: "当前为政策路径代理页面，不能生成正式降息概率。",
    },
  };
  ```

- [ ] **Step 5: Write corridor chart model tests**
  ```ts
  const model = buildRatesCorridorModel(
    macroFedFundsModuleFixture().primary_chart,
    macroSeriesFixture(["fed:target_lower", "fed:target_upper", "fed:effr", "fed:iorb", "liquidity:sofr"]),
  );
  expect(model.lower?.label).toBe("目标下限");
  expect(model.upper?.label).toBe("目标上限");
  expect(model.lines.map((series) => series.label)).toEqual(["EFFR", "IORB", "SOFR"]);
  expect(model.missingLabels).toContain("SOFR 30D");
  ```

- [ ] **Step 6: Implement `macroRatesChartModel.ts`**
  Use concept mapping:
  ```ts
  const CORRIDOR_SERIES_BY_CONCEPT: Record<string, RatesCorridorSeriesKey> = {
    "fed:target_lower": "target_lower",
    "fed:target_upper": "target_upper",
    "fed:effr": "effr",
    "fed:iorb": "iorb",
    "liquidity:sofr": "sofr",
    "fed:sofr_30d": "sofr_30d",
  };
  ```
  The helper must accept both hydrated series payloads and inline chart series.

- [ ] **Step 7: Run model tests**
  ```bash
  cd web
  npm test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesChartModel.test.ts
  ```
  Expected: all pass.

- [ ] **Step 8: Commit**
  ```bash
  git add web/src/features/macro/model/macroRatesWorkbenchModel.ts web/src/features/macro/model/macroRatesChartModel.ts web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts web/tests/unit/features/macro/model/macroRatesChartModel.test.ts web/tests/fixtures/macroFixture.ts
  git commit -m "feat: add rates workbench view models"
  ```

### Task 4: Add Rates Workbench UI And Route Branch

**Files:**
- Create: `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`
- Create: `web/src/features/macro/ui/rates/MacroRatesSubnav.tsx`
- Create: `web/src/features/macro/ui/rates/RatesMarketRead.tsx`
- Create: `web/src/features/macro/ui/rates/RatesFactStrip.tsx`
- Create: `web/src/features/macro/ui/rates/RatesPrimaryVisual.tsx`
- Create: `web/src/features/macro/ui/rates/RatesCorridorChart.tsx`
- Create: `web/src/features/macro/ui/rates/RatesDecisionSupport.tsx`
- Create: `web/src/features/macro/ui/rates/RatesDetailTables.tsx`
- Create: `web/src/features/macro/ui/rates/RatesDiagnosticsPanel.tsx`
- Create: `web/src/features/macro/ui/rates/macroRatesWorkbench.css`
- Modify: `web/src/features/macro/ui/pages/MacroMarketBoard.tsx:38-96`
- Modify: `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx:6-20`
- Modify: `web/src/features/macro/MacroWorkbenchRoute.tsx:93-110`
- Test: `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`
- Test: `web/tests/component/features/macro/MacroModulePages.test.tsx:183-205`

- [ ] **Step 1: Export reusable chart renderer**
  In `MacroMarketBoard.tsx`, rename:
  ```tsx
  function PrimaryChart({
    chart,
    moduleId,
    seriesData,
    seriesLoading,
  }: {
    chart: MacroModuleChart;
    moduleId: MacroModuleId;
    seriesData?: MacroSeriesData | null;
    seriesLoading?: boolean;
  }) {
  ```
  to:
  ```tsx
  export function MacroPrimaryChart({
    chart,
    moduleId,
    seriesData,
    seriesLoading,
  }: {
    chart: MacroModuleChart;
    moduleId: MacroModuleId;
    seriesData?: MacroSeriesData | null;
    seriesLoading?: boolean;
  }) {
  ```
  and update the internal call to:
  ```tsx
  <MacroPrimaryChart chart={chart} moduleId={moduleId} seriesData={seriesData} seriesLoading={seriesLoading} />
  ```

- [ ] **Step 2: Write component order test**
  For each fixture route, assert DOM order:
  ```ts
  expectRegionsInOrder([
    "利率页导航",
    "市场解读",
    "关键事实",
    "主要图表",
    "决策支持",
    "利率明细",
    "利率数据诊断",
  ]);
  ```

- [ ] **Step 3: Write proxy readability tests**
  ```ts
  renderRatesPage(macroAuctionsProxyModuleFixture(), "rates/auctions");
  expect(screen.getByText(/当前为拍卖代理页面/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "主要图表" })).not.toHaveTextContent("暂无");
  expect(screen.getByRole("region", { name: "市场解读" })).not.toHaveTextContent("treasury_auction");

  renderRatesPage(macroExpectationsProxyModuleFixture(), "rates/expectations");
  expect(screen.getByText(/当前为政策路径代理页面/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "市场解读" })).not.toHaveTextContent("fomc_probability_feed_missing");
  ```

- [ ] **Step 4: Implement rates route branch**
  In `MacroModulePageRenderer.tsx`:
  ```tsx
  if (isRatesModuleId(props.moduleId)) {
    return <MacroRatesModulePage {...props} moduleId={props.moduleId} />;
  }
  ```
  This branch must come after overview handling and before `MacroLeafModulePage`.

- [ ] **Step 5: Implement shell header adjustment**
  In `macroModuleHeader`, compute:
  ```ts
  const ratesPage = isRatesModuleId(moduleId);
  ```
  Use status items:
  ```ts
  statusItems: [
    { label: ratesPage ? "数据" : "状态", value: macroStatusLabel(module) },
    { label: "截至", value: macroAsOfLabel(module) },
    ...(ratesPage ? [] : [{ label: "版本", value: module.snapshot.projection_version ?? "暂无版本" }]),
  ],
  ```

- [ ] **Step 6: Implement rates components**
  Use the composition from `MacroRatesModulePage.tsx` in the file map. Keep every component focused:
  - `RatesMarketRead` receives only `view`.
  - `RatesFactStrip` receives only `facts`.
  - `RatesPrimaryVisual` receives `module`, `moduleId`, `token`, and `view`.
  - `RatesDiagnosticsPanel` receives `module` and `view`.

- [ ] **Step 7: Implement Fed funds corridor chart**
  `RatesCorridorChart` should render:
  ```tsx
  <figure className="macro-rates-corridor-chart" aria-label="联邦基金目标走廊">
    <figcaption>联邦基金目标走廊</figcaption>
    <svg role="img" aria-label="目标区间、EFFR、IORB 与 SOFR">
      <polygon data-testid="rates-corridor-band" />
      <polyline data-testid="rates-corridor-line-effr" />
    </svg>
    <div className="macro-rates-chart-legend" />
  </figure>
  ```
  The real implementation must compute SVG coordinates from the model; the test only relies on accessible labels and `data-testid` hooks.

- [ ] **Step 8: Implement CSS**
  `macroRatesWorkbench.css` must define these layout classes:
  - `.macro-rates-subnav`
  - `.macro-rates-market-read`
  - `.macro-rates-fact-strip`
  - `.macro-rates-primary-visual`
  - `.macro-rates-decision-support`
  - `.macro-rates-detail-tables`
  - `.macro-rates-diagnostics`
  - `.macro-rates-corridor-chart`
  - `.macro-rates-chart-legend`
  Use desktop two-column composition for market read/facts and full-width primary visual.

- [ ] **Step 9: Run focused component tests**
  ```bash
  cd web
  npm test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx
  ```
  Expected: rates pages render through `MacroRatesModulePage`; non-rates leaf tests still render through `MacroLeafModulePage`.

- [ ] **Step 10: Commit**
  ```bash
  git add web/src/features/macro/ui/rates web/src/features/macro/ui/pages/MacroMarketBoard.tsx web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx web/src/features/macro/MacroWorkbenchRoute.tsx web/tests/component/features/macro/MacroRatesWorkbench.test.tsx web/tests/component/features/macro/MacroModulePages.test.tsx
  git commit -m "feat: render rates modules as a workbench"
  ```

### Task 5: Wire E2E Fixtures And Responsive Harness

**Files:**
- Modify: `web/tests/e2e/support/mockApi.ts:1-8`
- Modify: `web/tests/e2e/support/mockApi.ts:1457-1471`
- Modify: `web/tests/architecture/macroResponsiveHardCut.test.ts:35-51`
- Modify: `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts:13-104`

- [ ] **Step 1: Return rates fixtures from mock API**
  Add a `switch` in `macroModuleData`:
  ```ts
  switch (moduleId) {
    case "rates/fed-funds":
      return macroFedFundsModuleFixture();
    case "rates/yield-curve":
      return macroYieldCurveModuleFixture();
    case "rates/auctions":
      return macroAuctionsProxyModuleFixture();
    case "rates/real-rates":
      return macroRealRatesModuleFixture();
    case "rates/expectations":
      return macroExpectationsProxyModuleFixture();
    default:
      break;
  }
  ```

- [ ] **Step 2: Update CSS owner test**
  Add `"macroRatesWorkbench.css"` to the `arrayContaining` assertion in `macroResponsiveHardCut.test.ts`.

- [ ] **Step 3: Add e2e product hierarchy assertions**
  In `macro-responsive-audit.spec.ts`, for routes beginning with `/macro/rates/`, assert:
  ```ts
  await expect(page.getByLabel("利率页导航")).toBeVisible();
  await expect(page.getByLabel("市场解读")).toBeVisible();
  await expect(page.getByLabel("主要图表")).toBeVisible();
  await expect(page.getByLabel("利率数据诊断")).toBeVisible();
  ```

- [ ] **Step 4: Add e2e raw-code guard**
  For rates routes, read the first viewport text and assert it does not match:
  ```ts
  /macro_module_view_v3|source_snapshot_id|rates:dgs|fed:effr|fomc_probability_feed_missing|treasury_auction_results_missing|\{|\}/
  ```
  Limit the check to visible text above diagnostics so source/provenance internals do not create false positives.

- [ ] **Step 5: Run architecture and e2e audits**
  ```bash
  cd web
  npm run test:architecture
  npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts
  ```
  Expected: no body overflow, no text overlap, no unhandled API requests, no retired CSS selectors.

- [ ] **Step 6: Commit**
  ```bash
  git add web/tests/e2e/support/mockApi.ts web/tests/architecture/macroResponsiveHardCut.test.ts web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts
  git commit -m "test: cover rates workbench responsive behavior"
  ```

### Task 6: Full Verification And Documentation Artifact

**Files:**
- Create: `docs/superpowers/plans/active/2026-06-01-rates-workbench-clarity-redesign-verification.md`
- Modify only if needed: `docs/TECH_DEBT.md`

- [ ] **Step 1: Run frontend focused gates**
  ```bash
  cd web
  npm run lint
  npm run test:architecture
  npm run typecheck
  npm test -- --run
  npm run build
  ```
  Expected: all exit 0.

- [ ] **Step 2: Run full project gate**
  ```bash
  make check-all
  ```
  Expected: exits 0. Copy full output into the verification artifact as required by `docs/WORKFLOW.md`.

- [ ] **Step 3: Run real-data smoke**
  ```bash
  uv run parallax config
  uv run parallax db health
  uv run parallax macro status
  ```
  Expected: commands complete; verification records redacted config paths and rates readiness, not secret values.

- [ ] **Step 4: Manual browser smoke**
  With the local server running, open:
  - `http://localhost:8765/macro/rates/fed-funds`
  - `http://localhost:8765/macro/rates/yield-curve`
  - `http://localhost:8765/macro/rates/auctions`
  - `http://localhost:8765/macro/rates/real-rates`
  - `http://localhost:8765/macro/rates/expectations`

  Record in the verification artifact:
  - Which pages are fact-backed.
  - Which pages are proxy-backed.
  - Whether yield curve draws available tenors.
  - Whether diagnostics appear after the primary visual.
  - Whether mobile/tablet views avoid horizontal body overflow.

- [ ] **Step 5: Review diff against plan**
  ```bash
  git diff --stat main...HEAD
  git diff main...HEAD -- web/src/features/macro web/tests docs/superpowers
  ```
  Expected: all touched files are listed in this plan or the verification artifact explains the additional file.

- [ ] **Step 6: Commit verification**
  ```bash
  git add docs/superpowers/plans/active/2026-06-01-rates-workbench-clarity-redesign-verification.md docs/TECH_DEBT.md
  git commit -m "docs: record rates workbench verification"
  ```
  Add `docs/TECH_DEBT.md` only when a real follow-up risk is recorded.

## PR Breakdown

1. **PR 1 — Yield Curve Contract Fix**
   - Owns Task 2.
   - Mergeable independently.
   - User-visible result: `/macro/rates/yield-curve` can draw available tenor points when backend chart series have inline `points` but no `latest`.

2. **PR 2 — Rates Workbench Models And UI**
   - Owns Tasks 3 and 4.
   - Depends on PR 1 only for the yield-curve fix.
   - User-visible result: all five rates routes use workbench hierarchy and proxy/partial language.

3. **PR 3 — Responsive Harness And Verification**
   - Owns Tasks 5 and 6.
   - Depends on PR 2.
   - User-visible result: rates routes are covered by component, architecture, e2e, real-data smoke, and full verification gates.

## Rollout Order

1. Merge PR 1 and deploy normally; no schema or worker changes.
2. Merge PR 2 behind the existing Macro route surface; no feature flag is required because it only changes rates-page rendering.
3. Merge PR 3 after `make check-all` and manual rates smoke are recorded.
4. After deploy, canary the five rates routes and compare screenshots against local verification.

## Rollback

- Revert PR 3 to remove stricter tests or verification-only changes if needed; no production behavior changes.
- Revert PR 2 to return rates modules to `MacroLeafModulePage`; data contracts remain unchanged.
- Revert PR 1 to restore old yield-curve extraction behavior only if the fallback creates incorrect tenor values. This is unlikely because it accepts the same normalized inline point shape already used by time-series charts.
- No data rollback, migration rollback, or worker restart is needed.

## Acceptance Test Commands

- AC1, AC10, AC12, AC13:
  `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts`
- AC2, AC5, AC8, AC11:
  `cd web && npm test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx`
- AC3:
  `cd web && npm test -- --run tests/unit/features/macro/model/macroRatesChartModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx`
- AC4:
  `cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroCharts.test.tsx`
- AC6:
  `cd web && npm test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`
  Expected assertion: official auction fixture selects future auction/recent result tables before proxy yield tables.
- AC7:
  `cd web && npm test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx`
  Expected assertion: real-rates fixture shows real-rate interpretation and facts before diagnostics.
- AC9:
  `cd web && npm test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`
  Expected assertion: official expectations fixture selects meeting probability and implied path surfaces before proxy tables.
- AC14:
  Manual smoke recorded in `docs/superpowers/plans/active/2026-06-01-rates-workbench-clarity-redesign-verification.md`.
- Completion gate:
  `make check-all`

## Verification Artifact

Create `docs/superpowers/plans/active/2026-06-01-rates-workbench-clarity-redesign-verification.md` before declaring the implementation complete. It must include:

- Spec coverage summary for AC1-AC14.
- Full `make check-all` output.
- Coverage section.
- Skipped tests section.
- E2E golden path section.
- Other commands run.
- Manual rates smoke notes for all five child routes.
- Remaining risks and follow-ups, with `docs/TECH_DEBT.md` updated when the follow-up is non-trivial.
