# Frontend React/Vite Architecture And Test Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved frontend architecture spec into an executable hard cut: frontend tests move to one `web/tests/` root, route tests move to route ownership, app/routes stop owning feature internals, CSS stops relying on `moduleKeep`, and architecture gates prevent the same coupling from coming back.

**Status:** Draft  
**Date:** 2026-05-14  
**Owning spec:** `docs/superpowers/specs/active/2026-05-14-frontend-react-vite-architecture-test-hard-cut-cn.md`  
**Target branch:** `codex/frontend-react-vite-hard-cut`

**Architecture:** Keep the current React 19 + Vite SPA. The plan changes ownership, not the product stack: `web/src` owns production code, `web/tests` owns all frontend tests and fixtures, root `tests/` stays Python/FastAPI pytest, `app/` owns providers/session bootstrap, `routes/` owns route orchestration, feature `api/model/ui/state` owns feature concerns, and `shared/ui` owns reused presentation primitives.

**Tech Stack:** React 19, Vite 8, TypeScript, React Router, TanStack Query, Zustand, CSS Modules, Vitest, React Testing Library, MSW, Playwright.

---

## Why The Previous Plan Was Not Actionable Enough

The earlier spec named the right direction but did not answer four execution questions clearly enough:

1. **Where do frontend tests live?** They should be centralized under `web/tests/`, not mixed into `web/src`, and not mixed into the root Python `tests/`.
2. **What is the first mergeable slice?** Start with test-root/tooling migration, then route-test harness extraction, because it preserves current behavior before moving architecture.
3. **Which files change in which PR?** Each task below has exact file ownership and commands.
4. **How do we avoid another compatibility layer?** Each slice ends with an architecture gate or deletion check, not a soft convention.

## Scope

In scope:

- Normalize all frontend tests into `web/tests/`, with mirrored source paths for unit/component tests and route integration tests under `web/tests/routes/`.
- Split the 3065-line `web/src/features/live/__tests__/CockpitApp.integration.test.tsx` into focused route tests.
- Move reusable app test setup into `web/tests/render`, `web/tests/msw`, `web/tests/socket`, and `web/tests/fixtures`.
- Reduce `web/src/app/CockpitApp.tsx` and `web/src/routes/AppRoutes.tsx` so app/session, shell state, route data, and feature UI have separate owners.
- Add architecture tests for test placement, relative cross-feature imports, `moduleKeep`, main style imports, and broad feature-level `:global(...)` leakage.
- Remove `moduleKeep` from `web/src/main.tsx` by importing CSS modules from owning components/routes.
- Update stale frontend test governance docs.

Out of scope:

- Rewriting the SPA to Next.js or another React framework.
- Replacing React Query, Zustand, React Router, Vitest, Playwright, or CSS Modules.
- Redesigning Token Radar/Search/Signal Lab visuals beyond the layout regressions caused by ownership cleanup.
- Rewriting all CSS into Tailwind utilities.
- Backend API contract changes.

## Target Directory Structure

The hard cut target is:

```text
web/
  src/
    app/
    routes/
    features/
      cockpit/
      live/
      notifications/
      search/
      signal-lab/
      stocks/
      token-target/
      watchlist/
    shared/
      model/
      query/
      routing/
      socket/
      ui/
    lib/
      api/
      env/
      types/
    styles/
    main.tsx
    vite-env.d.ts
  tests/
    setup.ts
    unit/
      lib/
      shared/
      features/
    component/
      shared/
      features/
    routes/
      live-radar.route.test.tsx
      search.route.test.tsx
      token-target.route.test.tsx
      signal-lab.route.test.tsx
      watchlist.route.test.tsx
      notifications.route.test.tsx
    architecture/
      cssOwnership.test.ts
      featureBoundaries.test.ts
      testPlacement.test.ts
      obsidianArchitectureCleanout.test.ts
    fixtures/
      appRouteFixtures.ts
      marketFixtures.ts
      tokenRadar.ts
      search.ts
      signalPulse.ts
      watchlist.ts
    msw/
      fixtures.ts
      handlers.ts
      scenarios.ts
      server.ts
    render/
      renderWithProviders.tsx
      renderRoute.tsx
    socket/
      socketScenarios.tsx
    e2e/
      golden-paths/
```

Root `tests/` remains the backend pytest tree. It is intentionally not used for frontend tests because `pyproject.toml` sets `testpaths = ["tests"]`, while `web` has its own Vite/Vitest/Playwright TypeScript toolchain.

## Test Migration Map

Move tests by responsibility, not by old location:

| Current pattern | Target pattern |
|-----------------|----------------|
| `web/src/lib/*.test.ts` | `web/tests/unit/lib/*.test.ts` |
| `web/src/shared/model/*.test.ts` | `web/tests/unit/shared/model/*.test.ts` |
| `web/src/shared/query/*.test.ts` | `web/tests/unit/shared/query/*.test.ts` |
| `web/src/features/*/model/*.test.ts` | `web/tests/unit/features/*/model/*.test.ts` |
| `web/src/features/*/state/*.test.ts` | `web/tests/unit/features/*/state/*.test.ts` |
| `web/src/features/*/*.test.ts` pure helper tests | `web/tests/unit/features/*/*.test.ts` |
| `web/src/shared/ui/*.test.tsx` | `web/tests/component/shared/ui/*.test.tsx` |
| `web/src/shared/socket/*.test.tsx` | `web/tests/component/shared/socket/*.test.tsx` |
| `web/src/features/*/api/*.test.tsx` | `web/tests/component/features/*/api/*.test.tsx` |
| `web/src/features/*/ui/*.test.tsx` | `web/tests/component/features/*/ui/*.test.tsx` |
| `web/src/features/*/ui/__tests__/*.routing.test.tsx` that renders only a feature page | `web/tests/component/features/*/ui/*.routing.test.tsx` |
| Any test rendering `<App />` or using `renderAppRoute` | `web/tests/routes/*.route.test.tsx` |
| `web/src/test/obsidianArchitectureCleanout.test.ts` | `web/tests/architecture/obsidianArchitectureCleanout.test.ts` |
| `web/src/test/msw/**` | `web/tests/msw/**` |
| `web/src/test/marketFixtures.ts` | `web/tests/fixtures/marketFixtures.ts` |
| `web/src/test/setup.ts` | `web/tests/setup.ts` |
| `web/e2e/golden-paths/*.spec.ts` | `web/tests/e2e/golden-paths/*.spec.ts` |

## Current Facts This Plan Is Grounded In

- `web/src/main.tsx` imports every feature CSS module and adds `moduleKeep` classes to `document.documentElement`.
- `web/src/app/CockpitApp.tsx` already became small, but it still calls `useLiveRouteState()` and `useLiveData()` before routing.
- `web/src/routes/AppRoutes.tsx` is still 280 lines and owns shell props, notifications, live merge, watchlist cases, Signal Lab compact data, and route declarations.
- `web/src/features/live/useLiveData.ts` owns bootstrap token, status, recent replay, token radar, and Signal Lab compact queries.
- `web/src/features/live/useLiveSelection.ts` imports cockpit internals by relative path and owns route navigation actions.
- `web/src/features/live/__tests__/CockpitApp.integration.test.tsx` is 3065 lines and tests app routing, shell, radar, search, token target, signal lab, watchlist, notifications, socket patching, and API mocks.
- `web/src/test/app-test-case-matrix.md` still references `web/src/App.test.tsx`, which no longer represents current test ownership.

## PR Breakdown

1. **PR 1 — Frontend Test Root:** create `web/tests/`, add `@tests/*`, move existing tests/harness/e2e out of `web/src` and `web/e2e`, update Vitest/Playwright/TypeScript config.
2. **PR 2 — Route Test Harness:** create shared render/API/socket fixtures and prove one small route test can use them. Mergeable on its own.
3. **PR 3 — Split App Integration Tests:** move route integration coverage from `features/live` into `web/tests/routes/`, delete the giant test, and add a placement gate.
4. **PR 4 — Route/Data Ownership:** move session/bootstrap and shell route data out of `live` and shrink `routes/AppRoutes.tsx`.
5. **PR 5 — Public Feature Contracts:** remove relative cross-feature internals and add import-boundary gates.
6. **PR 6 — CSS Ownership And `moduleKeep` Removal:** make owning components import their CSS modules, delete `moduleKeep`, then gate `main.tsx`.
7. **PR 7 — CSS Locality Tightening:** convert broad feature `:global(...)` selectors to local CSS module bindings feature by feature, leaving only documented shared primitives.
8. **PR 8 — Full Verification And Docs:** update docs/generated ownership matrix or delete stale matrix, run full frontend gates, and record visual evidence.

## Task 0: Pre-Flight And Worktree

**Files:**

- Read: `docs/superpowers/specs/active/2026-05-14-frontend-react-vite-architecture-test-hard-cut-cn.md`
- Read: `docs/FRONTEND.md`
- Read: `web/package.json`

- [ ] **Step 0.1: Create isolated worktree**

Run from repo root:

```bash
git worktree add .worktrees/frontend-react-vite-hard-cut -b codex/frontend-react-vite-hard-cut main
cd .worktrees/frontend-react-vite-hard-cut
git branch --show-current
git status --short
```

Expected:

```text
codex/frontend-react-vite-hard-cut
```

`git status --short` has no tracked file changes.

- [ ] **Step 0.2: Capture baseline commands**

Run:

```bash
cd web && npm run lint
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
```

Expected: all commands exit 0. If a baseline command fails, record the failing test name and stop before editing.

## Task 1: Frontend Test Root And Tooling

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/tsconfig.json`
- Modify: `web/playwright.config.ts`
- Modify: `web/package.json`
- Modify: `docs/FRONTEND.md`
- Move: `web/src/test/setup.ts` -> `web/tests/setup.ts`
- Move: `web/src/test/msw/**` -> `web/tests/msw/**`
- Move: `web/src/test/marketFixtures.ts` -> `web/tests/fixtures/marketFixtures.ts`
- Move: `web/src/test/obsidianArchitectureCleanout.test.ts` -> `web/tests/architecture/obsidianArchitectureCleanout.test.ts`
- Move: `web/e2e/golden-paths/**` -> `web/tests/e2e/golden-paths/**`
- Move: `web/src/features/live/__tests__/CockpitApp.integration.test.tsx` -> `web/tests/routes/CockpitApp.integration.test.tsx`
- Delete: `web/src/test/app-test-case-matrix.md`
- Move: all `web/src/**/*.test.ts` and `web/src/**/*.test.tsx` according to the Test Migration Map.

- [ ] **Step 1.1: Add the `@tests/*` alias and include test files in TypeScript**

Update `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "paths": {
      "@app/*": ["src/app/*"],
      "@routes/*": ["src/routes/*"],
      "@features/*": ["src/features/*"],
      "@shared/*": ["src/shared/*"],
      "@lib/*": ["src/lib/*"],
      "@tests/*": ["tests/*"]
    }
  },
  "include": ["src", "tests", "vite.config.ts", "playwright.config.ts"]
}
```

Keep all existing compiler options unchanged; only add the `@tests/*` path and the `tests` / `playwright.config.ts` include entries.

- [ ] **Step 1.2: Point Vitest at `web/tests`**

Update `web/vite.config.ts`:

```ts
const srcPath = (path: string) => new URL(`./src/${path}`, import.meta.url).pathname;
const testsPath = (path: string) => new URL(`./tests/${path}`, import.meta.url).pathname;
```

Add alias:

```ts
"@tests": testsPath("")
```

Update Vitest setup:

```ts
test: {
  environment: "jsdom",
  exclude: [...configDefaults.exclude, "tests/e2e/**"],
  setupFiles: "./tests/setup.ts"
}
```

- [ ] **Step 1.3: Point Playwright at `web/tests/e2e`**

Update `web/playwright.config.ts`:

```ts
testDir: "./tests/e2e/golden-paths",
```

Keep the existing preview server and `baseURL`.

- [ ] **Step 1.4: Lint test code as first-class frontend code**

Update `web/package.json`:

```json
"lint": "eslint --max-warnings=0 src tests vite.config.ts playwright.config.ts"
```

If `web/eslint.config.js` needs file globs updated to include tests, do that in this same step.

- [ ] **Step 1.5: Create the test root and move shared test infrastructure**

Run:

```bash
mkdir -p web/tests/{unit,component,routes,architecture,fixtures,render,socket,e2e}
git mv web/src/test/setup.ts web/tests/setup.ts
git mv web/src/test/msw web/tests/msw
git mv web/src/test/marketFixtures.ts web/tests/fixtures/marketFixtures.ts
git mv web/src/test/obsidianArchitectureCleanout.test.ts web/tests/architecture/obsidianArchitectureCleanout.test.ts
git mv web/e2e/golden-paths web/tests/e2e/golden-paths
git mv web/src/features/live/__tests__/CockpitApp.integration.test.tsx web/tests/routes/CockpitApp.integration.test.tsx
git rm web/src/test/app-test-case-matrix.md
```

Expected: `web/tests/setup.ts`, `web/tests/msw/server.ts`, `web/tests/fixtures/marketFixtures.ts`, `web/tests/architecture/obsidianArchitectureCleanout.test.ts`, and `web/tests/e2e/golden-paths/*.spec.ts` exist.

- [ ] **Step 1.6: Move unit tests out of `web/src`**

Run the moves below, creating target directories before each group:

```bash
mkdir -p web/tests/unit/lib
git mv web/src/lib/*.test.ts web/tests/unit/lib/

mkdir -p web/tests/unit/shared/model web/tests/unit/shared/query
git mv web/src/shared/model/*.test.ts web/tests/unit/shared/model/
git mv web/src/shared/query/*.test.ts web/tests/unit/shared/query/

mkdir -p web/tests/unit/features/live web/tests/unit/features/live/state
git mv web/src/features/live/liveTapeModel.test.ts web/tests/unit/features/live/
git mv web/src/features/live/state/*.test.ts web/tests/unit/features/live/state/

mkdir -p web/tests/unit/features/search web/tests/unit/features/search/model web/tests/unit/features/search/state
git mv web/src/features/search/tokenSearchRoute.test.ts web/tests/unit/features/search/
git mv web/src/features/search/model/*.test.ts web/tests/unit/features/search/model/
git mv web/src/features/search/state/*.test.ts web/tests/unit/features/search/state/

mkdir -p web/tests/unit/features/signal-lab/model web/tests/unit/features/signal-lab/state
git mv web/src/features/signal-lab/model/*.test.ts web/tests/unit/features/signal-lab/model/
git mv web/src/features/signal-lab/state/*.test.ts web/tests/unit/features/signal-lab/state/

mkdir -p web/tests/unit/features/token-target/state web/tests/unit/features/watchlist/model
git mv web/src/features/token-target/state/*.test.ts web/tests/unit/features/token-target/state/
git mv web/src/features/watchlist/model/*.test.ts web/tests/unit/features/watchlist/model/
```

- [ ] **Step 1.7: Move component and hook tests out of `web/src`**

Run:

```bash
mkdir -p web/tests/component/shared/ui web/tests/component/shared/socket
git mv web/src/shared/ui/*.test.tsx web/tests/component/shared/ui/
git mv web/src/shared/socket/*.test.tsx web/tests/component/shared/socket/

mkdir -p web/tests/component/features/cockpit/ui
git mv web/src/features/cockpit/ui/*.test.tsx web/tests/component/features/cockpit/ui/

mkdir -p web/tests/component/features/live/ui
git mv web/src/features/live/ui/*.test.tsx web/tests/component/features/live/ui/

mkdir -p web/tests/component/features/notifications/ui web/tests/component/features/notifications/ui/watchlist
git mv web/src/features/notifications/ui/*.test.tsx web/tests/component/features/notifications/ui/
git mv web/src/features/notifications/ui/__tests__/*.test.tsx web/tests/component/features/notifications/ui/watchlist/

mkdir -p web/tests/component/features/search/ui
git mv web/src/features/search/ui/__tests__/*.test.tsx web/tests/component/features/search/ui/

mkdir -p web/tests/component/features/signal-lab/api web/tests/component/features/signal-lab/ui
git mv web/src/features/signal-lab/api/*.test.tsx web/tests/component/features/signal-lab/api/
git mv web/src/features/signal-lab/ui/*.test.tsx web/tests/component/features/signal-lab/ui/
git mv web/src/features/signal-lab/ui/__tests__/*.test.tsx web/tests/component/features/signal-lab/ui/

mkdir -p web/tests/component/features/stocks/ui web/tests/component/features/token-target/ui
git mv web/src/features/stocks/ui/*.test.tsx web/tests/component/features/stocks/ui/
git mv web/src/features/token-target/ui/__tests__/*.test.tsx web/tests/component/features/token-target/ui/
```

After each move group, update imports that point to old `web/src/test` helpers so they use `@tests/*`.

- [ ] **Step 1.8: Update frontend architecture docs**

Update `docs/FRONTEND.md`:

- Change the layer map row from `test/` to `web/tests/`.
- State that `web/src` contains production code only.
- State that root `tests/` is backend pytest, while `web/tests/` is frontend Vitest/Playwright.

- [ ] **Step 1.9: Add a temporary placement smoke check**

Run:

```bash
find web/src -name "*.test.*" -o -name "*.spec.*" -print
test ! -d web/src/test
test ! -d web/e2e
```

Expected: the `find` command prints nothing; both `test ! -d` commands exit 0.

- [ ] **Step 1.10: Verify PR 1**

Run:

```bash
cd web && npm run lint
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run test:e2e
```

Expected: all commands exit 0 after imports are updated to the new `@tests/*` alias.

## Task 2: Route Test Harness

**Files:**

- Create: `web/tests/render/renderWithProviders.tsx`
- Create: `web/tests/render/renderRoute.tsx`
- Create: `web/tests/socket/socketScenarios.tsx`
- Create: `web/tests/fixtures/appRouteFixtures.ts`
- Create: `web/tests/msw/scenarios.ts`
- Modify: `web/tests/msw/fixtures.ts`
- Test: `web/tests/routes/live-radar.route.test.tsx`

- [ ] **Step 2.1: Add the provider render harness**

Create `web/tests/render/renderWithProviders.tsx` with a reusable QueryClient + MemoryRouter wrapper:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/",
    queryClient = createTestQueryClient(),
    ...options
  }: RenderOptions & { route?: string; queryClient?: QueryClient } = {},
) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );

  return {
    queryClient,
    ...render(ui, { wrapper: Wrapper, ...options }),
  };
}
```

- [ ] **Step 2.2: Add the app route render harness**

Create `web/tests/render/renderRoute.tsx`:

```tsx
import { App } from "../../src/App";
import { renderWithProviders } from "./renderWithProviders";

export function renderAppRoute(route: string) {
  return renderWithProviders(<App />, { route });
}
```

- [ ] **Step 2.3: Extract socket scenario helpers**

Create `web/tests/socket/socketScenarios.tsx` with the mutable socket snapshot currently embedded in `CockpitApp.integration.test.tsx`. Export these names:

```tsx
export const socketScenario = {
  status: "connected",
  events: [],
  notifications: [],
  liveMarketUpdates: [],
  lastMessageAt: 1_777_770_000_000,
};

export function resetSocketScenario() {
  socketScenario.status = "connected";
  socketScenario.events = [];
  socketScenario.notifications = [];
  socketScenario.liveMarketUpdates = [];
  socketScenario.lastMessageAt = 1_777_770_000_000;
}
```

Keep the existing `vi.mock("@shared/socket/...")` declarations inside route test files in this PR. Move those mocks to `socketScenarios.tsx` only after one route test proves the harness works.

- [ ] **Step 2.4: Add app API scenarios**

Create `web/tests/msw/scenarios.ts` and move the reusable bootstrap/status/recent/token-radar fixture setup out of the integration test. Export these scenario functions:

```ts
import {
  appStatusFixture,
  recentReplayFixture,
  signalPulseFixture,
  tokenRadarFixture,
} from "../fixtures/appRouteFixtures";
import type { ApiMock } from "./fixtures";
import { defaultBootstrap, ok } from "./fixtures";

export function mockBootstrap(apiMock: ApiMock) {
  apiMock.getBootstrapImpl = async () => defaultBootstrap();
}

export function mockAppShellStatus(apiMock: ApiMock) {
  apiMock.getApiImpl = async (path) => {
    if (path === "/api/status") return ok(appStatusFixture());
    throw new Error(`unexpected path ${path}`);
  };
}

export function mockLiveRadarRoute(apiMock: ApiMock) {
  apiMock.getApiImpl = async (path) => {
    if (path === "/api/status") return ok(appStatusFixture());
    if (path === "/api/recent") return ok(recentReplayFixture());
    if (path === "/api/token-radar") return ok(tokenRadarFixture());
    if (path === "/api/signal-lab/pulse") return ok(signalPulseFixture());
    throw new Error(`unexpected path ${path}`);
  };
}
```

Define `appStatusFixture()`, `recentReplayFixture()`, `tokenRadarFixture()`, and `signalPulseFixture()` in `web/tests/fixtures/appRouteFixtures.ts` by moving the existing literals from `CockpitApp.integration.test.tsx`.

- [ ] **Step 2.5: Prove the harness with one route test**

Create `web/tests/routes/live-radar.route.test.tsx` with one test migrated from the giant integration file:

```tsx
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { createApiMock, resetApiMock } from "@tests/msw/fixtures";
import { apiHandlers } from "@tests/msw/handlers";
import { server } from "@tests/msw/server";
import { mockBootstrap, mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";

const apiMock = createApiMock();

describe("live radar route", () => {
  beforeEach(() => {
    resetApiMock(apiMock);
    server.use(...apiHandlers(apiMock));
    mockBootstrap(apiMock);
    mockLiveRadarRoute(apiMock);
  });

  it("renders Token Radar as the default route", async () => {
    renderAppRoute("/");
    expect(await screen.findByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2.6: Verify PR 2**

Run:

```bash
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx
cd web && npm run typecheck
```

Expected: both commands exit 0.

## Task 3: Split App Integration Tests By Route

**Files:**

- Create: `web/tests/routes/live-radar.route.test.tsx`
- Create: `web/tests/routes/search.route.test.tsx`
- Create: `web/tests/routes/token-target.route.test.tsx`
- Create: `web/tests/routes/signal-lab.route.test.tsx`
- Create: `web/tests/routes/watchlist.route.test.tsx`
- Create: `web/tests/routes/notifications.route.test.tsx`
- Create: `web/tests/architecture/testPlacement.test.ts`
- Delete: `web/tests/routes/CockpitApp.integration.test.tsx`
- Create: `docs/generated/frontend-test-ownership.md`

- [ ] **Step 3.1: Move default radar route coverage**

Move these behaviors from temporary `web/tests/routes/CockpitApp.integration.test.tsx` into `web/tests/routes/live-radar.route.test.tsx`:

- Default route renders Token Radar columns.
- Radar row opens token target/search route.
- WebSocket market update patches visible token radar row.
- Window/scope controls update route/search params.

Keep this file under 500 lines. If it exceeds 500 lines, split market patching into `web/tests/routes/live-market-updates.route.test.tsx`.

- [ ] **Step 3.2: Move search route coverage**

Create `web/tests/routes/search.route.test.tsx` and move only `/search` workflow coverage:

- Topbar submit navigates to `/search?q=<query>&window=24h&scope=<scope>`.
- Search route renders token/keyword/ambiguous states from MSW scenarios.
- Search route does not render the old right-side `Select Token` empty state.

- [ ] **Step 3.3: Move token-target route coverage**

Create `web/tests/routes/token-target.route.test.tsx` and move only `/token/:targetType/:targetId` coverage:

- Token target route loads target header.
- Token target route renders shared `Social x Market Timeline`.
- Page container scrolls when content exceeds viewport.
- Timeline wheel interactions do not trap page scroll.

- [ ] **Step 3.4: Move Signal Lab and Watchlist route coverage**

Create:

- `web/tests/routes/signal-lab.route.test.tsx`
- `web/tests/routes/watchlist.route.test.tsx`

Move only route-level shell behavior into these files. Focused component tests stay under `web/tests/component/features/*/ui/`.

- [ ] **Step 3.5: Move notification route/shell coverage**

Create `web/tests/routes/notifications.route.test.tsx` for shell notification drawer behavior:

- Bell shows unread count from status/socket summary.
- Drawer opens and closes from topbar.
- Notification navigation uses public path builders.

- [ ] **Step 3.6: Add route-test placement gate**

Create `web/tests/architecture/testPlacement.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");
const testsRoot = join(webRoot, "tests");

describe("frontend test placement", () => {
  it("keeps production src free of frontend test files", () => {
    const offenders = collectFiles(srcRoot)
      .filter((path) => /\.(test|spec)\.(ts|tsx)$/.test(path))
      .map((path) => relative(webRoot, path));

    expect(offenders).toEqual([]);
  });

  it("keeps route integration tests under tests/routes", () => {
    const offenders = collectFiles(testsRoot)
      .filter((path) => /\.test\.tsx$/.test(path))
      .filter((path) => readTest(path))
      .filter((path) => !relative(testsRoot, path).startsWith("routes/"))
      .map((path) => relative(webRoot, path));

    expect(offenders).toEqual([]);
  });
});

function readTest(path: string): boolean {
  const text = readFileSync(path, "utf8");
  return /from\s+["'].*App["']|<App\s*\/>|renderAppRoute/.test(text);
}

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
```

- [ ] **Step 3.7: Replace stale matrix**

Create `docs/generated/frontend-test-ownership.md` with a short pointer:

```markdown
# App Route Test Ownership

Route integration tests live under `web/tests/routes/`.
Focused model/component tests live under `web/tests/unit/` and `web/tests/component/`, mirroring production source paths.
The executable source of truth is `web/tests/architecture/testPlacement.test.ts`.
```

- [ ] **Step 3.8: Verify PR 3**

Run:

```bash
test ! -f web/tests/routes/CockpitApp.integration.test.tsx
cd web && npm test -- --run tests/routes tests/architecture/testPlacement.test.ts
cd web && npm test -- --run
cd web && npm run typecheck
```

Expected: no giant integration file remains; route tests and full Vitest suite exit 0.

## Task 4: Route/Data Ownership Split

**Files:**

- Create: `web/src/app/useAppSession.ts`
- Create: `web/src/features/cockpit/api/useCockpitStatusQuery.ts`
- Create: `web/src/features/cockpit/model/cockpitShellModel.ts`
- Create: `web/src/features/live/api/useLiveRecentQuery.ts`
- Create: `web/src/features/live/api/useLiveRadarRouteData.ts`
- Create: `web/src/features/signal-lab/api/useSignalLabCompactQuery.ts`
- Modify: `web/src/app/CockpitApp.tsx`
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/routes/live.route.tsx`
- Modify: `web/src/routes/signal-lab.route.tsx`
- Modify: `web/src/features/live/useLiveData.ts`
- Test: `web/tests/routes/live-radar.route.test.tsx`
- Test: `web/tests/routes/signal-lab.route.test.tsx`

- [ ] **Step 4.1: Move bootstrap/auth into app session**

Create `web/src/app/useAppSession.ts`. Move the bootstrap query and `setAuthToken` effect from `useLiveData` into this hook:

```ts
import { getBootstrap, setAuthToken } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

export function useAppSession() {
  const [token, setToken] = useState("");
  const bootstrapQuery = useQuery({
    queryKey: queryKeys.bootstrap(),
    queryFn: getBootstrap,
    staleTime: Infinity,
  });

  useEffect(() => {
    const wsToken = bootstrapQuery.data?.data.ws_token;
    if (!wsToken) return;
    setAuthToken(wsToken);
    setToken(wsToken);
  }, [bootstrapQuery.data?.data.ws_token]);

  return useMemo(
    () => ({
      token,
      bootstrapHandles: bootstrapQuery.data?.data.handles ?? [],
      replayLimit: Math.min(25, bootstrapQuery.data?.data.replay_limit ?? 25),
      bootstrapLoading: bootstrapQuery.isPending,
      bootstrapError: bootstrapQuery.isError,
    }),
    [bootstrapQuery.data, bootstrapQuery.isError, bootstrapQuery.isPending, token],
  );
}
```

- [ ] **Step 4.2: Make `CockpitApp` provider-only**

Change `web/src/app/CockpitApp.tsx` so it no longer imports `@features/live`. It should call `useAppSession()` and render:

```tsx
<IntelSocketProvider
  token={session.token}
  handles={session.bootstrapHandles.join(",")}
  replay={session.replayLimit}
  notifications
>
  <AppRoutes session={session} />
</IntelSocketProvider>
```

Acceptance: `rg "useLiveData|useLiveRouteState|@features/live" web/src/app/CockpitApp.tsx` returns no matches.

- [ ] **Step 4.3: Split live route queries**

Create:

- `web/src/features/live/api/useLiveRecentQuery.ts` for `/api/recent`.
- `web/src/features/live/api/useLiveRadarRouteData.ts` for token radar items, decision counts, market targets, and live replay merge inputs.

Move token radar item derivation from `useLiveData` into `useLiveRadarRouteData`. Keep pure derivation in feature model files where possible.

- [ ] **Step 4.4: Split cockpit status and Signal Lab compact queries**

Create:

- `web/src/features/cockpit/api/useCockpitStatusQuery.ts` for `/api/status`.
- `web/src/features/signal-lab/api/useSignalLabCompactQuery.ts` for compact `/api/signal-lab/pulse`.

`routes/AppRoutes.tsx` may consume these public hooks to build shell props. `features/live/useLiveData.ts` must stop fetching Signal Lab compact data.

- [ ] **Step 4.5: Move route adapters to route files**

Move route-specific composition into route modules:

- `web/src/routes/live.route.tsx` owns live route state, live recent, radar data, live tape merge, and market subscription target list.
- `web/src/routes/signal-lab.route.tsx` owns Signal Lab route state and compact query handoff.
- `web/src/routes/watchlist.route.tsx` receives account cases from a route-level adapter or computes them from public live/cockpit data.

`web/src/routes/AppRoutes.tsx` should only build the shell frame and declare routes. It should not destructure token radar data, Signal Lab data, or watchlist case models directly.

- [ ] **Step 4.6: Verify PR 4**

Run:

```bash
rg "useLiveData|useLiveRouteState|@features/live" web/src/app/CockpitApp.tsx
rg "signalLabPulseQuery|signalPulseOverviewQuery" web/src/features/live web/src/routes -n
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/routes/signal-lab.route.test.tsx
cd web && npm run typecheck
```

Expected: first `rg` returns no matches; second `rg` finds only the new Signal Lab compact hook or route adapter; tests/typecheck exit 0.

## Task 5: Public Feature Contracts And Import Gates

**Files:**

- Modify: `web/src/features/cockpit/index.ts`
- Modify: `web/src/features/live/useLiveSelection.ts`
- Modify: `web/src/features/notifications/useNotificationsController.ts`
- Create: `web/tests/architecture/featureBoundaries.test.ts`
- Modify: `web/eslint.config.js`
- Test: `web/tests/architecture/featureBoundaries.test.ts`

- [ ] **Step 5.1: Export cockpit public contracts**

Update `web/src/features/cockpit/index.ts` to export only stable contracts used by other layers:

```ts
export { CockpitShell } from "./ui/CockpitShell";
export { SearchShell } from "./ui/SearchShell";
export { requiredMobileTaskForPathname } from "./model/mobileRouteTask";
export { useCockpitStore } from "./state/cockpitStore";
export type { MobileTask } from "./model/mobileTask";
```

- [ ] **Step 5.2: Remove relative cross-feature cockpit imports**

Change `web/src/features/live/useLiveSelection.ts` from relative imports like `../cockpit/model/mobileRouteTask` to public imports from `@features/cockpit`.

Acceptance:

```bash
rg "\\.\\./cockpit|\\.\\./search|\\.\\./signal-lab|\\.\\./watchlist" web/src/features -n
```

Expected: no matches outside tests.

- [ ] **Step 5.3: Add relative cross-feature import gate**

Create `web/tests/architecture/featureBoundaries.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");
const sourceExtensions = new Set([".ts", ".tsx"]);

describe("feature boundaries", () => {
  it("does not import another feature internals by relative path", () => {
    const offenders = collectFiles(join(srcRoot, "features"))
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => !path.includes(".test."))
      .flatMap((path) => {
        const rel = relative(webRoot, path);
        const matches = [...readFileSync(path, "utf8").matchAll(/\.\.\/(cockpit|live|search|signal-lab|stocks|token-target|watchlist)\/(api|model|state|ui)\//g)];
        return matches.map((match) => `${rel}: ${match[0]}`);
      });

    expect(offenders).toEqual([]);
  });
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
```

- [ ] **Step 5.4: Extend ESLint import restrictions**

Update `web/eslint.config.js` so alias deep imports remain blocked and add patterns for `@features/*/{api,model,state,ui}/*` from outside public indexes. Keep the architecture test as the relative-path backstop because ESLint cannot reliably infer owner from relative paths here.

- [ ] **Step 5.5: Verify PR 5**

Run:

```bash
cd web && npm test -- --run tests/architecture/featureBoundaries.test.ts
cd web && npm run lint
cd web && npm run typecheck
```

Expected: commands exit 0.

## Task 6: CSS Module Ownership And `moduleKeep` Removal

**Files:**

- Modify: `web/src/main.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- Modify: `web/src/features/live/ui/LivePage.tsx`
- Modify: `web/src/features/live/ui/LiveRadar.tsx`
- Modify: `web/src/features/search/ui/SearchIntelPage.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPage.tsx`
- Modify: `web/src/features/stocks/ui/StocksRadarPage.tsx`
- Modify: `web/src/features/token-target/ui/TokenTargetPage.tsx`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify: `web/src/shared/ui/obsidian.tsx`
- Modify: `web/src/shared/ui/RemoteState.tsx`
- Modify: `web/src/shared/ui/TokenProfileCard.tsx`
- Modify: CSS module files that currently contain `.moduleKeep`
- Create: `web/tests/architecture/cssOwnership.test.ts`

- [ ] **Step 6.1: Import CSS modules from owners**

Add side-effect imports in the component or primitive package that owns each CSS module:

```tsx
import "./cockpit.module.css";
```

Use this owner map:

- `cockpit.module.css` -> `CockpitShell.tsx`
- `live.module.css` -> `LiveRadar.tsx` and `LivePage.tsx`
- `search.module.css` -> `SearchIntelPage.tsx`
- `signalLab.module.css` -> `SignalLabPage.tsx`
- `stocks.module.css` -> `StocksRadarPage.tsx`
- `tokenTarget.module.css` -> `TokenTargetPage.tsx`
- `watchlist.module.css` -> `WatchlistPage.tsx`
- `obsidian.module.css` -> `obsidian.tsx`
- `shared.module.css` -> shared components that use its class names, starting with `RemoteState.tsx` and `TokenProfileCard.tsx`

- [ ] **Step 6.2: Remove module retention from `main.tsx`**

Edit `web/src/main.tsx` so it imports only:

```ts
import "./styles/tailwind.css";
import "./styles/tokens.css";
import "./styles/base.css";
import { AppRoot } from "./app/AppRoot";
```

Delete all CSS module imports and the `document.documentElement.classList.add(...)` block.

- [ ] **Step 6.3: Delete `.moduleKeep` selectors**

Remove every `:local(.moduleKeep)` rule from:

- `web/src/shared/ui/obsidian.module.css`
- `web/src/shared/ui/shared.module.css`
- `web/src/features/cockpit/ui/cockpit.module.css`
- `web/src/features/live/ui/live.module.css`
- `web/src/features/search/ui/search.module.css`
- `web/src/features/signal-lab/ui/signalLab.module.css`
- `web/src/features/stocks/ui/stocks.module.css`
- `web/src/features/token-target/ui/tokenTarget.module.css`
- `web/src/features/watchlist/ui/watchlist.module.css`

- [ ] **Step 6.4: Add `main.tsx` and `moduleKeep` gate**

Create `web/tests/architecture/cssOwnership.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");

describe("CSS ownership", () => {
  it("keeps main.tsx free of feature CSS retention", () => {
    const main = readFileSync(join(srcRoot, "main.tsx"), "utf8");
    expect(main).not.toContain("moduleKeep");
    expect(main).not.toContain("document.documentElement.classList.add");
    expect(main).not.toMatch(/features\/.+\.module\.css/);
    expect(main).not.toMatch(/shared\/ui\/.+\.module\.css/);
  });

  it("does not define moduleKeep classes", () => {
    const offenders = collectFiles(srcRoot)
      .filter((path) => extname(path) === ".css")
      .filter((path) => readFileSync(path, "utf8").includes("moduleKeep"))
      .map((path) => relative(webRoot, path));

    expect(offenders).toEqual([]);
  });
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
```

- [ ] **Step 6.5: Verify PR 6**

Run:

```bash
rg "moduleKeep|documentElement.classList.add" web/src -n
cd web && npm test -- --run tests/architecture/cssOwnership.test.ts
cd web && npm run build
```

Expected: `rg` returns no matches; test/build exit 0.

## Task 7: CSS Locality Tightening

**Files:**

- Modify: `web/tests/architecture/cssOwnership.test.ts`
- Modify: `web/src/features/cockpit/ui/*.tsx`
- Modify: `web/src/features/cockpit/ui/cockpit.module.css`
- Modify: `web/src/features/live/ui/*.tsx`
- Modify: `web/src/features/live/ui/live.module.css`
- Modify: `web/src/features/search/ui/*.tsx`
- Modify: `web/src/features/search/ui/search.module.css`
- Modify: `web/src/features/token-target/ui/*.tsx`
- Modify: `web/src/features/token-target/ui/tokenTarget.module.css`
- Modify: `web/src/features/watchlist/ui/*.tsx`
- Modify: `web/src/features/watchlist/ui/watchlist.module.css`

- [ ] **Step 7.1: Add broad `:global` gate with shared primitive allowlist**

Extend `cssOwnership.test.ts`:

```ts
const allowedGlobalPrefixes = [
  "ods-",
  "remote-state-",
  "token-profile-",
  "market-timeline-",
];
```

The test should fail when a feature CSS module defines `:global(.some-feature-class)` unless the class begins with one of the allowed shared prefixes. Shared primitive CSS under `web/src/shared/ui` may keep documented global primitive classes in this pass.

- [ ] **Step 7.2: Convert cockpit CSS selectors to local bindings**

In cockpit TSX files, import:

```tsx
import styles from "./cockpit.module.css";
```

Replace feature-owned class strings with local bindings:

```tsx
className={styles["cockpit-shell"]}
className={styles["side-rail"]}
className={styles["topbar"]}
```

In `cockpit.module.css`, replace matching `:global(.cockpit-shell)` selectors with local `.cockpit-shell` selectors.

- [ ] **Step 7.3: Convert live radar CSS selectors to local bindings**

In `LiveRadar.tsx`, `TokenRadarTable.tsx`, `TokenRadarRow.tsx`, and `LiveSignalTape.tsx`, import `styles` from `live.module.css` and replace feature-owned classes:

```tsx
className={styles["radar-panel"]}
className={styles["radar-row"]}
className={styles["token-radar-table"]}
```

Use `clsx(styles["radar-row"], selected && styles.selected)` for state classes. Keep `data-*` attributes only when tests or semantics need them.

- [ ] **Step 7.4: Convert search/token-target/watchlist feature selectors**

Repeat the same local-binding conversion for:

- `web/src/features/search/ui/search.module.css` and search UI files.
- `web/src/features/token-target/ui/tokenTarget.module.css` and token target UI files.
- `web/src/features/watchlist/ui/watchlist.module.css` and watchlist UI files.

Do one feature at a time and run that feature's tests after each conversion.

- [ ] **Step 7.5: Verify PR 7**

Run:

```bash
cd web && npm test -- --run tests/architecture/cssOwnership.test.ts
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run build
```

Expected: commands exit 0. Any remaining `:global(...)` in feature CSS must be either removed or added to an explicit shared primitive allowlist in `cssOwnership.test.ts`.

## Task 8: Full Frontend Verification And Browser Smoke

**Files:**

- Modify: `docs/superpowers/plans/active/2026-05-14-frontend-react-vite-architecture-test-hard-cut-plan-cn.md`
- Create or modify: `docs/superpowers/plans/active/2026-05-14-frontend-react-vite-architecture-test-hard-cut-verification-cn.md`
- Create or update: `docs/generated/frontend-test-ownership.md`

- [ ] **Step 8.1: Run full frontend gates**

Run:

```bash
cd web && npm run lint
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
cd web && npm run test:e2e
```

Expected: all commands exit 0.

- [ ] **Step 8.2: Run static ownership scans**

Run:

```bash
rg "moduleKeep|documentElement.classList.add" web/src -n
rg "\\.\\./(cockpit|live|search|signal-lab|stocks|token-target|watchlist)/(api|model|state|ui)" web/src/features web/src/routes -n
rg "compat|legacy|stage-tape|detail-drawer|obsidian-hard-cut" web/src -n
find web/src -name "*.test.*" -o -name "*.spec.*" -print
find web/tests/routes -name "CockpitApp.integration.test.tsx" -print
```

Expected:

- First command returns no matches.
- Second command returns no matches outside architecture tests.
- Third command returns no product-code matches; architecture tests may include forbidden strings as test fixtures.
- Fourth command returns no files.
- Fifth command returns no files.

- [ ] **Step 8.3: Browser smoke the routes**

Start the built app or existing Docker app, then browser-smoke these routes:

- `/`
- `/search?q=gmgn&window=24h&scope=all`
- `/signal-lab`
- `/stocks`
- `/watchlist`
- `/token/Asset/asset%3Asolana%3Atoken%3A4yEjcMiy6GAgrpWpUvhUXfaP1vQmJXfqJjEyxBSZpump?window=1h&scope=all`

Check:

- No incoherent overlap at desktop and mobile widths.
- Token target page scrolls.
- Social x Market Timeline appears on Search token mode and Token target pages.
- Topbar, side rail, and center column align under the same shell variables.
- Browser console has no uncaught runtime errors.

- [ ] **Step 8.4: Record verification**

Create `docs/superpowers/plans/active/2026-05-14-frontend-react-vite-architecture-test-hard-cut-verification-cn.md` with:

- Command outputs or summarized pass/fail lines.
- Browser route smoke notes.
- Any remaining `:global(...)` allowlist entries and why they are shared primitives.
- Residual risk list.

## Merge Criteria

The work is complete only when:

- The giant feature-owned app integration test is gone.
- All route integration tests live under `web/tests/routes/`.
- `web/src/app/CockpitApp.tsx` has no dependency on `@features/live`.
- `web/src/routes/AppRoutes.tsx` is route declaration and shell composition, not feature data orchestration.
- `web/src/main.tsx` imports only global base styles and `AppRoot`.
- `rg "moduleKeep|documentElement.classList.add" web/src -n` returns no matches.
- `cd web && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run test:e2e` exits 0.
