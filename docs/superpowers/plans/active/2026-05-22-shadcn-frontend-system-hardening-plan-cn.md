# Shadcn Frontend System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current shadcn sidebar migration into a coherent frontend system: fix the mobile shell regression, remove stale compatibility code, make the sidebar visually production-grade, and standardize routes, loading states, responsive layout, and shared UI primitives.

**Architecture:** Use shadcn/ui as the owned component foundation, not a sidebar-only dependency. The app shell should be `SidebarProvider + AppSidebar + SidebarInset + route outlet`; route modules should own route data and lazy loading; shared UI should expose modern primitives for buttons, tabs, toggles, states, and panels. No dual-path compatibility layer remains after each migration slice.

**Tech Stack:** React 19, React Router 6.30 data routers, Vite, Tailwind 4, shadcn/ui, Radix UI primitives, lucide-react, TanStack Query, Vitest, React Testing Library, Playwright, Docker Compose.

---

## Scope

- **In:** Frontend shell, sidebar visual redesign, responsive CSS contract, route architecture, shadcn primitive adoption, loading/error/empty state unification, obsolete compatibility cleanup, frontend docs/tests, Docker smoke verification.
- **Out:** Backend scoring, Kappa/CQRS projections, provider contracts, new product pages, auth changes, and worker throughput tuning except when `/readyz` blocks the final Docker verification evidence.

## Non-Negotiables

- Do not keep compatibility branches for retired navigation surfaces. Delete old side rail/mobile nav selectors, docs, tests, imports, and story-like fixtures once replacement tests pass.
- Do not introduce a second custom design system beside shadcn. Existing wrappers may stay only if they delegate to shadcn primitives and keep one public API.
- Do not leave route-wide imports that force every major page into the initial bundle when React Router can lazy-load the route.
- Do not ship visual fixes without browser evidence at `1366x768`, `834x1194`, and `390x844`.
- Do not claim Docker is ready unless `/healthz` and `/readyz` evidence are recorded. If `/readyz` is red for a backend worker, isolate it and either fix the worker issue or file it as an explicit backend blocker before frontend completion.

## Current Evidence

- Mobile topbar overlap risk: `web/src/features/cockpit/ui/CockpitTopbar.css:370` sets mobile `.topbar { min-height: 0; padding: 8px; }`; `web/src/features/cockpit/ui/cockpitShellContract.css:36` repeats mobile grid rules but does not lock the shell row height.
- Stale architecture contract: `docs/FRONTEND.md:73` still names `.desktop-side-rail` and `.mobile-route-nav`; `docs/FRONTEND.md:128` still requires mobile route nav coverage.
- Route composition bottleneck: `web/src/routes/AppRoutes.tsx:37` owns cross-feature queries, socket snapshots, notification state, badges, topbar props, and route elements; `web/src/app/AppRoot.tsx:23` still uses `<BrowserRouter>`, so React Router `Route.lazy` cannot be used.
- Shadcn underuse: `web/src/shared/ui/button.tsx` exists, but business controls still use custom raw buttons in `IconButton`, `RadarControls`, `SearchIntelControls`, topbar controls, macro/news/signal tabs, and queue controls.
- Loading state drift: `RemoteState`, `RouteFallback`, and local skeletons such as `StocksSkeleton` each render different structures.
- Test fixture drift: `web/src/features/signal-lab/test/fixtures/*.ts` lives under production `web/src`, contradicting the frontend test map.
- Sidebar polish gap: `AppSidebar` is structurally correct but visually plain, lacks a mature collapsed/expanded hierarchy, keeps visible helper copy in the footer, and does not yet use a refined active rail, badge, density, or nested disclosure treatment.

## File Structure

### Shell and navigation

- Modify `web/src/features/cockpit/ui/AppSidebar.tsx`: refine app sidebar composition, add nested disclosure behavior where useful, close mobile drawer reliably, remove instructional footer copy.
- Modify `web/src/features/cockpit/ui/AppSidebar.css`: rebuild sidebar visual language with tokens, active rail, collapsed icon polish, group spacing, badge treatment, and mobile drawer density.
- Modify `web/src/features/cockpit/ui/appNavigation.ts`: keep one canonical navigation tree; remove obsolete product labels such as retired decisions/scope concepts; ensure second-level nav is real route information, not decorative.
- Modify `web/src/features/cockpit/ui/CockpitShell.tsx`: keep one shell composition and remove duplicate hotkey/listener logic if shared with search shell.
- Modify `web/src/features/cockpit/ui/SearchShell.tsx`: delegate common shell behavior instead of duplicating `SidebarProvider`, `AppSidebar`, `NotificationLayer`, and hotkey wiring.
- Modify `web/src/features/cockpit/ui/CockpitTopbar.tsx`: route all icon/search controls through shared shadcn-based primitives.
- Modify `web/src/features/cockpit/ui/CockpitTopbar.css`: fix mobile row height and remove one-off button styling after primitive migration.
- Modify `web/src/features/cockpit/ui/cockpitShell.css`: keep layout-only shell rules.
- Modify `web/src/features/cockpit/ui/cockpitShellContract.css`: own breakpoints and row sizing; remove retired side-rail/mobile-route-nav contract.

### Shadcn shared UI system

- Modify `web/src/shared/ui/button.tsx`: keep as canonical button primitive; support app-needed sizes/variants only.
- Modify `web/src/shared/ui/IconButton.tsx`: either delete and migrate callers, or turn it into a thin `Button size="icon"` wrapper with no separate CSS contract.
- Create `web/src/shared/ui/badge.tsx`: shadcn Badge primitive for nav counts, status pills, and score tags.
- Create `web/src/shared/ui/alert.tsx`: shadcn Alert primitive for error and degraded states.
- Create `web/src/shared/ui/tabs.tsx`: shadcn/Radix Tabs wrapper to replace direct feature imports from `@radix-ui/react-tabs`.
- Create `web/src/shared/ui/toggle-group.tsx`: shadcn ToggleGroup wrapper for window/scope/status segmented controls.
- Create `web/src/shared/ui/select.tsx` only if a feature has a real option menu that should not be tabs/toggles.
- Create `web/src/shared/ui/panel.tsx`: app-specific but shadcn-composed `Panel`, `PanelHeader`, `PanelBody`, and `PanelActions` primitives for dense operational screens.
- Create `web/src/shared/ui/PageState.tsx`: unified `Loading`, `Empty`, `Error`, and `Stale` states composed from `Skeleton`, `Alert`, `Button`, and `Panel`.
- Delete or rewrite `web/src/shared/ui/RemoteState.tsx` and `web/src/shared/ui/RemoteState.css` after all callers migrate.

### Route architecture

- Modify `web/src/app/AppRoot.tsx`: replace `<BrowserRouter>` with `createBrowserRouter` + `RouterProvider`.
- Replace `web/src/routes/AppRoutes.tsx` with route config and small shell data providers; remove cross-feature query ownership from the root route file.
- Create `web/src/routes/router.tsx`: canonical data-router configuration.
- Create `web/src/routes/shell.route.tsx`: shell layout route that owns only shell chrome data.
- Create route modules where missing:
  - `web/src/routes/live.route.tsx`
  - `web/src/routes/stocks.route.tsx`
  - `web/src/routes/news.route.tsx`
  - `web/src/routes/macro.route.tsx`
  - `web/src/routes/watchlist.route.tsx`
  - `web/src/routes/search.route.tsx`
  - `web/src/routes/ops.route.tsx`
  - `web/src/routes/signal-lab.route.tsx`
  - `web/src/routes/signal-lab.pulse.route.tsx`
  - `web/src/routes/token-target.route.tsx`
- Create `web/src/routes/shellChromeData.ts`: shell-only status, notification, badge, and topbar model assembly with no page rendering responsibility.

### Feature migrations

- Modify `web/src/shared/ui/RadarControls.tsx`: migrate window/scope controls to `ToggleGroup`; remove `.active` custom button styling.
- Modify `web/src/shared/ui/HandleFilter.tsx`: migrate to shadcn `Input` or a focused app wrapper.
- Modify `web/src/features/search/ui/SearchIntelControls.tsx`: reuse `RadarControls` or shared `ToggleGroup` primitives.
- Modify `web/src/features/stocks/ui/StocksRadarPage.tsx`: remove local `StocksSkeleton`; use `PageState.Loading` or `DataTableState`.
- Modify `web/src/features/news/NewsPage.tsx`: replace direct Radix Tabs import with shared `Tabs`.
- Modify `web/src/features/macro/MacroPage.tsx`: replace direct Radix Tabs import with shared `Tabs`; split oversized route sections only where touched.
- Modify `web/src/features/signal-lab/ui/SignalLabPulse.tsx` and `web/src/features/signal-lab/ui/SignalLabWorkbench.tsx`: replace direct Radix Tabs and raw status buttons with shared primitives.
- Modify `web/src/features/watchlist/ui/HandleTimeline.tsx`: replace ad hoc tab buttons with shared `Tabs` or `ToggleGroup`.
- Modify `web/src/features/ops/ui/OpsDiagnosticsPage.tsx`: migrate queue selector/buttons to shared primitives when it intersects loading/state cleanup.
- Move `web/src/features/signal-lab/test/fixtures/*` to `web/tests/fixtures/signal-lab/` and update imports.

### Tests and docs

- Modify `docs/FRONTEND.md`: update source map, shell contract, shadcn primitive policy, route lazy policy, loading state policy, and UI verification checklist.
- Modify `web/tests/architecture/cssResponsiveContract.test.ts`: assert sidebar/sheet/topbar contract, not retired mobile route nav.
- Modify `web/tests/architecture/cssArchitectureHarness.test.ts`: reject reintroduction of retired side rail/mobile nav selectors and raw shared active-button patterns.
- Modify `web/tests/architecture/frontendArchitecture.test.ts` or equivalent import-boundary test: reject direct `@radix-ui/react-tabs` imports outside `shared/ui/tabs.tsx` and reject test fixtures under `web/src`.
- Modify route/component tests to assert shared state primitives, sidebar accessibility, mobile drawer close behavior, and same-tab navigation.
- Modify Playwright specs under `web/tests/e2e/golden-paths/`: add screenshots/locator checks for desktop expanded sidebar, desktop collapsed rail, tablet drawer trigger, mobile drawer, topbar/content non-overlap, and route lazy smoke.

---

## Task 1: Stabilize Runtime Baseline and Mobile Shell Contract

**Files:**
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.css`
- Modify: `web/src/features/cockpit/ui/cockpitShellContract.css`
- Modify: `web/tests/e2e/golden-paths/mobile-shell.spec.ts`
- Modify: `web/tests/e2e/golden-paths/tablet-shell.spec.ts`
- Modify: `docs/FRONTEND.md`

- [ ] **Step 1: Write failing mobile non-overlap test**

  Add a Playwright assertion that loads `/` at `390x844`, captures `.topbar` and `.center-column`, and fails if `topbar.bottom > centerColumn.top`. Also assert the sidebar trigger, search input, Ops button, and notification button fit inside `.topbar`.

  Run:

  ```bash
  cd web && npm run test:e2e -- --project=mobile-390 web/tests/e2e/golden-paths/mobile-shell.spec.ts
  ```

  Expected before fix: FAIL with topbar/content overlap or control containment failure.

- [ ] **Step 2: Fix shell sizing at the contract layer**

  Set a single mobile topbar height token in `cockpitShellContract.css`, for example `--cockpit-mobile-topbar-height: 48px`, and ensure `.topbar` uses `min-height` and `height` consistently at `max-width: 767px`. Remove the `min-height: 0` override from `CockpitTopbar.css`.

- [ ] **Step 3: Remove stale responsive documentation**

  In `docs/FRONTEND.md`, replace `.desktop-side-rail` and `.mobile-route-nav` references with the shadcn sidebar/sheet contract. Update the mobile/tablet verification checklist to require sidebar drawer access and topbar/content non-overlap.

- [ ] **Step 4: Verify shell contract**

  Run:

  ```bash
  cd web && npm run test:e2e -- --project=mobile-390 web/tests/e2e/golden-paths/mobile-shell.spec.ts
  cd web && npm run test:e2e -- --project=tablet-834 web/tests/e2e/golden-paths/tablet-shell.spec.ts
  cd web && npm run test:architecture
  ```

  Expected: all pass; no tests mention `mobile-route-nav` or `desktop-side-rail`.

---

## Task 2: Redesign AppSidebar as a Product-Grade Navigation Surface

**Files:**
- Modify: `web/src/features/cockpit/ui/AppSidebar.tsx`
- Modify: `web/src/features/cockpit/ui/AppSidebar.css`
- Modify: `web/src/features/cockpit/ui/appNavigation.ts`
- Modify: `web/src/shared/ui/sidebar.tsx` only if an upstream shadcn extension is needed.
- Test: `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`
- Test: `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts`

- [ ] **Step 1: Write visual/accessibility component tests**

  Assert the sidebar renders exactly three navigation groups, active route has `aria-current`/active state, badges are present for Token/Stocks/News, Macro subroutes are reachable, and the footer contains status affordance only, not instructional copy.

  Run:

  ```bash
  cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
  ```

  Expected before redesign: FAIL on footer copy, disclosure behavior, or missing refined states.

- [ ] **Step 2: Improve information architecture**

  Keep `appNavigation.ts` as the only nav tree. Use second-level menu only where it reduces cognitive load:
  - Radar: Token Radar, Stocks.
  - Intel: News, Macro with Overview/Assets/Correlation, Watchlist, Signal Lab.
  - System: Ops.

  Do not restore removed `decisions` or `scope` navigation concepts.

- [ ] **Step 3: Add mature sidebar interaction**

  Use shadcn sidebar primitives and `@radix-ui/react-collapsible` where nested Macro routes need disclosure. Add `SidebarRail` for desktop collapse affordance if not already exposed. Ensure mobile drawer closes after navigation through `useSidebar().setOpenMobile(false)`.

- [ ] **Step 4: Redesign sidebar CSS**

  Replace the current plain treatment with a dense trading-desk sidebar:
  - Strong active left rail or inset marker.
  - Small uppercase group labels with enough contrast.
  - Collapsed icon mode with shadcn tooltip behavior.
  - Badge pills aligned and clipped safely.
  - Mobile sheet width and spacing optimized for touch.
  - No visible shortcut/instruction text.

- [ ] **Step 5: Verify sidebar visuals in browser**

  Run:

  ```bash
  cd web && npm run test:e2e -- --project=desktop-1366 web/tests/e2e/golden-paths/sidebar-navigation.spec.ts
  cd web && npm run test:e2e -- --project=mobile-390 web/tests/e2e/golden-paths/sidebar-navigation.spec.ts
  ```

  Capture screenshots for desktop expanded, desktop collapsed, and mobile drawer in the verification artifact.

---

## Task 3: Make Shadcn the Shared UI Foundation

**Files:**
- Modify: `web/src/shared/ui/button.tsx`
- Modify or delete: `web/src/shared/ui/IconButton.tsx`
- Modify or delete: `web/src/shared/ui/IconButton.css`
- Create: `web/src/shared/ui/badge.tsx`
- Create: `web/src/shared/ui/alert.tsx`
- Create: `web/src/shared/ui/tabs.tsx`
- Create: `web/src/shared/ui/toggle-group.tsx`
- Create: `web/src/shared/ui/panel.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- Modify: `web/src/shared/ui/RadarControls.tsx`
- Modify: `web/src/features/search/ui/SearchIntelControls.tsx`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/macro/MacroPage.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabWorkbench.tsx`
- Modify: `web/src/features/watchlist/ui/HandleTimeline.tsx`

- [ ] **Step 1: Add architecture tests for primitive ownership**

  Reject direct `@radix-ui/react-tabs` imports outside `web/src/shared/ui/tabs.tsx`. Reject new raw segmented controls using `button.active` when `ToggleGroup` can express the state.

  Run:

  ```bash
  cd web && npm run test:architecture
  ```

  Expected before migration: FAIL on current direct Radix tabs and raw active-button controls.

- [ ] **Step 2: Add shared primitives**

  Add app-owned shadcn wrappers for Badge, Alert, Tabs, ToggleGroup, and Panel. Keep APIs small and variant names domain-neutral: `default`, `muted`, `outline`, `danger`, `success`, `warning`.

- [ ] **Step 3: Migrate button and segmented controls**

  Convert `IconButton` callers to `Button size="icon"` or make `IconButton` a zero-CSS wrapper around `Button`. Convert `RadarControls` and `SearchIntelControls` to `ToggleGroup`; delete obsolete `.active` selectors once migrated.

- [ ] **Step 4: Migrate tabs**

  Replace feature direct Radix Tabs imports with `@shared/ui/tabs`. Remove feature-local tab reset styles that duplicate shared primitive states; keep only feature layout spacing.

- [ ] **Step 5: Verify primitive migration**

  Run:

  ```bash
  cd web && npm run lint
  cd web && npm run test:architecture
  cd web && npm test -- --run
  ```

  Expected: no direct Radix tabs outside shared UI, no retired raw segmented control patterns in migrated files.

---

## Task 4: Unify Loading, Empty, Error, and Stale States

**Files:**
- Create: `web/src/shared/ui/PageState.tsx`
- Create: `web/src/shared/ui/PageState.css` only if Tailwind/classes are insufficient.
- Modify or delete: `web/src/shared/ui/RemoteState.tsx`
- Modify or delete: `web/src/shared/ui/RemoteState.css`
- Modify: `web/src/shared/ui/RouteFallback.tsx`
- Modify: `web/src/features/stocks/ui/StocksRadarPage.tsx`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Modify: `web/src/features/macro/MacroAssetCorrelationPage.tsx`
- Modify: `web/src/features/macro/MacroPage.tsx`
- Modify: `web/src/features/ops/ui/OpsDiagnosticsPage.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- Modify: `web/src/features/watchlist/ui/HandleTimeline.tsx`

- [ ] **Step 1: Write PageState component tests**

  Cover route loading, panel loading, inline loading, retryable error, empty state, and stale overlay. Assert accessible roles/labels and that retry actions use the canonical `Button`.

  Run:

  ```bash
  cd web && npm test -- --run tests/component/shared/ui/PageState.test.tsx
  ```

  Expected before implementation: FAIL because `PageState` does not exist.

- [ ] **Step 2: Implement PageState**

  Compose from `Skeleton`, `Alert`, `Button`, and `Panel`. Provide only these surfaces:
  - `PageState.Loading`
  - `PageState.Empty`
  - `PageState.Error`
  - `PageState.Stale`
  - `PageState.TableSkeleton`

- [ ] **Step 3: Replace all RemoteState callers**

  Migrate every caller found by:

  ```bash
  cd web && rg "RemoteState|SkeletonRows|PanelSkeleton|RouteStatePanel|StocksSkeleton" src tests
  ```

  Delete `RemoteState.*`, `RouteFallback` custom markup, and local skeleton components after the search returns no production callers.

- [ ] **Step 4: Verify state consistency**

  Run:

  ```bash
  cd web && npm test -- --run tests/component/shared/ui/PageState.test.tsx
  cd web && npm test -- --run
  cd web && npm run test:e2e -- --project=mobile-390 web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts
  ```

  Expected: all loading/empty/error states render without overlap and use the same primitive stack.

---

## Task 5: Replace Route Composition with Data Router and Lazy Route Modules

**Files:**
- Modify: `web/src/app/AppRoot.tsx`
- Replace: `web/src/routes/AppRoutes.tsx`
- Create: `web/src/routes/router.tsx`
- Create: `web/src/routes/shell.route.tsx`
- Create: `web/src/routes/shellChromeData.ts`
- Modify route files under `web/src/routes/*.route.tsx`
- Modify: `web/tests/routes/*.test.tsx`
- Modify: `web/tests/architecture/frontendArchitecture.test.ts`

- [ ] **Step 1: Add architecture test for route ownership**

  Assert `web/src/routes/AppRoutes.tsx` no longer imports every feature page and no route root file owns cross-feature server queries. Assert `AppRoot` uses `RouterProvider`.

  Run:

  ```bash
  cd web && npm run test:architecture
  ```

  Expected before migration: FAIL on `BrowserRouter`, root route imports, or shell-wide data ownership.

- [ ] **Step 2: Build data router**

  Replace `<BrowserRouter><AppRoutes /></BrowserRouter>` with:

  ```tsx
  const router = createBrowserRouter(routes);
  <RouterProvider router={router} fallbackElement={<PageState.Loading layout="route" label="Loading route" />} />
  ```

  Route config should use `lazy: () => import("./<route>.route")` for heavy pages.

- [ ] **Step 3: Move shell chrome data out of AppRoutes**

  Extract status, notification, sidebar badge, topbar, and hotkey model assembly into `shellChromeData.ts`. The shell route may read cross-cutting shell data, but page routes must own page data.

- [ ] **Step 4: Keep page data with page routes**

  Move live radar, stocks, news, macro, watchlist, ops, signal lab, search, and token target data hooks into their route modules or feature hooks. Do not leave compatibility props passing through the root route.

- [ ] **Step 5: Verify route lazy behavior**

  Run:

  ```bash
  cd web && npm run typecheck
  cd web && npm test -- --run tests/routes
  cd web && npm run build
  ```

  Expected: route tests pass and build output shows route chunks instead of a single large initial app chunk carrying all feature pages.

---

## Task 6: CSS Diet and Fixture Cleanup

**Files:**
- Modify: `web/src/features/ops/ui/ops.css`
- Modify: `web/src/features/search/ui/search.css`
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/shared/ui/obsidian.css`
- Modify: `web/src/features/macro/macro.css`
- Modify: `web/src/features/watchlist/ui/watchlist.css`
- Move: `web/src/features/signal-lab/test/fixtures/*` to `web/tests/fixtures/signal-lab/*`
- Modify imports that reference moved fixtures.
- Modify: `web/tests/architecture/cssArchitectureHarness.test.ts`

- [ ] **Step 1: Add fixture placement architecture test**

  Fail if `web/src/**/test/**` or `web/src/**/__fixtures__/**` exists. Production source should contain production code only.

- [ ] **Step 2: Move signal-lab fixtures**

  Move the three signal-lab fixture files into `web/tests/fixtures/signal-lab/` and update tests to import from the new path.

- [ ] **Step 3: Split oversized side-effect CSS by ownership**

  For each file above 500 lines, split only along ownership boundaries already visible in the file:
  - Route layout.
  - Table/list rows.
  - Detail panel.
  - Toolbar/controls.

  Do not create generic buckets such as `shared.css`, `misc.css`, or `legacy.css`.

- [ ] **Step 4: Tighten CSS harness**

  After the split, lower the side-effect CSS warning target to 500 lines where feasible, and reject retired selectors:

  ```text
  desktop-side-rail
  mobile-route-nav
  side-rail
  route-nav
  ```

- [ ] **Step 5: Verify CSS cleanup**

  Run:

  ```bash
  cd web && npm run test:architecture
  cd web && npm run lint
  cd web && npm run build
  ```

  Expected: no production fixtures under `web/src`, no retired navigation selectors, no oversized side-effect CSS introduced by this work.

---

## Task 7: Docker and End-to-End Verification

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-22-shadcn-frontend-system-hardening-verification-cn.md`
- Modify: `docs/TECH_DEBT.md` only if a real backend readiness blocker remains out of scope.

- [ ] **Step 1: Run full frontend gates**

  ```bash
  cd web && npm run lint
  cd web && npm run test:architecture
  cd web && npm run typecheck
  cd web && npm test -- --run
  cd web && npm run build
  cd web && npm run test:e2e
  ```

  Expected: all pass. Capture skipped test count and any Vite chunk warning.

- [ ] **Step 2: Run repository gate**

  ```bash
  make check-all
  ```

  Expected: exit code 0. Paste full output into verification artifact per `docs/WORKFLOW.md`.

- [ ] **Step 3: Rebuild and restart Docker**

  ```bash
  make docker-up
  docker compose ps
  curl -sS http://127.0.0.1:8765/healthz
  curl -sS http://127.0.0.1:8765/readyz | jq '{ok, reasons, db: .db.ok, providers: .provider_states}'
  ```

  Expected: app/postgres healthy, `/healthz` returns `ok`, `/readyz` returns `ok: true`. If `/readyz` is false because of `news_item_brief` or another backend worker, inspect logs enough to identify whether this branch caused it. If unrelated and still present, add a `docs/TECH_DEBT.md` follow-up with command evidence and do not describe frontend work as fully production-ready.

- [ ] **Step 4: Manual browser verification**

  Check:
  - Desktop `1366x768`: expanded sidebar is polished; collapse rail works; route links do not overlap content.
  - Tablet `834x1194`: sidebar is drawer/trigger driven; route content remains reachable.
  - Mobile `390x844`: topbar controls fit; drawer opens/closes; no topbar/content overlap; Live task nav remains only on live radar routes.
  - Radar row click opens same-tab route/search context, not a new browser tab.

---

## PR Breakdown

1. **PR 1 — Shell contract hotfix:** Task 1 only. Mergeable on its own; fixes mobile overlap and stale docs/tests for retired navigation.
2. **PR 2 — Sidebar visual redesign:** Task 2 only. Mergeable on top of PR 1; improves IA, nested nav, mobile drawer, collapsed rail, and sidebar polish.
3. **PR 3 — Shadcn primitive adoption:** Task 3 and Task 4. Converts buttons/tabs/toggles/loading states without keeping legacy component branches.
4. **PR 4 — Route architecture lazy split:** Task 5. Larger architectural change; depends on stable shared shell and PageState.
5. **PR 5 — CSS and fixture cleanup:** Task 6. Can start after PR 3; should land before final verification.
6. **PR 6 — Verification and Docker hardening:** Task 7. Records final evidence, Docker state, and any out-of-scope backend readiness issue.

## Rollout Order

1. Create isolated worktree from `main`: `.worktrees/shadcn-frontend-system-hardening` on branch `codex/shadcn-frontend-system-hardening`.
2. Land PR 1 first to remove the current mobile regression risk quickly.
3. Land visual sidebar PR after browser screenshots are reviewed.
4. Land shadcn primitive and state migration before route lazy split, so route fallback can reuse final primitives.
5. Land route lazy split and validate bundle output.
6. Land CSS/fixture cleanup and final verification.
7. Rebuild Docker and confirm `/healthz` and `/readyz`.

## Rollback

- PR 1 rollback: revert shell CSS/test/doc changes; low risk, but only if a replacement mobile topbar fix is ready.
- PR 2 rollback: revert sidebar visual files; route shell remains functional.
- PR 3 rollback: revert shared primitive migration as one PR; do not partially restore raw buttons or direct Radix tabs.
- PR 4 rollback: revert data-router migration to the previous router commit; do not keep both `BrowserRouter` and `RouterProvider`.
- PR 5 rollback: revert CSS/fixture movement; if test imports changed, revert the whole PR.
- Docker rollback: use the previous known-good image/commit if `/healthz` fails. If only `/readyz` fails for a pre-existing worker timeout, keep frontend rollback separate from backend remediation.

## Acceptance Criteria

- AC1. WHEN the app loads at `390x844`, THEN `.topbar` SHALL fully contain its controls and SHALL NOT overlap `.center-column`.
- AC2. WHEN users open navigation on desktop, tablet, and mobile, THEN the sidebar SHALL expose Radar, Stocks, News, Macro children, Watchlist, Signal Lab, and Ops through one shadcn sidebar/drawer system.
- AC3. WHEN searching the codebase, THEN retired navigation selectors/components SHALL NOT exist: `CockpitSideRail`, `MobileRouteNav`, `desktop-side-rail`, `mobile-route-nav`.
- AC4. WHEN feature tabs/window/scope controls render, THEN they SHALL use shared shadcn-based primitives rather than direct Radix imports or raw `.active` button groups.
- AC5. WHEN loading/error/empty states render across routes, THEN they SHALL use the unified PageState primitive and consistent accessible roles/labels.
- AC6. WHEN building the app, THEN heavy route modules SHALL be code-split through React Router data-router lazy routes.
- AC7. WHEN architecture tests run, THEN production `web/src` SHALL contain no test fixture folders.
- AC8. WHEN Docker is rebuilt and started, THEN `/healthz` SHALL return 200 and `/readyz` SHALL either return `ok: true` or an explicitly documented unrelated backend blocker with log evidence.

## Verification Commands

```bash
cd web && npm run lint
cd web && npm run test:architecture
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
cd web && npm run test:e2e
make check-all
make docker-up
docker compose ps
curl -sS http://127.0.0.1:8765/healthz
curl -sS http://127.0.0.1:8765/readyz | jq '{ok, reasons, db: .db.ok}'
```

## Open Risks

- The data-router lazy split is the largest behavioral change because route tests and route-level providers may assume `<BrowserRouter>`. Keep this as its own PR.
- Some CSS files are already large and old; splitting too aggressively can create churn. Split only touched ownership boundaries and let architecture tests prevent new bloat.
- `/readyz` currently can fail for backend worker timeouts unrelated to frontend. Treat this as a final release blocker only if the branch causes it; otherwise record it as a separate backend plan.
