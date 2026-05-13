# Frontend Architecture Hard Cut Verification

Plan: `docs/superpowers/plans/active/2026-05-13-frontend-architecture-hard-cut-plan-cn.md`

Worktree: `.worktrees/frontend-architecture-hard-cut/`

Branch: `codex/frontend-architecture-hard-cut`

## Task 0 Verification

### Worktree

- `git check-ignore -q .worktrees && echo ignored || echo not-ignored`: `ignored`
- `git worktree add .worktrees/frontend-architecture-hard-cut -b codex/frontend-architecture-hard-cut main`: passed
- `git worktree list`: includes `.worktrees/frontend-architecture-hard-cut`
- `git -C .worktrees/frontend-architecture-hard-cut branch --show-current`: `codex/frontend-architecture-hard-cut`
- `git -C .worktrees/frontend-architecture-hard-cut status --short`: initially clean except the copied untracked plan file

The plan file was untracked in the source checkout, so it was copied into the worktree before execution and committed with Task 0 bookkeeping.

### Baseline Commands

- `cd web && npm install`: passed; installed dependencies from lockfile, `0 vulnerabilities`
- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: failed on the first pass, then passed after baseline test-fixture alignment
- `cd web && npm run build`: passed; Vite emitted the existing `Some chunks are larger than 500 kB` warning
- `cd web && npm run lint`: passed
- `make contract-check`: passed, `2 passed in 23.37s`

Initial `npm test -- --run` failures:

- `SearchIntelPage.routing.test.tsx`: fixture still provided legacy `radar_item.live_market` / `anchor_price`; current UI reads `radar_item.market.decision_latest` / `event_anchor`.
- `App.test.tsx`: mocked `useIntelSocket` exposed `liveMarketUpdates` but did not mimic the real hook's `onLiveMarketUpdate` callback.

Baseline test-fixture fixes:

- Search fixture now uses `marketContextFixture` / `marketObservationFixture`.
- App socket mock now dispatches configured market updates through `onLiveMarketUpdate` once the matching market target is subscribed.

Targeted rechecks:

- `cd web && npm test -- --run src/components/__tests__/SearchIntelPage.routing.test.tsx -t "uses market cap"`: passed, `1 passed | 1 skipped`
- `cd web && npm test -- --run src/App.test.tsx -t "patches visible token-radar rows with websocket market updates"`: passed, `1 passed | 55 skipped`

Full recheck after fixes:

- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: passed, `25 passed`, `136 passed`
- `cd web && npm run build`: passed
- `cd web && npm run lint`: passed
- `make contract-check`: passed, `2 passed`

### App Test Matrix

Created `web/src/test/app-test-case-matrix.md`; every current `it(...)` entry in `web/src/App.test.tsx` is mapped to L0/L1/L2/L3 or deletion. No deletion candidates were identified for Task 0.

## Execution Notes

- The original pause condition for Task 10's production dependency no longer applies because the user explicitly instructed: "默认统一新增，移除掉所有暂停规则，依赖等均可以安装，直到彻底完成目标".

## Task 1 Verification

### Contract Model Changes

- Added `src/gmgn_twitter_intel/app/surfaces/api/schemas.py` with `ApiEnvelope[T]` and named response data models for frontend-consumed endpoints.
- Added `response_model=...` to existing `/api/*` route declarations without changing return payload construction or status codes.
- Added a `response_model` for `/readyz` because the generated OpenAPI TS file includes that route and the Task 1 unknown-response scan covers the whole file.
- Changed generated frontend OpenAPI output from `web/src/api/openapi.ts` to `web/src/lib/types/openapi.ts`.

### Commands

- `make regen-contract`: passed; regenerated `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts`
- `rg -n '"application/json": unknown|content: \\{\\s*"application/json": unknown' web/src/lib/types/openapi.ts`: no matches
- `make contract-check`: passed, `2 passed in 2.64s`

## Task 2 Verification

### Frontend Scaffold Changes

- Added path aliases in `tsconfig.json` and `vite.config.ts`.
- Added `@lib/env`, `@lib/api/client`, and `@lib/types` facade while keeping `web/src/api/client.ts` as a compatibility re-export.
- Added `AppRoot`, `AppRoutes`, route entry scaffolds, `ErrorBoundary`, and `RouteFallback`.
- Enabled staged lint rules for `react-refresh`, `jsx-a11y`, and lib/shared import boundaries.
- Added dev-only `eslint-plugin-react-refresh` to satisfy the planned Fast Refresh lint gate.
- Moved the exported token drawer summary helper out of `TokenRadarRow.tsx` so the component file passes Fast Refresh rules.

### Commands

- `cd web && npm run typecheck`: passed
- `cd web && npm run lint`: passed
- `cd web && npm test -- --run`: passed, `25 passed`, `136 passed`
- `cd web && npm run build`: passed; Vite emitted the existing `Some chunks are larger than 500 kB` warning

## Task 3 Verification

### Query/API Boundary Changes

- Added `web/src/shared/query/queryKeys.ts`.
- Moved token radar, search inspect, signal pulse, stocks radar, token-target, and notification API helpers into owning `features/*/api/` folders.
- Moved market-update cache patching to `web/src/shared/query/patchMarketUpdate.ts` and kept a temporary live wrapper for compatibility.
- Moved legacy UI/domain types to `web/src/lib/types/legacy-ui.ts`, kept generated types at `web/src/lib/types/openapi.ts`, and deleted old `web/src/api/types.ts`, `web/src/api/client.ts`, and `web/src/api/openapi.ts`.
- Added `.gitkeep` files for target `features/*/{ui,state,model}` directories so the plan's boundary grep commands run against real directories.

### Commands

- `cd web && rg -n 'from "[.][./].*/api/types"|from "[.][./].*/api/client"|src/api/types|src/api/client|src/api/openapi' src`: no matches
- `cd web && rg -n 'useQuery\\(|useMutation\\(|useInfiniteQuery\\(' src/features/*/ui src/features/*/state src/features/*/model src/routes src/shared/ui`: no matches
- `cd web && rg -n 'getApi|postApi|setQueryData|setQueriesData' src/features/*/ui src/features/*/state src/features/*/model src/routes src/shared/ui`: no matches
- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: passed, `25 passed`, `136 passed`
- Extra guard, `cd web && npm run lint`: passed

## Task 4 Verification

### URL State and Store Split Changes

- Added route-state modules for live, search, signal-lab, stocks, and token-target URL filters.
- Added shared route path/search helpers under `web/src/shared/routing/`.
- Replaced the old global `useTraderStore` with small local stores for live detail interaction state and cockpit mobile task state.
- Moved topbar search draft state into `CockpitApp` local state and kept submitted queries URL-owned.
- Removed auth token ownership from Zustand; bootstrap now writes the token through `setAuthToken(ws_token)`.
- Deleted `web/src/store/useTraderStore.ts`.
- Added route-state tests for live and token-target, and updated moved search/signal-lab route-state tests.
- Adjusted one App integration test to wait for token-radar data before asserting token tape selection; the previous sync point could click the replay-only POST row before token data resolved.

### Commands

- `cd web && rg -n 'useTraderStore|setToken|setWindow|setScope|setHandles|setSearch|setRadarSortMode|state\\.token|state\\.window|state\\.scope|state\\.handles|state\\.search|state\\.radarSortMode' src`: no matches; `rg` exited `1` as expected
- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run src/features/live/state src/features/search src/features/signal-lab src/features/token-target`: passed, `5 passed`, `20 passed`
- `cd web && npm test -- --run`: passed, `27 passed`, `145 passed`
- Extra guard, `cd web && npm run lint`: passed

## Task 5 Verification

### Component Ownership Changes

- Deleted `web/src/components/` by moving all components and component tests into feature-owned `ui/` folders or `web/src/shared/ui/`.
- Added public feature indexes for cockpit, live, search, signal-lab, stocks, token-target, and notifications.
- Moved shared UI primitives and cross-feature token UI to `shared/ui`: drawer primitives, `DecisionTag`, `RadarControls`, `ScoreLedger`, `TokenPostsPanel`, and `TokenProfileCard`.
- Moved cockpit mobile task type/routing helpers into `features/cockpit/model`.
- Added an ESLint `no-restricted-imports` guard for `@features/*/{api,model,state,ui}/*` deep imports; the plan grep remains the guard for relative deep feature imports.

### Commands

- `cd web && test ! -d src/components`: passed
- `cd web && rg -n 'from "@features/[^"]+/(api|model|state|ui)/|from "[.][./].*/features/[^"]+/(api|model|state|ui)/' src`: no matches; `rg` exited `1` as expected
- `cd web && npm run lint`: passed
- `cd web && npm run typecheck`: passed
- `cd web && npm test -- --run`: passed, `27 passed`, `145 passed`

## Task 6 Verification

### Shell Split Changes

- Replaced the old `CockpitLayout` file/component with `CockpitShell` and `SearchShell`.
- Split cockpit shell UI into `CockpitTopbar`, `CockpitSideRail`, `CockpitMobileNav`, and a cockpit `RadarControls` export.
- Moved search input draft state into `CockpitTopbar`; submit passes the query text back to the live selection/navigation controller.
- Routed `/search` through `SearchShell`, while live, stocks, token-target, and signal-lab use `CockpitShell`.
- Replaced raw pathname branch checks in cockpit/app files with route matching or typed segment parsing.

### Commands

- `cd web && rg -n 'CockpitLayout|pathname\\.startsWith\\(|isSearch|isStocks|isSignalLab|isLive' src/features/cockpit src/routes src/app`: no matches; `rg` exited `1` as expected
- `cd web && npm run typecheck`: passed
- `cd web && npm run lint`: passed
- `cd web && npm test -- --run`: passed, `27 passed`, `145 passed`

## Task 7 Verification

### Route-Aware Socket Changes

- Added `IntelSocketProvider`, socket context helpers, market target normalization, and `useMarketSubscription`.
- The socket provider authenticates after bootstrap token availability, stores status/lastMessageAt/event/notification streams, and sends replacement `subscribe` frames when handles, replay, notifications, or registered market targets change.
- Live radar registers visible radar market targets only for the index live route.
- Token target routes register the current route target.
- Search registers the resolver selected target only after a `token_result` inspect response resolves.
- Signal Lab and Stocks do not register market targets.
- Live market updates now patch React Query through `patchTokenRadarLiveMarketUpdate`; components no longer read raw `socket.liveMarketUpdates`.
- Deleted old `web/src/api/useIntelSocket.ts`.
- Added a backend regression proving repeated `subscribe` frames replace `client.market_targets` instead of unioning stale targets.

### Commands

- `uv run pytest tests/integration/test_api_websocket.py -q`: passed, `11 passed in 70.22s`
- `cd web && rg -n 'useIntelSocket|liveMarketUpdates|socket\\.events|socket\\.notifications' src/features src/routes src/app`: no matches; `rg` exited `1` as expected
- `cd web && npm test -- --run src/shared/socket src/features/live src/features/search src/features/token-target`: passed, `10 passed`, `28 passed`
- `cd web && npm run typecheck`: passed
- Extra guard, `cd web && npm run lint`: passed
- Extra guard, `cd web && npm test -- --run`: passed, `28 passed`, `146 passed`

## Task 8 Verification

### Test Pyramid Changes

- Added MSW node server setup under `web/src/test/msw/` and registered it from `web/src/test/setup.ts`.
- Added dev-only test dependencies `msw`, `jest-axe`, `axe-core`, and companion declarations via `@types/jest-axe`.
- Moved the root `web/src/App.test.tsx` coverage to `web/src/features/live/__tests__/CockpitApp.integration.test.tsx`; the root App test file no longer exists.
- Replaced API client module mocks/spies with MSW handlers backed by a test `apiMock`, preserving request path/param assertions without mocking `@lib/api/client`.
- Kept socket behavior isolated through socket-provider test helpers instead of the deleted `useIntelSocket` hook.
- Added L1 axe coverage for cockpit topbar/side rail, shared remote state/icon button, and representative UI in live, search, signal-lab, stocks, token-target, and notifications.
- Removed the `app-integration` Vitest project; all tests run under the standard Vitest config.
- Fixed axe-detected DOM semantics in `RemoteState` and Search UI while adding the accessibility checks.

### Commands

- `cd web && wc -l src/App.test.tsx 2>/dev/null || true`: no output because `src/App.test.tsx` is deleted
- `cd web && rg -n 'vi\\.mock\\(".*api/client|vi\\.mock\\(".*useIntelSocket|vi\\.spyOn\\(client, "getApi"|vi\\.spyOn\\(client, "postApi"' src`: no matches; `rg` exited `1` as expected
- `cd web && npm test -- --run`: passed, `31 passed`, `150 passed`
- `cd web && npm run typecheck`: passed
- Extra guard, `cd web && npm run lint`: passed

## Task 9 Verification

### Playwright Golden Path Changes

- Added dev-only `@playwright/test`.
- Added `test:e2e` and `test:e2e:headed` package scripts.
- Added `web/playwright.config.ts` with a Chromium-only project, `trace: retain-on-failure`, and a `webServer` command that runs `npm run build && npm run preview`.
- Added deterministic Playwright route handlers in `web/e2e/support/mockApi.ts` for `/api/*` endpoints used by the golden paths.
- Added five Chromium golden paths:
  - live cold load renders radar, token tape evidence, and URL-owned filters;
  - topbar search navigates to `/search?q=...` and renders Search Intel state;
  - radar target route renders token audit and post evidence;
  - Signal Lab hard reload preserves filters and opens pulse detail;
  - notification click navigates into Signal Lab context.

### Debugging Notes

The first full `npm run test:e2e` surfaced ErrorBoundary crashes in live/search/token-target flows. Root cause was that the E2E mock timeline/posts payloads were too shallow for the real UI contract: `TokenTimeline` requires `buckets` and `authors`, `StageTape` requires stage `people`/`price` metadata, and `TokenPostsPanel` requires `post_quality`. The mock payloads were expanded to match the existing MSW/Vitest fixture shape before rerunning the full suite.

Two later failures were Playwright strict-mode locator errors because repeated visible text appeared in multiple semantic regions. The assertions were narrowed to the intended search controls and post article while still checking visible page state.

### Commands

- `cd web && npx playwright install chromium`: passed
- `cd web && npm run build`: passed; Vite emitted the existing `Some chunks are larger than 500 kB` warning
- `cd web && npm run test:e2e`: passed, `5 passed`

## Task 10 Verification

### Remote State, CSS, and A11y Changes

- Added the production dependency `clsx`.
- Expanded `RemoteState` to the planned namespace API: `Loading`, `Empty`, `Error`, and `Stale`.
- Replaced text-only loading/empty/error states across live, search, signal-lab, stocks, token-target, and notifications.
- Replaced template-literal class conditionals with `clsx` and variant maps.
- Deleted `web/src/styles.css`; global CSS now lives in `styles/tailwind.css`, `styles/tokens.css`, and `styles/base.css`, while page/component selectors are held in feature-local CSS modules.
- Added a screen-reader label for topbar search, `aria-live="polite"` for the status pill region, and explicit `IconButton` usage/labels for icon-only controls.
- Raised `jsx-a11y/recommended` rules to lint errors.
- Excluded `web/e2e/**` from Vitest collection so Playwright specs only run under Playwright.

### Debugging Notes

The first new `RemoteState` API test was run before implementation and failed with `Cannot read properties of undefined (reading 'Loading')`, proving the expected red test. After implementation, `npm test -- --run src/shared/ui/RemoteState.test.tsx` passed.

The first full `npm test -- --run` after Task 10 changes found two issues: Vitest collected Playwright specs, and one integration assertion expected the previous Signal Lab empty-state sentence. `web/e2e/**` was excluded from Vitest, and the Signal Lab drawer kept the old user-visible text while still using `RemoteState.Empty`.

When CSS was first split into CSS modules, production CSS shrank to about 7 KB because side-effect-only CSS module imports did not retain global selectors. Each module now exposes a tiny `moduleKeep` class that `main.tsx` attaches to `document.documentElement`, preserving module output; the production CSS returned to about 85 KB and includes the migrated selectors.

### Commands

- `cd web && npm install`: passed; installed `clsx` and updated `package-lock.json`
- `cd web && npm test -- --run src/shared/ui/RemoteState.test.tsx`: initially failed before implementation, then passed, `3 passed`
- `cd web && test ! -f src/styles.css`: passed
- `cd web && rg -n 'className=\\{`.*\\$\\{|>loading<|loading\\.\\.\\.|"loading search intel"|<button[^>]*>\\s*<[^>]*(Icon|Search|Refresh|Bell|Home)' src`: no matches; `rg` exited `1` as expected
- `cd web && npm run lint`: passed
- `cd web && npm test -- --run`: passed, `31 passed`, `151 passed`
- `cd web && npm run typecheck`: passed
- `cd web && npm run build`: passed; Vite emitted the existing `Some chunks are larger than 500 kB` warning
- Extra guard, `cd web && npm run test:e2e`: passed, `5 passed`
