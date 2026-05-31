# Macro Responsive UI Layout Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the macro terminal UI layout layer so every macro page has an explicit page kind, shared responsive primitives, shell/sidebar-owned navigation, readable dense metrics, and no legacy compatibility rendering.

**Architecture:** This is a frontend hard cut over the existing `macro_module_view_v3` backend contract. Route resolution becomes page-kind based; `MacroShell` owns page header semantics; module pages render through overview/index/leaf/matrix renderers; cards, panels, metrics, evidence, health, and table frames move into small owner-scoped primitives. The correlation page remains backed by `/api/macro/assets/correlation`, but it is rehosted inside the same macro shell/header contract instead of staying a separate visual island.

**Tech Stack:** React 19, React Router 6.30, React Query, TypeScript, lucide-react, Radix Collapsible via shadcn sidebar, TanStack Table, Vitest, React Testing Library, Playwright, CSS cascade layers.

---

**Status**: Proposed
**Date**: 2026-05-26
**Owning spec**: `docs/superpowers/specs/active/2026-05-26-macro-responsive-ui-layout-hard-cut-cn.md`
**Input research**: Four subagent read-only audits on shell/navigation, module page renderer, asset/correlation matrix, and test harness.
**Branch**: `codex/macro-responsive-ui-layout-hard-cut`
**Mode**: Hard cut. Do not keep old selectors, old route visual branches, or thin compatibility wrappers.

## Pre-flight

- [ ] Create an isolated implementation worktree:

```bash
git worktree add .worktrees/macro-responsive-ui-layout-hard-cut -b codex/macro-responsive-ui-layout-hard-cut main
cd .worktrees/macro-responsive-ui-layout-hard-cut
```

- [ ] Confirm the worktree is clean and on the expected branch:

```bash
git status --short
git branch --show-current
```

Expected: no modified files; branch is `codex/macro-responsive-ui-layout-hard-cut`.

- [ ] Read the frontend constraints and owning spec:

```bash
sed -n '1,260p' AGENTS.md
sed -n '1,260p' docs/FRONTEND.md
sed -n '1,260p' docs/TESTING.md
sed -n '1,260p' docs/superpowers/specs/active/2026-05-26-macro-responsive-ui-layout-hard-cut-cn.md
```

- [ ] Run baseline targeted tests before editing:

```bash
cd web
npm test -- --run \
  tests/unit/features/macro/model/macroRoutes.test.ts \
  tests/unit/features/macro/model/macroPageViewModel.test.ts \
  tests/unit/features/macro/model/macroTableColumns.test.ts \
  tests/unit/features/macro/model/macroChartModel.test.ts \
  tests/component/features/cockpit/ui/AppSidebar.test.tsx \
  tests/component/features/macro/MacroModulePages.test.tsx \
  tests/component/features/macro/MacroAssetCorrelationPage.test.tsx \
  tests/component/features/macro/MacroShell.test.tsx \
  tests/routes/macro.route.test.tsx
```

Expected: current main passes. If not, record the exact failure before making changes.

## File Structure

### Route and Product Contract

- Modify `web/src/features/macro/model/macroNavigationTree.ts`
  - Add `pageKind` and `productTier` to nodes.
  - Keep hidden-supported routes addressable but out of primary sidebar.

- Modify `web/src/features/macro/model/macroRoutes.ts`
  - Replace the visual `asset-correlation` special case with a page-kind route resolution.
  - Keep module routes on `/api/macro/modules/{moduleId}`.
  - Keep matrix route on `/api/macro/assets/correlation`.

- Create `web/src/features/macro/model/macroPageRegistry.ts`
  - Export route descriptors, supported route lists, hidden labels, and page-kind helpers.

### Shell and Sidebar

- Modify `web/src/features/cockpit/ui/AppSidebar.tsx`
  - Keep Radix `Collapsible`.
  - Change nested branch default-open policy so third-level macro branches are collapsed by default.

- Modify `web/src/features/macro/ui/shell/MacroShell.tsx`
  - Accept a header model, `pageKind`, `productTier`, and optional header actions.

- Modify `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
  - Render header status from a generic header model rather than only `MacroModuleView`.

- Modify `web/src/features/macro/ui/shell/MacroBreadcrumb.tsx`
  - Accept explicit breadcrumb items so matrix routes can share shell grammar.

- Modify `web/src/features/macro/ui/shell/macroShell.css`
  - Keep only shell/header rules.
  - Remove page-specific layout assumptions from shell CSS.

### Macro Presentation Model

- Create `web/src/features/macro/model/macroModulePresentation.ts`
  - Pure functions for metrics, read summary, evidence groups, data health buckets, and table selection.

- Create `web/src/features/macro/model/macroCorrelationModel.ts`
  - Pure functions for correlation pair ranking, title lookup, source labels, gap labels, and tone labels.

### Shared Macro UI Primitives

- Create `web/src/features/macro/ui/primitives/MacroPageScaffold.tsx`
- Create `web/src/features/macro/ui/primitives/macroPageScaffold.css`
- Create `web/src/features/macro/ui/primitives/MacroPanel.tsx`
- Create `web/src/features/macro/ui/primitives/macroPanel.css`
- Create `web/src/features/macro/ui/primitives/MacroMetricStrip.tsx`
- Create `web/src/features/macro/ui/primitives/macroMetricStrip.css`
- Create `web/src/features/macro/ui/primitives/MacroReadPanel.tsx`
- Create `web/src/features/macro/ui/primitives/MacroTransmissionPanel.tsx`
- Create `web/src/features/macro/ui/primitives/MacroEvidencePanel.tsx`
- Create `web/src/features/macro/ui/primitives/MacroDataHealthPanel.tsx`
- Create `web/src/features/macro/ui/primitives/MacroMarketBoard.tsx`

### Tables and Matrix

- Create `web/src/features/macro/ui/tables/MacroTableFrame.tsx`
- Create `web/src/features/macro/ui/tables/macroTableFrame.css`
- Modify `web/src/features/macro/ui/tables/MacroDataTable.tsx`
- Modify `web/src/features/macro/ui/tables/MacroSourceTable.tsx`
- Modify `web/src/features/macro/ui/tables/macroTables.css`
  - Delete unused `.macro-source-table*` selectors.
  - Delete old `.macro-data-table-wrap` frame ownership after `MacroTableFrame` takes over.

### Page Renderers

- Create `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`
- Create `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`
- Create `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`
- Create `web/src/features/macro/ui/pages/MacroAssetIndexPage.tsx`
- Create `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`
- Modify `web/src/features/macro/MacroWorkbenchRoute.tsx`
- Modify `web/src/routes/macro.route.tsx`
- Modify `web/src/features/macro/index.ts`

### Delete Hard-Cut Files

- Delete `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
- Delete `web/src/features/macro/ui/pages/MacroAssetsLandingPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroAssetsLandingPage.css`
- Delete `web/src/features/macro/ui/pages/MacroAssetClassPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroCreditPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroEconomyPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroFedPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroLiquidityPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroOverviewPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroRatesPage.tsx`
- Delete `web/src/features/macro/ui/pages/MacroVolatilityPage.tsx`
- Delete `web/src/features/macro/MacroAssetCorrelationPage.tsx`
- Delete `web/src/features/macro/MacroAssetCorrelation.css`
- Delete `web/src/features/macro/ui/tables/MacroCorrelationMatrix.tsx`

### Tests

- Modify `web/tests/unit/features/macro/model/macroRoutes.test.ts`
- Create `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`
- Create `web/tests/unit/features/macro/model/macroModulePresentation.test.ts`
- Create `web/tests/unit/features/macro/model/macroCorrelationModel.test.ts`
- Modify `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`
- Modify `web/tests/component/features/macro/MacroShell.test.tsx`
- Modify `web/tests/component/features/macro/MacroModulePages.test.tsx`
- Replace `web/tests/component/features/macro/MacroAssetCorrelationPage.test.tsx` with matrix-shell expectations.
- Create `web/tests/component/features/macro/MacroMetricStrip.test.tsx`
- Create `web/tests/component/features/macro/MacroTableFrame.test.tsx`
- Modify `web/tests/routes/macro.route.test.tsx`
- Create `web/tests/architecture/macroResponsiveHardCut.test.ts`
- Create `web/tests/e2e/support/macroLayoutAudit.ts`
- Create `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts`

## Task 1: Route Kind, Product Tier, And Matrix Route Contract

**Files:**
- Modify: `web/src/features/macro/model/macroNavigationTree.ts`
- Modify: `web/src/features/macro/model/macroRoutes.ts`
- Create: `web/src/features/macro/model/macroPageRegistry.ts`
- Test: `web/tests/unit/features/macro/model/macroRoutes.test.ts`
- Test: `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`

- [ ] **Step 1: Write failing route contract tests**

Add tests that lock in the new contract:

```ts
import {
  buildMacroBreadcrumbs,
  parseMacroRouteTail,
} from "@features/macro/model/macroRoutes";
import {
  supportedMacroAuditRoutes,
  hiddenMacroDirectRoutes,
} from "@features/macro/model/macroPageRegistry";

describe("macro route page kinds", () => {
  it("resolves correlation as a matrix page under the macro route contract", () => {
    expect(parseMacroRouteTail("assets/correlation")).toEqual({
      canonicalPath: "/macro/assets/correlation",
      pageKind: "matrix",
      productTier: "primary",
      routeId: "assets/correlation",
      routeKind: "matrix",
      wasUnknown: false,
    });
  });

  it("separates primary product routes from hidden-supported direct routes", () => {
    expect(supportedMacroAuditRoutes).toHaveLength(32);
    expect(hiddenMacroDirectRoutes.map((route) => route.href)).toEqual([
      "/macro/rates/auctions",
      "/macro/fed/statements",
      "/macro/fed/speeches",
      "/macro/volatility/dashboard",
      "/macro/credit/cds",
    ]);
  });

  it("builds matrix breadcrumbs from the navigation tree", () => {
    expect(buildMacroBreadcrumbs("assets/correlation").map((crumb) => crumb.label)).toEqual([
      "宏观",
      "大类资产",
      "相关性",
    ]);
  });
});
```

- [ ] **Step 2: Run the failing tests**

```bash
cd web
npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts
```

Expected: fail because `pageKind`, `productTier`, `supportedMacroAuditRoutes`, and matrix breadcrumbs do not exist yet.

- [ ] **Step 3: Add page kind and product tier types**

Create `web/src/features/macro/model/macroPageRegistry.ts` with this shape:

```ts
import {
  MACRO_NAVIGATION_TREE,
  type MacroNavigationNode,
} from "./macroNavigationTree";
import type { MacroModuleId } from "./macroRoutes";

export type MacroPageKind = "overview" | "index" | "leaf" | "matrix" | "unsupported";
export type MacroProductTier = "primary" | "secondary" | "hiddenSupported" | "unsupported";
export type MacroRouteId = MacroModuleId | "assets/correlation";

export type MacroRouteDescriptor = {
  href: string;
  label: string;
  pageKind: Exclude<MacroPageKind, "unsupported">;
  productTier: Exclude<MacroProductTier, "unsupported">;
  routeId: MacroRouteId;
};

export const HIDDEN_MACRO_NAV_LABELS = [
  "拍卖",
  "FOMC 声明",
  "美联储讲话",
  "Dashboard",
  "CDS 代理",
] as const;

export function flattenMacroRouteDescriptors(
  nodes: MacroNavigationNode[] = MACRO_NAVIGATION_TREE,
): MacroRouteDescriptor[] {
  return nodes.flatMap((node) => {
    const current =
      node.routeId && node.pageKind && node.productTier
        ? [
            {
              href: node.href,
              label: node.label,
              pageKind: node.pageKind,
              productTier: node.productTier,
              routeId: node.routeId,
            },
          ]
        : [];
    return [...current, ...flattenMacroRouteDescriptors(node.children ?? [])];
  });
}

export const MACRO_ROUTE_DESCRIPTORS = flattenMacroRouteDescriptors();

export const supportedMacroAuditRoutes = MACRO_ROUTE_DESCRIPTORS.filter(
  (route) => route.productTier === "primary" || route.productTier === "secondary",
);

export const hiddenMacroDirectRoutes = MACRO_ROUTE_DESCRIPTORS.filter(
  (route) => route.productTier === "hiddenSupported",
);

export function macroRouteDescriptor(routeId: MacroRouteId): MacroRouteDescriptor | undefined {
  return MACRO_ROUTE_DESCRIPTORS.find((route) => route.routeId === routeId);
}
```

- [ ] **Step 4: Update the navigation tree with explicit metadata**

In `macroNavigationTree.ts`, change the node type:

```ts
import type {
  MacroPageKind,
  MacroProductTier,
  MacroRouteId,
} from "./macroPageRegistry";
import type { MacroRouteSection } from "./macroRoutes";

export type MacroNavigationNode = {
  label: string;
  href: string;
  routeId?: MacroRouteId;
  pageKind?: Exclude<MacroPageKind, "unsupported">;
  productTier?: Exclude<MacroProductTier, "unsupported">;
  navHidden?: boolean;
  section?: MacroRouteSection;
  children?: MacroNavigationNode[];
};
```

For each node that currently has `moduleId`, replace it with `routeId`, `pageKind`, and `productTier`. Use:

- `/macro`: `routeId: "overview"`, `pageKind: "overview"`, `productTier: "primary"`
- `/macro/assets`: `pageKind: "index"`, `productTier: "primary"`
- `/macro/assets/correlation`: `routeId: "assets/correlation"`, `pageKind: "matrix"`, `productTier: "primary"`
- `assets/crypto-derivatives`, `liquidity/global-dollar`, `liquidity/subsurface`, `economy/consumer`: `productTier: "secondary"`
- nav-hidden nodes: `productTier: "hiddenSupported"`
- all other visible module leaves and category pages: `productTier: "primary"`

- [ ] **Step 5: Update route parsing**

In `macroRoutes.ts`, replace the old `asset-correlation` resolution with:

```ts
export type MacroRouteResolution =
  | {
      routeKind: "module";
      moduleId: MacroModuleId;
      pageKind: "overview" | "index" | "leaf";
      productTier: MacroProductTier;
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "matrix";
      routeId: "assets/correlation";
      pageKind: "matrix";
      productTier: MacroProductTier;
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "unsupported";
      pageKind: "unsupported";
      productTier: "unsupported";
      canonicalPath: string;
      routeTail: string;
    };
```

Then implement parsing from `macroRouteDescriptor(...)` rather than the current hard-coded `normalized === "assets/correlation"` branch.

- [ ] **Step 6: Run route tests**

```bash
cd web
npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/macro/model/macroNavigationTree.ts \
  web/src/features/macro/model/macroRoutes.ts \
  web/src/features/macro/model/macroPageRegistry.ts \
  web/tests/unit/features/macro/model/macroRoutes.test.ts \
  web/tests/unit/features/macro/model/macroPageRegistry.test.ts
git commit -m "feat: define macro page kind route contract"
```

## Task 2: Sidebar Third-Level Default Collapse

**Files:**
- Modify: `web/src/features/cockpit/ui/AppSidebar.tsx`
- Modify: `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`

- [ ] **Step 1: Write failing sidebar tests**

Update the active nested macro test to assert that the macro root opens on macro routes but nested category branches start closed:

```ts
it("keeps third-level macro navigation collapsed by default on active leaf routes", () => {
  renderSidebar({ route: "/macro/assets/equities" });

  expect(screen.getByRole("button", { name: "收起宏观" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );

  const assetLink = screen.getByRole("link", { name: "大类资产" });
  expect(assetLink).toHaveAttribute("data-active", "true");
  expect(assetLink).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("button", { name: "展开大类资产" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(screen.queryByRole("link", { name: "美股" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "展开大类资产" }));
  expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute("aria-current", "page");
});
```

Also add `Dashboard` to the hidden-label assertion.

- [ ] **Step 2: Run the failing sidebar test**

```bash
cd web
npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
```

Expected: fail because `useBranchOpen(active)` currently auto-opens active nested branches.

- [ ] **Step 3: Implement explicit branch open policy**

Change `AppSidebar.tsx`:

```ts
function AppSidebarItem({ item }: { item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();
  const Icon = item.icon;
  const [open, setOpen] = useBranchOpen({ active, autoOpenActive: true });
  const contentId = useId();
  // existing render continues
}

function AppSidebarSubItem({ depth, item }: { depth: number; item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();
  const [open, setOpen] = useBranchOpen({ active, autoOpenActive: false });
  const contentId = useId();
  // existing render continues
}

function useBranchOpen({
  active,
  autoOpenActive,
}: {
  active: boolean;
  autoOpenActive: boolean;
}): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(active && autoOpenActive);

  useEffect(() => {
    if (active && autoOpenActive) {
      setOpen(true);
    }
  }, [active, autoOpenActive]);

  return [open, setOpen];
}
```

- [ ] **Step 4: Run sidebar tests**

```bash
cd web
npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/cockpit/ui/AppSidebar.tsx \
  web/tests/component/features/cockpit/ui/AppSidebar.test.tsx
git commit -m "feat: collapse nested macro sidebar branches by default"
```

## Task 3: Shell Header Contract

**Files:**
- Modify: `web/src/features/macro/ui/shell/MacroShell.tsx`
- Modify: `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
- Modify: `web/src/features/macro/ui/shell/MacroBreadcrumb.tsx`
- Modify: `web/src/features/macro/ui/shell/macroShell.css`
- Modify: `web/tests/component/features/macro/MacroShell.test.tsx`

- [ ] **Step 1: Write failing shell tests for generic header models**

Add tests for module and matrix headers:

```ts
import type { MacroShellHeaderModel } from "@features/macro/ui/shell/MacroShell";

it("renders a matrix header through the same macro shell grammar", () => {
  const header: MacroShellHeaderModel = {
    actions: <button type="button">60d</button>,
    breadcrumbs: [
      { label: "宏观", href: "/macro" },
      { label: "大类资产", href: "/macro/assets" },
      { label: "相关性", href: "/macro/assets/correlation" },
    ],
    eyebrow: "宏观工作台",
    question: "资产之间的风险传导是否正在同步？",
    statusItems: [
      { label: "状态", value: "滚动相关性" },
      { label: "窗口", value: "60d" },
    ],
    title: "资产相关性",
  };

  renderWithProviders(
    <MacroShell header={header} pageKind="matrix" productTier="primary">
      <section aria-label="matrix content">Matrix content</section>
    </MacroShell>,
    { route: "/macro/assets/correlation" },
  );

  expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "matrix");
  expect(screen.getByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toHaveTextContent(
    "宏观/大类资产/相关性",
  );
  expect(screen.getByRole("button", { name: "60d" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the failing shell tests**

```bash
cd web
npm test -- --run tests/component/features/macro/MacroShell.test.tsx
```

Expected: fail because `MacroShell` currently requires `module` and `moduleId`.

- [ ] **Step 3: Implement the generic shell props**

Replace `MacroShell` props with:

```ts
import type { ReactNode } from "react";

import type { MacroPageKind, MacroProductTier } from "../../model/macroPageRegistry";
import type { MacroBreadcrumb as MacroBreadcrumbItem } from "../../model/macroRoutes";
import { MacroPageHeader } from "./MacroPageHeader";

export type MacroShellStatusItem = {
  label: string;
  value: ReactNode;
};

export type MacroShellHeaderModel = {
  actions?: ReactNode;
  breadcrumbs: MacroBreadcrumbItem[];
  eyebrow: string;
  question?: string | null;
  statusItems: MacroShellStatusItem[];
  title: string;
};

export function MacroShell({
  children,
  header,
  pageKind,
  productTier,
}: {
  children: ReactNode;
  header: MacroShellHeaderModel;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
}) {
  return (
    <section
      className="macro-shell"
      aria-label="宏观工作台"
      data-page-kind={pageKind}
      data-product-tier={productTier}
    >
      <div className="macro-shell-main">
        <MacroPageHeader header={header} />
        <div className="macro-shell-content">{children}</div>
      </div>
    </section>
  );
}
```

Update `MacroPageHeader` to receive `header: MacroShellHeaderModel` and render `header.actions` beside the status strip.

- [ ] **Step 4: Convert breadcrumb to explicit items**

Change `MacroBreadcrumb` to:

```ts
import { Link } from "react-router-dom";
import type { MacroBreadcrumb as MacroBreadcrumbItem } from "../../model/macroRoutes";

export function MacroBreadcrumb({ breadcrumbs }: { breadcrumbs: MacroBreadcrumbItem[] }) {
  return (
    <nav aria-label="宏观面包屑" className="macro-shell-breadcrumb">
      {breadcrumbs.map((crumb, index) => (
        <span key={crumb.href}>
          {index > 0 ? <span aria-hidden="true">/</span> : null}
          {index === breadcrumbs.length - 1 ? (
            <span aria-current="page">{crumb.label}</span>
          ) : (
            <Link to={crumb.href}>{crumb.label}</Link>
          )}
        </span>
      ))}
    </nav>
  );
}
```

- [ ] **Step 5: Update shell CSS**

Keep these shell selectors and remove page-level assumptions:

```css
@layer app.features {
  .macro-shell {
    display: grid;
    min-width: 0;
    min-height: 0;
    color: var(--text-primary, #f8fafc);
  }

  .macro-shell-main,
  .macro-shell-content {
    display: grid;
    min-width: 0;
  }

  .macro-shell-main {
    gap: 10px;
  }

  .macro-shell-heading-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(240px, auto);
    align-items: end;
    gap: 16px;
  }

  .macro-shell-status-actions {
    display: grid;
    justify-items: end;
    gap: 8px;
    min-width: 0;
  }

  @media (max-width: 767px) {
    .macro-shell-heading-row,
    .macro-shell-status-actions {
      grid-template-columns: 1fr;
      justify-items: stretch;
    }
  }
}
```

- [ ] **Step 6: Run shell tests**

```bash
cd web
npm test -- --run tests/component/features/macro/MacroShell.test.tsx
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/macro/ui/shell/MacroShell.tsx \
  web/src/features/macro/ui/shell/MacroPageHeader.tsx \
  web/src/features/macro/ui/shell/MacroBreadcrumb.tsx \
  web/src/features/macro/ui/shell/macroShell.css \
  web/tests/component/features/macro/MacroShell.test.tsx
git commit -m "feat: generalize macro shell header contract"
```

## Task 4: Presentation Model And Shared Primitives

**Files:**
- Create: `web/src/features/macro/model/macroModulePresentation.ts`
- Create: `web/src/features/macro/ui/primitives/MacroPageScaffold.tsx`
- Create: `web/src/features/macro/ui/primitives/macroPageScaffold.css`
- Create: `web/src/features/macro/ui/primitives/MacroPanel.tsx`
- Create: `web/src/features/macro/ui/primitives/macroPanel.css`
- Create: `web/src/features/macro/ui/primitives/MacroMetricStrip.tsx`
- Create: `web/src/features/macro/ui/primitives/macroMetricStrip.css`
- Create: `web/src/features/macro/ui/primitives/MacroReadPanel.tsx`
- Create: `web/src/features/macro/ui/primitives/MacroTransmissionPanel.tsx`
- Create: `web/src/features/macro/ui/primitives/MacroEvidencePanel.tsx`
- Create: `web/src/features/macro/ui/primitives/MacroDataHealthPanel.tsx`
- Test: `web/tests/unit/features/macro/model/macroModulePresentation.test.ts`
- Test: `web/tests/component/features/macro/MacroMetricStrip.test.tsx`

- [ ] **Step 1: Write failing presentation model tests**

```ts
import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  buildMacroMetrics,
  macroReadSummary,
} from "@features/macro/model/macroModulePresentation";
import { macroOverviewModuleFixture } from "@tests/fixtures/macroFixture";

describe("macroModulePresentation", () => {
  it("normalizes metric labels without exposing raw keys", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        { concept_key: "asset:spx", label: "标普500", short_label: "SPX", display_value: "7473.47" },
        { concept_key: "vol:vix", label: "VIX", short_label: "VIX", display_value: "16.76" },
      ],
    });

    expect(metrics.map((metric) => metric.shortLabel)).toEqual(["SPX", "VIX"]);
    expect(metrics.map((metric) => metric.value)).toEqual(["7473.47", "16.76"]);
  });

  it("builds read, evidence, and health from v3 fields only", () => {
    const module = macroOverviewModuleFixture();

    expect(macroReadSummary(module)).toContain("总览");
    expect(buildMacroEvidenceGroups(module.module_evidence).map((group) => group.key)).toEqual([
      "confirmations",
      "contradictions",
      "watch_triggers",
      "data_gaps",
    ]);
    expect(buildMacroDataHealthBuckets(module.data_health, "overview")).toHaveLength(4);
  });
});
```

- [ ] **Step 2: Write failing metric component tests**

```ts
import { MacroMetricStrip } from "@features/macro/ui/primitives/MacroMetricStrip";
import { render, screen } from "@testing-library/react";

it("renders compact market labels in stable metric zones", () => {
  render(
    <MacroMetricStrip
      ariaLabel="关键指标"
      metrics={[
        {
          key: "asset:spx",
          label: "标普500",
          observedAtLabel: "观测于 2026-05-22",
          quality: "ok",
          qualityLabel: "可用",
          shortLabel: "SPX",
          unitLabel: "点",
          value: "7473.47",
        },
        {
          key: "macro:payrolls",
          label: "Payrolls",
          observedAtLabel: "观测于 2026-05-03",
          quality: "partial",
          qualityLabel: "部分可用",
          shortLabel: "Payrolls",
          unitLabel: null,
          value: "177K",
        },
      ]}
    />,
  );

  expect(screen.getByRole("region", { name: "关键指标" })).toBeInTheDocument();
  expect(screen.getByText("SPX")).toHaveAttribute("data-macro-metric-label", "true");
  expect(screen.getByText("Payrolls")).toHaveAttribute("data-macro-metric-label", "true");
});
```

- [ ] **Step 3: Run failing tests**

```bash
cd web
npm test -- --run \
  tests/unit/features/macro/model/macroModulePresentation.test.ts \
  tests/component/features/macro/MacroMetricStrip.test.tsx
```

Expected: fail because files do not exist.

- [ ] **Step 4: Implement the presentation model**

`macroModulePresentation.ts` must export:

```ts
import type {
  MacroDataHealth,
  MacroModuleTable,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
} from "@lib/types";

import { emptyTable } from "./macroModulePageModel";
import { formatMacroScalar, gapLabel } from "./macroPageViewModel";

export type MacroMetricDisplay = {
  key: string;
  label: string;
  observedAtLabel: string | null;
  quality: string | null;
  qualityLabel: string | null;
  shortLabel: string | null;
  unitLabel: string | null;
  value: string;
};

export function buildMacroMetrics({ tiles }: { tiles: MacroModuleTile[] }): MacroMetricDisplay[] {
  return tiles.map((tile, index) => ({
    key: String(tile.concept_key ?? tile.label ?? `metric:${index}`),
    label: stringValue(tile.label) ?? stringValue(tile.short_label) ?? "未命名指标",
    observedAtLabel:
      stringValue(tile.observed_at_label) ??
      stringValue(tile.quality_label) ??
      stringValue(tile.delta_label),
    quality: stringValue(tile.quality),
    qualityLabel: stringValue(tile.quality_label),
    shortLabel:
      stringValue(tile.short_label) ??
      stringValue(tile.source_label) ??
      stringValue(tile.quality_label),
    unitLabel: stringValue(tile.unit_label),
    value: formatMacroScalar(tile.display_value ?? tile.value),
  }));
}

export function primarySupportingTable(module: MacroModuleView): MacroModuleTable {
  return module.tables[0] ?? emptyTable(`${module.snapshot.module_id ?? "macro"}_supporting_table`);
}

export function extraTables(module: MacroModuleView): MacroModuleTable[] {
  return module.tables.slice(1);
}

export function macroReadSummary(module: MacroModuleView): string {
  const read = module.module_read;
  return formatMacroScalar(
    read.headline || read.summary || read.regime_label || module.snapshot.status || "暂无",
  );
}

export function buildMacroEvidenceGroups(evidence: MacroModuleView["module_evidence"]) {
  return EVIDENCE_GROUPS.map((group) => ({
    ...group,
    items: evidenceItemsForGroup(evidence, group.key),
  }));
}

export function buildMacroDataHealthBuckets(dataHealth: MacroDataHealth, scope: "leaf" | "overview") {
  return [
    {
      key: "module_gaps",
      label: "模块缺口",
      items: dataHealth.module_gaps.map(gapLabel).filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "chart_gaps",
      label: "图表缺口",
      items: dataHealth.chart_gaps.map(gapLabel).filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "global_gaps",
      label: scope === "leaf" ? "全局缺口（总览级参考）" : "全局缺口",
      items:
        scope === "overview"
          ? dataHealth.global_gaps.map(gapLabel).filter((label) => label !== "数据缺口待确认")
          : [],
      referenceCount: scope === "leaf" ? dataHealth.global_gaps.length : undefined,
    },
    {
      key: "future_integration_gaps",
      label: "未来集成缺口",
      items: dataHealth.future_integration_gaps
        .map(gapLabel)
        .filter((label) => label !== "数据缺口待确认"),
    },
  ];
}

function evidenceItemsForGroup(evidence: MacroModuleView["module_evidence"], key: string) {
  const items = evidence[key];
  if (!Array.isArray(items)) return [];
  return items
    .map((item) =>
      item && typeof item === "object"
        ? {
            detail: formatMacroScalar((item as MacroSemanticRecord).description),
            label: formatMacroScalar((item as MacroSemanticRecord).label),
          }
        : null,
    )
    .filter((item): item is { detail: string; label: string } =>
      Boolean(item && item.label !== "暂无"),
    );
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

const EVIDENCE_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "data_gaps", label: "数据缺口" },
] as const;
```

- [ ] **Step 5: Implement primitives**

`MacroPageScaffold.tsx`:

```tsx
import type { CSSProperties, ReactNode } from "react";
import type { MacroPageKind } from "../../model/macroPageRegistry";
import "./macroPageScaffold.css";

export function MacroPageScaffold({
  children,
  label,
  pageKind,
}: {
  children: ReactNode;
  label: string;
  pageKind: MacroPageKind;
}) {
  return (
    <section
      className="macro-page-scaffold"
      aria-label={label}
      data-page-kind={pageKind}
    >
      {children}
    </section>
  );
}
```

`MacroMetricStrip.tsx`:

```tsx
import type { MacroMetricDisplay } from "../../model/macroModulePresentation";
import "./macroMetricStrip.css";

export function MacroMetricStrip({
  ariaLabel,
  density = "auto",
  metrics,
}: {
  ariaLabel: string;
  density?: "auto" | "card" | "compact" | "list";
  metrics: MacroMetricDisplay[];
}) {
  if (metrics.length === 0) {
    return (
      <section className="macro-metric-strip" aria-label={ariaLabel} data-density={density}>
        <div className="macro-metric-empty" role="status">暂无关键指标</div>
      </section>
    );
  }

  return (
    <section
      className="macro-metric-strip"
      aria-label={ariaLabel}
      data-density={density}
      data-count={metrics.length}
    >
      {metrics.map((metric) => (
        <article className="macro-metric" data-quality={metric.quality ?? undefined} key={metric.key}>
          <div className="macro-metric-label-zone">
            <span className="macro-metric-short-label" data-macro-metric-label="true">
              {metric.shortLabel ?? metric.label}
            </span>
            <b>{metric.label}</b>
          </div>
          <div className="macro-metric-value-zone">
            <strong>{metric.value}</strong>
            {metric.unitLabel ? <em>{metric.unitLabel}</em> : null}
          </div>
          {metric.observedAtLabel ? <small>{metric.observedAtLabel}</small> : null}
        </article>
      ))}
    </section>
  );
}
```

`macroMetricStrip.css` must not use `overflow-wrap: anywhere` or `word-break: break-all`. Use `text-overflow: ellipsis` for compact labels and `overflow-wrap: normal` for short label zones.

- [ ] **Step 6: Run primitive tests**

```bash
cd web
npm test -- --run \
  tests/unit/features/macro/model/macroModulePresentation.test.ts \
  tests/component/features/macro/MacroMetricStrip.test.tsx
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/macro/model/macroModulePresentation.ts \
  web/src/features/macro/ui/primitives \
  web/tests/unit/features/macro/model/macroModulePresentation.test.ts \
  web/tests/component/features/macro/MacroMetricStrip.test.tsx
git commit -m "feat: extract macro presentation primitives"
```

## Task 5: Table Frame And Scroll Contract

**Files:**
- Create: `web/src/features/macro/ui/tables/MacroTableFrame.tsx`
- Create: `web/src/features/macro/ui/tables/macroTableFrame.css`
- Modify: `web/src/features/macro/ui/tables/MacroDataTable.tsx`
- Modify: `web/src/features/macro/ui/tables/MacroSourceTable.tsx`
- Modify: `web/src/features/macro/ui/tables/macroTables.css`
- Test: `web/tests/component/features/macro/MacroDataTable.test.tsx`
- Test: `web/tests/component/features/macro/MacroTableFrame.test.tsx`

- [ ] **Step 1: Write failing table frame tests**

```ts
import { MacroTableFrame } from "@features/macro/ui/tables/MacroTableFrame";
import { render, screen } from "@testing-library/react";

it("renders a labelled bounded horizontal scroll region", () => {
  render(
    <MacroTableFrame caption="大类资产矩阵" minWidth={720} stickyFirstColumn>
      <table>
        <thead><tr><th scope="col">资产</th><th scope="col">状态</th></tr></thead>
        <tbody><tr><th scope="row">SPX</th><td>可用</td></tr></tbody>
      </table>
    </MacroTableFrame>,
  );

  const frame = screen.getByRole("region", { name: "大类资产矩阵，可横向滚动" });
  expect(frame).toHaveAttribute("tabindex", "0");
  expect(frame).toHaveAttribute("data-sticky-first-column", "true");
  expect(screen.getByText("横向滚动查看完整列")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run failing table tests**

```bash
cd web
npm test -- --run \
  tests/component/features/macro/MacroTableFrame.test.tsx \
  tests/component/features/macro/MacroDataTable.test.tsx
```

Expected: fail because `MacroTableFrame` does not exist.

- [ ] **Step 3: Implement `MacroTableFrame`**

```tsx
import type { CSSProperties, ReactNode } from "react";
import "./macroTableFrame.css";

export function MacroTableFrame({
  caption,
  children,
  minWidth = 420,
  stickyFirstColumn = false,
}: {
  caption: string;
  children: ReactNode;
  minWidth?: number;
  stickyFirstColumn?: boolean;
}) {
  return (
    <div className="macro-table-frame" data-sticky-first-column={stickyFirstColumn ? "true" : "false"}>
      <div className="macro-table-frame-hint" id={tableHintId(caption)}>
        横向滚动查看完整列
      </div>
      <div
        aria-describedby={tableHintId(caption)}
        aria-label={`${caption}，可横向滚动`}
        className="macro-table-frame-scroller"
        role="region"
        style={{ "--macro-table-min-width": `${minWidth}px` } as CSSProperties}
        tabIndex={0}
      >
        {children}
      </div>
    </div>
  );
}

function tableHintId(caption: string): string {
  return `macro-table-hint-${caption.replace(/\s+/g, "-").replace(/[^\w-]/g, "")}`;
}
```

`macroTableFrame.css`:

```css
@layer app.features {
  .macro-table-frame {
    display: grid;
    gap: 6px;
    min-width: 0;
  }

  .macro-table-frame-hint {
    color: var(--text-muted, #94a3b8);
    font-size: 0.72rem;
  }

  .macro-table-frame-scroller {
    min-width: 0;
    overflow-x: auto;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px;
    background:
      linear-gradient(90deg, rgba(125, 211, 252, 0.1), transparent 26px),
      rgba(2, 6, 23, 0.28);
    scrollbar-gutter: stable;
  }

  .macro-table-frame-scroller > table {
    min-width: var(--macro-table-min-width);
  }

  .macro-table-frame[data-sticky-first-column="true"] tbody th:first-child,
  .macro-table-frame[data-sticky-first-column="true"] thead th:first-child {
    position: sticky;
    left: 0;
    z-index: 2;
    background: rgba(10, 16, 27, 0.96);
  }
}
```

- [ ] **Step 4: Move `MacroDataTable` into the frame**

Replace its return wrapper with:

```tsx
return (
  <MacroTableFrame caption={caption} minWidth={420} stickyFirstColumn>
    <table aria-label={caption} className="macro-data-table">
      <caption>{caption}</caption>
      {/* existing thead and tbody */}
    </table>
  </MacroTableFrame>
);
```

Import `MacroTableFrame`. Remove `.macro-data-table-wrap` from `macroTables.css`.

- [ ] **Step 5: Delete unused table selectors**

Remove `.macro-source-table` selectors from `macroTables.css` because `MacroSourceTable` renders `MacroDataTable`, not a `.macro-source-table` DOM node.

- [ ] **Step 6: Run table tests**

```bash
cd web
npm test -- --run \
  tests/component/features/macro/MacroTableFrame.test.tsx \
  tests/component/features/macro/MacroDataTable.test.tsx
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/macro/ui/tables/MacroTableFrame.tsx \
  web/src/features/macro/ui/tables/macroTableFrame.css \
  web/src/features/macro/ui/tables/MacroDataTable.tsx \
  web/src/features/macro/ui/tables/MacroSourceTable.tsx \
  web/src/features/macro/ui/tables/macroTables.css \
  web/tests/component/features/macro/MacroDataTable.test.tsx \
  web/tests/component/features/macro/MacroTableFrame.test.tsx
git commit -m "feat: add macro bounded table frame"
```

## Task 6: Page Renderers And Deleting Old Frame Wrappers

**Files:**
- Create: `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`
- Create: `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`
- Create: `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`
- Create: `web/src/features/macro/ui/pages/MacroAssetIndexPage.tsx`
- Modify: `web/src/features/macro/MacroWorkbenchRoute.tsx`
- Modify: `web/src/features/macro/index.ts`
- Delete hard-cut wrapper files listed in File Structure.
- Test: `web/tests/component/features/macro/MacroModulePages.test.tsx`
- Test: `web/tests/routes/macro.route.test.tsx`

- [ ] **Step 1: Write failing renderer tests**

Update `MacroModulePages.test.tsx` so it imports `MacroModulePageRenderer` and asserts page-kind scaffolds:

```ts
renderWithProviders(
  <MacroModulePageRenderer
    module={macroOverviewModuleFixture()}
    moduleId="overview"
    pageKind="overview"
    token="test-token"
  />,
  { route: "/macro" },
);

expect(screen.getByRole("region", { name: "总览模块页面" })).toHaveAttribute(
  "data-page-kind",
  "overview",
);
expect(document.querySelector(".macro-page-panel-current")).not.toBeInTheDocument();
```

Update route tests so `/macro/assets/correlation` still loads, but through `MacroWorkbenchRoute` shell grammar after Task 7.

- [ ] **Step 2: Run failing renderer tests**

```bash
cd web
npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
```

Expected: fail because renderer files do not exist and old wrappers still exist.

- [ ] **Step 3: Implement module renderer**

`MacroModulePageRenderer.tsx`:

```tsx
import type { MacroModuleView } from "@lib/types";
import type { MacroPageKind } from "../../model/macroPageRegistry";
import type { MacroModuleId } from "../../model/macroRoutes";
import { MacroAssetIndexPage } from "./MacroAssetIndexPage";
import { MacroLeafModulePage } from "./MacroLeafModulePage";
import { MacroOverviewModulePage } from "./MacroOverviewModulePage";

export type MacroModulePageProps = {
  module: MacroModuleView;
  moduleId: MacroModuleId;
  pageKind: MacroPageKind;
  token: string;
};

export function MacroModulePageRenderer(props: MacroModulePageProps) {
  if (props.pageKind === "overview") return <MacroOverviewModulePage {...props} />;
  if (props.pageKind === "index") return <MacroAssetIndexPage {...props} />;
  return <MacroLeafModulePage {...props} />;
}
```

- [ ] **Step 4: Implement overview and leaf compositions**

Overview must use full-width command summary:

```tsx
export function MacroOverviewModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });

  return (
    <MacroPageScaffold label="总览模块页面" pageKind="overview">
      <MacroPanel ariaLabel="宏观总览" role="summary" title="宏观总览" meta={macroStatusLabel(module)}>
        <MacroReadPanel module={module} />
        <MacroMetricStrip ariaLabel="关键指标" metrics={metrics.slice(0, 6)} density="compact" />
      </MacroPanel>
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
      />
      <MacroTransmissionPanel module={module} title="全局传导链" />
      <MacroDataHealthPanel dataHealth={module.data_health} scope="overview" />
    </MacroPageScaffold>
  );
}
```

Leaf must use compact metric density when metric count exceeds four:

```tsx
export function MacroLeafModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });

  return (
    <MacroPageScaffold label={`${macroRouteLabel(moduleId)}模块页面`} pageKind="leaf">
      <MacroMetricStrip
        ariaLabel="关键指标"
        density={metrics.length > 4 ? "compact" : "card"}
        metrics={metrics}
      />
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
      />
      <MacroReadPanel module={module} />
      <MacroTransmissionPanel module={module} title="传导链" />
      <MacroEvidencePanel evidence={module.module_evidence} />
      <MacroDataHealthPanel dataHealth={module.data_health} scope="leaf" />
    </MacroPageScaffold>
  );
}
```

- [ ] **Step 5: Rename asset index page**

Create `MacroAssetIndexPage.tsx` from the current `MacroAssetsLandingPage.tsx` logic, but wrap the table in `MacroTableFrame` and use `.macro-asset-index-*` selectors. Do not keep `MacroAssetsLandingPage` exports.

- [ ] **Step 6: Update `MacroWorkbenchRoute`**

Replace `startsWith` page dispatch with the route resolution data:

```tsx
function MacroModuleWorkbenchRoute({
  moduleId,
  pageKind,
  productTier,
  token,
}: {
  moduleId: MacroModuleId;
  pageKind: "overview" | "index" | "leaf";
  productTier: MacroProductTier;
  token: string;
}) {
  const query = useMacroModuleQuery({ moduleId, token });
  const module = query.data ?? null;

  if (query.isLoading) return <PageState.Loading layout="route" label="加载宏观模块" />;
  if (query.isError) return <PageState.Error error={query.error} />;
  if (!module) return null;

  const header = macroModuleHeader({ module, moduleId });

  return (
    <section className="macro-module-route" aria-label="宏观">
      <PageState.Stale updating={query.isFetching && !query.isLoading}>
        <MacroShell header={header} pageKind={pageKind} productTier={productTier}>
          <MacroModulePageRenderer
            module={module}
            moduleId={moduleId}
            pageKind={pageKind}
            token={token}
          />
        </MacroShell>
      </PageState.Stale>
    </section>
  );
}
```

- [ ] **Step 7: Delete old wrappers**

Delete every old wrapper and old frame file listed in the Delete Hard-Cut Files section. Update `web/src/features/macro/index.ts` so it exports only current public pages/primitives/models. Do not re-export deleted wrapper names.

- [ ] **Step 8: Run renderer and route tests**

```bash
cd web
npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add web/src/features/macro web/src/routes/macro.route.tsx \
  web/tests/component/features/macro/MacroModulePages.test.tsx \
  web/tests/routes/macro.route.test.tsx
git commit -m "feat: replace macro module frames with page-kind renderers"
```

## Task 7: Matrix Page Rehost And Correlation Model

**Files:**
- Create: `web/src/features/macro/model/macroCorrelationModel.ts`
- Create: `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`
- Modify: `web/src/features/macro/MacroWorkbenchRoute.tsx`
- Modify: `web/src/routes/macro.route.tsx`
- Modify: `web/tests/component/features/macro/MacroAssetCorrelationPage.test.tsx`
- Modify: `web/tests/routes/macro.route.test.tsx`
- Delete: `web/src/features/macro/MacroAssetCorrelationPage.tsx`
- Delete: `web/src/features/macro/MacroAssetCorrelation.css`
- Delete: `web/src/features/macro/ui/tables/MacroCorrelationMatrix.tsx`

- [ ] **Step 1: Write failing matrix shell tests**

Replace the old correlation component test with:

```ts
it("renders the correlation matrix inside macro shell grammar", async () => {
  renderWithProviders(<MacroMatrixPage token="test-token" />, {
    route: "/macro/assets/correlation",
  });

  expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
  expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "matrix");
  expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toHaveTextContent(
    "宏观/大类资产/相关性",
  );
  expect(await screen.findByRole("table", { name: "60d 资产相关性矩阵" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "20d" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "60d" })).toHaveAttribute("aria-pressed", "true");
});
```

- [ ] **Step 2: Run failing matrix tests**

```bash
cd web
npm test -- --run tests/component/features/macro/MacroAssetCorrelationPage.test.tsx tests/routes/macro.route.test.tsx
```

Expected: fail because `MacroMatrixPage` does not exist.

- [ ] **Step 3: Extract correlation model helpers**

Move pure helper logic from `MacroAssetCorrelationPage.tsx` into `macroCorrelationModel.ts`:

```ts
export function strongestCorrelationPairs(
  data: MacroAssetCorrelationData | null,
  direction: "positive" | "negative",
): MacroAssetCorrelationPair[] {
  const pairs =
    data?.pairs.filter(
      (pair) =>
        pair.available &&
        typeof pair.correlation === "number" &&
        (direction === "positive" ? pair.correlation >= 0 : pair.correlation < 0),
    ) ?? [];

  return pairs
    .sort((left, right) =>
      direction === "positive"
        ? Number(right.correlation) - Number(left.correlation)
        : Number(left.correlation) - Number(right.correlation),
    )
    .slice(0, 8);
}
```

Also export `assetTitleByKey`, `assetLabel`, `sourceLabel`, `correlationTone`, `matrixCorrelationLabel`, `signedCorrelationLabel`, and `correlationGapLabel`.

- [ ] **Step 4: Implement `MacroMatrixPage`**

`MacroMatrixPage` owns query/window state and returns a `MacroShell` with header actions:

```tsx
const WINDOWS: MacroAssetCorrelationWindow[] = ["20d", "60d", "120d"];

export function MacroMatrixPage({ token }: { token: string }) {
  const [window, setWindow] = useState<MacroAssetCorrelationWindow>("60d");
  const query = useMacroAssetCorrelationQuery({ token, window });
  const data = query.data ?? null;
  const header = macroMatrixHeader({ data, window, onWindowChange: setWindow });

  return (
    <section className="macro-module-route" aria-label="宏观">
      {query.isLoading ? <PageState.Loading layout="route" label="加载相关性" /> : null}
      {query.isError ? <PageState.Error error={query.error} /> : null}
      <MacroShell header={header} pageKind="matrix" productTier="primary">
        {data ? <MacroCorrelationMatrixContent data={data} /> : null}
      </MacroShell>
    </section>
  );
}
```

The header actions render the `20d/60d/120d` buttons. The content uses `MacroPageScaffold pageKind="matrix"`, `MacroPanel`, and `MacroTableFrame`. The matrix table must have `aria-label={`${data.window} 资产相关性矩阵`}` and `caption`.

- [ ] **Step 5: Remove route-level visual special case**

In `web/src/routes/macro.route.tsx`, remove the import and early return for root `MacroAssetCorrelationPage`. Always pass the parsed resolution into `MacroWorkbenchRoute`:

```tsx
export function MacroRoute() {
  const params = useParams();
  const token = useBootstrapToken();
  const resolution = parseMacroRouteTail(params["*"]);
  return <MacroWorkbenchRoute {...resolution} token={token} />;
}
```

In `MacroWorkbenchRoute`, add:

```tsx
if (props.routeKind === "matrix") {
  return <MacroMatrixPage token={props.token} />;
}
```

- [ ] **Step 6: Delete old matrix files**

Delete:

```bash
git rm web/src/features/macro/MacroAssetCorrelationPage.tsx \
  web/src/features/macro/MacroAssetCorrelation.css \
  web/src/features/macro/ui/tables/MacroCorrelationMatrix.tsx
```

Update `index.ts` exports to point at `ui/pages/MacroMatrixPage` if a public export is still needed by tests.

- [ ] **Step 7: Run matrix tests**

```bash
cd web
npm test -- --run \
  tests/unit/features/macro/model/macroCorrelationModel.test.ts \
  tests/component/features/macro/MacroAssetCorrelationPage.test.tsx \
  tests/routes/macro.route.test.tsx
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/features/macro web/src/routes/macro.route.tsx \
  web/tests/component/features/macro/MacroAssetCorrelationPage.test.tsx \
  web/tests/routes/macro.route.test.tsx
git commit -m "feat: rehost macro correlation matrix in shell"
```

## Task 8: CSS Hard Cut And Responsive Detail Pass

**Files:**
- Modify: `web/src/features/macro/ui/pages/macroPages.css`
- Modify: new primitive CSS files
- Modify: `web/src/features/macro/ui/tables/macroTables.css`
- Create: `web/tests/architecture/macroResponsiveHardCut.test.ts`

- [ ] **Step 1: Write failing CSS architecture guard**

Create `macroResponsiveHardCut.test.ts`:

```ts
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const macroCssFiles = [
  "src/features/macro/ui/pages/macroPages.css",
  "src/features/macro/ui/primitives/macroMetricStrip.css",
  "src/features/macro/ui/primitives/macroPageScaffold.css",
  "src/features/macro/ui/primitives/macroPanel.css",
  "src/features/macro/ui/tables/macroTables.css",
  "src/features/macro/ui/tables/macroTableFrame.css",
  "src/features/macro/ui/shell/macroShell.css",
].map((path) => join(process.cwd(), path));

describe("macro responsive hard cut", () => {
  it("does not use destructive word wrapping in metric labels", () => {
    const css = macroCssFiles
      .filter((file) => existsSync(file))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    expect(css).not.toMatch(/overflow-wrap:\s*anywhere/);
    expect(css).not.toMatch(/word-break:\s*break-all/);
  });

  it("does not keep retired macro layout selectors", () => {
    const css = macroCssFiles
      .filter((file) => existsSync(file))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    expect(css).not.toContain(".macro-page-panel-current");
    expect(css).not.toContain(".macro-correlation-head");
    expect(css).not.toContain(".macro-assets-index-matrix-wrap");
    expect(css).not.toContain(".macro-data-table-wrap");
  });
});
```

- [ ] **Step 2: Run failing architecture test**

```bash
cd web
npm test -- --run tests/architecture/macroResponsiveHardCut.test.ts
```

Expected: fail until old selectors and wrapping rules are removed.

- [ ] **Step 3: Remove old selector ownership**

Delete old CSS selectors:

- `.macro-page-panel-current`
- `.macro-page-kpi`
- `.macro-page-kpi-strip`
- `.macro-correlation-head`
- `.macro-correlation-page`
- `.macro-assets-index-matrix-wrap`
- `.macro-data-table-wrap`
- `.macro-source-table`

Keep `macroPages.css` only if it owns route-specific page renderer selectors that still exist after Task 6. If all page layout moved into primitives, delete `macroPages.css` and remove its imports.

- [ ] **Step 4: Align breakpoints**

Use the project frontend contract:

```css
@media (max-width: 767px) {
  /* mobile */
}

@media (min-width: 768px) and (max-width: 1279px) {
  /* tablet */
}

@media (min-width: 1280px) {
  /* desktop density */
}
```

Do not use viewport-scaled font sizes. Keep `letter-spacing: 0`.

- [ ] **Step 5: Run architecture tests**

```bash
cd web
npm run test:architecture
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/macro web/tests/architecture/macroResponsiveHardCut.test.ts
git commit -m "feat: hard cut macro responsive css selectors"
```

## Task 9: Responsive Browser Audit

**Files:**
- Create: `web/tests/e2e/support/macroLayoutAudit.ts`
- Create: `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts`
- Modify: `web/tests/e2e/support/mockApi.ts`

- [ ] **Step 1: Add e2e audit helpers**

`macroLayoutAudit.ts`:

```ts
import { expect, type Page } from "@playwright/test";

export const MACRO_AUDIT_VIEWPORTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "mobile-430", width: 430, height: 932 },
  { name: "tablet-834", width: 834, height: 1194 },
  { name: "compact-1096", width: 1096, height: 690 },
  { name: "desktop-1366", width: 1366, height: 720 },
  { name: "desktop-1920", width: 1920, height: 1080 },
] as const;

export async function expectNoMacroBodyOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }));
  expect(metrics.document, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1);
  expect(metrics.body, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1);
}

export async function expectNoMacroMetricFragmentation(page: Page) {
  const failures = await page.evaluate(() => {
    const watched = /^(SPX|VIX|CPI|SOFR|DXY|HY OAS|Payrolls|Claims)$/;
    return Array.from(document.querySelectorAll<HTMLElement>("[data-macro-metric-label]"))
      .filter((element) => watched.test(element.textContent?.trim() ?? ""))
      .flatMap((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const lineHeight = Number.parseFloat(style.lineHeight) || 16;
        const fragmented =
          element.getClientRects().length > 1 ||
          rect.height > lineHeight * 1.45 ||
          style.overflowWrap === "anywhere" ||
          style.wordBreak === "break-all";
        return fragmented
          ? [{ text: element.textContent?.trim(), height: rect.height, lineHeight }]
          : [];
      });
  });
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}

export async function expectHiddenMacroLabelsAbsent(page: Page) {
  const hidden = ["拍卖", "FOMC 声明", "美联储讲话", "Dashboard", "CDS 代理"];
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  for (const label of hidden) {
    await expect(nav.getByRole("link", { name: label })).toHaveCount(0);
  }
}

export async function expectMacroTableFramesBounded(page: Page) {
  const failures = await page.evaluate(() => {
    return Array.from(document.querySelectorAll<HTMLElement>(".macro-table-frame-scroller"))
      .flatMap((frame, index) => {
        const rect = frame.getBoundingClientRect();
        const leaks = rect.width > window.innerWidth + 1;
        const labelled = Boolean(frame.getAttribute("aria-label"));
        return leaks || !labelled
          ? [{ index, width: rect.width, windowWidth: window.innerWidth, labelled }]
          : [];
      });
  });
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}
```

- [ ] **Step 2: Add route sweep spec**

`macro-responsive-audit.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import {
  expectHiddenMacroLabelsAbsent,
  expectMacroTableFramesBounded,
  expectNoMacroBodyOverflow,
  expectNoMacroMetricFragmentation,
  MACRO_AUDIT_VIEWPORTS,
} from "@tests/e2e/support/macroLayoutAudit";
import { expectNoUnhandledApiRequests } from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

const PRODUCT_ROUTES = [
  "/macro",
  "/macro/assets",
  "/macro/assets/equities",
  "/macro/assets/bonds",
  "/macro/assets/commodities",
  "/macro/assets/fx",
  "/macro/assets/crypto",
  "/macro/assets/crypto-derivatives",
  "/macro/assets/correlation",
  "/macro/rates",
  "/macro/rates/fed-funds",
  "/macro/rates/yield-curve",
  "/macro/rates/real-rates",
  "/macro/rates/expectations",
  "/macro/fed",
  "/macro/liquidity",
  "/macro/liquidity/transmission-chain",
  "/macro/liquidity/fed-balance-sheet",
  "/macro/liquidity/operations",
  "/macro/liquidity/rrp-tga",
  "/macro/liquidity/reserves",
  "/macro/liquidity/global-dollar",
  "/macro/liquidity/subsurface",
  "/macro/economy",
  "/macro/economy/gdp",
  "/macro/economy/employment",
  "/macro/economy/inflation",
  "/macro/economy/consumer",
  "/macro/volatility",
  "/macro/volatility/vix",
  "/macro/credit",
  "/macro/credit/stress",
];

const HIDDEN_DIRECT_ROUTES = [
  "/macro/rates/auctions",
  "/macro/fed/statements",
  "/macro/fed/speeches",
  "/macro/volatility/dashboard",
  "/macro/credit/cds",
];

test.describe("macro responsive audit", () => {
  test("macro product and hidden-supported routes satisfy responsive layout contract", async ({ page }) => {
    test.slow();
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await installMockApi(page);

    for (const viewport of MACRO_AUDIT_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const route of [...PRODUCT_ROUTES, ...HIDDEN_DIRECT_ROUTES]) {
        await page.goto(route);
        await expect(page.getByLabel("宏观工作台").or(page.getByRole("status"))).toBeVisible();
        await expectNoMacroBodyOverflow(page);
        await expectNoMacroMetricFragmentation(page);
        await expectMacroTableFramesBounded(page);
        await expectHiddenMacroLabelsAbsent(page);
        await expectNoUnhandledApiRequests(page);
      }
    }

    expect(consoleErrors).toEqual([]);
  });
});
```

- [ ] **Step 3: Extend mock API if needed**

Make sure `installMockApi` handles `/api/macro/assets/correlation`. If it only handles module routes and series, add:

```ts
if (path === "/api/macro/assets/correlation") return fulfill(route, macroCorrelationData());
```

- [ ] **Step 4: Run the responsive audit**

```bash
cd web
npm run test:e2e -- macro-responsive-audit.spec.ts --project=desktop-1366
```

Expected: pass after implementation. This audit intentionally runs all six viewport sizes inside one Playwright project to avoid multiplying runtime across all projects.

- [ ] **Step 5: Commit**

```bash
git add web/tests/e2e/support/macroLayoutAudit.ts \
  web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts \
  web/tests/e2e/support/mockApi.ts
git commit -m "test: add macro responsive route audit"
```

## Task 10: Final Verification And Cleanup

**Files:**
- All modified files from prior tasks.
- `docs/superpowers/specs/active/2026-05-26-macro-responsive-ui-layout-hard-cut-cn.md`

- [ ] **Step 1: Search for forbidden compatibility remnants**

```bash
rg -n "MacroModulePageFrame|MacroAssetsLandingPage|MacroAssetCorrelationPage|MacroCorrelationMatrix|macro-page-panel-current|macro-correlation-head|macro-assets-index-matrix-wrap|macro-data-table-wrap|overflow-wrap:\\s*anywhere|word-break:\\s*break-all" web/src web/tests docs/superpowers/specs/active/2026-05-26-macro-responsive-ui-layout-hard-cut-cn.md
```

Expected: no matches, except the spec may mention old selectors only as historical context. If the spec historical context causes matches, do not edit implementation to satisfy the search; record that the remaining matches are documentation references.

- [ ] **Step 2: Run targeted macro tests**

```bash
cd web
npm test -- --run \
  tests/unit/features/macro/model/macroRoutes.test.ts \
  tests/unit/features/macro/model/macroPageRegistry.test.ts \
  tests/unit/features/macro/model/macroPageViewModel.test.ts \
  tests/unit/features/macro/model/macroTableColumns.test.ts \
  tests/unit/features/macro/model/macroChartModel.test.ts \
  tests/unit/features/macro/model/macroModulePresentation.test.ts \
  tests/unit/features/macro/model/macroCorrelationModel.test.ts \
  tests/component/features/cockpit/ui/AppSidebar.test.tsx \
  tests/component/features/macro/MacroShell.test.tsx \
  tests/component/features/macro/MacroMetricStrip.test.tsx \
  tests/component/features/macro/MacroTableFrame.test.tsx \
  tests/component/features/macro/MacroModulePages.test.tsx \
  tests/component/features/macro/MacroAssetCorrelationPage.test.tsx \
  tests/routes/macro.route.test.tsx
```

Expected: pass.

- [ ] **Step 3: Run frontend gates**

```bash
cd web
npm run lint
npm run typecheck
npm run build
npm run test:e2e -- macro-terminal.spec.ts --project=desktop-1366
npm run test:e2e -- macro-responsive-audit.spec.ts --project=desktop-1366
```

Expected: pass.

- [ ] **Step 4: Run full project gate before merge**

```bash
cd /Users/qinghuan/Documents/code/parallax
make check-all
```

Expected: pass. If unrelated backend or integration tests fail, record exact output and classify before changing unrelated code.

- [ ] **Step 5: Build and run Docker smoke after merge approval**

```bash
make docker-up
make docker-status
```

Expected: app service and PostgreSQL healthy. Open `http://127.0.0.1:8765/macro`, `/macro/assets`, `/macro/assets/correlation`, and `/macro/rates/yield-curve` for visual smoke.

- [ ] **Step 6: Commit final cleanup**

```bash
git status --short
git add web docs/superpowers/specs/active/2026-05-26-macro-responsive-ui-layout-hard-cut-cn.md
git commit -m "chore: verify macro responsive hard cut"
```

Expected: commit only if final cleanup changed files. If there are no changes after prior task commits, skip this commit.

## Acceptance Mapping

| Spec AC | Plan coverage |
|---------|---------------|
| AC1 overview no orphan card | Task 4 metrics/panel primitives, Task 6 overview page renderer, Task 8 CSS guard, Task 9 responsive audit |
| AC2 KPI labels never split vertically | Task 4 `MacroMetricStrip`, Task 8 wrapping guard, Task 9 fragmentation audit |
| AC3 mobile no overflow/overlap/clipped controls | Task 5 table frame, Task 8 breakpoints, Task 9 route sweep |
| AC4 bounded table/matrix scroll | Task 5 `MacroTableFrame`, Task 7 matrix rehost, Task 9 table frame audit |
| AC5 correlation shares shell/header grammar | Task 3 generic shell header, Task 7 matrix page |
| AC6 32 product + 5 hidden-supported route sweep | Task 1 route catalog, Task 9 Playwright sweep |
| AC7 frontend architecture tests pass | Task 8 static guard, Task 10 frontend gates |
| AC8 shared primitives and no duplicate route CSS | Task 4 primitives, Task 6 deleted wrappers, Task 8 forbidden selector guard |

## Subagent Execution Ownership

- Agent A: Task 1 and Task 2. Owns route contract and sidebar only.
- Agent B: Task 3 and shell tests. Owns macro shell/header only.
- Agent C: Task 4 and Task 6. Owns module presentation and page renderers.
- Agent D: Task 5 and Task 7. Owns table frame and matrix rehost.
- Agent E: Task 8 and Task 9. Owns architecture and Playwright audit.
- Integrator: Task 10. Reviews diffs, resolves conflicts, runs gates, and removes any accidental compatibility remnants.

Workers are not alone in the codebase. Each worker must avoid reverting edits from other workers, must stay inside its ownership set, and must update imports/tests to match already-landed tasks.
