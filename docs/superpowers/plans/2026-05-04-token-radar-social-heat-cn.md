# Token Radar 社交热度彻底重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Token Radar 从“token mention 排行榜”重构成交易员可用的“社交热度突增、讨论质量、传播路径、交易时机”系统。

**Architecture:** 这次是破坏式重构，不保留旧 API/UI 兼容字段。后端把 social heat、discussion quality、propagation、timing、tradeability、opportunity 拆成独立可解释模块；前端重做 Token Radar 表格和 token detail drawer；LLM 只做 watched-event 中文叙事和异步质量增强，不进入实时 token fact/ranking 主路径。

**Tech Stack:** Python 3.12, FastAPI, SQLite WAL/FTS5, pytest, ruff, React 19, TanStack Query, TypeScript, Vitest, Vite.

## 落地状态

截至 2026-05-04，本计划已进入实现完成和验证阶段：

- 右侧 `TokenDetailDrawer` 保留，空状态为 `Select Token`，选中 token 后默认进入 `Timeline`。
- `实时信号 Tape` 作为中间底部全局组件保留，不被 timeline 替代，也不藏进 drawer。
- `/api/token-flow` 运行时只输出新 semantic blocks：`social_heat`、`discussion_quality`、`propagation`、`tradeability`、`timing`、`opportunity`、`posts_query`、`timeline_query`。
- `/api/token-posts` 负责全量帖子分页，`/api/token-social-timeline` 负责 bucket、authors、posts 和传播 summary。
- 中文叙事 contract 已落地，运行时缺中文 display 会显示 `narrative_display_missing`；旧库不做兼容迁移，应用 schema 不匹配时清空应用表并从 0 重建。
- `account-quality` foundation 已落地，用于后续筛选高质量账号，不进入实时 ranking 主路径。
- 静态 mockup 在较窄 in-app browser 宽度下不再隐藏详情 drawer，而是降级为主区域下方全宽详情面板。

验证命令：

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm run typecheck && npm test -- --run && npm run build
```

---

## 一、中文总结

现在的系统底层方向是对的：事件先入库，确定性抽实体，token attribution 把 `$SYMBOL` 和 CA 拆开，rolling window 计算 5m/1h/24h 热度，market snapshots 提供稀疏价格和市值，diffusion health 初步识别作者集中和重复文本，`/api/token-posts` 已经能翻全量 token 帖子。

真正的问题不是“缺一个更大的分数”，而是产品语义没有拆干净。交易员要看的不是 mentions 数量，而是：

- 这个币的讨论是否相对自身历史和全局 stream **异常升温**；
- 这些帖子是否是 **高质量讨论**，还是复制、喊单、符号歧义；
- 热度是否从单点广播变成 **独立作者扩散**；
- 价格是否已经先涨完，还是社交热度仍可能领先价格；
- 这个 token 是否有确定 CA、可交易市场数据、足够新鲜的快照；
- 为什么系统给出 driver/watch/discard，风险上限是什么。

因此重构目标是：把 Token Radar 变成一个社交传播雷达，而不是热词榜。

## 二、核心原则

### 1. 事实和判断分离

事实只来自持久化证据：

- `events`
- `event_entities`
- `event_token_mentions`
- `event_token_attributions`
- `tokens`
- `token_market_snapshots`
- `narrative_seeds`
- `narrative_token_links`

判断来自纯函数 scoring modules。每个 score 必须返回：

```json
{
  "score": 82,
  "score_version": "social_heat_v1",
  "reasons": ["z_score_above_3"],
  "risks": ["public_stream_coverage"],
  "contributions": [
    {"feature": "heat.z_score", "value": 25, "reason": "z_score_above_3"}
  ],
  "risk_caps": [
    {"risk": "author_concentration_high", "cap": 65}
  ]
}
```

### 2. 不保留兼容代码

本计划刻意破坏旧接口语义：

- 删除 `/api/token-flow` 返回里的旧 `signal` block。
- 删除 token flow 里的 `evidence_highlights` 和 `evidence_highlight_best`，避免把抽样 evidence 误认为全量证据。
- 删除前端对旧 `signal.decision` 的默认 fallback。
- 删除前端 `TokenEvidenceHighlight` 类型。
- 旧 UI 表头、旧 EV/confidence/narrative 语义全部移除。
- 叙事 UI 不再直接显示 snake_case `narrative_label`，机器 label 只作为隐藏稳定 key；交易员看到中文标题、中文摘要和中文市场解释。

数据库不迁移旧数据，也不写“如果新字段没有就用旧字段”的兼容分支。需要旧数据时重新采集或离线重建，新 runtime 只服务新 schema。

### 3. LLM 不进入实时 ranking 主路径

实时路径保持确定性：

```text
GMGN event
  -> normalize
  -> entity extraction
  -> token identity resolution
  -> token attribution
  -> rolling social metrics
  -> deterministic scores
  -> API/UI
```

LLM/agent 只做异步增强：

- watched-event 中文叙事；
- top-post quality label；
- high-score signal critic note；
- account quality offline calibration。

### 4. 评分是多层结构，不是一个黑盒分

最终 opportunity 分数来自五个组件：

```text
opportunity_score =
  0.30 * social_heat_score
  + 0.25 * discussion_quality_score
  + 0.20 * propagation_score
  + 0.15 * tradeability_score
  + 0.10 * timing_score
```

然后应用 hard gates 和 risk caps：

- unresolved/ambiguous identity 不能是 driver；
- missing market/mcap 不能是 driver；
- repeated text cluster cap 45；
- author concentration cap 65；
- stale market cap 70；
- public-only no watched/source-quality confirmation cap 85；
- price already moved before social expansion 加 chase-risk cap。

## 三、文件结构总览

### 新增后端文件

- `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py`
  - 只负责社交热度分数。
- `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py`
  - 只负责帖子质量、证据强度、重复/低信息风险。
- `src/gmgn_twitter_intel/retrieval/propagation_scoring.py`
  - 只负责作者扩散、有效作者数、传播阶段。
- `src/gmgn_twitter_intel/retrieval/timing_scoring.py`
  - 只负责 social leads price / price leads social / chase risk。
- `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
  - 只负责身份、市场快照、市值、流动性/池子字段可用性。
- `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py`
  - 组合五个组件，输出最终 driver/watch/discard。
- `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
  - 从 attribution rows 聚合 buckets、authors、posts、timeline summary。
- `src/gmgn_twitter_intel/retrieval/post_text_quality.py`
  - 纯启发式文本质量函数，供 discussion quality 和 token posts 使用。
- `src/gmgn_twitter_intel/storage/account_quality_repository.py`
  - 后续 account quality foundation。
- `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
  - 后续读取账号质量，不进入第一版 live ranking。

### 修改后端文件

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
  - 从旧 signal/evidence 模型改成 social_heat/discussion_quality/propagation/timing/tradeability/opportunity。
- `src/gmgn_twitter_intel/retrieval/rolling_token_flow.py`
  - 保留 rolling attribution 聚合，但补充 multi-window stats 所需字段。
- `src/gmgn_twitter_intel/retrieval/token_posts_service.py`
  - 使用新的 discussion post quality 输出，不再调用旧 `post_score`。
- `src/gmgn_twitter_intel/retrieval/token_signal_scoring.py`
  - 删除。逻辑拆入上述新 scoring modules。
- `src/gmgn_twitter_intel/retrieval/diffusion_health.py`
  - 删除或只保留 text fingerprint 函数；扩散评分迁移到 `propagation_scoring.py`。
- `src/gmgn_twitter_intel/api/http.py`
  - 重写 `/api/token-flow` response contract。
  - 新增 `/api/token-social-timeline`。
- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
  - schema v8，新增中文叙事字段和 account quality 表。
- `src/gmgn_twitter_intel/storage/enrichment_repository.py`
  - 存储中文 narrative display fields。
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
  - prompt 和 parser 改成中文可读叙事 contract。
- `src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py`
  - seed 存 display/headline/market interpretation 中文字段。
- `src/gmgn_twitter_intel/retrieval/narrative_service.py`
  - API 输出中文叙事 display model。
- `src/gmgn_twitter_intel/retrieval/narrative_link_service.py`
  - seed-token link 输出中文 seed display。
- `src/gmgn_twitter_intel/cli.py`
  - 保留账号质量 stats rebuild/backfill；不提供中文叙事旧记录 backfill。

### 新增前端文件

- `web/src/components/TokenRadarTable.tsx`
  - 新雷达表格。
- `web/src/components/TokenRadarRow.tsx`
  - 单行 token 渲染。
- `web/src/components/TokenDetailDrawer.tsx`
  - 右侧详情抽屉。
- `web/src/components/TokenTimeline.tsx`
  - bucket timeline、author lanes、price/social overlay。
- `web/src/components/TokenPostsTab.tsx`
  - 全量帖子分页。
- `web/src/components/ScoreLedger.tsx`
  - score components、contributions、risk caps。
- `web/src/components/NarrativePanel.tsx`
  - 中文叙事流。
- `web/src/components/AccountLane.tsx`
  - 作者 lanes 和账号候选分析。
- `web/src/components/LiveSignalTape.tsx`
  - 保留并升级实时信号 tape，展示全局 live/replay/enrichment 脉冲。

### 修改前端文件

- `web/src/App.tsx`
  - 拆分组件后只保留数据 query、全局状态和 layout。
- `web/src/api/types.ts`
  - 删除旧 `signal`、`TokenEvidenceHighlight` 类型。
  - 新增 `SocialHeatBlock`、`DiscussionQualityBlock`、`PropagationBlock`、`TimingBlock`、`TradeabilityBlock`、`OpportunityBlock`、`TokenSocialTimelineData`。
- `web/src/api/client.ts`
  - 增加 timeline fetch helper 可选。
- `web/src/store/useTraderStore.ts`
  - 增加 detail tab、timeline bucket、sort mode。
- `web/src/lib/format.ts`
  - 增加 score、phase、risk cap、timeline bucket formatting。
- `web/src/styles.css`
  - 保留现有视觉方向，增加 timeline lanes 和 ledger 样式。

### 新增/修改测试

- `tests/test_social_heat_scoring.py`
- `tests/test_discussion_quality_scoring.py`
- `tests/test_propagation_scoring.py`
- `tests/test_timing_scoring.py`
- `tests/test_tradeability_scoring.py`
- `tests/test_opportunity_scoring.py`
- `tests/test_token_social_timeline_service.py`
- `tests/test_token_flow_social_heat_contract.py`
- `tests/test_api_http.py`
- `tests/test_llm_enrichment.py`
- `tests/test_enrichment_repository.py`
- `web/src/api/types.test.ts` 如当前工具链不方便可省略。
- `web/src/App.test.tsx`
- `web/src/lib/format.test.ts`

## 四、重构后前端产品与组件设计

### 设计目标

这个 cockpit 是交易员工作台，不是营销页。视觉要延续当前方向：

- 深色底、细网格、低噪声、信息密度高；
- Inter + JetBrains Mono 不换，保证当前系统气质一致；
- amber 仍是唯一主强调色；
- green/red 只用于价格方向；
- blue 只用于 watch/信息提示；
- 表格、drawer、panel 都保持 4-6px 小圆角；
- 不做大 hero、不做装饰卡片、不做渐变球；
- 所有文字都要适合高频扫读，避免解释性废话。

产品记忆点是：**一个币的社会传播像交易盘口一样可读**。左边筛条件，中间扫机会，右边看 timeline 和证据。

### 信息架构

页面保持三栏：

```text
┌──────────────┬──────────────────────────────────────┬──────────────────────┐
│ Side Rail    │ Token Radar                          │ Detail Drawer        │
│              │                                      │                      │
│ windows      │ Token Heat Quality Prop Market Time  │ Timeline             │
│ scope        │ rows                                 │ Posts                │
│ decisions    │                                      │ Score                │
│ narratives   │ bottom deck: Live / Narratives       │ Narratives           │
│ watchlist    │                                      │ Accounts             │
└──────────────┴──────────────────────────────────────┴──────────────────────┘
```

### 组件职责

`TokenRadarTable.tsx`

- 只负责表格 shell、表头、loading/empty 状态、排序入口。
- props:
  - `items: TokenFlowItem[]`
  - `selectedKey: string | null`
  - `manualDecisions: Record<string, Decision>`
  - `sortMode: "opportunity" | "heat" | "quality" | "propagation" | "timing"`
  - `onSelect(item)`
  - `onSortModeChange(mode)`

`TokenRadarRow.tsx`

- 单行显示交易员 3 秒扫读信息：
  - Token: `$SYMBOL / chain / short CA`
  - Heat: score + `mentions +delta z`
  - Quality: score + top reason/risk
  - Propagation: phase + authors + top share
  - Market: mcap + price delta
  - Timing: state + chase risk
  - Decision: driver/watch/discard
- 不显示长文本，不显示帖子内容。
- 点击行只选中 token，不触发 search fallback。

`TokenDetailDrawer.tsx`

- 右侧详情总控。
- tabs:
  - `Timeline`
  - `Posts`
  - `Score`
  - `Narratives`
  - `Accounts`
- 头部显示：
  - token symbol、chain、short CA；
  - opportunity score；
  - decision tag；
  - manual override D/W/X；
  - hard risks。

`TokenTimeline.tsx`

- 交易员最重要的视图。
- 上半部是 bucket heat strip：
  - 每个 bucket 高度表示 posts；
  - amber 表示 watched posts；
  - green/red 细线表示价格变化；
  - hover 显示 bucket summary。
- 中部是 author lanes：
  - seed author；
  - early amplifier；
  - amplifier；
  - repeater；
  - watched。
- 下半部是关键帖子列表：
  - 按时间顺序；
  - 显示 post quality、handle、文本摘要、source type、链接。

`TokenPostsTab.tsx`

- 全量帖子分页。
- 不解释 signal，只回答“这个窗口所有 token-attributed posts 是什么”。
- 支持：
  - recent sort；
  - quality sort；
  - watched only filter；
  - duplicate cluster filter。

`ScoreLedger.tsx`

- 显示五个 component score：
  - Heat
  - Quality
  - Propagation
  - Tradeability
  - Timing
- 每个 component 展开后显示：
  - contributions；
  - risks；
  - risk caps；
  - hard gates。

`NarrativePanel.tsx`

- 显示中文 LLM 叙事：
  - `display.name_zh`
  - `display.headline_zh`
  - `display.summary_zh`
  - `display.market_interpretation_zh`
- 机器 `label` 只用于 key、tooltip、debug，不作为主文案。
- seed-token link 显示：
  - watched author；
  - 中文叙事标题；
  - linked token；
  - lag；
  - link confidence；
  - matched terms。

`AccountLane.tsx`

- 显示这个 token 的作者质量线索：
  - first seen；
  - posts；
  - followers；
  - role；
  - watched status；
  - provisional account quality。
- 账号质量不足样本时显示 `样本不足`，不显示假精度。

`LiveSignalTape.tsx`

- 保留旧 cockpit 中非常有价值的 `实时信号 Tape`，它是全局事件流，不属于某一个 token 的详情页。
- 位置：中间主栏底部 deck，和 `NarrativePanel` 并列；在高度不足时仍保留至少 140px，可滚动。
- 数据来源：
  - WebSocket live events；
  - `/api/recent` replay events；
  - enrichment update；
  - narrative link update。
- 显示内容：
  - `@handle -> $TOKEN` 或 `@handle -> narrative`；
  - event age；
  - event type：`watched`、`token`、`narrative`、`enrichment`、`risk`；
  - compact reason，例如 `CA direct`、`watched seed`、`duplicate risk`；
  - 可选 score：post quality 或 opportunity score。
- 交互：
  - 点击 token event：选中对应 token，如果 token flow item 当前页没有该 token，则打开 search/query fallback 作为证据模式。
  - 点击 narrative event：打开 `Narratives` tab 并定位 seed/link。
  - 点击普通 watched event：打开 event focus，不改变 token radar 排序。
- 价值边界：
  - Tape 是“发生了什么”的实时脉冲；
  - Token Radar 是“什么值得交易员关注”的排序；
  - Timeline 是“某个 token 如何传播”的详情。
- 因此 tape 不能被 Token Timeline 替代，也不能藏进 drawer。

### 组件接口合同

这些接口进入 `web/src/api/types.ts` 和组件 props。实现时不要临时从旧字段推导。

```ts
export type Decision = "driver" | "watch" | "discard";
export type RadarSortMode = "opportunity" | "heat" | "quality" | "propagation" | "timing";
export type TokenDetailTab = "timeline" | "posts" | "score" | "narratives" | "accounts";
export type TimelineBucket = "30s" | "1m" | "5m";

export type ScoreContribution = {
  feature: string;
  value: number;
  reason: string;
};

export type RiskCap = {
  risk: string;
  cap: number;
};

export type ScoreBlock = {
  score: number;
  score_version: string;
  reasons: string[];
  risks: string[];
  contributions: ScoreContribution[];
  risk_caps: RiskCap[];
};

export type SocialHeatBlock = ScoreBlock & {
  window: WindowKey;
  mentions: number;
  weighted_mentions: number;
  previous_mentions: number;
  mention_delta: number;
  mention_delta_pct?: number | null;
  z_score?: number | null;
  new_burst_score?: number | null;
  stream_share: number;
  watched_share: number;
  status: "cold" | "rising" | "burst" | "new_burst" | "insufficient_history" | string;
};

export type DiscussionQualityBlock = ScoreBlock & {
  evidence_specificity: number;
  avg_post_quality: number;
  avg_attribution_confidence: number;
  duplicate_text_share: number;
  informative_post_count: number;
  watched_source_count: number;
};

export type PropagationBlock = ScoreBlock & {
  independent_authors: number;
  effective_authors: number;
  new_authors: number;
  top_author_share: number;
  author_entropy: number;
  reproduction_rate?: number | null;
  phase: "seed" | "ignition" | "expansion" | "concentration" | "fade" | string;
  top_authors: Array<{ handle: string; posts: number; followers?: number | null; role?: string | null }>;
};

export type TradeabilityBlock = ScoreBlock & {
  identity_tradeable: boolean;
  market_fresh: boolean;
  market_cap_present: boolean;
  liquidity_present: boolean;
  pool_present: boolean;
};

export type TimingBlock = {
  score: number;
  score_version: string;
  status: "social_leads_price" | "social_confirms_price" | "price_leads_social" | "social_fades" | "insufficient_data" | string;
  social_start_ms?: number | null;
  first_price_move_ms?: number | null;
  price_change_window_pct?: number | null;
  chase_risk: boolean;
  reasons: string[];
  risks: string[];
};

export type OpportunityBlock = ScoreBlock & {
  decision: Decision;
  components: {
    heat: number;
    quality: number;
    propagation: number;
    tradeability: number;
    timing: number;
  };
};

export type TokenFlowItem = {
  identity: TokenIdentityBlock;
  market: TokenMarketBlock;
  social_heat: SocialHeatBlock;
  discussion_quality: DiscussionQualityBlock;
  propagation: PropagationBlock;
  tradeability: TradeabilityBlock;
  timing: TimingBlock;
  opportunity: OpportunityBlock;
  posts_query: TokenPostsQuery;
  timeline_query: TokenSocialTimelineQuery;
};
```

组件 props：

```ts
type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  manualDecisions: Record<string, Decision>;
  sortMode: RadarSortMode;
  isLoading: boolean;
  error?: Error | null;
  onSelect: (item: TokenFlowItem) => void;
  onSortModeChange: (mode: RadarSortMode) => void;
};

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  decision: Decision;
  manualDecision?: Decision;
  onSelect: (item: TokenFlowItem) => void;
};

type TokenDetailDrawerProps = {
  token: TokenFlowItem | null;
  activeTab: TokenDetailTab;
  manualDecision?: Decision;
  timeline?: TokenSocialTimelineData | null;
  posts?: TokenPostsData | null;
  narrativeLinks: AttentionFrontierItem[];
  accountQuality?: AccountQualityData | null;
  isTimelineLoading: boolean;
  isPostsLoading: boolean;
  onTabChange: (tab: TokenDetailTab) => void;
  onDecisionOverride: (decision: Decision) => void;
  onLoadMorePosts: () => void;
};

type LiveSignalTapeItem =
  | { kind: "event"; payload: LivePayload; score?: number | null; reason: string }
  | { kind: "token"; token: TokenFlowItem; event?: LivePayload | null; score?: number | null; reason: string }
  | { kind: "narrative"; item: AttentionFrontierItem; score?: number | null; reason: string }
  | { kind: "enrichment"; payload: LivePayload; score?: number | null; reason: string };

type LiveSignalTapeProps = {
  items: LiveSignalTapeItem[];
  selectedEventId?: string | null;
  isLoading: boolean;
  maxRows?: number;
  onSelect: (item: LiveSignalTapeItem) => void;
};
```

### 数据流和状态归属

`App.tsx` 只保留数据获取、选择状态和 layout，不再直接写大段 UI。

必须保留在 `App.tsx` 的 query：

- `bootstrapQuery`
- `statusQuery`
- `recentQuery`
- `tokenFlowQuery`
- `tokenPostsQuery`
- `tokenTimelineQuery`
- `narrativeQuery`
- `frontierQuery`
- `accountQualityQuery`

必须保留在 `App.tsx` 的 derived data：

- `liveItems`: 由 WebSocket events 和 `/api/recent` replay 去重后按 `received_at_ms` 倒序合并。
- `liveSignalTapeItems`: 从 `liveItems`、`frontierQuery.data`、enrichment updates 归一化成 `LiveSignalTapeItem[]`。
- `selectedTapeEventId`: 当前 tape 选中项，用于行高亮。

必须保留在 `useTraderStore.ts` 的 UI 状态：

```ts
type TraderState = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  handles: string;
  search: string;
  submittedSearch: string;
  radarSortMode: RadarSortMode;
  detailTab: TokenDetailTab;
  timelineBucket: TimelineBucket;
  postSortMode: "recent" | "quality";
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  manualDecisions: Record<string, Decision>;
};
```

选择 token 的行为：

```text
select token row
  -> selectedSignal = { kind: "token", item }
  -> detailTab = "timeline"
  -> tokenTimelineQuery enabled
  -> tokenPostsQuery enabled but not visually active until Posts tab
  -> no search query side effect
```

排序行为：

```text
opportunity: opportunity.score desc
heat: social_heat.score desc
quality: discussion_quality.score desc
propagation: propagation.score desc
timing: timing.score desc, chase_risk false first
```

Tape 选择行为：

```text
select live token item
  -> if token exists in tokenFlowQuery current items: selectedSignal = { kind: "token", item }
  -> detailTab = "timeline"
  -> else selectedSignal = { kind: "event", payload }
  -> do not change radarSortMode

select live narrative item
  -> selectedSignal = { kind: "narrative", item }
  -> if linked token exists: select token and detailTab = "narratives"

select live event item
  -> selectedSignal = { kind: "event", payload }
  -> detail drawer shows event focus
```

### 静态效果到生产 UI 的映射

静态稿 `docs/mockups/token-radar-social-heat-cn.html` 是生产 UI 的结构蓝图，不是一次性视觉草稿。生产实现应保持这些视觉结构：

- `.cockpit-shell` / `.topbar` / `.cockpit-grid` 延续现有命名。
- 中间表格对应 `TokenRadarTable`：
  - `.radar-toolbar`
  - `.token-radar-table`
  - `.radar-head`
  - `.radar-row`
  - `.token-cell`
  - `.metric`
  - `.phase`
  - `.barline`
- 右侧详情对应 `TokenDetailDrawer`：
  - `.drawer-head`
  - `.drawer-kv`
  - `.focus-tabs` 或 `.tabs`
  - `.timeline-chart`
  - `.author-lanes`
  - `.score-grid`
  - `.narrative`
  - `.post-list`
- 中文叙事 panel 对应 `NarrativePanel`：
  - `display.headline_zh` 是主标题；
  - `display.summary_zh` 是第二行；
  - `display.market_interpretation_zh` 进入详情 tab；
  - `label` 只作为 React key 和 debug tooltip。
- 实时信号 tape 对应 `LiveSignalTape`：
  - `.bottom-deck`
  - `.live-signal-tape`
  - `.tape-row`
  - `.tape-kind`
  - `.tape-score`
  - `.tape-reason`
  - 保持和 mockup 中 `实时信号 Tape` 一样的 compact two-column deck 位置。

布局尺寸：

```css
.cockpit-grid {
  grid-template-columns: 198px minmax(860px, 1fr) 424px;
}

.radar-head,
.radar-row {
  grid-template-columns: minmax(112px, 136px) 112px 116px 126px 108px 116px 78px;
}

.detail-drawer {
  width: 424px;
}
```

响应式：

- `>= 1280px`: 三栏完整显示。
- `1024px..1279px`: 保留 side rail + radar，detail drawer 可收起为 overlay。
- `< 1024px`: radar 表格横向滚动，detail drawer 作为全屏 panel；这不是首版交易桌面目标，但不能文本重叠。

### UI 状态和空态

每个组件必须有明确状态。

`TokenRadarTable`

- loading: 保持表头，显示 8 行 skeleton。
- error: 显示 `Token Radar 暂不可用` 和错误 code。
- empty: 显示 `当前窗口暂无可交易 token 热度`。
- stale data: toolbar 显示 `stale` pill，不遮挡表格。

`TokenTimeline`

- loading: timeline chart skeleton + author lane skeleton。
- empty: `该窗口暂无传播时间线`。
- sparse: 显示 buckets，但加 risk tag `insufficient_timeline_data`。
- price missing: heat bars 仍显示，price line 留空并显示 `price snapshot missing`。

`TokenPostsTab`

- loading: post skeleton。
- empty: `该窗口暂无 token-attributed posts`。
- has more: 底部 `加载更多`。
- duplicate filter on: 顶部显示 `已隐藏重复文本簇`。

`ScoreLedger`

- no token: 不渲染。
- risk caps present: cap pill 必须在对应 component 下可见。
- hard gate present: 显示红色/灰色 risk pill，不能只放 tooltip。

`NarrativePanel`

- LLM off: 显示 `LLM 叙事未启用`。
- no narrative: 显示 `当前 token 暂无 watched seed link`。
- loading: 保留 panel 高度，显示 skeleton。
- missing Chinese fields: 不在运行时 fallback；这是 LLM 输出或新 schema 写入的 contract error，显示错误态 `narrative_display_missing`。

`LiveSignalTape`

- loading: 保持 panel header，显示 5 行 skeleton。
- empty: `等待 replay 或 live event`。
- disconnected: header action 显示 `ws disconnected`，但保留 replay rows。
- selected: selected row 使用和 radar selected 一致的 left amber inset。
- overflow: 超出 `maxRows` 后内部滚动，不挤压 Token Radar 表格。

### 前端测试必须覆盖的 UI 目标

`web/src/App.test.tsx`

- 表头出现 `Token / Heat / Quality / Propagation / Market / Timing / Decision`。
- 不出现旧 `EV`、旧 `narrative` 列、旧 `Evidence` 主列。
- row decision 来自 `item.opportunity.decision`。
- 点击 token row 后默认 tab 是 `Timeline`。
- `Timeline` tab 会请求 `/api/token-social-timeline`。
- `Posts` tab 会请求 `/api/token-posts`。
- `Score` tab 显示五个 component score。
- `Narratives` tab 显示中文 `headline_zh`，不显示 snake_case label。
- 当 response 中缺少中文 display 字段时，显示 `narrative_display_missing` 错误态。
- 页面底部保留 `实时信号 Tape` panel。
- WebSocket event 和 replay event 去重后进入 `LiveSignalTape`。
- 点击 tape 中的 token event 会选中 token 或打开 event focus，但不会改变当前 sort mode。
- WebSocket 断开时 tape 保留 replay rows，并显示 `ws disconnected`。

`web/src/lib/format.test.ts`

- `formatTimingStatus("social_leads_price")` 输出 `社交领先`。
- `formatTimingStatus("price_leads_social")` 输出 `价格先动`。
- `formatPropagationPhase("expansion")` 输出 `扩散`。
- `formatRisk("author_concentration_high")` 输出 `作者集中`。
- `formatScoreDelta(11)` 输出 `+11`。

### 交互规则

- 默认窗口：`1h`；交易员按 `1/2/3` 切 `5m/1h/24h`。
- 默认排序：`opportunity`。
- 切到 `5m` 时强调 ignition；切到 `1h` 强调 confirmation；切到 `24h` 强调 regime。
- 选中 token 后默认打开 `Timeline`。
- `Posts` tab 永远展示全量分页，不展示 highlight。
- `Score` tab 永远展示 ledger，不展示帖子瀑布。
- `Narratives` tab 只展示与当前 token 相关的中文 seed/link。
- 手动 D/W/X 只改变本地 override tag，不改变 backend `opportunity.decision`。
- 风险状态必须可见：
  - `author_concentration_high`
  - `duplicate_text_cluster`
  - `price_leads_social`
  - `market_missing`
  - `public_stream_coverage`

### 模拟效果

静态 mockup 文件：

- `docs/mockups/token-radar-social-heat-cn.html`
- `docs/mockups/token-radar-social-heat-cn.png`

模拟的数据要覆盖：

- 一个 `driver`：5m heat burst，中文叙事 seed，独立作者扩散，社交和价格确认。
- 一个 `watch`：public-only、传播健康但 market/timing 未完全确认。
- 一个 `discard`：重复文本或 top author concentration 高。
- 一个 `price_leads_social`：价格先动，社交后来，有追高风险。

验收标准：

- 表格在 1440px 宽度不重叠。
- 右侧 drawer 的 Timeline、Posts、Score、Narratives、Accounts 视觉层级一致。
- 中文叙事能一眼读懂，不露 snake_case。
- score 和 risk caps 看起来像交易风控面板，而不是模型解释长文。

## 五、后端 API 新合同

### `/api/token-flow`

新 response item：

```json
{
  "identity": {
    "identity_key": "token:bsc:0x...",
    "identity_status": "resolved_ca",
    "token_id": "token:bsc:0x...",
    "chain": "bsc",
    "address": "0x...",
    "symbol": "TOKEN"
  },
  "market": {
    "market_status": "fresh",
    "price": 0.01,
    "market_cap": 1000000,
    "liquidity": 200000,
    "pool_status": "ready",
    "snapshot_age_ms": 30000,
    "price_change_window_pct": 0.12,
    "price_change_status": "ready"
  },
  "social_heat": {
    "score": 86,
    "score_version": "social_heat_v1",
    "window": "5m",
    "mentions": 12,
    "weighted_mentions": 11.4,
    "previous_mentions": 3,
    "mention_delta": 9,
    "mention_delta_pct": 3.0,
    "z_score": 3.1,
    "new_burst_score": null,
    "stream_share": 0.042,
    "watched_share": 0.1,
    "status": "burst",
    "reasons": ["z_score_above_3", "positive_acceleration"],
    "risks": ["public_stream_coverage"],
    "contributions": [],
    "risk_caps": []
  },
  "discussion_quality": {
    "score": 78,
    "score_version": "discussion_quality_v1",
    "evidence_specificity": 90,
    "avg_post_quality": 74,
    "avg_attribution_confidence": 0.94,
    "duplicate_text_share": 0.08,
    "informative_post_count": 7,
    "watched_source_count": 1,
    "reasons": ["resolved_direct_evidence", "low_duplicate_share"],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "propagation": {
    "score": 72,
    "score_version": "propagation_v1",
    "independent_authors": 8,
    "effective_authors": 5.7,
    "new_authors": 6,
    "top_author_share": 0.25,
    "author_entropy": 1.74,
    "reproduction_rate": 1.5,
    "phase": "expansion",
    "top_authors": [],
    "reasons": ["multi_author_expansion"],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "tradeability": {
    "score": 80,
    "score_version": "tradeability_v1",
    "identity_tradeable": true,
    "market_fresh": true,
    "market_cap_present": true,
    "liquidity_present": true,
    "pool_present": true,
    "reasons": ["resolved_ca", "fresh_market"],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "timing": {
    "score": 70,
    "score_version": "timing_v1",
    "status": "social_confirms_price",
    "social_start_ms": 1777770000000,
    "first_price_move_ms": 1777770300000,
    "price_change_window_pct": 0.12,
    "chase_risk": false,
    "reasons": ["social_and_price_confirm"],
    "risks": []
  },
  "opportunity": {
    "score": 78,
    "score_version": "social_opportunity_v1",
    "decision": "driver",
    "components": {
      "heat": 86,
      "quality": 78,
      "propagation": 72,
      "tradeability": 80,
      "timing": 70
    },
    "reasons": ["social_burst", "healthy_expansion", "fresh_market"],
    "risks": ["public_stream_coverage"],
    "contributions": [],
    "risk_caps": []
  },
  "posts_query": {
    "token_id": "token:bsc:0x...",
    "window": "5m",
    "scope": "all"
  },
  "timeline_query": {
    "token_id": "token:bsc:0x...",
    "window": "5m",
    "bucket": "1m",
    "scope": "all"
  }
}
```

删除字段：

- `signal`
- `evidence_highlight_best`
- `evidence_highlights`
- `baseline` 顶层旧暴露，如仍需调试，放入 `social_heat.debug_baseline` 并默认不返回。

### `/api/token-social-timeline`

新增 endpoint：

```text
GET /api/token-social-timeline?token_id=...&window=1h&bucket=1m&scope=all&limit=200&cursor=...
```

用于 token 详情页 timeline，不依赖搜索 fallback。

核心原则：

- 从 `event_token_attributions` 读。
- 只读 `direct/selected` 且 `attribution_weight > 0`。
- 按 distinct `event_id` 去重。
- buckets 按 `bucket_start_ms` 聚合。
- authors 计算 first_seen、latest_seen、posts、followers、role。
- posts 使用 keyset cursor。

### `/api/token-posts`

保留 endpoint，但 response 里的 post score 改为 `discussion_quality_scoring.post_quality_score`。

删除旧 `post_score_v1`。

### `/api/narrative-flow`

改为中文 display model：

```json
{
  "label": "ai_agent_grok",
  "display": {
    "name_zh": "Grok AI Agent",
    "headline_zh": "Grok 相关发言重新点燃 AI Agent 代币注意力",
    "summary_zh": "某 watched 账号提到 Grok 产品进展，公开流中开始出现 AI Agent 相关 token 讨论。",
    "market_interpretation_zh": "交易员可能会关注 Grok、xAI、AI Agent 主题相关的 token 是否出现独立扩散。"
  },
  "flow": {
    "window": "1h",
    "mentions": 8,
    "watched_mentions": 2,
    "velocity": 0.13
  }
}
```

前端不直接显示 `label`。

## 六、评分原理

### Social Heat

目的：判断“讨论热度是否异常上升”。

输入：

- `mentions`
- `weighted_mentions`
- `previous_mentions`
- `mention_delta`
- `mention_delta_pct`
- `z_score`
- `new_burst_score`
- `stream_share`
- `watched_share`
- `is_new_local_evidence`
- `is_first_seen_by_watched`

计算：

```text
score =
  log_mentions_points
  + surprise_points
  + acceleration_points
  + stream_share_points
  + watched_points
  + novelty_points
  + weighted_mentions_points
```

建议权重：

- 当前 mention 数 log-scale，最多 25；
- z-score >= 3 给 25，>= 2 给 18，new burst 给 12；
- mention_delta > 0 最多 15；
- stream_share 按本窗口占比最多 10；
- watched_share 或 first watched 最多 10；
- first local evidence 最多 10；
- weighted mentions 接近 mentions 最多 5。

风险：

- mentions < 2: `thin_mentions`
- baseline 不足: `insufficient_baseline`
- coverage 固有风险: `public_stream_coverage`

### Discussion Quality

目的：判断“讨论有没有信息含量，还是噪声”。

输入：

- attribution source：GMGN payload、CA、cashtag selected、symbol-only；
- attribution confidence/weight；
- text fingerprint duplicate share；
- informative text ratio；
- watched source count；
- market context terms；
- post recency。

启发式信息量：

```text
informative if text contains any:
  CA
  concrete catalyst verbs
  price/market/liquidity/volume/holder terms
  product/person/project name
  URL/domain
  chart/thread/reference text
```

惩罚：

- 过短；
- 只有 ticker；
- 过多 cashtag；
- 重复 fingerprint；
- 低 attribution confidence。

### Propagation

目的：判断“热度是单点广播，还是独立扩散”。

输入：

- independent authors；
- effective authors；
- new authors by bucket；
- top_author_share；
- duplicate_text_share；
- watched author presence；
- narrative seed lag。

有效作者数：

```text
share_i = author_i_posts / total_posts
entropy = -sum(share_i * ln(share_i))
effective_authors = exp(entropy)
```

传播阶段：

- `seed`: 1 个作者或 1 条帖子；
- `ignition`: 2-3 个独立作者，热度刚启动；
- `expansion`: new authors 连续进入，top_author_share 下降；
- `concentration`: 总量上升但 top_author_share 高；
- `fade`: 当前 bucket 低于前 bucket 且无新作者。

### Timing

目的：判断“社交领先价格，还是已经追高”。

状态：

- `social_leads_price`: social heat 高，价格还没明显动；
- `social_confirms_price`: social 和 price 同窗口确认；
- `price_leads_social`: 价格先大幅移动，社交后来；
- `social_fades`: 价格动过后社交下降；
- `insufficient_data`: 快照不足。

第一版只基于稀疏 snapshots，不声明精确高频交易信号。

### Tradeability

目的：判断“这个信号是否能被交易执行”。

硬条件：

- `identity_status == resolved_ca`
- `token_id` 存在；
- chain/address tradeable；
- market snapshot 存在；
- market cap 存在；
- snapshot fresh。

辅助：

- liquidity；
- pool；
- holder；
- volume。

如果辅助字段没有，只降分，不编造。

### Opportunity

目的：输出交易员能扫的最终状态。

决策：

- `driver`: heat/quality/propagation/tradeability/timing 都过线，且无 hard risk。
- `watch`: token 可交易，但证据尚早、传播不够、市场字段不完整或 public-only。
- `discard`: token 身份不确定、市场缺失、重复/集中风险严重、明显 chase risk。

## 七、实施任务

### Task 1: 写新评分模块的失败测试

**Files:**
- Create: `tests/test_social_heat_scoring.py`
- Create: `tests/test_discussion_quality_scoring.py`
- Create: `tests/test_propagation_scoring.py`
- Create: `tests/test_timing_scoring.py`
- Create: `tests/test_tradeability_scoring.py`
- Create: `tests/test_opportunity_scoring.py`

- [ ] 测 `social_heat_score()`：z-score 高、delta 正、mentions 足够时输出 `status=burst`，score 高于 75。
- [ ] 测 `social_heat_score()`：mentions=1 时有 `thin_mentions` 风险，不能 driver。
- [ ] 测 `discussion_quality_score()`：direct CA + 高 attribution + 低重复文本，score 高。
- [ ] 测 `discussion_quality_score()`：重复 fingerprint share >= 0.5 时触发 `duplicate_text_cluster` 和 cap。
- [ ] 测 `propagation_score()`：8 个作者、effective authors > 4、top share < 0.35 时是 `expansion`。
- [ ] 测 `propagation_score()`：单作者占比 >= 0.75 时是 `concentration`，cap 65。
- [ ] 测 `timing_score()`：social burst 早于 price move 时为 `social_leads_price`。
- [ ] 测 `timing_score()`：price 已先涨很大时为 `price_leads_social` 和 `chase_risk`。
- [ ] 测 `tradeability_score()`：resolved CA + fresh market + mcap，score 高。
- [ ] 测 `tradeability_score()`：missing market/mcap 输出 hard risk。
- [ ] 测 `opportunity_score()`：hard risk 会覆盖加权总分，不能输出 driver。

运行：

```bash
uv run pytest tests/test_social_heat_scoring.py tests/test_discussion_quality_scoring.py tests/test_propagation_scoring.py tests/test_timing_scoring.py tests/test_tradeability_scoring.py tests/test_opportunity_scoring.py -q
```

预期：全部失败，因为模块还不存在。

### Task 2: 实现纯函数评分模块

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/propagation_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/timing_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py`
- Create: `src/gmgn_twitter_intel/retrieval/post_text_quality.py`

- [ ] 实现统一 helper：`score_payload(score_version, score, reasons, risks, contributions, risk_caps)`。
- [ ] 实现统一 helper：`apply_risk_caps(score, risk_caps)`。
- [ ] 实现 `social_heat_score(features: dict[str, Any]) -> dict[str, Any]`。
- [ ] 实现 `post_text_quality(text: str | None) -> dict[str, Any]`。
- [ ] 实现 `discussion_quality_score(features: dict[str, Any]) -> dict[str, Any]`。
- [ ] 实现 `propagation_score(features: dict[str, Any]) -> dict[str, Any]`。
- [ ] 实现 `timing_score(features: dict[str, Any]) -> dict[str, Any]`。
- [ ] 实现 `tradeability_score(features: dict[str, Any]) -> dict[str, Any]`。
- [ ] 实现 `opportunity_score(components: dict[str, dict[str, Any]]) -> dict[str, Any]`。
- [ ] 每个模块只做计算，不读数据库，不 import repository。

运行：

```bash
uv run pytest tests/test_social_heat_scoring.py tests/test_discussion_quality_scoring.py tests/test_propagation_scoring.py tests/test_timing_scoring.py tests/test_tradeability_scoring.py tests/test_opportunity_scoring.py -q
uv run ruff check src/gmgn_twitter_intel/retrieval
```

预期：评分模块测试通过。

### Task 3: 重构 TokenFlowService，不保留旧 signal/evidence 兼容字段

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/rolling_token_flow.py`
- Delete: `src/gmgn_twitter_intel/retrieval/token_signal_scoring.py`
- Modify: `tests/test_token_flow_social_heat_contract.py`
- Modify: `tests/test_token_conviction_flow.py`
- Modify: `tests/test_token_rolling_flow.py`

- [ ] 新建 contract 测试，断言 `/api/token-flow` item 包含 `social_heat`、`discussion_quality`、`propagation`、`tradeability`、`timing`、`opportunity`。
- [ ] 新建 contract 测试，断言 item 不包含 `signal`、`evidence_highlight_best`、`evidence_highlights`。
- [ ] 在 `RollingTokenFlow` 中保留 attribution 聚合，补充 `events_for_scoring` 所需文本、作者、fingerprint、bucket 时间。
- [ ] 在 `TokenFlowService._token_flow_item()` 中构造五个 score feature blocks。
- [ ] 使用新 scoring modules 生成五个组件和 `opportunity`。
- [ ] 删除 `signal_block()` 调用。
- [ ] 删除 `_evidence_items()` 和 `_evidence_total_counts()` 在 token-flow item 中的旧 highlight 语义。
- [ ] 保留 `posts_query`，新增 `timeline_query`。
- [ ] 排序改为 `opportunity.decision_priority`、`opportunity.score`、`social_heat.score`、`propagation.score`、freshness。

运行：

```bash
uv run pytest tests/test_token_flow_social_heat_contract.py tests/test_token_conviction_flow.py tests/test_token_rolling_flow.py -q
```

预期：新 contract 通过，旧字段不存在。

### Task 4: 新增 Token Social Timeline endpoint

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Create: `tests/test_token_social_timeline_service.py`
- Modify: `tests/test_api_http.py`

- [ ] 测 service：同一 token 在 1h 内的 posts 被按 1m bucket 聚合。
- [ ] 测 service：同一 event 多条 attribution 只算一次 post。
- [ ] 测 service：authors 输出 first_seen/latest_seen/posts/followers/role。
- [ ] 测 service：summary 输出 posts/authors/effective_authors/top_author_share/duplicate_text_share/phase。
- [ ] 测 service：cursor 能分页 posts，但 buckets 和 authors 基于完整 window summary。
- [ ] 实现 `_base_clauses()`，复用 token_id 或 chain/address identity 查询。
- [ ] 实现 `_post_rows()`，读取 `event_token_attributions` join `events`。
- [ ] 实现 `_bucket_posts()`。
- [ ] 实现 `_author_lanes()`。
- [ ] 实现 `_timeline_summary()`。
- [ ] 在 `api/http.py` 加 `/api/token-social-timeline`。
- [ ] endpoint 缺少 token identity 时返回 400 `missing_token_identity`。

运行：

```bash
uv run pytest tests/test_token_social_timeline_service.py tests/test_api_http.py -q
```

预期：timeline endpoint 合同通过。

### Task 5: 改造 TokenPostsService 的 post quality

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/token_posts_service.py`
- Modify: `tests/test_token_posts_service.py`
- Modify: `tests/test_api_http.py`

- [ ] 更新测试：`/api/token-posts` item 使用 `post_quality` block。
- [ ] 删除旧 `score_version=post_score_v1` 断言。
- [ ] 用 `discussion_quality_scoring.post_quality_score()` 计算单帖质量。
- [ ] response item 输出 `post_quality.score/reasons/risks/contributions/risk_caps`。
- [ ] 保持全量分页，不做 search fallback。

运行：

```bash
uv run pytest tests/test_token_posts_service.py tests/test_api_http.py -q
```

预期：全量帖子分页仍通过，post quality 新合同通过。

### Task 6: 中文叙事流破坏式改造

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Modify: `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- Modify: `src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py`
- Modify: `src/gmgn_twitter_intel/retrieval/narrative_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/narrative_link_service.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `tests/test_llm_enrichment.py`
- Modify: `tests/test_enrichment_repository.py`
- Modify: `tests/test_narrative_seed_builder.py`
- Modify: `tests/test_api_http.py`

- [ ] `llm_enrichment.py` prompt 改为要求中文字段：`summary_zh`、`display_name_zh`、`headline_zh`、`description_zh`、`market_interpretation_zh`。
- [ ] parser 拒绝缺少中文 display 字段的 narrative。
- [ ] schema v8 给 `event_enrichments`、`event_narratives`、`narrative_seeds` 加中文 display 字段。
- [ ] repository 存取中文字段。
- [ ] narrative retrieval 输出 `display` block。
- [ ] 前端不再显示 `narrative_label`，只显示 `display.name_zh/headline_zh`。
- [ ] 删除 `ops backfill-narrative-display`，中文叙事不靠旧 summary/label 生成占位字段。
- [ ] 运行时不写 fallback：缺中文字段就是 contract error，不做兼容修复。

运行：

```bash
uv run pytest tests/test_llm_enrichment.py tests/test_enrichment_repository.py tests/test_narrative_seed_builder.py tests/test_api_http.py -q
```

预期：中文 narrative 合同通过，旧 snake_case 不再作为 UI 文案。

### Task 7: 前端拆分和重做 Token Radar

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/store/useTraderStore.ts`
- Modify: `web/src/lib/format.ts`
- Create: `web/src/components/TokenRadarTable.tsx`
- Create: `web/src/components/TokenRadarRow.tsx`
- Create: `web/src/components/TokenDetailDrawer.tsx`
- Create: `web/src/components/TokenTimeline.tsx`
- Create: `web/src/components/TokenPostsTab.tsx`
- Create: `web/src/components/ScoreLedger.tsx`
- Create: `web/src/components/NarrativePanel.tsx`
- Create: `web/src/components/AccountLane.tsx`
- Create: `web/src/components/LiveSignalTape.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/lib/format.test.ts`

- [ ] `types.ts` 删除 `TokenEvidenceHighlight`、旧 `signal` 类型。
- [ ] `types.ts` 新增 `SocialHeatBlock`、`DiscussionQualityBlock`、`PropagationBlock`、`TradeabilityBlock`、`TimingBlock`、`OpportunityBlock`、`TokenSocialTimelineData`。
- [ ] `useTraderStore.ts` 新增 `radarSortMode`、`detailTab`、`timelineBucket`、`postSortMode`、`hideDuplicateClusters`、`watchedPostsOnly`、`manualDecisions`。
- [ ] `App.tsx` 只保留 query、selected token、manual decision override 和 layout，表格/详情/narrative 拆到组件。
- [ ] `App.tsx` 新增 `tokenTimelineQuery`，query key 包含 `token.timeline_query`、`timelineBucket`、`scope`。
- [ ] `App.tsx` 保留 `liveItems` merge/dedupe 逻辑，并新增 `liveSignalTapeItems` derived data。
- [ ] `TokenRadarTable.tsx` 实现表头、sort segmented、loading skeleton、empty/error/stale state。
- [ ] `TokenRadarRow.tsx` 实现 `Token / Heat / Quality / Propagation / Market / Timing / Decision` 七列，字段只来自新 semantic blocks。
- [ ] `TokenRadarRow.tsx` 默认 decision 来自 `item.opportunity.decision`，manual override 只显示 override 标记。
- [ ] `TokenDetailDrawer.tsx` 实现 drawer head、score badge、risk strip、D/W/X override、五个 tabs。
- [ ] 选中 token 后默认打开 `Timeline` tab，不再触发 search query side effect。
- [ ] `TokenTimeline.tsx` 调 `/api/token-social-timeline`，渲染 bucket heat strip、price line、author lanes、关键帖子。
- [ ] `TokenPostsTab.tsx` 调 `/api/token-posts`，渲染 full posts、quality score、load more、duplicate filter。
- [ ] `ScoreLedger.tsx` 渲染五个 component score、contributions、risk caps、hard gates。
- [ ] `NarrativePanel.tsx` 渲染中文 seed-token links，主文案使用 `display.headline_zh` 和 `display.summary_zh`。
- [ ] `AccountLane.tsx` 渲染作者 role、first seen、posts、followers、watched status、样本不足。
- [ ] `LiveSignalTape.tsx` 渲染实时信号 tape，输入 `LiveSignalTapeItem[]`，保留 replay rows、live rows、enrichment rows、narrative link rows。
- [ ] `LiveSignalTape.tsx` 点击 token/narrative/event 时按 tape 选择行为更新 selected signal，不改变 sort mode。
- [ ] `styles.css` 根据静态稿落地 `.radar-row` 七列、`.timeline-chart`、`.author-lanes`、`.score-grid`、`.narrative`、`.risk-strip`、`.live-signal-tape`、`.tape-row`。
- [ ] 移除所有旧 evidence highlight 渲染。
- [ ] `App.test.tsx` 覆盖新表头、默认 Timeline、timeline/posts 请求、中文 narrative、不显示 snake_case label、实时信号 Tape 保留。
- [ ] `format.test.ts` 覆盖 timing、propagation、risk、score delta 中文格式化。

运行：

```bash
cd web && npm test -- --run
cd web && npm run build
```

预期：前端测试和 build 通过，无旧字段引用。

### Task 8: Account Quality 数据基础

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Create: `src/gmgn_twitter_intel/storage/account_quality_repository.py`
- Create: `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Create: `tests/test_account_quality_repository.py`
- Create: `tests/test_account_quality_service.py`

- [ ] schema v8 新增 `account_profiles`。
- [ ] schema v8 新增 `account_token_call_stats`。
- [ ] schema v8 新增 `account_quality_snapshots`。
- [ ] repository 支持 upsert profile、upsert token call stat、insert quality snapshot。
- [ ] CLI 增加 `ops backfill-account-quality`。
- [ ] service 只读账号质量，不进入 live ranking。
- [ ] 测试从 attribution rows 生成 first mention stats。
- [ ] 测试市场快照不足时 outcome 为 `insufficient_market_history`。

运行：

```bash
uv run pytest tests/test_account_quality_repository.py tests/test_account_quality_service.py -q
```

预期：账号质量基础数据可 backfill，但不影响 token radar 实时排名。

### Task 9: 删除旧代码和旧测试语义

**Files:**
- Delete: `src/gmgn_twitter_intel/retrieval/token_signal_scoring.py`
- Modify: `tests/test_token_conviction_flow.py`
- Modify: `tests/test_token_attribution_flow.py`
- Modify: `tests/test_token_rolling_flow.py`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/api/types.ts`

- [ ] 删除旧 scoring module。
- [ ] 删除旧 `signal.score`、`signal.decision`、`evidence_highlights` 断言。
- [ ] 删除前端旧 headers 测试。
- [ ] 新测试只认 `opportunity` 和新 semantic blocks。
- [ ] 用 `rg "evidence_highlight|TokenEvidenceHighlight|signal\\.decision|signal\\.score|post_score_v1"` 确认无旧引用。

运行：

```bash
rg "evidence_highlight|TokenEvidenceHighlight|signal\\.decision|signal\\.score|post_score_v1" src tests web/src
```

预期：无匹配。如果文档中有历史说明，不算代码阻塞；源码和测试必须无匹配。

### Task 10: 全量验证

**Files:** All touched files.

- [ ] 运行 Python 单元测试。
- [ ] 运行 ruff。
- [ ] 运行 compileall。
- [ ] 运行前端测试。
- [ ] 运行前端 build。
- [ ] 启动本地服务，打开 cockpit，验证视觉和交互。

命令：

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test -- --run
cd web && npm run build
uv run gmgn-twitter-intel serve
```

浏览器检查：

- `/api/token-flow?window=5m&scope=all` 不返回旧 `signal` 和旧 evidence highlight。
- `/api/token-social-timeline?token_id=...&window=1h&bucket=1m&scope=all` 返回 buckets/authors/posts。
- cockpit 表格显示 `Token / Heat / Quality / Propagation / Market / Timing / Decision`。
- token 详情默认 Timeline，Posts 能加载全量，Score 能解释 components 和 risk caps。
- narrative panel 显示中文 headline，不显示 snake_case label。

## 八、风险和边界

- GMGN public stream 不是全 Twitter firehose，所有 score 必须保留 `public_stream_coverage` 风险。
- 价格是稀疏 snapshot，不是连续 K 线；Timing V1 只能做粗粒度判断。
- account quality 初期样本少，不进入 live ranking。
- LLM 中文叙事必须 evidence-bound，不能扩展未出现的 ticker。
- 不兼容旧前端和旧 API consumer；这是有意的破坏式重构。

## 九、完成定义

- 新 Token Radar 的主排序来自 `opportunity.score`。
- Heat、Quality、Propagation、Tradeability、Timing 分开显示。
- `driver/watch/discard` 可解释，带 contributions 和 risk caps。
- 全量帖子由 `/api/token-posts` 提供。
- 传播时间线由 `/api/token-social-timeline` 提供。
- 叙事流是中文可读文案。
- 源码和测试里没有旧 `signal`/`evidence_highlight` runtime 兼容引用。
- 全量验证命令通过。
