# Spec — 前端响应式与 CSS 架构 hard cut

**Status**: Draft  
**Date**: 2026-05-21  
**Owner**: Codex  
**Related**: `docs/FRONTEND.md` · `docs/superpowers/specs/active/2026-05-13-frontend-architecture-audit-and-target-cn.md` · `docs/superpowers/plans/active/2026-05-14-obsidian-desk-ui-cleanup-decoupling-cn.md`

## 1. 一句话定性

当前移动端不可用不是因为没有引入成熟 UI 框架，而是因为 `web/` 的响应式规则没有成为架构契约：CSS 以多个大型 side-effect 文件累积，桌面 cockpit 规则在文件后半段覆盖了早先移动端规则，路由级页面各自用固定宽表格和局部断点自救，缺少移动端验收门禁。

这次 hard cut 的目标是把前端从“桌面优先 + CSS 补丁堆叠”切到“shell 响应式契约 + 分层 cascade + feature 自治样式 + 多 viewport 测试闸门”。审查后的结论是：仅修 `cockpit.css` 不够，必须同时覆盖 `SearchShell`、移动端顶级导航、详细路由、E2E mock 数据、嵌套滚动和全量 side-effect CSS layer 迁移，才算彻底。

## 2. 工业界实践基线

本项目是高密度交易/情报 cockpit，不适合用通用 UI kit 重塑产品形态。工业界对这类 React/Vite 工具型前端的可维护做法通常是：

1. **布局契约先于组件细节。** 先定义 app shell、顶部栏、导航、内容滚动区、任务面板在 desktop/tablet/mobile 的行为，再让页面组件填充区域。
2. **移动端基线，桌面逐步增强。** 手机端必须是可用的一等体验；桌面信息密度是增强层，而不是默认表格被手机横向挤压。
3. **CSS cascade 可预测。** 用明确的 import 顺序和 cascade layer 管理 token/base/primitives/shell/features/overrides，避免“后写的大文件意外赢”。
4. **全局 CSS 极少，组件样式就近。** 全局只放设计 token、reset/base、共享 primitive。页面样式归 feature，复杂组件优先 CSS Modules。
5. **容器优先，viewport 兜底。** 对可复用面板和卡片用 container query 或容器类契约；路由 shell 才使用 viewport breakpoint。
6. **表格必须有移动端替代表达。** 数据密集表在桌面可以保留 sticky header 和列排序；手机端应变成卡片/摘要列表/任务分页，而不是完整表格横向滚动。
7. **视觉回归和功能回归一起跑。** Playwright 覆盖 desktop/tablet/mobile 的关键路径；对 shell 和高风险页面做稳定 mock 数据下的截图或几何断言。

## 3. 当前审计事实

### 3.1 CSS 规模与 ownership

`web/src` 当前有 **13,200 行 CSS**。最大文件：

| 文件 | 行数 | 类型 |
|---|---:|---|
| `web/src/features/live/ui/live.css` | 1,617 | feature global side-effect |
| `web/src/shared/ui/shared.css` | 1,375 | shared global side-effect |
| `web/src/features/signal-lab/ui/signalLab.css` | 1,324 | feature global side-effect |
| `web/src/features/cockpit/ui/cockpit.css` | 1,283 | shell global side-effect |
| `web/src/features/news/news.css` | 970 | feature global side-effect |
| `web/src/features/macro/macro.css` | 818 | feature global side-effect |
| `web/src/features/search/ui/search.css` | 747 | feature global side-effect |
| `web/src/features/ops/ui/ops.css` | 666 | feature global side-effect |

`main.tsx` 只导入了 `tailwind.css`、`tokens.css`、`base.css`，符合 `docs/FRONTEND.md` 的基础要求；但大量 feature 和 shared 组件继续通过 side-effect `.css` 产生全局 selector。CSS Modules 已经存在，但只覆盖一部分 Token Case / Pulse Detail 组件，整体处于混合中间态。

### 3.2 移动端根因

`web/src/features/cockpit/ui/cockpit.css` 前半段已经写了移动端规则：

- `@media (max-width: 1279px)` 隐藏 `.desktop-side-rail`，同时尝试显示一个 Shell 级业务筛选面板。
- `@media (max-width: 767px)` 尝试在 Shell 中显示 Live 任务切换，并用 `data-mobile-task-panel` 切换 Radar / Tape / Lab。

但同一文件从 “Obsidian Desk shell language ownership” 段落开始重新定义了一套 shell：

- `.cockpit-shell` 固定为 `width: 100vw; height: 100dvh; overflow: hidden;`
- `.topbar`、`.cockpit-grid`、`.side-rail`、Shell 级业务筛选面板、Live 任务切换被重新声明。
- 后半段把 Shell 级业务筛选面板和 Live 任务切换隐藏逻辑放在基础层，且后续 mobile media query 没有恢复任务切换。

结果是源顺序打穿了早先移动端规则：手机端仍显示桌面侧栏，底部任务导航不显示，截图里的 UI 基本只剩 side rail。

后续复查确认更深一层根因：Shell 级业务筛选面板本身就是错误边界。Token Radar、Stocks 等 feature 页面已经拥有自己的 window/scope/venue 控件，Shell 再渲染一套会在手机端形成重复控制面板，挤压内容区，并让 CSS 修复看起来像补丁。目标架构应彻底删除该 Shell 路径，而不是继续兼容。

再次复查确认第二个边界错误：Radar/Tape/Lab 是 Live 页面内部任务，不是全局 Cockpit Shell 导航。它应由 `features/live` 拥有，并且只在 `/` Live 页面出现；Stocks、News、Macro、Watchlist、Ops、Search、Token Case 等非 Live 路由不得渲染该底栏。

### 3.3 布局和滚动风险

- `web/src/styles/base.css` 对 `body` 设置 `overflow: hidden`，应用依赖内部滚动区。这个模型可以用于 cockpit，但必须由 shell 统一定义；现在 feature 页面也各自设置 `overflow` 和固定高度，滚动责任分散。
- `CockpitShell` 的 `center-column` 是主滚动区，但页面内部还有 `token-radar-table`、`news-table-wrap`、`watchlist` 等二级滚动容器，手机端容易出现不可发现的嵌套滚动。
- 多处使用 `width: 100vw`，在桌面滚动条和移动浏览器动态 viewport 下容易制造横向溢出。

### 3.4 固定宽数据面

桌面数据密度合理，但手机契约不完整：

- Token Radar：`radar-data-table` `min-width: 1060px`，同时有移动端卡片化规则，但受 shell 覆盖影响不可达。
- News：控制栏和 desk 有 `min-width: 1060px`，后续在 `max-width: 780px` 做单列转换。
- Stocks：桌面 `min-width: 760px`，tablet 降到 `560px`，但没有真正的手机卡片契约。
- Signal Lab / Macro / Search / Watchlist 各自有断点，但 breakpoint、滚动和信息隐藏规则不共享。

### 3.5 测试缺口

Playwright 当前配置只跑 `Desktop Chrome`。现有 e2e 中只有 `1920x1080` 和 `1366x720` 的显式 viewport 检查，没有 `390x844`、`430x932` 或 tablet 项目。也没有断言：

- mobile 下 `.desktop-side-rail` 不可见。
- mobile 下 `/` 的 `.live-task-nav` 可见且可切换任务；非 Live 路由不渲染 `.live-task-nav`。
- 页面级 `document.documentElement.scrollWidth <= viewportWidth`。
- `/`、`/search`、`/signal-lab`、`/stocks`、`/news`、`/macro`、`/token/:targetType/:targetId` 手机冷加载可操作。
- E2E mock API 当前没有覆盖 `/api/macro`、`/api/ops/diagnostics`、`/api/ops/queues/:queueName`、`/api/watchlist/:handle`、`/api/news/items/:id`。如果不先补 fixture，新增移动端路由测试会测试到错误态而不是布局。
- `/search` 使用 `SearchShell`，不是 `CockpitShell`；它共享 `.cockpit-shell`、`.search-shell`、`.cockpit-grid`、`.center-column`。任何 shell CSS 拆分都必须把 `SearchShell` 纳入同一迁移。
- 移动端隐藏 desktop rail 后，Radar / Stocks / News / Macro / Watchlist / Ops 的顶级导航必须由 Shell-owned mobile route nav 提供；Live-only `LiveTaskNav` 只覆盖 Radar / Tape / Lab。

## 4. Goals

- **G1. 手机端恢复可用。** 390px 宽 viewport 下 `/` 不显示桌面 rail，显示底部任务 nav，Radar/Tape/Lab 均可切换，顶部搜索和通知可触达。
- **G2. CSS cascade 可解释。** 引入明确 CSS layer/import contract；同一文件不得先写 mobile 覆盖、后写基础桌面规则覆盖回来。
- **G3. 样式 ownership 可机械化。** 全局 CSS 只允许 tokens/base/primitives/shell；feature 样式归 feature；复杂组件改 CSS Modules；大型 side-effect CSS 按责任拆分。
- **G4. 路由响应式矩阵完整。** `/`、`/search`、`/signal-lab`、`/stocks`、`/news`、`/macro`、`/watchlist`、`/token/:targetType/:targetId` 都声明 desktop/tablet/mobile 的布局行为。
- **G5. 数据密集组件有手机表达。** 桌面表格保留；手机用卡片、摘要行或任务面板，除极小局部 chip rail 外不依赖整页横向滚动。
- **G6. 滚动责任唯一。** shell 管页面滚动；局部滚动必须显式命名、可见、测试覆盖。禁止 feature 随意设置 viewport 高度。
- **G7. 多 viewport 验收进 CI。** Playwright 增加 desktop/tablet/mobile 项目和几何断言；对 shell 和关键页面增加稳定截图或布局断言。
- **G8. 文档和审计闸门同步。** `docs/FRONTEND.md` 更新 CSS 架构、响应式矩阵、测试要求；architecture tests 阻止回归。
- **G9. 移动端顶级导航可达。** 手机隐藏 desktop rail 后，用户仍可从 UI 进入 Radar、Stocks、News、Macro、Watchlist、Ops 和 Search；不能只依赖直接 URL。
- **G10. E2E mock 覆盖测试矩阵。** 每条移动端 cold-load 路由必须有确定性 fixture，且测试失败时能区分 API mock 缺失和 UI 断裂。
- **G11. Shell 数据边界不倒退。** CSS/布局迁移不得把 feature API hooks、WebSocket subscription 或 route-state 写进 shell UI 组件；这些仍留在 routes/features 的控制层。

## 5. Non-goals

- 不改后端 API、WebSocket、评分、read model 或数据契约。
- 不迁移到 Next.js、SSR、React Server Components。
- 不引入 MUI、Ant Design、shadcn 或整套通用 UI kit。
- 不重做品牌视觉，不改 Obsidian Desk 的基本视觉语言。
- 不追求一次性把所有 CSS 变成 Tailwind utility；允许 CSS Modules + 少量 utility + token 变量混合，但 ownership 必须清楚。
- 不在本轮解决 bundle splitting、性能追踪、Sentry 等非响应式问题。

## 6. Target CSS Architecture

### 6.0 Route And Shell Ownership

当前组合链路必须保持清楚：

```text
AppRoot
  -> CockpitApp
    -> routes/AppRoutes              # owns route-level data composition and socket subscription wiring
      -> CockpitShell / SearchShell  # layout only, receives typed props, no feature fetching
        -> feature routes            # feature-owned UI and feature hooks
```

Rules:

- `CockpitShell` / `SearchShell` 只拥有 layout、hotkey binding、topbar/notification layer composition。
- `CockpitShell` / `SearchShell` 不渲染 route-specific filters；window/scope/venue/handle 控件由消费它们的 feature route 拥有。
- feature API hooks、React Query cache mutation、WebSocket market target subscription 不进入 shell UI 组件。
- `/search` 是 first-class shell variant，所有 shell CSS 拆分和 mobile tests 必须覆盖它。
- mobile top-level navigation is shell-owned navigation UI, not a side effect of desktop rail.

### 6.1 文件层

目标结构：

```text
web/src/styles/
  tailwind.css          # Tailwind import only
  tokens.css            # design tokens and Tailwind @theme declarations consumed by utilities
  base.css              # html/body/#root/reset/base elements
  primitives.css        # shared low-level UI primitives only
  layout.css            # shell-independent layout utilities once shared across two or more routes

web/src/features/cockpit/ui/
  CockpitShell.module.css
  CockpitTopbar.module.css
  CockpitSideRail.module.css
  cockpit.tokens.css    # shell-level CSS variables used across two or more cockpit shell modules

web/src/features/<feature>/ui/
  <RoutePage>.module.css
  <Component>.module.css
  <feature>.css         # allowed only for route-level page selectors during migration
```

### 6.2 Cascade layers

All non-module side-effect CSS must be layered:

```css
@layer app.base, app.primitives, app.shell, app.features, app.overrides;
```

Rules:

- `tokens.css` defines variables only.
- `base.css` owns `html`, `body`, `#root`, resets, and native element defaults.
- shared primitives use `@layer app.primitives`.
- cockpit shell uses `@layer app.shell`.
- feature route CSS uses `@layer app.features`.
- `app.overrides` is temporary and must include a comment with removal criteria.
- CSS Modules may skip global layers because class names are locally scoped, but their files should still keep mobile rules after base rules.
- Migration must either wrap every existing side-effect CSS file in the correct layer or explicitly allowlist it with a removal task. A single root layer declaration is not sufficient because unlayered CSS outranks layered CSS.

### 6.3 Breakpoint policy

Use semantic breakpoints by product behavior, not device names:

| Breakpoint | Width | Intent |
|---|---:|---|
| mobile | `< 768px` | single primary task, bottom nav, no desktop side rail |
| tablet | `768-1279px` | single content column, optional compact top controls |
| desktop | `>= 1280px` | rail + dense table + multi-panel deck |
| wide | `>= 1600px` | extra density only; no new required information |

Default CSS should be mobile-safe. Desktop density is added through `@media (min-width: 768px)` and `@media (min-width: 1280px)` where practical. Existing max-width rules may remain during migration, but new code should not introduce desktop base rules followed by mobile patches unless there is a documented reason.

### 6.4 Container policy

Reusable panels that can appear in search results, token case, route pages, or side rails should respond to their container, not the viewport. Use CSS container queries for:

- Token Case summary blocks.
- Metric strips.
- Queue/list item cards.
- Evidence/post cards.

Viewport media queries remain appropriate for shell-level decisions such as rail visibility, topbar row count, and mobile task nav.

## 7. Responsive Route Matrix

| Route | Desktop | Tablet | Mobile |
|---|---|---|---|
| `/` Token Radar | rail + topbar + radar table + bottom deck | no rail, top controls, radar primary | no rail, bottom task nav; Radar/Tape/Lab each full-width task |
| `/search` | SearchShell + results + token case panel | stacked results and case | search input first, filters compact, results/case stacked, Home/Main affordance reachable |
| `/signal-lab` | queue + workbench/detail surface | stacked queue/workbench | list-first, detail route visible without hidden panel trap |
| `/signal-lab/pulse/:id` | list context + pulse detail | detail first with list accessible | detail visible as primary task, source/evidence sections stacked; no fixed three-column hero |
| `/stocks` | dense stock radar table | reduced columns | stock card list, no mandatory horizontal scroll |
| `/news` | queue/table + detail surface | stacked table/detail | existing card mode hardened; no 1060px control rail |
| `/news/:newsItemId` | selected news item detail | stacked detail | detail content visible and scrollable to bottom |
| `/macro` | dashboard grid | stacked major panels | one-column regime/indicators/events cards |
| `/watchlist` | hero + timeline + insight rail | stacked content | handle switcher + metrics + timeline cards; user can switch handles without desktop rail |
| `/token/:targetType/:targetId` | dossier + side rails | stacked dossier | hero, propagation, timeline, market, gaps in one column |
| `/ops` | diagnostics grid | stacked diagnostics | one-column status cards; no blocking fixed table |

Mobile top-level navigation must include Radar, Stocks, News, Macro, Watchlist, Ops, and Search. Live-only Radar/Tape/Lab task switching is a separate `features/live` concern and must not render on non-Live routes.

## 8. Acceptance Criteria

- **AC1.** On exact mobile projects `390x844` and `430x932`, cold-loading `/` shows `.live-task-nav`, hides `.desktop-side-rail`, and has no page-level horizontal overflow.
- **AC2.** On mobile, tapping Radar/Tape/Lab changes the visible task panel without route reload and without blank content.
- **AC3.** On mobile, topbar search submits to `/search?q=<query>` and the search route remains usable without side rail.
- **AC4.** On mobile, `/stocks` renders stock rows as cards or a compact list; no required horizontal table scroll wider than viewport.
- **AC5.** On mobile, `/news`, `/news/:newsItemId`, `/macro`, `/watchlist`, `/ops`, `/signal-lab/pulse/:candidateId`, and `/token/:targetType/:targetId` cold-load with visible primary content and no overlapping controls.
- **AC6.** Mobile route tests assert no horizontal overflow both on `document.documentElement` and on route-critical nested containers.
- **AC7.** Mobile route tests scroll each primary route container to bottom and assert the final meaningful row/card/action is reachable and not covered by fixed nav.
- **AC8.** CSS architecture tests fail if any shell CSS unit reintroduces duplicate shell base blocks after mobile rules, if feature CSS owns shell selectors, or if Live-only task selectors / top-level mobile nav are owned by the wrong layer.
- **AC9.** CSS architecture tests report any side-effect CSS file above 700 lines unless allowlisted with a migration note; target after migration is no side-effect CSS file above 500 lines, including `shared/ui/obsidian.css` and `features/watchlist/ui/watchlist.css`.
- **AC10.** Playwright has desktop, tablet, `mobile-390`, and `mobile-430` projects; desktop-only specs cannot force mobile projects back to desktop with `page.setViewportSize`.
- **AC11.** `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build`, and `npm run test:e2e` pass from `web/`.
- **AC12.** `docs/FRONTEND.md` documents CSS layers, side-effect CSS rules, route responsive matrix, and viewport verification gate.

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| CSS split changes visual density on desktop | High | Add desktop Playwright assertions before refactor; keep current visual language and only move ownership/order first |
| Mobile card conversion hides important trading signals | High | Define per-route mobile information hierarchy before deleting columns |
| CSS Modules migration churns many selectors and tests | Medium | Start with cockpit shell, then high-risk route surfaces; update tests with semantic roles where possible |
| Screenshot tests become flaky | Medium | Use deterministic MSW data; prefer geometry assertions for layout invariants and limited screenshots for shell smoke |
| Tailwind v4 layer semantics surprise custom CSS | Medium | Keep Tailwind import isolated; layer only app custom CSS; avoid relying on unlayered overrides |
| Existing user changes in `macro` collide | Low | Do not touch macro implementation until its current dirty changes are reviewed or preserved |

## 10. Rollout Strategy

1. **P0 restore mobile shell.** Fix source order / shell display rules and add mobile e2e guard.
2. **P1 establish CSS architecture gates.** Add layer policy, file-size/ownership tests, and docs.
3. **P2 split cockpit CSS.** Move shell/topbar/rail/mobile nav into focused modules or layered files.
4. **P3 harden route surfaces.** Token Radar, Stocks, News, Signal Lab, Search, Watchlist, Token Case, Macro, Ops each gets explicit mobile behavior.
5. **P4 finish CSS cleanup.** Reduce large side-effect CSS files, remove temporary overrides, and enforce the budget.

## 11. References

- [MDN `@layer`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@layer): cascade layer declaration, precedence, and nested layer syntax.
- [MDN CSS container queries](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries): component styles based on container size instead of only viewport.
- [web.dev media queries](https://web.dev/learn/design/media-queries): media queries as one part of responsive layout, not the whole strategy.
- [Tailwind CSS responsive design](https://tailwindcss.com/docs/responsive-design): mobile-first breakpoint variants and container query variants in Tailwind v4.
- [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots): deterministic screenshot checks for high-risk UI regressions.
