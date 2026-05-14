# Spec — Token Case Redesign

**Status**: In Progress
**Date**: 2026-05-14
**Branch**: `main`
**Related**:
- `docs/superpowers/specs/active/2026-05-13-obsidian-desk-ui-hard-cut-cn.md` (G3 Selected Case)
- `docs/superpowers/specs/active/2026-05-14-token-intel-product-cleanup-cn.md` (Search Intel token_result)
- `docs/superpowers/specs/active/2026-05-14-watchlist-handle-intel-cn.md` (同套 case-file grammar)
- `docs/generated/token-case-redesign-ui-mockup.html`(用 HANSA 真实数据渲染的视觉基线)

## 一句话

把 token 二级页 `/token/:targetType/:targetId` 和 Search Intel `token_result` 收拢成单一共享组件 `TokenCasePanel`，由新端点 `GET /api/token-case` 一口气下发 dossier；narrative-first 摆放，9 个 section 全部对齐 Obsidian Desk case-file grammar，与 watchlist-handle-intel/PulseDetail 同视角同密度。

## 背景

当前 `/token/:targetType/:targetId`（`web/src/features/token-target/ui/TokenTargetPage.tsx`）和 `/search` 的 `token_result`（`SearchTokenIntelPage.tsx`）是两个独立组件，承载几乎相同的内容（identity / market / social / decision），但用了不同的布局、不同的字段集合、不同的视觉密度。User-facing 后果：

1. **TokenTargetPage 没有信息密度。** 只有 4 段：score header、social+market 双 chart、posts panel、score ledger。Hero 仅展示 title + window picker + back，identity/profile/links/CA 都没上场；market 即使有数据也不分 anchor/latest/live；narrative thesis、key amplifiers、data gaps 完全缺席。
2. **数据路径脆弱。** 页面调 `/api/token-radar?limit=48` 然后线性扫描找 target；token 一旦掉出 top-48 就走 degraded 路径，hero 退化成 raw target_id URI 字符串，没有重试，没有 scope 扩大入口。
3. **视觉与其他页脱节。** 没用 CSS Modules，没用 case-file primitives（`ObsidianCase` 系列），chart 颜色硬编码，CN/EN 混排，无 i18n 边界；同期的 PulseDetailView/Watchlist mockup 已经稳定在 case-file grammar，token detail 是唯一一块 outlier。
4. **两份近重复实现。** `SearchTokenIntelPage` 在 search 路径下做了一版相似的 dossier 布局（`search-content-grid` + `search-primary-stack` + `search-insight-stack`）；维护两套等于持续制造不一致。

`obsidian-desk-ui-hard-cut` G3 明确把 selected token 归入 case-file 模板；`token-intel-product-cleanup` 已经规定了 Search Intel token_result 的 3 层结构。本 spec 的工作是把"radar 二级页"也并入同一个 case-file，并把 dossier 做厚到与其他 detail 页一致。

## 第一性原则

每一块 UI 都要能用一句话回答交易员的一个问题。问不出来就删。

| 问题 | UI 元素 | 数据源 |
|---|---|---|
| 这是哪个 token？ | logo / `$SYMBOL` + name / chain / CA / official links | `asset_profiles` + `asset_identity_current` |
| 数据有多新？ | window / scope / last update / data health | request params + `agent_brief.data_gaps` |
| 信号面在哪？ | mentions / authors / watched / top-share / phase | `timeline.summary` + `agent_brief.propagation` |
| 谁在推？故事是什么？ | 3 个 propagation phase 卡（seed/ignition/expansion） + lead account | `timeline.stages` + `agent_brief.propagation.phases` |
| 证据是什么？ | post timeline，按 catalyst 排序，每条带 phase 色条 + PQ 分 + 收原文 | `posts.items` + `post_quality.contributions` |
| 现在该不该看？ | bull thesis（含触发条件）+ bear thesis（含失效条件） | `agent_brief.bull_bear` |
| 是谁在传播？ | 关键放大账号列表 + 角色（seed / amplifier / scanner） | `agent_brief.propagation.key_accounts` |
| 市场对得上吗？ | live market snapshot（price / mcap / liq / holders）+ readiness 占位 | `LivePriceGateway` snapshot + WS `live_market_update` |
| 缺什么？ | 缺口清单（OHLC / holders / profile / contract risk） | `agent_brief.data_gaps` |

Narrative-first：identity → propagation summary → narrative timeline → posts。市场、bull/bear、放大账号、缺口都收在右栏。决策不抢头条；要决策建议时去 Pulse Detail。

## Goals

- **G1 单一 TokenCasePanel。** `web/src/shared/ui/case-file/TokenCasePanel.tsx` 是共享纯展示组件，接 `TokenCaseViewModel` props，不 fetch。`/token/:targetType/:targetId` 与 `/search` token_result 走同一个组件，差异只在 ViewModel 来源。
- **G2 单一后端 dossier 端点。** `GET /api/token-case?target_type=X&target_id=Y&window=W&scope=S&posts_limit=N` 返回 dossier，shape 镜像 `search/inspect.data.token_result`，复用相同的 repository/service 层。
- **G3 9 个 section，对齐 case-file grammar。** Hero、Metric Strip、Propagation Summary、Mention Timeline、Live Market、Bull、Bear、Key Amplifiers、Data Gaps。视觉密度对齐 `docs/generated/token-case-redesign-ui-mockup.html`。
- **G4 删旧件。** `TokenTargetPage`、`TokenTargetCaseSummary`、`TokenSocialMarketTimeline`、`TokenPostsPanel`、`ScoreLedger`、`SearchTokenIntelPage` 的旧 body 全删；`SearchIntelSidebar`、`search-content-grid` 的旧两栏布局让位给 TokenCasePanel。
- **G5 真实数据为锚。** 视觉、字段、缺口、空状态都以 `asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump`（HANSA）作为实拉 fixture，确保 narrative-thin、market-pending、no-pulse 这些常见状态都不渲染空白。
- **G6 一刀切 PR。** 一个 PR 内完成后端端点 + TokenCasePanel + 两个 route 接入 + 删旧件 + 测试，对齐项目 hard-cut 习惯，避免 dual-write/feature-flag 带来的临时不一致。

## Non-Goals

- 不动 `factor_snapshot_json` v3 schema 与 score 计算。
- 不重新生成 `agent_brief`；本 spec 只消费 `agent_brief.project_summary / propagation / bull_bear / data_gaps`。
- 不接入 Pulse 决策（HANSA 没有 candidate；当 `pulse_candidates` 存在时由后续 spec 决定是否在 TokenCasePanel 暴露 trade route，不在本次范围）。
- 不绘 OHLC 蜡烛。`MarketCandlesService` 现在只在 `search/inspect` 内部 enrich；TokenCasePanel 的 Live Market 只渲染 snapshot + readiness 占位。OHLC 等独立 spec。
- 不动 `/api/target-posts` 的 cursor 协议；它继续承接 load-more 翻页。
- 不动 WS `live_market_update` 通道；TokenCasePanel 用现有 `useMarketSubscription` 订阅。
- 不动 Radar 列表页（已有 token-intel-product-cleanup spec）。

## Product Design

视觉基线见 `docs/generated/token-case-redesign-ui-mockup.html`，用 HANSA 实拉数据渲染。

### 页面布局（desktop ≥1180px）

```
+---------------------------------------------------------------+
| HERO  (56px logo · symbol+name · CA · window/scope · actions) |
+---------------------------------------------------------------+
| METRIC STRIP  4 cards: mentions · phase · watched · readiness |
+---------------------------------------------------------------+
| PROPAGATION SUMMARY  meta+pills(0.72fr) | 3 phase cards(1.28fr)|
+---------------------------------------------------------------+
| WORKSPACE                                                     |
| +--- TIMELINE (1.46fr) ----+--- SIDE RAIL (0.54fr) ---------+|
| | toolbar [Catalyst|Recent | Live Market (snapshot/empty)   ||
| |          |Watched]       | Bull thesis (health-tone card) ||
| | posts events (phase bar  | Bear thesis (risk-tone card)   ||
| |   on left, PQ pills,     | Key Amplifiers (cluster list)  ||
| |   <details> for original)| Data Gaps (risk-tone list)     ||
| | Load more posts          |                                ||
| +-------------------------+----------------------------------+|
+---------------------------------------------------------------+
```

### Section 内容契约

| Section | 字段 | 数据源 |
|---|---|---|
| Hero | logo（`profile.identity.logo_url` 或 fallback mono mark）；`$SYMBOL` + name；chain + `code(CA)`；actions: Search Intel(primary)、GMGN、GeckoTerminal、X live；controls: window 4-way、scope 2-way | `target` + `profile` |
| Metric Strip · 1 | mentions: `summary.posts`；副文 `effective_authors`、`top_author_share` | `timeline.summary` |
| Metric Strip · 2 | phase: `summary.phase`（tone=health 当 expansion/escalation）；副文 phase confidence | `timeline.summary` + `timeline.stages` |
| Metric Strip · 3 | watched: `summary.watched_posts / authors`；tone=risk 当 0 | `timeline.summary` |
| Metric Strip · 4 | readiness: market readiness（pending / partial / ready）；副文 data gaps 数 | `market_live.status` + `data_gaps.length` |
| Propagation Summary | left: `project_summary.summary_zh` + status pills；right: 3 stage cards（seed/ignition/expansion），每卡显示 phase 名 + count + lead account + `read_zh` | `agent_brief.project_summary` + `agent_brief.propagation.phases` + `timeline.stages` |
| Mention Timeline | toolbar: 3-tab sort（Catalyst / Recent / Watched）；每个 post 一行 event：左侧 72px 时间 gutter；event card 左边 3px phase 色条；top pills（PQ 分 / CA evidence / attribution / scanner pattern / duplicate caller …）；title = `text` 截断；`<details>` 展开原文 + `post_quality.contributions` 三行分解 | `posts.items` + `posts.has_more` + `posts.next_cursor` |
| Live Market | 当 `market_live.status='ready'`：渲染 price/mcap/liq/holders + `observed_at_ms` + provider；status≠ready 时渲染 `empty-market` 卡（dashed border, mono labels），明文说明 pricefeed_id 路由、WS 订阅、OHLC 状态 | `LivePriceGateway` snapshot + WS `live_market_update` |
| Bull Thesis | tone-health card：标题 `Bull · 多头` + stance pill；`thesis_zh` 正文；触发条件列表（`triggers_zh`） | `agent_brief.bull_bear.bull` |
| Bear Thesis | tone-risk card：标题 `Bear · 空头` + stance pill；`thesis_zh` 正文；失效条件列表（`invalidations_zh`） | `agent_brief.bull_bear.bear` |
| Key Amplifiers | cluster list：每行 `@handle` · role（seed lead / ignition lead / expansion lead / amplifier / scanner）· posts 数 + 首次出现相对时间 | `agent_brief.propagation.key_accounts` |
| Data Gaps | risk-tone list：每条 ⚠ 引导，纯文本来自后端 `data_gaps` | `agent_brief.project_summary.data_gaps` |

### 状态与空态

| 情形 | 渲染 |
|---|---|
| `/api/token-case` 4xx/5xx | 整页 `RemoteState.Error`，retry 按钮 |
| target 无法解析（404 from dossier service） | `RemoteState.Empty`，文案 "未找到 token"，附返回 Radar / 打开 Search 入口 |
| `timeline.summary.posts === 0` | Metric Strip + Hero 仍渲染；Propagation Summary 与 Workspace 区合并成单卡空态 "本窗口无 mention 命中" + 扩 window/scope 建议 |
| `market_live.status !== 'ready'` | Live Market 渲染 dashed `empty-market` 卡（见 mockup），不静默隐藏 |
| `agent_brief` 缺 bull_bear（早期 token） | Bull/Bear 两卡缺省渲染 "尚无 bull/bear 评估" 提示卡（tone=neutral），保留布局 |
| `posts.items` 还在 loading | timeline 渲染 3 个 skeleton event row，保留 toolbar |
| 用户未登录 / 401 | 由顶层 `/login` 拦截，本组件不处理 |

### 移动端（≤820px）

- Hero：48px logo + title 双栏；actions 折到下一行左对齐。
- Metric Strip 4 卡纵向单列。
- Propagation Summary 上下堆叠：meta 在前，3 phase 卡纵向。
- Workspace 单列：timeline 在前，side rail 各 section 顺次堆叠。
- Posts event-row 取消 time gutter，时间挪到顶部 meta 行。

## Component Boundaries

### 共享 primitive · `web/src/shared/ui/case-file/`

新增（每个一个文件 + 同名 `.module.css`）：

- `TokenCasePanel.tsx` — 接 `TokenCaseViewModel` props，编排 9 个 section 的容器。
- `TokenCaseHero.tsx` — logo / symbol+name / CA / window-scope controls / actions。
- `TokenCaseMetricStrip.tsx` — 4 metric cards，支持 tone 参数。
- `TokenCasePropagationSummary.tsx` — left meta + right 3 phase cards。
- `TokenCaseTimeline.tsx` — toolbar + events 列表 + load-more；event row 内嵌 `TokenCasePostEventCard`。
- `TokenCasePostEventCard.tsx` — 单条 post（pills、title、quality breakdown、`<details>` 原文）。
- `TokenCaseMarketRail.tsx` — live market 卡（ready / empty 两态）。
- `TokenCaseBullBearRail.tsx` — bull/bear 双卡。
- `TokenCaseAmplifiersRail.tsx` — cluster list。
- `TokenCaseDataGapsRail.tsx` — risk-tone gaps list。

`TokenCaseViewModel` 类型定义放 `web/src/shared/model/tokenCaseViewModel.ts`（不是 fetch 层，纯类型）。

每个组件遵守 obsidian-desk 视觉规则：CSS Modules + Obsidian 色卡 + JetBrains Mono 标签 + IBM Plex Sans 正文 + 10px uppercase eyebrows。CSS class 前缀 `tcp-` 或 module-scoped。

### Feature adapter · `web/src/features/token-case/`

- `model/useTokenCase.ts` — `useQuery` 调 `GET /api/token-case`，依赖 `(target_type, target_id, window, scope)`。15s `staleTime`，与现有 radar 轮询节奏对齐。
- `model/useTokenCasePosts.ts` — `useInfiniteQuery` 调 `GET /api/target-posts`，cursor 翻页。dossier 已自带首页，hook 跳过首页 fetch（initialData / initialPageParam）。
- `model/buildTokenCaseViewModel.ts` — 接 dossier + posts pages + 用户 UI state（postSort、postRange、watchedOnly），输出 `TokenCaseViewModel`。
- `ui/TokenCaseRoute.tsx` — 给两条 route 都用的薄包装：`useParams` + `useSearchParams` + `useMarketSubscription([target])` + `<TokenCasePanel vm={vm} />`。

### Route 改造

- `web/src/routes/token-target.route.tsx` — 改为渲染 `TokenCaseRoute`；内部 `useTokenCase` 调 `/api/token-case` 拿 dossier，传给 `<TokenCasePanel vm={...}/>`。不再 import `TokenTargetPage`。
- `web/src/features/search/ui/SearchTokenIntelPage.tsx` — `token_result` 分支不再渲染 `search-content-grid`；改为直接用 `inspect.data.token_result`（在 SearchInspectService 改造后已经与 `TokenCaseDossier` 同 shape）调 `buildTokenCaseViewModel`，渲染 `<TokenCasePanel vm={...}/>`。**不**重复调 `/api/token-case`（避免一次 inspect + 一次 case dossier 两次走相同 service）。`ambiguous_result` 与 `topic_result` 分支不变。

### 删除清单

Frontend 一次删除：

- `web/src/features/token-target/` 整个目录（`TokenTargetPage.tsx` + `TokenTargetCaseSummary.tsx` + `tokenTarget.css` + 同名测试）
- `web/src/shared/ui/TokenSocialMarketTimeline.tsx`（含内联 chart）
- `web/src/shared/ui/TokenPostsPanel.tsx`（PostCard 一并删）
- `web/src/shared/ui/ScoreLedger.tsx`
- `web/src/features/search/ui/SearchIntelSidebar.tsx`（如仍存在）
- `web/src/features/search/ui/search-content-grid.css` 与 `search-primary-stack` / `search-insight-stack` 相关 class
- `web/src/shared/ui/TokenIntelHeader.tsx` 若被 token_result 唯一占用则一并删；如仍被其他页用则保留

Backend：无删除，新增端点 + service 方法。

## Data Flow

### 后端 dossier 端点

```
GET /api/token-case
Authorization: Bearer <ws_token>

Query:
  target_type: "Asset" | "CexToken"   (required)
  target_id:   string                 (required)
  window:      "5m" | "1h" | "4h" | "24h"   (default "1h")
  scope:       "all" | "watched"      (default "all")
  posts_limit: integer 1..50          (default 24)

Response:
  200 { ok: true, data: TokenCaseDossier }
  404 { ok: false, error: "target_not_found" }   when identity not resolvable
  401 { ok: false, error: "unauthorized" }
  400 { ok: false, error: "invalid_window" | "invalid_scope" | "invalid_target" }
```

`TokenCaseDossier` shape（对齐 `search/inspect.data.token_result` 一比一）：

```
{
  target: { target_type, target_id, symbol, chain_id, address, status, source, reason },
  profile: { status, provider, observed_at_ms, identity{ symbol, name, logo_url, banner_url, description },
             links{ website_url, twitter_url, twitter_username, telegram_url, gmgn_url, geckoterminal_url },
             source{ provider, raw_available, last_error } },
  timeline: { query, summary, market_overlay, stages[], buckets[], authors[] },
  posts:   { query, score_window, total_count, returned_count, has_more, next_cursor, items[] },
  agent_brief: { schema_version, generated_by, project_summary, propagation, bull_bear },
  market_live: LivePriceGatewaySnapshot   // 来自 /api/live-market 同款服务
}
```

实现复用：

- Service 入口 `TokenCaseService.dossier(target_type, target_id, window, scope, posts_limit)`。
- 内部组合：`AssetIdentityResolver.resolve(target_type, target_id)` → 失败抛 `TargetNotFound` → 404；成功后并行调 `TokenProfileReadModel.fetch`、`TokenTargetRepository.timeline_rows`、`TokenTargetRepository.posts_page`、`SearchAgentBriefBuilder.build`、`LivePriceGateway.snapshot`。
- 不调用 `MarketCandlesService.enrich_overlay`（OHLC 不在 dossier 内）。
- 缓存策略：和 `search/inspect` 一致，不加额外 cache 层；服务层异步并发。

`SearchInspectService` 内部 `token_result` 分支由 `TokenCaseService.dossier` 复用：把 `token_result` 改为调 `TokenCaseService.dossier(...)` 加 `market_overlay` enrich，避免两条代码路径。

### 前端数据流

```
RouteEntry
  └─ TokenCaseRoute (token-target.route.tsx OR SearchTokenIntelPage)
       useParams + useSearchParams ─┐
                                    │
       useTokenCase ──── GET /api/token-case (dossier first page)
       useTokenCasePosts ── GET /api/target-posts (cursor pages 2+)
       useMarketSubscription ── WS live_market_update
                                    │
       buildTokenCaseViewModel ←────┘
                                    │
       <TokenCasePanel vm={vm} />
```

WS 更新：`useMarketSubscription([target])` 收到 `live_market_update` 后写入 react-query cache 的 `market_live` 字段；TokenCasePanel 的 Live Market 自动重渲染。

## Acceptance Criteria

- **AC1 共享组件**：`/token/:targetType/:targetId` 与 `/search?q=<resolved-token>` 两个 URL 在浏览器中渲染的 token 详情视觉结构、CSS class 命名、section 顺序完全一致，仅 query/route 来源不同。
- **AC2 dossier 端点**：`GET /api/token-case?target_type=Asset&target_id=asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump&window=24h&scope=all` 在本地实拉返回 200，包含 9 个 section 所需的全部字段，且与 `search/inspect.data.token_result` 一致。
- **AC3 narrative-first**：Hero 之后第一个内容 section 是 Propagation Summary（不是市场 / 不是决策）；narrative_thesis 文本不被截断。
- **AC4 缺数据不空白**：当 `market_live.status !== 'ready'`，Live Market 渲染 dashed empty-market 卡，明文写 pricefeed_id 状态 + WS 订阅状态 + OHLC empty。
- **AC5 删除完成**：仓库中不存在 `TokenTargetPage.tsx`、`TokenTargetCaseSummary.tsx`、`TokenSocialMarketTimeline.tsx`、`TokenPostsPanel.tsx`、`ScoreLedger.tsx`、`SearchIntelSidebar.tsx`；`SearchTokenIntelPage.tsx` 不再渲染 `search-content-grid`。
- **AC6 视觉对齐**：TokenCasePanel 用 IBM Plex Sans / JetBrains Mono / Obsidian 色卡；与 `docs/generated/watchlist-handle-intel-ui-mockup.html` 及 `docs/generated/token-case-redesign-ui-mockup.html` 对照像素级一致（spacing / border / 色调 token）。
- **AC7 移动端**：≤820px 视口下页面无横滑，9 个 section 全部可访问；Hero actions 折行不破布局。
- **AC8 不在 Radar 也能开**：当 token 不在任何 `token_radar_rows` 行内时，`/token/:targetType/:targetId` 仍正常加载 dossier；旧 degraded path（"Not in current radar window"）不再存在。
- **AC9 测试通过**：lint / typecheck / pytest（含新加 integration test）/ Vitest / web build 全绿；Docker 镜像可重建。
- **AC10 浏览器 QA**：hard-reload `/token/Asset/asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump?window=1h&scope=all`、`/token/Asset/<same>?window=24h&scope=watched`、`/search?q=HANSA` 三条路径均渲染 TokenCasePanel；无 console error；market 占位卡正确显示。

## Test Plan

### Backend integration

`tests/integration/test_token_case_http.py`（新文件，hit 真 PG，禁止 mock）：

- `test_token_case_returns_dossier_for_resolved_asset` — 用现有 fixture（HANSA 或同等 resolved asset）请求端点，断言 9 大 section 字段齐全。
- `test_token_case_returns_404_when_target_not_resolvable` — 用未注册 CA 请求，断言 404 `target_not_found`。
- `test_token_case_requires_auth` — 无 Authorization 时返回 401。
- `test_token_case_invalid_window` / `invalid_scope` — 400。
- `test_token_case_reuses_search_inspect_shape` — 同 target 调 `/api/search/inspect` 与 `/api/token-case`，断言 `data.token_result === data`（除 `market_overlay` 字段差异）。

### Frontend unit (Vitest + RTL)

- `web/src/shared/ui/case-file/__tests__/TokenCasePanel.test.tsx` — 接固定 ViewModel fixture，断言 9 个 section 全部渲染、phase 色条按 `data-phase` 正确着色、PQ pill 显示分值、`<details>` 默认收起。
- `web/src/shared/ui/case-file/__tests__/TokenCaseMarketRail.test.tsx` — 三态：`status=ready` 渲染 price block；`status=missing` 渲染 dashed empty 卡；`status=pending_observation` 渲染 anchor-only。
- `web/src/shared/ui/case-file/__tests__/TokenCaseBullBearRail.test.tsx` — 有 bull_bear 渲染双卡；缺 bull_bear 渲染 neutral 占位。
- `web/src/features/token-case/__tests__/buildTokenCaseViewModel.test.ts` — 输入 dossier + posts pages，断言映射正确：缺字段补 null、phase tone 推断、watched 计数。

### Frontend integration

- `web/src/features/token-case/__tests__/TokenCaseRoute.routing.test.tsx` — mock fetch；`/token/Asset/...` 与 `/search?q=...` 都挂同一个 panel。
- `web/src/test/obsidianArchitectureCleanout.test.ts` — 加规则：不允许 `import` `TokenTargetPage` / `TokenSocialMarketTimeline` / `TokenPostsPanel` / `ScoreLedger`（已删）。

### E2E（手动 + 半自动）

- Playwright MCP 加载 mockup target 三条 URL，截图归档到 `docs/generated/token-case-redesign-*.png`。

## Risks

| Risk | Mitigation |
|---|---|
| 与 `search/inspect` 重复逻辑漂移 | `SearchInspectService.token_result` 改为内部调 `TokenCaseService.dossier`，单一真源；integration test 断言两端 shape 一致。 |
| HANSA fixture 一段时间后数据变化 / radar 状态漂移 | 测试使用 fixture-frozen data；mockup HTML 已快照存于 `docs/generated/`。新加 integration test 不依赖具体 token，用 fixture builder。 |
| `agent_brief` 在新 token 上可能为空（无 bull_bear / 无 phases） | 每个 section 设计为可降级；TokenCasePanel 不假定字段存在。组件 unit test 强制覆盖空字段 case。 |
| 删除 `ScoreLedger` 后用户失去 factor 透视 | factor 数据在 PulseDetailView 的 PulseAgentRail 仍存在（pulse_candidate 路径）；纯打分透视移到 Pulse Detail 不在 token detail 重做。 |
| Live market WS 与 react-query cache 不同步 | `useMarketSubscription` 收到事件后 `queryClient.setQueryData` 写 dossier 的 `market_live` 子字段；写完 trigger 自然重渲染。 |
| 单 PR 改动量较大（hard cut） | 子组件全部 CSS Modules + 单一 ViewModel adapter，diff 局部化；测试先行，避免回滚成本。 |

## Implementation Notes

按 TDD 顺序：

1. 写 backend integration test（先红）。
2. 实现 `TokenCaseService.dossier` + `/api/token-case` 端点。
3. 改造 `SearchInspectService.token_result` 调 `TokenCaseService.dossier`。
4. 后端测试转绿。
5. 写 `TokenCasePanel` 单元测试（先红）。
6. 落各 sub-component + CSS Modules。
7. 写 `buildTokenCaseViewModel` 单元测试。
8. 实现 hook 层（`useTokenCase` / `useTokenCasePosts` / `useMarketSubscription` 接入）。
9. 改 `web/src/routes/token-target.route.tsx` 与 `SearchTokenIntelPage.tsx` 接入。
10. 删除清单中的所有旧文件（一次性）。
11. 运行 lint / typecheck / vitest / pytest / build。
12. 浏览器 QA + 截图。
13. 更新 `docs/FRONTEND.md` 的 route 描述与 `docs/CONTRACTS.md` 的 API 表。

CSS Modules 命名遵守 PulseDetail 的做法：每个 sub-component 一个同名 `.module.css`；不写全局 selector；颜色一律用 `var(--*)` 引用 `tokens.css`。

不引入新依赖。`react-query`、`lightweight-charts`、`lucide-react` 都已存在；本 spec 不需要 lightweight-charts（OHLC 不在范围）。
