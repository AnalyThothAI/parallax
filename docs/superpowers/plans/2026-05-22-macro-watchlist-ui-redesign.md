# Macro Watchlist UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Macro module navigation and Watchlist source monitoring clearer, more data-dense, and easier to scan from a trader/operator point of view.

**Architecture:** Keep all business facts in existing backend contracts. Macro adds feature-owned tab navigation over the existing routed module catalog and removes the noisy per-page related-route card. Watchlist consumes the existing `/api/watchlist/handles/overview` endpoint to render a full Twitter source desk, while the selected handle still uses the existing overview, summary, and timeline hooks.

**Tech Stack:** React 19, TypeScript, React Router, TanStack Query, Radix Tabs primitive, lightweight-charts for existing Macro charts, Vitest/React Testing Library, side-effect CSS under feature-owned namespaces.

---

## Scope

This is a frontend-only hardening pass. It does not add tables, workers, provider calls, or scoring logic. Macro continues to render deterministic `/api/macro/modules/{module_id}` payloads, and Watchlist continues to render deterministic watchlist API facts.

## File Structure

- Modify `web/src/features/macro/model/macroRoutes.ts`
  - Add grouped route helpers for primary and secondary Macro tabs.
- Modify `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
  - Render tabs below the module header.
- Modify `web/src/features/macro/ui/shell/MacroShell.tsx`
  - Keep the shell as the composition boundary.
- Modify `web/src/features/macro/ui/shell/macroShell.css`
  - Style primary and secondary tabs with the existing Macro namespace.
- Modify `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
  - Remove the repeated related-page panel.
- Modify `web/src/features/macro/ui/pages/macroPages.css`
  - Remove related-route styling no longer used.
- Modify `web/tests/unit/features/macro/model/macroRoutes.test.ts`
  - Cover grouped tab helpers and correlation route placement.
- Modify `web/tests/component/features/macro/MacroShell.test.tsx`
  - Assert tab navigation is visible and active.
- Modify `web/tests/component/features/macro/MacroModulePages.test.tsx`
  - Assert repeated related-page card is no longer rendered.
- Modify `web/src/features/watchlist/model/watchlistRows.ts`
  - Expand the row view model from handle/unread/last-seen into scan-ready source stats.
- Create `web/src/features/watchlist/ui/WatchlistSourceNavigator.tsx`
  - Render the full Twitter source list and aggregate strip.
- Create `web/src/features/watchlist/ui/WatchlistSourceNavigator.css`
  - Own source-list styling under `watchlist-` selectors.
- Modify `web/src/features/watchlist/ui/WatchlistPage.tsx`
  - Fetch handles overview and compose the source navigator with the selected dossier.
- Modify `web/src/features/watchlist/ui/WatchlistHero.tsx`
  - Add selected-source context without duplicating source-list controls.
- Modify `web/src/features/watchlist/ui/WatchlistMetricStrip.tsx`
  - Keep selected-handle metrics compact.
- Modify `web/src/features/watchlist/ui/watchlist.css`
  - Rebalance layout around source navigator + dossier.
- Modify `web/src/features/watchlist/ui/watchlistResponsive.css`
  - Make source list horizontal/scrollable on smaller screens.
- Modify `web/tests/unit/features/watchlist/model/watchlistRows.test.ts`
  - Cover sorting and row stats.
- Modify `web/tests/component/features/watchlist/ui/WatchlistPage.test.tsx`
  - Cover multi-handle navigation, active handle URL, and selected dossier continuity.
- Modify `web/tests/routes/watchlist.route.test.tsx`
  - Cover route-level persisted overview usage with the source navigator.

## Task 1: Macro Route Tab Model

**Files:**
- Modify `web/src/features/macro/model/macroRoutes.ts`
- Modify `web/tests/unit/features/macro/model/macroRoutes.test.ts`

- [ ] **Step 1: Write failing tests**

Add tests that expect:

```ts
expect(macroPrimaryTabRoutes().map((route) => route.moduleId)).toEqual([
  "overview",
  "assets",
  "rates",
  "fed",
  "liquidity",
  "volatility",
  "credit",
]);
expect(macroSecondaryTabRoutes("assets").map((route) => route.href)).toEqual([
  "/macro/assets",
  "/macro/assets/equities",
  "/macro/assets/bonds",
  "/macro/assets/commodities",
  "/macro/assets/fx",
  "/macro/assets/crypto",
  "/macro/assets/crypto-derivatives",
  "/macro/assets/correlation",
]);
expect(macroActiveSection("assets/crypto")).toBe("assets");
```

- [ ] **Step 2: Verify red**

Run:

```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts
```

Expected: fail because the helper functions do not exist.

- [ ] **Step 3: Implement helper functions**

Add route helpers derived from `MACRO_MODULE_ROUTES`; include a virtual correlation tab only under `assets`.

- [ ] **Step 4: Verify green**

Run the same test command. Expected: pass.

## Task 2: Macro Workbench Tabs

**Files:**
- Modify `web/src/features/macro/ui/shell/MacroPageHeader.tsx`
- Modify `web/src/features/macro/ui/shell/macroShell.css`
- Modify `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx`
- Modify `web/src/features/macro/ui/pages/macroPages.css`
- Modify `web/tests/component/features/macro/MacroShell.test.tsx`
- Modify `web/tests/component/features/macro/MacroModulePages.test.tsx`

- [ ] **Step 1: Write failing tests**

Update Macro shell tests to expect a `navigation` named `宏观模块` with active `美股`, and update page tests to assert there is no repeated `相关页面` region.

- [ ] **Step 2: Verify red**

Run:

```bash
cd web && npm test -- --run tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroModulePages.test.tsx
```

Expected: fail because the tabs are absent and the related-page card still renders.

- [ ] **Step 3: Implement tabs and remove duplicate related card**

Render primary and secondary tab links in `MacroPageHeader`; keep accessible names, active states, and URL-backed routing. Remove the related-route panel from the frame.

- [ ] **Step 4: Verify green**

Run the same test command. Expected: pass.

## Task 3: Watchlist Source Row Model

**Files:**
- Modify `web/src/features/watchlist/model/watchlistRows.ts`
- Modify `web/tests/unit/features/watchlist/model/watchlistRows.test.ts`

- [ ] **Step 1: Write failing tests**

Extend row tests to assert the row model includes `recentSourceCount`, `recentSignalCount`, `totalSignalCount`, `summaryStatus`, `summaryIsStale`, and a stable `activityScore`, sorted by unread, recent signals, recent source events, last seen, then original order.

- [ ] **Step 2: Verify red**

Run:

```bash
cd web && npm test -- --run tests/unit/features/watchlist/model/watchlistRows.test.ts
```

Expected: fail because the row model only exposes handle, unread count, and last seen.

- [ ] **Step 3: Implement expanded row model**

Use only `WatchlistHandleRowOverview` fields plus notification unread counts. Do not derive anything from live replay or WebSocket events.

- [ ] **Step 4: Verify green**

Run the same test command. Expected: pass.

## Task 4: Watchlist Source Navigator

**Files:**
- Create `web/src/features/watchlist/ui/WatchlistSourceNavigator.tsx`
- Create `web/src/features/watchlist/ui/WatchlistSourceNavigator.css`
- Modify `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify `web/src/features/watchlist/ui/watchlist.css`
- Modify `web/src/features/watchlist/ui/watchlistResponsive.css`
- Modify `web/tests/component/features/watchlist/ui/WatchlistPage.test.tsx`
- Modify `web/tests/routes/watchlist.route.test.tsx`

- [ ] **Step 1: Write failing tests**

Add component and route assertions that `/watchlist` renders the full source list from `/api/watchlist/handles/overview`, highlights the selected handle, and clicking another handle updates the URL to `?handle=<handle>&timeline_scope=<current>`.

- [ ] **Step 2: Verify red**

Run:

```bash
cd web && npm test -- --run tests/component/features/watchlist/ui/WatchlistPage.test.tsx tests/routes/watchlist.route.test.tsx
```

Expected: fail because the source navigator does not exist and the page does not fetch handle overview rows.

- [ ] **Step 3: Implement navigator**

`WatchlistPage` should call `useWatchlistHandlesOverviewQuery`, merge API rows with configured handles through `emptyWatchlistHandleRow`, build sorted rows with `buildWatchlistRows`, and render `WatchlistSourceNavigator`.

- [ ] **Step 4: Verify green**

Run the same test command. Expected: pass.

## Task 5: Visual Polish And Verification

**Files:**
- Modify feature CSS only as needed under `macro-` and `watchlist-` namespaces.

- [ ] **Step 1: Run focused frontend tests**

```bash
cd web && npm test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/watchlist/model/watchlistRows.test.ts tests/component/features/watchlist/ui/WatchlistPage.test.tsx tests/routes/watchlist.route.test.tsx
```

- [ ] **Step 2: Run architecture and lint gate**

```bash
cd web && npm run lint
```

- [ ] **Step 3: Run typecheck**

```bash
cd web && npm run typecheck
```

- [ ] **Step 4: Browser verification**

Start Vite if needed:

```bash
cd web && npm run dev -- --host 127.0.0.1 --port 5173
```

Open `/macro`, `/macro/assets`, `/macro/assets/correlation`, and `/watchlist` at desktop and mobile widths. Confirm tabs do not overlap, charts still render, Watchlist source rows remain reachable, and selected-handle dossier content is preserved.

## Self-Review

- Spec coverage: Macro tabs, related-page cleanup, Watchlist multi-handle source desk, existing data contracts, mature chart reuse, and verification are all mapped to tasks.
- Placeholder scan: No `TBD`, open-ended implementation placeholders, or unspecified commands remain.
- Type consistency: Helper names and row fields are consistent across model, UI, and tests.
