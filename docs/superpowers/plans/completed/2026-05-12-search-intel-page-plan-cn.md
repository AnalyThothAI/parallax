# Search Intel Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a route-backed `/search` second-level result page that turns a manual search into a dense 24h token/topic intelligence surface with Twitter evidence, project summary, propagation analysis, and bull/bear agent views.

**Architecture:** Keep KISS: add one read-only aggregate endpoint, one route, and focused frontend components. The backend composes existing Search V2, target timeline, target posts, token radar, and deterministic agent-brief builders; no storage migration, no background job, and no fake OHLC. The frontend renders the resolver-selected result kind directly: token result, topic result, or ambiguous candidates.

**Tech Stack:** FastAPI, PostgreSQL read models, Python dataclass/dict payloads, React Router, React Query, TypeScript, existing CSS. No chart dependency in the first cut; use compact CSS/SVG timeline from returned buckets. Add Lightweight Charts only after a real OHLC endpoint exists.

---

## Status

**Status:** Completed
**Date:** 2026-05-12
**Owning spec:** `docs/superpowers/specs/completed/2026-05-12-search-intel-page-kiss-cn.md`
**Prototype:** `docs/prototypes/search-intel-page-prototype.html`
**Worktree:** `.worktrees/search-intel-page/`
**Branch:** `codex/search-intel-page`

## Product Shape

The search page is not a new left-rail view. It appears only after the user submits the top search box or opens a shareable URL:

- Token URL: `/search?q=$RKC&window=24h&scope=all`
- Keyword URL: `/search?q=%E6%8C%96%E7%9F%BF&window=24h&scope=all`
- Ambiguous URL: same route, with resolver returning multiple candidates.

The page hides the old right-side detail drawer and left `views` rail while on `/search`. The top search remains manual: typing does not rerun the page until submit.

Agent block design:

- **项目总结:** What the project/query is, what happened in the past 24h, current state, and data gaps.
- **传播:** Seed/amplifier/validation/decay path, key accounts, stage-level propagation facts.
- **多空观点:** Bull thesis, bear thesis, upgrade triggers, invalidation triggers, and evidence ids.

## Data Contract

Create `SearchInspectData` in both backend payload docs and `web/src/api/types.ts`.

```ts
export type SearchInspectData = {
  query: {
    q: string;
    normalized_q: string;
    window: WindowKey;
    scope: ScopeKey;
    result_kind: "token_result" | "topic_result" | "ambiguous_result" | "empty_result";
  };
  resolver: {
    confidence: number;
    target_candidates: SearchTargetCandidate[];
    selected_target?: SearchTargetCandidate | null;
    reasons: string[];
  };
  token_result?: SearchTokenResult | null;
  topic_result?: SearchTopicResult | null;
  ambiguous_result?: SearchAmbiguousResult | null;
};

export type SearchAgentBrief = {
  schema_version: "search_agent_brief_v1";
  generated_by: "deterministic";
  project_summary: {
    one_liner: string;
    summary_zh: string;
    current_state: string;
    data_gaps: string[];
    evidence_event_ids: string[];
  };
  propagation: {
    summary_zh: string;
    phases: Array<{
      phase: string;
      window_label: string;
      tweets: number;
      authors: number;
      lead_accounts: string[];
      read_zh: string;
      evidence_event_ids: string[];
    }>;
    key_accounts: Array<{ handle: string; role: string; posts: number; first_seen_ms?: number | null }>;
  };
  bull_bear: {
    stance: "watch" | "research" | "avoid" | "unknown";
    bull: { thesis_zh: string; evidence_event_ids: string[]; triggers_zh: string[] };
    bear: { thesis_zh: string; evidence_event_ids: string[]; invalidations_zh: string[] };
  };
};
```

Backend payload rules:

- Token result uses `/api/target-social-timeline` semantics with `window=24h`, `limit=200`, plus `/api/target-posts` with `range=current_window`, `sort=recent`, `limit=200`.
- Topic result uses `/api/search` semantics filtered to the requested window and summarizes returned search items.
- Ambiguous result never picks a token automatically; it shows candidates plus 24h topic evidence for the raw query.
- `market_overlay.price_series_type` must be `"anchor_line"` until real OHLC exists.

## File-Level Edits

### Backend

- Create `src/parallax/domains/token_intel/read_models/search_agent_brief.py`
  - Responsible for deterministic `SearchAgentBrief`.
  - New public functions:
    - `build_token_agent_brief(*, target, timeline, posts, radar_item) -> dict[str, Any]`
    - `build_topic_agent_brief(*, query, items) -> dict[str, Any]`
  - No LLM call in this file.

- Create `src/parallax/domains/token_intel/read_models/search_inspect_service.py`
  - Responsible for composing Search V2 + timeline + posts + radar into `SearchInspectData`.
  - New class:
    - `SearchInspectService(search_query, token_radar, targets)`
    - `inspect(q: str, *, window: str, scope: str, limit: int, now_ms: int | None = None) -> dict[str, Any]`

- Modify `src/parallax/domains/token_intel/read_models/search_service.py`
  - Add optional `window: str = "24h"` and `now_ms: int | None = None`.
  - Pass `since_ms` into `SearchEventsQuery` so keyword results are actually 24h-scoped.
  - Hard-cut old unwindowed search behavior; default `/api/search` to `window=24h`.

- Modify `src/parallax/domains/token_intel/queries/search_events_query.py`
  - Add optional `since_ms` to `route_hits`, `target_hits_page`, `_target_hits`, `_handle_hits`, `_lexical_hits`, `_substring_hits`, `_trigram_hits`.
  - Add `AND events.received_at_ms >= %s` to each route when `since_ms` is provided.

- Modify `src/parallax/app/surfaces/api/http.py`
  - Add `GET /api/search/inspect`.
  - Add optional `window` to `/api/search` for consistency.
  - Return bad request for unsupported window/scope with existing helpers.

- Modify `docs/CONTRACTS.md`
  - Document `/api/search/inspect`.
  - Document `search_agent_brief_v1`.
  - State that price overlay is anchor-only, not OHLC.

### Frontend

- Create `web/src/api/useSearchInspectQuery.ts`
  - React Query hook for `/api/search/inspect`.
  - Query key: `["search-inspect", q, window, scope]`.
  - Disabled when `q.trim()` is empty.

- Modify `web/src/api/types.ts`
  - Add `SearchInspectData`, `SearchAgentBrief`, `SearchTokenResult`, `SearchTopicResult`, `SearchAmbiguousResult`.

- Create `web/src/features/search/searchRouteState.ts`
  - Parse/serialize `q`, `window`, `scope`.
  - Defaults: `window=24h`, `scope=all`.

- Create `web/src/components/SearchIntelPage.tsx`
  - Owns route state, query hook, loading/error/empty states.
  - Renders one of:
    - `SearchTokenResultView`
    - `SearchTopicResultView`
    - `SearchAmbiguousResultView`

- Create `web/src/components/SearchAgentBrief.tsx`
  - Renders exactly three sections: 项目总结, 传播, 多空观点.
  - Does not hide evidence ids.

- Create `web/src/components/SearchTwitterResults.tsx`
  - Dense 24h Twitter table: time, phase/match type, account, content, engagement, market anchor, evidence id.
  - Supports stage filter from timeline clicks.

- Create `web/src/components/SearchTimelinePanel.tsx`
  - Compact social bucket timeline with price anchor overlay when available.
  - Labels anchor overlay clearly as anchor, not K-line.

- Modify `web/src/app/CockpitApp.tsx`
  - Add route: `<Route path="search" element={<SearchIntelPage />} />`.

- Modify `web/src/features/live/useLiveSelection.ts`
  - On search submit, navigate to `/search?q=${query}&window=${windowKey}&scope=${scope}`.
  - Stop opening the old query detail drawer for normal search submissions.
  - Keep token page opening only for explicit token row actions, not for global search.

- Modify `web/src/components/CockpitLayout.tsx`
  - Detect `location.pathname.startsWith("/search")`.
  - Add `search-focus-mode` class to `.cockpit-grid`.
  - Hide side rail and detail panel in search focus mode.

- Modify `web/src/styles.css`
  - Add `.cockpit-grid.search-focus-mode`.
  - Add dense search page styles matching prototype.
  - Reuse existing tokens/colors; do not introduce marketing hero/card layout.

### Tests

- Create `tests/unit/test_search_agent_brief.py`.
- Create `tests/unit/test_search_inspect_service.py`.
- Modify `tests/unit/test_search_service.py`.
- Modify `tests/integration/test_api_http.py`.
- Create `web/src/features/search/searchRouteState.test.ts`.
- Create `web/src/components/__tests__/SearchIntelPage.routing.test.tsx`.
- Create `web/src/components/__tests__/SearchAgentBrief.test.tsx`.

## Task 1: Route Search To The New Page

**Files:**

- Modify: `web/src/features/live/useLiveSelection.ts`
- Modify: `web/src/app/CockpitApp.tsx`
- Create: `web/src/features/search/searchRouteState.ts`
- Test: `web/src/features/search/searchRouteState.test.ts`
- Test: `web/src/components/__tests__/SearchIntelPage.routing.test.tsx`

- [ ] **Step 1: Write route-state tests**

```ts
import { describe, expect, it } from "vitest";

import { parseSearchRouteState, serializeSearchRouteState } from "./searchRouteState";

describe("searchRouteState", () => {
  it("defaults to 24h/all and preserves q", () => {
    expect(parseSearchRouteState(new URLSearchParams("q=%24RKC"))).toEqual({
      q: "$RKC",
      window: "24h",
      scope: "all",
    });
  });

  it("drops unsupported window and scope values", () => {
    expect(parseSearchRouteState(new URLSearchParams("q=mining&window=bad&scope=bad"))).toEqual({
      q: "mining",
      window: "24h",
      scope: "all",
    });
  });

  it("serializes stable shareable URLs", () => {
    expect(
      serializeSearchRouteState({ q: "挖矿", window: "24h", scope: "all" }).toString(),
    ).toBe("q=%E6%8C%96%E7%9F%BF&window=24h&scope=all");
  });
});
```

- [ ] **Step 2: Implement route-state helpers**

```ts
import type { ScopeKey, WindowKey } from "../../api/types";

const VALID_WINDOWS = new Set<WindowKey>(["5m", "1h", "4h", "24h"]);
const VALID_SCOPES = new Set<ScopeKey>(["all", "matched"]);

export type SearchRouteState = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function parseSearchRouteState(params: URLSearchParams): SearchRouteState {
  const windowParam = params.get("window") as WindowKey | null;
  const scopeParam = params.get("scope") as ScopeKey | null;
  return {
    q: params.get("q")?.trim() ?? "",
    window: windowParam && VALID_WINDOWS.has(windowParam) ? windowParam : "24h",
    scope: scopeParam && VALID_SCOPES.has(scopeParam) ? scopeParam : "all",
  };
}

export function serializeSearchRouteState(state: SearchRouteState): URLSearchParams {
  const next = new URLSearchParams();
  if (state.q.trim()) next.set("q", state.q.trim());
  next.set("window", state.window);
  next.set("scope", state.scope);
  return next;
}
```

- [ ] **Step 3: Add stub page route**

Create `SearchIntelPage.tsx` with an empty-state shell first, wire it into `CockpitApp.tsx`, and assert a MemoryRouter render at `/search?q=%24RKC` shows `Search Intel`.

- [ ] **Step 4: Change global search submit**

In `submitEvidenceSearch`, replace the old non-token branch with route navigation:

```ts
const next = new URLSearchParams();
next.set("q", query);
next.set("window", windowKey);
next.set("scope", scope);
navigate(`/search?${next.toString()}`);
setSelectedSignal(null);
setSelectedTapeEventId(null);
setSelectedBucketStartMs(null);
setSelectedEventId(null);
setMobileTask("radar");
```

Keep existing Signal Lab behavior when `isSignalLabRoute` is true.

- [ ] **Step 5: Run focused frontend tests**

Run:

```bash
cd web && npm run test -- searchRouteState SearchIntelPage.routing
```

Expected: both new test files pass.

## Task 2: Add 24h Windowing To Search Read Model

**Files:**

- Modify: `src/parallax/domains/token_intel/read_models/search_service.py`
- Modify: `src/parallax/domains/token_intel/queries/search_events_query.py`
- Modify: `tests/unit/test_search_service.py`

- [ ] **Step 1: Write failing unit test**

Add a fake `SearchEventsQuery` that records `since_ms`, then assert `SearchService.search("挖矿", window="24h", now_ms=1_700_086_400_000)` passes `since_ms=1_700_000_000_000`.

- [ ] **Step 2: Implement optional window support**

Add `WINDOW_MS` import from `asset_flow_service` in `search_service.py`, compute `since_ms` only when `window` is provided, and pass it into `route_hits` and `target_hits_page`.

- [ ] **Step 3: Add SQL predicates**

In every `SearchEventsQuery` route helper, append `AND events.received_at_ms >= %s` only when `since_ms` is not `None`. Do this by building `time_clause` and `params` explicitly; do not string-interpolate values.

- [ ] **Step 4: Run backend focused tests**

Run:

```bash
uv run pytest tests/unit/test_search_service.py -q
```

Expected: all search service tests pass.

## Task 3: Build Deterministic Agent Brief

**Files:**

- Create: `src/parallax/domains/token_intel/read_models/search_agent_brief.py`
- Test: `tests/unit/test_search_agent_brief.py`

- [ ] **Step 1: Write token brief test**

Fixture should include:

- timeline summary with 73 posts, 18 authors, top_author_share `0.22`
- four stages: seed, ignition, expansion, chase
- posts with event ids `ev_401`, `ev_433`, `ev_482`, `ev_556`

Assertions:

- `schema_version == "search_agent_brief_v1"`
- `project_summary.summary_zh` mentions 24h and current state
- `propagation.phases` has four items
- `bull_bear.bull.triggers_zh` is non-empty
- `bull_bear.bear.invalidations_zh` is non-empty
- every cited evidence id exists in input posts/stages

- [ ] **Step 2: Implement brief builder**

Rules:

- Project summary is deterministic from target symbol, timeline summary, stage phases, and market gaps.
- Propagation phases come from timeline stages first, then buckets if stages are empty.
- Bull thesis uses breadth, watched posts, low top-author share, expansion phase.
- Bear thesis uses chase phase, duplicate/price-only late posts, missing market data.
- Stance:
  - `watch` when authors >= 3 and posts >= 5 and phase is not `seed`
  - `research` when there are posts but weak author breadth
  - `unknown` when no posts
  - `avoid` when duplicate_text_share >= 0.6 or top_author_share >= 0.7

- [ ] **Step 3: Run unit test**

Run:

```bash
uv run pytest tests/unit/test_search_agent_brief.py -q
```

Expected: new brief test passes.

## Task 4: Add `/api/search/inspect`

**Files:**

- Create: `src/parallax/domains/token_intel/read_models/search_inspect_service.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Test: `tests/unit/test_search_inspect_service.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Write inspect service tests**

Cover four cases:

- one resolved candidate returns `result_kind="token_result"`
- no resolved candidate but search items returns `result_kind="topic_result"`
- multiple resolved/ambiguous candidates returns `result_kind="ambiguous_result"`
- empty query returns `result_kind="empty_result"`

- [ ] **Step 2: Implement service composition**

`SearchInspectService.inspect()` should:

1. Call `SearchService.search(q, limit=limit, scope=scope, window=window, now_ms=now_ms)`.
2. Classify resolver result.
3. For token result, call:
   - `TokenTargetSocialTimelineService.timeline(target_type=selected_target["target_type"], target_id=selected_target["target_id"], window=window, scope=scope, limit=200, now_ms=now_ms)`
   - `TokenTargetPostsService.target_posts(target_type=selected_target["target_type"], target_id=selected_target["target_id"], window=window, scope=scope, post_range="current_window", sort="recent", limit=200, now_ms=now_ms)`
   - `AssetFlowService.asset_flow(window=window, limit=96, scope=scope, now_ms=now_ms)`
4. Build `agent_brief` with `build_token_agent_brief`.
5. For topic/ambiguous result, build `agent_brief` with `build_topic_agent_brief` from Search V2 items.

- [ ] **Step 3: Wire API route**

Add:

```py
@router.get("/search/inspect")
async def search_inspect(
    request: Request,
    q: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "24h",
    scope: Annotated[str, Query()] = "all",
    limit: Annotated[int, Query()] = 200,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    with runtime.repositories() as repos:
        data = SearchInspectService(
            search_query=SearchEventsQuery(repos.conn),
            token_radar=repos.token_radar,
            targets=repos.token_targets,
        ).inspect(q, window=parsed_window, scope=parsed_scope, limit=_limit(limit, maximum=200), now_ms=_now_ms())
    return _json({"ok": True, "data": data})
```

- [ ] **Step 4: Add integration API assertion**

In `tests/integration/test_api_http.py`, add a request to `/api/search/inspect?q=$PEPE&window=24h&scope=all` and assert:

- HTTP 200
- `data.query.result_kind` is present
- `data.resolver.target_candidates` is a list
- `data.token_result.agent_brief.schema_version == "search_agent_brief_v1"` when a target resolves

- [ ] **Step 5: Run focused backend tests**

Run:

```bash
uv run pytest tests/unit/test_search_agent_brief.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py -q
```

Expected: focused tests pass.

## Task 5: Render The Search Intel Page

**Files:**

- Create: `web/src/api/useSearchInspectQuery.ts`
- Modify: `web/src/api/types.ts`
- Create: `web/src/components/SearchIntelPage.tsx`
- Create: `web/src/components/SearchAgentBrief.tsx`
- Create: `web/src/components/SearchTwitterResults.tsx`
- Create: `web/src/components/SearchTimelinePanel.tsx`
- Modify: `web/src/styles.css`
- Test: `web/src/components/__tests__/SearchAgentBrief.test.tsx`
- Test: `web/src/components/__tests__/SearchIntelPage.routing.test.tsx`

- [ ] **Step 1: Add API hook**

```ts
export function useSearchInspectQuery({
  q,
  window,
  scope,
}: {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
}) {
  return useQuery({
    queryKey: ["search-inspect", q, window, scope],
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(q.trim()),
  });
}
```

- [ ] **Step 2: Render agent brief tests**

Test must assert visible section labels:

- `项目总结`
- `传播`
- `多头观点`
- `空头观点`
- at least one evidence id, such as `ev_482`

- [ ] **Step 3: Build token result layout**

Use the prototype as the reference, but keep component boundaries:

- `SearchIntelPage` owns route/query state and loading/error.
- `SearchTimelinePanel` owns hourly buckets and anchor overlay.
- `SearchAgentBrief` owns project/propagation/bull-bear.
- `SearchTwitterResults` owns the 24h evidence table.

- [ ] **Step 4: Build topic result layout**

Topic result must show:

- 24h mention count
- top authors
- topic clusters derived from keyword matches and target mentions if present
- 24h Twitter rows
- `SearchAgentBrief` with topic-style project summary replaced by topic summary

- [ ] **Step 5: Build ambiguous result layout**

Ambiguous result must show:

- candidate comparison
- why no auto-selection happened
- raw topic evidence table
- call-to-action buttons to open a candidate token result URL

- [ ] **Step 6: Run frontend tests and typecheck**

Run:

```bash
cd web && npm run test -- SearchIntelPage SearchAgentBrief searchRouteState
cd web && npm run typecheck
```

Expected: tests and typecheck pass.

## Task 6: Search Focus Layout

**Files:**

- Modify: `web/src/components/CockpitLayout.tsx`
- Modify: `web/src/styles.css`
- Test: `web/src/components/__tests__/SearchIntelPage.routing.test.tsx`

- [ ] **Step 1: Add layout state**

In `CockpitLayout`, compute:

```ts
const isSearch = location.pathname.startsWith("/search");
```

Apply:

```tsx
className={`cockpit-grid mobile-task-${mobileTask} ${isSignalLab ? "signal-lab-mode" : ""} ${isSearch ? "search-focus-mode" : ""}`}
```

- [ ] **Step 2: Hide side rail and detail panel in CSS**

```css
.cockpit-grid.search-focus-mode {
  grid-template-columns: minmax(0, 1fr);
}

.cockpit-grid.search-focus-mode > .desktop-side-rail,
.cockpit-grid.search-focus-mode > .detail-task-panel,
.cockpit-grid.search-focus-mode > .responsive-control-panel {
  display: none;
}

.cockpit-grid.search-focus-mode > .center-column {
  border-right: 0;
}
```

- [ ] **Step 3: Assert no side rail content on search route**

In route test, render `/search?q=$RKC` and assert `screen.queryByText("views")` is not present while `Search Intel` is present.

## Task 7: Docs, Contract, Verification

**Files:**

- Modify: `docs/CONTRACTS.md`
- Optionally modify: `docs/FRONTEND.md`
- Create after implementation: `docs/superpowers/plans/active/2026-05-12-search-intel-page-verification-cn.md`

- [ ] **Step 1: Update contracts**

Document:

- `/api/search/inspect`
- `search_agent_brief_v1`
- `result_kind`
- anchor-only market overlay boundary

- [ ] **Step 2: Run generated contract check**

Run:

```bash
make regen-contract
make contract-check
```

Expected: generated OpenAPI and frontend API types match the new endpoint.

- [ ] **Step 3: Run full completion gate**

Run:

```bash
make check-all
```

Expected: exit 0. If not, record exact failure in verification instead of claiming done.

- [ ] **Step 4: Manual UI verification**

Run dev server:

```bash
cd web && npm run dev
```

Open:

- `http://127.0.0.1:5173/search?q=$RKC&window=24h&scope=all`
- `http://127.0.0.1:5173/search?q=挖矿&window=24h&scope=all`

Record screenshots or notes proving:

- no left `views` rail
- no right detail drawer / select-token panel
- token result renders 24h Twitter rows
- topic result renders 24h Twitter rows
- agent brief shows 项目总结, 传播, 多头观点, 空头观点
- market chart labels anchor overlay and does not fake K-line

## PR Breakdown

1. **PR 1 — search route shell:** route state, `/search` route, focus layout, global search navigation. Mergeable with stub page and tests.
2. **PR 2 — search inspect backend:** 24h-scoped search, deterministic agent brief, `/api/search/inspect`, backend tests.
3. **PR 3 — frontend result page:** API hook, token/topic/ambiguous renderers, agent brief, Twitter table, frontend tests.
4. **PR 4 — docs and verification:** contracts, generated OpenAPI/types, `make check-all`, manual UI verification artefact.

## Rollback

- Route shell rollback: remove `/search` route and restore old `submitEvidenceSearch` branch; no data migration involved.
- Backend rollback: remove `/api/search/inspect`; existing `/api/search`, `/api/target-social-timeline`, and `/api/target-posts` remain untouched except optional window parameter. If window parameter causes issues, default it to `None` and preserve old behavior.
- Frontend rollback: remove `SearchIntelPage` route and CSS `search-focus-mode`.
- Docs rollback: revert contract additions and regenerate OpenAPI.

## Acceptance Criteria

- Submitting the global search box navigates to `/search?q=<query>&window=<window>&scope=<scope>`; it does not open the old query drawer.
- `/search` has no left `views` rail and no right select-token/detail drawer.
- Token query renders resolver, 24h metrics, timeline, 24h Twitter rows, market/fundamental facts, and agent brief.
- Keyword query renders 24h topic evidence and agent brief.
- Ambiguous query renders candidates and evidence without silently choosing one target.
- Agent brief has project summary, propagation, bull thesis, bear thesis, triggers, invalidations, and visible evidence ids.
- Price overlay is labelled `anchor_line` until real OHLC exists.
- `make check-all` passes before shipping.

## AI Extension Boundary

Do not block first release on LLM output. The deterministic `search_agent_brief_v1` is the production fallback and should be good enough to ship. A later PR can add an optional OpenAI Agents SDK summarizer that consumes the same evidence payload and returns the same schema, but the UI and API must behave identically when the LLM is disabled or times out.
