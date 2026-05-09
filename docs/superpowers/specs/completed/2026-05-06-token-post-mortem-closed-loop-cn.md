# Token 复盘视图与 Timing 修复 Spec

日期：2026-05-06
配套：`2026-05-06-token-timeline-frontend-cn.md`（前端组件设计）

## 0. 结论

把"用户对一个暴涨 token 做事后复盘"作为一等产品场景接入。当前架构里，复盘所需的原子数据已基本入库，**缺的是一条专为复盘服务的下游派生轴**和**对 timing 错误因果断言的截肢**。

本 spec 提出三件事：

1. **复盘视图**：把已入库但未消费的三类数据（推文引用关系、LLM 事件类型、watched 首次提及标记）暴露到 timeline / posts API，让前端能画出对齐的复盘视图。
2. **催化排序**：新增一条"基于 post 下游观察窗口"的 catalyst 排序服务，**不读 post 的上游身份特征**（粉丝、watched、首发、置信度），完全用下游传播事实定义催化。
3. **Timing 截肢**：删除 timing 评分中的"社交领先 / 社交确认"等因果断言档，把 timing 降回"价格已涨多少 + 市场数据是否就绪"的事实卫生指标。

不引入新存储实体、不新建后台 worker、不引入标注流程或反馈算子。

## 1. 背景

### 1.1 产品场景

当前 forward 链路（token-flow → opportunity_score → notification）回答的是"现在哪个币值得看"。但用户在使用过程中持续遇到第二类问题：**"$XYZ 已经涨了，把这段时间倒带，告诉我发生了什么"**。

复盘场景的具体子问题：

- 价格在哪个时刻启动？涨幅多大？
- 社交端在价格之前还是之后开始动？
- 哪一条推真正引发了传播——不是"第一条提到的"，而是"后面跟进最多、最分散、最高质量的"？
- 跟进的传播形态是同质 copy-pasta（bot/shill 集群）还是独立人类讨论？
- 整段窗口里热度是怎么演化的（一次性 broadcast / organic 多层级联 / 内生爆发慢衰减）？

这些问题不是 forward 评分能回答的，因为 forward 评分把整段窗口压成单一标量分。复盘要的是**事件级 + 时间序列级**的展开。

### 1.2 现有产品形态

cockpit 里 `TokenDetailDrawer` 已有 Timeline / Posts / Score / Lab / Accounts 五个 tab。其中 Timeline 与 Posts 已经在消费 `/token-social-timeline` 与 `/token-posts` 的输出，但呈现的内容只能回答上述子问题中"价格涨了多少"和"提及量多少"两项。剩余子问题数据齐但无服务消费，或服务有但前端没渲染。

复盘不需要新建独立页面，**应当在 Timeline tab 内升级**——保持用户对该入口的既有认知。

## 2. 现状架构

### 2.1 数据流

```
GMGN public WS
  → collector (direct_ws / normalizer / service)
  → ingest_service
       events
       event_entities
       event_token_mentions
       event_token_attributions
       account_token_alerts
  → enrichment_worker (LLM social_event_v2)
       social_event_extractions
       attention_seeds
       event_clusters
  → 现有 retrieval 服务：
       token_flow_service        (forward 排名)
       token_social_timeline_service (timeline + posts + authors + bucket prices)
       token_posts_service       (posts 列表)
  → api/http.py
       GET /token-flow
       GET /token-social-timeline
       GET /token-posts
  → 前端 TokenDetailDrawer (Timeline / Posts / Score / Lab / Accounts)
```

底层存储 PostgreSQL（Alembic + Psycopg 3）。

### 2.2 已有能力

`token_social_timeline_service` 输出已经包含：

- 自适应桶宽（5m→30s, 1h→5m, 4h→15m, 24h→1h）
- 桶级 mentions / authors / new_authors / watched_posts / duplicate_text_share / top_author_share / effective_authors / reproduction_rate
- 桶级价格（取桶末 `at_or_before` 价）与相对窗口起点的涨跌幅
- 整窗口 phase 分类（seed / ignition / expansion / concentration / fade / decay）
- 作者级别的 role 分类（seed / early_amplifier / amplifier / watched）
- post 级别的 post_quality 评分

`token_posts_service` 已经支持三个 range（current_window / since_ignition / all_history），固定按 `received_at_ms` 倒序，游标分页。

**这意味着复盘视图所需的 80% 数据已经在 API 响应里，前端只渲染了一部分**。

### 2.3 已入库但未消费的数据

三类数据已经在 PG 表里，但没有任何 retrieval 服务暴露它们：

- **`events.reference_json`**：每条 quote / reply / retweet 的父 tweet_id、父作者。模型层 `Reference{tweet_id, author_handle, type}` 完整；只在 `ingest_service` 拼接文本时取过 `reference.text` 做实体抽取，cascade 关系完全无人消费。
- **`social_event_extractions.event_type`**：watched 事件经 LLM 后落在该表，每事件唯一一行，类型枚举包含 `meme_phrase_seed / listing_hint / product_mention / ecosystem_boost / regulation_comment / exchange_risk / founder_reply / market_structure_comment / rumor`。仅 harness 子系统消费，timeline / posts 服务没 join。
- **`account_token_alerts.is_first_seen_global / is_first_seen_by_author`**：标记"该 token 在该作者下是否首次出现"。仅 notification 子系统消费，timeline / posts 服务没 join。

### 2.4 timing 现状

`timing_score` 当前实现把"两个价格快照 + 一个聚合热度"映射成 5 档因果断言：`social_leads_price=82` / `social_confirms_price=70` / `late_after_large_move=55` / `chase_risk=45` / `social_fades=42` / `insufficient_history=40~50`。

该输出以 0.12 权重进入 `opportunity_score`，直接影响 driver/watch/discard 决策。

## 3. 问题

### 3.1 复盘子问题与现状 gap

把 §1.1 的用户子问题逐条对到现有数据：

| 子问题 | 数据是否在 DB | 是否暴露给前端 |
|---|---|---|
| 价格何时启动、涨幅多少 | ✅ | ✅ |
| 价格 vs 提及对齐 | ✅ | ⚠ 已暴露但前端未叠加成同图 |
| 哪条推引发了传播 | ⚠ 数据在（events 时序 + reference_json + 后续提及）但**无服务派生** | ❌ |
| 传播是独立分散还是 copy-pasta | ⚠ 数据在但无派生 | ❌ |
| 事件类型（listing/meme/...） | ✅ `social_event_extractions.event_type` | ❌ 未 join |
| 传播路径树 | ✅ `events.reference_json` | ❌ 完全无消费 |
| 热度形状（phase 序列）| ✅ `build_timeline_features` | ⚠ 已暴露但前端未渲染 |

**两类缺口**：

1. **暴露缺口**：数据在 DB 里、前端能用，但 retrieval 服务没把字段 join 出来。需要扩展现有 timeline 服务的 SQL join 与响应字段。
2. **派生缺口**：单条 post 的"催化能力"不在任何已有字段里，需要新派生层。

### 3.2 上游身份排序的根本错误

直觉上会想用 `(is_first_seen, is_watched, attribution_confidence, author_followers)` 给 posts 排序，把"看起来重要的"顶上去。这在产品上是错的：

- **first-mover 是 bot 主导**。Crypto 场景里 mempool sniper / CA scanner / 自动转发 bot 几乎稳定占据 first-mover；`is_first_seen_global` 的真实分布是"哪个 bot 跑得快"，不是"谁是真正的 catalyst"。
- **influencer 效应已被证伪**。Bakshy/Hofman/Mason/Watts (2011, WSDM) 在 7400 万条 Twitter URL cascade 上证明：控制 topic 与 timing 后，influencer 效应弱到不显著；大量普通用户的集体行动比少量大 V 更能驱动级联。
- **watched 是观察者偏差**。watched 反映"我们的先验偏好"，把它当排序权重等于把数据回归到先验，丧失发现新信号的能力。
- **attribution_confidence 与催化正交**。它是"这条推确实在讲这个 token"的可信度，与"这条推是否引发了下游传播"完全不同。

催化剂的定义本身是**反事实的**：这条推存在 vs 不存在，下游传播是否显著不同。这是**只能从下游观察、不能从上游推断**的量。任何把上游身份特征当 catalyst 排序的设计都是定义错位。

### 3.3 timing 因果断言的定义错位

timing 输入是两个价格快照。从两个标量可以做的判断只有"差值符号"和"差值大小"，**做不出"社交是否领先价格"的因果断言**——后者至少需要两个时间序列在多个时刻的协方差结构。

但当前实现把"差值大小落在 8%-20%"映射成 `social_confirms_price`，把"差值 < 8%"映射成 `social_leads_price`。这两档是**用价格变化大小冒充因果方向**，是定义错位，不是公式可调的问题。

任何静态 token（社交未动、价格未动）都会被打成 `social_leads_price=82`，把信噪比低的 token 顶到 driver 候选。这与产品想要的"timing 帮我判断 alpha 真实性"的功能恰好相反。

## 4. 第一性原理

1. **催化是下游观察的，不是上游推断的**。一条推是不是 catalyst，取决于它后面 Δ 分钟内激发了什么；和它自己的粉丝数、是不是先发、是不是 watched 都没有直接因果关系。任何排序信号都必须建立在该 post 之后的传播事实上。
2. **能用眼看的不要算**。Lead-lag、催化单点归因、phase 转折点这种统计推断在小窗口里功效几乎为零；有经验的人 30 秒就能从一张对齐图里看出来。系统的责任是把数据摆好。
3. **能 join 的不要造**。复盘需要的展示数据已经在 DB 里，缺的是 join，不是新表 / 新算法 / 新 worker。
4. **能截肢的不要重构**。timing 错的是因果断言部分，对的是 chase_risk 和 market_observation_status；不要为了修错的去重写对的。
5. **不引入用户不需要的认知负担**。Bayesian 概率、置信区间、NULL catalyst 候选这些设计的认知成本是线性的，统计严谨的边际收益接近零。

## 5. 目标

### 5.1 范围

G1. **复盘视图可用**：用户在 cockpit 看到一段时间内 token 的"价格 + 提及 + 阶段 + 事件清单 + 引用关系"对齐视图，能用眼回答 §1.1 的全部子问题。

G2. **催化排序可用**：post 列表支持 `sort=catalyst` 模式，按下游传播观察打分排序；前端展示排序值与各项 components，用户可审计。

G3. **timing 不再制造假信号**：timing 输出从"因果断言"降级为"事实卫生指标"，权重在 opportunity 中相应下调，不再把信噪比低的 token 推到 driver 候选。

G4. **不破坏现有契约**：所有新增字段以 optional 形式追加；旧客户端继续工作；新 score_version 让旧/新 snapshot 在评估上自然分桶。

### 5.2 可证伪指标

| ID | 指标 | 目标 |
|---|---|---|
| M1 | cascade 字段在三种 reference type（quote/reply/retweet）上正确建边 | 100% |
| M2 | post 暴露的 `is_first_seen_by_watched_for_token` 与底表一致 | 100% |
| M3 | post 暴露的 `event_type` 与底表一致（缺失时为 null）| 100% |
| M4 | 抗 bot 测试：单一作者 30 次 copy-pasta 的 catalyst score 显著低于 5 个独立作者各 1 次原创回应 | ≥ 3× 倍差 |
| M5 | catalyst score 不依赖 `author_followers / is_watched / is_first_seen / attribution_confidence` 任一字段 | 单变量扰动测试不变 |
| M6 | timing 输出域只含 `{chase_risk, market_pending, market_unavailable, neutral}` 四种状态 | 完备性 |
| M7 | 新权重下，opportunity 决策 driver/watch/discard 计数偏移 | ≤ 15% |

全部能在 CI 自动验证。

## 6. 目标架构

### 6.1 总体数据流（与现状对比）

```
GMGN WS → collector → ingest → enrichment
   ↓
   PG: events / event_entities / event_token_attributions /
       account_token_alerts / social_event_extractions / token_market_snapshots / ...
   ↓
   ┌─────────────────────────────┬────────────────────────────────┐
   │  forward 链（现有，保留）   │  backward 链（本期新增/扩展）  │
   │  token_flow_service         │  token_social_timeline_service │
   │  social_heat / opportunity  │     ↑ 扩展三类 join + cascade  │
   │  timing_score (本期截肢)     │  catalyst_ranking_service      │
   │  notification_*             │     ↑ 新建（下游派生层）       │
   └─────────────────────────────┴────────────────────────────────┘
            ↓                                    ↓
       /token-flow                        /token-social-timeline (扩展)
       /opportunity-*                     /token-posts?sort=catalyst (新)
            ↓                                    ↓
       cockpit forward 视图               cockpit Timeline tab (升级)
```

forward 链保持不变（除 timing 截肢）。backward 链以"扩展现有 timeline 服务 + 新建一个 on-demand 催化排序派生服务"两步落地，不引入任何后台 worker 或新表。

### 6.2 新增的概念实体

只有一个：**Catalyst Ranking** —— "对一条 post 在其下游 30 分钟观察窗口内的传播效应做派生打分"。该实体是**计算派生**，不是存储实体；每次 API 请求实时算，不持久化。

理由：
- 持久化需要后台 worker 与表设计，是显著工程开销；
- 4h 窗口下候选 ≤ 200，派生计算 ≤ 50ms，没有持久化必要；
- 算法第一版可能多次迭代，持久化反而拖慢迭代速度。

如未来证明需要预聚合（24h 窗口慢、并发量大），PG materialized view 天然支持，是后置优化。

### 6.3 与现有服务的边界

| 服务 | 边界 |
|---|---|
| `ingest_service` / `enrichment_worker` | 不动 |
| `signal_repository` / `notification_*` | 不动 |
| `token_flow_service` | 仅消费 timing 截肢的 score_version 升级 |
| `token_social_timeline_service` | 扩展：SQL 增加三类 LEFT JOIN（events.reference_json, account_token_alerts, social_event_extractions），输出新增 cascade 字段与 post 上的展示字段 |
| `token_posts_service` | 扩展：增加 `sort=catalyst` 分发到 catalyst_ranking_service |
| `catalyst_ranking_service`（新）| 纯派生层，输入是窗口内的 candidates + followup pool + baseline pool，输出是带 score 与 components 的 post 列表 |
| `timing_score`（截肢）| 输出域收敛为 4 状态；版本 v3 → v4 |
| `opportunity_scoring` | 权重 timing 0.12 → 0.06，propagation 0.22 → 0.28 |
| 前端 Timeline tab | 升级为价格 + 提及 + 阶段 + 事件清单 + cascade 五件套；详见前端 spec |

## 7. 核心模型：催化的下游观察定义

### 7.1 概念

对一条 post P 在 token T 上的催化分 = **"P 之后 Δ 时间内、T 的传播事实"派生出的标量**，完全独立于 P 的上游身份特征。

派生输入：
- **followups(P, Δ)**：在 (t_P, t_P + Δ] 内 token T 的全部其他作者的提及
- **cascade_followups(P, Δ)**：followups 的子集，限制为"显式引用 P 或与 P 共享 anchor term"
- **baseline_rate(T, t_P)**：T 在 (t_P − 1h, t_P) 的每分钟提及率（用于扣减自然背景）

### 7.2 文献基础

每一项派生指标都对应一篇社交传播研究：

| 派生指标 | 文献 | 引用要点 |
|---|---|---|
| **excess**（相对 baseline 的超额跟进）| Kleinberg (2002) "Bursty and Hierarchical Structure in Streams" | Burst 必须相对 baseline rate 检出，绝对计数无意义 |
| **independence**（跟进作者多样性）| Centola (2010) Science "The Spread of Behavior in an Online Social Network Experiment" | 复杂传染（交易决策属此类）需要多源独立曝光，单源高频曝光无效 |
| **cascade_grip**（直接引用比例）| Goel, Anderson, Hofman, Watts (2016) Management Science "The Structural Virality of Online Diffusion" | 区分 broadcast（一发多转）与 cascade（多层传递）；后者才是 viral |
| **structural_virality**（树 Wiener index）| 同上 | 节点对均距，broadcast ≈ 1，多层 organic >> 1 |
| **time-to-K-authors**（扩散速度）| Cheng, Adamic, Dow, Kleinberg, Leskovec (2014) WWW "Can Cascades Be Predicted?" | 时间特征（root → first reshare 时间、doubling time）胜过结构特征 |
| **avg_followup_quality**（反 shill 加权）| Hodas & Lerman (2014) Scientific Reports "The simple rules of social contagion" | 曝光效应饱和；同 author 重复曝光不应重复计 |
| **不**用 follower / first-seen / watched | Bakshy, Hofman, Mason, Watts (2011) WSDM "Everyone's an Influencer" | 控制 topic + timing 后 influencer 效应弱到不显著 |

后续可加但本期不上：
- **decay shape**（Crane, Sornette 2008 PNAS）：内生 viral 是幂律慢衰减，外生 broadcast 是快衰减，能进一步区分真 catalyst 与一次性曝光。
- **Romero, Meeder, Kleinberg (2011) WWW 的 topic-specific stickiness curve**：不同 event_type 应有不同的传播阈值。

### 7.3 Crypto 场景特异性

通用社交传播文献没覆盖的 crypto 特性：

- **Bot 占 first-mover 是常态**：任何用 first-mover 当 proxy 的设计都会被 bot 主导。这是为什么 §3.2 的根本错误判断在 crypto 比通用场景更严重。
- **Copy-pasta 集群在结构上长这样**：高 followup 数 + 低 independence + 高 duplicate_text_share + cascade_grip 接近 0（不引用任何源帖，只是同时刷屏）。所以 independence + cascade_grip 双卡能识别。
- **真 catalyst 的形态**：第一波 quote 来自 mid-tier 账号（5 分钟内），第二波从他们的关注者扩散（15-30 分钟），第三波出现独立讨论（30-60 分钟）。这是 Crane-Sornette 的 endogenous critical 形状，对应 time-to-K-authors 与 structural_virality 的高分。

### 7.4 派生指标族

催化分由六项加权组合：

| 项 | 权重 | 测量内容 |
|---|---|---|
| excess | 0.30 | 相对 token 自身 baseline rate 的超额跟进数（log 归一）|
| independence | 0.20 | 跟进作者集合的 entropy / 计数比 |
| cascade_grip | 0.20 | 跟进里有多少是直接引用或 anchor echo P |
| time-to-K-authors | 0.15 | 从 P 到第 K 个独立作者跟进的时间（K=5）|
| structural_virality | 0.10 | cascade tree 的 Wiener index（归一）|
| avg_followup_quality | 0.05 | 跟进帖 post_quality_score 均值 |

总分映射到 [0, 100]。具体公式与归一方式在 plan 阶段细化。

权重设计原则：
- excess 是核心信号（0.30），但不能独大，否则 bot 集群会拿高分；
- independence 与 cascade_grip 各 0.20，是"反 bot / 反 broadcast"的双卡；
- time-to-K-authors 0.15 反映扩散速度，权重次之因为窗口内时间分辨率有限；
- structural_virality 与 quality 是辅助维度。

### 7.5 输出契约

每条 post 在 catalyst 模式下返回**单一标量分数 + 六项 component 透明分解**。component 必须可见，理由：

- 用户能审计排序为什么是这个序；
- 算法迭代可以观察到具体哪一项推动了排名变化；
- 出现争议的排序时，可以直接看 components 而不是猜算法。

## 8. timing 重构的语义降级

### 8.1 从因果断言到事实卫生

timing 当前 5 档因果断言全部删除。新版只输出 4 种状态：

- `chase_risk`：pre-pump 价格已涨 ≥ 15%（事实）
- `market_pending`：市场数据正在抓取中（事实）
- `market_unavailable`：市场数据源不可用（事实）
- `neutral`：以上皆否（默认）

每种状态对应固定分数。**没有任何"社交领先价格"或"社交确认价格"的判断。**

任何"社交领先 / 滞后"的判断由前端 timeline 视图呈现——价格曲线和提及柱在同一张图，用户用眼看。

### 8.2 在 opportunity 评分中的位置变化

旧权重让 timing 占 0.12，与 quality / propagation 同档。这意味着 timing 的因果断言能直接拉高/压低 driver 决策。

新权重 timing 0.06，把释放的 6% 转给 propagation（0.22 → 0.28）。理由：

- timing 降级为卫生指标后，它的信号密度本来就不应该和 quality / propagation 同档；
- propagation 是结构性传播事实（独立作者数、reproduction rate 等），比单点价格变化更接近"是否真的有 alpha"的本质；
- 总权重和不变（仍 = 1.0），不破坏 opportunity 公式的归一性。

opportunity 决策规则中 timing 的硬阈值也相应下调（55 → 50），以适配新的输出域。

## 9. 接口契约（语义级）

### 9.1 timeline endpoint 增量

`GET /token-social-timeline` 在原有响应结构上追加：

- 每条 post 上增加：
  - `is_first_seen_by_watched_for_token`（来自 `account_token_alerts`，仅展示用，不参与排序）
  - `event_type`（来自 `social_event_extractions`，可能为 null）
  - `reference`（来自 `events.reference_json`，含 tweet_id / author_handle / type，可能为 null）
- 顶层增加 `cascade` 字段：每个事件的 `(event_id, parent_event_id, edge_type)` 列表，前端递归构树。

所有字段 optional；旧客户端忽略不影响功能。

### 9.2 catalyst 排序 endpoint

`GET /token-posts?sort=catalyst`：与现有 `sort=recent` 共享 endpoint，仅排序模式与响应增量不同。

catalyst 模式下每条 post 在 §9.1 的展示字段之外，再追加：

- `catalyst_score`（[0, 100] 标量）
- `catalyst_components`（六项派生分解，含跟进数、独立性、cascade grip、扩散时间、结构性 virality、跟进质量、观察窗口大小）

catalyst 模式第一版不支持游标分页（单次返回 ≤ 100 条）。理由：catalyst 排序键涉及条件字段，游标编码复杂，与产品价值不成比例。

### 9.3 timing 输出形态变化

`timing_score` 输出 `score_version` 从 `timing_v3` bump 到 `timing_v4`。`status` 字段域收敛为 §8.1 的 4 种。

下游消费者（`opportunity_scoring`、`token_signal_evaluation_service`）的兼容方式：

- `opportunity_scoring`：直接消费新版分数与权重（同步发布）
- `token_signal_evaluation_service`：靠 `score_version` 字段在评估时分桶（**前提是 evaluation SQL 增加 score_version 过滤**，见 §11）

## 10. 不在范围

- **pump 自动检测**：用户在前端选时间窗（默认 lookback=4h）。自动检测属未来增强。
- **catalyst 概率分布与 NULL 候选**：catalyst score 是单一标量加 components 透明分解，已经满足审计需求。
- **lead-lag 数字化输出**：把 price 与 mentions 同图渲染，让用户用眼看。
- **控制组配对 / Bayesian 归因 / ground truth 标注**：本期不引入任何统计推断。
- **反馈算子 / 权重学习**：`harness_credits` 维持 `report_only`。
- **新存储实体 / 新后台 worker**：catalyst 是 on-demand 派生。
- **衰减形状判别（Crane-Sornette endogenous vs exogenous）**：算法上可加，本期不上，作为下个版本候选。
- **跨链 / 同 token 多链 deployment 的合并复盘**：第一版按 token_id 单实体复盘，多链合并待后续。

## 11. 风险与演进路径

### 11.1 entity_key join 一致性

`account_token_alerts.entity_key` 与 `event_token_attributions.identity_key` 是否同一空间，决定了 §9.1 的 first-seen 字段能否正确 join。这是落地前**必须先做的诊断**，不通过则需要回退到按 `(event_id, entity_type, normalized_value)` join，或在写入侧统一 key。

### 11.2 隐式 echo 边的假阳性

cascade_grip 的"隐式 echo"（基于共享 anchor term）只能在 watched 事件上算（anchor terms 来自 LLM）。非 watched 事件 anchor terms 缺失会让 cascade_grip 偏低。第一版只用显式 quote/reply/retweet 边，把"隐式 echo"作为可选 stretch goal。

### 11.3 baseline_rate 估计偏差

§7.1 的 baseline 用 `(t_P − 1h, t_P)`。新 token 在 t_P − 1h 时 mentions ≈ 0，baseline ≈ 0，excess 会被打高；老 token 进入 viral 阶段后 baseline 也在涨，excess 会偏低。第一版接受这个偏差并在响应里标 baseline_status；下一版可以改用该 token 的 30 天 robust z 作 baseline。

### 11.4 实时计算成本

4h 窗口下单次 ≤ 50ms。极端 24h 窗口（候选 ≈ 800、跟进池 ≈ 8000），cascade_grip 的文本扫描可能 500ms。优化路径按需展开：4h 不优化，24h 加 LRU 缓存，极端情况物化视图。

### 11.5 catalyst 排序与 timing 视图的产品冲突

`sort=catalyst` 与 `sort=recent` 是不同的产品语义，前端必须用明确的切换控件，默认保持 `recent`，避免破坏现有用户的浏览习惯。

### 11.6 score_version 跨版本污染

`token_signal_evaluation_service` 当前评估 SQL 没有 `WHERE score_version = ?`。timing v3 → v4 之后旧/新 snapshot 在同一 evaluation 里混算会污染 hit rate。

**修法**：evaluation SQL 加 score_version 过滤。这是另一份 spec / plan 的事，本期可以不绑死，但 timing 截肢一旦上线，后续的 evaluation 数据需要标注"含 timing 切换噪声"。

### 11.7 权重微调对现有 alert 的影响

propagation +0.06 与 timing −0.06 总和为 0，但 opportunity 决策 5 个 component 阈值的命中分布会变。M7 的 ≤ 15% 偏移阈值是经验值。如实际偏移过大，回退路径优先调权重幅度（半幅过渡），而非回退 timing 截肢——错的就是错的。

### 11.8 演进路径

本期完成后的自然下一步候选，按价值排序：

1. **score_version 过滤**：把 evaluation 闭环修干净。
2. **隐式 echo 在非 watched 事件上的近似**：用确定性 entity 作为 anchor 替代品（已抽取的 cashtag / hashtag），让 cascade_grip 不再依赖 LLM 覆盖。
3. **decay shape 判别**：在 catalyst score 上加 Crane-Sornette 衰减分类，区分内生 viral 与外生 broadcast。
4. **30 天 robust z baseline**：替换 §7.1 的 1h baseline，提高新/老 token 的 excess 估计精度。
5. **跨链合并复盘**：同 symbol 多链 deployment 的统一视图。
6. **catalyst 物化视图**：当 24h 窗口并发上来时，按 PG materialized view 做预聚合。

每一步都是独立 spec / plan，不绑定本期。
