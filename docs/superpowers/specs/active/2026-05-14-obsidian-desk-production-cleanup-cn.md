# Spec — Obsidian Desk Production Cleanup

**Status**: In Progress  
**Date**: 2026-05-14  
**Branch**: `codex/obsidian-desk-production-cleanup` from `main`  
**Worktree**: `.worktrees/obsidian-desk-production-cleanup`  
**Related**: `docs/superpowers/plans/active/2026-05-14-obsidian-desk-ui-cleanup-decoupling-cn.md`, `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`

## Background

The Obsidian Desk hard cut has been merged into `main`. A fresh worktree was cut from current `main` because the old `.worktrees/obsidian-desk-ui-hard-cut` branch is no longer the source of truth.

The current `main` source already contains Obsidian primitives, feature-local CSS ownership, Watchlist as a first-class route, Search Intel decomposition, and Signal Pulse memo-first rendering. The remaining production gap is visual and structural: the app still behaves like a framed prototype window instead of a real production desktop surface, and the deployed `http://127.0.0.1:8765/` bundle can render the selected token case without the `ods-*` Obsidian styles.

Baseline measurements from the fresh worktree Vite render at `1920x1080`:

- `.cockpit-shell` renders at `1500x920`, positioned at `x=210`, `y=28`.
- `document.body.scrollHeight` is only `920`, so the app intentionally does not occupy the viewport.
- `.detail-task-panel` is `388px` wide while `.detail-drawer` expands to `1034px` height inside an `865px` panel, causing nested and mismatched scroll regions.
- Vite source render loads `ods-case` styles correctly; the live `8765` bundle reports `.selected-case-file { display: block; border: 0 }`, proving the built production CSS path is stale or not guaranteed to load shared Obsidian CSS.

## Problem

The UI still carries design-board assumptions into production:

1. The shell uses `width: min(1500px, calc(100vw - 56px))`, `height: min(920px, calc(100vh - 56px))`, `min-height: 720px`, and `margin: 28px auto`. This creates the large unused border around the app.
2. `shared.module.css` is imported after feature CSS in `main.tsx`, so old shared drawer rules can override later hard-cut feature layout rules.
3. `obsidian.module.css` is imported through `shared/ui/obsidian.tsx` but is not forced into the root CSS module keep list. A production build must not depend on component import side effects for the core case-file grammar.
4. The right detail pane is too narrow for a six-field selected case and still inherits sticky/full-viewport drawer sizing from the old drawer system.

## Docker / `8765` Diagnosis

`make docker-up` rebuilds the Docker context from the current directory. When run from the repository root, it builds the root checkout, not this fresh worktree. The project `.dockerignore` excludes `.worktrees`, so changes under `.worktrees/obsidian-desk-production-cleanup` cannot enter the image unless the command is run from that worktree or the changes are merged/copied back to the root checkout first.

Observed state on 2026-05-14:

- Running container: `parallax-main-app-1`, image `parallax-main-app`, port `8765:8765`.
- `http://127.0.0.1:8765/` serves `/assets/index-DqbcU3fJ.css` and `/assets/index-afyGRmqT.js`.
- The Vite render from this worktree serves source assets and measures `.selected-case-file { display: grid; border-top-width: 1px }`.
- The running `8765` bundle measured `.selected-case-file { display: block; border: 0 }`, which is consistent with an old or mismatched built asset.

To test this branch through Docker, stop the root container that owns `8765`, then run `make docker-up` from `/Users/qinghuan/Documents/code/parallax/.worktrees/obsidian-desk-production-cleanup`. Running `make docker-up` from `/Users/qinghuan/Documents/code/parallax` will continue to build whatever is present in the root checkout.

## Audit Alignment

This spec fixes the production viewport/CSS failure first. It does not pretend the broader architecture audit is done. Current alignment against the provided audit:

| Audit item | Current source status | This spec status |
|------------|-----------------------|------------------|
| TokenDetailDrawer is new case header over old tab body. | Still true. `TokenDetailDrawer.tsx` uses `buildTokenCaseView` for the top case, then still keeps Timeline / Posts / Score / Lab / Accounts tabs. | Not fixed here; next structural cleanup. |
| SearchIntelPage body still uses old panels. | Still true. `SearchIntelPage.tsx` still renders `SearchMetricStrip`, `SearchTwitterResults`, `SearchAgentBrief`, `search-panel`, and `search-content-grid`. | Not fixed here; next structural cleanup. |
| SignalLabWorkbench shell still uses dashboard grammar. | Still true. `SignalLabWorkbench.tsx` still renders `signal-stage-grid` and `signal-filter-bar`; `SignalLabInspector` remains the cleaner memo-first path. | Not fixed here; next structural cleanup. |
| CockpitApp is still more than a composition root. | Still true. `web/src/app/CockpitApp.tsx` still calls `useLiveData`, `useQueryClient().invalidateQueries()`, owns hotkeys, prop bags, and the route table. | Not fixed here; next structural cleanup. |
| `routes/*.tsx` are dead re-export shells. | Still true. Each route file is a one-line re-export while real `<Routes>` remain in `CockpitApp.tsx`. | Not fixed here; next structural cleanup. |
| Dual token systems remain. | Still true. `tokens.css` keeps `--case-*` mirrors and compatibility aliases such as `--bg`, `--panel`, `--accent`, `--green`, `--red`, `--blue`; many CSS modules still consume them. | Not fixed here; next structural cleanup. |
| `shared.module.css` is a feature-specific dump. | Still true. It remains 1443 lines and contains drawer, timeline, replay, and score-ledger rules. | Partially mitigated only by removing Live-owned shell overrides that broke the production layout. |
| `obsidian.module.css` hard-coded hex colors bypass tokens. | Still true; multiple hard-coded tone colors remain. | Not fixed here. |
| `main.tsx` CSS module keep hack exists. | Still true, but this spec makes it explicit that Obsidian CSS must be kept from the root entry until CSS ownership is decomposed. | Stabilized, not removed. |
| Missing `shared/ui/case-file/` package. | Still true. Primitives remain in `shared/ui/obsidian.tsx` plus `obsidian.module.css`. | Not fixed here; next structural cleanup. |
| `tokenCase`, `searchCase`, `pulseCase`, `watchlistCase` are under-consumed. | Still true except Watchlist. `TokenRadarRow` and drawer top consume `tokenCase`; `SearchDossier` consumes only the search header; Signal Pulse rows/inspector consume `pulseCase`, but Workbench shell does not. | Not fixed here. |
| `lib/watchlist.ts` shim still exists. | Still true. `CockpitApp` still builds `WatchlistRow[]` then `WatchlistAccountCase[]`; `CockpitSideRail` still consumes `WatchlistRow`. | Not fixed here. |
| Notification routing duplicates `signalLabPath`. | Still true. `useNotificationsController.ts` keeps local `buildSignalLabUrl` and always navigates Signal Lab style. | Not fixed here. |
| `ScoreLedger` keeps Attention / Discussion / Spread / Entry labels. | Still true in `ScoreLedger.tsx` and tests. | Not fixed here. |
| Legacy CSS selectors remain. | Still true. `drawer-*`, `replay-*`, `timeline-*`, `search-*`, `signal-*`, and `data-radar-metric` selectors remain. | Partially mitigated for the shell/detail bug only. |
| Fullscreen production shell. | Previously failing: shell `1500x920` at `x=210`, `y=28`. | Fixed here and covered by Playwright. |
| Selected Case CSS broken in production bundle. | Previously failing on `8765`: selected case computed `display:block`, `border:0`. | Fixed in source by explicit Obsidian CSS root import/keep and covered by Playwright production preview; Docker must be rebuilt from this worktree to see it on `8765`. |

## Goals

- **G1 Fullscreen production desk.** The app shell fills `100vw` and `100dvh` with no outer prototype margin, no fixed `1500x920` cap, and no minimum height that overflows small screens.
- **G2 Stable CSS ownership.** Shared primitive CSS loads before feature CSS; feature CSS owns final shell, route, radar, and drawer layout.
- **G3 Obsidian CSS guaranteed.** `obsidian.module.css` is imported and kept from the root entry so `ods-case`, `ods-field`, `ods-pill`, and `ods-evidence` styles are present in production bundles.
- **G4 Selected Case usable.** The right pane uses a production width band, internal scroll, and a drawer height that matches its panel instead of extending beyond it.
- **G5 Verification catches regression.** E2E coverage asserts the shell fills the viewport and the selected case has Obsidian layout styles in the production preview build.

## Non-Goals

- No backend API, database, agent, or scoring changes.
- No redesign of Search Intel, Watchlist, Signal Pulse, or Token Target beyond shell/detail layout compatibility.
- No return to the old metric table or tab-first drawer.
- No cleanup of old worktrees or untracked files in the root checkout.

## Design

`web/src/main.tsx` becomes the CSS bundle authority:

1. global tailwind/tokens/base
2. feature CSS modules in repository import-order
3. shared Obsidian and shared legacy primitive CSS modules explicitly added to the module keep list

Feature ownership is enforced by deleting Live-owned `cockpit-grid` overrides and by giving Cockpit's production drawer sizing rules stronger container-specific selectors than the old shared drawer rules.

`web/src/features/cockpit/ui/cockpit.module.css` owns the final production shell:

- `.cockpit-shell`: `width: 100vw`, `height: 100dvh`, `min-height: 0`, `margin: 0`, `border-radius: 0`
- `.cockpit-grid`: `196px minmax(0, 1fr) clamp(420px, 24vw, 520px)`
- `.detail-task-panel`: height-bound internal scroll
- `.detail-task-panel > .detail-drawer`: `position: static`, `height: 100%`, `max-height: 100%`

`web/src/styles/base.css` ensures the root owns the viewport and body does not introduce an accidental page scroll around the desktop app.

The Playwright cold-load golden path will assert:

- Shell x/y are `0`.
- Shell width/height match the viewport.
- Selected case computed `display` is `grid`.
- Selected case border is non-zero.
- The drawer does not exceed the visible detail panel height.

## Acceptance Criteria

- **AC1.** At `1920x1080`, `.cockpit-shell` SHALL have `x=0`, `y=0`, width `1920`, and height `1080`.
- **AC2.** At `1366x768`, `.cockpit-shell` SHALL still fill the viewport without body scrollbars caused by shell margins or fixed minimum height.
- **AC3.** In the production preview build, `.selected-case-file` SHALL compute to `display: grid` and have a visible border from Obsidian CSS.
- **AC4.** `.detail-drawer` SHALL not be taller than `.detail-task-panel` on the initial live route.
- **AC5.** The right detail pane SHALL be at least `420px` wide on desktop routes with an outer detail panel.
- **AC6.** `npm --prefix web run lint`, `npm --prefix web run typecheck`, targeted Vitest, `npm --prefix web run build`, and the updated Playwright golden path SHALL pass.

## Risks

| Risk | Mitigation |
|------|------------|
| Fullscreen shell makes route pages feel too wide. | Preserve existing internal columns and route scroll regions; only remove the outer prototype frame. |
| CSS import reordering changes old drawer/timeline styles. | Run Cockpit integration tests and the live cold-load Playwright path. |
| `100dvh` behaves differently in mobile browsers. | Keep the existing mobile media rules; remove only the prototype cap/margin. |
| `8765` still serves an old build after source is fixed. | Validate with Vite and production preview; note that the running backend must be rebuilt/restarted to pick up new assets. |

## Progress Log

| Time | Milestone | Validation |
|------|-----------|------------|
| 2026-05-14 07:27 CST | Created fresh worktree from `main` and installed frontend deps. | `git worktree add .worktrees/obsidian-desk-production-cleanup -b codex/obsidian-desk-production-cleanup main`; `npm --prefix web install` |
| 2026-05-14 07:31 CST | Baseline source checks passed. | `npm --prefix web run lint`; `npm --prefix web run typecheck` |
| 2026-05-14 07:36 CST | Measured Vite and `8765` visual baselines. | Vite shell `1500x920`, selected case `display:grid`; `8765` selected case `display:block`, `border:0`, confirming production CSS asset mismatch/staleness. |
| 2026-05-14 07:43 CST | Implemented production viewport and selected-case CSS hardening. | Vite measurement at `1920x1080`: shell `0,0,1920,1080`; detail pane `461px`; selected case `display:grid`, `border-top-width:1px`. Measurement at `1366x768`: shell `0,0,1366,768`, body overflow hidden, detail pane `420px`. |
| 2026-05-14 07:48 CST | Completed frontend verification. | `npm --prefix web run format:check` PASS; `npm --prefix web run lint` PASS; `npm --prefix web run typecheck` PASS; targeted Vitest PASS (`58 passed`); `npm --prefix web run test:e2e -- live-cold-load.spec.ts` PASS; `npm --prefix web run build` PASS with existing chunk-size warning; full `npm --prefix web run test` PASS (`36 files`, `161 tests`). |
| 2026-05-14 08:05 CST | Re-checked Docker `8765` and mapped the architecture audit against current source. | `8765` is served by `parallax-main-app-1` from the root checkout and still references old asset hashes; audit matrix added above to separate this spec's production layout fix from the remaining case-file architecture cleanup. |
