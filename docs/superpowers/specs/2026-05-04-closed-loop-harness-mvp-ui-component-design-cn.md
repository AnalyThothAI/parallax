# 闭环 Harness MVP UI 组件设计

日期：2026-05-04

具体页面设计：

```text
docs/superpowers/specs/2026-05-04-closed-loop-harness-concrete-page-design-cn.md
docs/prototypes/closed-loop-harness-cockpit.html
```

## 一句话结论

MVP UI 不应该重做整个 cockpit。应该保留现有交易员工作台骨架：

```text
Topbar
SideRail
TokenRadarTable
LiveSignalTape
TokenDetailDrawer
```

只把旧 `NarrativePanel` 替换成 harness 工作流视图，并在右侧 drawer 增加与 selected signal/token 相关的闭环详情。

UI 目标不是“展示更多信息”，而是让交易员能沿着一条链路快速判断：

```text
谁制造了 attention seed
原文 anchor 是什么
是否有 token uptake
系统冻结了什么 snapshot
shadow decision 是什么
outcome 是否结算
credit 怎么分配
score bucket 是否说明系统有 edge
```

## 基于当前页面的观察

我在 `http://localhost:8765/` 观察到的当前真实页面是一个高密度交易 cockpit，不是空白应用。当前屏幕结构如下：

```text
Topbar:
  intel.cockpit
  token/socket/status
  global search
  MATCHED / flow / enrich counters
  refresh

Left SideRail:
  views: Live / Tokens / Narratives / Accounts / Jobs/Ops
  window: 5m / 1h / 24h
  scope: watched / all stream
  handle filter
  decisions
  watchlist

Center:
  Token Radar table
  bottom deck:
    LiveSignalTape
    NarrativePanel
    SearchResults

Right:
  TokenDetailDrawer
  empty state: Select Token
```

当前页面已经做对的部分：

- `TokenRadarTable` 是主工作区，应该继续作为首页中心；
- `LiveSignalTape` 是实时脉冲，不应该被 harness report 替代；
- `SideRail` 已经承担全局窗口、范围和 watched handles 过滤；
- `TokenDetailDrawer` 是正确的详情承载面；
- 视觉语言是工业/交易终端风格，适合继续做高密度信息，而不是重做成 dashboard 卡片页。

当前页面需要换芯的部分：

- `Narratives` 作为左侧一级视图会继续强化旧叙事心智；
- 中间底部 `叙事流` 面板只展示 topic/seed link，不展示闭环状态；
- 右侧 drawer 的 `Narratives` tab 会继续让用户把 narrative 当交易对象；
- topbar 的 `enrich` counter 只说明 LLM job，不说明 harness 是否闭环健康；
- left rail 的 `decisions` 当前来自 token opportunity，不区分 harness shadow decision。

所以 MVP UI 的改造点非常明确：

```text
SideRail: Narratives -> Harness
BottomDeck: NarrativePanel -> HarnessPanel
RightDrawer: Narratives tab -> Harness tab
Topbar/Health: enrich counter 后续补 harness health
```

这不是视觉大改，而是产品对象替换。

## 当前页面替换地图

### 必须保留

```text
Topbar
Searchbar
StatusPills
SideRail layout
TokenRadarTable
LiveSignalTape
SearchResults
TokenDetailDrawer shell
Token Timeline / Posts / Score / Accounts tabs
```

这些是现有工作流基础，重做它们会违反 KISS。

### 必须替换

```text
SideRail "Narratives" button
NarrativePanel component
TokenDetailDrawer "Narratives" tab
SelectedSignal kind="narrative"
NarrativeFlowData as product-facing type
```

替换后：

```text
SideRail "Harness"
HarnessPanel
TokenDetailDrawer "Harness" tab
SelectedSignal kind="social_event" | "attention_seed" | "harness_snapshot"
SocialEventData / AttentionSeedData / HarnessSnapshotData
```

### 可以后置

```text
ScoreBucketPanel
SettlementCoveragePanel
WeightDriftPanel
Dedicated Harness Evaluation view
```

这些是评估层，不阻塞第一版 UI 替换。

## MVP 页面线框

### 当前页面目标形态

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ intel.cockpit  status/search                         MATCHED flow harness  │
├──────────────┬──────────────────────────────────────────────┬───────────────┤
│ SideRail     │ Center                                       │ DetailDrawer  │
│              │                                              │               │
│ Live         │ Token Radar                                  │ selected obj   │
│ Tokens       │                                              │               │
│ Harness      │ token rows remain primary                    │ Trace          │
│ Outcomes     │                                              │ Snapshot       │
│ Ops          │                                              │ Outcome        │
│              ├──────────────────────────────────────────────┤ Credit         │
│ window       │ LiveSignalTape | HarnessPanel | Search       │               │
│ scope        │                                              │               │
└──────────────┴──────────────────────────────────────────────┴───────────────┘
```

### BottomDeck MVP

```text
LiveSignalTape
  - event/token pulses
  - unchanged

HarnessPanel
  - health strip
  - Events / Seeds / Snapshots segmented control
  - compact rows

SearchResults
  - unchanged
```

### DetailDrawer MVP

如果选择 token：

```text
Header: token identity + opportunity score
Tabs: Timeline / Posts / Score / Harness / Accounts
Harness tab:
  Linked Seeds
  Active Snapshots
  Latest Outcome
  Credit Rows
```

如果选择 social event / seed / snapshot：

```text
Header: author + event_type + status
Tabs: Trace / Snapshot / Outcome / Credit
```

实现上可以先复用 `TokenDetailDrawer` shell，后续再抽出通用 `DetailDrawerShell`。

## MVP UI 原则

### 1. 不做大屏重构

现有布局已经符合 operational cockpit：

```text
left rail: filters / windows / watchlist
center: token radar + live tape + compact panels
right drawer: selected token detail
```

MVP 不改变三栏结构，不做 landing page，不做大 hero，不做装饰性图形。

### 2. 不用旧 narrative 兼容语义

旧 UI 里的 `Narratives` 不是简单改名。它应该被替换为：

```text
Harness
Seeds
Snapshots
Outcomes
Credits
```

不要在 UI 中 fallback 到旧 `narrative_label`。如果新 harness 数据不存在，显示明确状态：

```text
harness_not_started
outcome_pending
missing_market
no_credit_yet
```

### 3. MVP 只服务 shadow 闭环

UI 不显示 live trading 操作，不显示下单按钮，不显示仓位建议。

允许显示：

```text
shadow_signal
paper_signal, if later enabled
risk_reject_reason
outcome_status
credit
```

### 4. 高密度、低装饰

继续使用当前视觉语言：

- 深色底；
- JetBrains Mono 数字；
- amber 作为注意力/active；
- blue 作为 watch/info；
- red/green 只用于方向和异常收益；
- 小圆角；
- 表格和 compact panel 优先；
- 不使用大卡片堆叠。

## 信息架构

MVP UI 有三层。

### 第一层：实时发现

位置：中心底部，替换旧叙事流 compact panel。

组件：

```text
HarnessPanel
  -> SocialEventFeed
  -> AttentionSeedList
  -> HarnessHealthStrip
```

回答：

```text
现在有哪些 watched account social events？
哪些成为了 attention seed？
LLM/harness 是否正常？
```

### 第二层：单对象详情

位置：右侧 `TokenDetailDrawer` 或新 `HarnessDetailDrawer` tab。

组件：

```text
HarnessTrace
SnapshotLedger
OutcomeCard
CreditLedger
EvidenceRail
```

回答：

```text
这条 seed/snapshot 的完整证据链是什么？
为什么 shadow long/watch/no_trade？
有没有结算？
credit 分给了谁？
```

### 第三层：效果评估

位置：后续独立 compact panel 或右侧 drawer 的 `Evaluation` tab。

组件：

```text
ScoreBucketPanel
WeightDriftPanel
SettlementCoveragePanel
```

回答：

```text
系统有没有 edge？
哪些分数区间有效？
哪些 source/event_type/horizon 在变好或变差？
```

## 新 API 数据模型

UI 不直接消费数据库字段，而消费 read models。

### `SocialEventItem`

```ts
export type SocialEventItem = {
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  schema_version: "social-event-v1" | string;
  event_type: string;
  source_action: string;
  subject: string;
  direction_hint: "attention_positive" | "attention_negative" | "neutral" | string;
  attention_mechanism: string;
  impact_hint: number;
  semantic_novelty_hint: number;
  confidence: number;
  is_signal_event: boolean;
  anchor_terms: AnchorTerm[];
  token_candidates: SocialTokenCandidate[];
  semantic_risks: string[];
  summary_zh: string;
  event?: EventRecord | null;
};
```

### `AttentionSeedItem`

```ts
export type AttentionSeedItem = {
  seed_id: string;
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  event_type: string;
  subject: string;
  anchor_terms: AnchorTerm[];
  token_uptake_count: number;
  top_linked_symbols: string[];
  seed_status: "seed_only" | "linked" | "snapshot_ready" | "outcome_pending" | "settled" | string;
  risks: string[];
};
```

### `HarnessSnapshotItem`

```ts
export type HarnessSnapshotItem = {
  snapshot_id: string;
  asset: string;
  decision_time_ms: number;
  horizon: "6h" | "24h" | string;
  combined_score: number;
  policy_signal: "NO_TRADE" | "LONG" | "SHORT_OR_AVOID" | string;
  shadow_signal: "NO_TRADE" | "LONG_SMALL" | "SHORT_SMALL" | string;
  event_clusters: HarnessClusterSummary[];
  market_state: Record<string, unknown>;
  versions: HarnessVersionBlock;
  outcome_status: "pending" | "settled" | "missing_market" | "insufficient_market_data" | string;
  credit_status: "none" | "assigned" | string;
  risks: string[];
};
```

### `HarnessOutcomeItem`

```ts
export type HarnessOutcomeItem = {
  snapshot_id: string;
  settled_at_ms: number;
  actual_return: number;
  expected_return: number;
  abnormal_return: number;
  realized_vol: number;
  normalized_outcome: number;
  baseline_version: string;
};
```

### `HarnessCreditItem`

```ts
export type HarnessCreditItem = {
  credit_id: string;
  snapshot_id: string;
  cluster_id: string;
  asset: string;
  event_type: string;
  source: string;
  horizon: string;
  event_score: number;
  responsibility: number;
  credit: number;
  created_at_ms: number;
};
```

### `ScoreBucketItem`

```ts
export type ScoreBucketItem = {
  bucket: "<=-0.8" | "-0.8~-0.4" | "-0.4~0.4" | "0.4~0.8" | ">=0.8" | string;
  sample_count: number;
  avg_normalized_outcome: number;
  avg_abnormal_return: number;
  hit_rate: number;
  settled_count: number;
  pending_count: number;
};
```

## 顶层布局设计

### 保留 `App.tsx` 的主骨架

现有 `App.tsx` 中：

```tsx
<main className="cockpit-shell">
  <header className="topbar" />
  <div className="cockpit-grid">
    <aside className="side-rail" />
    <section className="center-column" />
    <TokenDetailDrawer />
  </div>
</main>
```

MVP 保留。

### 修改点

#### 1. SideRail views

从：

```text
Live
Tokens
Narratives
Accounts
Jobs/Ops
```

改成：

```text
Live
Tokens
Harness
Outcomes
Ops
```

说明：

- `Harness` 指当前窗口 social events / seeds / snapshots；
- `Outcomes` 指 settled reports；
- `Ops` 指 jobs、schema、settlement coverage。
- `Live` 和 `Tokens` 保持当前位置，避免用户重新学习主路径。

#### 2. Center bottom deck

现有：

```text
LiveSignalTape | NarrativePanel | SearchResults
```

改成：

```text
LiveSignalTape | HarnessPanel | SearchResults
```

当前 `NarrativePanel` 所在区域高度和密度适合直接替换。`HarnessPanel` 不应该比旧面板更高，否则会挤压 Token Radar 的可视行数。

#### 3. TokenDetailDrawer tabs

现有：

```text
Timeline
Posts
Score
Narratives
Accounts
```

改成：

```text
Timeline
Posts
Score
Harness
Accounts
```

`Harness` tab 只显示和当前 token 相关的 seeds/snapshots/credits。

## 当前组件改造清单

### `App.tsx`

当前 `App.tsx` 已经承担 query、socket、selection、layout。MVP 不要求立刻拆大文件，但 harness 查询和 selection 应集中在一个小块里，避免散落。

新增查询：

```ts
const socialEventsQuery = useQuery({
  queryKey: ["social-events", windowKey, handles],
  queryFn: () => getApi<SocialEventsData>("/api/social-events", {
    token,
    params: { window: windowKey, limit: 50, handles }
  }),
  enabled: Boolean(token),
  refetchInterval: 10_000
});

const attentionSeedsQuery = useQuery({
  queryKey: ["attention-seeds", windowKey, handles],
  queryFn: () => getApi<AttentionSeedsData>("/api/attention-seeds", {
    token,
    params: { window: windowKey, limit: 50, handles }
  }),
  enabled: Boolean(token),
  refetchInterval: 10_000
});

const harnessSnapshotsQuery = useQuery({
  queryKey: ["harness-snapshots", windowKey, harnessHorizon],
  queryFn: () => getApi<HarnessSnapshotsData>("/api/harness-snapshots", {
    token,
    params: { window: windowKey, horizon: harnessHorizon, limit: 50 }
  }),
  enabled: Boolean(token),
  refetchInterval: 15_000
});
```

删除或替换：

```ts
const narrativeQuery = ...
const narratives = ...
SelectedSignal kind: "narrative"
```

新增 selected kinds：

```ts
type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "social_event"; item: SocialEventItem }
  | { kind: "attention_seed"; item: AttentionSeedItem }
  | { kind: "harness_snapshot"; item: HarnessSnapshotItem }
  | { kind: "alert"; item: AlertRecord }
  | { kind: "search"; item: SearchItem }
  | { kind: "query"; query: string }
  | null;
```

### `TokenDetailDrawer.tsx`

当前 tabs：

```ts
Timeline / Posts / Score / Narratives / Accounts
```

改为：

```ts
Timeline / Posts / Score / Harness / Accounts
```

`TokenDetailTab` 类型同步：

```ts
export type TokenDetailTab = "timeline" | "posts" | "score" | "harness" | "accounts";
```

新增 props：

```ts
harnessSeeds: AttentionSeedItem[];
harnessSnapshots: HarnessSnapshotItem[];
harnessOutcomes: HarnessOutcomeItem[];
harnessCredits: HarnessCreditItem[];
isHarnessLoading: boolean;
```

删除 props：

```ts
narratives
narrativeLinks
llmConfigured
```

如果仍要显示 LLM 配置状态，应通过 `HarnessHealthStrip`，不是 token drawer 的 narrative tab。

### `LiveSignalTape.tsx`

当前 tape 支持 token/frontier/event。

MVP 改为支持：

```text
token
social_event
attention_seed
harness_snapshot
event
```

Tape row 不展示完整 snapshot，只展示脉冲：

```text
SEED @cz_binance · meme_phrase_seed · build on BNB
SNAP BNB · shadow LONG_SMALL · score .42
```

### `NarrativePanel.tsx`

删除或重写为 `HarnessPanel.tsx`。

不要在文件中保留旧 `NarrativeFlowRow`、`FrontierRow` 语义。旧 `AttentionFrontierItem` 如果继续存在，也应该重命名为 harness/token uptake read model。

### `api/types.ts`

新增 harness types 后，删除旧 product-facing narrative types：

```text
NarrativeFlowData
NarrativeFlowItem
AttentionFrontierData, if it still uses narrative wording
AttentionFrontierItem, if not renamed
```

如果后端仍保留 `/api/attention-frontier`，前端 type 名应该表达新语义：

```ts
type HarnessTokenUptakeItem = ...
```

更推荐后端也改名，避免旧词污染。

## 组件树

```text
App
  Topbar
  SideRail
    RailSection
    RailButton
  CenterColumn
    TokenRadarTable
    BottomDeck
      LiveSignalTape
      HarnessPanel
        HarnessHealthStrip
        SocialEventFeed
        AttentionSeedList
      SearchResultsPanel
  TokenDetailDrawer
    TokenTimeline
    TokenPostsTab
    ScoreLedger
    HarnessTokenTab
      TokenSeedLinks
      SnapshotLedger
      OutcomeCard
      CreditLedger
    AccountLane
```

后续评估页：

```text
HarnessEvaluationPanel
  ScoreBucketPanel
  SettlementCoveragePanel
  WeightDriftPanel
```

## 组件详细设计

## 1. `HarnessPanel`

### 目的

替换旧 `NarrativePanel`，作为实时 harness 入口。

它不是大报告，只是一个 compact panel，展示最近的 social events、attention seeds 和 harness 状态。

### 位置

`App.tsx` 的 `bottom-deck` 第二列。

### Props

```ts
type HarnessPanelProps = {
  socialEvents: SocialEventItem[];
  seeds: AttentionSeedItem[];
  snapshots: HarnessSnapshotItem[];
  health: HarnessHealth;
  selectedId?: string | null;
  isLoading?: boolean;
  onSelectEvent: (item: SocialEventItem) => void;
  onSelectSeed: (item: AttentionSeedItem) => void;
  onSelectSnapshot: (item: HarnessSnapshotItem) => void;
};
```

### 布局

```text
header:
  Harness · social-event-v1 · schema pass %

body:
  health strip
  tabs: Events / Seeds / Snapshots
  compact rows
```

### Row 信息

每行最多两层：

```text
@cz_binance · meme_phrase_seed · 4m ago
build on BNB · attention_positive · conf 0.88
```

不要在 row 内放长解释。长解释进入右侧详情。

### 状态

```text
loading: "加载 harness state"
empty: "当前窗口暂无 social event"
llm off: "LLM extractor disabled"
schema failing: "schema failure rate high"
```

### 设计约束

- 使用现有 `.compact-panel` 样式；
- 不做卡片内嵌卡片；
- tab 使用现有 `.segmented`；
- row 高度稳定，避免 live updates 抖动。

## 2. `HarnessHealthStrip`

### 目的

告诉用户闭环是否在生产意义上健康，而不是只告诉 LLM 是否开启。

### Props

```ts
type HarnessHealth = {
  llm_configured: boolean;
  extractor_running: boolean;
  schema_success_rate?: number | null;
  pending_jobs: number;
  snapshots_24h: number;
  pending_outcomes: number;
  settlement_coverage?: number | null;
};
```

### 显示字段

```text
schema 96%
snap 42
pending 18
settled 73%
```

### 颜色

- schema success >= 95%: green;
- 80-95%: amber;
- <80%: red;
- settlement coverage missing: muted.

### KISS 约束

只显示 4 个指标，不做复杂监控页。

## 3. `SocialEventFeed`

### 目的

展示 LLM 从高价值 watched account 动态抽出的结构化 social event。

### Props

```ts
type SocialEventFeedProps = {
  items: SocialEventItem[];
  selectedId?: string | null;
  compact?: boolean;
  onSelect: (item: SocialEventItem) => void;
};
```

### Row 结构

```text
left:
  author + event_type + time

middle:
  subject
  anchor chips

right:
  impact / novelty / confidence
```

### Row 示例

```text
@elonmusk · product_or_ai_update · 2m
Grok product progress
[Grok] [xAI]    impact .72 novelty .68 conf .86
```

### 交互

点击 row：

- `selectedSignal = { kind: "social_event", item }`;
- 右侧 drawer 打开 `HarnessTrace`。

### 风险显示

semantic risks 只显示前 2 个 chip：

```text
sarcasm_or_joke
ambiguous_reference
```

不要把所有风险塞满 row。

## 4. `AttentionSeedList`

### 目的

展示哪些 social events 已经成为 attention seed，以及是否有 token uptake。

### Props

```ts
type AttentionSeedListProps = {
  items: AttentionSeedItem[];
  selectedSeedId?: string | null;
  onSelect: (item: AttentionSeedItem) => void;
};
```

### Row 结构

```text
@heyi · exchange_or_listing_hint · seed_only
anchor: "Binance Alpha"
links: BNB, CAKE · risks: unresolved_symbol
```

### 状态标签

```text
seed_only
linked
snapshot_ready
outcome_pending
settled
```

### 视觉语义

- `seed_only`: muted;
- `linked`: blue;
- `snapshot_ready`: amber;
- `settled`: green/red according to normalized outcome if available.

## 5. `HarnessTrace`

### 目的

右侧详情里的完整链路视图。

### Props

```ts
type HarnessTraceProps = {
  socialEvent?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
};
```

### 布局

使用纵向 timeline，不使用大流程图。

```text
1 Extracted
  @cz · event_type · anchor terms

2 Seed
  seed_status · token uptake count

3 Snapshot
  combined_score · shadow_signal · horizon

4 Outcome
  pending / settled / missing_market

5 Credit
  cluster credit rows
```

### 重要约束

不要写成“因果链”。标题用：

```text
Trace
Predictive Credit
Outcome
```

不要用：

```text
Cause
Why price moved
```

## 6. `SnapshotLedger`

### 目的

展示 snapshot 的事前冻结状态。

### Props

```ts
type SnapshotLedgerProps = {
  snapshot: HarnessSnapshotItem | null;
};
```

### 显示内容

```text
snapshot_id
asset
horizon
combined_score
shadow_signal
policy_signal
decision_time
versions
risks
```

### 版本显示

版本信息默认折叠：

```text
versions: config/news-social-mvp-v1 · prompt/social-event-v1 · scoring/harness-score-v1
```

点击展开：

```text
config_version
prompt_version
schema_version
scoring_version
weight_version
policy_version
risk_version
baseline_version
```

### KISS 约束

不做 JSON viewer。版本字段用 key-value rows。

## 7. `OutcomeCard`

### 目的

展示 horizon 到期后的结算结果。

### Props

```ts
type OutcomeCardProps = {
  outcome?: HarnessOutcomeItem | null;
  status: HarnessSnapshotItem["outcome_status"];
};
```

### 状态

```text
pending
settled
missing_entry_price
missing_exit_price
missing_baseline
insufficient_market_data
```

### Settled 显示

```text
actual_return
expected_return
abnormal_return
realized_vol
normalized_outcome
baseline_version
```

### 视觉

- normalized_outcome > 0: green number;
- normalized_outcome < 0: red number;
- pending/missing: muted with reason;
- 不用大号 PnL，避免被误解成实盘收益。

## 8. `CreditLedger`

### 目的

展示多事件 predictive credit，而不是因果归因。

### Props

```ts
type CreditLedgerProps = {
  credits: HarnessCreditItem[];
};
```

### Row

```text
event_type · source · horizon
event_score .36 · responsibility 47% · credit +.261
```

### 空状态

```text
outcome_not_settled
credit_not_assigned
```

### 设计约束

明确文案：

```text
Predictive credit, not causal proof.
```

这句可以放 tooltip 或小字，不要做大段说明。

## 9. `HarnessTokenTab`

### 目的

替换 `TokenDetailDrawer` 里的 `Narratives` tab，显示当前 token 和 harness 之间的关系。

### Props

```ts
type HarnessTokenTabProps = {
  token: TokenFlowItem;
  seeds: AttentionSeedItem[];
  snapshots: HarnessSnapshotItem[];
  outcomes: HarnessOutcomeItem[];
  credits: HarnessCreditItem[];
  isLoading?: boolean;
  onSelectSnapshot: (snapshot: HarnessSnapshotItem) => void;
};
```

### 内容顺序

```text
1. Linked Seeds
2. Active Snapshots
3. Latest Outcome
4. Credit Rows
```

### 为什么放在 token drawer

交易员从 token radar 进入时，最自然的问题是：

```text
这个 token 的热度是不是被某个 high-value account seed 拉起来的？
```

所以 token drawer 的 harness tab 应该回答这个问题，而不是展示全局 social events。

## 10. `ScoreBucketPanel`

### 目的

展示 MVP 是否真的有 edge。

### Props

```ts
type ScoreBucketPanelProps = {
  items: ScoreBucketItem[];
  horizon: string;
  isLoading?: boolean;
};
```

### 图形选择

MVP 不引入图表库。

用 CSS table + horizontal bars：

```text
bucket      n    avg y    hit
<=-.8      12   -.31     33%
-.8~-.4    31   -.12     42%
-.4~.4     90   +.01     51%
.4~.8      28   +.14     61%
>=.8       10   +.29     70%
```

### 成功/失败状态

```text
monotonic: ready / weak / failed / insufficient_sample
```

### KISS 约束

只显示 score bucket，不做多维可视化。

## 11. `SettlementCoveragePanel`

### 目的

避免用户误以为没有 outcome 就是信号失败。

### Props

```ts
type SettlementCoveragePanelProps = {
  total_snapshots: number;
  settled: number;
  pending: number;
  missing_market: number;
  insufficient_market_data: number;
};
```

### 显示

```text
settled 73%
pending 18
missing_market 7
insufficient 4
```

### 位置

ScoreBucketPanel 附近，或者 Ops/Harness evaluation drawer。

## 12. `WeightDriftPanel`

### 目的

只做 report-only，避免 UI 暗示权重已经影响 live scoring。

### Props

```ts
type WeightDriftPanelProps = {
  items: HarnessWeightItem[];
};
```

### Row

```text
source:cz_binance · 6h · n=83 · mean_credit +.042 · weight 1.02
event_type:meme_phrase_seed · 24h · n=42 · report_only
```

### 状态标签

```text
report_only
candidate
active
```

MVP 只允许 `report_only`。

## App 状态设计

### 新 store 字段

```ts
type HarnessView = "events" | "seeds" | "snapshots" | "outcomes" | "evaluation";
type HarnessDetailTab = "trace" | "snapshot" | "outcome" | "credit";

type TraderState additions = {
  harnessView: HarnessView;
  selectedHarnessId: string | null;
  harnessHorizon: "6h" | "24h";
  setHarnessView: (view: HarnessView) => void;
  setSelectedHarnessId: (id: string | null) => void;
  setHarnessHorizon: (horizon: "6h" | "24h") => void;
};
```

### 修改 `SelectedSignal`

从：

```ts
{ kind: "narrative"; item: AttentionFrontierItem }
```

改成：

```ts
| { kind: "social_event"; item: SocialEventItem }
| { kind: "attention_seed"; item: AttentionSeedItem }
| { kind: "harness_snapshot"; item: HarnessSnapshotItem }
```

`narrative` kind 删除。

## React Query 设计

### 新 query keys

```ts
["social-events", windowKey, handles]
["attention-seeds", windowKey, handles]
["harness-snapshots", windowKey, harnessHorizon]
["harness-outcomes", windowKey, harnessHorizon]
["harness-credits", selectedSnapshotId]
["harness-score-buckets", harnessHorizon]
["harness-health"]
```

### Refetch interval

```text
social-events: 10s
attention-seeds: 10s
harness-snapshots: 15s
outcomes: 30s
score-buckets: 60s
weights: 60s
```

### KISS 约束

不要在前端做 credit/score 计算，只展示后端 read model。

## 文件变更计划

### 新增组件文件

```text
web/src/components/HarnessPanel.tsx
web/src/components/HarnessHealthStrip.tsx
web/src/components/SocialEventFeed.tsx
web/src/components/AttentionSeedList.tsx
web/src/components/HarnessTrace.tsx
web/src/components/SnapshotLedger.tsx
web/src/components/OutcomeCard.tsx
web/src/components/CreditLedger.tsx
web/src/components/HarnessTokenTab.tsx
web/src/components/ScoreBucketPanel.tsx
web/src/components/SettlementCoveragePanel.tsx
web/src/components/WeightDriftPanel.tsx
```

### 修改文件

```text
web/src/App.tsx
web/src/api/types.ts
web/src/api/client.ts
web/src/store/useTraderStore.ts
web/src/components/TokenDetailDrawer.tsx
web/src/components/LiveSignalTape.tsx
web/src/styles.css
web/src/App.test.tsx
```

### 删除或替换

```text
web/src/components/NarrativePanel.tsx
```

可以删除文件，或者先重命名/重写成 `HarnessPanel.tsx`。不要保留旧 `NarrativePanel` 语义。

## CSS 设计

### 新 class 命名

```text
harness-panel
harness-health-strip
harness-feed
harness-row
harness-row.selected
harness-anchor-chip
harness-risk-chip
harness-trace
harness-trace-step
snapshot-ledger
outcome-card
credit-ledger
score-bucket-panel
score-bucket-row
weight-drift-row
```

### 视觉约束

- 复用 `--panel`, `--line`, `--accent`, `--green`, `--red`, `--blue`；
- row height 固定在 54-76px；
- chips 不能撑高行；
- 长文本最多两行；
- 所有数字用 `var(--mono)`；
- 不新增主色；
- 不用卡片嵌套卡片。

### 状态颜色

```text
attention_positive: amber
attention_negative: red
neutral: muted
settled positive outcome: green
settled negative outcome: red
pending/missing: muted
schema unhealthy: red
schema warning: amber
```

## 交互设计

### 点击 social event

```text
select social event
-> right drawer shows HarnessTrace
-> active stage = Extracted
```

### 点击 attention seed

```text
select seed
-> right drawer shows HarnessTrace
-> active stage = Seed
```

### 点击 snapshot

```text
select snapshot
-> right drawer shows SnapshotLedger + OutcomeCard + CreditLedger
```

### 点击 token radar row

现有行为保留：

```text
select token
-> TokenDetailDrawer timeline
```

如果该 token 有 harness links，drawer header 显示一个小 badge：

```text
harness linked 3
```

### 键盘

保持现有：

```text
1/2/3 switch windows
/ search
```

新增可以后置，不进 MVP。

## 空状态设计

### `HarnessPanel`

```text
当前窗口暂无 social event
```

### LLM disabled

```text
LLM extractor disabled
```

### Schema unhealthy

```text
social-event-v1 schema failure high
```

### Outcome pending

```text
outcome pending · horizon not reached
```

### Missing market

```text
missing market data · cannot settle
```

### No credit

```text
credit not assigned
```

## 测试设计

### Component tests

`App.test.tsx` 覆盖：

- HarnessPanel empty state；
- social event row render；
- attention seed row render；
- selected social event opens right-side trace；
- token drawer shows Harness tab；
- old `Narratives` tab 不存在；
- score bucket table renders sample counts；
- outcome pending/missing/settled 三种状态。

### Type tests

如果当前工具链不方便单独做 type tests，则由 `npm run typecheck` 覆盖。

### Snapshot 不建议

不做大 snapshot tests。UI 是高密度 cockpit，快照测试会脆。

## MVP 实施阶段

### UI Stage 1: HarnessPanel 替换 NarrativePanel

目标：

```text
底部中间面板显示 social events / seeds / snapshots
```

涉及：

```text
types
queries
HarnessPanel
SocialEventFeed
AttentionSeedList
HarnessHealthStrip
App.tsx bottom-deck
```

不改 drawer。

### UI Stage 2: TokenDetailDrawer 增加 Harness tab

目标：

```text
选中 token 后能看到相关 seeds/snapshots/outcomes/credits
```

涉及：

```text
TokenDetailDrawer
HarnessTokenTab
SnapshotLedger
OutcomeCard
CreditLedger
```

删除 `Narratives` tab。

### UI Stage 3: Evaluation compact view

目标：

```text
能看 score bucket 和 settlement coverage
```

涉及：

```text
ScoreBucketPanel
SettlementCoveragePanel
WeightDriftPanel(report-only)
```

### UI Stage 4: Polish only after data proves useful

目标：

```text
调整密度、排序、筛选和 selected states
```

不新增概念。

## 后端就绪门槛

UI 重构不能先于闭环 read model 太多，否则前端会被迫伪造 harness 状态。MVP 前端可以在 mock data 下开发组件，但合并到主 cockpit 前至少需要这些 API 契约稳定：

```text
/api/social-events
/api/attention-seeds
/api/harness-snapshots
/api/harness-outcomes
/api/harness-credits
/api/harness-health
```

其中第一刀必须有：

```text
social-events
attention-seeds
harness-snapshots
harness-health
```

`outcomes` 和 `credits` 可以先显示 pending/empty，但字段名必须固定。否则 UI 很容易把缺失数据解释成旧 narrative empty state。

## 对现有页面的影响评估

### 用户心智影响

当前页面的问题不是信息少，而是“叙事”这个对象太软。替换成 Harness 后，用户心智会从：

```text
这个话题是什么？
```

变成：

```text
这条 watched account 动态制造了什么 attention seed？
有没有 token uptake？
系统是否冻结 snapshot？
shadow decision 和 outcome 是什么？
credit 是否支持这个信号家族？
```

这是正向影响。代价是页面初期会显得更冷、更工程化，但更接近交易生产。

### 信息密度影响

MVP 不增加主屏层级，只替换旧 `NarrativePanel`，所以不会显著压缩 `TokenRadarTable` 的可视行数。

风险点：

```text
Harness row 字段过多
Snapshot/outcome 状态塞进底部面板
Score bucket 提前进入主屏
```

规避方法：

```text
底部 HarnessPanel 只做入口
完整 trace 放右侧 drawer
score bucket 放 evaluation view
```

### 交易价值影响

正向：

- 能看到 CZ/Musk/何一这类账号动态和 token uptake 的连接；
- 能区分 seed-only 和 snapshot-ready；
- 能看到 shadow decision，不再只看“热闹话题”；
- outcome/credit 出来后，可以判断某类 social event 是否真的有预测力。

负向：

- 旧 narrative count 会消失，表面上信号数量可能减少；
- 没有 settlement 的窗口会显示 pending，不会强行给结论；
- 一些有趣但不可结算的话题不会再被包装成交易信号。

这个负向是有意的。MVP 的目标不是让页面更热闹，而是让每个 surfaced signal 都能进入闭环。

### 工程影响

需要改动的前端 surface 较集中：

```text
web/src/App.tsx
web/src/api/types.ts
web/src/store/useTraderStore.ts
web/src/components/NarrativePanel.tsx
web/src/components/TokenDetailDrawer.tsx
web/src/components/LiveSignalTape.tsx
web/src/styles.css
```

不需要重写：

```text
TokenRadarTable
TokenTimeline
TokenPostsTab
ScoreLedger
AccountLane
SearchResults
WebSocket base client
```

因此 UI 改造是局部换芯，不是全站重构。

### 运维影响

Topbar 的 `enrich` counter 不足以代表 harness 健康。后续应把它拆成更接近生产闭环的健康信号：

```text
schema success rate
pending extraction jobs
snapshot count
pending outcomes
settlement coverage
```

MVP 可以先在 `HarnessHealthStrip` 展示，不急着改 Topbar。等用户确认这些指标真的有用，再把其中 1 到 2 个提升到 Topbar。

## MVP 验收标准

UI MVP 完成时，必须满足：

```text
1. 左侧不再出现 Narratives 一级入口
2. 底部不再渲染 NarrativePanel
3. token drawer 不再有 Narratives tab
4. SelectedSignal 不再有 kind="narrative"
5. HarnessPanel 能显示 social events / seeds / snapshots 三类对象
6. 点击 social event / seed / snapshot 能打开右侧 trace
7. token drawer 的 Harness tab 能显示相关 seed/snapshot/outcome/credit
8. outcome pending / settled / missing_market 三种状态显示清楚
9. score bucket 只在 evaluation 区域显示，不抢主屏
10. 没有任何 UI fallback 到旧 narrative_label
```

视觉验收：

```text
1. 1440px 桌面宽度下三栏不重叠
2. 1024px 宽度下 row 文本不溢出按钮或 chips
3. live update 不导致 bottom deck 高度抖动
4. Harness rows 每行最多两层文本
5. 数字列对齐，score/credit 使用等宽数字
```

测试验收：

```text
npm run typecheck
npm test -- --run
npm run build
```

如果后端一起改动，还必须跑：

```text
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

## 是否遵循 KISS

推荐方案符合 KISS，原因是：

```text
保留 cockpit shell
只替换旧叙事组件
不新增图表库
不新增复杂路由
不把后端 score/credit 计算搬到前端
不做 live trading 操作
不保留旧 narrative fallback
```

不符合 KISS 的做法包括：

```text
先做完整 evaluation dashboard
先做 graph/Sankey
先做多页面信息架构
在前端模拟 settlement/credit
保留 Narratives 和 Harness 双入口
```

因此 UI 第一刀应该只做：

```text
NarrativePanel -> HarnessPanel
Narratives tab -> Harness tab
SelectedSignal narrative -> social_event/attention_seed/snapshot
```

这三件事完成，产品对象就换掉了。

## 反模式清单

不要做：

- 大屏 hero；
- 复杂 Sankey/graph；
- embedding cluster 可视化；
- 多 agent trace UI；
- 下单按钮；
- PnL 英雄数字；
- 旧 narrative fallback；
- 旧 narrative label badge；
- 过早 Weight Drift 主屏；
- 复杂 dashboard 多页导航。

## 最终 MVP UI 效果

交易员看到的是：

```text
左侧:
  window / scope / watched handles

中间:
  token radar
  live tape
  harness panel
  search

右侧:
  selected token / event / seed / snapshot 的闭环详情
```

从操作上，他可以完成：

```text
看到 CZ/Musk/何一动态
查看 exact anchor terms
确认是否已有 token uptake
查看 shadow snapshot
等待/查看 outcome
查看 credit
查看 score bucket 是否有 edge
```

这就是 MVP UI 的边界。它不是更漂亮的叙事流，而是闭环 harness 的控制台。
