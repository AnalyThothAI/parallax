# News Router Detail Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 News 从“列表 + 右侧 selected inspector”硬切为“`/news` 扫描列表 + `/news/items/:newsItemId` 可分享 evidence page”，删除旧路由、旧 inspector、旧兼容 UI。

**Architecture:** `/news` 只负责过滤、排序、分页、进入详情；不保留 selected row state，也不在列表页渲染 trade read。`/news/items/:newsItemId` 是唯一 item 对象页，直接消费 `/api/news/items/{news_item_id}` 的 provider signal、token impacts、token identity、fact/brief 状态和数据缺口；前端不从 headline/summary 推导交易结论。硬切要求删除 `/news/:newsItemId` 兼容路由、`NewsInspector`、未使用的 news view-model helper、相关 CSS 和测试期望。

**Tech Stack:** React Router data routes, React Query, TypeScript, feature-owned CSS under `web/src/features/news`, Vitest/React Testing Library, Playwright golden paths.

---

### Task 1: Hard Cut News Item Route

**Files:**
- Modify: `web/src/routes/router.tsx`
- Modify: `web/src/shared/routing/paths.ts`
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`

- [ ] **Step 1: Write failing route/path expectations**

Update the component test that clicks a news row so it expects the new object path:

```ts
expect(screen.getByTestId("location")).toHaveTextContent("/news/items/news-1");
```

Update the mobile cold-load case for the news detail route:

```ts
{
  label: "News detail",
  path: "/news/items/news-row-1",
}
```

- [ ] **Step 2: Run tests to verify current route shape fails**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx
```

Expected: the row-open test fails because `newsItemPath()` still returns `/news/news-1`.

- [ ] **Step 3: Replace route objects without compatibility route**

In `web/src/routes/router.tsx`, replace the old item route:

```tsx
{
  path: "news",
  lazy: () => import("./news.route"),
},
{
  path: "news/items/:newsItemId",
  lazy: () => import("./news.route"),
},
```

Delete the old block:

```tsx
{
  path: "news/:newsItemId",
  lazy: () => import("./news.route"),
},
```

Do not add a redirect from `/news/:newsItemId`.

- [ ] **Step 4: Update shared path builder**

In `web/src/shared/routing/paths.ts`, change `newsItemPath` to:

```ts
export function newsItemPath(newsItemId: string): string {
  return `/news/items/${encodeURIComponent(newsItemId)}`;
}
```

- [ ] **Step 5: Verify route tests pass**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx
```

Expected: PASS for the updated row-open expectation and detail fetch tests.

- [ ] **Step 6: Commit route hard cut**

```bash
git add web/src/routes/router.tsx web/src/shared/routing/paths.ts web/tests/component/features/news/NewsPage.test.tsx web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts
git commit -m "feat(news): hard cut item detail route"
```

### Task 2: Remove List-Page Selected Inspector

**Files:**
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/ui/NewsTape.tsx`
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/features/news/ui/newsTape.css`
- Delete: `web/src/features/news/ui/NewsInspector.tsx`
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`
- Modify: `web/tests/component/features/news/NewsTape.test.tsx`

- [ ] **Step 1: Write failing assertions for list-only News page**

In `NewsPage.test.tsx`, rename the first test to:

```ts
it("renders a provider-signal tape without an inline inspector", async () => {
```

Keep the existing row assertions, then replace the old inspector expectation with:

```ts
expect(screen.queryByLabelText("news inspector")).not.toBeInTheDocument();
expect(screen.queryByText("Provider signal")).not.toBeInTheDocument();
```

- [ ] **Step 2: Run tests to verify the inline inspector is still present**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx
```

Expected: FAIL because `NewsInspector` still renders.

- [ ] **Step 3: Remove selected row state from `NewsPage.tsx`**

Delete these imports:

```ts
import { useEffect, useMemo, useState } from "react";
import { NewsInspector } from "./ui/NewsInspector";
```

Replace them with:

```ts
import { useState } from "react";
```

Remove `selectedNewsItemId`, `selectedItem`, and the `useEffect` block that auto-selects the first row.

Replace the current `news-compact-layout` render block with:

```tsx
<NewsTape rows={rows} onOpen={(newsId) => navigate(newsItemPath(newsId))} />
```

- [ ] **Step 4: Simplify `NewsTape` props and behavior**

In `NewsTape.tsx`, change props to:

```ts
type NewsTapeProps = {
  rows: NewsRow[];
  onOpen: (newsItemId: string) => void;
};
```

Change the component signature to:

```tsx
export function NewsTape({ rows, onOpen }: NewsTapeProps) {
```

Remove `selectedId`, `onSelect`, and `selected` handling. Change the main row button click to open the shareable detail route:

```tsx
<button
  aria-label={`Open news item ${row.headline}`}
  className="news-tape-row-main"
  type="button"
  onClick={() => onOpen(row.news_item_id)}
>
```

Keep the explicit icon button only if tests prove it adds keyboard clarity. If kept, both buttons must route to the same `newsItemPath`.

- [ ] **Step 5: Delete inspector file and CSS selectors**

Delete:

```bash
rm web/src/features/news/ui/NewsInspector.tsx
```

In `web/src/features/news/news.css`, remove `.news-compact-layout` and its media query block.

In `web/src/features/news/ui/newsTape.css`, remove all selectors containing:

```css
.news-tape-inspector
.news-tape-provider-fields
.news-tape-token-impact
.news-tape-inspector-actions
.news-tape-row.is-selected
```

Keep only tape-row, signal, token-strip, and open-button styles.

- [ ] **Step 6: Verify no inspector references remain**

Run:

```bash
rg -n "NewsInspector|news-tape-inspector|news-compact-layout|is-selected" web/src/features/news web/tests/component/features/news
```

Expected: no output.

- [ ] **Step 7: Run component tests**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/component/features/news/NewsTape.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit inspector removal**

```bash
git add web/src/features/news/NewsPage.tsx web/src/features/news/ui/NewsTape.tsx web/src/features/news/news.css web/src/features/news/ui/newsTape.css web/tests/component/features/news/NewsPage.test.tsx web/tests/component/features/news/NewsTape.test.tsx
git rm web/src/features/news/ui/NewsInspector.tsx
git commit -m "refactor(news): remove inline inspector"
```

### Task 3: Reframe Detail Page As Evidence Page

**Files:**
- Modify: `web/src/features/news/NewsPage.tsx`
- Create: `web/src/features/news/ui/NewsItemEvidencePage.tsx`
- Create: `web/src/features/news/ui/NewsItemEvidencePage.css`
- Modify: `web/src/features/news/NewsDetail.css`
- Delete: `web/src/features/news/newsViewModel.ts`
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`

- [ ] **Step 1: Write detail-page assertions around source-backed data**

In the provider detail test, assert evidence-page labels and data gaps:

```ts
expect(await screen.findByText("Evidence page")).toBeInTheDocument();
expect(screen.getByText("Provider aiRating")).toBeInTheDocument();
expect(screen.getByText("Token impacts")).toBeInTheDocument();
expect(screen.getByText("Execution gaps")).toBeInTheDocument();
expect(screen.getByText("Price reaction")).toBeInTheDocument();
expect(screen.getByText("Liquidity / OI")).toBeInTheDocument();
expect(screen.getByText("Agent thesis")).toBeInTheDocument();
expect(screen.queryByText("Agent memo")).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the detail test to verify current copy fails**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx -t "OpenNews provider"
```

Expected: FAIL because the current page still says `Provider signal` and does not render explicit execution gaps.

- [ ] **Step 3: Extract evidence component**

Create `web/src/features/news/ui/NewsItemEvidencePage.tsx` with this public component shape:

```tsx
import { formatRelativeTime } from "@lib/format";
import type { NewsFactLane, NewsItemDetail, NewsTokenLane } from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import { ExternalLink } from "lucide-react";

import {
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenMarketLabel,
} from "../model/newsSignalViewModel";
import "./NewsItemEvidencePage.css";

export function NewsItemEvidencePage({ item }: { item: NewsItemDetail }) {
  const tokens = newsDisplayTokenLanes(item);
  const facts = item.fact_lanes ?? [];
  return (
    <article className="news-evidence-page">
      <header className={`news-evidence-hero ${newsSignalTone(item.signal)}`}>
        <div className="news-row-kicker">
          <span>Evidence page</span>
          <span>{item.signal.method || item.signal.source}</span>
          <span className={newsSignalTone(item.signal)}>{newsSignalLabel(item.signal)}</span>
          <span>{newsSignalScoreLabel(item.signal)}</span>
        </div>
        <h2>{item.headline}</h2>
        <p>{item.summary || item.signal.summary_en || "No source summary available."}</p>
        {item.canonical_url ? (
          <a className="news-outline-link" href={item.canonical_url} rel="noreferrer" target="_blank">
            <ExternalLink aria-hidden />
            Original
          </a>
        ) : null}
      </header>
      <section className="news-evidence-strip" aria-label="provider signal context">
        <EvidenceMetric label="Direction" value={newsSignalLabel(item.signal)} hint={item.signal.direction} />
        <EvidenceMetric label="Score" value={newsSignalScoreLabel(item.signal)} hint={item.signal.status} />
        <EvidenceMetric label="Tokens" value={String(tokens.length)} hint={newsLifecycleLabel(item.lifecycle_status)} />
      </section>
      <section className="news-evidence-grid">
        <ProviderSignalEvidence item={item} tokens={tokens} />
        <ExecutionGapPanel briefStatus={item.agent_brief?.status ?? "pending"} />
        <FactEvidence facts={facts} />
        <MetadataEvidence item={item} />
      </section>
    </article>
  );
}
```

Define the helper components in the same file for this hard cut: `EvidenceMetric`, `ProviderSignalEvidence`, `ExecutionGapPanel`, `FactEvidence`, and `MetadataEvidence`. They must only render fields already present on `NewsItemDetail`; they must not infer trade action, invalidation, price reaction, or market read.

- [ ] **Step 4: Wire `NewsPage.tsx` to the evidence component**

Import the new component:

```ts
import { NewsItemEvidencePage } from "./ui/NewsItemEvidencePage";
```

Replace the old detail render:

```tsx
<NewsItemDetailView item={item} />
```

with:

```tsx
<NewsItemEvidencePage item={item} />
```

Delete the old inline component block from `NewsItemDetailView` through `trimContent`.

- [ ] **Step 5: Delete dead heuristic helper**

Confirm no imports remain:

```bash
rg -n "newsViewModel|inferNewsInstruments|agentBriefMissingText" web/src web/tests
```

Then delete:

```bash
rm web/src/features/news/newsViewModel.ts
```

- [ ] **Step 6: Style detail as an evidence object page**

Create `web/src/features/news/ui/NewsItemEvidencePage.css` under `@layer app.features`. Use owner-prefixed selectors only:

```css
@layer app.features {
  .news-evidence-page {
    display: grid;
    gap: 12px;
    padding: 10px;
  }

  .news-evidence-hero,
  .news-evidence-section,
  .news-evidence-metric {
    border: 1px solid var(--line);
    border-radius: 7px;
    background: rgba(10, 13, 13, 0.76);
  }

  .news-evidence-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }

  .news-evidence-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 0.34fr);
    gap: 12px;
    align-items: start;
  }
}
```

Move any still-needed selectors out of `NewsDetail.css` or delete `NewsDetail.css` if all detail styling moves to the new owner CSS. Do not leave duplicate `.news-detail-*` styles unused.

- [ ] **Step 7: Verify detail tests pass**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit evidence page refactor**

```bash
git add web/src/features/news/NewsPage.tsx web/src/features/news/ui/NewsItemEvidencePage.tsx web/src/features/news/ui/NewsItemEvidencePage.css web/src/features/news/NewsDetail.css web/tests/component/features/news/NewsPage.test.tsx
git rm web/src/features/news/newsViewModel.ts
git commit -m "refactor(news): make item detail an evidence page"
```

### Task 4: Tighten Tests And Architecture Gates

**Files:**
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`
- Modify: `web/tests/component/features/news/NewsTape.test.tsx`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`
- Modify: `web/tests/e2e/support/mockApi.ts`
- Modify: `web/tests/architecture/dataRouterArchitecture.test.ts` only if it contains route snapshots that mention `/news/:newsItemId`

- [ ] **Step 1: Add hard-cut grep assertions where appropriate**

If no architecture test already guards route shape, add a test in `web/tests/architecture/dataRouterArchitecture.test.ts`:

```ts
it("does not keep the retired news item route", () => {
  const routerSource = readFileSync("src/routes/router.tsx", "utf8");
  expect(routerSource).toContain('path: "news/items/:newsItemId"');
  expect(routerSource).not.toContain('path: "news/:newsItemId"');
});
```

- [ ] **Step 2: Update mock API detail path if needed**

`web/tests/e2e/support/mockApi.ts` already matches `/api/news/items/`. Keep that API path unchanged. Only update browser-route fixtures from `/news/news-row-1` to `/news/items/news-row-1`.

- [ ] **Step 3: Run focused frontend gates**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/component/features/news/NewsTape.test.tsx tests/architecture/dataRouterArchitecture.test.ts
```

Expected: PASS.

- [ ] **Step 4: Run architecture harnesses**

Run:

```bash
cd web && npm run test:architecture
```

Expected: PASS with no CSS ownership, retired route, or deleted-file import failures.

- [ ] **Step 5: Commit test hardening**

```bash
git add web/tests/component/features/news/NewsPage.test.tsx web/tests/component/features/news/NewsTape.test.tsx web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts web/tests/e2e/support/mockApi.ts web/tests/architecture/dataRouterArchitecture.test.ts
git commit -m "test(news): lock shareable item route"
```

### Task 5: Document Product Contract And Prototype

**Files:**
- Modify: `docs/FRONTEND.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/prototypes/news-trading-desk-static.html`
- Create/Update: `docs/generated/frontend-verification/news-router-list-static-desktop.png`
- Create/Update: `docs/generated/frontend-verification/news-router-detail-static-desktop.png`

- [ ] **Step 1: Update frontend route contract**

In `docs/FRONTEND.md`, replace the News route paragraph with:

```md
- **News route.** `/news` is the provider-signal tape and renders only shareable filters, pagination, source-backed signal fields, and links into `/news/items/:newsItemId`. `/news/items/:newsItemId` is the item evidence page and renders provider aiRating, token impacts, token identity, fact candidates, source metadata, and persisted agent brief state directly from `/api/news/items/{news_item_id}`. The list route must not keep an inline selected inspector or recreate trading narrative from headline, summary, or keyword rules. The detail route must show explicit gaps for price reaction, liquidity/OI, and agent thesis when those fields are not present.
```

- [ ] **Step 2: Update public contract docs**

In `docs/CONTRACTS.md`, add this sentence to the News Intel contract:

```md
The frontend item URL is `/news/items/:newsItemId`; `/news/:newsItemId` is not a compatibility route.
```

- [ ] **Step 3: Keep prototype aligned**

The static prototype should keep these shareable prototype routes:

```text
file:///.../docs/prototypes/news-trading-desk-static.html#/news
file:///.../docs/prototypes/news-trading-desk-static.html#/news/items/htx-sanctions
```

Regenerate screenshots:

```bash
npx playwright screenshot --viewport-size=1440,1000 'file:///Users/qinghuan/Documents/code/parallax/docs/prototypes/news-trading-desk-static.html#/news' docs/generated/frontend-verification/news-router-list-static-desktop.png
npx playwright screenshot --viewport-size=1440,1000 'file:///Users/qinghuan/Documents/code/parallax/docs/prototypes/news-trading-desk-static.html#/news/items/htx-sanctions' docs/generated/frontend-verification/news-router-detail-static-desktop.png
```

- [ ] **Step 4: Commit docs and prototype**

```bash
git add docs/FRONTEND.md docs/CONTRACTS.md docs/prototypes/news-trading-desk-static.html docs/generated/frontend-verification/news-router-list-static-desktop.png docs/generated/frontend-verification/news-router-detail-static-desktop.png
git commit -m "docs(news): document shareable evidence page"
```

### Task 6: Final Verification

**Files:**
- No source edits.

- [ ] **Step 1: Run focused unit/component tests**

Run:

```bash
cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/component/features/news/NewsTape.test.tsx tests/unit/features/news/newsSignalViewModel.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run frontend architecture and type gates**

Run:

```bash
cd web && npm run test:architecture
cd web && npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
cd web && npm run lint
```

Expected: PASS.

- [ ] **Step 4: Run a production build**

Run:

```bash
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 5: Browser verification**

Start the app if needed, then verify:

```text
/news
/news/items/news-row-1
```

Expected:
- `/news` shows filters, pagination, and the news tape only.
- Clicking any tape row changes the URL to `/news/items/<id>`.
- `/news/items/<id>` hard reloads and fetches `/api/news/items/<id>`.
- There is no inline selected inspector on `/news`.
- There is no redirect or supported compatibility path for `/news/<id>`.

- [ ] **Step 6: Final hard-cut grep**

Run:

```bash
rg -n "news/:newsItemId|NewsInspector|news-tape-inspector|news-compact-layout|inferNewsInstruments|agentBriefMissingText" web/src web/tests docs
```

Expected: no output, except this plan file if it has not been archived yet.

---

## Self-Review

- Spec coverage: This plan covers router hard cut, list-only `/news`, shareable `/news/items/:newsItemId`, evidence-page rendering, CSS cleanup, tests, docs, and prototype screenshots.
- Placeholder scan: No unresolved placeholder markers or open-ended “handle later” steps remain.
- Type consistency: Route param remains `newsItemId`; API path remains `/api/news/items/{news_item_id}`; frontend browser path changes to `/news/items/:newsItemId`.
