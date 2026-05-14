# Token Intel Product Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Radar 和 Search Intel 改成交易员可用的确定 token 情报工作流，删除候选/旧排序/debug 语言。

**Architecture:** Radar 和 Search 分两条独立实现线。Radar 负责 compact scan row/header；Search 负责 token_result 情报页与 ambiguous/topic 分流。两者共享 `tokenCase` 或轻量 token identity/profile primitives，但不互相跨 feature 深引用。

**Tech Stack:** React 19, TypeScript strict, CSS Modules with global selectors, TanStack Query, Vitest, Testing Library, Playwright/browser QA.

---

## File Structure

- `docs/superpowers/specs/active/2026-05-14-token-intel-product-cleanup-cn.md`: product spec and acceptance criteria.
- `web/src/features/live/ui/TokenRadarTable.tsx`: Radar scan bar/list shell.
- `web/src/features/live/ui/TokenRadarRow.tsx`: compact token case row.
- `web/src/features/live/ui/LiveRadar.tsx`: passes window/scope controls into Radar scan bar.
- `web/src/features/live/ui/live.module.css`: Radar compact layout.
- `web/src/features/search/ui/SearchIntelPage.tsx`: route/query/result-kind dispatcher only.
- `web/src/features/search/ui/SearchTokenIntelPage.tsx`: token_result intelligence page.
- `web/src/features/search/ui/SearchAmbiguousCase.tsx`: ambiguous_result candidate compare.
- `web/src/features/search/ui/SearchTopicCase.tsx`: topic_result evidence page.
- `web/src/features/search/ui/SearchIntelControls.tsx`: window/scope controls.
- `web/src/features/search/ui/search.module.css`: Search token intelligence layout.
- `web/src/test/obsidianArchitectureCleanout.test.ts`: guard old product language.

## Task 1: Radar Compact Case Row

**Files:**
- Modify: `web/src/features/live/ui/TokenRadarRow.tsx`
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Modify: `web/src/features/live/ui/LiveRadar.tsx`
- Modify: `web/src/features/live/ui/live.module.css`
- Modify: `web/src/features/live/ui/TokenRadarRow.test.tsx`
- Modify: `web/src/test/obsidianArchitectureCleanout.test.ts`

- [ ] **Step 1: Write/adjust tests**

Expected assertions:

```ts
expect(screen.queryByRole("button", { name: "Attention" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Proof" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Reach" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Entry" })).not.toBeInTheDocument();
expect(screen.getByText("$SLOP")).toBeInTheDocument();
expect(screen.getByText(/posts/i)).toBeInTheDocument();
expect(screen.getByText(/authors/i)).toBeInTheDocument();
expect(screen.getByRole("button", { name: /open token item/i })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /open search intel/i })).toBeInTheDocument();
```

- [ ] **Step 2: Implement scan bar**

Move window/scope controls into `TokenRadarTable` props:

```ts
type TokenRadarTableProps = {
  windowKey: WindowKey;
  scope: ScopeKey;
  onWindowChange: (window: WindowKey) => void;
  onScopeChange: (scope: ScopeKey) => void;
};
```

Render only title/count plus controls. Do not render sort tabs.

- [ ] **Step 3: Implement compact row**

Keep one main row button and separate actions:

```tsx
<article className="radar-row compact">
  <button className="radar-row-select" onClick={() => onSelect(item)}>...</button>
  <div className="case-row-actions">...</div>
</article>
```

Do not place `<a>` inside the row button.

- [ ] **Step 4: Verify**

Run:

```bash
npm --prefix web run test -- src/features/live/ui/TokenRadarRow.test.tsx src/test/obsidianArchitectureCleanout.test.ts
npm --prefix web run typecheck
npm --prefix web run lint
```

## Task 2: Search Token Intel Page

**Files:**
- Modify: `web/src/features/search/ui/SearchIntelPage.tsx`
- Create: `web/src/features/search/ui/SearchTokenIntelPage.tsx`
- Create: `web/src/features/search/ui/SearchAmbiguousCase.tsx`
- Create: `web/src/features/search/ui/SearchTopicCase.tsx`
- Create: `web/src/features/search/ui/SearchIntelControls.tsx`
- Modify: `web/src/features/search/ui/search.module.css`
- Modify: `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`
- Modify: `web/src/test/obsidianArchitectureCleanout.test.ts`

- [ ] **Step 1: Write/adjust tests**

Token result must not show candidates:

```ts
expect(screen.queryByText("candidates")).not.toBeInTheDocument();
expect(screen.queryByText("CANONICAL_SYMBOL_MATCH")).not.toBeInTheDocument();
expect(screen.queryByText("one_resolved_target")).not.toBeInTheDocument();
```

Token result must show token intelligence:

```ts
expect(screen.getByRole("region", { name: /Token intelligence/i })).toBeInTheDocument();
expect(screen.getByText("market cap")).toBeInTheDocument();
expect(screen.getByText("24h Evidence Stream")).toBeInTheDocument();
expect(screen.getByText(/Runtime narrative/)).toBeInTheDocument();
```

Ambiguous result must still show candidate compare.

- [ ] **Step 2: Split result components**

`SearchIntelPage.tsx` keeps query and dispatch:

```tsx
if (data.query.result_kind === "token_result" && data.token_result) {
  return <SearchTokenIntelPage data={data} result={data.token_result} routeState={routeState} onRouteChange={updateRoute} />;
}
```

- [ ] **Step 3: Implement token intelligence layout**

`SearchTokenIntelPage` renders:

1. header with profile/link/action controls
2. decision/snapshot strip
3. primary timeline/evidence column
4. side thesis/score column

Do not render resolver candidate list in token_result.

- [ ] **Step 4: Verify**

Run:

```bash
npm --prefix web run test -- src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx src/test/obsidianArchitectureCleanout.test.ts
npm --prefix web run typecheck
npm --prefix web run lint
```

## Task 3: Integration And QA

**Files:**
- Modify as needed after merging Task 1 and Task 2.

- [ ] **Step 1: Run full frontend checks**

```bash
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
```

- [ ] **Step 2: Rebuild Docker**

```bash
make docker-up
docker compose ps
```

Expected: app container healthy on `0.0.0.0:8765->8765`.

- [ ] **Step 3: Browser QA**

Open `http://localhost:8765/` and verify:

- Radar has no `Attention / Proof / Reach / Entry` buttons.
- Radar rows are compact and action-oriented.
- Search Intel token_result does not show resolver candidates.
- Browser console has no errors or warnings.

