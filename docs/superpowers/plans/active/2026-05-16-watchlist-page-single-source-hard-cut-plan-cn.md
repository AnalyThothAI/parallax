# Watchlist Page Single Source Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/watchlist` a single-source, API-backed handle drilldown that no longer mixes persisted watchlist facts with `/api/recent` / WebSocket replay-derived account cases.

**Architecture:** Reuse the existing `watchlist_intel` domain and event-token projection. Add derived overview read endpoints, hard-delete the selected-page live-buffer path, isolate watchlist route state with `timeline_scope`, and introduce a small shared route-return control used by Token Case and Watchlist. No new tables, workers, provider calls, or compatibility fallbacks.

**Tech Stack:** Python 3, FastAPI, psycopg, pytest, React 19, TypeScript, TanStack Query, React Router, Vitest/RTL, Playwright, Vite.

**Status:** Implemented
**Date:** 2026-05-16
**Owning spec:** `docs/superpowers/specs/active/2026-05-16-watchlist-page-single-source-hard-cut-cn.md`
**Worktree:** `.worktrees/watchlist-single-source-hard-cut/` (removed after local merge)
**Branch:** `codex/watchlist-single-source-hard-cut` (merged into `main`)

---

## Pre-flight

- [ ] Spec is approved.
- [ ] Create and enter the worktree:
  ```bash
  git worktree add .worktrees/watchlist-single-source-hard-cut -b codex/watchlist-single-source-hard-cut
  cd .worktrees/watchlist-single-source-hard-cut
  git branch --show-current
  ```
  Expected branch: `codex/watchlist-single-source-hard-cut`.
- [ ] Verify baseline status:
  ```bash
  git status --short
  ```
  Expected: no unrelated local edits inside the worktree.
- [ ] Run focused baseline tests:
  ```bash
  uv run pytest tests/integration/watchlist/ tests/unit/domains/watchlist_intel/ -q
  cd web && npm test -- --run tests/unit/features/watchlist tests/component/features/watchlist tests/routes/watchlist.route.test.tsx
  ```
  Expected: pass, or record existing failures before editing.

Known-failing baseline tests:

- None expected.

## File-level Edits

### Backend API And Domain Reads

- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/repositories/watchlist_intel_repository.py:376-440`
  - Add derived overview methods using existing facts.
  - Keep raw SQL in the repository.
  - Reuse `EventTokenProjectionQuery(self.conn).for_events(...)` for resolved token projection.
  - Extract shared row decoding/aggregation helpers so timeline and overview do not duplicate token/candidate parsing.

- Modify `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_service.py:177-223`
  - Extend `WatchlistHandleReadService` with handle-list overview and selected-handle overview methods.
  - Keep summary/timeline methods intact.
  - Validate configured handle membership through the same `_configured_handle(...)` path.

- Modify `src/gmgn_twitter_intel/app/surfaces/api/schemas.py:225-244`
  - Add `WatchlistHandleOverviewData`.
  - Add `WatchlistHandlesOverviewData`.
  - Use typed Pydantic submodels for overview query, metrics, clusters, and handle rows.

- Modify `src/gmgn_twitter_intel/app/surfaces/api/http.py:132-186`
  - Add authenticated `GET /api/watchlist/handles/overview`.
  - Add authenticated `GET /api/watchlist/handle/{handle}/overview`.
  - Use the same handle normalization and unknown-handle 404 behavior as summary/timeline.

- Regenerate:
  - `docs/generated/openapi.json`
  - `web/src/lib/types/openapi.ts`

### Frontend Watchlist Feature

- Modify `web/src/routes/AppRoutes.tsx:1-210`
  - Remove `buildWatchlistAccountCases` import and selected-page account-case creation.
  - Add watchlist handle overview query for sidebar rows.
  - Pass `handles`, `accountUnreadCounts`, and `token` to `WatchlistRoute`.

- Modify `web/src/routes/watchlist.route.tsx:1-8`
  - Replace `accountCases` route props with hard-cut props:
    - `handles: string[]`
    - `accountUnreadCounts?: Record<string, number> | null`
    - `token: string`

- Modify `web/src/features/watchlist/state/watchlistRouteState.ts:1-26`
  - Canonical URL key becomes `timeline_scope`.
  - Do not parse old `scope=signal|all`.
  - Preserve `handle` on scope updates.

- Create `web/src/features/watchlist/api/useWatchlistHandlesOverviewQuery.ts`
  - Fetch `/api/watchlist/handles/overview`.

- Create `web/src/features/watchlist/api/useHandleOverviewQuery.ts`
  - Fetch `/api/watchlist/handle/{handle}/overview`.

- Modify `web/src/features/watchlist/api/useHandleTimelineQuery.ts:6-31`
  - Keep API query parameter `scope`.
  - Route state supplies `timeline_scope`.

- Replace `web/src/features/watchlist/model/watchlistCase.ts`
  - Delete `WatchlistAccountCase` and `buildWatchlistAccountCases`.
  - Keep or move `normalizeWatchlistHandle` into a focused route/handle model.
  - Add pure mappers for overview rows and display labels only.

- Modify `web/src/features/watchlist/model/watchlistRows.ts:1-46`
  - Replace live-item derivation with server handle overview rows plus notification unread counts.

- Split `web/src/features/watchlist/ui/WatchlistPage.tsx:1-430`
  - Keep `WatchlistPage` as the route composer.
  - Move focused components to:
    - `web/src/features/watchlist/ui/WatchlistHero.tsx`
    - `web/src/features/watchlist/ui/WatchlistMetricStrip.tsx`
    - `web/src/features/watchlist/ui/HandleTopicSummary.tsx`
    - `web/src/features/watchlist/ui/HandleTimeline.tsx`
    - `web/src/features/watchlist/ui/HandleTimelineItem.tsx`
    - `web/src/features/watchlist/ui/WatchlistInsightRail.tsx`

- Modify `web/src/features/watchlist/ui/watchlist.css`
  - Keep existing Obsidian visual language.
  - Add styles for resolved targets vs candidate mentions.
  - Remove selectors only used by deleted account-case evidence lists.

- Modify `web/src/features/watchlist/index.ts`
  - Export new hooks/types/components used by routes.
  - Stop exporting deleted account-case types/builders.

### Shared Banner Return Control

- Create `web/src/shared/ui/RouteBackLink.tsx`
  - A small router-provider-free return link with ArrowLeft icon, label, and accessible name.

- Create `web/src/shared/ui/RouteBackLink.module.css`
  - Local styles for the shared return control.

- Modify `web/src/shared/ui/case-file/TokenCaseHero.tsx:37-42`
  - Replace naked `<a href="/">返回</a>` with `RouteBackLink`.

- Modify `web/src/shared/ui/case-file/TokenCaseHero.module.css:17-39`
  - Remove token-case-local back link styling or map it to the shared component wrapper.

- Modify `web/src/features/watchlist/ui/WatchlistHero.tsx`
  - Add the same `RouteBackLink` to `/` with label `返回`.

### Tests And Architecture Gates

- Add backend tests:
  - `tests/integration/watchlist/test_watchlist_overview_api.py`
  - `tests/unit/test_watchlist_overview_model.py` if aggregation helpers are pure enough to test without PostgreSQL.

- Modify existing backend tests:
  - `tests/integration/watchlist/test_watchlist_intel_api.py`
  - `tests/integration/watchlist/test_watchlist_intel_repository.py`

- Add frontend tests:
  - `web/tests/unit/features/watchlist/state/watchlistRouteState.test.ts`
  - `web/tests/unit/features/watchlist/model/watchlistRows.test.ts`
  - `web/tests/unit/features/watchlist/model/watchlistOverview.test.ts`
  - `web/tests/component/features/watchlist/api/useHandleOverviewQuery.test.tsx`
  - `web/tests/component/features/watchlist/api/useWatchlistHandlesOverviewQuery.test.tsx`
  - `web/tests/component/features/watchlist/ui/WatchlistPage.test.tsx`
  - `web/tests/component/shared/ui/RouteBackLink.test.tsx`

- Modify frontend architecture tests:
  - `web/tests/architecture/featureBoundaries.test.ts`
  - Add or extend an architecture grep that rejects selected-page `accountCases` and watchlist-local `scope=signal|all` parsing.

## Public Payload Shapes

The exact generated OpenAPI types are produced by `make regen-contract`; implementation should target these semantic shapes.

### `WatchlistHandlesOverviewData`

```ts
type WatchlistHandlesOverviewData = {
  window: "24h" | "7d";
  items: WatchlistHandleRowOverview[];
};

type WatchlistHandleRowOverview = {
  handle: string;
  last_source_event_at_ms: number | null;
  recent_source_event_count: number;
  recent_signal_event_count: number;
  total_signal_event_count: number;
  summary_status: "ready" | "not_ready";
  summary_is_stale: boolean;
};
```

### `WatchlistHandleOverviewData`

```ts
type WatchlistHandleOverviewData = {
  query: {
    handle: string;
    scope: "signal" | "all";
    window: "24h" | "7d";
  };
  metrics: {
    source_event_count: number;
    signal_event_count: number;
    resolved_token_count: number;
    candidate_mention_count: number;
    narrative_count: number;
    last_source_event_at_ms: number | null;
  };
  resolved_token_clusters: WatchlistCluster[];
  candidate_mention_clusters: WatchlistCluster[];
  narrative_clusters: WatchlistCluster[];
  clusters_truncated: boolean;
  risk_notes: string[];
};

type WatchlistCluster = {
  label: string;
  count: number;
  query: string;
  kind: "resolved_token" | "candidate_mention" | "narrative";
  target_type?: "Asset" | "CexToken";
  target_id?: string;
  symbol?: string | null;
  source: "token_resolutions" | "social_event_candidates" | "event_cashtags" | "event_hashtags" | "anchor_terms";
};
```

## PR Breakdown

1. **PR 1 — Backend overview contract**  
   Adds overview repository/read-service/API/schema tests and regenerated OpenAPI. No frontend runtime changes beyond generated types.

2. **PR 2 — Watchlist frontend hard cut**  
   Replaces selected-page account-case props with overview/summary/timeline hooks, splits Watchlist UI components, changes route key to `timeline_scope`, and updates tests.

3. **PR 3 — Shared banner return + cleanup gates**  
   Adds `RouteBackLink`, updates Token Case and Watchlist heroes, deletes old compatibility exports/tests, adds architecture grep gates, and runs browser QA.

Each PR should be independently reviewable. PR 2 depends on PR 1 generated types. PR 3 depends on PR 2 only for final cleanup tests.

## Task 1: Backend RED Tests For Overview Contract

**Files:**
- Create: `tests/integration/watchlist/test_watchlist_overview_api.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_repository.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_api.py`

- [ ] **Step 1: Add selected-handle overview API test**

Add a test that seeds:

- two source events for `marionawfal`;
- one `social_event_extractions.is_signal_event=true` row with `token_candidates=[{"symbol":"ALOY"}]`;
- one event with a resolved `CexToken` resolution;
- one hashtag.

Expected response from `/api/watchlist/handle/marionawfal/overview?scope=signal`:

```python
assert response.status_code == 200
data = response.json()["data"]
assert data["metrics"]["signal_event_count"] == 1
assert data["metrics"]["candidate_mention_count"] == 1
assert data["metrics"]["resolved_token_count"] == 1
assert data["candidate_mention_clusters"][0]["label"] == "$ALOY"
assert data["resolved_token_clusters"][0]["kind"] == "resolved_token"
```

- [ ] **Step 2: Add all-scope overview test**

Seed one non-signal event with a hashtag. Assert `scope=all` includes it in `source_event_count` and narrative clusters, while `scope=signal` excludes it.

- [ ] **Step 3: Add handle-list overview test**

Call `/api/watchlist/handles/overview` with settings handles `("marionawfal", "toly")`. Assert the endpoint returns only configured handles and includes persisted last-seen values.

- [ ] **Step 4: Add error contract tests**

Assert:

```python
client.get("/api/watchlist/handle/unknown/overview?token=secret").status_code == 404
client.get("/api/watchlist/handle/marionawfal/overview?token=secret&scope=legacy").status_code == 400
client.get("/api/watchlist/handle/%20/overview?token=secret").status_code == 400
```

- [ ] **Step 5: Run red tests**

```bash
uv run pytest tests/integration/watchlist/test_watchlist_overview_api.py tests/integration/watchlist/test_watchlist_intel_repository.py -k "overview" -q
```

Expected: fail because overview endpoints and repository methods do not exist yet.

## Task 2: Backend GREEN Implementation

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Regenerate: `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`

- [ ] **Step 1: Add repository overview methods**

Add methods with these signatures:

- `handles_overview(self, *, handles: Sequence[str], since_ms: int) -> list[dict[str, Any]]`
- `handle_overview(self, *, handle: str, scope: str, since_ms: int, limit: int = 500) -> dict[str, Any]`

Implementation constraints:

- Normalize every handle with `normalize_watchlist_handle`.
- Use `lower(e.author_handle) = %s`, matching the existing expression index.
- For `scope="signal"`, require `se.is_signal_event = TRUE`.
- Fetch event ids once, then call `self.token_resolutions_for_events(...)`.
- Aggregate clusters from fetched rows and projected token resolutions.
- Do not call external providers.
- Do not create or update any tables.

- [ ] **Step 2: Add deterministic cluster helper**

Keep it private to the repository or a same-domain pure module. It must produce stable ordering:

1. descending count;
2. resolved token clusters before candidate clusters before narratives;
3. case-insensitive label ascending.

Cluster rules:

- `resolved_token_clusters`: from `token_resolutions[*].symbol` or CEX target suffix.
- `candidate_mention_clusters`: from `social_event.token_candidates[*].symbol` and event cashtags not present in resolved cluster keys.
- `narrative_clusters`: from hashtags and non-token anchor terms.
- `risk_notes`: include `"candidate_mentions_unresolved"` when candidate count is greater than resolved count.

- [ ] **Step 3: Add read-service methods**

Add methods:

- `handles_overview(self, *, configured_handles: Sequence[str], now_ms: int | None = None) -> dict[str, Any]`
- `overview(self, *, handle: str, configured_handles: Sequence[str], scope: str, now_ms: int | None = None) -> dict[str, Any]`

Use a fixed first implementation window of 7 days, matching the handle-summary operating window. Do not read frontend route state here.

- [ ] **Step 4: Add API endpoints**

Add routes beside the existing watchlist routes:

- `GET /watchlist/handles/overview`, response model `ApiEnvelope[WatchlistHandlesOverviewData]`.
- `GET /watchlist/handle/{handle}/overview`, response model `ApiEnvelope[WatchlistHandleOverviewData]`, query parameter `scope=signal|all` with default `signal`.

Error behavior:

- invalid handle: `ApiBadRequest("invalid_handle", field="handle")`;
- unknown configured handle: 404 `handle_not_found`;
- invalid scope: `ApiBadRequest("invalid_scope", field="scope")`.

- [ ] **Step 5: Regenerate contracts**

```bash
make regen-contract
```

Expected changed files:

- `docs/generated/openapi.json`
- `web/src/lib/types/openapi.ts`

- [ ] **Step 6: Run backend green tests**

```bash
uv run pytest tests/integration/watchlist/test_watchlist_overview_api.py tests/integration/watchlist/test_watchlist_intel_api.py tests/integration/watchlist/test_watchlist_intel_repository.py -q
uv run ruff check src/gmgn_twitter_intel/domains/watchlist_intel src/gmgn_twitter_intel/app/surfaces/api tests/integration/watchlist
```

Expected: pass.

## Task 3: Frontend RED Tests For Hard Cut

**Files:**
- Modify: `web/tests/unit/features/watchlist/state/watchlistRouteState.test.ts`
- Modify: `web/tests/unit/features/watchlist/model/watchlistRows.test.ts`
- Create: `web/tests/unit/features/watchlist/model/watchlistOverview.test.ts`
- Create: `web/tests/component/features/watchlist/api/useHandleOverviewQuery.test.tsx`
- Create: `web/tests/component/features/watchlist/api/useWatchlistHandlesOverviewQuery.test.tsx`
- Modify: `web/tests/component/features/watchlist/ui/WatchlistPage.test.tsx`
- Modify: `web/tests/routes/watchlist.route.test.tsx`

- [ ] **Step 1: Add route-state hard-cut tests**

Assert:

```ts
expect(parseWatchlistRouteState(new URLSearchParams("handle=marionawfal&timeline_scope=all"), "toly")).toEqual({
  selectedHandle: "marionawfal",
  timelineScope: "all",
});
expect(parseWatchlistRouteState(new URLSearchParams("handle=marionawfal&scope=all"), "toly").timelineScope).toBe("signal");
```

The second assertion proves old `scope` is not a compatibility path.

- [ ] **Step 2: Add hook tests**

For `useHandleOverviewQuery`, assert the request path and params:

```ts
expect(requests).toEqual([
  "/api/watchlist/handle/marionawfal/overview?scope=signal",
]);
```

For `useWatchlistHandlesOverviewQuery`, assert:

```ts
expect(requests).toEqual(["/api/watchlist/handles/overview?"]);
```

- [ ] **Step 3: Add page test for candidate vs resolved display**

Mock overview with:

- `resolved_token_count: 0`;
- `candidate_mention_count: 3`;
- `candidate_mention_clusters: [{ label: "$ALOY", count: 3, kind: "candidate_mention" }]`.

Render `/watchlist?handle=marionawfal&timeline_scope=signal`. Assert:

```ts
expect(screen.getByText("Resolved targets")).toBeInTheDocument();
expect(screen.getByText("0")).toBeInTheDocument();
expect(screen.getByText("Candidate mentions")).toBeInTheDocument();
expect(screen.getByText("$ALOY")).toBeInTheDocument();
```

- [ ] **Step 4: Add route integration hard-cut test**

Render `AppRoutes` with no socket events and no `/api/recent` items. Mock watchlist overview/timeline with persisted data. Assert selected page still renders persisted counts and clusters.

- [ ] **Step 5: Run red frontend tests**

```bash
cd web
npm test -- --run tests/unit/features/watchlist/state/watchlistRouteState.test.ts tests/unit/features/watchlist/model/watchlistRows.test.ts tests/unit/features/watchlist/model/watchlistOverview.test.ts tests/component/features/watchlist/api/useHandleOverviewQuery.test.tsx tests/component/features/watchlist/api/useWatchlistHandlesOverviewQuery.test.tsx tests/component/features/watchlist/ui/WatchlistPage.test.tsx tests/routes/watchlist.route.test.tsx
```

Expected: fail because hooks, route state, and page props still use the old path.

## Task 4: Frontend GREEN Hard Cut

**Files:**
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/routes/watchlist.route.tsx`
- Modify: `web/src/features/watchlist/state/watchlistRouteState.ts`
- Create: `web/src/features/watchlist/api/useHandleOverviewQuery.ts`
- Create: `web/src/features/watchlist/api/useWatchlistHandlesOverviewQuery.ts`
- Modify: `web/src/features/watchlist/api/useHandleTimelineQuery.ts`
- Replace/modify: `web/src/features/watchlist/model/watchlistCase.ts`
- Modify: `web/src/features/watchlist/model/watchlistRows.ts`
- Modify/split: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Create: focused Watchlist UI component files listed above.
- Modify: `web/src/features/watchlist/index.ts`

- [ ] **Step 1: Rewrite route state**

Expose:

```ts
export type WatchlistRouteState = {
  selectedHandle: string | null;
  timelineScope: WatchlistTimelineScope;
};
```

The parser reads `timeline_scope`; the serializer writes `timeline_scope`; old `scope` is ignored.

- [ ] **Step 2: Add overview hooks**

Implement `useHandleOverviewQuery` and `useWatchlistHandlesOverviewQuery` in `features/watchlist/api`. They must be the only new code that calls `getApi` for overview endpoints.

- [ ] **Step 3: Hard-cut `WatchlistPage` props**

New prop shape:

```ts
type WatchlistPageProps = {
  handles: string[];
  accountUnreadCounts?: Record<string, number> | null;
  token: string;
};
```

Remove `accountCases`, `selectedCase`, `emptyAccountCase`, and page-level live-buffer fallbacks.

- [ ] **Step 4: Move selected-handle facts to overview data**

Hero:

- handle from route state;
- last seen from `overview.metrics.last_source_event_at_ms`;
- search/open X actions unchanged.

Metric strip:

- notification unread count from `accountUnreadCounts?.[handle]`;
- source events from overview metrics;
- resolved targets from overview metrics;
- candidate mentions from overview metrics;
- narratives from overview metrics.

Insight rail:

- resolved token clusters;
- candidate mention clusters;
- narrative clusters;
- risk notes.

- [ ] **Step 5: Rewrite watchlist rows**

`buildWatchlistRows` input becomes:

```ts
type BuildWatchlistRowsInput = {
  rows: WatchlistHandleRowOverview[];
  accountUnreadCounts?: Record<string, number> | null;
};
```

Sort by:

1. unread count desc;
2. `last_source_event_at_ms` desc;
3. configured/server order.

No `LivePayload` import in `watchlistRows.ts`.

- [ ] **Step 6: Delete old selected-page model path**

Remove exports and tests for:

- `WatchlistAccountCase`;
- `WatchlistEvidence`;
- `buildWatchlistAccountCases`;
- live-buffer token/narrative clustering for selected handle.

Keep only handle normalization if still needed, in a focused model file.

- [ ] **Step 7: Run frontend green tests**

```bash
cd web
npm test -- --run tests/unit/features/watchlist/state/watchlistRouteState.test.ts tests/unit/features/watchlist/model/watchlistRows.test.ts tests/unit/features/watchlist/model/watchlistOverview.test.ts tests/component/features/watchlist/api/useHandleOverviewQuery.test.tsx tests/component/features/watchlist/api/useWatchlistHandlesOverviewQuery.test.tsx tests/component/features/watchlist/ui/WatchlistPage.test.tsx tests/routes/watchlist.route.test.tsx
npm run typecheck
```

Expected: pass.

## Task 5: Shared Banner Return Control

**Files:**
- Create: `web/src/shared/ui/RouteBackLink.tsx`
- Create: `web/src/shared/ui/RouteBackLink.module.css`
- Modify: `web/src/shared/ui/index.ts` if present, otherwise import directly through `@shared/ui/RouteBackLink`.
- Modify: `web/src/shared/ui/case-file/TokenCaseHero.tsx`
- Modify: `web/src/shared/ui/case-file/TokenCaseHero.module.css`
- Modify: `web/src/features/watchlist/ui/WatchlistHero.tsx`
- Create: `web/tests/component/shared/ui/RouteBackLink.test.tsx`
- Modify/create: token-case hero component test if needed.

- [ ] **Step 1: Write shared component test**

Assert:

```ts
renderWithProviders(<RouteBackLink to="/" label="返回" ariaLabel="返回 Token Radar" />, { route: "/token/Asset/x" });
const link = screen.getByRole("link", { name: "返回 Token Radar" });
expect(link).toHaveAttribute("href", "/");
expect(link).toHaveTextContent("返回");
```

- [ ] **Step 2: Implement `RouteBackLink`**

Use `Link` from `react-router-dom`, `ArrowLeft` from `lucide-react`, and CSS Module styling. Do not use a naked `<a href="/">`.

- [ ] **Step 3: Replace Token Case hero return**

`TokenCaseHero` imports `RouteBackLink` and renders it in the existing top bar.

- [ ] **Step 4: Add Watchlist hero return**

`WatchlistHero` renders the same component with `to="/"`, label `返回`, and `ariaLabel="返回 Token Radar"`.

- [ ] **Step 5: Run tests**

```bash
cd web
npm test -- --run tests/component/shared/ui/RouteBackLink.test.tsx tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx tests/component/features/watchlist/ui/WatchlistPage.test.tsx
npm run lint
```

Expected: pass.

## Task 6: Compatibility Deletion And Static Gates

**Files:**
- Modify: `web/tests/architecture/featureBoundaries.test.ts`
- Modify or create: `web/tests/architecture/watchlistHardCut.test.ts`
- Modify: deleted old test imports under `web/tests/unit/features/watchlist/model/watchlistCase.test.ts`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 1: Add architecture grep test**

Reject these runtime patterns under `web/src`:

```ts
[
  "WatchlistAccountCase",
  "buildWatchlistAccountCases",
  "accountCases=",
  "searchParams.get(\"scope\") as WatchlistTimelineScope",
]
```

Allow references only in completed/active docs and deleted-test history is not relevant inside `web/src`.

- [ ] **Step 2: Remove old tests**

Delete or rewrite tests that assert live-buffer selected-page account cases. The new tests should assert overview API behavior.

- [ ] **Step 3: Update tech debt**

Remove or close `watchlist-page-data-source-split` if present. Add a dated note that the split was hard-cut by this plan.

- [ ] **Step 4: Run static gates**

```bash
cd web
npm test -- --run tests/architecture tests/unit/features/watchlist tests/component/features/watchlist tests/routes/watchlist.route.test.tsx
npm run lint
npm run typecheck
```

Expected: pass.

## Task 7: Docs And Generated Contract Alignment

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md` if route-state ownership examples need updating.
- Modify: `docs/generated/openapi.json`
- Modify: `web/src/lib/types/openapi.ts`
- Modify: `docs/generated/frontend-test-ownership.md` only if generation requires it.

- [ ] **Step 1: Update contracts**

Add Watchlist overview endpoints to the Watchlist handle intel contract:

- `/api/watchlist/handles/overview`;
- `/api/watchlist/handle/{handle}/overview`;
- canonical frontend route key `timeline_scope`.

- [ ] **Step 2: Update frontend docs**

Clarify that `features/watchlist/api` owns selected-handle summary, overview, and timeline server state. The selected page does not consume `/api/recent`.

- [ ] **Step 3: Regenerate contracts again after final API changes**

```bash
make regen-contract
```

Expected: generated files match schema changes and no unrelated drift.

- [ ] **Step 4: Run docs checks**

```bash
uv run pytest tests/integration/test_docs_generated.py -q
```

Expected: pass.

## Task 8: End-to-End Verification

**Files:** no implementation files.

- [ ] **Step 1: Run backend verification**

```bash
uv run pytest tests/integration/watchlist/ tests/unit/domains/watchlist_intel/ tests/integration/test_api_http.py -q
uv run ruff check src/gmgn_twitter_intel/domains/watchlist_intel src/gmgn_twitter_intel/app/surfaces/api tests/integration/watchlist
```

- [ ] **Step 2: Run frontend verification**

```bash
cd web
npm test -- --run tests/unit/features/watchlist tests/component/features/watchlist tests/component/shared/ui/RouteBackLink.test.tsx tests/routes/watchlist.route.test.tsx tests/architecture
npm run typecheck
npm run lint
npm run build
```

- [ ] **Step 3: Browser QA against local app**

Open:

```text
http://localhost:8765/watchlist?handle=marionawfal&timeline_scope=signal
http://localhost:8765/watchlist?handle=marionawfal&timeline_scope=all
http://localhost:8765/token/Asset/asset%3Aeip155%3A1%3Aerc20%3A0xf280b16ef293d8e534e370794ef26bf312694126
```

Verify:

- Watchlist candidate mentions and resolved targets are separate.
- Watchlist does not show empty live-buffer metrics when timeline rows exist.
- Scope switch updates `timeline_scope`, not `scope`.
- Token Case and Watchlist use the same return control.
- No failing `/api/watchlist/*` requests.
- No console errors.
- Desktop and mobile viewports have no overlapping text.

- [ ] **Step 4: Full gate before merge**

```bash
make check-all
```

Expected: pass. Record output in the verification artifact before declaring complete.

## Rollout Order

1. Merge backend overview contract and generated types.
2. Merge frontend hard cut after generated types are available.
3. Merge shared banner cleanup and architecture gates.
4. Deploy normally with the existing service image.
5. Verify production `/watchlist?handle=<configured>&timeline_scope=signal` with one high-volume handle and one low-volume handle.

No database migration is required.

## Rollback

- Backend overview endpoints are additive and can be reverted without data migration.
- Frontend hard cut can be reverted as a single PR if the new overview endpoints are unhealthy, but do not reintroduce partial compatibility in the same branch.
- Because no schema changes are introduced, rollback is code-only.

## Acceptance Test Commands

- AC1, AC2, AC3:
  ```bash
  uv run pytest tests/integration/watchlist/test_watchlist_overview_api.py -q
  cd web && npm test -- --run tests/component/features/watchlist/ui/WatchlistPage.test.tsx
  ```

- AC4, AC5:
  ```bash
  cd web && npm test -- --run tests/unit/features/watchlist/state/watchlistRouteState.test.ts tests/routes/watchlist.route.test.tsx
  ```

- AC6:
  ```bash
  cd web && npm test -- --run tests/component/shared/ui/RouteBackLink.test.tsx tests/component/features/watchlist/ui/WatchlistPage.test.tsx tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx
  ```

- AC7:
  ```bash
  cd web && npm test -- --run tests/architecture
  ```

- AC8, AC9:
  ```bash
  uv run pytest tests/integration/watchlist/test_watchlist_overview_api.py::test_watchlist_handle_overview_rejects_unknown_handle tests/integration/watchlist/test_watchlist_overview_api.py::test_watchlist_handle_overview_uses_public_token_projection -q
  ```

## Verification

Create `docs/superpowers/plans/active/2026-05-16-watchlist-page-single-source-hard-cut-verification.md` before declaring the implementation complete. It must include:

- implementation summary mapped to this plan;
- full command output for targeted backend tests;
- full command output for frontend tests/typecheck/lint/build;
- browser QA notes with URLs and viewport sizes;
- skipped tests and reason;
- remaining risks and tech-debt updates;
- final `make check-all` output or explicit blocker.
