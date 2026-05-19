# News Intel Table Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current News card/tape page with a Token Radar-style dense table, server cursor pagination, and a minimal item detail route.

**Architecture:** News remains inside the existing Cockpit shell and keeps the existing left rail unchanged. `/news` becomes a scan surface using `@tanstack/react-table` and `/api/news?limit=25&cursor=...`; `/news/:newsItemId` renders one item using `/api/news/items/:news_item_id`. Story and identity are not separate visible navigation concepts; they appear only as row/detail metadata.

**Tech Stack:** React 19, React Router, TanStack Query, TanStack Table, existing `RemoteState`, existing `fetchNewsRows` HTTP client.

---

### Task 1: Client Contract And Hooks

**Files:**
- Modify: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/shared/query/queryKeys.ts`
- Modify: `web/src/features/news/useNewsPage.ts`

- [x] Add `claim`, `realis`, and `affected_targets` to `NewsFactLane`.
- [x] Add `NewsItemDetail` for item payloads returned by `/api/news/items/:id`.
- [x] Extend `fetchNewsRows` params to include `limit`, `cursor`, `status`, `lane`, `source`, `target`, and `q`; keep lane normalization for `token_lanes_json` / `fact_lanes_json`.
- [x] Add `fetchNewsItem({ newsItemId, token })`.
- [x] Change `useNewsPageWithToken(token, { limit, cursor })` to fetch one page with `limit=25`.
- [x] Add `useNewsItemWithToken(token, newsItemId)`.

### Task 2: Hard Cut News Table

**Files:**
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/news.css`

- [x] Remove the old `news-tape`, card rows, footer chips, and lifecycle-centric visual hierarchy.
- [x] Use `useReactTable` with columns: `Time / Source`, `Event / Question`, `Instrument / Price`, `Route`, `Next`.
- [x] Maintain a cursor stack in `NewsPage` so `Next` pushes `next_cursor` and `Prev` pops to the previous cursor.
- [x] Use `limit=25`; never request or render all news rows.
- [x] Row click routes to `/news/:newsItemId`.
- [x] Render loading, error, empty, and refreshing states with `RemoteState`.

### Task 3: Item Detail Route

**Files:**
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/routes/news.route.tsx`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/news.css`

- [x] Change router from `path="news"` to support `path="news"` and `path="news/:newsItemId"`.
- [x] The item page renders headline, source, route state, market read, next action, market map, extracted facts, token identity, story continuity, and production metadata.
- [x] Keep story and identity as detail blocks only; no visible Story/Identity navigation tabs.

### Task 4: Tests

**Files:**
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`
- Modify: `web/tests/unit/features/news/useNewsPage.test.ts`

- [x] Update component test to assert table headers, 25-row pagination behavior, and row link to `/news/news-1`.
- [x] Update hook/model tests to assert cursor query params and item detail query.
- [x] Run: `cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/unit/features/news/useNewsPage.test.ts`

### Task 5: Verification

**Files:**
- Verify: `web/src/features/news/NewsPage.tsx`
- Verify: `web/src/features/news/news.css`

- [x] Run targeted Vitest.
- [x] Run `cd web && npm run typecheck`.
- [x] Start the web app if needed and inspect `/news` and `/news/<sample-id>` in browser.
