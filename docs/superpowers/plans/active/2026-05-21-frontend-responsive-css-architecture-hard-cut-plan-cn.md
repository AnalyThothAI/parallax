# Frontend Responsive CSS Architecture Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the web app reliably usable on mobile and replace scattered CSS overrides with a documented, test-enforced CSS architecture.

**Architecture:** Keep the existing React/Vite/TanStack stack. Fix the cockpit shell first, then introduce CSS cascade/ownership gates, then migrate each high-risk feature surface to explicit desktop/tablet/mobile contracts. Avoid UI-kit migration; use CSS Modules, layered side-effect CSS, existing design tokens, and Playwright viewport gates.

**Tech Stack:** React 19, Vite 8, React Router, TanStack Query/Table, CSS Modules, Tailwind CSS v4 import, Playwright, Vitest, Testing Library, MSW.

---

## Current Execution State — 2026-05-21

- Done: P0 mobile shell recovery, mobile route cold-load matrix, deterministic E2E mocks, Docker build/start health check.
- Done: real cascade layers are now active for base/primitives/shell/features side-effect CSS; the architecture test no longer allowlists unlayered app CSS except `styles/tailwind.css`.
- Done: final shell breakpoint decisions moved into `web/src/features/cockpit/ui/cockpitShellContract.css`, so old `cockpit.css` source-order drift cannot decide rail/nav visibility.
- Done: mobile task panel visibility is shell-owned; feature CSS is blocked from owning `[data-mobile-task-panel]`, `.mobile-task-radar`, `.mobile-task-tape`, or `.mobile-task-lab`.
- Done: tablet shell regression coverage proves `834px` hides desktop rail, shows compact route navigation, hides mobile task nav, and can navigate to Stocks.
- Still open: split oversized CSS files by responsibility, move component-specific selectors to CSS Modules, and convert remaining data-dense mobile surfaces beyond the tested no-overflow baseline.

---

## File Structure

### Create

- `web/tests/e2e/golden-paths/mobile-shell.spec.ts`  
  Mobile shell guard for `/`, bottom task nav, rail visibility, task switching, and search submit.
- `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`  
  Mobile cold-load guard for `/search`, `/signal-lab`, `/signal-lab/pulse/:candidateId`, `/stocks`, `/news`, `/news/:newsItemId`, `/watchlist`, `/token/:targetType/:targetId`, `/macro`, and `/ops`.
- `web/tests/e2e/support/layoutAssertions.ts`  
  Shared Playwright helpers for no document overflow, no nested overflow, vertical reachability, fixed-nav occlusion, and strict API mock coverage.
- `web/tests/architecture/cssResponsiveContract.test.ts`  
  Static CSS guard for layer usage, shell source order, file-size budget, and forbidden viewport patterns.
- `web/src/styles/primitives.css`  
  Shared primitive layer for reusable layout/control classes that are currently mixed into `shared.css`.
- `web/src/features/cockpit/ui/MobileRouteNav.tsx` or equivalent  
  Mobile top-level navigation entry for Radar, Stocks, News, Macro, Watchlist, Ops, and Search.

### Modify

- `web/playwright.config.ts`  
  Add desktop/tablet/mobile projects.
- `web/src/main.tsx`  
  Import `primitives.css` after `base.css` once Task 4 creates the file.
- `web/src/styles/base.css`  
  Clarify root scrolling contract and remove global assumptions that conflict with mobile shell.
- `web/src/styles/tokens.css`  
  Add only variables referenced by new shell or mobile route navigation CSS; do not change color language.
- `web/src/shared/ui/shared.css`  
  Split primitive/layout rules into `styles/primitives.css` or CSS Modules where ownership is local.
- `web/src/features/cockpit/ui/cockpit.css`  
  Short-term P0 fix, then split or layer shell/topbar/rail/task nav rules.
- `web/src/features/cockpit/ui/CockpitShell.tsx`
- `web/src/features/cockpit/ui/SearchShell.tsx`
- `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- `web/src/features/cockpit/ui/MobileTaskNav.tsx`
- `web/src/features/live/ui/live.css`
- `web/src/features/live/ui/TokenRadarTable.tsx`
- `web/src/features/stocks/ui/stocks.css`
- `web/src/features/stocks/ui/StocksRadarPage.tsx`
- `web/src/features/news/news.css`
- `web/src/features/news/NewsPage.tsx`
- `web/src/features/search/ui/search.css`
- `web/src/features/signal-lab/ui/signalLab.css`
- `web/src/features/watchlist/ui/watchlist.css`
- `web/src/shared/ui/obsidian.css`
- `web/src/shared/ui/case-file/*.module.css`
- `web/tests/e2e/support/mockApi.ts`
- `docs/FRONTEND.md`

## Task 1: Lock The Mobile Shell Regression

**Files:**
- Create: `web/tests/e2e/golden-paths/mobile-shell.spec.ts`
- Modify: `web/playwright.config.ts`

- [ ] Add exact viewport Playwright projects using product-named profiles.

  In `web/playwright.config.ts`, add projects for:

  ```ts
  projects: [
    { name: "desktop-1366", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 720 } } },
    { name: "desktop-1920", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } } },
    { name: "tablet-834", use: { ...devices["iPad Pro 11"], viewport: { width: 834, height: 1194 } } },
    { name: "mobile-390", use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } } },
    { name: "mobile-430", use: { ...devices["Pixel 5"], viewport: { width: 430, height: 932 } } },
  ],
  ```

- [ ] Scope existing desktop-only specs so multi-project runs do not silently override project viewport.

  Existing `live-cold-load.spec.ts` and `topbar-layout.spec.ts` call `page.setViewportSize`. Either:

  - mark them with `test.describe.configure({ mode: "serial" })` plus a project guard that skips non-desktop projects; or
  - remove manual viewport calls and rely on `desktop-1366` / `desktop-1920` projects.

- [ ] Add a static test or grep gate that rejects new `page.setViewportSize` calls outside dedicated responsive specs.

- [ ] Write the failing mobile shell test.

  Test requirements:

  - install MSW mock API with `installMockApi(page)`;
  - `page.goto("/")`;
  - assert `.desktop-side-rail` is hidden;
  - assert `.mobile-task-nav` is visible;
  - assert `Radar`, `Tape`, and `Lab` nav buttons are visible;
  - assert `document.documentElement.scrollWidth <= window.innerWidth + 1`;
  - assert the active `[data-mobile-task-panel]` is visible and inactive panels are not visible;
  - click `Tape`, verify `aria-current` moved and the visible panel is `[data-mobile-task-panel="tape"]`;
  - click `Lab`, verify `aria-current` moved and the visible panel is `[data-mobile-task-panel="lab"]`;
  - preserve a `window.__routeBackSentinel` value before task switching and assert it remains unchanged to prove no route reload;
  - submit global search and assert URL contains `/search?q=test-token`.

- [ ] Run the focused test and confirm it fails before CSS changes.

  ```bash
  cd web
  npx playwright test tests/e2e/golden-paths/mobile-shell.spec.ts --project=mobile-390
  ```

  Expected before implementation: failure because the desktop rail is visible and/or mobile nav is hidden.

## Task 1.5: Make E2E Mock Coverage Strict

**Files:**
- Modify: `web/tests/e2e/support/mockApi.ts`
- Create: `web/tests/e2e/support/layoutAssertions.ts`
- Reuse or extend fixtures under `web/tests/fixtures/`

- [ ] Add deterministic mock responses for every route in the mobile matrix.

  Required endpoint coverage:

  - `/api/watchlist/handles/overview`
  - `/api/watchlist/handles/{handle}/overview`
  - `/api/watchlist/handles/{handle}/summary`
  - `/api/watchlist/handles/{handle}/timeline`
  - `/api/macro`
  - `/api/ops/diagnostics`
  - `/api/ops/queues/{queueName}`
  - `/api/news/items/{newsItemId}`
  - any existing route-level query called by `/signal-lab/pulse/:candidateId`

- [ ] Add `expectNoUnhandledApiRequests(page)` helper.

  It should collect responses with status `404` where body includes `unhandled`, then fail the test with the path list.

- [ ] Add `expectNoDocumentHorizontalOverflow(page)` helper.

  It should evaluate:

  ```ts
  document.documentElement.scrollWidth <= window.innerWidth + 1
  ```

- [ ] Add `expectNoNestedHorizontalOverflow(page, selectors)` helper.

  It should check each selector's `scrollWidth <= clientWidth + 1` unless the selector is explicitly allowed to be a horizontal chip rail.

- [ ] Add `expectScrollableToLastMeaningfulElement(page, containerSelector, targetSelector)` helper.

  It should scroll the container to the bottom, then assert the target is visible and not covered by fixed `.mobile-task-nav`.

## Task 2: Fix Cockpit Shell Source Order

**Files:**
- Modify: `web/src/features/cockpit/ui/cockpit.css`
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`

- [ ] In `cockpit.css`, make the source order mobile-safe.

  Required shape:

  1. base shell rules;
  2. desktop rules under `@media (min-width: 1280px)`;
  3. tablet rules under `@media (min-width: 768px) and (max-width: 1279px)`;
  4. mobile rules under `@media (max-width: 767px)` at the end of the file or in a later imported file.

- [ ] Remove duplicate `.cockpit-shell`, `.topbar`, `.cockpit-grid`, `.side-rail`, `.responsive-control-panel`, and `.mobile-task-nav` base blocks that contradict one another.

- [ ] Ensure mobile final computed behavior is:

  ```css
  @media (max-width: 767px) {
    .desktop-side-rail {
      display: none;
    }

    .responsive-control-panel {
      display: grid;
    }

    .mobile-task-nav {
      display: grid;
    }
  }
  ```

- [ ] Ensure desktop final computed behavior is:

  ```css
  @media (min-width: 1280px) {
    .desktop-side-rail {
      display: grid;
    }

    .responsive-control-panel,
    .mobile-task-nav {
      display: none;
    }
  }
  ```

- [ ] Run the mobile shell test again and make it pass.

  ```bash
  cd web
  npx playwright test tests/e2e/golden-paths/mobile-shell.spec.ts --project=mobile-390
  ```

## Task 3: Add Static CSS Contract Tests

**Files:**
- Create: `web/tests/architecture/cssResponsiveContract.test.ts`
- Modify: `web/tests/architecture/cssOwnership.test.ts` if shared helpers are needed

- [ ] Add a test that scans all cockpit shell CSS units, not only `cockpit.css`.

  Shell CSS units include:

  - `web/src/features/cockpit/ui/*.css`
  - `web/src/features/cockpit/ui/*.module.css`

- [ ] Add a test that fails if shell CSS declares `.mobile-task-nav { display: none; }` or grouped selectors containing `.mobile-task-nav` after the last mobile `display: grid` rule.

- [ ] Add a test that fails if `.desktop-side-rail` lacks a mobile hidden rule.

- [ ] Add a test that fails if feature CSS outside `features/cockpit` owns shell selectors:

  - `.cockpit-shell`
  - `.cockpit-grid`
  - `.center-column`
  - `.topbar`
  - `.desktop-side-rail`
  - `.mobile-task-nav`
  - `.responsive-control-panel`

- [ ] Add a test that reports side-effect CSS files above 700 lines.

  Temporary allowlist:

  ```ts
  const oversizedSideEffectCss = new Set([
    "features/live/ui/live.css",
    "shared/ui/shared.css",
    "features/signal-lab/ui/signalLab.css",
    "features/cockpit/ui/cockpit.css",
    "features/news/news.css",
    "features/macro/macro.css",
    "features/search/ui/search.css",
    "features/ops/ui/ops.css",
    "shared/ui/obsidian.css",
    "features/watchlist/ui/watchlist.css",
  ]);
  ```

  The assertion should fail for new oversized files and include a message that each allowlisted file must be reduced during this plan.

- [ ] Add a test that fails if new side-effect feature CSS omits an `@layer app.features` or `@layer app.shell` declaration after the layer migration task is complete.

- [ ] Add a post-migration test that fails on any unlayered side-effect CSS file not explicitly allowlisted.

- [ ] Run architecture tests.

  ```bash
  cd web
  npm test -- --run tests/architecture/cssOwnership.test.ts tests/architecture/cssResponsiveContract.test.ts
  ```

## Task 4: Establish CSS Layers And Primitive Ownership

**Files:**
- Create: `web/src/styles/primitives.css`
- Modify: `web/src/main.tsx`
- Modify: `web/src/styles/base.css`
- Modify: `web/src/shared/ui/shared.css`
- Modify: `web/src/shared/ui/RemoteState.tsx`
- Modify: `web/src/shared/ui/TokenProfileCard.tsx`

- [ ] Add app layer declaration.

  In the earliest app CSS import that is safe for all browsers, declare:

  ```css
  @layer app.base, app.primitives, app.shell, app.features, app.overrides;
  ```

- [ ] Move reusable primitive selectors from `shared/ui/shared.css` into `styles/primitives.css`.

  Candidate selectors:

  - `.remote-state*`
  - low-level metric strips
  - generic empty/error/loading panels
  - generic icon/text utility classes that are not feature-specific

- [ ] Wrap primitive CSS in:

  ```css
  @layer app.primitives {
    /* primitive rules */
  }
  ```

- [ ] Keep feature-specific token/radar/search/signal selectors out of `primitives.css`.

- [ ] Wrap every existing side-effect CSS file in an explicit app layer or add it to a temporary allowlist with the exact task that removes it.

  Required side-effect files:

  - `features/cockpit/ui/cockpit.css` -> `@layer app.shell`
  - `features/live/ui/live.css` -> `@layer app.features`
  - `features/news/news.css` -> `@layer app.features`
  - `features/search/ui/search.css` -> `@layer app.features`
  - `features/signal-lab/ui/signalLab.css` -> `@layer app.features`
  - `features/stocks/ui/stocks.css` -> `@layer app.features`
  - `features/watchlist/ui/watchlist.css` -> `@layer app.features`
  - `features/macro/macro.css` -> `@layer app.features`
  - `features/ops/ui/ops.css` -> `@layer app.features`
  - `shared/ui/shared.css` -> split or `@layer app.primitives`
  - `shared/ui/obsidian.css` -> split or `@layer app.primitives`

- [ ] Update imports so shared primitives still load once.

  Preferred path: `main.tsx` imports `./styles/primitives.css` after `base.css`, and shared components stop importing `shared.css` if all needed selectors moved.

- [ ] Run lint, typecheck, and component tests that render shared UI.

  ```bash
  cd web
  npm run lint
  npm run typecheck
  npm test -- --run tests/component/shared/ui
  ```

## Task 5: Split Cockpit CSS Into Focused Ownership Units

**Files:**
- Modify or create CSS Modules under `web/src/features/cockpit/ui/`
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`
- Modify: `web/src/features/cockpit/ui/SearchShell.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- Modify: `web/src/features/cockpit/ui/MobileTaskNav.tsx`
- Create or modify: `web/src/features/cockpit/ui/MobileRouteNav.tsx`
- Modify: `web/tests/component/features/cockpit/ui/*.test.tsx`
- Modify: `web/tests/e2e/golden-paths/topbar-layout.spec.ts`
- Modify: `web/tests/e2e/golden-paths/mobile-shell.spec.ts`

- [ ] Split cockpit responsibilities into shell, topbar, side rail, and mobile task nav style units.

  Acceptable options:

  - CSS Modules per component; or
  - one layered side-effect file per component, each under `@layer app.shell`.

- [ ] Preserve stable semantic hooks for tests using either roles, aria labels, or `data-testid`.

  Do not keep global class names only for test convenience if CSS Modules would otherwise be cleaner.

- [ ] Keep `CockpitShell` as the only owner of page-level grid and scroll contract.

- [ ] Keep `CockpitTopbar` as the only owner of topbar row/column behavior.

- [ ] Keep `CockpitSideRail` as desktop-only navigation and filter rail.

- [ ] Keep `MobileTaskNav` as mobile-only task switcher.

- [ ] Add a mobile top-level route navigation affordance for Radar, Stocks, News, Macro, Watchlist, Ops, and Search.

  Acceptable UI forms:

  - compact route drawer opened from topbar;
  - bottom nav overflow/menu item;
  - command-style route switcher.

  It must not rely on the desktop side rail being visible.

- [ ] Include `SearchShell` in the split.

  `/search` must preserve:

  - global search input;
  - notification access;
  - Main/Home affordance on mobile;
  - no desktop rail;
  - usable stacked result/case content.

- [ ] Run cockpit unit/component tests and e2e shell tests.

  ```bash
  cd web
  npm test -- --run tests/component/features/cockpit/ui
  npx playwright test tests/e2e/golden-paths/topbar-layout.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts
  ```

## Task 6: Harden Token Radar Mobile Surface

**Files:**
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Modify: `web/src/features/live/ui/live.css` or new CSS Modules
- Modify: `web/tests/e2e/golden-paths/live-cold-load.spec.ts`
- Modify: `web/tests/e2e/golden-paths/mobile-shell.spec.ts`

- [ ] Make desktop Token Radar retain dense sortable table behavior.

- [ ] Make mobile Token Radar render as a card/list layout with these visible facts:

  - token symbol/name/logo;
  - score;
  - decision tag;
  - narrative summary / reason;
  - social counts;
  - key market facts;
  - GMGN/listed actions.

- [ ] Remove dependency on `min-width: 1060px` for the mobile rendering path.

- [ ] Keep sorting controls reachable on mobile.

- [ ] Add mobile e2e assertions for a radar row:

  - row article visible;
  - score visible;
  - narrative text visible;
  - GMGN link visible;
  - no document-level horizontal overflow.

- [ ] Run live tests.

  ```bash
  cd web
  npm test -- --run tests/unit/features/live tests/component/features/live
  npx playwright test tests/e2e/golden-paths/live-cold-load.spec.ts --project=chromium-desktop
  npx playwright test tests/e2e/golden-paths/mobile-shell.spec.ts --project=mobile-390
  ```

## Task 7: Convert Stocks To Mobile Cards

**Files:**
- Modify: `web/src/features/stocks/ui/StocksRadarPage.tsx`
- Modify: `web/src/features/stocks/ui/stocks.css` or new CSS Module
- Modify: `web/tests/component/features/stocks/ui/StocksRadarPage.test.tsx`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`

- [ ] Keep desktop stock radar table.

- [ ] Add mobile card/list markup or CSS grid that does not require `min-width: 560px`.

- [ ] Show at minimum symbol, latest quote state, market move, OI/funding or availability, and source status.

- [ ] Add component test for mobile layout by rendering the page and asserting card semantics.

- [ ] Add mobile route test for `/stocks`.

- [ ] Run focused tests.

  ```bash
  cd web
  npm test -- --run tests/component/features/stocks/ui/StocksRadarPage.test.tsx
  npx playwright test tests/e2e/golden-paths/mobile-route-cold-load.spec.ts --project=mobile-390
  ```

## Task 7.5: Harden Signal Pulse Detail Mobile Surface

**Files:**
- Modify: `web/src/features/signal-lab/ui/PulseDetailRoutePage.tsx`
- Modify: `web/src/features/signal-lab/ui/PulseDetail/*.module.css`
- Modify: `web/src/features/signal-lab/ui/signalLab.css`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`
- Modify: `web/tests/component/features/signal-lab/ui/PulseDetailRoutePage.routing.test.tsx`

- [ ] Add mobile cold-load coverage for `/signal-lab/pulse/pulse-bnb`.

- [ ] Assert the mobile detail route shows:

  - `$BNB` hero;
  - decision surface;
  - agent reasoning rail or stacked equivalent;
  - source events;
  - evidence links.

- [ ] Remove fixed three-column assumptions from `PulseHero.module.css` at mobile widths.

- [ ] Remove or override mobile-hostile inspector widths such as `minmax(360px, 0.86fr)` in `signalLab.css`.

- [ ] Add a queue-to-detail mobile flow from `/signal-lab?window=4h&scope=matched&q=BNB`.

## Task 7.6: Add Watchlist Mobile Handle Switching

**Files:**
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify: `web/src/features/watchlist/ui/watchlist.css` or new CSS Module
- Modify: `web/tests/component/features/watchlist/ui/WatchlistPage.test.tsx`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`

- [ ] Add a mobile handle switcher that uses the `handles` prop already passed through `WatchlistRoute`.

  Acceptable UI forms:

  - segmented handle rail;
  - compact select/listbox;
  - modal/sheet opened by a handle button.

- [ ] Ensure switching handle updates URL state and fetches that handle's overview, summary, and timeline.

- [ ] Add a component test that switches from `toly` to `traderpow`.

- [ ] Add a mobile e2e test for `/watchlist` that switches handles without desktop rail.

## Task 8: Harden Remaining Route Surfaces

**Files:**
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/search/ui/search.css`
- Modify: `web/src/features/signal-lab/ui/signalLab.css`
- Modify: `web/src/features/watchlist/ui/watchlist.css`
- Modify: `web/src/features/macro/macro.css` only after preserving existing dirty work
- Modify: `web/src/features/ops/ui/ops.css`
- Modify: `web/src/shared/ui/case-file/*.module.css`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`

- [ ] Add mobile cold-load assertions for `/search?q=HANSA&window=24h&scope=all`.

- [ ] Add mobile cold-load assertions for `/signal-lab?window=4h&scope=matched&q=BNB`.

- [ ] Add mobile cold-load assertions for `/signal-lab/pulse/pulse-bnb`.

- [ ] Add mobile cold-load assertions for `/news`.

- [ ] Add mobile cold-load assertions for `/news/news-row-1`.

- [ ] Add mobile cold-load assertions for `/watchlist`.

- [ ] Add mobile cold-load assertions for `/token/Asset/<fixture-target>?window=1h&scope=all`.

- [ ] Add mobile cold-load assertions for `/macro`.

- [ ] Add mobile cold-load assertions for `/ops`.

- [ ] For each route, assert:

  - a primary heading or region is visible;
  - no desktop rail is visible;
  - no page-level horizontal overflow;
  - no route-critical nested container has horizontal overflow unless explicitly allowlisted;
  - the primary route container can scroll to the last meaningful item/action;
  - fixed mobile nav does not cover the last interactive control;
  - at least one primary action or primary row/card is visible.

- [ ] Add route-specific mobile assertions:

  - Stocks: card/list facts include symbol, quote, move, source/health.
  - News: queue/card and detail summary are both reachable.
  - News detail: selected item detail is visible.
  - Macro: regime, component scores, indicator/events sections are reachable.
  - Watchlist: handle switcher, metrics, timeline card.
  - Token Case: hero, propagation, mention timeline, live market.
  - Search: input, resolver result, token case or topic result.
  - Signal Lab: list, filters, detail navigation.
  - Ops: incident board, runtime chain, queue inspector/config sections.

- [ ] Fix route CSS until every assertion passes.

  Do not convert all CSS in one pass. Work route by route and keep desktop e2e passing after each route.

## Task 9: Reduce Large Side-Effect CSS Files

**Files:**
- Modify: `web/src/features/live/ui/live.css`
- Modify: `web/src/shared/ui/shared.css`
- Modify: `web/src/features/signal-lab/ui/signalLab.css`
- Modify: `web/src/features/cockpit/ui/cockpit.css`
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/features/macro/macro.css`
- Modify: `web/src/features/search/ui/search.css`
- Modify: `web/src/features/ops/ui/ops.css`
- Modify: `web/src/shared/ui/obsidian.css`
- Modify: `web/src/features/watchlist/ui/watchlist.css`
- Modify: `web/tests/architecture/cssResponsiveContract.test.ts`

- [ ] For each oversized file, split by responsibility:

  - route shell/layout;
  - toolbar/filter controls;
  - row/card item;
  - detail/rail panel;
  - local state surfaces.

- [ ] Split `RemoteState`, `TokenProfileCard`, market timeline, replay, and token-post styles out of `shared/ui/shared.css`.

- [ ] Include `shared/ui/obsidian.css` and `features/watchlist/ui/watchlist.css` in the reduction budget.

- [ ] Prefer CSS Modules for component-specific selectors.

- [ ] Keep side-effect CSS only for route root selectors and shared page-level layout.

- [ ] Lower the side-effect CSS budget in the architecture test from 700 to 500 after the split.

- [ ] Remove allowlist entries as each file is reduced.

- [ ] Run the full frontend test suite after each two files are migrated.

  ```bash
  cd web
  npm test -- --run
  npm run test:e2e
  ```

## Task 10: Document The New Contract

**Files:**
- Modify: `docs/FRONTEND.md`
- Modify: `docs/superpowers/specs/active/2026-05-21-frontend-responsive-css-architecture-hard-cut-cn.md` if decisions changed during implementation
- Modify: `docs/generated/frontend-test-ownership.md` if frontend test ownership docs are regenerated or maintained manually

- [ ] Add a CSS Architecture section to `docs/FRONTEND.md`.

  Include:

  - cascade layer order;
  - global CSS ownership;
  - CSS Modules policy;
  - side-effect CSS file budget;
  - breakpoint policy;
  - container query guidance;
  - route responsive matrix;
  - mobile e2e verification gate.

- [ ] Update the UI Verification Gate to require desktop/tablet/mobile checks for frontend architecture changes.

- [ ] Record that UI kit migration is a non-goal unless a future product spec changes this decision.

## Task 11: Full Verification

**Files:** no code changes expected

- [ ] Run frontend lint.

  ```bash
  cd web
  npm run lint
  ```

- [ ] Run frontend typecheck.

  ```bash
  cd web
  npm run typecheck
  ```

- [ ] Run frontend unit/component/route/architecture tests.

  ```bash
  cd web
  npm test -- --run
  ```

- [ ] Run frontend build.

  ```bash
  cd web
  npm run build
  ```

- [ ] Run Playwright e2e across all projects.

  ```bash
  cd web
  npm run test:e2e
  ```

- [ ] Manually verify in browser with real app or preview server:

  - `/`
  - `/search?q=HANSA&window=24h&scope=all`
  - `/signal-lab?window=4h&scope=matched&q=BNB`
  - `/stocks`
  - `/news`
  - `/news/news-row-1`
  - `/macro`
  - `/watchlist`
  - `/ops`
  - `/signal-lab/pulse/pulse-bnb`
  - `/token/Asset/<representative-target>?window=1h&scope=all`

  Check mobile width around 390px, tablet width around 834px, and desktop width around 1366px.

## Execution Notes

- Before implementation, run `git status --short` and preserve all unrelated user changes. Do not stage unrelated PNG deletions or untracked screenshot artefacts unless the user explicitly asks.
- Commit by task or small task group. Good commit boundaries:
  - `test: add mobile shell regression coverage`
  - `fix: restore responsive cockpit shell`
  - `test: enforce responsive css contract`
  - `refactor: split cockpit shell css`
  - `fix: add mobile token radar cards`
  - `fix: add mobile stocks radar cards`
  - `docs: document frontend responsive css contract`
- Do not change backend contracts, route paths, scoring labels, or token image behavior in this plan.
