# Macro Terminal UI Navigation Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Macro Terminal UI information architecture so navigation lives in the shell/sidebar, module pages answer module-local questions, and global macro state no longer pollutes every child page.

**Architecture:** This is a hard-cut contract and UI rewrite for the existing macro surface. Backend module views move from `macro_module_view_v2` to `macro_module_view_v3` with separated read/evidence/transmission/data-health semantics; frontend macro routes derive from one navigation tree; the shadcn `AppSidebar` becomes the only full macro navigation surface; macro pages are rebuilt as overview, index, and leaf renderers.

**Tech Stack:** Python 3.12, FastAPI, deterministic macro read models, React 19, React Router 6.30, React Query, TypeScript, shadcn sidebar, lucide-react, Vitest, React Testing Library, Playwright, CSS cascade layers.

---

**Status**: Draft
**Date**: 2026-05-26
**Owning spec**: `docs/superpowers/specs/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-cn.md`
**Worktree**: `.worktrees/macro-terminal-ui-navigation-hard-cut/`
**Branch**: `codex/macro-terminal-ui-navigation-hard-cut`
**Mode**: Single implementation plan. Do not split into compatibility phases.

## Pre-flight

- [ ] Confirm the spec is approved for implementation.
- [ ] Create the worktree:

```bash
git worktree add .worktrees/macro-terminal-ui-navigation-hard-cut -b codex/macro-terminal-ui-navigation-hard-cut main
cd .worktrees/macro-terminal-ui-navigation-hard-cut
```

- [ ] Verify the worktree:

```bash
git worktree list
git status --short
git branch --show-current
```

Expected: current branch is `codex/macro-terminal-ui-navigation-hard-cut`; unrelated changes in the main checkout are not present unless they were already on `main`.

- [ ] Read the required docs in the worktree:

```bash
sed -n '1,260p' docs/FRONTEND.md
sed -n '1,240p' docs/WORKFLOW.md
sed -n '1,240p' src/parallax/domains/macro_intel/ARCHITECTURE.md
sed -n '1,380p' timsun-assets-snapshot.md
```

- [ ] Run baseline targeted tests and record known failures:

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
cd web && npm test -- --run tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
```

Expected: Python should pass or expose unrelated baseline failures. Current frontend route/page tests may fail on old names such as `当前解读` and `宏观传导图`; record exact output before editing.

## File-level Edits

### Backend macro contract

- Modify `src/parallax/domains/macro_intel/_constants.py`
  - Change `MACRO_MODULE_VIEW_VERSION` from `macro_module_view_v2` to `macro_module_view_v3`.
  - Do not keep a v2 constant for fallback rendering.

- Modify `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
  - Keep existing module ids and route paths.
  - Add data-only board definitions for index pages, starting with `/macro/assets`.
  - Add helper functions that return concept groups without importing frontend code.
  - Suggested dataclass:

```python
@dataclass(frozen=True)
class MacroSectionBoardSpec:
    board_id: str
    title: str
    route_path: str
    concept_keys: tuple[str, ...]
```

  - Add `section_board_specs: tuple[MacroSectionBoardSpec, ...] = ()` to `MacroModuleConfig`.
  - For `assets`, add boards:
    - `equities`: `/macro/assets/equities`, concepts `asset:spx`, `asset:spy`, `asset:qqq`, `asset:iwm`
    - `bonds`: `/macro/assets/bonds`, concepts `asset:tlt`, `asset:hyg`, `asset:lqd`
    - `commodities`: `/macro/assets/commodities`, concepts `commodity:wti`, `asset:gld`, `asset:uso`
    - `fx`: `/macro/assets/fx`, concepts `fx:dxy`, `fx:broad_dollar`
    - `crypto`: `/macro/assets/crypto`, concepts `crypto:btc`, `crypto:eth`
    - `crypto_derivatives`: `/macro/assets/crypto-derivatives`, concepts `crypto:btc`, `crypto:eth`

- Modify `src/parallax/domains/macro_intel/services/macro_module_views.py`
  - Replace `_ordered_payload(...)` fields:

```python
def _ordered_payload(
    *,
    snapshot: dict[str, Any],
    tiles: list[dict[str, Any]],
    primary_chart: dict[str, Any],
    tables: list[dict[str, Any]],
    module_read: dict[str, Any],
    module_evidence: dict[str, Any],
    transmission: list[dict[str, Any]],
    data_health: dict[str, Any],
    provenance: dict[str, Any],
    related_routes: list[dict[str, str]],
    section_boards: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "snapshot": snapshot,
        "tiles": tiles,
        "primary_chart": primary_chart,
        "tables": tables,
        "module_read": module_read,
        "module_evidence": module_evidence,
        "transmission": transmission,
        "data_health": data_health,
        "provenance": provenance,
        "related_routes": related_routes,
        "section_boards": section_boards,
    }
```

  - Remove old `read`, `evidence`, and top-level `data_gaps` from the module view payload.
  - Replace `_read` with `_module_read(config, feature_map, primary_chart, data_health, snapshot)`.
  - Replace `_evidence` with `_module_evidence(config, feature_map, primary_chart, data_health, cex_source)`.
  - Replace `_data_gaps` with `_data_health(config, snapshot, feature_map, concept_keys, primary_chart, cex_source)`.
  - Add `_transmission(config, snapshot, feature_map, data_health)`.
  - Add `_section_boards(config, feature_map)`.
  - For `config.module_id == "overview"`, allow global scenario and global data gaps in `module_read`, `module_evidence`, `transmission`, and `data_health.global_gaps`.
  - For every non-overview module, do not read `snapshot["scenario_json"]` in `_module_read` or `_module_evidence`.
  - For every non-overview module, put global snapshot gaps only in `data_health.global_gaps` and mark them as reference-only, not module blockers.

- Modify `src/parallax/app/surfaces/api/routes_macro.py`
  - Keep `/api/macro/modules/{module_id}` as the module endpoint.
  - No fallback path for v2.
  - No frontend-specific navigation endpoint in this plan.

- Modify `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
  - Update expected module view version to `macro_module_view_v3`.

- Modify `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
  - Add tests for `assets` section board specs and route paths.

- Modify `tests/unit/domains/macro_intel/test_macro_module_views.py`
  - Replace v2 payload assertions with v3 assertions.
  - Add tests proving:
    - non-overview reads do not reuse global scenario regime;
    - non-overview evidence does not reuse global scenario confirmations;
    - non-overview module blockers exclude unrelated global snapshot gaps;
    - overview still surfaces global data health;
    - `/macro/assets` returns section boards.

- Modify `tests/unit/test_api_macro_contract.py`
  - Update expected projection version and payload keys.
  - Assert old keys `read`, `evidence`, and `data_gaps` are absent from module payloads.

### Frontend macro route and types

- Modify `web/src/lib/types/frontend-contracts.ts`
  - Replace `MacroModuleView.read`, `MacroModuleView.evidence`, and `MacroModuleView.data_gaps`.
  - Add:

```ts
export type MacroDataHealth = {
  summary_status?: string | null;
  summary_label?: string | null;
  module_gaps: MacroSemanticRecord[];
  chart_gaps: MacroSemanticRecord[];
  global_gaps: MacroSemanticRecord[];
  future_integration_gaps: MacroSemanticRecord[];
};

export type MacroTransmissionNode = {
  label?: string | null;
  value?: unknown;
  kind?: string | null;
  status?: string | null;
  status_label?: string | null;
};

export type MacroSectionBoard = {
  id: string;
  title: string;
  href: string;
  rows: MacroSemanticRecord[];
  status?: string | null;
  status_label?: string | null;
};
```

  - Update `MacroModuleView` to include `module_read`, `module_evidence`, `transmission`, `data_health`, and `section_boards`.

- Create `web/src/features/macro/model/macroNavigationTree.ts`
  - Export a single frontend macro navigation tree used by route parsing, breadcrumbs, and `AppSidebar`.
  - Include all supported macro module ids plus the correlation route.
  - Expose:

```ts
export const MACRO_NAVIGATION_TREE: MacroNavigationNode[] = [
  { id: "macro.overview", label: "总览", href: "/macro", moduleId: "overview", children: [] },
  {
    id: "macro.assets",
    label: "大类资产",
    href: "/macro/assets",
    moduleId: "assets",
    children: [
      { id: "macro.assets.equities", label: "美股", href: "/macro/assets/equities", moduleId: "assets/equities", children: [] },
      { id: "macro.assets.bonds", label: "债券", href: "/macro/assets/bonds", moduleId: "assets/bonds", children: [] },
      { id: "macro.assets.commodities", label: "商品", href: "/macro/assets/commodities", moduleId: "assets/commodities", children: [] },
      { id: "macro.assets.fx", label: "外汇", href: "/macro/assets/fx", moduleId: "assets/fx", children: [] },
      { id: "macro.assets.crypto", label: "加密资产", href: "/macro/assets/crypto", moduleId: "assets/crypto", children: [] },
      { id: "macro.assets.cryptoDerivatives", label: "加密衍生品", href: "/macro/assets/crypto-derivatives", moduleId: "assets/crypto-derivatives", children: [] },
      { id: "macro.assets.correlation", label: "相关性", href: "/macro/assets/correlation", moduleId: "assets/correlation", children: [] },
    ],
  },
  {
    id: "macro.rates",
    label: "利率",
    href: "/macro/rates",
    moduleId: "rates",
    children: [
      { id: "macro.rates.fedFunds", label: "联邦基金", href: "/macro/rates/fed-funds", moduleId: "rates/fed-funds", children: [] },
      { id: "macro.rates.yieldCurve", label: "收益率曲线", href: "/macro/rates/yield-curve", moduleId: "rates/yield-curve", children: [] },
      { id: "macro.rates.auctions", label: "拍卖", href: "/macro/rates/auctions", moduleId: "rates/auctions", children: [] },
      { id: "macro.rates.realRates", label: "实际利率", href: "/macro/rates/real-rates", moduleId: "rates/real-rates", children: [] },
      { id: "macro.rates.expectations", label: "政策预期", href: "/macro/rates/expectations", moduleId: "rates/expectations", children: [] },
    ],
  },
  {
    id: "macro.fed",
    label: "美联储",
    href: "/macro/fed",
    moduleId: "fed",
    children: [
      { id: "macro.fed.statements", label: "FOMC 声明", href: "/macro/fed/statements", moduleId: "fed/statements", children: [] },
      { id: "macro.fed.speeches", label: "美联储讲话", href: "/macro/fed/speeches", moduleId: "fed/speeches", children: [] },
    ],
  },
  {
    id: "macro.liquidity",
    label: "流动性",
    href: "/macro/liquidity",
    moduleId: "liquidity",
    children: [
      { id: "macro.liquidity.transmissionChain", label: "传导链", href: "/macro/liquidity/transmission-chain", moduleId: "liquidity/transmission-chain", children: [] },
      { id: "macro.liquidity.fedBalanceSheet", label: "资产负债表", href: "/macro/liquidity/fed-balance-sheet", moduleId: "liquidity/fed-balance-sheet", children: [] },
      { id: "macro.liquidity.operations", label: "公开市场操作", href: "/macro/liquidity/operations", moduleId: "liquidity/operations", children: [] },
      { id: "macro.liquidity.rrpTga", label: "RRP / TGA", href: "/macro/liquidity/rrp-tga", moduleId: "liquidity/rrp-tga", children: [] },
      { id: "macro.liquidity.reserves", label: "银行准备金", href: "/macro/liquidity/reserves", moduleId: "liquidity/reserves", children: [] },
      { id: "macro.liquidity.globalDollar", label: "全球美元", href: "/macro/liquidity/global-dollar", moduleId: "liquidity/global-dollar", children: [] },
      { id: "macro.liquidity.subsurface", label: "资金面暗流", href: "/macro/liquidity/subsurface", moduleId: "liquidity/subsurface", children: [] },
    ],
  },
  {
    id: "macro.economy",
    label: "经济数据",
    href: "/macro/economy",
    moduleId: "economy",
    children: [
      { id: "macro.economy.gdp", label: "GDP", href: "/macro/economy/gdp", moduleId: "economy/gdp", children: [] },
      { id: "macro.economy.employment", label: "就业", href: "/macro/economy/employment", moduleId: "economy/employment", children: [] },
      { id: "macro.economy.inflation", label: "通胀", href: "/macro/economy/inflation", moduleId: "economy/inflation", children: [] },
      { id: "macro.economy.consumer", label: "消费", href: "/macro/economy/consumer", moduleId: "economy/consumer", children: [] },
    ],
  },
  {
    id: "macro.volatility",
    label: "波动率",
    href: "/macro/volatility",
    moduleId: "volatility",
    children: [
      { id: "macro.volatility.dashboard", label: "Dashboard", href: "/macro/volatility/dashboard", moduleId: "volatility/dashboard", children: [] },
      { id: "macro.volatility.vix", label: "VIX", href: "/macro/volatility/vix", moduleId: "volatility/vix", children: [] },
    ],
  },
  {
    id: "macro.credit",
    label: "信用",
    href: "/macro/credit",
    moduleId: "credit",
    children: [
      { id: "macro.credit.cds", label: "CDS 代理", href: "/macro/credit/cds", moduleId: "credit/cds", children: [] },
      { id: "macro.credit.stress", label: "压力", href: "/macro/credit/stress", moduleId: "credit/stress", children: [] },
    ],
  },
];
export const MACRO_MODULE_ROUTES: MacroModuleRoute[] = flattenMacroNavigation(MACRO_NAVIGATION_TREE);
export function macroModuleHref(moduleId: MacroModuleId): string;
export function macroRouteLabel(moduleId: MacroModuleId): string;
export function macroNavigationPath(moduleId: MacroModuleId | "assets/correlation"): MacroNavigationNode[];
```

- Modify `web/src/features/macro/model/macroRoutes.ts`
  - Keep `MacroModuleId`, route resolution, href, label, and breadcrumb helpers.
  - Import route data from `macroNavigationTree.ts`.
  - Delete `macroPrimaryTabRoutes` and `macroSecondaryTabRoutes`.
  - Change unsupported route handling from silent overview fallback to:

```ts
return {
  canonicalPath: `/macro/${normalized}`,
  routeKind: "unsupported",
  routeTail: normalized,
};
```

  - Update `MacroRouteResolution` with an `unsupported` variant.

- Modify `web/src/features/macro/api/useMacroModuleQuery.ts`
  - Keep the same endpoint.
  - Update the imported view type only.

- Modify `web/tests/fixtures/macroFixture.ts`
  - Update fixture payloads to v3 keys.
  - Add fixture examples for:
    - overview with global data health;
    - assets landing with `section_boards`;
    - equities leaf with module-local data health and transmission.

- Modify `web/tests/unit/features/macro/model/macroRoutes.test.ts`
  - Delete expectations for primary and secondary tab helpers.
  - Add tests for tree-derived route labels, breadcrumbs, correlation route, and unsupported route state.

### Shell/sidebar navigation

- Modify `web/src/features/cockpit/ui/appNavigation.ts`
  - Import the macro navigation tree.
  - Replace the current three macro children with the full tree:

```ts
{
  children: macroNavigationForSidebar(),
  icon: BriefcaseBusiness,
  label: "宏观",
  matchPath: "/macro/*",
  to: "/macro",
}
```

  - Preserve other app routes unchanged.

- Modify `web/src/features/cockpit/ui/AppSidebar.tsx`
  - Render nested macro children recursively instead of one child level only.
  - Ensure the macro parent can be active while only one leaf has `aria-current="page"`.
  - Preserve `useCloseSidebarOnNavigate` for mobile drawer close behavior.
  - Do not fetch macro navigation from the API in the sidebar.

- Modify `web/src/features/cockpit/ui/AppSidebar.css`
  - Add styles for one additional nested macro depth.
  - Keep CSS under `@layer app.shell`.
  - Avoid horizontal overflow in collapsed and mobile states.

- Modify `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`
  - Replace the current macro child assertions with:
    - `宏观` parent exists;
    - `大类资产` domain exists;
    - `美股` leaf exists and links to `/macro/assets/equities`;
    - `/macro/assets/equities` marks only `美股` as current;
    - `/macro/assets/correlation` marks only `相关性` as current.

### Macro shell header

- Modify `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
  - Remove imports and calls for `macroActiveSection`, `macroPrimaryTabRoutes`, and `macroSecondaryTabRoutes`.
  - Remove `MacroTabLink`.
  - Remove the header data-gap strip.
  - Keep:
    - `MacroBreadcrumb`;
    - kicker;
    - title;
    - question/subtitle;
    - status/as-of/history readiness.
  - Update history readiness to prefer `module.data_health.summary_status` when present.

- Modify `web/src/features/macro/ui/shell/macroShell.css`
  - Delete `.macro-shell-primary-tabs`, `.macro-shell-secondary-tabs`, and `.macro-shell-tab` selectors.
  - Reduce header visual weight so the first viewport prioritizes content.
  - Keep all macro shell CSS inside `@layer app.features`.

- Modify `web/tests/component/features/macro/MacroShell.test.tsx`
  - Assert the header does not render `宏观主模块` or `宏观模块`.
  - Assert breadcrumb, title, question, status, and as-of remain visible.

### Macro pages

- Modify `web/src/features/macro/MacroWorkbenchRoute.tsx`
  - Handle the new unsupported route resolution.
  - Render a `PageState.Error` or dedicated unsupported macro route state for unsupported paths.
  - Route `overview` to overview renderer, `assets` to the new asset index renderer, and leaf modules to the leaf renderer.

- Modify `web/src/routes/macro.route.tsx`
  - Use the new unsupported variant from `parseMacroRouteTail`.
  - Do not navigate unsupported routes to `/macro`.

- Replace `web/src/features/macro/ui/pages/MacroAssetsLandingPage.tsx`
  - Render `module.section_boards` as compact asset-class sections.
  - Each section shows:
    - title;
    - status label;
    - compact data rows;
    - a link to the leaf page.
  - It must not render the generic leaf frame.

- Modify `web/src/features/macro/ui/pages/MacroOverviewPage.tsx`
  - Keep overview global by design.
  - Render global read/evidence/transmission/data-health from v3 fields.
  - Use accessible regions:
    - `宏观总览`;
    - `核心驱动`;
    - `全局传导链`;
    - `数据健康`.

- Replace `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
  - Keep it as the leaf module renderer, or rename it to `MacroLeafModulePageFrame.tsx` if the file becomes clearer.
  - Render regions in this order:
    1. `关键指标`
    2. `市场板`
    3. `模块判断`
    4. `传导链`
    5. `模块证据`
    6. `数据来源`
    7. `模块数据健康`
  - Read from v3 keys only:
    - `module.module_read`;
    - `module.module_evidence`;
    - `module.transmission`;
    - `module.data_health`;
    - `module.provenance`.
  - Delete `TransmissionMap` logic that builds nodes from `module.read`.
  - Delete any fallback that reads old `read`, `evidence`, or `data_gaps`.

- Modify all small wrapper pages under `web/src/features/macro/ui/pages/`
  - `MacroAssetClassPage.tsx`
  - `MacroCreditPage.tsx`
  - `MacroCryptoDerivativesPage.tsx`
  - `MacroEconomyPage.tsx`
  - `MacroFedPage.tsx`
  - `MacroLiquidityPage.tsx`
  - `MacroRatesPage.tsx`
  - `MacroVolatilityPage.tsx`
  - Ensure each wrapper uses the v3 leaf frame and no old region labels.

- Modify `web/src/features/macro/ui/pages/macroPages.css`
  - Rework layout after semantics are correct.
  - Keep dense terminal-like tables and panels.
  - Keep card radius at `8px` or less.
  - Avoid nested cards and decorative blobs.
  - Ensure `390px`, `430px`, `834px`, `1366px`, and `1920px` layouts do not overlap.

### Tests

- Modify `web/tests/component/features/macro/MacroModulePages.test.tsx`
  - Replace old region names with new region names.
  - Add tests for:
    - assets landing section boards;
    - equities leaf module-local read;
    - no global gap strip in header;
    - transmission nodes come from `module.transmission`.

- Modify `web/tests/routes/macro.route.test.tsx`
  - Replace old `宏观传导图` expectations.
  - Add unsupported route test.
  - Add sidebar navigation reachability expectation where route render includes shell.

- Modify `web/tests/unit/features/macro/model/macroPageViewModel.test.ts`
  - Update helper expectations for v3 keys.

- Modify or add `web/tests/e2e/golden-paths/macro-terminal.spec.ts`
  - Verify:
    - desktop `/macro/assets/equities` shows sidebar tree and no macro horizontal tabs;
    - mobile drawer opens and reaches `宏观 -> 大类资产 -> 美股`;
    - `/macro/assets` renders asset-class sections;
    - unsupported route shows unsupported state.

## Task 1: Backend v3 Contract and Module Semantics

**Files:**
- Modify: `src/parallax/domains/macro_intel/_constants.py`
- Modify: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- Modify: `src/parallax/domains/macro_intel/services/macro_module_views.py`
- Test: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
- Test: `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
- Test: `tests/unit/domains/macro_intel/test_macro_module_views.py`
- Test: `tests/unit/test_api_macro_contract.py`

- [ ] **Step 1: Write failing backend tests**

Add tests that assert:

```python
assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
assert "module_read" in view
assert "module_evidence" in view
assert "transmission" in view
assert "data_health" in view
assert "section_boards" in view
assert "read" not in view
assert "evidence" not in view
assert "data_gaps" not in view
```

Add a non-overview snapshot fixture with:

```python
"scenario_json": {
    "current_regime": "term_premium_pressure",
    "confidence": 0.79,
    "confirmations": [{"code": "global_term_premium", "description": "global only"}],
},
"data_gaps_json": [{"code": "missing_liquidity_srf", "label": "缺少 SRF"}],
```

For `assets/equities`, assert:

```python
assert "期限溢价压力" not in view["module_read"]["headline"]
assert all(item.get("code") != "global_term_premium" for item in view["module_evidence"]["confirmations"])
assert all(gap.get("code") != "missing_liquidity_srf" for gap in view["data_health"]["module_gaps"])
assert any(gap.get("code") == "missing_liquidity_srf" for gap in view["data_health"]["global_gaps"])
```

- [ ] **Step 2: Run backend tests to verify RED**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
```

Expected: FAIL because v3 keys and catalog section boards do not exist.

- [ ] **Step 3: Implement v3 payload**

Implement the file-level edits above. Keep helper functions pure and deterministic. Use early returns for missing snapshots. Do not add compatibility fallbacks.

- [ ] **Step 4: Run backend tests to verify GREEN**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit backend contract slice**

```bash
git add src/parallax/domains/macro_intel/_constants.py \
  src/parallax/domains/macro_intel/services/macro_module_catalog.py \
  src/parallax/domains/macro_intel/services/macro_module_views.py \
  tests/unit/domains/macro_intel/test_macro_migration_contract.py \
  tests/unit/domains/macro_intel/test_macro_module_catalog.py \
  tests/unit/domains/macro_intel/test_macro_module_views.py \
  tests/unit/test_api_macro_contract.py
git commit -m "feat: hard cut macro module view v3"
```

## Task 2: Frontend Types, Fixtures, and Route Tree

**Files:**
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Create: `web/src/features/macro/model/macroNavigationTree.ts`
- Modify: `web/src/features/macro/model/macroRoutes.ts`
- Modify: `web/src/features/macro/api/useMacroModuleQuery.ts`
- Modify: `web/tests/fixtures/macroFixture.ts`
- Test: `web/tests/unit/features/macro/model/macroRoutes.test.ts`
- Test: `web/tests/unit/features/macro/model/macroPageViewModel.test.ts`

- [ ] **Step 1: Write failing TypeScript route/model tests**

Add route tests for:

```ts
expect(macroModuleHref("assets/equities")).toBe("/macro/assets/equities");
expect(macroRouteLabel("assets/equities")).toBe("美股");
expect(macroNavigationPath("assets/equities").map((node) => node.label)).toEqual([
  "宏观",
  "大类资产",
  "美股",
]);
expect(parseMacroRouteTail("not-real")).toMatchObject({
  routeKind: "unsupported",
  routeTail: "not-real",
});
```

Remove tests importing `macroPrimaryTabRoutes` and `macroSecondaryTabRoutes`.

- [ ] **Step 2: Run frontend model tests to verify RED**

```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts
```

Expected: FAIL because the tree file and unsupported route variant do not exist.

- [ ] **Step 3: Implement v3 types and single macro navigation tree**

Update the types and fixtures. Ensure `MacroModuleView` no longer defines old `read`, `evidence`, or `data_gaps` keys.

- [ ] **Step 4: Run frontend model tests to verify GREEN**

```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit frontend model slice**

```bash
git add web/src/lib/types/frontend-contracts.ts \
  web/src/features/macro/model/macroNavigationTree.ts \
  web/src/features/macro/model/macroRoutes.ts \
  web/src/features/macro/api/useMacroModuleQuery.ts \
  web/tests/fixtures/macroFixture.ts \
  web/tests/unit/features/macro/model/macroRoutes.test.ts \
  web/tests/unit/features/macro/model/macroPageViewModel.test.ts
git commit -m "feat: derive macro routes from navigation tree"
```

## Task 3: Move Full Macro Navigation Into AppSidebar

**Files:**
- Modify: `web/src/features/cockpit/ui/appNavigation.ts`
- Modify: `web/src/features/cockpit/ui/AppSidebar.tsx`
- Modify: `web/src/features/cockpit/ui/AppSidebar.css`
- Test: `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`

- [ ] **Step 1: Write failing sidebar tests**

Add assertions:

```tsx
renderSidebar({ route: "/macro/assets/equities" });
expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");
expect(screen.getByRole("link", { name: "大类资产" })).toHaveAttribute("href", "/macro/assets");
expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute("href", "/macro/assets/equities");
expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute("aria-current", "page");
expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
```

- [ ] **Step 2: Run sidebar tests to verify RED**

```bash
cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
```

Expected: FAIL because current sidebar only renders `总览`, `资产`, and `相关性`.

- [ ] **Step 3: Implement recursive sidebar rendering**

Render child nodes recursively. Use `SidebarMenuSub` and `SidebarMenuSubItem` for nested levels. Keep link labels as plain labels and use `aria-current` only on the exact active leaf.

- [ ] **Step 4: Run sidebar tests to verify GREEN**

```bash
cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit sidebar slice**

```bash
git add web/src/features/cockpit/ui/appNavigation.ts \
  web/src/features/cockpit/ui/AppSidebar.tsx \
  web/src/features/cockpit/ui/AppSidebar.css \
  web/tests/component/features/cockpit/ui/AppSidebar.test.tsx
git commit -m "feat: move macro navigation into sidebar tree"
```

## Task 4: Remove Macro Header Navigation and Unsupported Fallbacks

**Files:**
- Modify: `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
- Modify: `web/src/features/macro/ui/shell/macroShell.css`
- Modify: `web/src/features/macro/MacroWorkbenchRoute.tsx`
- Modify: `web/src/routes/macro.route.tsx`
- Test: `web/tests/component/features/macro/MacroShell.test.tsx`
- Test: `web/tests/routes/macro.route.test.tsx`

- [ ] **Step 1: Write failing header and route tests**

Add assertions:

```tsx
expect(screen.queryByRole("navigation", { name: "宏观主模块" })).not.toBeInTheDocument();
expect(screen.queryByRole("navigation", { name: "宏观模块" })).not.toBeInTheDocument();
expect(screen.getByRole("heading", { name: "美股风险" })).toBeInTheDocument();
```

For unsupported path:

```tsx
renderMacroRoute("/macro/not-real");
expect(await screen.findByRole("status")).toHaveTextContent("不支持的宏观页面");
```

- [ ] **Step 2: Run tests to verify RED**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroShell.test.tsx tests/routes/macro.route.test.tsx
```

Expected: FAIL because old header nav still renders and unsupported routes normalize to overview.

- [ ] **Step 3: Remove header tabs and silent fallback**

Delete header tab logic, tab CSS, and unsupported-to-overview behavior. Keep breadcrumb and status.

- [ ] **Step 4: Run tests to verify GREEN**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroShell.test.tsx tests/routes/macro.route.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit shell cleanup slice**

```bash
git add web/src/features/macro/ui/shell/MacroPageHeader.tsx \
  web/src/features/macro/ui/shell/macroShell.css \
  web/src/features/macro/MacroWorkbenchRoute.tsx \
  web/src/routes/macro.route.tsx \
  web/tests/component/features/macro/MacroShell.test.tsx \
  web/tests/routes/macro.route.test.tsx
git commit -m "feat: remove repeated macro page navigation"
```

## Task 5: Rebuild Assets Landing as a Terminal Index

**Files:**
- Replace: `web/src/features/macro/ui/pages/MacroAssetsLandingPage.tsx`
- Modify: `web/src/features/macro/ui/pages/macroPages.css`
- Test: `web/tests/component/features/macro/MacroModulePages.test.tsx`

- [ ] **Step 1: Write failing assets landing tests**

Use the updated fixture with `section_boards` and assert:

```tsx
expect(screen.getByRole("region", { name: "大类资产索引" })).toBeInTheDocument();
expect(screen.getByRole("heading", { name: "美股" })).toBeInTheDocument();
expect(screen.getByRole("heading", { name: "债券" })).toBeInTheDocument();
expect(screen.getByRole("link", { name: "查看美股" })).toHaveAttribute("href", "/macro/assets/equities");
expect(screen.queryByRole("region", { name: "模块判断" })).not.toBeInTheDocument();
```

- [ ] **Step 2: Run page tests to verify RED**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "assets landing"
```

Expected: FAIL because `/macro/assets` still uses the generic frame.

- [ ] **Step 3: Implement terminal index page**

Render one section per `section_boards` item. Use `MacroDataTable` for rows when possible; otherwise render a compact table inside the asset index component. Keep link text explicit, such as `查看美股`.

- [ ] **Step 4: Run page tests to verify GREEN for assets landing**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "assets landing"
```

Expected: PASS for assets landing assertions. Run the full `MacroModulePages.test.tsx` file in Task 6 after the leaf renderer changes.

- [ ] **Step 5: Commit assets landing slice**

```bash
git add web/src/features/macro/ui/pages/MacroAssetsLandingPage.tsx \
  web/src/features/macro/ui/pages/macroPages.css \
  web/tests/component/features/macro/MacroModulePages.test.tsx
git commit -m "feat: rebuild macro assets landing"
```

## Task 6: Rebuild Leaf Module Page Semantics

**Files:**
- Modify or replace: `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroAssetClassPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroCreditPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroCryptoDerivativesPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroEconomyPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroFedPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroLiquidityPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroRatesPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroVolatilityPage.tsx`
- Modify: `web/src/features/macro/ui/pages/MacroOverviewPage.tsx`
- Modify: `web/src/features/macro/ui/pages/macroPages.css`
- Test: `web/tests/component/features/macro/MacroModulePages.test.tsx`

- [ ] **Step 1: Write failing leaf semantic tests**

For equities:

```tsx
expect(screen.getByRole("region", { name: "市场板" })).toBeInTheDocument();
expect(screen.getByRole("region", { name: "模块判断" })).toBeInTheDocument();
expect(screen.getByRole("region", { name: "传导链" })).toBeInTheDocument();
expect(screen.getByRole("region", { name: "模块证据" })).toBeInTheDocument();
expect(screen.getByRole("region", { name: "模块数据健康" })).toBeInTheDocument();
expect(screen.queryByText("缺少 SRF")).not.toBeInTheDocument();
```

For transmission:

```tsx
expect(screen.getByText("Yahoo")).toBeInTheDocument();
expect(screen.getByText("美股风险偏好")).toBeInTheDocument();
```

- [ ] **Step 2: Run page tests to verify RED**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx
```

Expected: FAIL because the page still reads v2 keys and old semantic names.

- [ ] **Step 3: Implement leaf renderer**

Use v3 fields only. Delete any read from:

```ts
module.read
module.evidence
module.data_gaps
```

Render transmission directly from `module.transmission`. Render data health from grouped buckets and label global gaps as overview-level references only when present.

- [ ] **Step 4: Run page tests to verify GREEN**

```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit leaf page slice**

```bash
git add web/src/features/macro/ui/pages \
  web/tests/component/features/macro/MacroModulePages.test.tsx
git commit -m "feat: rebuild macro module page semantics"
```

## Task 7: Visual and Responsive Hardening

**Files:**
- Modify: `web/src/features/cockpit/ui/AppSidebar.css`
- Modify: `web/src/features/macro/ui/shell/macroShell.css`
- Modify: `web/src/features/macro/ui/pages/macroPages.css`
- Modify: `web/src/features/macro/ui/charts/macroCharts.css` only if chart containers overflow after layout changes.
- Modify: `web/src/features/macro/ui/tables/macroTables.css` only if compact index tables overflow.
- Test: `web/tests/architecture/cssArchitectureHarness.test.ts`
- Test: `web/tests/architecture/cssResponsiveContract.test.ts`
- Test: `web/tests/e2e/golden-paths/macro-terminal.spec.ts`

- [ ] **Step 1: Write or update responsive expectations**

Add Playwright expectations:

```ts
await page.goto("/macro/assets/equities");
await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
await expect(page.getByRole("navigation", { name: "宏观主模块" })).toHaveCount(0);
await expect(page.getByRole("region", { name: "市场板" })).toBeVisible();
```

For mobile:

```ts
await page.setViewportSize({ width: 390, height: 844 });
await page.goto("/macro/assets/equities");
await page.getByRole("button", { name: /sidebar/i }).click();
await expect(page.getByRole("link", { name: "美股" })).toBeVisible();
```

- [ ] **Step 2: Run architecture tests to verify RED or current failures**

```bash
cd web && npm run test:architecture
```

Expected: PASS if CSS ownership remains valid, or FAIL with exact selectors to fix.

- [ ] **Step 3: Polish layout**

Apply visual rules after semantic tests pass:

- header compact;
- no nested cards;
- compact asset index tables;
- no hidden horizontal macro tab overflow;
- sidebar nested macro tree readable at desktop and mobile;
- stable panel dimensions;
- text wraps inside controls and panels.

- [ ] **Step 4: Run visual test commands**

```bash
cd web && npm run test:architecture
cd web && npm run test:e2e -- --grep "macro terminal"
```

Expected: PASS.

- [ ] **Step 5: Commit visual hardening slice**

```bash
git add web/src/features/cockpit/ui/AppSidebar.css \
  web/src/features/macro/ui/shell/macroShell.css \
  web/src/features/macro/ui/pages/macroPages.css \
  web/src/features/macro/ui/charts/macroCharts.css \
  web/src/features/macro/ui/tables/macroTables.css \
  web/tests/architecture/cssArchitectureHarness.test.ts \
  web/tests/architecture/cssResponsiveContract.test.ts \
  web/tests/e2e/golden-paths/macro-terminal.spec.ts
git commit -m "style: harden macro terminal layout"
```

Only include chart/table CSS files in the commit if they changed.

## Task 8: Full Verification and Documentation

**Files:**
- Modify: `docs/FRONTEND.md`
- Create: `docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-verification-cn.md`
- Modify: `docs/TECH_DEBT.md` only if non-trivial follow-ups remain.

- [x] **Step 1: Update frontend documentation**

In `docs/FRONTEND.md`, update the Macro route convention to state:

- macro shell/sidebar owns macro navigation;
- module pages consume `macro_module_view_v3`;
- frontend does not use old `read`, `evidence`, or `data_gaps` module keys;
- frontend does not recompute macro scoring or module reads.

- [x] **Step 2: Run targeted verification**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
cd web && npm run lint
cd web && npm run test:architecture
cd web && npm run typecheck
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
cd web && npm run build
```

Expected: all commands exit 0.

- [x] **Step 3: Run full completion gate**

```bash
make check-all
```

Expected: exit 0. If it fails on unrelated known failures, record full output and classify the failure before claiming completion.

Result: exit 2 on unrelated `ruff format --check` baseline; see verification artifact.

- [x] **Step 4: Browser verification**

Start the local app:

```bash
cd web && npm run dev
```

Verify with Browser or Playwright:

- `/macro`
- `/macro/assets`
- `/macro/assets/equities`
- `/macro/assets/correlation`
- `/macro/not-real`
- desktop `1366x720`
- desktop `1920x1080`
- tablet `834x1194`
- mobile `390x844`
- mobile `430x932`

Record:

- no repeated macro header nav;
- sidebar/drawer reaches `宏观 -> 大类资产 -> 美股`;
- assets page is an index;
- leaf page regions match the v3 semantic names;
- unsupported route is explicit;
- no overlapping text or clipped controls;
- no failing `/api/*` requests.

- [x] **Step 5: Write verification artifact**

Create `docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-verification-cn.md` with:

- commands run;
- full outputs for completion gates required by `docs/WORKFLOW.md`;
- screenshots or screenshot paths;
- remaining risks;
- deviations from this plan.

- [x] **Step 6: Commit docs and verification**

```bash
git add docs/FRONTEND.md \
  docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-verification-cn.md \
  docs/TECH_DEBT.md
git commit -m "docs: record macro terminal ui hard cut verification"
```

Only include `docs/TECH_DEBT.md` if it changed.

## PR Breakdown

Single PR only:

1. **Macro Terminal UI Navigation Hard-Cut**
   - Backend module view v3.
   - Sidebar macro navigation tree.
   - Removed macro page tabs and unsupported fallback.
   - Assets index page.
   - Leaf page semantic cleanup.
   - Visual hardening.
   - Documentation and verification.

Reason: the user requested one plan and no compatibility code. Splitting into partial PRs would require temporary compatibility or mixed v2/v3 states.

## Rollout Order

1. Merge backend v3 and frontend v3 in the same PR.
2. Deploy the service and frontend bundle together.
3. Run `uv run parallax db health` after deploy.
4. Open `/macro`, `/macro/assets`, and one leaf page against the deployed app.
5. Confirm no macro route is reading old v2 keys in browser console or network payloads.

## Rollback

- Revert the single PR if macro routes fail after deploy.
- No database migration is planned, so rollback is code-only.
- Because this is a hard cut, do not hotfix by restoring old tab helpers or v2 adapters. If rollback is needed, revert the PR and reapply a corrected v3 hard cut.

## Acceptance Test Commands

- AC1 and AC2:

```bash
cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx
```

- AC3, AC4, AC5, and AC6:

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx
```

- AC7:

```bash
cd web && npm test -- --run tests/routes/macro.route.test.tsx
```

- AC8:

```bash
cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
```

- AC9:

```bash
cd web && npm run lint
cd web && npm run test:architecture
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
```

- AC10:

```bash
cd web && npm run test:e2e -- --grep "macro terminal"
```

## Verification

Verification must be written to `docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-verification-cn.md` before declaring implementation complete. The verification artifact must include `make check-all` output, targeted macro command output, browser viewport notes, screenshots or screenshot paths, skipped tests, coverage notes, and residual risks.
