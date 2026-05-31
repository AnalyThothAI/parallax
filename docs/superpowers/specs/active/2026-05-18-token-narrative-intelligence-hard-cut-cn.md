# Spec — Token Narrative Intelligence Hard Cut

**Status**: Draft, awaiting review
**Date**: 2026-05-18
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/FRONTEND.md`
- `docs/DESIGN_DISCIPLINE.md`
- `src/parallax/domains/token_intel/ARCHITECTURE.md`
- `src/parallax/domains/pulse_lab/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-14-token-case-redesign-cn.md`
- `docs/superpowers/specs/active/2026-05-14-pulse-decision-context-narrative-cn.md`
- `docs/superpowers/specs/active/2026-05-18-pulse-agent-runtime-hard-cut-cn.md`

## 一句话

把 Token Radar 和 Token Case 从"热度/传播统计"升级成"可交易叙事读模"：新增独立 `narrative_intel` 域，沉淀 per-mention 语义、token-window 叙事簇、24h discussion digest；Token Radar 组合展示叙事摘要和公开 Pulse overlay，Token Case 展示完整多空/传播/反身性 dossier。Signal Pulse 可以消费这些叙事证据，但不能成为 Radar 的上游，也不能写 Radar 或 Digest。

## 背景

当前系统已经有三条清晰链路：

1. **Token Radar 是扫描面。** 前端架构写明 Token Radar 是 scan surface，主行点击进入搜索上下文，已知 canonical target id 时可进入 Token Case dossier（`docs/FRONTEND.md:48-49`）。后端架构写明 Token Radar 是 persisted pipeline，不是 UI regex，也不是 API payload 重建；生产链路从 GMGN frame 到 `TokenRadarProjectionWorker -> token_radar_rows.factor_snapshot_json -> read models / Signal Pulse / notifications -> HTTP / WebSocket / CLI / frontend`（`src/parallax/domains/token_intel/ARCHITECTURE.md:7-29`）。

2. **Token Case 是持久详情页。** `/token/:targetType/:targetId` 由 `features/token-case` 拥有，解析 URL 里的 `window`、`scope`、timeline sort，调用 `/api/token-case`，用 dossier 的第一页种子数据启动 `/api/target-posts`，并且只订阅当前 target 的 live market updates（`docs/FRONTEND.md:48`）。这个页面位置是对的，但现在缺少真正的叙事读模。

3. **Signal Pulse 是证据优先的决策读模。** Pulse 架构说明它把 Token Radar projection rows 变成可 replay 的 Pulse decisions，但 PostgreSQL material facts 仍是唯一业务真相；LLM 不自己获取关键事实，只能在 sealed `PulseEvidencePacket` 里综合、质疑和引用 refs（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:8-12`）。Pulse public read model 只暴露带 `evidence_packet_hash` 的 `display_*` rows（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:93-103`），且 Pulse 明确不能写 `token_radar_rows`（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:113-122`）。

这些链路受几条项目级约束保护：material facts 和 rebuildable read models 分离（`docs/ARCHITECTURE.md:31-37`）；每个 derived read model 只有一个 runtime writer（`docs/ARCHITECTURE.md:55-66`）；`NOTIFY` 只是 wake hint，不是真相（`docs/ARCHITECTURE.md:67-71`）；hard cut 删除旧 runtime path，不保留回退分支（`docs/ARCHITECTURE.md:72-75`）；API surface 只翻译 domain calls，不能做 scoring、token resolution、raw SQL joins 或 provider calls（`docs/ARCHITECTURE.md:196-202`）。

现有 Token Radar 的"WHY NOW"还停留在扫描解释层。`buildTokenRadarCompactCase` 把 narrative 组装成 phase + informative post count，再取第一个 risk 或 reason 文案（`web/src/shared/model/tokenRadarCompactCase.ts:33-44`, `web/src/shared/model/tokenRadarCompactCase.ts:174-191`）。这能说明"为什么它进列表"，但不能说明"大家围绕这个币到底在炒什么"：是利好叙事、恐慌叙事、嘲讽传播、价格 chase、scanner 复读，还是被另一个 token/主题 hijack。

现有 Token Case 有 deterministic `agent_brief`，但它不是叙事智能。`build_token_agent_brief` 明确返回 `generated_by: deterministic`（`src/parallax/domains/token_intel/read_models/search_agent_brief.py:37-40`）。它的 bull/bear 文案是围绕作者扩散、watched handle、流动性缺口写的模板（`src/parallax/domains/token_intel/read_models/search_agent_brief.py:56-83`）。这作为安全占位可以接受，但无法回答产品经理和 meme 交易员真正要的问题：过去 24 小时围绕这个币的主叙事是什么，谁在传播，多空分别拿什么证据说话，反身性处在哪个阶段。

现有 Mention Timeline 缺语义标签。`token_target_post_payload` 序列化了 event id、作者、文本、attribution、watched 状态、post quality、stage phase、author role、代表帖标记和 price delta（`src/parallax/domains/token_intel/read_models/token_target_post_serializer.py:29-57`）。它没有 stance、attention valence、narrative cluster、claim type、evidence type、co-mentioned targets、semantic confidence。用户能读原帖，但系统没有把原帖组织成可交易叙事。

后端已经有一个很早期的 semantic catalyst 插槽。Radar projection 会聚合 `llm_direction_hint`、`llm_impact_hint`、`llm_semantic_novelty_hint`、`llm_label_confidence`（`src/parallax/domains/token_intel/services/token_radar_projection.py:474-499`）。factor snapshot 里也有 `direction_counts`、`impact_mean`、`novelty_mean`、`confidence_mean`、`llm_covered_mentions`、`mentions`、`semantic_coverage`（`src/parallax/domains/token_intel/scoring/factor_snapshot.py:231-263`）。但它现在是 score-family ingredient，不是 per-post timeline label，也不是 token-window discussion digest。

2026-05-18 的本地运行观测也支持这个判断。按项目要求先运行了 `uv run parallax config`，确认活跃配置来自 `/Users/qinghuan/.parallax/` 下的 operator-owned config/workers 文件，没有打印 secrets。随后观察本地服务：Token Radar 新鲜且有大量 rows，但 top rows 的 `llm_covered_mentions=0`，direction counts 为空；SOL Token Case 24h 有足够原帖和作者可以分析叙事，但 UI 仍主要展示数量、phase 和未标注 timeline；Signal Pulse 内部有 candidates，但 public items 可以因为 display gates 返回 0。这说明 Pulse 可作为公开决策 overlay，但不能作为 Radar/Token Case 的唯一叙事来源。

## 问题

meme 币交易员需要的不只是"哪个 token 正热"，而是"现在市场正在递归交易哪个故事"。当前 Token Radar 能回答发现问题：帖子数、作者数、传播阶段、市场 gate、分数。它不能回答叙事问题：24h 主叙事、多空论据、语义漂移、谁在放大哪类 claim、注意力是可交易还是 toxic、价格是被讨论推动还是讨论在追价格、什么条件会让这个 setup 失效。Token Case 有原料但没有组织，Mention Timeline 没有 stance/sentiment，Signal Pulse 有更深决策链路但 public 输出受 gate 控制且属于下游决策产品。把 Pulse 直接塞回 Radar 会让扫描产品依赖下游决策产品，破坏架构边界。

## 第一性原则

**meme alpha 是反身性注意力，不是简单情绪。** meme 币可以因为嘲讽、愤怒、恐慌、玩梗、救援叙事、价格 chase 而涨。`positive sentiment` 不等于 bullish trade stance，负面注意力也可能形成交易性扩散。因此模型必须拆开：

| 维度 | 说明 |
|------|------|
| `attention_valence` | 讨论的注意力色彩：positive、negative、mixed、ironic、hostile、panic、celebratory、informational |
| `trade_stance` | 帖子对交易方向的表达：bullish、bearish、neutral、skeptical、exit-risk、research-only |
| `propagation_state` | 扩散阶段：seed、ignition、expansion、concentration、exhaustion、drift |

**叙事 claim 必须证据绑定。** LLM 可以压缩、命名和总结叙事，但任何展示给用户的 claim 都必须能指回 event ids、作者、market anchors 或 data-gap refs。这延续 Pulse 的 sealed evidence packet 原则（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:8-12`）和 facts-first 原则（`docs/ARCHITECTURE.md:31-37`）。

**发现、解释、决策必须分层。** Token Radar 从 facts/factor snapshots 做 scan ranking；Narrative Intelligence 解释某 token/window 的讨论含义；Signal Pulse 判断是否形成公开候选和 playbook。API 可以把三者组合给 UI，但写模型必须分离，遵守 one-writer rule（`docs/ARCHITECTURE.md:55-66`）。

**硬切就不保留旧解释路径。** 新方案上线后，Token Radar 和 Token Case 不应在 narrative 缺失时静默退回 deterministic agent brief 或泛化的 semantic catalyst 文案。缺失就是显式状态：`pending`、`insufficient`、`semantic_unavailable`。这符合项目 no runtime compatibility layer 的硬切约束（`docs/ARCHITECTURE.md:72-75`）。

## Goals

- **G1 Radar 行级叙事可用。** `/api/token-radar` 返回的每一行都包含 `discussion_digest`，状态为 `ready | pending | insufficient | semantic_unavailable`。ready 时必须有 dominant narrative、stance mix、attention valence mix、propagation read、semantic coverage、evidence refs；非 ready 时必须展示具体 data gap，而不是泛化 catalyst 文案。

- **G2 Token Case 成为交易员 dossier。** `/token/:targetType/:targetId` 的主解释从 deterministic `agent_brief` 切到 `token_discussion_digest`。页面必须回答：现在讨论什么、多头怎么说、空头怎么说、故事如何扩散、反身性 loop 在哪、哪些帖子支撑这些判断。

- **G3 Mention Timeline 每条帖子带语义。** `/api/target-posts` 每个 item 都有 `semantic` block。它可以是 ready、pending 或 unavailable，但 UI 不再从 `post_quality`、`is_watched`、`stage_phase`、`author_role` 推断 sentiment/stance。

- **G4 Pulse 只做公开 overlay，不做 Radar 上游。** Token Radar 可以展示同 target/window/scope 下公开 displayable 且有 `evidence_packet_hash` 的 Signal Pulse overlay。Radar 排名、WHY NOW、discussion digest 生成都不依赖 Pulse 是否发布。

- **G5 可审计。** narrative summary、bull/bear 论点、risk、catalyst、invalidation、propagation label 只要展示为 claim，就必须带 evidence refs 或 data-gap refs。不能引用证据的总结不能作为 claim 展示。

- **G6 覆盖率透明。** UI 必须展示 semantic coverage，让用户区分"系统读完讨论后认为观点混合"和"系统还没有足够语义标签"。

## Non-goals

- 不创建买卖订单、仓位建议、止损规则或执行建议。
- 不把 Token Radar 变成 Signal Pulse，也不让 Pulse 给 Radar 排名。
- 不扩数据源范围；本 spec 只使用当前 GMGN public stream、persisted events、enrichment facts、identity facts、profile facts、market ticks 和现有 read models。
- 不让 token identity resolution 变成概率模型或 LLM hot path。
- 不新增人工标注、训练集或模型训练工作流。
- 不承诺每个低信息 token 都会有 LLM 叙事总结；低信息状态必须被诚实展示。
- 不保留 canonical Token Case 的旧解释 runtime path。

## Target Architecture

目标架构新增一条一等公民的 **Narrative Intelligence** read path，位于 Token Radar discovery 和 Signal Pulse decisioning 之间。

推荐新增独立 domain：`domains/narrative_intel`。不建议把它塞进 `token_intel` 或 `pulse_lab`。

理由：

- `token_intel` 现在拥有 token identity、Radar feature aggregation、factor snapshot 和 scan ranking。叙事标签/聚类/总结的 compute budget、freshness、失败模式和产品合同都不同，放进去会污染 ranking contract。
- `pulse_lab` 拥有 candidate admission、sealed evidence packet、agent runtime、audit ledger、public display gate。它可以消费 narrative digest 作为 evidence，但不应成为通用 token 叙事面的唯一生产者。
- `narrative_intel` 的职责边界足够清楚：读 facts/read models，写自己的 rebuildable narrative read models，通过 interfaces 暴露给 API composition 和 Pulse evidence builder。

硬切后的层级职责：

| Layer | Owns | Does not own |
|-------|------|--------------|
| `token_intel` | Token Radar ranking、factor snapshot、deterministic token target views、target post retrieval | Narrative digest generation、Pulse decisions、LLM prose |
| `narrative_intel` | Mention semantics、narrative clusters、token discussion digests、semantic coverage、evidence refs | Token identity、market tick persistence、Radar rank score、Pulse public display status |
| `pulse_lab` | Candidate admission、sealed evidence packet、LLM decision runtime、audit ledger、public Pulse read model | Token Radar ranking、general discussion digest ownership、timeline labeling |
| API surfaces | Radar row + digest + public Pulse overlay 的组合 | Raw SQL joins、provider calls、scoring、token resolution |
| Frontend | 根据 public contract 渲染 scan/dossier 状态 | 本地重算 ranking、推断语义、调用 provider |

## Conceptual Data Flow

```text
GMGN public stream
  -> ingestion/evidence facts
  -> token_intel TokenRadarProjectionWorker
  -> token_radar_rows.factor_snapshot_json
  -> Token Radar scan rows

GMGN public stream
  -> ingestion/evidence facts + target resolutions + enriched_events + market_ticks
  -> narrative_intel MentionSemanticsWorker
  -> token_mention_semantics
  -> narrative_intel TokenDiscussionDigestWorker
  -> token_discussion_digests
  -> Token Radar narrative column + Token Case dossier + semantic Mention Timeline

token_radar_rows + token_discussion_digests + market/identity facts
  -> pulse_lab PulseEvidenceBuilder
  -> pulse_evidence_packets
  -> Pulse decision runtime
  -> public Signal Pulse read model
  -> optional Token Radar / Token Case Pulse overlay
```

关键箭头：

- `token_intel -> narrative_intel` 只是 read dependency。Narrative workers 可以用 Radar rows 做 admission/prioritization，但不能写或修改 Radar rows。
- `narrative_intel -> pulse_lab` 只是 evidence input。Pulse 可以在 sealed packet 里引用 digest 和底层 semantic refs，但 Pulse 不拥有 digest。
- `pulse_lab -> Token Radar UI` 只是 public read composition。公开 Pulse overlay 可以显示在 Radar/Case 旁边，但不能改变 Radar rank、WHY NOW 或 digest 内容。
- `NOTIFY` 仍然只是 wake hint。Narrative workers 必须有 bounded interval catch-up，保持和现有 read-model worker 一样的可靠性语义（`docs/ARCHITECTURE.md:67-71`）。

## Worker Triggers And State Machine

这条链路需要新增 worker，但不应该做成"每来一条 tweet 就触发一次大模型"。正确模型是 admission-first：Radar 负责发现哪些 token/window 值得解释，Narrative workers 只对 admitted token/window 做增量语义和 digest。

### Worker Split

| Worker | Writes | Unit | 作用 |
|--------|--------|------|------|
| `MentionSemanticsWorker` | `token_mention_semantics` | `event_id + target_type + target_id + schema_version + text_fingerprint` | 给单条 token mention 打语义标签。它只处理未标注或 schema/model 过期的 event-target pair。 |
| `TokenDiscussionDigestWorker` | `token_discussion_digests` | `target_type + target_id + window + scope + schema_version` | 聚合某 token/window/scope 的讨论，生成主叙事、多空、传播、反身性、触发和失效条件。 |

也可以在实现上用一个 runtime worker 承载两个 stage，但产品和架构语义上必须拆成两个 read-model writer。否则 per-mention 语义、token-window digest、LLM 调用预算、重试语义会混在一起。

### Trigger Sources

| Trigger | MentionSemanticsWorker | TokenDiscussionDigestWorker | 设计理由 |
|---------|------------------------|-----------------------------|----------|
| `token_radar_updated` wake | Yes, 进入 admission 后处理未标注 mentions | Yes, 当 Radar rank/phase/source event set 变化时排 digest refresh | Radar 是发现层，Narrative 是解释层；wake 只提示重读 DB。 |
| 新 token mention 进入已 admitted target/window | Yes | Maybe, 满足 refresh threshold 后触发 | 单条新帖先标注，digest 不必每帖重算。 |
| token resolution 从 NIL/AMBIGUOUS 变成可归属 target | Yes | Yes, 若归属后进入 admitted set | 以前不能解释的事件现在可归属，需要补语义和 digest。 |
| `social_event_extractions` 新增或更新 | Yes, 可复用已有 hints 或重算低覆盖 labels | Maybe | 现有 enrichment 是输入，不是完整 digest。 |
| market context 出现显著变化 | No, 单帖语义不因价格变化改变 | Yes, 只刷新 `reflexivity_read` / late risk | price chase、exhaustion risk 属于 token-window digest，不属于单帖 stance。 |
| periodic catch-up | Yes | Yes | 防止 missed wake；符合 wake-is-not-truth。 |
| Pulse candidate / Pulse decision 变化 | No | No | Pulse 只能消费 digest 或被 API 组合为 overlay，不能触发 Radar 叙事链路。 |

明确不触发的场景：

- 任意 raw tweet 进入系统但没有被 token resolution 归到 admitted target/window。
- 单纯 market tick 更新触发 per-mention 语义重标。
- Pulse hidden candidate、dead job、hold publish 状态反向触发 Radar/Digest。
- API request path 临时发现缺 digest 后 inline 跑 LLM。

### Admission State

`narrative_intel` 需要一个轻量 admission 概念，用来限制分析范围。它不一定必须暴露为 public API，但 worker 必须按这个状态思考。

Admission key:

- `target_type`
- `target_id`
- `window`
- `scope`
- `schema_version`

Admission 来源：

- Radar top set：当前窗口/范围内 rank 靠前的 rows。
- High-alert set：达到 Radar 高关注门槛或传播加速的 rows。
- Dossier demand set：用户打开 Token Case 后，当前 target/window/scope 可以短期提升优先级，但仍然异步，不在 request path 跑 LLM。
- Carry set：上一个周期已 ready 且仍在窗口内的 targets，用低频 refresh 防止 UI 快速退化。

Admission 不是业务真相，只是 worker 调度状态。真正可展示的产品状态来自 `token_mention_semantics` 和 `token_discussion_digests`。

### Per-Mention Label State

单条 event-target pair 的状态机应尽量小：

```text
unlabeled
  -> queued
  -> labeled
  -> stale
  -> queued

queued
  -> retryable_error
  -> queued

queued
  -> semantic_unavailable
```

State semantics:

| State | 含义 | 退出条件 |
|-------|------|----------|
| `unlabeled` | 事件已归属 target，但当前 schema/model/text_fingerprint 下没有语义标签 | 进入 admitted target/window |
| `queued` | 等待批处理或模型调用 | 成功、失败或判定不可标 |
| `labeled` | 有可用 stance/valence/claim/cluster/confidence | schema/model/text_fingerprint 变化或进入 stale |
| `stale` | 标签存在但 schema/model 过期 | 重新排队 |
| `retryable_error` | provider 或临时运行错误 | backoff 后重试 |
| `semantic_unavailable` | 文本缺失、语言不可处理、证据不足或安全原因无法标注 | schema/输入变化后才重试 |

复杂度约束：

- `MentionSemanticsWorker` 只做 per-mention semantic，不生成 token-level bull/bear。
- 同一 `event_id + target_id + text_fingerprint + schema_version` 不重复烧模型。
- 低 confidence 不是失败；它是可聚合但会降低 digest confidence 的证据。

### Token-Window Digest State

token-window digest 的状态机承载用户可见状态：

```text
unseen
  -> admitted
  -> labeling
  -> digest_pending
  -> ready

admitted -> insufficient
labeling -> insufficient
digest_pending -> retryable_error -> digest_pending
ready -> refresh_due -> labeling
ready -> stale -> refresh_due
ready -> suppressed
insufficient -> refresh_due
```

State semantics:

| State | 含义 | 用户可见状态 |
|-------|------|--------------|
| `unseen` | 目标未进入 narrative admission | 通常不出现在 Radar payload；Token Case 可显示 `semantic_unavailable` |
| `admitted` | 目标值得分析，正在读取 source set | `pending` |
| `labeling` | mention labels 覆盖率未达 digest 门槛 | `pending` |
| `digest_pending` | label 足够，等待生成/更新 digest | `pending` |
| `ready` | digest 可展示且 evidence refs 验证通过 | `ready` |
| `insufficient` | source volume、independent authors、coverage、identity 或 market context 不足 | `insufficient` |
| `refresh_due` | 有足够变化需要刷新 | 继续展示旧 digest，但标记 computed time/coverage；不能伪装成最新 |
| `stale` | 超出 TTL 或 schema/model 过期 | `pending` 或 stale-ready，取决于 UI contract |
| `retryable_error` | 临时错误，可 backoff | `pending` + health gap |
| `suppressed` | 不再在 admission set，停止主动刷新但保留历史 read model | Radar 不展示；Token Case 可展示 last known + stale/gap |

Digest refresh 不应由每条新 label 触发。满足任一条件才 refresh：

- 新 labeled mentions 达到配置阈值。
- 新独立作者达到配置阈值。
- 新 watched/high-quality 作者出现。
- dominant cluster 变化。
- stance mix 或 attention valence mix 发生显著变化。
- market move 相对 social anchor 出现显著变化，影响 price-chase / exhaustion-risk 判断。
- 上次 digest 超过窗口对应 TTL。
- schema/model 版本变化。

### Estimated Frequency

以下是初始估算，不是 SLA；最终阈值应进入 worker config，而不是写死在 UI 或 API。

| 对象 | 热门 admitted set | 普通 admitted set | 低信息 / suppressed |
|------|-------------------|-------------------|---------------------|
| Mention semantics batch | 每 1-2 分钟处理新增未标注 mentions | 每 5-10 分钟 | 30-60 分钟或不主动跑 |
| `5m` digest | 每 1-2 分钟，且必须有足够新增标签 | 每 5 分钟 | 不主动跑 |
| `1h` digest | 每 2-5 分钟 | 每 10-15 分钟 | 30-60 分钟 |
| `4h` digest | 每 5-10 分钟 | 每 15-30 分钟 | 30-60 分钟 |
| `24h` digest | 每 10-15 分钟 | 每 30-60 分钟 | 60 分钟或仅按需 |

推荐初始 refresh threshold：

- 新 labeled mentions >= 3。
- 新独立作者 >= 2。
- 新 watched/high-quality 作者 >= 1。
- dominant narrative cluster 改变。
- stance mix 或 attention valence mix 改变超过约 20%。
- price change since social anchor 超过约 10-15%。
- digest TTL 到期。

这些数字的作用是控制模型预算和 UI 新鲜度的初始平衡，不是交易信号本身。它们应通过 worker health、coverage 和实际运行成本调整。

## Core Models

### TokenMentionSemantics

per-event、per-target 的原子语义标签，是 timeline sentiment 和 digest evidence 的底层单位。

Fields:

- `event_id`
- `target_type`
- `target_id`
- `window_context`
- `text_fingerprint`
- `language`
- `trade_stance`: bullish、bearish、neutral、skeptical、exit-risk、research-only、unknown
- `attention_valence`: positive、negative、mixed、ironic、hostile、panic、celebratory、informational、unknown
- `narrative_cluster_key`
- `claim_type`: catalyst、risk、joke、price-action、project-update、listing、liquidity、holder、macro、scam-warning、off-token、other
- `evidence_type`: firsthand-claim、quoted-claim、scanner-alert、influencer-take、reply-banter、market-recap、project-account、unknown
- `co_mentioned_targets`
- `semantic_confidence`
- `evidence_refs`
- `model_run_id`
- `schema_version`
- `computed_at_ms`

Invariants:

- 一条 label row 只描述一个 event-target pair。同一条 tweet 同时提到 SOL 和 SOS 时，可以产生两个 target semantics。
- `attention_valence` 和 `trade_stance` 独立。负面注意力可能仍有交易性，bullish price chatter 也可能是低质量复读。
- 低 confidence label 可以存储，但 ready digest 的 claim 必须考虑 confidence 和 coverage。

### NarrativeCluster

target/window 范围内的语义相似讨论簇。

Fields:

- `cluster_key`
- `target_type`
- `target_id`
- `window`
- `scope`
- `label_zh`
- `summary_zh`
- `stance_mix`
- `attention_valence_mix`
- `claim_type_mix`
- `top_authors`
- `representative_event_ids`
- `first_seen_ms`
- `last_seen_ms`
- `velocity`
- `co_targets`
- `confidence`

Invariants:

- cluster label 是产品解释，不是 token identity fact。
- cluster membership 必须能从 `TokenMentionSemantics` 和 source events 重建。
- 一个 token 可以同时存在多个 cluster；digest 负责判断 dominance 和 conflict。

### TokenDiscussionDigest

target/window/scope 的产品解释 read model。

Fields:

- `target_type`
- `target_id`
- `window`
- `scope`
- `status`: ready、pending、insufficient、semantic_unavailable
- `headline_zh`
- `dominant_narratives`
- `bull_view`
- `bear_view`
- `stance_mix`
- `attention_valence_mix`
- `propagation_read`
- `reflexivity_read`
- `watch_triggers`
- `invalidation_conditions`
- `data_gaps`
- `semantic_coverage`
- `source_event_count`
- `labeled_event_count`
- `evidence_refs`
- `model_run_id`
- `schema_version`
- `computed_at_ms`

Invariants:

- digest 是 read model，不是 material fact。
- ready digest 的 narrative、bull、bear、propagation、reflexivity、invalidation claims 必须引用 evidence refs。
- insufficient digest 必须说明缺口来自 volume、identity、market、semantic coverage、worker freshness 还是 confidence。
- digest 可以总结 public 和 watched discussion，但必须保留 scope，不能让 `all` 和 `matched` 隐式混合。

### ReflexivityRead

`TokenDiscussionDigest` 内的结构化字段，把 meme 传播翻译成交易员可读的反身性 loop。

Fields:

- `loop_state`: pre-narrative、narrative-forming、attention-chase、price-chase、exhaustion-risk、narrative-drift、unknown
- `attention_leads_price`: true、false、unknown
- `price_leads_attention`: true、false、unknown
- `primary_reflexive_driver`: joke、identity、influencer、listing、price-action、panic、social-raid、project-update、macro-spillover、unknown
- `crowd_memory`
- `late_risk`
- `evidence_refs`

设计理由：

meme 交易不是判断文本是否"看多"，而是判断注意力是否在吸引更多注意力，以及这个循环是否已经变成价格 chase 或 exit liquidity。这个结构把反身性显式化，但不把它做成黑箱分数。

### PulseOverlay

Radar 和 Token Case 的公开组合对象。

Fields:

- `status`: absent、public_candidate、public_watch、public_risk_rejected
- `candidate_id`
- `recommendation`
- `display_status`
- `evidence_packet_hash`
- `summary_zh`
- `risk_labels`
- `computed_at_ms`

Invariants:

- 只有 public displayable 且带 packet hash 的 Pulse row 才能形成 overlay。
- overlay 永远不是 Radar rank 或 narrative digest status 的来源。
- hidden Pulse states 留在 operator/audit surface，不在 Radar 里伪装成半公开信号。

## Interface Contracts

### `/api/token-radar`

每个 item 包含：

- 现有 rank、token、social、market、score、profile、factor breakdown。
- `discussion_digest`: compact digest，包含 status、headline、dominant narrative label、stance mix、attention valence mix、semantic coverage、data gaps、evidence refs。
- `pulse_overlay`: absent 或 public displayable overlay。

行为：

- `discussion_digest.status = ready` 时，UI 可以渲染 narrative 和 stance。
- `pending` 时，UI 展示 semantic analysis 正在追赶，不展示旧 generic catalyst prose。
- `insufficient` 时，UI 展示具体 data gap。
- `semantic_unavailable` 时，UI 展示分析链路健康缺口。
- endpoint 不调用 provider，不 inline 跑 LLM，不在 request path 做 semantic compute。

### `/api/token-case`

token dossier 包含：

- 现有 target identity、profile、market、propagation、score、first page posts。
- `discussion_digest` 作为主解释对象。
- `narrative_clusters`，按当前 target/window/scope。
- `pulse_overlay`，仅公开时存在。
- canonical token dossier 不再把 deterministic `agent_brief` 当产品解释 runtime path。

行为：

- 页面顶部回答"现在这个币的讨论核心是什么"。
- Bull 和 Bear section 引用 event refs。
- Data gaps 是一等状态，不藏在泛化 prose 后面。
- 非 token 的 search topic brief 可以作为独立搜索语义保留，但 canonical Token Case explanation 由 digest 驱动。

### `/api/target-posts`

每个 item 包含：

- 现有 post payload fields。
- `semantic`: status、trade stance、attention valence、narrative cluster key、claim type、evidence type、confidence、gap reason。

行为：

- Mention Timeline 可以按 stance、valence、cluster、claim type 过滤或打标签。
- 缺失 semantic label 时必须明确原因：worker pending、source insufficient、semantic unavailable 等。
- UI 不从 `post_quality`、`is_watched`、`stage_phase`、`author_role` 推断 stance。

### `/api/signal-lab/pulse`

Public contract 继续 display-gated。内部 Pulse evidence packet 可以包含 discussion digest refs 和底层 semantic event refs。Public Pulse lists 仍只暴露带 evidence packet hash 的 displayable rows，符合现有 public display contract（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:93-103`）。

### WebSocket

不新增 WebSocket 业务真相。Live messages 可以触发可见页面 refresh，但 token narrative correctness 来自持久化 read models 和 HTTP reads。这与现有 "wake is not truth" 约束一致（`docs/ARCHITECTURE.md:67-71`）。

## Acceptance Criteria

- **AC1.** WHEN Token Radar 返回任意 target/window/scope 的 row，THEN row SHALL 包含 `discussion_digest.status`，且 semantic coverage 为 0 时不渲染旧的 generic `semantic catalyst snapshot` 文案。

- **AC2.** WHEN `discussion_digest.status = ready`，THEN row SHALL 暴露 dominant narrative、stance mix、attention valence mix、semantic coverage、evidence refs。

- **AC3.** WHEN narrative analysis 不可用，THEN Token Radar 和 Token Case SHALL 渲染显式 data-gap state，而不是 deterministic bull/bear template。

- **AC4.** WHEN Token Case 加载 canonical token target，THEN 主解释 SHALL 来自 `TokenDiscussionDigest`，不是 `search_agent_brief_v1`。

- **AC5.** WHEN Mention Timeline 加载 posts，THEN 每条 post SHALL 包含 semantic block，状态为 ready 或带 unavailable/pending reason。

- **AC6.** WHEN Signal Pulse 对某 Radar target 没有 public displayable row，THEN Token Radar SHALL 不展示 Pulse overlay，但仍展示自己的 discussion digest。

- **AC7.** WHEN Signal Pulse 对同 target/window/scope 有 public displayable row 且带 evidence packet hash，THEN Token Radar 和 Token Case MAY 展示 Pulse overlay，但不得改变 Radar rank 或 digest 内容。

- **AC8.** WHEN narrative claim、bull argument、bear argument、invalidation condition 被展示，THEN payload SHALL 包含 evidence refs 或 data-gap refs。

- **AC9.** WHEN source discussion 独立作者不足或 semantic coverage 低，THEN digest SHALL 展示 `insufficient` 或低覆盖率，不得过度总结。

- **AC10.** WHEN narrative worker 错过 wake notification，THEN bounded interval catch-up SHALL 最终重建受影响 narrative read model。

- **AC11.** WHEN raw tweets 持续流入但 target/window 未进入 narrative admission，THEN system SHALL 不触发 per-mention LLM labeling，也不生成 digest。

- **AC12.** WHEN 单个 admitted target/window 只有一条新增 labeled mention，THEN system SHALL 允许更新 mention semantics，但 SHALL NOT 必须刷新 token-level digest；digest refresh 由阈值、TTL、cluster/stance/market 变化驱动。

- **AC13.** WHEN Pulse hidden candidate、hold publish、dead job 或 internal count 变化，THEN system SHALL NOT 用这些状态触发 Narrative workers；Pulse 只消费 digest 或作为公开 overlay 被 API 组合。

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM 成本随 public mentions 膨胀 | High | 用 Radar admission 和 event-window prioritization 控制 digest 生成；per-mention labels 证据绑定；低价值 row 允许 insufficient；request path 不跑 LLM。 |
| 叙事总结 hallucination | High | 所有展示 claim 必须带 evidence refs；发布 ready digest 前验证 refs 存在于 source set。 |
| 把 sentiment 误当 tradability | High | `attention_valence` 与 `trade_stance` 分开建模和展示，不合成单个 sentiment pill。 |
| Pulse 耦合泄漏进 Radar | High | API 可以组合 public Pulse rows；Pulse 不写 Radar/Digest；Radar rank 仍归 `token_intel`。 |
| 热门 row 的 semantic labels 滞后 | Medium | 显示 `pending`、worker freshness、computed time、coverage；stale digest 作为 stale 展示，不转成泛化文案。 |
| 低量 token 被过度解释 | Medium | digest 可以是 `insufficient`；summary 需要最低 evidence 和 confidence。 |
| Off-token narrative hijack | Medium | 存 `co_mentioned_targets`、claim type、off-token labels。SOL 讨论里出现 SOS、HYPE/PURR 等漂移时，表达为 narrative drift，而不是纯 SOL sentiment。 |
| Radar UI 信息过密 | Medium | Radar 只显示 compact headline、stance mix、coverage、dominant label；Token Case 承接完整 dossier。 |
| 新 domain 带来复杂度 | Medium | 新 domain 的理由是 semantic labeling 与 ranking/decisioning 生命周期不同；职责收窄为 narrative read models。 |
| 状态机膨胀 | Medium | 拆成 per-mention label state 和 token-window digest state 两个小状态机；admission 只做调度，不变成产品真相。 |
| 用户混淆 hidden Pulse candidates 与 Radar signals | Low | 只有 displayable 且有 packet hash 的 Pulse 才能 overlay；内部 counts 留在 Pulse health/operator surfaces。 |

## Evolution Path

这个设计应该让后续三类扩展自然发生，而不需要再次推翻：

- Market-wide Narrative Board：按当前 meme archetype 分组 token，例如 mascot raid、listing rumor、celebrity joke、ecosystem rotation、rescue narrative、scam warning。
- Narrative state backtesting：用 immutable computed digests 和 score versions 评估 forward returns，而不是从 UI 文案反推标签。
- 更高质量的 Pulse evidence packets：Pulse 引用 digest clusters 和 per-post semantic refs，不需要 decision agent 重新从 raw discussion 里抽故事。

需要注意不要封死未来外部数据源，但本 spec 刻意只站在当前 facts-first ingestion 和 market model 上。未来如果引入其他社交源，必须先作为 facts 或 source-cache rows 进入系统，不能让 narrative worker 直接在 LLM/browser 里抓取外部事实。

## Alternatives Considered

**A. 只扩展 Signal Pulse，把 Pulse 结果展示到 Token Radar。** Rejected。Pulse 是 decision-oriented、display-gated 的下游产品；它可以在 Radar 有大量扫描价值时正确返回 0 个 public items。让 Pulse 成为 Radar 主叙事来源，会让扫描产品依赖下游交易决策产品，也会把 hidden audit candidates 和公开信号混在一起。

**B. 保留 deterministic `agent_brief`，加几条 sentiment 字符串。** Rejected。当前 brief 明确是 deterministic template（`src/parallax/domains/token_intel/read_models/search_agent_brief.py:37-83`）。加 sentiment 仍然不能表达 narrative clusters、evidence refs、attention valence、trade stance、reflexivity。

**C. 把 narrative 字段直接塞进 `token_radar_rows.factor_snapshot_json`。** Rejected。factor snapshot 是 Token Radar score contract（`src/parallax/domains/token_intel/ARCHITECTURE.md:48-85`）。Narrative digest 的 freshness、compute cost、失败模式和 UI contract 都不同，混进去会膨胀 ranking contract，并诱导把 prose quality 当作 score truth。

**D. 前端直接从 post text 推 sentiment。** Rejected。前端架构要求 ranking score 和 breakdown 来自 API，UI 不本地重算 ranking facts（`docs/FRONTEND.md:58`）。客户端 sentiment 也不可审计、不可 replay、不可证据绑定。

**E. 只复用现有 `social_event_extractions` semantic hints。** Rejected。现有 hints 是有价值的 ingredient，但它们当前聚合进 score-family facts，而不是 per-post timeline labels 或 token-window narrative dossiers（`src/parallax/domains/token_intel/services/token_radar_projection.py:474-499`, `src/parallax/domains/token_intel/scoring/factor_snapshot.py:231-263`）。它不满足 Radar/Token Case 的完整产品合同。

**F. 给 Token Radar 加一个通用 sentiment score 列。** Rejected。meme 交易奖励的是注意力、冲突、玩梗和递归传播，不是干净的正面情绪。单一 sentiment score 会隐藏 bullish thesis、hostile attention、panic attention、ironic spread、exit-liquidity chatter 的差异。

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Narrative Intelligence 读 persisted facts/read models，只写自己的 rebuildable read models。 |
| Always | Narrative workers 先经过 admission，再批量处理 mention labels 和 digest refresh。 |
| Always | Token Radar 可以在 API response 里组合 digest 和 public Pulse overlay，但 ranking 仍归 Token Radar。 |
| Always | Canonical Token Case 的主解释由 digest 驱动。 |
| Always | Mention Timeline 的 semantic state 必须显式，即使 unavailable。 |
| Always | 展示 claim 必须有 evidence refs 或 data-gap refs。 |
| Ask first | 扩展到 GMGN public stream 以外的新外部社交/市场源。 |
| Ask first | 把 narrative state 变成影响 Radar 排名的新 alpha score。 |
| Ask first | 加人工标注、训练数据或概率模型评估。 |
| Never | Pulse 写 `token_radar_rows` 或 `token_discussion_digests`。 |
| Never | Radar projection 读 Pulse rows 来决定 rank 或 WHY NOW。 |
| Never | API request handlers 调 LLM、provider 或临时做 semantic joins。 |
| Never | UI 从 post quality、watched status、author role 推断 stance。 |
| Never | Missing narrative data 退回旧 deterministic token-dossier prose。 |
