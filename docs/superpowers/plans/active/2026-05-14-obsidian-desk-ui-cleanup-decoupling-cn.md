# Obsidian Desk UI Cleanup And Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Obsidian Desk hard cut by removing compatibility leftovers, moving business parsing out of UI files, and assigning visual language rules to the owning frontend modules.

**Architecture:** Keep the existing React/Vite feature-layer architecture. Feature `model/` files own view-model derivation; feature `ui/` files render props and shared Obsidian primitives; `shared/ui/obsidian` owns only reusable presentation contracts and primitives; global `styles/` keeps tokens/base only.

**Tech Stack:** React 19, Vite, TypeScript, CSS Modules with existing `:global(...)` feature style pattern, Vitest, Playwright.

---

## Current Audit Findings

- `web/src/features/live/model/TokenRadarRow.model.ts` and unused exports in `tokenCase.ts` still preserve old Heat/Quality/Propagation/Timing-era helper vocabulary.
- `SearchIntelPage.tsx` mixes route rendering, raw `radar.factor_snapshot` parsing, metric derivation, topic bucketing, and UI components in one large file.
- Signal Pulse links to internal `/search` routes with raw `<a href>`, bypassing React Router SPA navigation.
- `CockpitShell` hides the outer detail panel for `/signal-lab` and `/watchlist`, but mobile task availability still only disables detail for `/stocks`.
- `web/src/styles/obsidian-hard-cut.css` is a late-loaded global override layer containing cockpit, live, watchlist, and signal-lab selectors. This violates `docs/FRONTEND.md` ownership guidance that global styles should be tokens/base only.
- `ObsidianTone` / source type aliases are duplicated in live/search/pulse models instead of coming from one design-language contract.
- Watchlist recent-evidence metadata uses raw millisecond strings instead of the product time vocabulary used elsewhere.

## File Ownership After Cleanup

- `web/src/shared/ui/obsidianLanguage.ts`: Pure design-language type contracts (`ObsidianTone`, `ObsidianSource`, field/evidence shapes that do not import React).
- `web/src/shared/ui/obsidian.tsx`: React primitives only; imports/re-exports the shared language types.
- `web/src/features/live/model/tokenCase.ts`: Single token case adapter; no old drawer/radar metric helper exports.
- `web/src/features/search/model/searchCase.ts`: Dossier view model only.
- `web/src/features/search/model/searchRadar.ts`: Search radar summary and score/data-health view model.
- `web/src/features/search/model/searchTopicTimeline.ts`: Topic bucket derivation.
- `web/src/features/search/ui/SearchDossier.tsx`, `SearchMetricStrip.tsx`, `SearchRadarPanel.tsx`, `SearchTopicTimeline.tsx`: focused render components.
- `web/src/features/signal-lab/ui/SignalLabInspector.tsx`, `SignalLabPulse.tsx`: use React Router `Link` for internal Search Intel navigation.
- `web/src/features/cockpit/ui/cockpit.module.css`: shell/topbar/side rail rules previously in `obsidian-hard-cut.css`.
- `web/src/features/live/ui/live.module.css`: Token Radar and selected-case row/detail rules previously in `obsidian-hard-cut.css`.
- `web/src/features/watchlist/ui/watchlist.module.css`: Watchlist page rules previously in `obsidian-hard-cut.css`.
- `web/src/features/signal-lab/ui/signalLab.module.css`: Signal Pulse page rules previously in `obsidian-hard-cut.css`.
- `web/src/styles/obsidian-hard-cut.css`: deleted after rules move to owning modules.

## Task 1: Shared Language Contract And Token Legacy Cleanup

**Files:**
- Create: `web/src/shared/ui/obsidianLanguage.ts`
- Modify: `web/src/shared/ui/obsidian.tsx`
- Modify: `web/src/features/live/model/tokenCase.ts`
- Delete: `web/src/features/live/model/TokenRadarRow.model.ts`
- Test: `web/src/features/live/model/tokenCase.test.ts`

- [ ] **Step 1: Write the failing cleanup tests**

Add assertions to `tokenCase.test.ts` that import only `buildTokenCaseView` from `./tokenCase`, verify the model still labels Community/Narrative/Market/Decision, and do not import `TokenRadarRow.model`.

- [ ] **Step 2: Run red test and stale-reference scan**

Run:

```bash
npm --prefix web run test -- src/features/live/model/tokenCase.test.ts
rg "TokenRadarRow\\.model|tokenDrawerSummary|heatTitle|heatMeta|qualityTitle|qualityMeta|propagationTitle|propagationMeta" web/src -n
```

Expected: tests pass before code change, but `rg` finds stale helpers that must be removed.

- [ ] **Step 3: Implement cleanup**

Create `obsidianLanguage.ts` with pure exported types. Import those types in `obsidian.tsx`, `tokenCase.ts`, `searchCase.ts`, and `pulseCase.ts`. Move `compactLabel` and `qualityLabel` into `tokenCase.ts` as non-exported local helpers. Remove unused metric-era exports and delete `TokenRadarRow.model.ts`.

- [ ] **Step 4: Verify task**

Run:

```bash
npm --prefix web run test -- src/features/live/model/tokenCase.test.ts src/shared/ui/Obsidian.test.tsx
rg "TokenRadarRow\\.model|tokenDrawerSummary|heatTitle|heatMeta|qualityTitle|qualityMeta|propagationTitle|propagationMeta" web/src -n
npm --prefix web run typecheck
```

Expected: tests/typecheck pass; `rg` returns no matches.

## Task 2: Search Intel Model/UI Decomposition

**Files:**
- Create: `web/src/features/search/model/searchRadar.ts`
- Create: `web/src/features/search/model/searchTopicTimeline.ts`
- Create: `web/src/features/search/ui/SearchDossier.tsx`
- Create: `web/src/features/search/ui/SearchMetricStrip.tsx`
- Create: `web/src/features/search/ui/SearchRadarPanel.tsx`
- Create: `web/src/features/search/ui/SearchTopicTimeline.tsx`
- Modify: `web/src/features/search/ui/SearchIntelPage.tsx`
- Test: `web/src/features/search/model/searchCase.test.ts`
- Test: `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`

- [ ] **Step 1: Write focused tests**

Add model tests covering `buildSearchRadarSummary` for radar item present/missing and `buildTopicBuckets` for empty/non-empty topic results. Add a routing test that every sidebar section link in token search resolves to an existing section id.

- [ ] **Step 2: Run red tests**

Run:

```bash
npm --prefix web run test -- src/features/search/model/searchCase.test.ts src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx
```

Expected: new imports/functions fail until implemented.

- [ ] **Step 3: Implement decomposition**

Move raw radar parsing (`asRecord`, `numberValue`, `stringValue`, `latestCandleClose`, score family/data health extraction) from `SearchIntelPage.tsx` to `searchRadar.ts`. Move topic bucket calculation to `searchTopicTimeline.ts`. Move render-only dossier, metric strip, radar panel, and topic timeline into focused UI files. Ensure `SearchIntelPage.tsx` only orchestrates route state, query state, and component composition.

- [ ] **Step 4: Verify task**

Run:

```bash
npm --prefix web run test -- src/features/search/model/searchCase.test.ts src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx
npm --prefix web run typecheck
```

Expected: tests/typecheck pass; `SearchIntelPage.tsx` is materially smaller and contains no raw `factor_snapshot` parsing.

## Task 3: Signal Pulse Interaction And Route Coupling Cleanup

**Files:**
- Modify: `web/src/features/signal-lab/ui/SignalLabInspector.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabInspector.test.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.test.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`
- Modify: `web/src/features/live/__tests__/CockpitApp.integration.test.tsx`

- [ ] **Step 1: Write interaction tests**

Update Signal Pulse tests to assert Search Intel actions are React Router links with `/search?...` hrefs. Add a cockpit integration assertion that mobile detail is unavailable whenever the outer detail panel is hidden.

- [ ] **Step 2: Run red tests**

Run:

```bash
npm --prefix web run test -- src/features/signal-lab/ui/SignalLabInspector.test.tsx src/features/signal-lab/ui/SignalLabPulse.test.tsx src/features/live/__tests__/CockpitApp.integration.test.tsx
```

Expected: tests expose the current detail availability and link semantics gap.

- [ ] **Step 3: Implement cleanup**

Replace internal Search Intel `<a href>` with `Link` from `react-router-dom`; keep external venue links as `<a target="_blank">`. Compute `detailAvailable` from the same `shouldHideOuterDetail` route predicate used to render the detail panel.

- [ ] **Step 4: Verify task**

Run the same test command plus `npm --prefix web run typecheck`.

## Task 4: CSS Ownership Hard Cut

**Files:**
- Modify: `web/src/main.tsx`
- Modify: `web/src/features/cockpit/ui/cockpit.module.css`
- Modify: `web/src/features/live/ui/live.module.css`
- Create: `web/src/features/watchlist/ui/watchlist.module.css`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify: `web/src/features/signal-lab/ui/signalLab.module.css`
- Delete: `web/src/styles/obsidian-hard-cut.css`

- [ ] **Step 1: Move styles by ownership**

Move cockpit shell/topbar/sidebar/mobile rules to `cockpit.module.css`; live radar/detail rules to `live.module.css`; watchlist page rules to `watchlist.module.css`; signal pulse layout overrides to `signalLab.module.css`.

- [ ] **Step 2: Remove global override import**

Delete `import "./styles/obsidian-hard-cut.css";` from `main.tsx` and delete `web/src/styles/obsidian-hard-cut.css`.

- [ ] **Step 3: Verify CSS ownership**

Run:

```bash
test ! -f web/src/styles/obsidian-hard-cut.css
rg "obsidian-hard-cut|\\.cockpit-shell|\\.watchlist-page|\\.signal-lab-layout|\\.radar-row-select" web/src/styles web/src/features -n
npm --prefix web run lint
npm --prefix web run typecheck
```

Expected: hard-cut file is gone; page selectors live under `features/`, not `styles/`.

## Task 5: Watchlist Detail Polish

**Files:**
- Modify: `web/src/features/watchlist/model/watchlistCase.ts`
- Modify: `web/src/features/watchlist/model/watchlistCase.test.ts`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`

- [ ] **Step 1: Write model test**

Assert recent evidence meta is a product-readable relative/age label or `no timestamp`, never a raw millisecond string.

- [ ] **Step 2: Run red test**

Run:

```bash
npm --prefix web run test -- src/features/watchlist/model/watchlistCase.test.ts
```

Expected: the raw millisecond meta assertion fails until the model formats it.

- [ ] **Step 3: Implement model polish**

Return `receivedAtMs` from the model or format meta through the existing frontend formatter in a deterministic way. Keep all search links route-built through `searchPath`.

- [ ] **Step 4: Verify task**

Run the same test command plus `npm --prefix web run typecheck`.

## Task 6: Visual And Full Validation

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-14-obsidian-desk-ui-cleanup-decoupling-cn.md`
- Modify: `docs/superpowers/specs/active/2026-05-13-obsidian-desk-ui-hard-cut-cn.md`

- [ ] **Step 1: Browser visual comparison**

Start the Vite dev server, capture screenshots for `/`, `/watchlist`, `/signal-lab`, `/search?q=BTC`, and compare against `docs/prototypes/obsidian-desk-v2-static.html` plus existing `docs/generated/visual-audit/*` screenshots.

- [ ] **Step 2: Run frontend gates**

Run:

```bash
npm --prefix web run format
npm --prefix web run format:check
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

- [ ] **Step 3: Run final repo gate**

Run:

```bash
make check-all
```

- [ ] **Step 4: Record progress**

Update this plan and the source spec progress log with commands, results, skipped tests, visual notes, and remaining risks.

## Progress Log

| Time | Task | Progress | Validation |
|------|------|----------|------------|
| 2026-05-14 02:20 CST | Plan | Created cleanup/decoupling plan from component audit, frontend architecture rules, and prototype comparison gaps. | `git worktree list`; `git branch --show-current`; `git status --short`; `sed -n docs/FRONTEND.md docs/DESIGN_DISCIPLINE.md docs/WORKFLOW.md` |
| 2026-05-14 06:18 CST | Task 1 | Centralized Obsidian tone/source/string field contracts and removed Token Radar legacy row/model helpers. | `npm --prefix web run test -- src/features/live/model/tokenCase.test.ts src/shared/ui/Obsidian.test.tsx` passed; `npm --prefix web run typecheck` passed; legacy token helper `rg` search returned no matches. |
| 2026-05-14 06:23 CST | Task 2 | Split Search Intel route component into model builders and focused UI children for dossier, metrics, radar, and topic timeline; added section-link coverage. | `npm --prefix web run test -- src/features/search/model/searchCase.test.ts src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx` passed; `npm --prefix web run typecheck` passed. |
| 2026-05-14 06:25 CST | Task 3 | Replaced Signal Pulse internal search anchors with React Router links and aligned mobile detail availability with hidden outer-detail routes. | `npm --prefix web run test -- src/features/signal-lab/ui/SignalLabInspector.test.tsx src/features/signal-lab/ui/SignalLabPulse.test.tsx src/features/cockpit/ui/CockpitSideRail.test.tsx` passed; `npm --prefix web run typecheck` passed. |
| 2026-05-14 06:34 CST | Task 4 | Removed `styles/obsidian-hard-cut.css`, imported Watchlist styling through its own feature module, and moved obvious live/search/signal/stocks responsive rules out of Cockpit CSS. | `test ! -f web/src/styles/obsidian-hard-cut.css` passed; `rg "obsidian-hard-cut" web/src -n` returned no matches; `npm --prefix web run typecheck` passed; `npm --prefix web run build` passed. |
| 2026-05-14 06:39 CST | Task 5 | Changed Watchlist evidence meta from raw milliseconds to product-readable relative age labels. | Red test failed on raw `1700000500000`; after implementation `npm --prefix web run test -- src/features/watchlist/model/watchlistCase.test.ts` passed; `npm --prefix web run typecheck` passed. |
| 2026-05-14 06:41 CST | Task 6 | Completed frontend validation and browser visual pass for `/`, `/watchlist`, `/signal-lab`, and `/search?q=BTC`; screenshots captured under `docs/generated/visual-audit/`. | `npm --prefix web run format` passed; `npm --prefix web run format:check` passed; `npm --prefix web run lint` passed; `npm --prefix web run typecheck` passed; `npm --prefix web run test` passed (`36 files`, `161 tests`); `npm --prefix web run build` passed with existing chunk-size warning; `npm --prefix web run test:e2e` passed (`5 passed`) with expected local backend proxy warnings. |
| 2026-05-14 06:52 CST | Follow-up | Added a zero-layout WS status beacon to the topbar brand area so connection state is visible without restoring the old status-pill row. | `npm --prefix web run test -- src/features/cockpit/ui/CockpitTopbar.test.tsx` passed; `npm --prefix web run typecheck` passed; `npm --prefix web run lint` passed; `npm --prefix web run format:check` passed; `npm --prefix web run build` passed with existing chunk-size warning; browser snapshot exposed `WebSocket idle · no message yet` status in the banner. |
| 2026-05-14 06:53 CST | Repo gate | Started `make check-all`; stopped it at user request before completion. Completed portions had passed: formatting, mypy, frontend typecheck/lint/format check, unit/architecture/contract pytest (`530 passed`, `12 skipped`), and integration tests had progressed to 35% before termination. | `make check-all` intentionally interrupted after user said full run was not needed. |

## Decision Log

| Time | Decision | Rationale |
|------|----------|-----------|
| 2026-05-14 06:18 CST | Use `shared/ui/obsidianLanguage.ts` as the single language contract for tone/source/string evidence. | Keeps feature models aligned to the visual design grammar without importing React components into pure model code. |
| 2026-05-14 06:23 CST | Keep route components as data/route wiring only; move derivation and panel rendering into model/UI children. | Prevents Search Intel from becoming the next coupled page and makes prototype-language iteration local to small files. |
| 2026-05-14 06:25 CST | Internal product navigation uses Router `Link`; venue/external navigation remains `<a target="_blank">`. | Preserves SPA state for Search Intel while retaining normal browser behavior for GMGN/OKX venue exits. |
| 2026-05-14 06:34 CST | Keep route-shell CSS in Cockpit and move feature viewport rules to feature modules. | Cockpit should own layout containers and mobile task switching; feature modules should own token/search/signal/watchlist/stocks visual behavior. |
| 2026-05-14 06:39 CST | Watchlist model formats evidence meta before UI rendering. | Keeps presentation semantics out of `WatchlistPage` and prevents raw event timestamps from leaking into Obsidian evidence rows. |
| 2026-05-14 06:52 CST | Use a topbar WS beacon instead of restoring full `StatusPills`. | The user asked for connection status without taking space; an absolutely positioned beacon preserves the Obsidian desk banner density while retaining accessible status text and tooltip. |
