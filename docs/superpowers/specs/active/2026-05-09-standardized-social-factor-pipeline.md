# 标准化社交因子流水线 Spec

**状态**：草案，待评审  
**日期**：2026-05-09  
**作者**：Claude (with aaurix)  
**所属层**：Spec（回答 *why & what*；交付路径见对应 plan）

---

## 1. 背景

GMGN-twitter-intel 现有的打分链路由五个评分服务组成（`social_heat_scoring` / `propagation_scoring` / `discussion_quality_scoring` / `tradeability_scoring` / `timing_scoring`），由 `opportunity_scoring` 以固定权重 `(0.26, 0.22, 0.28, 0.18, 0.06)` 合成最终分。这套设计是渐进堆叠出来的：每加一个维度就在 opportunity 里多加一项加权，没有统一的因子工程框架做约束。

Phase 1（migration `20260509_0016` 与 `ops sync-gmgn-directory`，2026-05-09 合入 main）打通了 GMGN 平台订阅数据：`account_profiles` 现有 2991 行带 `gmgn_user_id` / `gmgn_user_tags` / `gmgn_platform_followers`。这给社交因子提供了一个**已经被 GMGN 平台用户筛选过的"trader-relevance"权重**——比从原始 Twitter API v2 拉 followers 高一阶。

但 Phase 1 的果实尚未被任何 scoring 服务消费：`token_radar_projection._source_rows` 的 SQL 不 JOIN `account_profiles`。同时一次架构审计（2026-05-09）发现 7 项稳定性 / 死代码问题 + 1 项整体架构件缺失（横截面归一化）。

本 spec 的任务：**用因子工程的标准方法把社交数据这一族重写一次**，使每条推文经过 `raw → atomic → window → normalize` 四层后，能产出可被下游模型（IC 评估、横截面排名、跨族合成）正确使用的标准化因子。

本 spec **不**涉及链上 holder 因子族、链上资金流因子族、Twitter API v2 engagement、LLM 模型升级——这些放到独立的 spec（参见 §10）。

## 2. 现状审计

### 2.1 我们已经收得下来的原始信号

每条 tweet 经过 `collector/normalizer.py` 后，`events` 表里有：`event_id`、`tweet_id`、`author_handle`、`author_followers`（GMGN WS 的 `f` 字段，对 `public_broadcast` 频道为 `NULL`）、`author_tags_json`（GMGN 的 `ut`）、`text_clean`、`cashtags_json`、`hashtags_json`、`received_at_ms`、`is_watched`、`raw_json`。

经过 `pipeline/entity_extractor.py` + `pipeline/deterministic_token_resolver.py`，每个 token 提及落在 `token_intent_resolutions`，状态枚举 `{EXACT, UNIQUE_BY_CONTEXT, AMBIGUOUS}`，绑定 `target_id`（asset UUID）。

经过 LLM enrichment worker（`pipeline/social_event_extraction.py`），`social_event_extractions` 表写入：`event_type`、`direction_hint TEXT`、`impact_hint DOUBLE PRECISION`、`semantic_novelty_hint DOUBLE PRECISION`、`is_signal_event BOOLEAN`、`confidence`。

Phase 1 之后，`account_profiles` 又多了 `gmgn_user_id`、`gmgn_user_tags TEXT[]`、`gmgn_platform_followers BIGINT`、`gmgn_directory_observed_at_ms`，覆盖 2991 个 trader-relevant 账号。

### 2.2 我们**没有**的信号（决定本 spec 的边界）

| 框架文献中常用的字段 | 我们的状态 | 替代策略 |
|---|---|---|
| `like_count / reply_count / retweet_count / quote_count / view_count` | 没有，GMGN WS feed 不携带 | 不算 `engagement` 与 `organic_score`；把"被多少 trader 订阅"当 curated 替代 |
| Twitter 数字 `author_id`（snowflake） | 部分账号有（GMGN 的 `user_id` 字段，base64 或 snowflake 字符串），handle 永远有 | 用 `gmgn_user_id` 做稳定 dedup，handle 做主键（已是现状） |
| `verified` 蓝标 | 没有 | 用 `gmgn_user_tags` ∋ `{kol, founder, master, celebrity, exchange, binance_square}` 当替代权重 |
| `account_created_at` | 没有 | 用 `account_profiles.first_seen_ms` 做近似（"被本系统首次观察到"，比真实账号年龄保守） |
| `bio` 静态值 | 没有（仅 bio 变更 delta 通过 `BioChange` 事件记录） | 不用 |
| 每条推的二级传播链路（被谁转发） | 没有 | 不算结构性 virality；用作者集合多样性（unique_authors / author_entropy）做近似 |

### 2.3 既有评分服务在四层框架下的位置

| 层 | 现有代码 | 状态 |
|---|---|---|
| **raw** | `events` / `token_intent_resolutions` / `social_event_extractions` / `account_profiles` | ✅ 信息齐 |
| **atomic** | `pipeline/token_radar_feature_builder.py` 内联 + LLM 表的 `direction_hint / impact_hint / semantic_novelty_hint` | ⚠️ LLM 抽出的语义信号尚未被 retrieval 层消费；author quality 只读 `events.author_followers`（不可靠）而非 `account_profiles.gmgn_platform_followers`（Phase 1 数据） |
| **window** | `token_radar_projection._source_rows`（一次 bulk SQL）+ `token_radar_feature_builder` 内存切窗（5m/1h/4h/24h） | ✅ 工作；窗口设置与社交信号 6–48h 半衰期相符 |
| **normalize** | `baseline_scoring`（per-token 时序 z，6 baseline slots EWMA） | ❌ 不完整：(a) EWMA 顺序依赖；(b) 没有跨币横截面 rank；(c) `opportunity_scoring` 用固定权重而非 z-score 加权 |

完整审计与文件行号证据在 2026-05-09 对话中已沉淀，不在此处重复展开（见 git log 上下文中 Explore agent 的输出）。

## 3. 问题诊断

### 3.1 不稳定问题（同输入产出不同分）

- **B1 顺序依赖的 baseline EWMA**：`baseline_scoring._ewma_stats` 在线累积，对 `slot_counts` 顺序敏感。SQL 不保证返回顺序时，相同数据可以产出不同 z-score。
- **B2 timing chase-risk 自相残杀**：`timing_scoring` 的 `price_change_before_social_pct` 取"严格在 event 之前"的最近一次 price observation。同 token 短时间内被两条 tweet 触发时，第二条会拿第一条 tweet 的 payload price 当 baseline，触发 chase risk → score 50 → 38。
- **B3 author_followers 取 WS feed 不可靠**：`events.author_followers` 对 `public_broadcast` 频道为 NULL；`diffusion_health.top_authors` 排序键含此字段，同账号在不同频道事件中表现不一致。

### 3.2 死代码 / 信号断流（已抽未用）

- **D1 `diffusion_health()` 整个函数死代码**：实现了正确的 propagation 计算（unique authors / effective authors / dedup / followers-weighted top authors），但仅 `text_fingerprint` 辅助函数被引用；本体没接进 `token_radar_feature_builder._propagation_features`，后者是一份更弱的内联实现。
- **D2 Phase 1 数据零集成**：`account_profiles.gmgn_platform_followers / gmgn_user_tags / gmgn_user_id` 没有 scoring 服务读取。
- **D3 LLM hints 死分**：`discussion_quality_scoring` 的 `llm_semantic_utility / llm_label_confidence` 输入槽永远是 `None`（feature builder 不 JOIN `social_event_extractions`），最大可贡献的 10 分**结构性死亡**。
- **D4 `seed_lag_ms` 永远 None**：`propagation_scoring.seed_points` 的 10/5 分支从未触发；`event_clusters` 表里有数据但不被 token-radar 消费。
- **D5 `account_quality_snapshots` 写后只读 API**：`precision_score / early_call_score / spam_risk_score` 只在 `/api/account-quality` 端点被读，没有任何 scoring 服务用作权重。

### 3.3 架构层缺件

- **A1 没有横截面归一化**：BTC 的 `heat=70` 与某新 meme 的 `heat=70` 在 `opportunity_scoring` 里被同等加权——**size 因子伪装成 alpha**。这是因子工程的核心错误。
- **A2 `score_version` 不是合约**：7 个服务都在输出 `score_version`，但 `token_score_evaluations` 表（migration `20260506_0001` 已建好，schema 完整：`(horizon, window, scope, score_version, bucket_label)` 主键）**零代码引用**。bump version 不会真的隔离 A/B 群体。
- **A3 没有 idempotency 合约**：缺乏"同输入 → 同输出"的 golden test。

## 4. 第一性原理

### 4.1 四层模型的不可压缩性

任何把 raw 直接 group-by 出 z-score 的因子，IC 必然偏低。中间两层（atomic、window）的工作必须显式做，因为：

- **atomic** 解决"信号语义"——一条推 mention 一个 token，是真的在讨论还是只是带过？这条推的发声人是否值得听？这条推的情感是看多还是看空？这些必须在单条记录粒度上解决，不能寄希望于聚合稀释噪声。
- **window** 解决"时间尺度匹配信号衰减"——社交话题的半衰期为 6–48 小时（Crane & Sornette 2008 PNAS, *Robust dynamic classes revealed by measuring the response function of a social system*）。窗口太短抓不到完整传播过程，窗口太长稀释 burst 信号。一个稳健的因子应当在多个窗口（5m/1h/4h/24h）并行计算，让下游模型按时间维度选用。
- **normalize** 解决"跨币可比"——同一时刻 BTC 与新 meme 的绝对量级差 5 个数量级。**必须做时序 z-score（按币内）和横截面 rank（按时刻）**两步，前者去 size，后者去截面分布形态。

### 4.2 适配本系统的关键调整

| 框架原版 | 本系统的适配 | 理由 |
|---|---|---|
| `quality = log1p(followers) × verified_factor × age_score` | `quality = log1p(gmgn_platform_followers) × tag_weight × first_seen_age_score` | GMGN 平台订阅数比原始 Twitter followers 更接近"对加密交易者的影响力"——已经被 ~10 万 GMGN 用户隐式投票。Bakshy et al. 2011 (WSDM, *Everyone's an Influencer*) 显示原始 followers 与传播量相关性极弱；GMGN 订阅是带选择偏置的"trader-curated 关注度"。 |
| `engagement = likes + 2·replies + 3·quotes + 1.5·retweets` | **不计算**；用作者权重 + 多账号独立性替代 | 数据物理上拿不到。把 `engagement_sum` / `organic_score` / "付费推广嫌疑"这一族信号整体砍掉，避免拿 0 当 0 用。 |
| `sentiment ∈ [-1,1]` 通过 LLM 抽 | 直接复用 `social_event_extractions.direction_hint`（已离线产出） | LLM 调用成本已发生在 enrichment_worker，不重复调用。 |
| `novelty = 1 − cos(emb_today, emb_30d_centroid)` | 复用 `social_event_extractions.semantic_novelty_hint` | 同上，已经离线计算过。 |
| `bot_proba` botometer | **不做**；相信 GMGN 已用 platform-follower-curation 完成隐式去 bot | 自建 bot 检测属于 CLAUDE.md "premature complexity"；GMGN 平台订阅本身就是反 bot 投票（机器人不会被人工订阅）。 |

### 4.3 为什么砍 engagement 反而更干净

加密推上 engagement 是 bot-dominated（Bakshy et al. 2011 的发现到加密领域更极端）。failing 的产品方向是"把所有 engagement 加权"，胜出的方向是"找到真正会被交易者关注的 KOL 并加权"。Phase 1 的 `gmgn_platform_followers` 直接给我们后者，跳过整个反 bot 工程。**这是少数"约束变成优势"的情形**。

### 4.4 横截面 rank 的不可省

跨币因子合成的标准公式是 `signal = z_within_token(x) → rank_within_universe → family_aggregate → cross_family_combine`。少了横截面那一步，所有"BTC 一直 mention 多"的情况会持续给 BTC 一个高分；factor IC 会被 size 因子吃掉。Goel et al. 2016 (*Management Science*, *The Structural Virality of Online Diffusion*) 的核心论点是：传播规模的对数差异主要由 size 决定，去 size 才能露出 virality 真实分布。

## 5. 目标与可证伪指标

每条目标后括号给出"如何观测这条目标是否达成"。目标按优先级降序排列。

### 5.1 一级目标（Phase 2.x 必须达到，否则不上线）

- **G1 幂等性合约**：对一份固定的 fixture 数据集，`opportunity_score` 和所有 5 个分项分数 100% 可重复。  
  *观测*：golden test 在 CI 跑两次，diff 必须为空。预期失败前置 `B1 / B2 / B3` 都必须先修。

- **G2 Phase 1 数据消费率**：retrieval 层的"作者权重"取数有 ≥ 80% 命中 `account_profiles.gmgn_platform_followers`（剩余 20% 是非 directory-covered 账号，回落到 `events.author_followers`）。  
  *观测*：在每次 token-radar 项目重建时统计。

- **G3 横截面 rank 在 API 响应可见**：`opportunity_scoring` 的输出新增 `cross_section_rank` 字段（per-window-cohort 内的百分位排名 ∈ [0, 1]），且每个原子信号 z-score 在 `extra` 中可见。  
  *观测*：API 响应 schema 测试。

- **G4 score_version 是合约**：`token_score_evaluations` 表每天有新行写入，`(horizon, window, scope, score_version, bucket_label)` 维度齐全。下游评估服务只读"当前 score_version"的行。  
  *观测*：每日 cron 巡检；bump score_version 后 24h 内能在表里看到新版本的桶。

- **G5 Bot-pattern 鲁棒性**：单作者 copy-pasta 集群（5 条相同 fingerprint 的推、同一 author）在新 attention 因子上的得分**严格小于** 5 条独立 author 的有机讨论。  
  *观测*：unit test 用 fixture 直接断言。CLAUDE.md 明文要求。

### 5.2 二级目标（Phase 3 评估，作为继续投入的判据）

- **G6 IC 下限**：至少 1 个新增族级因子（`attention / quality / sentiment / narrative` 之一）在 24h forward return 上的 60-day 滚动 Spearman IC ≥ 0.05，ICIR ≥ 0.3。  
  *观测*：`token_score_evaluations` 中可读出。低于阈值则该族继续观测，不进 opportunity composite。
- **G7 与既有 opportunity_score 相关性**：新合成的 `social_composite_v1` 与现有 `social_opportunity_v3` 的 30 天滚动相关系数应在 [0.4, 0.85] 之间。低于 0.4 说明完全不同信号（需重新审视设计）；高于 0.85 说明换汤不换药（不值得上线）。  
  *观测*：每周回归。

### 5.3 显式不追求的目标

- **不**追求"打败所有现有评分"。本 spec 的目标是把基础设施做对，使得后续评分实验有方法论保证。
- **不**追求"端到端高 IC 的单因子"。社交因子单独 IC 通常在 0.03–0.10，与 holder/flow 因子合成才显著。
- **不**追求"实时低延迟"。社交信号衰减 6h 起步，分钟级延迟可接受。

## 6. 目标架构

### 6.1 四层职责划分

```
┌─────────────────────────────────────────────────────────────┐
│ raw   : events / token_intent_resolutions /                 │
│         social_event_extractions / account_profiles         │
│         （现有，不增不减）                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ atomic: 每条 mention 计算 5 个 per-event 信号               │
│   - tweet_quality           (作者层)                        │
│   - mention_confidence      (token 提取层)                  │
│   - tweet_sentiment         (LLM direction_hint)            │
│   - tweet_novelty           (LLM semantic_novelty_hint)     │
│   - tweet_impact            (LLM impact_hint)               │
│ 实现位置: token_radar_feature_builder 扩展，按 token 分组前 │
│   先在 mention 粒度算原子信号                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ window: 4 个并行窗口 (5m/1h/4h/24h) 内聚合 atomic           │
│   per token, per window, 产出 ~12 个 raw 聚合量             │
│   实现位置: token_radar_feature_builder 现有扩展            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ normalize: 两阶段                                           │
│   a) 时序 z-score (per-token rolling baseline 14–30天)     │
│   b) 横截面 rank (per-window-cohort)                       │
│ 实现位置: 扩展 baseline_scoring + 新增 cross_section helper │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ compose: 4 个族 → 1 个 social composite                    │
│   attention / quality / sentiment / narrative              │
│   族内 = mean of z-rank scores                              │
│   族间 = 等权重 (Phase 2.x), IC-weighted (Phase 3, 单独spec)│
│ 实现位置: 新增 social_composite_scoring，与现有             │
│   opportunity_scoring 并行运行；不替换                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ settle / eval:                                              │
│   - settlement: harness_outcomes 已有                       │
│   - eval: 把 (score, score_version, bucket, fwd_return)    │
│           写入 token_score_evaluations (现表，新写入路径)   │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 核心因子族定义

每个族包含一组语义同类的归一化信号，族内简单平均（不做 PCA）。

#### 6.2.1 Attention 族（关注度的"量"）

度量 token 在窗口内被讨论的体量与传播广度。包含：

- **`mention_count_z_rank`**：窗口内总提及数（按 mention_confidence 加权求和）的时序 z 后再做横截面 rank。
- **`weighted_mention_z_rank`**：`Σ confidence × tweet_quality` 的归一化形式。这是 attention 族的核心信号——它把"被多少 trader-relevance 高的人说"和"被说了多少次"捆在一起。
- **`unique_authors_z_rank`**：`nunique(author, weight=confidence)` 的归一化形式。直接对抗"单人刷量"。

族分数 = 三者均值。

#### 6.2.2 Quality 族（讨论是否健康，反 bot）

度量 token 讨论的多样性与组织程度。包含：

- **`kol_share_z_rank`**：`Σ confidence × 1[author has tag ∈ {kol, founder, master, exchange}] / Σ confidence` 的归一化形式。GMGN 编辑标签替代了"verified 蓝标"。
- **`author_entropy_z_rank`** *(取负号)*：作者分布的香农熵，越高越分散。取负号后高分代表"集中刷"风险高。
- **`duplicate_text_share_z_rank`** *(取负号)*：`text_fingerprint` 后最大重复占比。取负号后高分代表"copy-pasta"风险高。

族分数 = 前一个的 z-rank 减后两者 z-rank 的 0.5 倍（对抗信号）。

#### 6.2.3 Sentiment 族（共识与方向）

度量 token 讨论的情感方向与一致程度。**关键设计**：情感分数必须用提及量做置信度门控，0 提及的高情感是噪声。

- **`sentiment_mean_weighted`**：`Σ direction × tweet_quality / Σ tweet_quality`，方向值取自 `social_event_extractions.direction_hint`（映射 `bullish=+1, neutral=0, bearish=-1`）。
- **`sentiment_disagreement`**：`std(direction)` 加权后；高分代表共识低（可能是叙事撕裂）。

族分数 = `sentiment_mean_weighted × sqrt(min(1, mention_count_normalized))`。  
"× √量"是文献中的标准 confidence gating（参考 *Empirical Bayes shrinkage* 思路），把缺数据时的极端值收缩到 0 附近。

#### 6.2.4 Narrative 族（新叙事 vs 老话题）

度量 token 是否承载新的叙事元素。

- **`novelty_score`**：`mean(semantic_novelty_hint × tweet_quality) / mean(tweet_quality)`。
- **`tag_diversity`**：`nunique(author tags ∋ {kol, founder, master, ...})`，跨 GMGN 编辑标签的传播宽度（替代框架中的 `community_count`）。

族分数 = `novelty_score × log1p(tag_diversity)`。

#### 6.2.5 Composite

`social_composite_v1 = mean(attention, quality, sentiment, narrative)`，等权重起步。每个族分数都已是横截面 rank 后的 [-1, 1] 数值，直接平均没有量纲问题。

**重要**：这个 composite **不替换** `opportunity_scoring.social_opportunity_v3`，而是作为新增字段并行输出。两者的相关性会被持续监测（G7）。

### 6.3 既有组件的处置

| 组件 | 处置 | 理由 |
|---|---|---|
| `social_heat_scoring` (`social_heat_v2`) | **保留并修复 B1**；继续输出，与新 attention 族并行 | 用户已经在看；先稳定，不重写 |
| `propagation_scoring` (`propagation_v2`) | **保留**；接入 `diffusion_health()` 替换内联实现（修 D1）；接入 `seed_lag_ms` (修 D4) | 内核合理，主要是死信号没接 |
| `discussion_quality_scoring` (`discussion_quality_v2`) | **保留**；接入 LLM hints (修 D3) | 死分槽位接上即可 |
| `tradeability_scoring` / `timing_scoring` | **保留**；timing 修 B2；不进社交因子合成（不属于社交族） | 这两个是市场流动性维度 |
| `opportunity_scoring` (`social_opportunity_v3`) | **保留固定权重版本**；新增 `social_composite_v1` 字段并行输出 | 不破坏既有接口 |
| `diffusion_health()` | **接入 propagation_scoring 链路**（修 D1） | 已经写好，复用 |
| `baseline_scoring` | **修 B1（顺序确定性）+ 扩展 baseline 窗口到 14d** | 内核保留 |
| **新增** `cross_section_normalizer` | per-window cohort 内的 rank 工具 | 缺这个组件 |
| **新增** `social_composite_scoring` | 4 族合成、emit 新版本字段 | 新功能 |
| **新增** `token_score_evaluations` 写入路径 | 让 score_version 真成合约（修 A2） | eval 表已建只是没人写 |

**不新增**：任何持久化表（`token_score_evaluations` 已存在）、任何新 worker、任何新 LLM 调用、任何 PCA / GBDT 实现。

## 7. 概念数据流

一条新 tweet 抵达后，要走完以下逻辑步骤才能成为打分输入。每步标注**计算 vs 持久化**——大多数原子信号是按需派生的，不入新表。

```
Step 1 (持久化): WS → events / event_token_mentions
Step 2 (持久化, async): events → social_event_extractions (LLM enrichment_worker)
Step 3 (持久化): event_token_mentions → token_intent_resolutions (resolver)
Step 4 (按需派生): mention 粒度的 5 个 atomic 信号
        - 在 token_radar_projection rebuild 时通过 SQL JOIN account_profiles +
          social_event_extractions 拿齐输入
        - 在 Python 中按公式算出 (tweet_quality, mention_confidence, sentiment,
          novelty, impact) 5-tuple
Step 5 (按需派生): per-token-per-window 聚合 → 12 个 raw 聚合量
Step 6 (按需派生): per-token 时序 z-score (rolling 14d baseline)
Step 7 (按需派生): per-window-cohort 横截面 rank
Step 8 (按需派生): 4 个族分数 + 1 个 composite
Step 9 (持久化): 写入 token_radar_rows.score_json (现有)
Step 10 (持久化, 定期 settle): forward return 计算 (harness_outcomes 现有)
Step 11 (持久化, 定期 aggregate): score_version × bucket × horizon → 
        token_score_evaluations 行
```

**点之间的契约**：
- Step 4 的输出对每个 mention 是确定性的（同输入→同 5-tuple），不依赖历史状态。
- Step 5 → Step 6 之间的 baseline 是只读历史，不依赖未来观察（防 look-ahead bias）。
- Step 7 的 cohort 定义见 §8.2。
- Step 11 是 score_version 真成合约的关键步骤：每行带 `score_version` 标签，下游评估只看当前版本。

## 8. 核心数据模型（语义层，非 schema）

### 8.1 Atomic mention record

每个被解析出的 token mention 都对应一个 atomic record（按需派生，不入新表，由 `token_radar_feature_builder` 的扩展函数返回）：

```
{
  mention_id: <复合 key, 来自 event_id + target_id>,
  token_id, window_anchor_ts,
  tweet_quality:        float ∈ [0, 1],         # 作者层置信
  mention_confidence:   float ∈ {1.0, 0.85, 0}, # 来自 resolution_status
  tweet_sentiment:      float ∈ [-1, +1],       # bullish/neutral/bearish
  tweet_novelty:        float ∈ [0, 1],         # LLM
  tweet_impact:         float ∈ [0, 1],         # LLM
  author_handle:        string,                  # 用于 author_entropy
  author_tags:          list[string],            # 用于 kol_share / tag_diversity
  text_fingerprint:     string,                  # 用于 duplicate_text_share
}
```

`tweet_quality` 公式：
```
quality = log1p(gmgn_platform_followers OR events.author_followers OR 1) / log1p(100000)
        × tag_weight(author_tags)
        × age_score(now − account_profiles.first_seen_ms)
```
- `gmgn_platform_followers` 命中时直接用；否则回落到 `events.author_followers`，再否则用 1（log1p(1)=0.69，给个最低权）。
- `tag_weight`: `kol/founder/master = 1.0`, `exchange/binance_square/celebrity/politics/media/companies = 0.85`, `trader/other = 0.7`, 无标签 = 0.5。
- `age_score = min(1, age_days / 180)`，半年新号给 < 1 权。

`mention_confidence` 映射：`EXACT → 1.0`, `UNIQUE_BY_CONTEXT → 0.85`, `AMBIGUOUS → 0`（直接丢弃）。

### 8.2 Cohort 的定义（横截面 rank 的关键）

横截面 rank 必须有明确的"参与者集合"。本系统定义：

> 在窗口 `W` 结束时刻 `t` 的 cohort = 满足以下任一条件的 token：
> 1. `W` 窗口内有 ≥ 1 条带 mention_confidence ≥ 0.85 的提及，**或**
> 2. `W` 窗口内有 ≥ 1 条来自 `gmgn_user_tags ∋ {kol, founder, master}` 作者的 mention（无门槛），**或**
> 3. 在 `[t-24h, t]` 内有 ≥ 1 条 `account_token_alerts.is_first_seen_global = true` 记录。

第 3 条专门防"刚出生的 token 没基础流量但应该进 cohort"。

排除：稳定币（USDT / USDC / DAI / FDUSD / TUSD 等），按 `registry_assets.symbol` 黑名单过滤。**这避免框架 §五 §4 的稳定币污染问题**。

### 8.3 Factor record 的可观测合约

每个 token-window-snapshot 的 score_json 必须包含：

```
{
  score_version: "social_composite_v1",
  composite_score: float,            // 主分
  cross_section_rank: float ∈ [0,1], // 同 cohort 百分位
  family_scores: {
    attention: float, quality: float, sentiment: float, narrative: float
  },
  family_components: {
    attention: { mention_count_z_rank, weighted_mention_z_rank, ... },
    quality: { kol_share_z_rank, ... },
    ...
  },
  atomic_mention_summary: {
    n_mentions, n_unique_authors, n_kol_authors,
    median_quality, kol_share, max_text_repeat,
    sentiment_distribution: {bullish:n, neutral:n, bearish:n},
    novelty_p90: float, impact_p90: float
  },
  baseline: { window_days, n_slots_used, mean, std, status },
  cohort: { size, definition_version }
}
```

**所有族级与 composite 分数都必须可被反推回 atomic 信号**——CLAUDE.md 明文要求"black-box scores are forbidden"。

## 9. 接口契约

### 9.1 与 `token_radar_projection` 的契约

- `token_radar_feature_builder` 必须新增 mention-level 中间步骤，先产出 atomic record list，再做 per-token aggregation。
- 现有的 `social_heat / discussion_quality / propagation` 三个 family score 字段保留，新增 `social_composite` 与 `family_scores` 节点。
- `score_json` schema 向前兼容：新增字段不影响现有消费方解析。

### 9.2 与 `harness_outcomes` / `token_score_evaluations` 的契约

- 每次 `token_radar_projection` rebuild 时，把 `(score_version, score, bucket_label, asset_id, window, scope, horizon, generated_at_ms)` 的元组缓存到一个 settlement-ready 视图。
- `harness_settlement` 在 forward 区间到期时计算 `actual_return / abnormal_return`，然后聚合成 `token_score_evaluations` 行（按 `(horizon × window × scope × score_version × bucket_label)` group by）。
- 评估读取端**强制按 `score_version` 过滤**，禁止跨版本聚合，避免污染 IC 估计。

### 9.3 幂等性合约

- 给定相同的 `(events, token_intent_resolutions, social_event_extractions, account_profiles, price_observations)` 输入快照与相同的 `now_ms`，`token_radar_projection.rebuild()` 必须产出 byte-identical 的 `score_json`。
- 这条合约由 golden test 强制：fixture 跑两次 diff 必须为空（CI 红灯）。

### 9.4 Cohort 一致性合约

- 同一 `(window, generated_at_ms)` 下，所有 token 的 `cross_section_rank` 必须基于相同的 cohort 集合。即：rank 计算在 token-radar 全量重建的最后一步统一进行，不能 per-token 单算。

## 10. 范围外（明确不在本 spec）

按 CLAUDE.md "Out-of-scope" 纪律，以下项**不**在本 spec 中讨论或交付：

- **Twitter API v2 / engagement counts**：用户 2026-05-09 显式确认放弃。`gmgn_platform_followers` 是已经过 trader-curation 的代理。
- **链上 holder 因子族**：缺数据源（需 Helius/Bitquery/Solscan/自建 indexer），单独 spec。
- **链上资金流因子族（CEX netflow / smart money / whale）**：同上。
- **Bot 检测增强**：依赖 GMGN 平台订阅的 trader-curation 隐式去 bot；自建 botometer 等属于 CLAUDE.md "premature complexity"。
- **LLM 模型升级 / 替换 / fine-tuning**：复用 `social_event_extractions` 现有产出，不动 enrichment 链路。
- **新表持久化 atomic mention records**：按需派生，不持久化；理由：mentions 已在 `event_token_mentions` 全量在表，atomic 只是几个 column 的算术变换。
- **PCA / GBDT / IC-weighted family combination**：Phase 3 单独 spec；本 spec 用等权重族内 + 等权重族间起步。
- **新 LLM 调用**：所有语义信号复用 `social_event_extractions` 已有字段。
- **替换 `opportunity_scoring`**：新 composite 与旧 score 并行输出，不破坏现有 API 消费方。
- **回测框架重构**：复用 `harness_outcomes` 现有 settlement，新增 `token_score_evaluations` 写入路径而已。
- **Survivorship bias 修复**：现有 `registry_assets` 已用 soft-delete（`is_active` 标志）保留死币，本 spec 默认其足够；如不够则单独 spec。
- **Factor exposure on factor returns 类高阶分析**：完全 Phase 3+。

## 11. 风险

### 11.1 设计层风险

- **R1 LLM hints 噪声**：`semantic_novelty_hint / impact_hint / direction_hint` 是 LLM 输出，本身有抽取误差。  
  *缓解*：按 `social_event_extractions.confidence` 加权；低于 0.6 的 mention 在 atomic 层降权 50%；narrative 族对此最敏感，若 IC 低于阈值优先怀疑该族而不是怀疑整套框架。

- **R2 Cohort 定义漂移**：cohort 是横截面 rank 的根；定义变化会导致同一 token 在不同时刻进出 cohort，影响时序可比。  
  *缓解*：cohort 定义版本号与 `score_version` 联动；任何调整都 bump version；评估只看同版本数据。

- **R3 baseline 窗口长度取舍**：14 天太短可能仍受 burst 污染，30 天太长可能跨越 regime。  
  *缓解*：用 5% 截尾 mean/std（trimmed statistics）抵抗 burst；对 baseline 不足 7 天的 token 标记 `baseline_status = "insufficient_history"` 并跳过 z-score 步（直接用横截面 rank）。

- **R4 score_version 频繁 bump**：每次小调整 bump 会让 `token_score_evaluations` 行数稀疏，IC 估计不稳。  
  *缓解*：约定"只在改变 atomic / window / normalize 任一层公式时 bump"，参数微调不 bump；约定 version 一旦 bump 必须等待至少 14 天 forward return 累积才能比较。

### 11.2 实现层风险

- **R5 cross-section rank 在 SQL vs Python 实现的一致性**：rank 必须在所有 token 都 ready 后统一算，而不是 per-token 增量。  
  *缓解*：在 `token_radar_projection.rebuild()` 末尾加一个独立 normalize pass，所有 score 算完后做一次跨币 rank。

- **R6 backtest-live consistency**：原子信号公式必须对历史 replay 与实时流跑出完全相同结果。  
  *缓解*：原子信号实现是纯函数，不读时钟；历史 replay 时把 `now_ms` 显式传入。golden test 跨"历史 fixture"和"实时 fixture"两份覆盖。

### 11.3 衡量层风险

- **R7 IC 估计样本不足**：项目运行天数较短，每个 score_version × bucket 维度可能样本量 < 30。  
  *缓解*：评估前用 Wilson 置信区间（`token_score_evaluations.wilson_low / wilson_high` 已有列）报告区间；样本量 < 30 标记 `evidence_quality = low`，不做决策。

- **R8 Bot pattern 测试通过≠生产防御**：unit test 用的是构造 fixture，可能覆盖不到真实生产的攻击模式。  
  *缓解*：每月手工抽样 top-10 attention rank token，目视检查作者列表；发现异常模式补充 fixture。

## 12. 演进路径

按"做一段、跑一段、再决定"的节奏。每段产出明确的可观测条件。

### Phase 2.0 — 把基础设施做对（必须做）

**目标**：达到 G1 / G2 / G3。

- 修复 B1（baseline 顺序依赖）、B2（timing 不幂等）、B3（author_followers 取数）。
- 接入 Phase 1 数据：`_source_rows` SQL JOIN `account_profiles`，atomic 层用 `gmgn_platform_followers` 算 `tweet_quality`。
- 引入 `cross_section_normalizer` 模块，per-window-cohort 内做 rank。
- 增加 `composite_score` 与 `cross_section_rank` 字段到 `token_radar_rows.score_json`。
- 引入 idempotency golden test。

**进入 Phase 2.1 的判据**：G1 测试连续绿 7 天；G2 命中率 ≥ 80%。

### Phase 2.1 — 接入已抽未消费的语义信号（建议做）

**目标**：达到 G5。

- 修复 D1（接 `diffusion_health` 进 propagation_scoring）、D3（接 LLM hints 进 discussion_quality）、D4（接 event_clusters 进 seed_lag_ms）。
- 实现 `social_composite_scoring`，4 个族级因子等权合成，输出 `social_composite_v1`。
- 增加 bot-pattern unit test（copy-pasta vs 独立讨论的 attention 因子排名）。

**进入 Phase 2.2 的判据**：bot-pattern test 通过；`social_composite_v1` 与 `social_opportunity_v3` 在生产数据上的相关性在 [0.4, 0.85]。

### Phase 2.2 — 让 score_version 成为合约（必须做）

**目标**：达到 G4。

- 实现 `token_score_evaluations` 写入路径，由 `harness_settlement` 在 forward return 到期时聚合。
- 评估读取端按 `score_version` 强制过滤。
- 增加每日 cron 巡检：每个活跃 score_version 应当每天有新行写入。

**进入 Phase 3 的判据**：`token_score_evaluations` 累积 ≥ 14 天数据，能给出第一个 IC 数字。

### Phase 3 — IC 加权与跨族合成（单独 spec）

**目标**：达到 G6 / G7。

不在本 spec 范围。占位说明：当前 Phase 2.x 的等权重族间合成是基线；Phase 3 引入 `rolling_ic_weights` 用 forward return 调权；同时探索是否引入 holder/flow 因子族（届时已有 holder/flow spec）。

## 13. 文献依据

公式选择援引以下文献作为设计基础：

- **Crane, R., & Sornette, D. (2008)**. *Robust dynamic classes revealed by measuring the response function of a social system*. PNAS 105(41). → 社交话题半衰期 6–48h 的经验值，决定 5m/1h/4h/24h 窗口设置。
- **Goel, S., Anderson, A., Hofman, J., & Watts, D. (2016)**. *The Structural Virality of Online Diffusion*. Management Science 62(1). → 横截面 rank 的必要性论证；size 因子去除。
- **Bakshy, E., Hofman, J., Mason, W., & Watts, D. (2011)**. *Everyone's an Influencer*. WSDM 2011. → 原始 followers 与传播相关性弱的论证；用 trader-curated `gmgn_platform_followers` 替代的依据。
- **Kleinberg, J. (2002)**. *Bursty and Hierarchical Structure in Streams*. KDD 2002. → `social_heat_scoring` 的 burst 检测概念基础；本 spec 中用 trimmed-EWMA 实现简化版。
- **Cheng, J., Adamic, L., Dow, P., Kleinberg, J., & Leskovec, J. (2014)**. *Can Cascades be Predicted?*. WWW 2014. → cascade 预测中的 unique authors / time-to-second-share 重要性；支持 `unique_authors` 与 `seed_lag_ms` 的因子地位。
- **Centola, D. (2010)**. *The Spread of Behavior in an Online Social Network Experiment*. Science 329. → 复杂传染需多次曝光；支持 `weighted_mention` 的乘法形式而非求和。

---

## 附录 A：与现有 score_version 的关系

| 现有 | 新输出 | 关系 |
|---|---|---|
| `social_heat_v2` | `social_heat_v3`（修 B1 后 bump） | atomic 公式不变，baseline 顺序确定性修复 |
| `propagation_v2` | `propagation_v3`（接 diffusion_health + seed_lag_ms 后 bump） | 死信号接活，公式扩展 |
| `discussion_quality_v2` | `discussion_quality_v3`（接 LLM hints 后 bump） | 死分槽位接上 |
| `tradeability_v2` | 不变 | 非社交族 |
| `timing_v4` | `timing_v5`（修 B2 后 bump） | chase risk 公式调整 |
| `social_opportunity_v3` | 不变（保留） | 等权重旧版继续运行 |
| — | **新增** `social_composite_v1` | 4 族等权合成 |

bump 节奏：每个修复独立 PR、独立 bump、独立 14 天 evaluation 累积。

## 附录 B：与"框架原版"的差异速查

| 框架原版 | 本 spec | 差异原因 |
|---|---|---|
| 原子信号包含 `engagement / organic_score` | 不包含 | GMGN WS 不传 engagement counts |
| 原子信号包含 `toxicity = bot_proba` | 不包含 | GMGN trader-curated followers 隐式去 bot |
| `quality = log1p(followers) × verified × age` | `quality = log1p(gmgn_platform_followers) × tag_weight × first_seen_age_score` | 数据替代 |
| LLM 抽 sentiment / novelty | 复用 `social_event_extractions` | 已离线产出 |
| 时序 z 用 `rolling_mean/std` 30天 5%截尾 | 14 天 trimmed EWMA + 5% 截尾 | 项目运行时间短，30 天太奢侈 |
| 横截面 rank | per-window-cohort rank | 显式定义 cohort（`§8.2`） |
| 族内 PCA 或 mean | 等权 mean | 样本量不足做 PCA，等权先稳 |
| 跨族 IC/ICIR 加权 或 GBDT | 等权 mean（Phase 2.x），IC 加权（Phase 3） | 分阶段，避免 premature complexity |
| 验证清单 6 项 | 用 `token_score_evaluations` schema 提供 5 项（Wilson、IC、ICIR、bucket 多空、cohort coverage）；regime 分段在 Phase 3 | schema 已有 |
