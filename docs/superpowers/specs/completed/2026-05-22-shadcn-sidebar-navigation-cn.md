# Shadcn Sidebar Navigation Upgrade Spec

## 背景

当前 cockpit shell 把三类职责混在同一个左侧 rail：全局路由导航、Radar 过滤器、Radar 诊断/decision counts，以及 Watchlist 快捷列表。这个结构在早期足够快，但现在路由数量已经扩展到 Token Radar、Stocks、News、Macro、Watchlist、Signal Lab、Ops、Search、Token Case，继续堆自定义 rail 会让响应式、二级菜单、移动端导航和后续功能增长都变得脆弱。

Radar item 详情打开也存在明确体验问题：整行点击和主 token 链接都使用新标签，导致高频扫盘时切换慢、浏览器标签污染、返回 Radar 上下文成本高。

## 产品目标

1. 把 app shell 升级为成熟、可持续的 shadcn/ui Sidebar 结构，而不是继续维护自定义 side rail。
2. 让导航表达产品信息架构：全局导航只回答“去哪里”，页面工具栏回答“怎么看/怎么过滤”。
3. 支持长期增长：一二级菜单、badge、icon rail、mobile offcanvas、topbar trigger 都应由同一套 sidebar primitive 承担。
4. Radar row 默认同页进入 Token Case 或 Search，外部站点链接才打开新标签。
5. 移除侧栏里的 `decisions`、`scope`、handle filter 和 watchlist row 列表，降低认知噪音。

## 信息架构

全局导航采用最多两级：

- Radar
  - Token Radar: `/`
  - Stocks: `/stocks`
- Intel
  - News: `/news`
  - Macro: `/macro`
    - Overview: `/macro`
    - Assets: `/macro/assets`
    - Correlation: `/macro/assets/correlation`
  - Watchlist: `/watchlist`
  - Signal Lab: `/signal-lab`
- System
  - Ops: `/ops`

Search 继续以 topbar search 为主。若 sidebar footer 有空间，可以放 Search utility，但不能替代 topbar 搜索工作流。

## 交互要求

- Desktop:
  - Sidebar 常驻左侧，使用 shadcn `SidebarProvider`、`Sidebar`、`SidebarInset`。
  - 支持折叠到 icon rail；折叠后主内容不应产生不可用宽度。
  - 当前路由高亮由 React Router active state 驱动，不再依赖散落的 `useMatch` 手写判断。
- Tablet / Mobile:
  - 不再维护单独 `MobileRouteNav`。
  - 使用 sidebar trigger 打开 offcanvas sidebar。
  - 所有顶级路由在移动端可达，无横向滚动导航条。
- Radar:
  - 点击 row、键盘 Enter/Space、点击 token 主链接都进行同页路由。
  - resolved token 进入 `/token/:targetType/:targetId`。
  - unresolved token 进入 `/search?q=...&window=24h&scope=...`。
  - 外部链接如 X、GMGN、官网、OKX 仍保留 `target="_blank"`。
- Page controls:
  - Radar 的 window/scope/venue 留在 Radar toolbar。
  - handle filter 不再放在全局 sidebar；若继续需要，应成为 Radar 或 Watchlist 页面内部控制。
  - decision counts 不再作为全局导航区块展示；若未来需要，应做成 Radar 内部 summary 或 diagnostic panel。

## 技术设计

采用 shadcn/ui sidebar 的代码拥有模式：组件代码进入本仓库并按本项目 CSS/ownership 规则维护。不会把 sidebar 当外部黑盒。

新增共享 UI primitives：

- `web/src/shared/ui/sidebar.tsx`
- `web/src/shared/ui/sheet.tsx`
- `web/src/shared/ui/separator.tsx`
- `web/src/shared/ui/tooltip.tsx`

新增 cockpit shell units：

- `web/src/features/cockpit/ui/appNavigation.ts`
  - 数据驱动导航定义，包含 label、path、icon、match、badge key、children。
- `web/src/features/cockpit/ui/AppSidebar.tsx`
  - 渲染 shadcn sidebar、groups、submenu、badge、active state。
- `web/src/features/cockpit/ui/AppSidebar.css`
  - 只负责 gmgn 主题适配和 app-specific shell spacing。

重构 shell：

- `CockpitShell` 使用 `SidebarProvider`、`AppSidebar`、`SidebarInset`。
- `SearchShell` 使用同一套 shell，避免 search route 成为第二个导航体系。
- `CockpitSideRail` 与 `MobileRouteNav` 退役。

## 非目标

- 不重做 Token Case 页面布局。
- 不引入 shadcn 全量设计系统或批量改造所有按钮、表格、卡片。
- 不改后端 API、CQRS read model、WebSocket subscription 语义。
- 不把外部链接改为同页路由。

## 验证要求

- Component tests:
  - Radar row 同页导航，不调用 `window.open`。
  - External links 仍新标签。
  - Sidebar 渲染一二级导航、active state、badge。
- Route tests:
  - `/`、`/stocks`、`/news`、`/macro`、`/watchlist`、`/ops`、`/search` 可达。
  - Side navigation counts 能显示 Token/Stocks/News badge。
- Architecture tests:
  - CSS ownership 仍满足 feature/shared 规则。
  - responsive contract 更新为 sidebar/offcanvas，不再要求 `MobileRouteNav`。
- Manual/browser verification:
  - Desktop 1366/1920、tablet 834、mobile 390。
  - Radar row click 后同页进入 Token Case/Search，浏览器 back 回 Radar。
  - Mobile sidebar trigger 可打开并导航，无横向 route nav。

## 风险

- shadcn sidebar 是 viewport-level primitive，会改变 shell DOM 和 CSS cascade；需要集中更新 responsive architecture tests。
- 当前 `CockpitTopbar` 已经承担很多状态，SidebarInset 引入后要避免 topbar 与 center scroller 双重固定造成滚动失控。
- 项目使用 Tailwind v4 和自定义 cascade layers，shadcn 生成代码必须适配现有 token，不直接引入不受控的全局主题桶。
