# Spec — 前端架构与测试 · 审计 + 目标架构 hard cut

**Status**: Draft
**Date**: 2026-05-13
**Owner**: Claude
**Related**: `docs/superpowers/specs/active/2026-05-11-frontend-experience-architecture-hard-cut.md`（前一轮 hard cut，部分落地） · `docs/superpowers/specs/completed/2026-05-10-frontend-deep-link-routing.md` · `docs/FRONTEND.md` · `docs/ARCHITECTURE.md`

## 1. 背景

### 1.1 一句话定性

`web/` 在 2026-05-11 hard cut 后达到了 **"路由分层 + 部分 feature hook 抽取"** 的中间态，但 **状态所有权 / 组件契约 / 测试金字塔 / CSS 体系 / DX 脚手架** 五条主线都未到生产线。最大风险不是某个 bug，而是 **"未来任一改动需要同时理解 `CockpitApp` + `CockpitLayout` + `useTraderStore` + `useLiveSelection` 四块状态机"** —— 爆炸半径过大、回归靠手测、新人无法独立交付一个完整 feature。

### 1.2 当前状态（事实清单，已 grep / wc 核对）

**A. 架构与状态所有权**

- `web/src/app/CockpitApp.tsx` 273 行；单点装载 `/`、`/token/:targetType/:targetId`、`/signal-lab`、`/signal-lab/pulse/:candidateId`、`/search`、`/stocks`，全部包在一个 `CockpitLayout` 内。
- `web/src/components/CockpitLayout.tsx` 474 行，**76-prop drilling 容器**；通过 `location.pathname.startsWith()` 在 layout 内分支 `isSearch / isStocks / isLive / isSignalLab` 四种版式（`CockpitLayout.tsx:127–132`、`:217`、`:310`、`:328`、`:335`），违反 "组件只渲染、决策上移" 的原则。
- `web/src/store/useTraderStore.ts` 15 字段同时持有：① 路由可分享的过滤（`token` / `window` / `scope` / `handles` / `search` / `radarSortMode`）② cockpit-local 交互（`detailTab` / `detailWindow` / `postRange` / `postSortMode` / `hideDuplicateClusters` / `watchedPostsOnly`）③ 选中状态（`selectedBucketStartMs` / `selectedEventId` / `detailMode`）。三类生命周期被绑在一个 store。
- `web/src/components/TokenTargetPage.tsx:76` 直接 `useQuery + getApi`；`:51-52` 把 `scope` 从 URL 和 store 双源读取（fallback 链）。违反 2026-05-11 spec 的 G6（"presentational components do not call `getApi` directly"）。
- `web/src/api/useIntelSocket.ts` 不论路由都开（只要有 `token`），`marketTargets` 来自 radar 行；订阅在 `/search`、`/signal-lab`、`/stocks` 路径下也持续维持，做无用功。

**B. 测试**

- `web/src/App.test.tsx` 一个文件 1427+ 行；通过 `vi.mock("./api/client")` 和 `vi.mock("./api/useIntelSocket")` 直接 mock 模块导出 —— 与实现细节强耦合，重构 api 层后所有测试需要重写。
- 没有 MSW（请求 mock 走模块替换而非网络层）。
- 没有 Playwright（仅 `.playwright-mcp/` 截图目录，是 MCP 工具产物，不是 e2e 框架）。
- `web/src/components/__tests__/*.routing.test.tsx` 5 个路由测试仅做 "渲染没崩" 级别断言。
- 0 a11y 自动化测试（ESLint `jsx-a11y/alt-text: warn` 是唯一规则）。
- `web/vite.config.ts` 通过 `projects[]` 把 App.test.tsx 单独 sequence 跑（`groupOrder: 1`），是为了避开 jsdom 跨测试串扰 —— 这本身就是 App.test.tsx 过大的副作用。

**C. Vite / TS / 契约 / DX**

- `web/src/api/types.ts` 1232 行手写 + `web/src/api/openapi.ts` 1458 行 generated 但 eslint ignore + 无人消费 → 双源真相。
- 无 path alias，组件大量 `../../../api/types` 风格 import。
- 无 `ErrorBoundary`，单组件 throw 整个 cockpit 白屏。
- 无 `Suspense`，所有 loading 走 `isPending` 手工分支。
- 无 route-level code splitting；首屏一次性下载 SignalLab + Search + Stocks。
- 无 `eslint-plugin-react-refresh`（Vite + React 19 社区默认必装）。
- `tsconfig.json` 缺 `noUncheckedIndexedAccess` / `exactOptionalPropertyTypes` / `verbatimModuleSyntax`。
- 无 `VITE_*` envvar 层，`web/src/api/client.ts:38–39` 直接读 `window.location.origin`。
- `ws_token` 通过 `useTraderStore` 暴露给所有组件。

**D. CSS / 设计体系 / a11y**

- `web/src/styles.css` 5506 行单文件；class 名通过 `className={\`mobile-task-${task} ${isSignalLab ? "signal-lab-mode" : ""} ${isStocks ? "stocks-main-nav-mode" : ""} ${isSearch ? "search-focus-mode" : ""}\`}`（`CockpitLayout.tsx:217`）字符串拼接，无类型保护。
- 装了 `@tailwindcss/vite` v4 但组件几乎不用 utility。
- `web/src/shared/ui/RemoteState.tsx` 有 `SkeletonRows` / `PanelSkeleton` / `RouteStatePanel`，但 `SignalLabPulse` / `TokenPostsPanel` / `PulseDetailPage` / `SearchIntelPage`（`"loading search intel"` 字面量，`SearchIntelPage.tsx:61`）仍用文本占位 —— 2026-05-11 spec G5 未完成。
- 顶栏 search input 无 `<label>`（`CockpitLayout.tsx:172-177`），仅 placeholder。

## 2. 问题陈述

工程层面：改动一个 page 需要理解整个 `CockpitApp + CockpitLayout + useTraderStore + useLiveSelection` 状态机；新增 feature 没有清晰的 "拷贝模板"；测试套件与具体模块路径耦合，重构必断测；CSS 不能局部裁剪。

用户层面：路由间状态丢失（refresh `/` 后 window 不保留）；URL 不能分享精确视图（`/?` 后没有 query）；签号订阅在不相关路由仍维持，耗带宽；通知和异步错误偶有"卡 loading"或"白屏 throw"。

契约层面：手写 types 与 openapi 双源，schema drift 不可控。

## 3. 第一性原则（spec 全文的不动点）

1. **URL 是导航和可分享过滤的唯一所有者。** `window` / `scope` / `handles` / `search` / `radarSortMode` 在所有有路由身份的页面上都必须能通过冷加载 URL 复现。Zustand 不允许镜像任何路由参数。
2. **React Query 是 server state 的唯一所有者。** HTTP 拉取塞 cache、WebSocket delta 通过 `setQueryData` 打补丁。组件**不直接调用** `getApi`。
3. **Zustand 只持有 cockpit-local 不可分享的交互状态**（`detailTab` / `postRange` / `selectedBucketStartMs` / `watchedPostsOnly` / `hideDuplicateClusters` / `mobileTask` 等）。其余字段从 store 删除。
4. **WebSocket 订阅是路由感知 + 引用计数的。** `marketTargets` 只在该路由真实需要时订阅，路由切换释放订阅。
5. **API 类型唯一源：`openapi-typescript`。** 手写 `api/types.ts` 缩成 facade（重命名 / 业务别名），不允许声明新字段。
6. **每个组件回答三问**：做什么、外部怎么调用、依赖谁。回答不清就重新切分。`CockpitLayout` 必须从 76 props 降到 ≤ 10。
7. **测试金字塔覆盖全栈**：纯函数 unit / RTL component / MSW-backed RQ integration / Playwright 关键路径。`App.test.tsx` 解体。
8. **每个 Phase 是一个独立 hard cut PR**，不允许 dual-write / feature flag，验收红绿成对。

## 4. 目标 / 非目标

### 4.1 目标

- G1. 依赖单向 `lib → shared → features → routes → app`，由 ESLint `import/no-restricted-paths` 机械化守护。
- G2. `useTraderStore` 字段 ≤ 10 且不含 `token` / `window` / `scope` / `handles` / `search` / `radarSortMode`（15 → ≤ 10 = 删除 6 + 余 9）。
- G3. `web/src/components/` 这一层不存在；所有组件落到 `features/<f>/ui/` 或 `shared/ui/`。
- G4. `CockpitLayout` 不存在；继任者 `CockpitShell` / `CockpitTopbar` / `CockpitSideRail` / `CockpitMobileNav` 每个 ≤ 10 props，自取 hook。
- G5. 任意路由（`/` `/token/:type/:id` `/signal-lab` `/signal-lab/pulse/:id` `/search` `/stocks`）的当前过滤可通过 URL search params 完整复现冷加载。
- G6. 组件层无 `useQuery` / `useMutation` / `getApi` / `setQueryData` 调用；这些只在 `features/*/api/` 出现。
- G7. WebSocket 单例由 `shared/socket/IntelSocketProvider` 持有；`marketTargets` 由 `useMarketSubscription` 按引用计数注册 / 释放。
- G8. `App.test.tsx` 行数 < 100 或文件删除；测试套件按 L0–L3 四层分布。
- G9. 测试不依赖 `vi.mock("./api/client")` 或 `vi.mock("./api/useIntelSocket")`；HTTP 与 WS 替换由 MSW 在网络层完成。
- G10. Playwright 5–7 条 golden path 在 chromium 上跑通；CI 集成。
- G11. API 类型由 `openapi-typescript` 单源生成；`lib/types/index.ts` 仅做业务别名 facade；CI `git diff --exit-code lib/types/openapi.ts` 阻止漂移。
- G12. 路由级 `lazy()` + `Suspense` + `ErrorBoundary`；单 route 抛错不带崩整页。
- G13. `noUncheckedIndexedAccess` / `exactOptionalPropertyTypes` 开启；path alias `@app/* @routes/* @features/* @shared/* @lib/*` 接入。
- G14. `styles.css` 5506 行不存在；CSS 拆为 `styles/{tokens,base,tailwind}.css` 三件套 + 组件就近 `.module.css` 与 Tailwind utility 组合。
- G15. 字符串拼接 className 不存在；改 `clsx` / 联合类型 prop。
- G16. `jsx-a11y/recommended` 全为 error；axe-core 在 L1+L2 测试 0 violations。
- G17. RemoteState 在所有 loading / empty / error / stale 场景统一使用；不再有 `"loading search intel"` 这种文本占位。

### 4.2 非目标

- N1. 不改后端 schema / scoring / 公共 HTTP+WS 契约（只调对接方式）。
- N2. 不引入 UI kit / Radix / MUI / shadcn；Tailwind utility + 自有原语足够。
- N3. 不引入 SSR / RSC / Next.js。
- N4. 不引入新的 state library（Jotai / Recoil / Redux）。Zustand + RQ + URL 就够。
- N5. 不重写产品功能；功能等价是验收硬要求。
- N6. **不追求 bundle size / 速度作为 spec 验收**。不设 chunk gzip 预算，不接 bundle-analyzer CI 阻塞，不做 `React.memo` 热点优化，不强制 `manualChunks` vendor 拆分。路由级 `lazy()` 留下（为 Suspense / ErrorBoundary 边界服务），但不为它写 size assertion。
- N7. Playwright 不跑 firefox / webkit；只 chromium。
- N8. 不上 Storybook / visual regression / Sentry / OpenTelemetry。
- N9. 不启用 React 19 compiler。

## 5. 目标架构 · 整体

### 5.1 五层分层模型

| 层 | 责任 | 允许 import | 禁止 |
|---|---|---|---|
| `app/` | 组合根：QueryClientProvider · BrowserRouter · ErrorBoundary · Suspense · Routes 装载。**只装配，不决策、不取数、不持有局部状态**。 | `routes/` · `shared/` · `lib/` | 不直接 import `features/*` 内部模块，只 import 各 feature 的 route entry。 |
| `routes/` | 每条路由一个文件（`live.route.tsx` / `signal-lab.route.tsx` / `signal-lab.pulse.route.tsx` / `search.route.tsx` / `stocks.route.tsx` / `token-target.route.tsx`）。**route entry = 路由级 lazy + ErrorBoundary 边界 + Suspense fallback**。 | `features/*` 的 entry export · `shared/ui` | 不写业务、不持有状态。 |
| `features/<f>/` | 每个 feature 自闭包：`api/`（RQ hook + WS bridge）· `model/`（pure TS 域模型 + 计算）· `state/`（URL 解析/序列化 + per-feature zustand slice 如有）· `ui/`（React 组件）· `index.ts`（对外 entry export）。 | 同 feature 内任意层 · `shared/*` · 其他 feature 的 `index.ts` | **禁止**跨 feature 深 import（`features/live/ui/X.tsx` 不能 import `features/search/ui/Y.tsx`）。 |
| `shared/` | 跨 feature 复用：`ui/`（RemoteState / Skeleton / Empty / ErrorBoundary / Segmented / IconButton 原语）· `query/`（query-key factory + cache patch helper）· `socket/`（useIntelSocket 通用桥）· `routing/`（路径常量 + 类型化导航）· `format/`（数字/时间/地址，原 `lib/format` 升格）· `a11y/`。 | `lib/` 与 stdlib | **禁止** import `features/*` 或 `app/`。 |
| `lib/` | 与 React 无关的纯 TS 工具与契约：`api/`（openapi 生成 + fetch client + ApiError）· `env/`（VITE_* 解析 + 类型化 config）· `types/`（openapi 重导出 + 业务别名 facade）。 | stdlib · 第三方 | **禁止** import 任何 React 代码、`shared/`、`features/`、`app/`。 |

依赖方向（单向）：`lib/ → shared/ → features/ → routes/ → app/`。反向**机械化**禁止（ESLint `import/no-restricted-paths`）。

### 5.2 目标目录树

```
web/src/
├── app/
│   ├── AppRoot.tsx                 # QueryClient + Router + ErrorBoundary + Suspense
│   ├── AppRoutes.tsx               # <Routes> 表，只列 route entries
│   └── providers/                  # QueryClient 配置 / Toast / ThemeTokens
├── routes/
│   ├── live.route.tsx
│   ├── signal-lab.route.tsx
│   ├── signal-lab.pulse.route.tsx
│   ├── search.route.tsx
│   ├── stocks.route.tsx
│   └── token-target.route.tsx
├── features/
│   ├── live/
│   │   ├── api/                    # useLiveRadarQuery, useLiveRecentQuery, useLiveMarketSocket
│   │   ├── model/                  # tokenRadarItems, liveTapeModel, marketUpdatePatch
│   │   ├── state/                  # liveRouteState (URL), liveSelectionSlice (zustand)
│   │   ├── ui/                     # LivePage, LiveRadar, LiveTape, TokenDetailDrawer, RadarRow
│   │   └── index.ts
│   ├── signal-lab/
│   │   ├── api/                    # useSignalPulseList, useSignalPulseDetail, useAccountEvents
│   │   ├── model/                  # decision counting, pulse compactor
│   │   ├── state/                  # signalLabRouteState (URL)
│   │   ├── ui/                     # SignalLabPage, SignalLabWorkbench, SignalLabPulse, PulseDetail
│   │   └── index.ts
│   ├── search/
│   │   ├── api/                    # useSearchInspectQuery
│   │   ├── model/                  # search route state + result kind decision
│   │   ├── state/                  # searchRouteState
│   │   ├── ui/                     # SearchIntelPage + sub-panels
│   │   └── index.ts
│   ├── stocks/
│   ├── token-target/
│   ├── notifications/              # 跨路由抽屉 + toast + ws bridge
│   └── cockpit/                    # 顶栏 + 左侧 rail + 移动端 task nav
├── shared/
│   ├── ui/                         # RemoteState, Skeleton, Empty, ErrorBoundary, Segmented, IconButton
│   ├── query/                      # queryKeys factory, patchQueriesByPredicate
│   ├── socket/                     # useIntelSocket, socket types
│   ├── routing/                    # paths, navigate helpers, useRouteScope
│   ├── format/                     # 数字 / 时间 / 地址 / token label
│   └── a11y/
├── lib/
│   ├── api/                        # client.ts (fetch + ApiError), websocketUrl
│   ├── env/                        # parseEnv (VITE_*) + Config type
│   └── types/                      # openapi.ts (generated) + index.ts (facade)
└── styles/
    ├── tokens.css                  # design tokens (colors / fonts / spacing / radius / shadow)
    ├── base.css                    # reset + html/body
    └── tailwind.css                # @import "tailwindcss" + @theme directives
```

### 5.3 组件契约 · `CockpitLayout` 拆分

```
CockpitShell           # 路由级 layout outlet（Search 用 SearchShell，其它用 CockpitShell）
  ├── CockpitTopbar    # 自取：status pill + searchbar + notification bell + useNotificationsController
  ├── CockpitSideRail  # 自取：views nav + scope/handles (URL-aware) + decision counts + watchlist
  └── Outlet           # 路由内容
CockpitMobileNav       # 路由级 task nav，自取 location
```

每个组件 ≤ 10 props，自己消费 hook，不向上接 prop drilling。Search 路由用 `SearchShell` 独立 outlet，**杀掉 layout 内的 `isSearch ? ... : null` 散落分支**。

### 5.4 ESLint 边界守护

```js
// eslint.config.js 新增
"import/no-restricted-paths": [
  "error",
  {
    zones: [
      { target: "src/lib",    from: ["src/shared", "src/features", "src/routes", "src/app"] },
      { target: "src/shared", from: ["src/features", "src/routes", "src/app"] },
      { target: "src/features/*/ui",
        from: "src/features/!(<self>)/**/*", except: ["**/index.ts"] },
      { target: "src/features/*/api",
        from: "src/features/!(<self>)/**/*", except: ["**/index.ts"] },
      { target: "src/features/*/state",
        from: "src/features/!(<self>)/**/*", except: ["**/index.ts"] },
    ]
  }
],
"no-restricted-imports": [
  "error",
  { paths: [
    { name: "../../../api/client", message: "use feature api hook" },
    // openapi facade 强制规则
    { name: "@lib/types/openapi", importNames: ["*"],
      message: "use @lib/types facade, not raw openapi" }
  ]}
],
"plugin:react-refresh/only-export-components": ["error"],
"plugin:jsx-a11y/recommended": "error",  // warn → error
```

## 6. 目标架构 · 交互 / 状态流（URL ⟷ RQ ⟷ Zustand ⟷ WS）

### 6.1 状态五桶模型

| 桶 | 寿命 | 例 | 序列化 |
|---|---|---|---|
| **URL search params** | 跟随路由，可分享，可冷重启复现 | `window` · `scope` · `handles` · `q` · `sort` · `signal-lab.status/handle` · `token-target.window/scope/tab/postRange/postSort` | `URLSearchParams` |
| **React Query cache** | 进程内；stale-time / refetchInterval 控制；WS delta `setQueryData` 打补丁 | 所有 `/api/*` 响应 · `current_market` · pulse list/detail · search inspect | key factory |
| **Per-feature Zustand slice** | 进程内，跨路由可保留；**不允许镜像 URL** | `live.detailTab` · `live.postRange` · `live.postSortMode` · `live.selectedBucketStartMs` · `live.selectedEventId` · `live.watchedPostsOnly` · `live.hideDuplicateClusters` · `notifications.drawerOpen` · `cockpit.mobileTask` | 内存；可选 persist 仅对 `cockpit.mobileTask` 等无关数据 |
| **Component local `useState`** | 单次挂载；submit 前的草稿 | 顶栏 search input 值（submit 才落 URL）· 临时折叠开关 · 草稿 | 不持久化 |
| **Browser storage** | 跨标签 / 跨会话 | 本 spec 不存 ws_token；只在 `lib/api/client.ts` closure 内 | 不在本 spec 范围 |

**关键裁决**：
- `useTraderStore` 15 字段 → ≤ 10 字段。删除 `token` / `window` / `scope` / `handles` / `search` / `radarSortMode`；余 `detailTab` / `detailWindow` / `detailMode` / `selectedBucketStartMs` / `selectedEventId` / `postRange` / `postSortMode` / `hideDuplicateClusters` / `watchedPostsOnly` = 9 字段。
- `radarSortMode` 走 URL（`/?sort=heat` 可分享）。
- `token`（ws_token）从 store 移除，进 `lib/api/client.ts` closure；bootstrap 拉到后 `setWsToken(token)` 注入；组件不再感知。
- `search`（顶栏输入框）→ 顶栏组件 local `useState`，submit 才 `navigate` 写 URL；彻底消灭双源。

### 6.2 数据流四象限

```
              INPUT                                    OUTPUT
      ┌─────────────────────┐               ┌────────────────────────┐
      │  HTTP /api/*        │               │  React Query cache     │
      │  WS /ws frame       │ ──────────►   │  (single owner of      │
      │                     │               │   server data)         │
      └─────────────────────┘               └──────────┬─────────────┘
                                                       │
                                                       ▼
      ┌─────────────────────┐               ┌────────────────────────┐
      │  URL search params  │ ──────────►   │  RQ queryKey / params  │
      │  (single owner of   │               │  feature route-state   │
      │   nav + filter)     │               │  hook → useQuery       │
      └─────────────────────┘               └──────────┬─────────────┘
                                                       │
                                                       ▼
      ┌─────────────────────┐               ┌────────────────────────┐
      │  User gesture       │ ──click───►   │  Zustand slice (local) │
      │  (click / type /    │ ──submit──►   │  URL navigate          │
      │   key)              │ ──hotkey──►   │  React Query mutate    │
      └─────────────────────┘               └────────────────────────┘
```

读写规则（机械化、可 lint）：
- **组件读**：从 RQ `useXxxQuery` 拿 server 数据；从 Zustand slice 拿交互；从 `useSearchParams` 拿路由状态。**绝不**从 RQ cache 之外取 server data。
- **组件写**：通过 feature 暴露的 `setXxx` action 或 `navigate(...)`；**绝不**直接调 `getApi` / `setQueryData`。

### 6.3 路由感知的 WebSocket 生命周期

现状：`useIntelSocket` 在 `useLiveData` 里挂载，只要 `token` 在就保持连接 + 订阅 radar 行的 `marketTargets`，无视当前路由。

目标：

```
ws 连接          ← AppRoot 级别一次，跨整个会话保持
auth/ready       ← 连接 ready 后发一次（不变）

market_targets   ← 由当前激活 feature 通过 useMarketSubscription(targets) 注册
                   features/live 在 / 路由下注册 radar 可见行
                   features/token-target 在 /token/... 注册当前 target
                   features/search 在 /search?q=token 注册解析后的 target
                   features/signal-lab / stocks 不注册
                   路由切换 / 行更新触发 diff → 发送增量 subscribe / unsubscribe 帧

notifications    ← AppRoot 全局订阅（跨路由通知不能丢）
events           ← features/live 注册（仅 / 路由下需要 live tape）
```

实现：单例 socket 由 `shared/socket/IntelSocketProvider` 提供；`useMarketSubscription(targets: TargetRef[])` 是注册-引用计数 hook，feature unmount 时减计数；后台聚合后 send 一次 `subscribe` 帧。

**契约**：路由切到 `/signal-lab` 时，radar 的 `marketTargets` 自动释放；socket 连接保留，订阅集合改变。

### 6.4 RQ 缓存补丁拓扑（`shared/query/`）

```ts
// shared/query/queryKeys.ts —— 唯一定义 query key 的地方
export const queryKeys = {
  bootstrap: () => ["bootstrap"] as const,
  status:    () => ["status"] as const,
  liveRecent:(p: { scope: ScopeKey; handles: string }) => ["live", "recent", p] as const,
  tokenRadar:(p: { window: WindowKey; scope: ScopeKey }) => ["token-radar", p] as const,
  signalPulse:(p: { window: WindowKey; scope: ScopeKey; limit?: number; sort?: string }) =>
    ["signal-lab", "pulse", p] as const,
  signalPulseDetail:(id: string) => ["signal-lab", "pulse", "detail", id] as const,
  searchInspect: (p: SearchRouteState) => ["search", "inspect", p] as const,
  tokenTargetTimeline: (p: TokenTargetParams) => ["token-target", "timeline", p] as const,
  tokenTargetPosts:    (p: TokenTargetParams) => ["token-target", "posts", p] as const,
};

// shared/query/patchMarketUpdate.ts —— WS delta 打补丁的唯一通道
export function patchMarketUpdate(qc: QueryClient, update: LiveMarketUpdatePayload) {
  qc.setQueriesData(
    { predicate: (q) => q.queryKey[0] === "token-radar" },
    (data: AssetFlowData | undefined) => data ? applyMarketUpdate(data, update) : data
  );
}
```

**规则**：`features/*/api/` 内 `useQuery` 必须使用 `queryKeys.xxx(...)`；WS 桥必须通过 `patch*` helper 改 cache。**禁止**在组件内直接 `setQueryData`。

### 6.5 路由表 + 重载契约

| 路径 | URL 参数 | 冷加载行为 |
|---|---|---|
| `/` | `window`（默认 `1h`）· `scope`（默认 `all`）· `handles`（默认空）· `sort`（默认 `opportunity`） | radar / tape 同时 skeleton；socket 订阅 radar 行 |
| `/token/:targetType/:targetId` | `window` · `scope` · `tab`（默认 `timeline`）· `postRange`（默认 `current_window`）· `postSort`（默认 `recent`） | timeline + posts 同时 skeleton；socket 订阅当前 target |
| `/signal-lab` | `window` · `scope` · `status` · `handle` · `q`（均可选） | list skeleton；**不自动跳详情** |
| `/signal-lab/pulse/:candidateId` | 继承 `/signal-lab` 全部 | list + detail 同时 skeleton；mobile 默认 detail 面板 |
| `/search` | `q`（必需）· `window` · `scope`（默认 `all`） | inspect skeleton；socket 在 token-result 出现后才订阅 target |
| `/stocks` | `window` · `scope` | 不订阅 market_targets |

**强制硬规则**：删除任何 redirect-on-empty（如 signal-lab 自动跳详情）；空状态显示"无结果"，路由稳定。

### 6.6 跨 feature 协作

| 协作 | 协议 | 实现 |
|---|---|---|
| 顶栏 search 提交 → navigate | `features/cockpit/ui/CockpitTopbar.tsx` 在 submit 时按当前路由派发：`/signal-lab` → 更新 `q`；其他 → `/search?q=...` | local input + `useNavigate` |
| Notification 点击 → 路由跳转 | `features/notifications/useNotificationsController` 接收 item，按 `entity_kind` 派生路径 | 调用 `shared/routing/paths` |
| Watchlist 行点击 → signal-lab 过滤 handle | `features/cockpit/ui/CockpitSideRail` 用 `<Link to={paths.signalLab({ handle })} />` | 不走 store |
| Live Tape 选中 → 详情抽屉 | `features/live/state/liveSelectionSlice` | 仅 `/` 路由下生效；其他路由不实例化 |
| Radar 行点击 → 进 Search Intel | `useNavigate(paths.search(item, window, scope))` | 不依赖 store |

**关键变化**：`useLiveSelection` 不再读 `useLocation`、不再做 `suppressTokenDetailRoute` 分支。它只在 `/` 路由下挂载（通过 `features/live/ui/LivePage` 内部使用），其他路由不实例化。

### 6.7 服务端契约影响

为了让 URL-first + 路由感知订阅可行，以下点需要与后端确认；不可行则 spec 退化方案见 §11 风险表。

1. **WS `subscribe` 帧的替换语义**：需要后端支持 "后续 `subscribe` 帧覆盖 `market_targets` 集合"（或新加 `subscribe.update`）。若不支持，退化为"路由切换重连"。
2. **`/api/bootstrap` 中 `ws_token`**：本 spec 不改服务端；只改前端把 token 从 store 移到 client closure。
3. **`/api/search/inspect` 支持 `target_type` + `target_id` 直查**：从 token-radar 跳过来时避免再走 resolver。**待确认**，不支持时不强求。
4. 公共 HTTP/WS 契约其它部分不动（满足 N1）。

## 7. 目标架构 · 测试金字塔

### 7.1 四层结构

```
        ▲
       ╱ ╲     L3 — Playwright 凝烟（关键用户路径）        5–7 条
      ╱   ╲    在 vite preview + MSW Service Worker 内
     ╱─────╲   stub HTTP / WS；只跑 chromium
    ╱       ╲
   ╱         ╲ L2 — RTL + MSW integration（每个 feature 一组）
  ╱           ╲ 跨 feature 协作（notification → route）走这里
 ╱─────────────╲
╱_______________╲ L1 — RTL component（单组件 + mocks）
                   L0 — Vitest pure unit（lib/ · shared/format · features/*/model · features/*/state）
```

| 层 | 工具 | 跑得 | 数量目标 |
|---|---|---|---|
| **L0** pure unit | Vitest（无 DOM） | `features/*/model` · `features/*/state` · `shared/format` · `lib/api/util` · `shared/query` keyFactory | 行覆盖 ≥ 80% on `model/` + `state/` |
| **L1** component | Vitest + jsdom + RTL | 单组件渲染、键鼠交互、a11y 角色（axe-core） | 每个 `features/*/ui/` 公共组件 ≥ 1 测 |
| **L2** integration | Vitest + jsdom + RTL + **MSW** + QueryClientProvider + MemoryRouter | route 入口 + MSW handler 模拟 `/api/*` + WS 帧 → 验证渲染 / 交互 / URL 变化 | 每条路由 ≥ 1 测；跨 feature ≥ 3 测 |
| **L3** e2e smoke | **Playwright (chromium)** + `vite preview` + MSW Service Worker | 真实浏览器跨页面流 | 5–7 条 |

### 7.2 `App.test.tsx` 解体映射

| 现状测试主题 | 落到 |
|---|---|
| `renders radar rows with mock-aligned semantic fields` 类 | L1 `features/live/ui/TokenRadarRow.test.tsx` |
| `patches visible token-radar rows with websocket market updates` | L2 `features/live/__tests__/marketUpdatePatch.integration.test.tsx` |
| `notification toast → navigate` | L2 `features/notifications/__tests__/notificationFlow.integration.test.tsx` |
| `hotkey 1–4 切换 window` | L1 `features/cockpit/ui/CockpitTopbar.hotkey.test.tsx` |
| `signal-lab 列表渲染 + 过滤` | L2 `features/signal-lab/__tests__/signalLabFilters.integration.test.tsx` |
| `bootstrap 失败 fallback` | L2 `app/__tests__/bootstrap.integration.test.tsx` |
| 冷加载首屏 → radar 行可见 → 进 token-target | L3 `e2e/golden-paths/live-to-token-target.spec.ts` |
| 冷加载首屏 → 顶栏 search 提交 → search intel | L3 `e2e/golden-paths/search-submit.spec.ts` |

`vite.config.ts` 的 `app-integration` project 删除；全部并入 `web-unit`。

### 7.3 MSW 落地

- `src/test/msw/handlers.ts` 集中定义 HTTP handler。
- `src/test/msw/wsServer.ts` 用 `msw` + `ws` 模拟服务端 push 帧。
- `src/test/setup.ts` 中 `beforeAll(() => server.listen())` / `afterAll(server.close())` / `afterEach(server.resetHandlers())`。
- 删除 `vi.mock("./api/client")` 与 `vi.mock("./api/useIntelSocket")` —— 测试断的是网络层而非模块边界。

### 7.4 Playwright 落地

- `web/playwright.config.ts`：projects 只 `{ name: "chromium", use: devices["Desktop Chrome"] }`。
- `web/e2e/golden-paths/*.spec.ts` 5–7 条。
- CI workflow 新增 `npm run test:e2e`（chromium only）。
- MSW 在浏览器端走 Service Worker（`msw/browser`）；spec 同步阶段确认 `vite preview` 静态托管下 service worker 能注册。

### 7.5 a11y 自动化

- L1 / L2 测试里加 `axe-core/react` 或 `jest-axe`：`expect(container).toHaveNoViolations()`，每个公共组件至少跑一次。
- ESLint `jsx-a11y/recommended` 全为 error（4.1 G16）。

## 8. 目标架构 · DX / Vite / TS / 契约

### 8.1 tsconfig.json

```jsonc
{
  "compilerOptions": {
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true,
    "verbatimModuleSyntax": true,
    "baseUrl": ".",
    "paths": {
      "@app/*":      ["src/app/*"],
      "@routes/*":   ["src/routes/*"],
      "@features/*": ["src/features/*"],
      "@shared/*":   ["src/shared/*"],
      "@lib/*":      ["src/lib/*"]
    }
  }
}
```

路径别名同步进 `vite.config.ts` 的 `resolve.alias`。

### 8.2 ErrorBoundary + Suspense

- `app/AppRoot.tsx` 包顶级 `ErrorBoundary`（onError → notification toast），fallback "前端崩溃 · 重载 · 复制堆栈"。
- 每个 `routes/*.route.tsx` 内层再包一次 `ErrorBoundary` + `<Suspense fallback={<RouteFallback/>}/>`。
- `RouteFallback` = `shared/ui/RemoteState.Loading layout="route"`，保留 layout 形状。

### 8.3 Route-level lazy（为边界服务，非追求 size）

```ts
const LiveRoute        = lazy(() => import("@routes/live.route"));
const SignalLabRoute   = lazy(() => import("@routes/signal-lab.route"));
const SearchRoute      = lazy(() => import("@routes/search.route"));
const StocksRoute      = lazy(() => import("@routes/stocks.route"));
const TokenTargetRoute = lazy(() => import("@routes/token-target.route"));
```

提供清晰的 Suspense / ErrorBoundary 边界与代码隔离；**不**为之设 chunk size budget（N6）。

### 8.4 Envvar 层

- `lib/env/env.ts`：用 zod-equivalent 校验（简单 fn 即可）解析 `import.meta.env`，输出 typed config（`apiBase` / `wsUrl` / `mode`）。
- `lib/api/client.ts` 从 typed config 拿 base URL；不再 `window.location.origin` 字面量。
- `.env.development` / `.env.production` 提交进库；`.env.local` gitignored。

### 8.5 OpenAPI 单一源

- `npm run generate:types` 在 `prebuild` + CI 上跑。
- `lib/types/openapi.ts` = `openapi-typescript` 输出。
- `lib/types/index.ts` = 业务别名 facade：**只允许 `export type Foo = OpenApiFoo`**，ESLint 守护（`no-restricted-imports` 禁止从 `@lib/types/openapi` 直接 import 到 features）。
- 删除 `web/src/api/types.ts` 1232 行（hard cut）。
- CI 跑 `git diff --exit-code lib/types/openapi.ts` 阻止"忘记跑 generate"。

### 8.6 Auth token 处理

- 从 `useTraderStore.token` 移除。
- `lib/api/client.ts` 内 `let _wsToken: string | null = null` closure；`bootstrap()` 拉到后 `setWsToken(token)` 注入。
- 组件不再感知 token 存在；`enabled: Boolean(token)` 这种逻辑在 feature hook 内部消化（通过等 bootstrap query resolve）。

### 8.7 ESLint 增项

```js
"plugin:jsx-a11y/recommended",                     // warn → error
"plugin:react-refresh/only-export-components",
"@typescript-eslint/no-explicit-any": "error",
"@typescript-eslint/no-non-null-assertion": "error",
"import/no-restricted-paths": /* §5.4 */,
"no-restricted-imports": /* §8.5 facade 守护 */,
```

## 9. 目标架构 · CSS / 设计体系 / a11y

### 9.1 `styles.css` 分解为三件套

| 文件 | 内容 |
|---|---|
| `styles/tokens.css` | `--color-*` `--space-*` `--radius-*` `--font-*` `--shadow-*` `--ease-*`。Tailwind v4 `@theme` directive 共享。 |
| `styles/base.css` | reset + html/body + 全局滚动条 + 字体加载。 |
| `styles/tailwind.css` | `@import "tailwindcss"` + `@theme { ... }` |

页面级 CSS **不再存在**。

### 9.2 组件 CSS 规则

- **优先 Tailwind utility**；`bg-surface-1 border border-line-2 rounded-lg p-4 grid gap-3` 直接写在 JSX。
- 当 utility 链 ≥ 6 个或语义重要（`watchlist-row`、`rail-button`、`pill-good`）→ 用 `@apply` 升格为语义 class，**就近放在组件同目录 `<Comp>.module.css`**（CSS Module，类型化）。
- 全杀字符串拼接 className（G15）。改 `clsx` + 联合类型 prop。

### 9.3 RemoteState 一致性

`shared/ui/RemoteState.tsx` 扩展为：

```tsx
<RemoteState.Loading layout="route|panel|inline" rows={n} label="..." />
<RemoteState.Empty title="..." hint="..." action={<button.../>} />
<RemoteState.Error error={e} onRetry={...} />
<RemoteState.Stale data={...} updating={true}>{children}</RemoteState.Stale>
```

所有现存"文本 loading"占位（`SignalLabPulse` / `TokenPostsPanel` / `PulseDetailPage` / `SearchIntelPage` 的 `"loading search intel"`）替换。

### 9.4 a11y

- 顶栏 status pill 补 `aria-live="polite"`。
- search input 加 `<label>`。
- 所有图标 icon-button 走 `<IconButton aria-label="...">` 原语，不允许裸 `<button>` 包 `<Icon/>` 而无 label。
- L1 测试通过 axe-core 校验。

### 9.5 性能

- N6：**不设 chunk gzip 预算 / 不接 bundle-analyzer CI / 不写 size assertion / 不做 `React.memo` 热点优化 / 不强制 `manualChunks` vendor 拆分**。
- 路由级 `lazy()`（§8.3）保留，理由是边界与代码隔离。
- 自然的 Vite 默认行为不阻塞；优化日后单独 spec。

## 10. Phase 拆分（4 个 hard cut，按顺序）

每个 phase = 一个 PR + 一组验收 + 一次手测。phase 之间**不允许部分落地**；要么整 phase 进 main，要么整个 phase 回退。

### 10.1 Phase A — DX & 契约脚手架（基础地基）

**改什么**：
- tsconfig 严格化（`noUncheckedIndexedAccess` / `exactOptionalPropertyTypes` / `verbatimModuleSyntax`）+ path alias（`@app/* @routes/* @features/* @shared/* @lib/*`）；vite.config 同步 alias。
- vite.config envvar 层（`lib/env/`）。
- `lib/api/`（搬现 `api/client.ts`）+ `lib/types/`（openapi.ts generated + index.ts facade）落地；**全局替换** `import ... from ".../api/types"` → `from "@lib/types"`；删除 `web/src/api/types.ts`。
- `app/AppRoot.tsx` + `app/AppRoutes.tsx` + `routes/*.route.tsx` 文件落地，route-level `lazy()` + `ErrorBoundary` + `Suspense`（路由文件内仍 import 旧 `components/*`，不挪逻辑代码）。
- ESLint 增项：`react-refresh/only-export-components` 启用；`jsx-a11y/recommended` 接入但保留 **warn 级**（D 期才升 error）；`import/no-restricted-paths` 启用 lib + shared zone，features 间 zone **暂不收紧**（B 期才启用）。

**不动什么**：CSS、组件目录（`components/` 还在）、Zustand、测试套件结构。

**验收 A**：
- A1. `npm run build` 通过；`npm run typecheck` 在 `noUncheckedIndexedAccess` / `exactOptionalPropertyTypes` 下 0 报错。
- A2. 任一 route 抛错只崩该 route，不崩整页（手测：在 SignalLabPage 内 throw 一个 Error，验证其他 route 仍可用）。
- A3. `lib/types/openapi.ts` 与 `docs/generated/openapi.json` 在 CI `git diff --exit-code` 一致。
- A4. `web/src/api/types.ts` 不存在；`grep -rn 'from ".*api/types"' src` 输出为空；所有源文件通过 `@lib/types` 取类型。
- A5. `npm run lint --max-warnings=0` 通过（含 react-refresh / jsx-a11y warn 级 / import/no-restricted-paths lib + shared zone）。
- A6. 所有现有测试仍绿。

### 10.2 Phase B — 架构 + 状态所有权（最重）

**改什么**：
- 目录大搬：`components/` 解散到 `features/<f>/ui/`；`features/` 子目录补齐 `api/ model/ state/ ui/ index.ts`。
- `useTraderStore` 18 字段 → ≤ 8 字段（§6.1）。新增 `features/live/state/liveSelectionSlice.ts`、`features/signal-lab/state/...`。
- URL-first 落地：`window` / `scope` / `handles` / `search` / `radarSortMode` 进 URL；`/?window=1h&scope=all&handles=toly,ansem&sort=heat` 冷加载可复现。`useTraderStore` 15 → 9 字段（按 §6.1）。
- `TokenTargetPage` 内 `useQuery + getApi` 替换为 `features/token-target/api/useTokenRadarRowQuery`。
- `CockpitLayout` 拆为 `CockpitShell + CockpitTopbar + CockpitSideRail + CockpitMobileNav`，每个 ≤ 10 props。
- `SearchShell` 独立 outlet；删 layout 内 `isSearch / isStocks` 分支。
- `shared/query/queryKeys.ts` + `patchMarketUpdate` 落地，所有 useQuery key 收敛。
- `shared/socket/IntelSocketProvider` + `useMarketSubscription` 落地；路由切换释放订阅。
- 删除 signal-lab redirect-on-empty / token-target fake-flow-item 等兼容代码。
- `auth.token` 退出 store，进 `lib/api/client.ts` closure。

**不动什么**：测试金字塔结构（B 期里测试 case 会跟着改但不引入 MSW —— 把 `vi.mock` 改成指向新模块路径即可）。CSS。

**writing-plans 阶段拆分**：B 体量过大，在 plan 文档中拆为 B1–B5 sub-PR 序列（同一 feature 分支顺序合并，最终一次进 main）：
- B1：目录大搬（结构 + 把现有组件搬过去，不改逻辑）
- B2：URL-first（store 缩水 + URL 序列化 + features/*/state/ 落地）
- B3：CockpitLayout 拆分 + SearchShell 独立
- B4：`TokenTargetPage` 去 getApi + queryKeys 收敛
- B5：WebSocket 单例 + 路由感知订阅 + cache patch 通道

**验收 B**：
- B1. `useTraderStore` 字段 ≤ 10 且不含 `token` / `window` / `scope` / `handles` / `search` / `radarSortMode`。
- B2. `grep -rn "getApi\|postApi\|setQueryData" src/features/*/ui src/features/*/state src/features/*/model src/routes src/shared/ui` 输出为空。
- B3. `grep -rn "useQuery\|useMutation\|useInfiniteQuery" src/features/*/ui src/features/*/state src/features/*/model src/routes` 输出为空（这些 hook 只在 `features/*/api/` 出现）。
- B4. `web/src/components/` 目录不存在；`CockpitLayout.tsx` 文件不存在；其继任者 `CockpitShell` / `CockpitTopbar` / `CockpitSideRail` / `CockpitMobileNav` 每个 props ≤ 10。
- B5. 冷加载 `/?window=4h&scope=matched&handles=toly&sort=heat` 重现完整状态（手测 + L2 测试断言 URL → state → render）。
- B6. 路由从 `/` 切到 `/signal-lab` 后，socket 端订阅集合不再包含 token-radar 的 `market_targets`（DevTools socket inspector 手测 + L2 测试 spy `ws.send` 验证；后端若不支持替换语义则退化为 reconnect 后订阅集合正确）。
- B7. ESLint `import/no-restricted-paths` features 间 zone 启用且 0 报错。
- B8. 现有 App.test.tsx 测试 case 适配后全绿（暂未拆分；按新模块路径调整 mock）。
- B9. 手测：5 个路由冷加载 / 路由切换 / 关键交互（顶栏 search 提交 / 通知点击跳转 / radar 行点击进 token-target）全部正常。

### 10.3 Phase C — 测试金字塔重建

**改什么**：
- `App.test.tsx` 按 §7.2 表拆为 L1 / L2 / L3 分布。
- 接入 MSW：`src/test/msw/handlers.ts` + `wsServer.ts` + `setup.ts`。
- 接入 Playwright：`web/playwright.config.ts`（chromium only）+ `web/e2e/golden-paths/*.spec.ts` 5–7 条。
- `vite.config.ts` 删除 `app-integration` project。
- 接入 axe-core / `jest-axe`，在 L1 公共组件测试中跑 a11y。
- CI 新增 `npm run test:e2e`（chromium）。

**不动什么**：CSS / a11y eslint 严格度（D 期再收）。

**验收 C**：
- C1. `wc -l src/App.test.tsx` < 100，或文件删除。
- C2. `npm run test` 跑通且**不依赖** `vi.mock("./api/client")` 或 `vi.mock("./api/useIntelSocket")`（`grep -rn "vi.mock.*api/client\|vi.mock.*useIntelSocket" src` 空）。
- C3. `npm run test:e2e` 在 chromium 上绿。
- C4. 5 条 golden path 覆盖：冷加载首屏 / 顶栏 search → search intel / radar → token-target / signal-lab 列表过滤 / notification 跳转。
- C5. 每个 `features/*/ui/` 公共组件至少 1 个 L1 测试。
- C6. axe-core 在所有 L1 测试 0 violations。

### 10.4 Phase D — CSS + a11y 收尾

**改什么**：
- `styles.css` (5506) 拆为 `styles/{tokens,base,tailwind}.css`，page-specific class 改 Tailwind utility 或就近 CSS Module。
- 所有"文本 loading"占位替换为 `RemoteState.Loading`。
- `clsx` 替代字符串拼接 className。
- ESLint `jsx-a11y/*` 从 warn 升 error；补齐 aria-label / aria-live。
- 顶栏 status pill / icon-button / search input 加 aria-label。

**不动什么**：性能预算 / bundle size assertion / `React.memo` 优化（N6）。

**验收 D**：
- D1. `wc -l web/src/styles.css` = 0（文件删除）；`styles/{tokens,base,tailwind}.css` 三件套存在。
- D2. `grep -rn 'className={\`.*\${' src/` 输出为空（无字符串拼接 className）。
- D3. ESLint `jsx-a11y/*` 全为 error 等级且 0 报错。
- D4. axe-core 在 L1 + L2 测试 0 violations。
- D5. 手测：5 条路由视觉与 Phase C 末态一致（无明显回归）。
- D6. RemoteState 统一：`grep -rnE '"loading[^"]*"|>loading<|loading\.\.\.' src/features src/routes` 不命中文本 loading 字面量；所有 loading / empty / error 状态都通过 `<RemoteState.*>` 渲染（人工 review L1 测试快照）。

## 11. 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Phase B 体量过大，单 PR review 困难 | 高 | writing-plans 阶段拆为 B1–B5 sub-PR 序列；同 feature 分支顺序合并，最终一次进 main。 |
| WS `subscribe` 替换语义后端不支持（§6.7 #1） | 高 | spec 同步阶段写信问后端 owner；不支持则 Phase B5 引入"路由切换重连"降级实现，验收 B6 改为"重连后订阅集合正确"。 |
| MSW 在 jsdom + WS 模拟稳定性 | 中 | L2 WS 测试如果 jsdom 不稳，部分迁到 L3 Playwright + MSW Service Worker；不强求 jsdom WS。 |
| OpenAPI 业务别名 facade 失控（开发者偷偷加字段） | 中 | ESLint `no-restricted-imports` + `lib/types/index.ts` review checklist：只允许 `export type X = OpenApiX`。 |
| Tailwind v4 工具链稳定性（v4 刚 GA） | 中 | Phase D 单独 PR，回退路径明确（保留 v3 fallback config）。 |
| Playwright MSW Service Worker 在 `vite preview` 注册失败 | 中 | Phase C 早期 spike：先验证 service worker 注册可行；不可行则把 e2e 切换到 mock 服务器子进程（`msw/node` + Express）。 |
| 拆 styles.css 时丢失视觉细节 | 中 | Phase D 前先拍 5 条路由的 screenshot 作为基线，PR 截图对比；未来项接 Playwright visual regression。 |
| Zustand store 缩水破坏未审计的组件 | 中 | Phase B2 grep `useTraderStore.*\.(window\|scope\|handles\|search\|token\|radarSortMode)` 找出所有消费点；逐一迁。 |
| App.test.tsx 拆解过程中漏断言 | 中 | Phase C 前建 case 矩阵（现状 ~50+ test cases）；review 时核对每条对应到 L1/L2/L3 文件路径。 |

## 12. 替代方案（被否决）

- **单 hard cut（一次全干）**：用户选 phased（且 Phase B 已经够重）。
- **保留 `components/` 大目录，只内部清洗**：不解决"无所有权"。
- **Suspense + RSC + Next.js**：违反 N3；当前是纯 SPA 单容器，迁移成本远超收益。
- **保留 zustand-persist 全量**：违反"URL 是分享语义的唯一所有者"原则。
- **直接接 OpenAPI 不留 facade**：facade 让"业务术语"与后端命名解耦，零成本，留着。
- **手写 types 保留为 single source**：drift 问题不可控；放弃。
- **Playwright 跨 chromium + firefox + webkit**：CI 成本与维护成本高，N7 否决。
- **加 bundle size budget / `React.memo` 热点优化**：N6 否决（不追求速度）。

## 13. 边界总表

| 类 | 行为 |
|---|---|
| Always | 依赖单向 `lib → shared → features → routes → app`，ESLint 守护。 |
| Always | URL 是导航 + 可分享过滤的唯一所有者。 |
| Always | RQ 是 server state 的唯一所有者，WS 通过 `setQueryData` 入 cache。 |
| Always | WebSocket 订阅是路由感知 + 引用计数的。 |
| Always | Query keys 在 `shared/query/queryKeys.ts` 集中。 |
| Always | API 类型来自 `openapi-typescript` 单一源。 |
| Always | 每个 Phase = 一个 hard cut，phase 间禁止 dual-write。 |
| Always | RemoteState 在所有 loading / empty / error / stale 场景统一使用。 |
| Ask first | 把任何字段从 Zustand 拿出来或新增 Zustand 字段（B 之后）。 |
| Ask first | 改路由路径 / 改 URL 参数语义 / 引入新依赖（UI kit / state lib / animation lib）。 |
| Ask first | 拆 styles.css 时如发现视觉无法 1:1 复现。 |
| Never | 跨 feature 深 import（除 `index.ts`）。 |
| Never | 组件直接调 `getApi` / `setQueryData`。 |
| Never | Zustand 镜像 URL 字段。 |
| Never | layout 内通过 `location.pathname.startsWith()` 决定子组件可见性。 |
| Never | `className={\`...${cond ? "x" : ""}...\`}` 字符串拼接。 |
| Never | 静默 redirect（如 signal-lab 自动跳详情、token-target 假数据填充）。 |
| Never | `--no-verify` 跳 pre-commit / `--no-edit` 跳 commit hook。 |
| Never | 为追求 bundle size / 速度引入 React.memo / manualChunks / size assertion（N6）。 |

## 14. 演进路径（本 spec 之外）

- React 19 compiler（rolling out）
- Playwright visual regression
- 路由级 prefetch（mouseenter 预加载相邻 route 的 lazy chunk）
- Storybook（如设计体系长大）
- Sentry / OpenTelemetry browser SDK
- Bundle size budget（如未来出现真实性能问题）

## 15. 决议日志（brainstorming 阶段）

| 决议 | 选择 | 理由 |
|---|---|---|
| spec 形态 | 审计 + 目标架构 spec | 后续直接进 writing-plans 写 4 个 plan |
| 审计集群 | 4 项全选（架构 / 测试 / DX / CSS） | 都要进验收 |
| 营造路线 | 单 spec + 阶梯式 hard cut（4 phase） | 单 PR 太重 |
| CSS 路线 | Tailwind utility 优先 + design tokens | Tailwind v4 已装；社区主流 |
| e2e 路线 | Playwright 凝烟 + 关键路径 | jsdom 不够；只跑 chromium |
| API 类型 | openapi-typescript 单一源 + facade | 消除双源真相 |
| 状态拓扑 | URL-first | 冷加载完整可复现 |
| 性能 | N6 不追求 | 用户明确不要 |
| Playwright 浏览器 | 只 chromium | 不跨 firefox / webkit |
| Phase B 拆分 | writing-plans 阶段拆 B1–B5 sub-PR | 单 phase PR 太重 |
