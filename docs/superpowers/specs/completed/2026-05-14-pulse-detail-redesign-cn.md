# Spec — Pulse Detail Page Redesign

**Status**: Draft, awaiting review
**Date**: 2026-05-14
**Branch**: `main`
**Related**:
- `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`
- `docs/superpowers/specs/active/2026-05-11-frontend-experience-architecture-hard-cut.md`
- `docs/superpowers/specs/active/2026-05-13-frontend-architecture-design-language-review-cn.md`
- `docs/FRONTEND.md`
- `docs/CONTRACTS.md`
- 真实数据样本: `pulse-fa2a12fedd9332271732110ed8bd7b1b49065282` ($TITTY, solana, meme route)

## 一句话

把 `/signal-lab/pulse/<id>` 改成 researcher 的事实判读页：事实账本在前、agent 三段（Analyst / Critic / Judge）在右栏并列，原始推文按 timeline period 分组可读，gate 与 agent 失谐显式呈现。删除现有 `SignalLabInspector`，前端从 `decision_json` 单点输出迁到 `decision_json + pulse_agent_run_steps` 双源消费。

## 背景

### 当前页面的实际形态

`PulseDetailPage` 直接 mount `SignalLabInspector`，`SignalLabInspector` 同时被 `SignalLabPage` 队列右栏复用。两处都被 `signal-lab-inspector-pane` 这一约束面板宽度承载。`SignalLabInspector` 内部分 5 段：Case header / Agent memo / Fact ledger / Source events / Debug facts。

### 真实数据样本（$TITTY 这条 pulse）

- subject: solana token `gTi4ZMMM…krypump`, symbol `TITTY`
- `pulse_status: trade_candidate`、`score_band: high_conviction`、composite `rank_score 82`
- `decision.route: meme`、`decision.recommendation: trade_candidate`、`decision.confidence: 0.35`、`decision.stage_count: 3`
- 4 family 分数: social_heat 91 (rank 0.91), social_propagation 85 (rank 0.85), semantic_catalyst 50 (raw 0, missing), timing_risk 0 (data_health missing)
- `market.decision_latest` 存在但 `event_anchor: null`，`latest_status: stale`，缺位 119 分钟
- 5 条 source = 5 条 evidence，3 条来自 `@cache100x` (2.7K followers)，1 条 `@moontoklisting` (48.7K), 1 条 `@qkl2058` empty repost
- 3 个 stage 真实存在于 `pulse_agent_run_steps`，分别 3.7s / 4.9s / 6.1s：
  - Analyst: confidence 0.82，5 条 evidence bullet（中文）
  - Critic: confidence_ceiling 0.45 (↓ 0.82)，5 weaknesses + 4 missing_fact_impacts（英文）
  - Judge: confidence 0.35 (在 ceiling 之下)，summary 中文，5 residual_risks + 3 invalidation_conditions

### 实际问题（按第一性原理排序）

1. **agent 在事实之前。** 当前 Agent memo 在 Fact ledger 上面，违反 target-agent-architecture spec §2.1 "事实账本先于 agent 意见"。
2. **Stage 信息坍缩。** 三阶段 Analyst / Critic / Judge 只露 Judge final；Critic 的 confidence ceiling、weaknesses、missing_fact_impacts 完全不可见——而真实数据里 Critic 是把 0.82 压到 0.45 的关键节点，UI 上没有任何呈现。
3. **Gate 与 agent 不一致没被暴露。** $TITTY 是 deterministic gate `high_conviction (82)` 但 agent Judge `0.35`，这种"系统内分歧"是审计黄金信号，当前 UI 完全没标。
4. **Source events 是裸 ID。** `evidence_event_ids: ["gmgn:twitter_monitor_basic:616d…"]` 只显示字符串，不反查全文。用户连"哪个作者发的、几个 follower"都看不到，"为什么这个 token 被 surface"无法回答。
5. **数据新鲜度只用 `data_health` 枚举。** 真实情况是 `market anchor missing · decision_latest stale 119m`，但 UI 上只显示 `data_health: market=missing`。119 分钟这一具体延迟在 UI 上不存在。
6. **Stage / Gate 字段被重复展示两遍。** Case header 显示 Stage、Gate、Agent verdict，紧接着 Agent memo 又把 Stage / Gate 再列一次。视觉密度浪费。
7. **Debug facts 折在最底。** 但 `schema_version / prompt_version / pulse_version / gate_version` 这些恰好是 spec §5.2 RunAuditLedger 要求的回放必备字段。优先级反了。
8. **没有 abstain / risk_rejected 的视觉变体。** Spec 目标 high_conviction 占比 <15%，意味着大部分 pulse 会落到 abstain / watch / rejected，但 UI 没区分。

## 第一性原则

主用户是 **researcher**，不是 PM / trader。研究员要回答的核心问题（按打开页面后的视觉次序）：

| 顺序 | 问题 | 页面应回答 |
|---|---|---|
| 1 | 这是什么 token？为什么这时候出现？ | symbol + chain + 触发性 social burst |
| 2 | 系统看到的数据有多新鲜、缺什么？ | 6 维 freshness 颗粒（identity / social / event_anchor / decision_latest / cohort / alpha rank） |
| 3 | 事件按时间是怎么发生的？ | 4 节点 timeline: market_anchor / first / peak / now |
| 4 | 是哪种信号在推动？ | 4 factor family 分数 + 关键 facts |
| 5 | 市场端能不能撑？ | mcap / liq / vol / holders + stale 标记 |
| 6 | 系统看到的全部推文是什么？谁在喊？ | source events 全列表 + author concentration |
| 7 | Agent 三段是怎么得出 final 的？ | gate-vs-agent 张力 + Analyst → Critic ceiling → Judge final |
| 8 | 复现这次 run 需要什么？ | versions / run_id / replay 折叠 |

Agent 的输出是事实之上的"同侪意见"，不是页眉。Gate 与 agent 不一致时，UI 必须显式呈现，而不是隐藏在某个字段里。

## Goals

- **G1** 删除 `SignalLabInspector`、`pulseCase.ts`、CSS 中的 `signal-pulse-*` global 类。一次切净，不双轨。
- **G2** 新建 `PulseDetailView` 组件，作为 `/signal-lab/pulse/<id>` 路由与 `SignalLabPage` 队列内联视图的 **同一实现**。density 是 prop，不是分支组件。
- **G3** Dedicated 路由 (`/signal-lab/pulse/<id>`) 跳出 `SignalLabPage` 的两栏布局，独占 viewport。Hero 顶部加 `← back to queue` 链接；不在 dedicated 路由里嵌队列侧栏。`◀ prev · next ▶` mini-navigator 是 phase 2。
- **G4** 主列严格按"事实账本在前"组织：Hero → Timeline → Family grid → Market context → Evidence list。
- **G5** 右栏 Agent rail 同时显示 Analyst / Critic / Judge 三段，并在顶部高亮 gate-vs-agent 张力。
- **G6** Evidence 列表行 = 完整推文（time + handle + followers + body + flag），分组规则按 timeline period（pre-burst / burst / post-burst / latest）+ sticky toolbar。
- **G7** 时间统一用绝对 UTC 时间戳呈现，不使用相对 "T-Nm" 字样。
- **G8** Abstain / risk_rejected / 缺数据 用同骨架，在原位标 "missing / stale / gate-blocked"，不切换到错误页面。
- **G9** 新增 1 个后端端点（`/api/social-events/by-ids`）+ 1 个 read-model 字段扩展（pulse 返回 payload 包含 Analyst / Critic stage outputs），不改 DB schema。
- **G10** 删除当前 `SignalLabInspector.test.tsx` 中所有断言；新组件按子组件粒度独立单测，整页 fixture 用 $TITTY 真实数据快照。

## Non-Goals

- 不改 `pulse_agent_run_steps` / `pulse_agent_runs` / `pulse_candidates` 数据库 schema。
- 不改 agent runtime / `decision_json` schema / Analyst-Critic-Judge prompt 与契约。
- 不改 `SignalLabWorkbench`（队列左栏）。redesign 仅影响 inspector 面板与 dedicated route。
- 不重做 `Token Radar`、`Search Intel`、`Watchlist` 或其它路由。
- 不引入 dayjs / luxon 等额外时间库；用 `Intl.DateTimeFormat`。
- 不引入 chart 库；burst histogram 用 inline DOM (24 桶 div bar) 实现。
- 不引入 react-virtuoso；超过 100 行用 `react-window`（仓库未引入但 spec 接受作为 phase 2，phase 1 用纯滚动）。
- 不做 mobile breakpoint；目标 desktop / wide tablet（≥ 1024px viewport）。
- 不引入 tooltip / hover 浮层。
- 不为 evidence list 做 URL-synced filter；filter 状态本地，phase 2 再考虑深链接。

## 使用场景与 density

| 场景 | 路由 | 容器宽度 | density |
|---|---|---|---|
| Dedicated detail | `/signal-lab/pulse/<id>` | 跳出 `SignalLabPage` 的 inspector-pane，独占 ≥ 1024px viewport | `full` |
| Queue inline | `/signal-lab` 队列右栏 | `signal-lab-inspector-pane` 约束的窄列（≈ 460–640px） | `compact` |

`PulseDetailView` 接 `density: "full" | "compact"`。两者数据相同，仅排版与折叠默认值不同。下表是 region × density 的差异表。

| Region | full | compact |
|---|---|---|
| Hero | 3 栏（identity / burst 24-bar / freshness 6 行） | 2 栏（identity / burst 12-bar）；freshness 折成单行 chip 串 |
| Timeline | 4 节点横排 grid | 4 节点纵排 stack |
| Family grid | 2 × 2 | 1 × 4 纵排 |
| Market context | 4 metric 横排 | 2 × 2 |
| Evidence | 主体；toolbar sticky；分组默认展开 burst + latest | 主体；toolbar sticky；分组默认仅展开 burst |
| Agent rail | 右栏 sticky 全展 | 整段折到底部 accordion；Judge 默认展开，Analyst / Critic 默认收起 |

## UI 信息架构

### Hero

**字段：**

- Identity 栏：`$SYMBOL` (Berkeley Mono 22px) + chain + 缩短地址 + market_type
- Pills（≤ 4 个，按真实状态出现）：
  - `score_band` (来自 `score_band`)，tone = opportunity / health / info / risk
  - `route` (来自 `decision.route`)，tone = info
  - `decision.recommendation` (来自 `decision.recommendation`)，tone = agent
  - **失谐标记**：当 `score_band ∈ {high_conviction, trade_candidate}` 且 `decision.confidence < 0.5` 时显示 pill `gate-agent mismatch`，tone = risk
  - **数据缺位标记**：当 `factor_snapshot.market.readiness.anchor_status = missing` 或 `latest_status = stale` 时显示 pill `market data stale`，tone = risk
- candidate_id 短显
- Action bar：
  - dedicated mode: `← back to queue` + Search Intel（primary）+ Birdeye + Pump.fun + 其它 venue 链接
  - compact mode (inline)：`Open in full view ↗`（跳 dedicated）+ Search Intel + venue 链接（压缩成 icon-only）

**Burst histogram：**

- 24 个桶（每桶 1h，覆盖最近 24h），桶高度 = 该小时窗口内 source event 数量；最高 5 像素 / event，封顶 56px
- 标 first / peak / now 三个锚点，时间用绝对 UTC 时间戳（`2026-05-13 17:04 UTC`）+ 括号绝对时间相对当前的差（`(57m ago)`）作为副标
- 桶数据从已有 `factor_snapshot.families.social_heat.facts.mentions_1h/4h/24h` 不够细，需要从 source events 时间戳自行 bin 化；这一步在前端 `model/pulseDetail.ts` 内完成

**Freshness 栏：**

- 6 行 `label · status · age` 形式：
  - `identity` → `factor_snapshot.data_health.identity`
  - `social` → `factor_snapshot.data_health.social` + age 来自最新 source event 的 timestamp 与 now 之差
  - `event_anchor` → `factor_snapshot.market.event_anchor` 是否存在
  - `decision_latest` → `factor_snapshot.market.decision_latest.observed_at_ms` 与 now 之差
  - `cohort` → `factor_snapshot.normalization.cohort_status` + cohort_size
  - `alpha rank` → `factor_snapshot.normalization.alpha_rank` + 计算 percentile

### Event Timeline

4 节点（dedicated 横排 / compact 纵排）：

| 节点 | 数据来源 | 颜色 |
|---|---|---|
| market anchor | `factor_snapshot.market.decision_latest.observed_at_ms` + mcap/liq/holders/vol | risk 边（如果 stale 或 anchor missing）/ health 边（如果 ready） |
| first mention | source events 中 timestamp 最早一条的 author/handle/followers/text 摘要 | neutral 边 |
| burst peak | `T_peak`（见下文 Evidence 分组定义）；显示该窗口内 mention count、unique authors | opportunity 边 |
| now | pulse `updated_at_ms`、`Σ stage.latency_ms`、stage_count、判定 verdict pill | health 边 |

每节点：`tag (绝对时间)` + 1 行 bold 标题 + 1 行细节。点击节点可以滚动到 evidence list 对应区间（深链接）。

### Factor Families

2 × 2 grid（dedicated）/ 1 × 4 stack（compact）。每个 family：

- 上行：name + score (16–18px) + rank（`cohort rank 0.91 · top 9%`）
- 下方 breakdown 4–6 行 monospace（每行 `label · value`）：
  - social_heat: mentions 1h/4h/24h, unique authors, attention surprise + baseline size 提示, watched seed
  - social_propagation: independent authors, time to 2nd/3rd author, top author share + 谁是 top author, duplicate text share, kol/watched count
  - semantic_catalyst: llm covered mentions, direction mix, impact/novelty
  - timing_risk: price change before/since social, dex floor 状态

缺失字段用 `n/a (missing)` 红色字，不要变 `0` 或 `-`。`top_author_share` ≥ 0.5 用 warn 色，≥ 0.7 用 risk 色。

### Market Context

4 个 metric 卡（mcap / liq / vol_24h / holders）。规则：

- liq < $50K → metric 边框 warn
- vol_24h / mcap ≥ 5 → metric 边框 risk + span 文字加 `· N.N× mcap`
- holders < 500 → metric 边框 warn
- 整体如果 `latest_status = stale` 或 `event_anchor missing`：在 grid 下方一行 risk 字 `⚠ event_anchor null · decision_latest stale Nm · stale_fields: [...]`

### Evidence Events

#### 顶部 toolbar (sticky)

```
[●All N]  [★Cited M]   @handle 芯片 ×k   type ▾   sort ▾
```

- `All / Cited` 互斥切换（默认 All）；Cited 即 `evidence_event_ids` 子集
- author 芯片自动从 source events 计算：默认显示 ≥ 2 条出现的 author，按 post 数排序，最多 5 芯片 + `+N more`；点击 toggle 单作者过滤
- type = `tweet / quote / repost / reply` 多选过滤
- sort = `time asc` (默认，对齐 timeline) / `time desc` / `followers desc`

#### 分组规则（精确定义）

定义：
- `T_first` = min(timestamp_ms in source events)
- `T_peak` = 12-minute sliding window 内 mention 数最大的窗口的中心时间（如有并列取最早窗口）
- `T_now` = pulse `updated_at_ms`

| Group | 范围（左闭右开） | 默认展开规则 |
|---|---|---|
| earlier | `(-∞, T_peak - 30min)` | 组内行数 ≤ 5 默认展开；否则总行数 > 20 时折叠 |
| burst window | `[T_peak - 30min, T_peak + 12min]` | 永远展开 |
| post-burst | `(T_peak + 12min, T_now - 10min)` | 组内行数 > 12 时折叠 |
| latest | `[T_now - 10min, T_now]` | 永远展开 |

当 group 范围内行数为 0 时，整组不渲染（不显示空 group head）。

group head: `▾/▸ 名称 · 范围(UTC) · count events · ★ cited count · stats`。点击折叠状态切换。

#### 行渲染

每行 4 列 grid：`绝对时间 (HH:mm UTC)` / `author 块` / `body` / `★`。

- author 块：`@handle` (b) + 2nd line `followers · channel · 类型 · concentration tag`
  - concentration tag 仅当该作者 ≥ 2 条出现时显示 `N/total`
- author 标志：
  - `flag-watched`：handle 在 watched 列表，绿色字
  - `flag-spam`：当 followers < 5K 且该作者占 ≥ 30% 该 pulse 的 post 数，粉色字
- body：text_clean（fallback text → text_raw），WebKit line-clamp 2，点击行展开成全文 + parse + thread metadata
- `★` 当行属于 `evidence_event_ids`
- 整行如果是空 body（pure repost），加 `empty-body` 类，opacity 降至 0.62，body 显示 `(empty repost · no body text)`

#### 规模行为

| 规模 | 行为 |
|---|---|
| ≤ 12 | 全展开内联，无 max-height |
| 13–50 | scroll-frame `max-height: min(60vh, 720px)` |
| 50–100 | 上 + 时间分组折叠按表 |
| 100–200 | 上 + 组内虚拟化 (`react-window`)；group-head 显示统计但不渲染折叠行 |
| 200+ | 上 + 后端 cursor 分页，"load more"显式按钮 |

#### Author concentration bar

evidence 列表下方固定一条横向 stacked bar，分段长度按各作者 post 数比例，颜色随 author 分类。

**Author 分类规则**（纯前端计算，无后端字段新增；`author_watched` 来自 `SocialEventDetail.author_watched`）：

| 类别 | 判定 | 颜色 |
|---|---|---|
| `watched` | `author_watched == true` | health |
| `spam_suspect` | `author_followers < 5000` AND (`this_author_post_share ≥ 0.30` OR 该作者全部为 repost/quote 无原创 body) | risk |
| `kol_signal` | `author_followers ≥ 10000` AND `this_author_post_count == 1` | opportunity |
| `normal` | 其它 | info |

bar 下方 legend 列 top 3 作者（按 post 数）+ `+N more` 当总作者数 > 3。

同样的分类用于 evidence 行 author 块下方的 `flag-*` 文字色：`watched` 绿 / `spam_suspect` 粉 / `kol_signal` 金 / `normal` 无 flag（保持灰色 dim）。

#### Author chip toolbar

顶部 toolbar 自动从 source events 计算 author chip：
- 按 post 数降序取前 5 作者展示芯片
- 超过 5 时显示 `+N more` 芯片（点击展开二级菜单，phase 2 实装；phase 1 仅 5 + `+N more` 静态显示）
- 单作者 pulse（unique authors == 1）不渲染 chip 行

#### Abstain / 空 evidence

当 `decision.recommendation = abstain` 或 `evidence_event_ids` 空集：
- toolbar `★Cited` tab 灰显且不可点
- 列表上方加 callout：`agent abstained — showing all source events for context`
- group accordion 不变

### Agent Decision Rail

#### Rail header

`agent decision rail` 标题 + meta `model · stage_count · total_latency`。

#### Gate-vs-agent 张力卡（条件渲染）

> 命名说明：这里 **"gate"** 指 deterministic candidate ranking gate，即 `score_band` + composite `rank_score`。与 `factor_snapshot.gates.{eligible_for_high_alert, blocked_reasons}` 这个 eligibility gate 是两个不同概念。UI 文案统一用 "score gate" / "score band" 避免歧义。

显示条件：(`score_band ∈ {high_conviction, trade_candidate}`) AND (`decision.recommendation ∈ {watchlist, ignore, abstain}` OR `decision.confidence < 0.5`)。阈值 `0.5` 抽成常量 `GATE_AGENT_MISMATCH_CONFIDENCE`。

显示内容：
- 一行 `score gate: <score_band> (rank_score N)`（opportunity 色）→ `agent: <recommendation> · <confidence>`（risk 色）
- 副注：`composite rank score said top tier; 3-stage agent collapsed confidence to X. Review reason in Critic.`

#### Stage cards

**默认路径 (`decision.route ∈ {cex, meme}`)：** 渲染 Analyst → Critic → Judge 三段，顺序固定。

**Research-only 路径 (`decision.route = "research_only"`)：** 仅渲染一个 `research_only_gate` 段卡，标题 `pre-LLM gate`，meta 标 deterministic；不渲染 Analyst/Critic/Judge。卡内显示 `gate reason` 与 `decision.abstain_reason`。Hero 不显示 gate-vs-agent 张力卡（research_only 是 gate 选择，不算"分歧"）。

**Stage 内容：**

每段：
- 段头 `stage N · <name>` + meta `latency · model · status`
- KPI 行（小 chip）：
  - Analyst: `recommendation` + `confidence`
  - Critic: `should_abstain` + `confidence_ceiling (↓ from analyst)`
  - Judge: `route` + `recommendation` + `confidence (vs ceiling)` + `abstain_reason`
- summary（仅 Analyst / Judge）：完整 `summary_zh`
- 列表区：
  - Analyst: `evidence` 列表
  - Critic: `weaknesses` (warn 色) + `missing_fact_impacts` (risk 色)
  - Judge: `residual_risks` (risk 色) + `invalidation_conditions` (warn 色)
- 任何空字段（如 `weaknesses: []`）显示 `(no entries)` 而不是隐藏
- stage 缺位（如 `stages.critic = null` 表示 critic 阶段未跑或失败）：渲染该段卡为占位 `stage N · <name> · skipped`，meta 区显示 status；下游 Judge 卡的 ceiling 比对副注改为 `(no critic ceiling)`

#### Replay 折叠

底部 `<details>`：
- versions 列表：pulse_version / gate_version / prompt_version / schema_version / runtime_version
- run_id, candidate_id, agent_run_id
- 链接 `view raw pulse_agent_run_steps`（phase 2，先留 anchor 不实现）

### 展示规则总则

**时间格式：** 一律绝对 UTC，格式 `2026-05-13 17:04`（不显示秒，不显示时区缩写——UI 顶部固定 `times shown in UTC` legend 即可）。"差值" 用括号副注 `(57m ago)` 或 `(in 4h)`。Hero burst marks、Timeline tags、Evidence row 时间、Freshness ages 都用此规则。

**数字格式：**
- USD：`$114K`（compactNumber，∞ 位精度根据量级缩放）
- 整数：千分逗号 `1,243`
- 百分：`0.91 · top 9%`（rank）/ `0.35` (confidence) 一律两位小数
- 比例：`13.5× mcap`

**fallback 规则：**
- 任何 number 为 `null` 或 `NaN` → 显示 `n/a`，tone = neutral；如该字段属于 data_health `missing` 类，加 `(missing)` 副注，tone = risk
- 任何 string 为空 → 显示 `—`
- enum 缺位 → `(unset)`

**颜色规则：** 严格使用 `tokens.css` 已定义的 5 个 tone（opportunity / health / info / risk / agent + neutral）；不引入新色。

**字体：** 数据字段一律 `var(--mono)`；正文 `var(--sans)`。

## 公共契约要求

不改 schema。两处增量：

### 1. Pulse payload 扩展

`GET /api/signal-lab/pulse/<candidate_id>` 返回的 `SignalPulseItem` 增加 `stages` 字段：

```
stages: {
  analyst:  { status, latency_ms, model, started_at_ms, finished_at_ms, response: { ... } } | null
  critic:   { status, latency_ms, model, started_at_ms, finished_at_ms, response: { weaknesses, missing_fact_impacts, confidence_ceiling, should_abstain, ... } } | null
  judge:    { status, latency_ms, model, started_at_ms, finished_at_ms, response: { ... } } | null
  research_only_gate?: { ... } | null
}
```

数据源：从 `pulse_agent_run_steps` 按 `run_id, stage, attempt_index DESC` 取每 stage 最后一次成功 attempt。read model 在 `signal_pulse_service.py` 内组装；新增字段在 `frontend-contracts.ts` 显式声明。

### 2. 新端点 `/api/social-events/by-ids`

```
GET /api/social-events/by-ids?ids=<comma-separated>&limit=200
Authorization: Bearer <token>

→ ApiEnvelope<{
    events: SocialEventDetail[]
  }>

type SocialEventDetail = {
  event_id: string
  timestamp_ms: number
  source_provider: string
  channel: string
  action: "tweet" | "quote" | "repost" | "reply" | string
  author_handle: string | null
  author_name: string | null
  author_followers: number | null
  author_watched: boolean       // 来自 watched handle 集合 lookup
  text_clean: string | null
  canonical_url: string | null
}
```

实现：`repos.evidence.events_by_ids(ids)` 已存在，端点只做 `id 列表 → 批量 lookup → 投影`。授权与现有 `/api/recent`、`/api/social-events` 一致。

### 3. 时间统一

后端返回继续用 `_at_ms` epoch ms；前端 `@lib/format` 内新增 `formatUtcTimestamp(ms)` 与 `formatRelativeAge(ms, refMs)`（前者绝对，后者副注用）。两者纯函数，无外部依赖。

## 组件边界 — 防耦合

> 原则：每个组件接受 typed props，零副作用，零路由依赖；数据获取/路由解析全部在 page-level 容器完成。

### 文件结构

```
web/src/features/signal-lab/ui/PulseDetail/
  PulseDetailView.tsx          # orchestrator, props 接受 SignalPulseItem + SourceEventDetail[] + density
  PulseHero.tsx
  PulseHero.module.css
  PulseTimeline.tsx
  PulseTimeline.module.css
  PulseFactorFamilies.tsx
  PulseFactorFamilies.module.css
  PulseMarketContext.tsx
  PulseMarketContext.module.css
  PulseEvidenceList.tsx
  PulseEvidenceList.module.css
  PulseAgentRail.tsx
  PulseAgentRail.module.css
  index.ts                     # 只 re-export PulseDetailView 与必要类型

web/src/features/signal-lab/model/
  pulseDetail.ts               # buildPulseDetailView, 纯函数
  pulseDetail.test.ts          # 用 $TITTY fixture

web/src/features/signal-lab/api/
  useSignalPulseCandidate.ts   # 已有，扩展类型即可
  useSourceEvents.ts           # 新 hook, 包装 /api/social-events/by-ids

web/src/lib/format/
  time.ts                      # formatUtcTimestamp, formatRelativeAge
  time.test.ts

tests/fixtures/pulse/titty.json # 完整 SignalPulseItem 真实数据快照, 用于单测
```

### 组件契约

| 组件 | 输入 (props) | 输出 (副作用) |
|---|---|---|
| `PulseDetailView` | `{ item: SignalPulseItem, sourceEvents: SocialEventDetail[], density: "full"｜"compact", now: number }` | 0 |
| `PulseHero` | `{ subject, scoreBand, decision, freshness, mismatch, burstHistogram }` | 0 |
| `PulseTimeline` | `{ nodes: TimelineNode[], density }` | 0 |
| `PulseFactorFamilies` | `{ families: FactorFamilyView[], density }` | 0 |
| `PulseMarketContext` | `{ metrics: MarketMetric[], staleNotice?: string }` | 0 |
| `PulseEvidenceList` | `{ groups: EvidenceGroup[], citedIds: Set<string>, density, onRowExpand?: (id) => void }` | 仅本地 useState 管理 filter / 折叠状态 |
| `PulseAgentRail` | `{ mismatch?: GateAgentMismatch, analyst?, critic?, judge?, replay, density }` | 0 |

### 数据流

```
PulseDetailPage (route container)
  ├── useSignalPulseCandidate(candidateId) → SignalPulseItem (with stages)
  ├── useSourceEvents(item.source_event_ids) → SocialEventDetail[]
  └── PulseDetailView
        ├── buildPulseDetailView(item, sourceEvents, now) → PulseDetailViewModel (pure)
        └── 各子组件直接读 PulseDetailViewModel 的子树
```

`SignalLabPage` 队列内联调用相同：

```
SignalLabPage
  └── 当 isPulseRoute=false 时:
        ├── useSignalPulseCandidate(inlinePulseItem.candidate_id)
        ├── useSourceEvents(inlinePulseItem.source_event_ids)
        └── PulseDetailView density="compact"
```

### 反耦合约束

1. `PulseDetailView` 与其子组件**不**导入 `react-router-dom`、`@tanstack/react-query`、`@lib/api/client`。
2. `buildPulseDetailView` 是 deterministic 纯函数，给定相同 `(item, sourceEvents, now)` 输出相同 `PulseDetailViewModel`；可以在 server-side 渲染或 jest snapshot 中复现。
3. CSS 用 module（`*.module.css`），不再用 `signal-pulse-case` 这种 global 类。Tone 颜色通过 props → className `data-tone="risk|health|…"` 映射，CSS module 内只引用 `var(--…-ink)` 等已定义 token。
4. 删除当前 `signal-lab/ui/SignalLabInspector.tsx`、`signal-lab/ui/SignalLabInspector.test.tsx`、`signal-lab/model/pulseCase.ts`、`signal-lab/index.ts` 中的相关导出；同 PR 删 `signalLab.module.css` 内 `.signal-pulse-*` 选择器。

#### 路由拓扑变化

```
当前 (AppRoutes.tsx:240-250):
  /signal-lab           → SignalLabRoute
    /signal-lab/pulse/<id>  → SignalLabPulseRoute  (嵌在 SignalLabRoute Outlet 里)

目标:
  /signal-lab           → SignalLabRoute (队列 + inline inspector)
  /signal-lab/pulse/<id> → PulseDetailRoute  (顶层路由，CockpitShell 下，不嵌 SignalLabRoute)
```

`PulseDetailRoute` 直接挂在 cockpitShellElement 路由下，不再是 SignalLabRoute 的子路由。同时移除 `SignalLabPage` 内 `isPulseRoute && <Outlet />` 分支（不再需要）。

队列里点击 candidate 的行为不变（仍然内联渲染到右栏）。`Open in full view ↗` 按钮在 inline `PulseDetailView` header 上提供，跳到 dedicated 路由。
5. 删除 `web/src/shared/ui/case-file/index.ts` 内未被其它路由使用的 Obsidian 原语（探索阶段确认：`ObsidianFieldGrid`、`ObsidianEvidenceList`、`ObsidianCaseHeader`、`ObsidianCase` 还有其它使用者，保留；只删孤立的 `signal-pulse-*` global CSS）。
6. 新增 `react-window` 仅在 Evidence 100+ 行触发，phase 1 可以先 stub 为纯滚动并 TODO 标，phase 2 再实装；spec 允许 phase 1 不引入 react-window 依赖，但 hook 边界（`PulseEvidenceList` 的 `groups` 输入）必须从一开始就支持组内 windowing 替换。

## 验收标准

### 功能正确

1. 打开 `/signal-lab/pulse/pulse-fa2a12fedd9332271732110ed8bd7b1b49065282`：
   - Hero 显示 `$TITTY`、`solana`、`high conviction band` pill、`meme route` pill、**`gate-agent mismatch` pill**、**`market data stale` pill**
   - Burst histogram 24 桶 (T_now-24h ~ T_now)，标签为 UTC 绝对时间（如 `2026-05-13 15:25 UTC · first` / `2026-05-13 16:16 UTC · peak` / `2026-05-13 17:04 UTC · now`），副注用括号显示与当前差值（`(101m ago)`）
   - Freshness 显示 6 行；`market anchor: missing` 红字；`decision_latest: stale · 119m`（绝对差值字段，UI 文案"119m ago"是相对副注，不与"统一绝对时间"原则冲突——absolute 原则适用于点时间，duration 字段始终是相对量）
   - Timeline 4 节点；market anchor 节点带 risk 边
   - 4 family 卡：social_heat 91 / propagation 85 / semantic 50 (missing 红字) / timing 0 (missing 红字)；propagation 卡里 `top author share 0.60 ← @cache100x` 行存在
   - Market context 4 metric：`$30,863` liquidity warn 边；`$1,537,006 · 13.5× mcap` risk 边
   - Evidence 列表 5 行，全部 ★（cited）；`@cache100x · 2.7K · #1/3 / #2/3 / #3/3` concentration 标签；底部 author concentration bar 显示 60% / 20% / 20% 三段
   - Agent rail 顶部 `gate-vs-agent` 卡：`gate: high_conviction (82) → agent: trade_candidate · 0.35`
   - Analyst card：confidence 0.82，5 evidence；Critic card：ceiling 0.45 + 5 weaknesses + 4 missing-fact impacts；Judge card：confidence 0.35 + 5 residual risks + 3 invalidation conditions
   - Replay 折叠展示 `pulse_version / gate_version / prompt_version / schema_version / runtime_version / run_id`

2. 打开队列 `/signal-lab` 后选中同一 candidate：右栏渲染 `density="compact"` 版本，所有上述数据可见（仅排版折叠不同）。

3. 单条 source 的 pulse（p50 == 1 event）：Evidence 列表无分组、无 toolbar 折叠按钮；author concentration bar 单段。

4. p99 (19 events) pulse：toolbar sticky 工作，分组按规则展开/折叠；evidence 行数 ≤ 19，无 `react-window` 触发。

5. Abstain pulse（任取 `decision.recommendation = abstain`）：rail 顶部 mismatch 卡仍可能显示（gate 高 agent abstain）；evidence toolbar `★Cited` tab 灰显；列表上方显示 `agent abstained — showing all source events for context`。

### 工程质量

6. `PulseDetailView` 与所有子组件不 import `react-router-dom`、`@tanstack/react-query`、`fetch`、`axios`，CI lint 规则可检测（grep 检查）。
7. `buildPulseDetailView` 单测：给定 $TITTY fixture，断言 ViewModel 中 8 个区块的字段；给定 abstain fixture、空 evidence fixture、p50 单事件 fixture 各一份。
8. 删除 `SignalLabInspector*` 后 `pnpm test`、`pnpm typecheck`、`pnpm lint` 全绿。
9. E2E `signal-lab-filters.spec.ts` 测试不动；新增 `pulse-detail.spec.ts` 覆盖 dedicated 路由加载 + density="compact" inline 渲染 + evidence toolbar 切换 All/Cited。
10. 后端 `GET /api/social-events/by-ids` 返回长度 == ids 长度（不存在的 id 返回时跳过并在 envelope `meta` 标 `not_found: [...]`，前端容忍）。
11. CSS module 内**不**使用 `:global(.signal-pulse-*)` 或其它全局类。

### 视觉一致

12. 5 个 tone 严格来自 `tokens.css`；新增颜色字面值需先扩 tokens（本 spec 不预期需要）。
13. 字体：所有数据字段 `var(--mono)`；正文 `var(--sans)`。Hero 资产符号 22px mono；section title 12px mono uppercase；body 12–13px sans。
14. Radius 一律 `var(--radius)` (7px)；阴影一律 `var(--shadow-elevated)`。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `pulse_agent_run_steps` stage 输出大（response_json 可能 ~ 数 KB），inline 进 pulse payload 让 list 接口变慢 | 仅 `GET /api/signal-lab/pulse/<id>` 单条端点包含 `stages`；list 接口 `/api/signal-lab/pulse` 不带；同时给单条端点加 `If-None-Match` ETag |
| `events_by_ids` 一次 200 条仍然可能 500ms+ | 端点设 `limit=200` 硬上限；前端 hook 默认只取 source_event_ids 前 100；超出后按需 `cursor` 拉 phase 2 |
| Source events 删除（GDPR / dedup） | hook 与渲染层都按"返回长度 < 请求长度"处理，缺失行用占位 `(event missing or removed)` 灰行，不阻塞主体 |
| 时间统一 UTC 但用户可能误读成本地时间 | 页面顶部 freshness 区第一行固定 `times shown in UTC` legend；hero 角落复述 |
| burst histogram 在 source events 全为 0 时空状态 | 显示 24 个空 bar 与 placeholder `no source mentions captured`；不抛错 |
| `gate-vs-agent` 卡阈值（confidence < 0.5）选错 | 阈值作为常量 `GATE_AGENT_MISMATCH_CONFIDENCE` 在 `pulseDetail.ts` 顶部定义，单测覆盖边界值 |
| density="compact" 模式下 evidence + agent rail 都很长导致整体抖动 | compact 模式 evidence 列表自带 `max-height: 60vh`；agent rail 折叠成 accordion 时整段单独滚动 |
| 删除旧 `SignalLabInspector` 时其它 import 没清干净 | grep 检查：`grep -rn "SignalLabInspector\|signal-pulse-case\|pulseCase" web/src` 应为空（除新组件内部） |

## 决策日志

| 决策 | 理由 |
|---|---|
| Hard cut 删除 `SignalLabInspector` 与相关 case-file 用法，不双轨 | 与 [[feedback_hard_cut_style]] 偏好一致；当前组件被研究员视角完全否定，dual-track 只会拖长清场 |
| density 是 prop，不分成两个组件 | 数据 100% 重合，仅排版差异；分双组件等于复制视图逻辑，违反"不要耦合" |
| 时间统一绝对 UTC | researcher 工作流跨时区/跨会话复盘，相对时间 (T-Nm) 在事后追查时含义漂移；用户明确要求 |
| 不引入 dayjs 等时间库 | `Intl.DateTimeFormat` 与少量手写差值函数足够；新增依赖会扩大攻击面与 bundle 体积 |
| Burst histogram 用 inline DOM bar 不用 chart 库 | 24 个 div bar 完全够；引图表库（recharts/visx）会拖入数百 KB 与无关 API |
| Evidence scale 用"分组 + 滚动"先，"虚拟化"phase 2 | 真实数据 p99 = 19，phase 1 不需要 react-window；过早抽象违反"don't design for hypothetical future" |
| Stage 输出从 `pulse_agent_run_steps` 而非新表读 | run_steps 已经有完整 Analyst / Critic / Judge 数据，新建表/写双份违反 hard cut 原则；只需在 read model 投影 |
| 新端点 `/api/social-events/by-ids` 而不复用 `/api/social-events` 模糊查询 | 按 id 批量是不同语义；模糊查询接口的 filter shape 不应与"已知 ids 列表"耦合 |
| `gate-vs-agent mismatch` 显式 pill + rail 卡 | 这是当前 UI 完全隐藏的最重要审计信号；从第一性原理是"研究员第一眼应看到的张力" |
| Author concentration bar 是独立组件而非 evidence list 内嵌一行 | concentration 是 evidence 列表上的"汇总观点"，分开渲染让 list 本身保持纯时间序，aggregation 独立 |
| compact mode 把 agent rail 放最底 accordion | 队列右栏宽度太窄无法承载并列 rail；compact 必然要折叠，把 agent 折掉而非 evidence 折掉是因为 evidence 是"事实"（应优先可见），agent 是"意见" |
