# Frontend Architecture Design-Language Review

**Status**: Review  
**Date**: 2026-05-13  
**Owner**: Codex  
**Scope**: `web/` frontend architecture, design-language ownership, route/data composition, CSS system, and tests.  
**Related**: `docs/FRONTEND.md`, `docs/superpowers/specs/active/2026-05-13-obsidian-desk-ui-hard-cut-cn.md`, `docs/superpowers/plans/active/2026-05-13-obsidian-desk-ui-hard-cut-plan-cn.md`, `docs/prototypes/obsidian-desk-v2-static.html`

## Executive Read

The frontend is structurally halfway through a good migration: the directory map now says `app / routes / features / shared / lib`, and ESLint has some boundary rules. But the actual product language is still held in route containers, CSS globals, and page-local JSX helpers rather than in feature models and shared design primitives. That is why the current UI feels complex: every surface explains the same intelligence pipeline with different vocabulary.

Obsidian Desk v2 should not be implemented as “new CSS over current components.” It needs a small architecture hard cut: define the case-file grammar as shared primitives and feature-owned view models, then migrate each route to that grammar. Otherwise Token Radar, Selected Token, Search Intel, Watchlist, and Signal Pulse will keep drifting.

## Findings

### P1 — `CockpitApp` is acting as a route/data/selection god component, so page design language cannot be owned by routes.

`docs/FRONTEND.md` says `app/` may compose route elements but must not own feature data queries or business rendering (`docs/FRONTEND.md:7-14`). In practice, `CockpitAppRoutes` owns live data destructuring, socket event merge, selection state, token detail data, notifications, watchlist rows, shell props, and route tree composition in one 377-line file (`web/src/app/CockpitApp.tsx:53-134`, `web/src/app/CockpitApp.tsx:153-258`, `web/src/app/CockpitApp.tsx:292-334`). `AppRoutes` just returns `CockpitApp` (`web/src/app/AppRoutes.tsx:1-5`), and route files are re-export shims rather than route orchestrators (`web/src/routes/live.route.tsx:1`, `web/src/routes/search.route.tsx:1`, `web/src/routes/signal-lab.route.tsx:1`).

Impact: adding `/watchlist`, changing selected detail grammar, or making Signal Pulse memo-first all require edits in a central cockpit file. That makes the design language a branching condition inside app composition instead of a route-level contract.

Recommendation: split the cockpit composition into a shell provider and route-owned surfaces:

- `app/AppRoutes.tsx` owns route tree only.
- `features/cockpit/ui/CockpitShell` owns layout only.
- `features/live/LiveRoute.tsx`, `features/watchlist/WatchlistRoute.tsx`, `features/signal-lab/SignalLabRoute.tsx`, `features/search/SearchRoute.tsx` own their route data/state adapters.
- Shared topbar/notifications can stay in cockpit, but route detail panels should be injected as route-owned slots.

### P1 — Feature boundaries are documented but not consistently enforced; `live` imports cockpit/search internals.

`docs/FRONTEND.md` says feature UI should import through public indexes, and deep imports across feature internals are blocked (`docs/FRONTEND.md:25`). ESLint only blocks alias deep imports like `@features/*/state/*` (`web/eslint.config.js:55-70`) and does not prevent relative cross-feature imports. Current code uses exactly those relative imports: `useLiveSelection` imports cockpit model/state and search route internals (`web/src/features/live/useLiveSelection.ts:9-12`), and notifications imports cockpit model internals (`web/src/features/notifications/useNotificationsController.ts:7`).

Impact: mobile task state, search routing, live selection, and notifications are coupled by file path rather than contract. This will make Watchlist and case-file routing fragile because any feature can silently reach into another feature’s state.

Recommendation:

- Move cross-route path builders to `shared/routing` or feature public indexes only.
- Move mobile task concepts to `features/cockpit` public API or a `shared/routing/routeTasks.ts` contract if truly cross-feature.
- Add ESLint/path test that catches relative imports such as `../cockpit/model`, `../cockpit/state`, `../search/state`, and `../signal-lab/ui` from outside the owning feature.

### P1 — The CSS architecture is effectively global CSS disguised as CSS modules.

`main.tsx` imports every feature CSS module and attaches `moduleKeep` classes to `documentElement` solely to keep module files in the bundle (`web/src/main.tsx:7-25`). The modules themselves define global selectors via `:global(...)` (`web/src/features/live/ui/live.module.css:1-91`, `web/src/features/cockpit/ui/cockpit.module.css:1-92`, `web/src/shared/ui/shared.module.css:1-80`). This bypasses the usual benefit of CSS modules: selector locality.

Impact: design language cannot be composed safely. `.radar-row`, `.segmented`, `.detail-drawer-card-stack`, `.filter-cell`, `.entity-tags`, `.venue-link`, `.decision-tag`, and similar names are global primitives without a clear owner. Changing Obsidian Desk colors or case-row spacing risks cross-route regressions.

Recommendation:

- Make global CSS limited to `styles/tokens.css`, `styles/base.css`, and deliberate `shared/ui` primitives.
- Replace feature-global selectors with either CSS module bindings (`styles.row`) or shared primitive classes (`caseRow`, `caseSection`, `caseBadge`) exported from one shared case-file module.
- Delete `moduleKeep` once selectors are local or explicitly imported by components.

### P1 — Product semantics live inside JSX helpers instead of reusable view models.

Token Radar row renders heat, quality, propagation, market, timing, and decision directly in JSX (`web/src/features/live/ui/TokenRadarRow.tsx:56-109`) and keeps formatting/business labeling helpers in the same component (`web/src/features/live/ui/TokenRadarRow.tsx:114-316`). Search Intel builds branch-specific metrics and facts directly in `SearchIntelPage` (`web/src/features/search/ui/SearchIntelPage.tsx:227-326`, `web/src/features/search/ui/SearchIntelPage.tsx:330-430`, `web/src/features/search/ui/SearchIntelPage.tsx:475-520`). Signal Pulse inspector converts raw factor snapshot fields into UI cards in the component (`web/src/features/signal-lab/ui/SignalLabInspector.tsx:21-33`, `web/src/features/signal-lab/ui/SignalLabInspector.tsx:63-247`).

Impact: there is no canonical frontend concept for “case,” “official fact,” “community proof,” “narrative,” “agent memo,” or “decision.” The same domain must be reinterpreted differently per page, which is the root of the user-facing complexity.

Recommendation:

- Introduce pure feature model adapters: `TokenCaseView`, `SearchCaseView`, `PulseCaseView`, `WatchlistAccountCase`.
- JSX should render those views; source attribution and unavailable states should be decided before UI rendering.
- Add model tests for each adapter before changing visuals.

### P1 — The current design language is factor-centric, not user-job-centric.

Token Radar exposes columns `Heat`, `Quality`, `Propagation`, `Market`, `Timing`, `Decision` (`web/src/features/live/ui/TokenRadarTable.tsx:61-71`). Selected Token repeats heat/quality/spread/timing in its header (`web/src/features/live/ui/TokenDetailDrawer.tsx:150-162`) and hides official/community/narrative behind profile card/tabs (`web/src/features/live/ui/TokenDetailDrawer.tsx:194-273`). Signal Pulse shows useful facts but primary cards are implementation concepts: `Agent Recommendation`, `Fact Card`, `Eligibility Gates`, `Data Health`, `Alpha Families`, raw JSON (`web/src/features/signal-lab/ui/SignalLabInspector.tsx:63-247`).

Impact: the user sees pipeline internals before product answers. Mature intel desks usually keep internal scoring explainable, but the first read is always “what is it / why now / who is involved / what confirms or invalidates it / what do I do next.”

Recommendation: make the canonical visual grammar:

```text
Identity -> Official -> Community -> Narrative -> Market -> Decision -> Evidence -> Next action
```

Internal scores remain available as audit detail, not the primary row grammar.

### P2 — Watchlist is modeled as a rail decoration instead of a product surface.

`WatchlistRow` only contains handle, unread count, and last seen time (`web/src/lib/watchlist.ts:3-7`). Side rail links each account to `signalLabPath({ handle })` (`web/src/features/cockpit/ui/CockpitSideRail.tsx:111-130`), and the test locks that behavior in (`web/src/features/cockpit/ui/CockpitSideRail.test.tsx:27-32`).

Impact: Watchlist cannot answer the user’s real question: “这个账号最近在推什么 token / narrative / evidence?” It also overloads Signal Lab as both agent queue and account-detail page.

Recommendation: create `features/watchlist` with `/watchlist` and `/watchlist?handle=...`. The model should derive account cases from handles, live events, entities, token intents, unread counts, and Search Intel links. Signal Lab can still filter by handle, but it should not be the account file.

### P2 — Data ownership is mixed: `useLiveData` fetches cross-feature data from a non-API layer.

`useLiveData` imports `getApi`, `getBootstrap`, and `setAuthToken` directly (`web/src/features/live/useLiveData.ts:1-13`), fetches status/recent data in the hook body (`web/src/features/live/useLiveData.ts:32-64`), and also fetches Signal Pulse overview/list data (`web/src/features/live/useLiveData.ts:68-97`). This conflicts with the stated convention that feature API hooks own server reads/writes (`docs/FRONTEND.md:29`).

Impact: live becomes the implicit dashboard data aggregator. That may work for a cockpit, but it prevents Signal Pulse and Watchlist from owning their own data semantics and makes route-level loading/error behavior harder to reason about.

Recommendation:

- Move live dashboard API calls into `features/live/api/*` hooks.
- Move Signal Pulse compact query ownership to `features/signal-lab/api` and consume through public exports.
- Let route composition decide which summaries are needed, not `live` by default.

### P2 — URL state and interaction state are partially mixed.

`useLiveRouteState` owns URL filters (`web/src/features/live/state/liveRouteState.ts:55-67`), but `useLiveSelection` also navigates between live/search/signal routes, resets drawer state, updates mobile task, and clears selected signals (`web/src/features/live/useLiveSelection.ts:31-310`). It knows `/signal-lab`, `/search`, `/stocks`, mobile task routing, and token search path (`web/src/features/live/useLiveSelection.ts:38-43`, `web/src/features/live/useLiveSelection.ts:160-209`, `web/src/features/live/useLiveSelection.ts:222-227`).

Impact: selection is not a bounded live concern anymore. Adding Watchlist means more path checks or special suppressions, and the detail panel becomes a global state machine.

Recommendation: split selection into:

- `liveSelection`: selected token/tape item within live route.
- `detailPanelController`: shell-level slot state if global detail truly persists across routes.
- Route navigation helpers in `shared/routing` or public feature route APIs.

### P2 — Tests currently preserve old architecture and old language.

Golden paths assert old copy and routes: Signal Lab text “Review Signal Pulse agent candidates by status, source, and query.” (`web/e2e/golden-paths/signal-lab-filters.spec.ts:6-18`) and notification navigation into `/signal-lab?q=BNB` (`web/e2e/golden-paths/notification-navigation.spec.ts:6-15`). `CockpitSideRail.test` asserts watchlist row href `/signal-lab?handle=toly` (`web/src/features/cockpit/ui/CockpitSideRail.test.tsx:27-32`). `TokenRadarRow.test` asserts old metric-cell selectors such as `data-radar-metric="market"` and `data-radar-metric="timing"` (`web/src/features/live/ui/TokenRadarRow.test.tsx:38-50`, `web/src/features/live/ui/TokenRadarRow.test.tsx:103-112`).

Impact: tests will resist the desired product language unless rewritten first. That is good if the old behavior is intended, but harmful during a design-language hard cut.

Recommendation: update tests around the new architecture vocabulary: `Case`, `Official`, `Community`, `Narrative`, `Decision`, `Agent Memo`, `/watchlist`. Keep low-level market correctness tests in model adapters, not DOM metric selectors.

### P3 — Existing docs describe the desired architecture better than the code enforces it.

`docs/FRONTEND.md` says `styles/` should contain global tokens/base only and feature/page selectors should live beside features (`docs/FRONTEND.md:21-22`), but current feature CSS is globally injected via `main.tsx` (`web/src/main.tsx:7-25`). It says route modules should parse URL state and choose owning feature views (`docs/FRONTEND.md:9-10`), but route modules are re-export shims (`web/src/routes/live.route.tsx:1`, `web/src/routes/search.route.tsx:1`, `web/src/routes/signal-lab.route.tsx:1`).

Impact: new contributors will follow docs and be surprised by runtime reality. That increases entropy.

Recommendation: either align code with docs during Obsidian hard cut, or temporarily update docs to name the transitional architecture. The better option is to align code.

## Design-Language Architecture Target

The durable target should be:

```text
API/WS contracts
  -> feature api hooks
  -> feature model adapters
  -> shared case-file primitives
  -> route-owned pages
  -> cockpit shell slots
```

Where:

- `shared/ui/caseFile` owns presentational grammar.
- `features/live/model/tokenCase.ts` owns Token Radar and selected token case semantics.
- `features/search/model/searchCase.ts` owns Search Intel case semantics.
- `features/watchlist/model/watchlistCase.ts` owns account-file semantics.
- `features/signal-lab/model/pulseCase.ts` owns Signal Pulse memo/fact-ledger semantics.
- `app/` owns providers and routes only.

This is a design-language architecture, not just a folder cleanup.

## Recommended Refactor Order

1. **Create shared case-file primitives and tokens first.** Do not start with page rewrites. A design language needs a real API.
2. **Move Token Radar semantics into `TokenCaseView`.** This is the highest-impact surface and gives the rest of the app a vocabulary.
3. **Create Watchlist as a route.** It forces the architecture to stop abusing Signal Lab as account detail.
4. **Refactor Search Intel into shared case sections.** This validates that case-file primitives handle deep research pages, not just compact rows.
5. **Refactor Signal Pulse into `PulseCaseView`.** Preserve debug facts behind disclosure, but make memo/fact-ledger primary.
6. **Delete global CSS/moduleKeep pattern.** Once primitives exist, migrate feature selectors away from `:global`.
7. **Strengthen boundary enforcement.** Add lint/test coverage for relative cross-feature internals.

## Risk If We Only Restyle

If Obsidian Desk v2 is implemented as CSS + copy changes over the current architecture, three regressions are likely:

- The new palette lands but pages still disagree on meaning.
- Watchlist remains a rail/filter, not a product workflow.
- Signal Pulse remains an inspector with nicer cards.

That would make the UI look newer without becoming easier to understand.

## Bottom Line

The right unit of redesign is not “component,” it is “case grammar.” The current frontend has enough infrastructure to support that, but the design language must move from scattered JSX/CSS into shared primitives plus feature-owned view models. That is the line between a polished prototype and a durable product surface.
