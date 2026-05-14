# Frontend React/Vite Architecture And Test Hard Cut

**Status**: Spec  
**Date**: 2026-05-14  
**Owner**: Codex  
**Scope**: `web/` React/Vite architecture, component ownership, CSS ownership, test taxonomy, and anti-compatibility gates.  
**Related**: `docs/FRONTEND.md`, `docs/superpowers/specs/active/2026-05-13-frontend-architecture-design-language-review-cn.md`, `docs/superpowers/plans/active/2026-05-14-obsidian-desk-ui-cleanup-decoupling-cn.md`

## Executive Read

The direction is right, but it needs to be enforced as a hard architecture cut rather than another styling pass.

Modern React/Vite practice does not mean "use more libraries" or "convert everything to Tailwind." It means every layer has one owner: routes own URL state and page orchestration, feature API hooks own server state, feature models own pure view derivation, shared UI owns reusable presentational primitives, and components remain mostly pure render surfaces. The current code has moved toward that shape, but it still carries three sources of repeat regressions:

1. CSS Modules are used mostly as globally injected stylesheet buckets through `main.tsx` and `moduleKeep`.
2. App/route integration is still centralized in `AppRoutes`, with `live` acting as an app-level data coordinator.
3. Tests are split across production source folders and `web/src/test`, so source ownership and test ownership are visually mixed. Route/app integration tests also live inside feature folders and assert implementation selectors and old copy.

This spec defines the hard cut: delete compatibility selectors and legacy names, localize styles, move route-level tests to route/app harnesses, and add architectural gates so "old frame with new paint" cannot reappear.

## Official Baseline

The baseline comes from current official docs, not taste alone:

- React recommends a framework for new full apps, but allows Vite-style from-scratch SPAs when a framework is not the right fit. Since this frontend is shipped inside a Python/FastAPI service and does not need React SSR right now, a Vite SPA remains acceptable, provided routing, data fetching, styling, and testing are intentionally owned. Source: [Creating a React App](https://react.dev/learn/start-a-new-react-project), [Build a React App from Scratch](https://react.dev/learn/build-a-react-app-from-scratch).
- React components and hooks must be pure and predictable. Derived display data should be calculated during render or in pure model functions, not synchronized through effects. Source: [Rules of React](https://react.dev/reference/rules), [You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect).
- Each state value needs a single owner. Shared state should be lifted to the closest common owner, while local interaction state should stay local. Source: [Sharing State Between Components](https://react.dev/learn/sharing-state-between-components).
- Custom hooks are for reusable stateful logic, not for hiding arbitrary lifecycle code or sharing state itself. Source: [Reusing Logic with Custom Hooks](https://react.dev/learn/reusing-logic-with-custom-hooks).
- Complex UI state may move into pure reducers when it is bug-prone or has many transitions. Source: [Extracting State Logic into a Reducer](https://react.dev/learn/extracting-state-logic-into-a-reducer).
- Vite supports CSS Modules as a first-class local styling mechanism and recommends modern CSS primitives such as CSS variables. Env access should go through `import.meta.env` and `VITE_*` variables. Source: [Vite Features](https://vite.dev/guide/features), [Vite Env Variables and Modes](https://vite.dev/guide/env-and-mode/).
- Vitest explicitly supports colocated tests. That is a valid framework option, but this repo's current shape has enough test sprawl that the hard cut should choose one visible frontend test root instead. Source: [Vitest Writing Tests](https://vitest.dev/guide/learn/writing-tests).

## Best Practice Target For This App

### React Component Rules

- Components are pure render units: props in, JSX out, callbacks out.
- Components do not parse backend payloads inline. Payload interpretation belongs in `features/<name>/model/` or `shared/model/`.
- Components do not call `getApi`, `postApi`, `useQuery`, `useMutation`, `queryClient.set*`, or socket APIs unless they are explicitly API/hook components in the owning feature layer.
- Derived values are calculated directly or through pure model adapters. Effects are only for external synchronization such as subscriptions, browser APIs, or imperative chart libraries.
- Cross-feature reusable UI is promoted to `shared/ui` before reuse. Copying a feature-local component into another feature is not allowed.
- Interaction state uses the smallest reasonable owner: local component state for simple controls, route state for shareable URL filters, React Query for server state, and Zustand only for narrow app-shell interaction state.

### Vite/CSS Rules

- `styles/` contains only Tailwind import, design tokens, and base element styles.
- Feature CSS belongs beside the feature and is imported by the component/route that uses it, not globally retained through `moduleKeep`.
- CSS Modules should use local class bindings for feature-specific selectors. `:global(...)` is allowed only for documented shared primitive classes or third-party integration hooks.
- Design primitives live in `shared/ui`, with stable class names and typed React components.
- No late global override layer is allowed. A CSS fix must move to the owning module or the shared primitive that owns the visual grammar.
- The build must stay Vite-native: no custom bundler layer, no ad hoc env reads, no direct `process.env` in browser code.

### Route/Data Rules

- `app/` owns providers and router bootstrap only.
- `routes/` owns route tree and URL-state orchestration.
- Each route module should pick the owning feature route adapter. It should not become a giant data aggregator.
- Feature `api/` hooks own React Query keys and endpoint adapters.
- Feature `model/` functions own view models and are directly unit tested.
- Feature `ui/` renders from props or feature public hooks. It does not import another feature's internals.
- Cross-feature path builders live in `shared/routing` or a feature public index.

## Current Fit Assessment

| Area | Current State | Fit | Required Direction |
|------|---------------|-----|--------------------|
| React/Vite stack | React 19, Vite 8, React Query, Zustand, React Router, Vitest, Playwright | Good base | Keep stack; no framework rewrite now |
| Route ownership | `AppRoutes` still destructures live data, notification state, watchlist rows, shell props, route elements | Partial | Move route data adapters into route-owned modules |
| Component reuse | `TokenSocialMarketTimeline` was promoted to `shared/ui`; old dead timeline selectors removed | Improving | Make this the rule for all cross-feature components |
| CSS ownership | Global `moduleKeep` imports still retain all feature CSS; many modules use `:global` selectors | Weak | Convert to local CSS module classes and shared primitives |
| Data derivation | Several model adapters exist, but UI still contains parsing/formatting in larger route components | Partial | Pure feature model adapters first, render second |
| Boundary enforcement | ESLint blocks alias deep imports but not relative cross-feature internals | Weak | Add relative cross-feature import gate |
| Tests | 44 frontend test files; model/component tests are mostly well placed; route integration tests are misplaced and overcoupled | Partial | Normalize by test level and ownership |

## Test Audit

Current `web` test inventory:

- Total frontend test files: 44
- `web/src/features/**`: 27
- `web/src/shared/**`: 8
- `web/src/lib/**`: 3
- `web/src/test/**`: 1 executable architecture test plus fixtures/harness files
- `web/e2e/**`: 5 Playwright golden paths

Largest tests by line count:

- `web/src/features/live/__tests__/CockpitApp.integration.test.tsx`: 3065 lines
- `web/src/lib/tokenRadar.test.ts`: 533 lines
- `web/src/features/live/ui/TokenRadarRow.test.tsx`: 460 lines
- `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`: 391 lines
- `web/src/lib/venue.test.ts`: 324 lines

The problem is not that Vitest cannot support colocated tests. It can. The repo problem is that tests currently live both beside source files and under `web/src/test`, while some route/app tests are placed inside a feature and import across feature internals. `CockpitApp.integration.test.tsx` lives under `features/live`, but it verifies app routing, shell behavior, search routing, watchlist, Signal Pulse, stocks, token target pages, socket mocks, API mocks, and responsive shell contracts. That file is an app/route integration harness, not a live feature test.

The hard cut is therefore stricter than the generic Vitest default: all frontend tests move under `web/tests/`. The repository root `tests/` remains the Python/FastAPI pytest suite because `pyproject.toml` already points pytest at `tests`, and mixing TypeScript/Vitest fixtures into that tree would blur tool ownership.

This creates three forms of coupling:

1. **Ownership coupling**: A live feature folder appears to own app-level behavior.
2. **Selector coupling**: Tests assert CSS classes and low-level selectors such as `.side-rail`, `.desktop-side-rail`, `data-radar-metric`, and `.detail-drawer`.
3. **Fixture coupling**: Giant app fixtures and mock API behavior are embedded in one integration file, so unrelated route changes must understand live test setup.

## Test Taxonomy Target

### L0: Pure Model And Mapper Tests

Location:

- Centralized under `web/tests/unit/**`, mirroring the production path: `web/tests/unit/features/<name>/model/*.test.ts`, `web/tests/unit/shared/model/*.test.ts`, `web/tests/unit/lib/*.test.ts`

Allowed:

- Pure imports from the unit under test.
- Fixture imports from `@tests/fixtures/*`.
- Exact value assertions.

Not allowed:

- React rendering.
- MSW.
- DOM selectors.
- Cross-route app setup.

### L1: Focused Component And Hook Tests

Location:

- Centralized under `web/tests/component/**`, mirroring the production path: `web/tests/component/features/<name>/ui/*.test.tsx`, `web/tests/component/shared/ui/*.test.tsx`, `web/tests/component/features/<name>/api/*.test.tsx`

Allowed:

- React Testing Library.
- Accessibility checks with `axe`.
- Role/label based assertions.
- Minimal local wrappers from `@tests/render/*`.

Not allowed:

- Rendering the full `App`.
- Testing another feature's route.
- CSS implementation selectors except for explicit public state classes such as `active` when no semantic equivalent exists.

### L2: Route Integration Tests

Location:

- Centralized route harness: `web/tests/routes/*.test.tsx`

Allowed:

- `App` or route shell rendering.
- MSW/API scenario builders.
- Socket scenario builders.
- URL and route assertions.
- One route workflow per file.

Not allowed:

- Living inside a feature folder.
- Importing feature internals through relative paths.
- Large all-app fixture factories inside the test file.
- Broad "everything still works" files over 500 lines.

### L3: Browser Golden Paths

Location:

- `web/tests/e2e/golden-paths/*.spec.ts`

Allowed:

- Representative user journeys against the built app or dev server.
- Route smoke, keyboard/search, responsive layout, critical request checks.

Not allowed:

- Duplicating all L2 API branch coverage.
- Asserting implementation CSS internals unless the user-visible regression is layout-specific.

### Architecture Gates

Location:

- `web/tests/architecture/*.test.ts`

Allowed:

- Static source scans for forbidden imports, dead selectors, compatibility aliases, route/data ownership, and global CSS leakage.

Not allowed:

- Product behavior assertions.
- Large snapshots.

## Test Harness Normalization

Create these shared test harness modules:

- `web/tests/render/renderWithProviders.tsx`: QueryClient, Router, common wrappers.
- `web/tests/render/renderRoute.tsx`: route-entry rendering with initial URL.
- `web/tests/msw/scenarios.ts`: named API scenarios instead of local giant `mockApi` functions.
- `web/tests/socket/scenarios.ts`: socket snapshot and subscription test utilities.
- `web/tests/fixtures/tokenRadar.ts`: token radar fixtures.
- `web/tests/fixtures/search.ts`: search fixtures.
- `web/tests/fixtures/signalPulse.ts`: Signal Pulse fixtures.
- `web/tests/fixtures/watchlist.ts`: watchlist fixtures.

The old `web/src/test/app-test-case-matrix.md` should be deleted or replaced by a live test ownership matrix generated from actual file paths under `docs/generated/` only if it remains useful. It currently says `Source: web/src/App.test.tsx`, which is stale and should not remain a governance source.

## Required Hard Cuts

### Cut 1: CSS Module Ownership

Delete the `main.tsx` `moduleKeep` retention pattern. Each component or route imports its own CSS module and uses local classes, or consumes typed shared primitives. The only global CSS allowed is tokens/base and deliberately named shared primitives.

Acceptance:

- `main.tsx` imports only `styles/tailwind.css`, `styles/tokens.css`, `styles/base.css`, and `AppRoot`.
- `rg "moduleKeep|documentElement.classList.add" web/src` returns no matches.
- New architecture test fails if a feature CSS module has broad `:global(.page-or-feature-selector)` without an allowlist entry.

### Cut 2: AppRoutes Diet

Split `AppRoutes` so it no longer destructures all live data and passes every route prop. The cockpit shell may receive shell state, but each route owns its data adapter.

Acceptance:

- `app/CockpitApp.tsx` only wraps providers and returns route tree.
- `routes/AppRoutes.tsx` owns route declarations and shell selection only.
- `features/live` does not import `../cockpit/*` or `../search/*`.
- Route adapters live in `routes/*` or feature public route exports.

### Cut 3: Public Feature Contracts

No feature imports another feature's `api`, `model`, `state`, or `ui` internals by alias or relative path. Cross-feature concepts move to `shared/routing`, `shared/socket`, `shared/query`, `shared/model`, or a public feature index.

Acceptance:

- ESLint catches alias deep imports.
- Architecture test catches relative imports matching `../<other-feature>/api|model|state|ui`.
- All route path builders are imported from `shared/routing` or public feature APIs.

### Cut 4: Shared UI Before Reuse

Any component used by more than one feature is promoted to `shared/ui` or a narrower shared package before reuse. No feature may import another feature's UI component directly.

Acceptance:

- Search and token target continue to share `TokenSocialMarketTimeline`.
- Future duplicate timeline/header/profile/post/score components fail review unless extracted first.
- Dead selectors are deleted in the same change that removes the old component.

### Cut 5: Test Level Relocation

Move all frontend tests out of `web/src` into `web/tests`. Keep source ownership visible by mirroring production paths inside `web/tests/unit` and `web/tests/component`.

Acceptance:

- `features/live/__tests__/CockpitApp.integration.test.tsx` is split into route-level files under `web/tests/routes/`.
- `find web/src -name "*.test.*" -o -name "*.spec.*"` returns no files.
- `find web/tests -type f` contains all Vitest, RTL, MSW, fixture, architecture, and Playwright files.
- No L2 route integration test exceeds 500 lines.
- L2 tests use shared scenario builders rather than local all-app fixture factories.
- Component tests query by role/label where possible and avoid CSS selectors except when testing public class state.

## Implementation Order

1. Move all frontend test files and frontend test tooling into `web/tests/`.
2. Add architecture gates for test placement, relative cross-feature imports, `moduleKeep`, global CSS leakage, and route-test placement.
3. Build the shared test harness and scenario fixtures.
4. Split `CockpitApp.integration.test.tsx` by route workflow into `web/tests/routes/`.
5. Move route data orchestration out of `AppRoutes` into route-owned adapters.
6. Convert one feature at a time from global CSS selectors to local CSS module bindings.
7. Delete `moduleKeep` from `main.tsx` once no feature CSS relies on global retention.
8. Run full frontend gates and browser visual checks after each route slice.

## Non-Goals

- Do not rewrite the app to Next.js or a full-stack React framework in this pass.
- Do not convert all CSS to Tailwind utilities. Tailwind can remain available, but the ownership problem is selector scope, not lack of utility classes.
- Do not replace React Query, Zustand, React Router, or Vitest without a separate decision doc.
- Do not add compatibility aliases for old class names or old component names. The point is to delete the old frame.

## Risks

- Moving tests before harness extraction will create churn without lowering coupling.
- Moving CSS without visual checks can reintroduce spacing/overflow regressions.
- Keeping route integration tests inside feature folders will keep hiding app-level coupling.
- Keeping `moduleKeep` will make every later style fix suspect because any feature can still globally affect any route.

## Verification Gates

Every implementation plan generated from this spec must include:

- `cd web && npm run lint`
- `cd web && npm run typecheck`
- `cd web && npm test -- --run`
- `cd web && npm run build`
- `cd web && npm run test:e2e`
- Browser smoke for `/`, `/search`, `/signal-lab`, `/stocks`, `/watchlist`, and `/token/:targetType/:targetId`
- Static gates:
  - `find web/src -name "*.test.*" -o -name "*.spec.*"`
  - `rg "moduleKeep|documentElement.classList.add" web/src`
  - `rg "\\.\\./(cockpit|live|search|signal-lab|stocks|token-target|watchlist)/(api|model|state|ui)" web/src/features web/src/routes`
  - `rg "compat|legacy|stage-tape|detail-drawer|obsidian-hard-cut" web/src`

## Definition Of Done

The hard cut is done when:

1. The app still ships as a Vite SPA inside the FastAPI Docker image.
2. Route state, server state, derived view models, and presentation have separate owners.
3. Shared components are actually shared, not copied or imported from another feature's internals.
4. Feature CSS is local by default, global by exception, and exception-gated.
5. Tests communicate ownership from directory structure: production code lives under `web/src`; frontend tests live under `web/tests`; backend pytest remains under repository-root `tests`.
6. No compatibility CSS, dead component names, or stale test matrix entries remain.
