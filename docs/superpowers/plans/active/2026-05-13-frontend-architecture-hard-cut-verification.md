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

## Current Risks / Pauses

- Task 8 requires new dev dependencies: `msw`, `jest-axe`, `axe-core`.
- Task 9 requires new dev dependency: `@playwright/test`.
- Task 10 requires new production dependency: `clsx`.

Per the execution pause conditions, dependency installation must pause for user confirmation before adding the Task 10 production dependency.

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
