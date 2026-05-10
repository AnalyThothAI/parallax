# Spec — 前端可深链路由化（Token Radar / Signal Lab / Watchlist）

**Status**: Draft
**Date**: 2026-05-10
**Owner**: aaurix
**Related**: 待生成 plan `docs/superpowers/plans/active/2026-05-10-frontend-deep-link-routing.md`

## Background

`web/` 目前是一个无路由 SPA：

- `web/src/main.tsx:17` 以 `ReactDOM.createRoot` 直接挂载 `<App />`，未引入任何路由库（`web/package.json` 中无 `react-router*` / `@tanstack/router` 依赖）。
- "页面切换"由两处状态驱动：Zustand store `web/src/store/useTraderStore.ts` 中的 `activeView ∈ { "live", "signal_lab" }`、`signalLabHandle`、`signalLabStatus`、`signalLabSearch`、`window`、`scope` 等；以及 `web/src/App.tsx` 中的本地 `useState` 字段 `pageTargetRef`（`App.tsx:110`）、`mobileTask`、`selectedPulseItem`。
- Token Radar 二级页 `web/src/components/TokenTargetPage.tsx` 已经按 `target_type + target_id` 自取数据：`web/src/api/useTokenTargetQueries.ts:24`（`/api/target-social-timeline`）与 `:36`（`/api/target-posts`）。它在 `web/src/App.tsx` 的中列条件渲染中根据 `pageTargetRef` 替换雷达表格，返回按钮调用 `setPageTargetRef(null)`。
- Signal Lab 列表页与详情：`web/src/components/SignalLabWorkbench.tsx`（列表）、`web/src/components/SignalLabPulse.tsx`（侧栏精简列表）、`web/src/components/SignalLabInspector.tsx`（详情）。Inspector 渲染在 `App.tsx` 的右栏 `detail-task-panel`，**完全依赖列表已加载的对象**——后端 `src/gmgn_twitter_intel/api/http.py:438` 只暴露 `/api/signal-lab/pulse` 列表端，没有单条 candidate 的读端。
- Watchlist 数据模型在 `web/src/lib/watchlist.ts`，仅存 `{ handle, unreadCount, lastSeenAtMs }`；`unreadCount` 来自 `accountUnreadCounts` API 字段（`web/src/lib/watchlist.ts:30`），点击不触发本地副作用。侧栏点击通过 `App.tsx:505 focusWatchHandle(handle)` 设置 `signalLabHandle = "@xxx"` 进入 Signal Lab 视图，本质是过滤参数而非独立资源。
- 全 `web/src/` 中无 `useSearchParams` / `URLSearchParams` / `pushState` / `window.location` 赋值的使用；URL 永不变化、刷新即丢、链接不可分享。

后端读端契约位于 `src/gmgn_twitter_intel/api/http.py`：

- Token 二级页所需端点 `/target-posts`（行 170）、`/target-social-timeline`（行 208）均接受稳定的 `target_type + target_id` 作为查询参数。
- Signal Lab 列表 `/signal-lab/pulse`（行 438）接受 `window/scope/status/handle/q/limit/cursor`。
- 无 `/signal-lab/pulse/{candidate_id}` 单点接口。

## Problem

用户无法把"Token Radar 二级页"或"某条 Pulse"以 URL 形式分享、收藏或在新标签页打开；浏览器后退/前进按钮不反映任何前端状态；任何刷新都把用户送回默认视图，丢失筛选与选择。这阻碍了团队内部的协作（无法把一条可疑信号"贴链接"）、用户的多任务工作流（无法用浏览器多标签并行盯多个 token），以及任何"从外部系统跳进 UI 指定位置"的能力。

## First principles

**导航状态属于 URL，不属于内存。** 浏览器把 URL 当作页面身份，前进/后退/刷新/复制粘贴/收藏全部建立在这个契约上。把 `activeView` / `pageTargetRef` / `signalLabHandle` 这类决定页面渲染什么的字段放在 Zustand 内，等同于宣布"我们的 UI 不接受浏览器的导航语义"。这是必须放弃的状态。

**单一 source of truth。** URL ↔ Zustand 的双向同步在过去多次出现"漂移 bug"——本设计直接把导航字段从 store 中物理删除，由 router hook 直读，编译期就消除回退路径。

**深链需要后端可独立解析。** 任何"刷新即可加载详情"的二级页，必须存在一个不依赖列表预加载的单条 GET 端点。否则路由是装饰，而不是契约。

**复用现有契约。** 既有 `/target-posts` / `/target-social-timeline` 已经按稳定 id 查询，直接消费即可；`/signal-lab/pulse/{candidate_id}` 是必须新增的最小后端补丁，schema 与列表项 `SignalPulseItem` 同形，避免前端再写映射层。

## Goals

- **G1.** 任意 Token Radar 二级页可通过 URL 直接打开并刷新一致：同一 `(target_type, target_id)` 在冷启动浏览器、未访问过列表的情况下渲染出与点击进入完全相同的内容。
- **G2.** 任意 Pulse 二级页同上：以 `candidate_id` 为唯一参数，刷新后内容完整渲染，不依赖 `signal-lab/pulse` 列表端预加载。
- **G3.** Signal Lab 列表的 `scope`、`window`、`status`、`handle`、`q` 五个筛选项以 URL query 表示；复制 URL 在新窗口打开、列表筛选与原窗口完全一致。
- **G4.** 浏览器后退键能从二级页恢复到来源列表，列表的筛选与滚动位置恢复至离开时的状态。
- **G5.** 既有业务行为零回归：实时 WS 推送、列表渲染、Inspector 内容、Decision/Snooze/Dismiss 操作、scope 切换、watchlist 未读计数在迁移后语义保持一致，依据 `docs/FRONTEND.md` 的 UI verification gate 跑通。
- **G6.** 编译期校验：Zustand store 中不再保留 `activeView` / `signalLabHandle` / `signalLabStatus` / `signalLabSearch`；`App.tsx` 中不再保留 `pageTargetRef` 本地 `useState`（删除后构建通过）。

## Non-goals

- **N1.** 不为 Watchlist 创建独立路由。Watchlist 是 Signal Lab 列表的过滤入口，handle 项指向 `/signal-lab?handle=…`。
- **N2.** 不改 `EvidenceDetailDrawer` / `TokenDetailDrawer` 这类右栏上下文抽屉的形态——它们是"上下文 peek"，不是"二级页"。
- **N3.** 不重写 mobile 底栏 `mobileTask` 的 panel 切换 UX——它是布局态而非导航态，保留在 store。
- **N4.** 不引入 SSR、不引入路由级代码分割（`React.lazy`）作为本期目标，仅保留为后续扩展路径。
- **N5.** 不动 score 计算与 component breakdown 显示约定（`docs/FRONTEND.md` 的 score display rule 不变）。
- **N6.** 本期不重排 `web/src/` 目录布局；只在现有 `components/` 下抽出 page component 子集。

## Target architecture

**外壳。** `main.tsx` 在 `<QueryClientProvider>` 内嵌套 `<BrowserRouter>`。`<App />` 退化为 `<Routes>` 的容器；所有跨页共享的 chrome（侧栏、scope/decisions、watchlist 列表、底栏 deck、右栏 detail panel slot）抽进 `<CockpitLayout>` 组件，`<Routes>` 嵌套于其内部的 `<Outlet />`。

**Page component 划分。** 在 `web/src/components/` 下新增 page-level 组件：`<LivePage>`（雷达 + 底栏 deck）、`<TokenTargetPage>`（既有，改为消费 `useParams` 而非 store）、`<SignalLabPage>`（workbench + pulse 列表 + Inspector slot）、`<PulseDetailPage>`（沿用 `SignalLabInspector` 渲染，数据来自新的 single-item hook）。

**状态所有权重划。** Zustand store 在本设计后只保留*非导航状态*：

- WS 订阅与连接生命周期；
- watchlist 的 `unreadCount` / `lastSeenAtMs`（不变）；
- selection 缓存（用于 list → detail 的 prefetch hint，不再驱动渲染）；
- decision/snooze/dismiss 的乐观更新 buffer。

以下字段被消除：Zustand `activeView`、`signalLabHandle`、`signalLabStatus`、`signalLabSearch` 不再驱动渲染（由 `useSearchParams` 直读）；`App.tsx` 本地 `useState` 字段 `pageTargetRef` 整体删除（由 `useParams` 直读）；`selectedPulseItem` 仅保留为 list → detail 切换时的 prefetch hint，不再驱动渲染。

**层间纪律。** 维持 `docs/FRONTEND.md` 的层规则不变：组件不直连 `api/`；新增的 pulse 单点 hook 落在 `web/src/api/useSignalLabQueries.ts`（或同构位置），由 page component 通过 store/hook 读取。`api/` 里新 hook 的 staleTime 与列表保持一致，避免双源缓存冲突。

**移动端。** `mobileTask` 仍负责"显示哪个 column"（live / task / detail），与 URL 正交。这是布局响应式状态，不是导航状态。

## Conceptual data flow

```
collector → ingest → enrichment → retrieval
                                       ↓
        ┌─ /api/token-radar ──── store(WS) ──── <LivePage>
        ├─ /api/target-* ────────────────────── <TokenTargetPage>     (URL: /token/:targetType/:targetId)
        ├─ /api/signal-lab/pulse ─────────────── <SignalLabPage>      (URL: /signal-lab?…)
        └─ /api/signal-lab/pulse/{id} (NEW) ──── <PulseDetailPage>    (URL: /signal-lab/pulse/:candidateId)
```

变化的箭头：

- 新增 `/api/signal-lab/pulse/{candidate_id}` → `<PulseDetailPage>`。这是必须新增的，因为 list-only contract 让 deep-link 在刷新时无数据可渲染。
- 既有 `/target-*` 端点的消费方从"由 store `pageTargetRef` 间接驱动"改为"由 URL 直接驱动"。这不是新增数据流，是同一条数据流的触发源换边。

不引入新箭头到 collector / ingest / enrichment 层；本设计完全在 retrieval ↔ web 之间。

## Core models

**Route 集合（前端导航语义层）。** 路由是前端的"导航 model"：

- `/` —— Live Cockpit。雷达列表 + 底栏 deck。
- `/token/:targetType/:targetId` —— Token 二级页。`targetType ∈ { Asset, CexToken }`、`targetId` 为 retrieval 层 resolver 输出的稳定 id（与 `/target-*` 端点入参一致）。不接受链上 `address` 作为路径段，因为它不被后端 `/target-*` 直接接受。
- `/signal-lab` —— Signal Lab 列表，五个 query 字段：`scope`、`window`、`status`、`handle`、`q`。所有字段未传时取 store/UI 的"默认筛选"（与现状一致）。
- `/signal-lab/pulse/:candidateId` —— Pulse 二级页。`candidateId` 为 `SignalPulseItem.candidate_id`（`web/src/types.ts` 中已声明非空）。资源不存在时在该路由内显示 in-page 404 状态（不跳转）。
- 未匹配任何路由的 URL（例如手输入错路径）—— 重定向到 `/`，**不**显示 404 全屏（避免在内部工具中制造体验断层）。注意这与"路由匹配但资源不存在"是两件事。

**Watchlist 链接生成约定。** `web/src/App.tsx` sidebar 中 watchlist 项不再调 `focusWatchHandle`，而是渲染为 `<Link to={'/signal-lab?handle=' + handle}>`。链接是 watchlist 的对外契约，handle 字符串是该契约的唯一 id。

## Interface contracts

**新增 HTTP 端点（PR1 范围）。**

`GET /api/signal-lab/pulse/{candidate_id}` —— 返回单条 `SignalPulseItem`。

- 输入：路径参数 `candidate_id`（字符串、非空）；可选 query `window`、`scope` 仅用于决定派生字段（如热度窗口、scope 内排序位次）的取值范围；缺省时取与列表端相同的默认（`window=1h`、`scope=all`）。**不**用 scope/window 过滤 candidate 本身，否则破坏 G2（深链刷新一致性）。
- 输出：单对象 payload，与 `/api/signal-lab/pulse` 列表项 schema 严格同形。前端类型 `SignalPulseItem` 在两端共用，禁止单点端引入新字段或裁剪字段。
- 错误：当 candidate 不存在时返回 404；auth 与列表端共用 `_authenticated_runtime`。当前 `api/http.py` 不配置应用层 rate limit middleware，本端口同样不引入新限流。
- 幂等性：纯读，与列表端共用 `SignalPulseService` selector 路径，不引入新查询计划。

**前端导航契约。**

- 列表 → 二级页：通过 `<Link>` / `useNavigate`，**禁止** 任何代码直接调用 `window.location`、`history.pushState`、`history.replaceState`。
- 二级页 → 列表回退：依赖浏览器原生 `history.back()`；额外提供"返回"按钮调用 `useNavigate(-1)`，回退栈为空时 fallback 到 `/`。
- Query 序列化：scope/window/status/handle/q 五个字段缺省时不写入 URL（保持地址栏短）；非缺省时显式写入。

## Acceptance criteria

- **AC1.** WHEN 用户在 Token Radar 列表点击一行 THEN 浏览器地址栏更新为 `/token/:targetType/:targetId` 且二级页内容与现状一致。
- **AC2.** WHEN 用户在 `/token/:targetType/:targetId` 上硬刷新（清缓存或新窗口冷加载）THEN 二级页内容完整渲染，不依赖列表预加载。
- **AC3.** WHEN 用户访问 `/signal-lab/pulse/:candidateId` 且该 candidate 存在 THEN Inspector 渲染该 candidate 全字段；WHEN 不存在 THEN 在该路由内显示 in-page 404 提示（保留侧栏 + 列表可见），不重定向、不全屏报错。
- **AC4.** WHEN 用户在 `/signal-lab` 修改 scope/window/status/handle/q THEN URL query 同步更新，且复制 URL 在新标签打开列表筛选完全一致。
- **AC5.** WHEN 用户在二级页按浏览器后退键 THEN 回到来源列表，列表的滚动位置与筛选与离开时一致。
- **AC6.** WHEN 既有手动验证清单（`docs/FRONTEND.md` §UI verification gate）跑过 THEN 全部通过——无失败 `/api/*`、WS 帧到达、score 仍带 component breakdown。
- **AC7.** WHEN 编译当前代码库 THEN Zustand store 中不再存在 `activeView`、`pageTargetRef`、`signalLabHandle` 字段（迁移完整性的硬证据）。

## Risks

| 风险 | 严重性 | 缓解 |
|------|--------|------|
| `App.tsx` 拆解触发条件渲染漏切，破坏现状 UX | 高 | PR2 单独完成 layout 抽离 + Token 路由；Vitest + RTL 渲染快照覆盖 `/` 与 `/token/...`；UI verification gate 全跑 |
| URL ↔ Zustand 双源同步漂移 | 中 | 物理删除导航字段而非保留双源；编译期防止开发者把状态加回 store |
| `/signal-lab/pulse/{candidate_id}` 触发 N+1 或鉴权遗漏 | 中 | 复用 `PulseRepository.candidate_by_id` 的单行查询（`src/gmgn_twitter_intel/storage/pulse_repository.py:621`）与 `SignalPulseService` 的 `_item` mapper；auth 走 `_authenticated_runtime`，与列表端同一路径，pytest 覆盖 401/404 |
| 二级页 deep-link 在现有 retrieval 缺数据时表现退化（例如 scope 切换后该 candidate 不在该 scope） | 中 | 单点端不强制 scope 过滤，仅用于跨窗口诊断；前端在显示时给出明确的 scope 提示 |
| react-router 增加 ~12KB gzip | 低 | 接受；后续可按需 `React.lazy` 切代码分割，不在本期 |
| 移动端 `mobileTask` 与路由的关系混淆 | 中 | spec 显式声明 `mobileTask` 是布局态、不参与 URL；`Boundaries` 表格列入；评审时检查 |
| watchlist 链接化破坏副作用 | 低 | 经审计 `App.tsx:505 focusWatchHandle` 当前*不触发*任何 unreadCount 变更；`unreadCount` 来自 `accountUnreadCounts` API 字段（`web/src/lib/watchlist.ts:30`）。链接化仅替换 `onClick` 为 `<Link>`，无副作用变更 |

## Evolution path

本设计为后续以下扩展铺路而不预提交：

- **路由级代码分割**：`<TokenTargetPage>` / `<SignalLabPage>` / `<PulseDetailPage>` 成为天然的 `React.lazy` 切点。
- **新增二级页**（如 `/account/:handle` 的账户主页）：复用 `<CockpitLayout>` 与三层 page 模式，不需要再次推翻外壳。
- **embed 视图**（`/token/...?embed=1` 给外部仪表盘嵌入）：query 已是首选状态层，扩展无需路由结构变更。

需要保留的可逆性：

- `targetType` / `targetId` 路径段不引入业务语义校验（保持 router 不知 domain）；后端契约变化不会逼着改路由。

## Alternatives considered

- **A. 自造 `pushState` + `popstate` 监听 hook，不引入路由库。** 拒绝：`web/` 已有 1638 行的 `App.tsx` 与多个跨页 chrome 区域，自造路由意味着自己实现嵌套路由、`<Outlet />` 等价物、链接组件、滚动恢复——所有这些 react-router 已经成熟实现，自造的边际维护成本远高于 ~12KB gzip 的依赖代价。违反 "不重复造轮子" 原则。
- **B. 路由作为门面，Zustand 仍驱动渲染（双向同步）。** 拒绝：双源同步在过去已多次出现 staleness 与 ordering bug；`docs/FRONTEND.md` 的"State discipline"原则要求清晰的所有权边界。即便短期成本更低，长期会让任何"修一个状态字段"的改动都需要在两侧确认。
- **C. 仅在初始加载和"分享"时读写 URL，运行时仍用 Zustand。** 拒绝：浏览器后退/前进键不反映 UI 变化等于"假路由"；G4 直接破功；用户预期与现状几乎无差。
- **D. 把 Watchlist 升级成独立资源 `/watchlist/:handle`。** 拒绝：watchlist 是 Signal Lab 的过滤入口，不是独立资源；强行造路由会复制 Signal Lab 的 chrome，且使"切过滤器"变成"换页"，破坏现有快速切换 UX。
- **E. 以链上 address 作为 token 路径段（`/token/:address`）。** 拒绝：后端 `/target-*` 端点不接受 address，前端将被迫做 address → target_id 的映射查询，每次进二级页多一次往返；且 CEX token 没有 address。

## Boundaries

| 类别 | 行为 |
|------|------|
| Always | 导航字段以 URL 为唯一 source of truth；组件通过 `useParams` / `useSearchParams` 读 |
| Always | 列表 → 二级页通过 `<Link>` / `useNavigate` 完成 |
| Always | Pulse / Token 二级页提供独立的 single-item 数据获取路径，不依赖列表预加载 |
| Always | watchlist 项作为 `<Link>` 渲染，click 仍触发 `markWatchHandleRead` 副作用 |
| Ask first | 新增任何 "深层资源 → 路由" 的提案（如 account profile、project profile） |
| Ask first | 把现有抽屉（Evidence/TokenDetail）升级为路由 |
| Never | 在任何代码处直接读写 `window.location` / `history.pushState` / `history.replaceState` |
| Never | 在 Zustand store 内重新引入 `activeView` / `signalLabHandle` / `signalLabStatus` / `signalLabSearch`；在 `App.tsx` 内重新引入 `pageTargetRef` |
| Never | 在前端做 score 重算或组件 breakdown 重组，沿用 API 输出 |
