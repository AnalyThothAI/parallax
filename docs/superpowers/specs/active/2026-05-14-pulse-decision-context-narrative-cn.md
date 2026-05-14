# Pulse Decision Context & Narrative Output — Phase 0b.5 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-14
**Owner**: Claude with Qinghuan
**Scope**: 在已落地的 Unified Agent Runtime（target-agent-architecture-design phase 0b）之上，把 Pulse Decision Pipeline 的 Analyst stage 输出契约从 "summary_zh + evidence: list[str]" 升级为 "narrative_type + narrative_thesis + bull_view + bear_view + key_evidence_event_ids" 五个一等字段；并把 DecisionContextBuilder 喂给 Analyst 的输入从 "仅 factor_snapshot" 扩到 "factor_snapshot + history_brief + new_tweets + factor_delta" 三元组。Critic prompt 单向扩到审查 narrative coherence；Judge / FinalDecision schema / Token Radar 列表读路径 / search_agent_brief deterministic 模板均不在本 spec 范围内。

**Related**:
- `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`
- `docs/superpowers/plans/active/2026-05-14-unified-agent-runtime-phase-0b-plan-cn.md`
- `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md`
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`
- `docs/ARCHITECTURE.md` Pulse Agent Runtime 段
- `docs/CONTRACTS.md` Signal Pulse decision block
- `docs/DESIGN_DISCIPLINE.md`
- `docs/RELIABILITY.md` Pulse Agent Audit Ledger 段

---

## 一句话结论

Pulse Decision Pipeline 当前缺的不是 stage 数量、不是新框架、不是新表，而是**让 Analyst 同时看到更多事实（历史时序 + 新增 tweets + 因子 delta）并显式产出更多结构（叙事 + 多空二元视角）**。这是 phase 0b 三阶段架构内部的契约演进，不动 Critic / Judge / FinalDecision / Token Radar / search_agent_brief 任何已稳定的边界。

---

## 1. 当前代码事实

### 1.1 已稳定的好边界

- `pulse_lab` 拥有 Pulse Decision 全部领域逻辑：route policy、completeness gate、worker、repository、read model（per ARCHITECTURE.md Pulse Agent Runtime 段）。
- `integrations/openai_agents` 只负责 OpenAI Agents SDK adapter 与 stage prompt，不持有领域决策或 SQL（per ARCHITECTURE.md 同段，per target-agent-design §5.2）。
- `pulse_agent_run_steps` 已经是完整 replay ledger，每个 Analyst / Critic / Judge stage 输入、prompt、输出、latency 都落库（per RELIABILITY.md Pulse Agent Audit Ledger）。
- `pulse_candidates.decision_*` 列 + `decision_json` 是公共决策契约的唯一持久化源（per CONTRACTS.md Signal Pulse decision block）。
- `AnalystOpinion / CritiqueReport / FinalDecision` 三个 Pydantic schema 已在 unified-agent-runtime-phase-0b plan task 2 落地，Analyst 已经输出 `summary_zh` 与 `evidence: list[str]`。
- `pulse-detail-redesign-cn.md` 设计的 `PulseDetailView` 通过 `stages.analyst.response` / `stages.critic.response` / `stages.judge.response` 三段消费 stage outputs，前端已经预留所有 stage 字段的渲染入口。
- `domains/token_intel/read_models/search_agent_brief.py` deterministic 拼装 Search Inspect 的 `agent_brief.bull_bear`，是 LLM 不可用时的 pre-LLM brief，与本 spec 解耦。
- `build_token_agent_brief` 已经是 deterministic per-token 24h 摘要 builder，输出三段：`project_summary` + `propagation`（含阶段切分）+ `bull_bear`（deterministic 模板拼装）。可在 enqueue 路径直接复用其前两段；deterministic bull_bear 段不喂给 Analyst（详见 §5.3），避免 anchor LLM 到固定模板。
- `TokenTargetRepository.timeline_rows(target_key, since_ms, ordered_by_attribution_weight)` 已经支持按时间窗口拉某 token 的 tweets，并按归因权重排序。

### 1.2 仍然不成熟的点

- Analyst 当前 `summary_zh` 一句话糅合三件事：当前在炒什么 narrative、为什么 bullish / bearish、给出什么 recommendation。下游消费者无法分离。
- Analyst 当前 `evidence: list[str]` 是无类型字符串列表，既不区分多空方向、也不绑定具体 event_id，无法做证据真实性校验、无法回放时定位原文。
- DecisionContextBuilder 当前给 Analyst 的输入是 `factor_snapshot` 单段。Analyst 看不到上一窗口对比、看不到本窗口新增 tweets 原文、看不到因子层面的 delta，因此无法判断 narrative 是 "新出现" 还是 "持续中"、无法 cite 具体 tweet。
- Critic 当前 prompt 只评估 Analyst 的 `summary_zh + evidence + confidence`。如果 Analyst 加 narrative 与 bull/bear 字段，Critic 没有指令去 audit 它们的真实性。

### 1.3 根因判断

"agent 输出不够准确" 在已落地的 Analyst / Critic / Judge 架构里并不需要新加 stage 或新框架。三阶段架构是正确的，**问题是 Analyst 的 input 缺少时序对比事实、output schema 没有把已经隐式存在的语义（叙事、多空）显式化**。把这两件事补齐，agent 输出质量在不增加 stage 数量的前提下提升一个量级。

---

## 2. 第一性原理

### 2.1 叙事是 first-class observation，不是 summary 副产物

市场叙事（在炒什么）是 Analyst 看到的最重要 observation 之一。把它压缩进 `summary_zh` 一句话意味着：(a) 无法 audit narrative 是否 overclaim；(b) 无法跨 token 聚合 narrative cohort（"过去 24h memetic narrative 的 token 数 vs utility narrative"）；(c) phase 1 outcome calibration 时无法以 narrative 维度切样本。叙事必须以可命名（type 枚举）+ 可描述（自由 thesis 文本）的形式输出，作为 Analyst 的 first-class field。

### 2.2 多空是 Analyst 同时持有的二元视角，不是 Critic 单向降权

target-agent-design §2.4 明确：Critic 是 governor，不是 theater。多空对立属于"观察"，不属于"约束"。把多空塞给 Critic 会让 Critic 同时承担观察与约束两个角色，违反单一职责，并且让"看空论据"被等同于"应该 abstain"——这是两件不同的事。正确的位置是 Analyst：Analyst 同时持有 bull 与 bear 两面视角并各自给出 evidence；Critic 只对这两面视角做事实性审查与降权。

### 2.3 Agent 只能解释事实，不能补造事实

target-agent-design §2.1。这条原则对 bull/bear 的直接含义是：**asymmetric 必须允许**。如果某个 token 实际上没有有效的 bear 论据（基本面与社交面都正向），硬要 Analyst 编一个 bear view 就是 hallucination。每个 view 必须可标记为 `absent / weak / moderate / strong`；strength=absent 时 thesis_zh 与 supporting_event_ids 必须为空。

### 2.4 历史时序是事实，不是 memory

target-agent-design §2.5 把 reflection / memory 留给 phase 1。本 spec 不引入 memory。但"上一窗口 vs 本窗口的对比" 与 "本窗口新增 tweets" 是 deterministic 可重建的**事实**，不是 agent 的过去判断回看，因此应该作为 DecisionContext 的事实输入，不属于 memory 范畴。本 spec 让 agent 看到事实层面的时序差，而不是看到自己上一次的判断。

### 2.5 Reuse before create

DESIGN_DISCIPLINE §27。本 spec 不新建 history summary 表、不新建 rolling cache worker、不新建 outbox。三元组中的 history_brief 复用现有 deterministic builder；new_tweets 复用现有 timeline 查询；factor_delta 直接从 factor_snapshot 已经计算好的 social_heat facts 中提取。

### 2.6 Replay 优先于 prompt tuning

target-agent-design §2.5。新增字段必须落入 `pulse_agent_run_steps.input_json` 和 `response_json` 完整保存，保证 7 天内的任何 run 都能从 DB 重建 agent 当时看到的事实与输出的判断。

---

## 3. 目标（带 falsifiable metrics）

| ID | 目标 | 验收 metric |
|---|---|---|
| G1 | Analyst 显式产出 narrative_type + narrative_thesis | 每条 status=ok 的 token_target analyst step 的 response_json 含非空 `narrative_type` ∈ 受控 enum 且 `narrative_thesis` 长度 ≥ 30 字符；否则 stage 标 status=failed |
| G2 | Analyst 显式产出 bull_view + bear_view，asymmetric 允许 | 每个 view 含 `strength` ∈ {absent, weak, moderate, strong}；strength ≠ absent 时 `thesis_zh` 非空且 `supporting_event_ids` 非空；strength = absent 时 thesis_zh 与 supporting_event_ids 必须为空 |
| G3 | DecisionContext 含三元组并完整持久化 | 每条 analyst step 的 input_json 含 `decision_context.{history_brief, new_tweets, factor_delta}` 三段非空；history_brief.schema_version 与 search_agent_brief deterministic 输出 byte-equal |
| G4 | Critic 审查范围扩到 narrative，但仍单向 | Critic prompt 含三项 narrative 审查指令；任何 critic step 的 response_json 不得包含 narrative_type / narrative_thesis / bull_view / bear_view 字段（runtime validator 拒绝） |
| G5 | 三元组与新字段可重放 | 任取最近 7 天 token_target analyst step，从 input_json 重建的 DecisionContext byte-equal enqueue 时的 snapshot；从 response_json 反序列化的 AnalystOpinion v2 通过完整 schema 验证 |
| G6 | Hallucination 控制 | 0% Analyst response 包含 supporting_event_ids 中不在 `decision_context.history_brief.evidence_event_ids ∪ decision_context.new_tweets[].event_id` 并集的 event_id（worker 写入前校验，违例则 retry，重试后仍违例则 stage 标 failed 并 abstain） |
| G7 | 成本可控 | 单次 token_target run 的 token 用量分布：input p95 ≤ 12K，output p95 ≤ 2K（含三 stage 合计）；7 天 soft launch 后实测，若超阈值则调整 new_tweets 上限或 history_brief 长度限制 |

---

## 4. 非目标

- 不修改 Critic / Judge stage 的 output schema（CritiqueReport / FinalDecision 完全不动）。
- 不修改 Signal Pulse public payload 的 `decision` block 字段（route / recommendation / confidence / abstain_reason / stage_count / summary_zh / invalidation_conditions / residual_risks / evidence_event_ids 全部保持现状）。
- 不修改 `pulse_candidates.decision_*` 列结构。narrative / bull / bear 仅在 `pulse_agent_run_steps[stage=analyst].response_json` 落库，不进 candidate 主表。
- 不修改 Token Radar 任何 schema、查询、列表读路径或 frontend `TokenFlowItem` 类型。Token Radar 看见 agent 输出是独立 surface spec 的范围。
- 不修改 `search_agent_brief_v1` deterministic 模板，保留作 LLM-unavailable 时的 fallback brief。
- 不引入 outcome collector / reflector / narrative memory / multi-model voting / fine-tuning（target-agent-design phase 1+ 范围）。
- 不修改 DecisionContextBuilder 给 Critic / Judge 的输入（仅扩 Analyst input）。
- 不修改 source_seed 通道——source_seed 已 hard-block 在 LLM 前，不触达本 spec 改动的 Analyst stage。
- 不修改 LivePriceGateway / DEX WS 配置 / cohort 归一化算法（pipeline-current-state-cn 独立 spec 的范围）。
- 不引入 `narrative_thesis` 字段到任何 query / filter / 聚合统计 API。phase 0b.5 仅在 stage replay ledger 内可见。

---

## 5. 目标架构

### 5.1 分层增量

target-agent-design §5.1 五层架构保持不变。增量限定在两个位置：

```
DecisionContextBuilder            (扩 output 内容)
  ├─ factor_snapshot              (沿用 v3_social_attention)
  ├─ history_brief                (NEW: 复用 deterministic per-token brief builder)
  ├─ new_tweets                   (NEW: 复用 per-token timeline 查询)
  └─ factor_delta                 (NEW: 从 factor_snapshot.families.social_heat 抽取)

RoutePolicy                       (unchanged)
CompletenessGate                  (unchanged)

StageRunner
  Analyst                         (扩 output schema → AnalystOpinion v2)
  Critic                          (扩 prompt 审查范围，schema 不动)
  Judge                           (unchanged)

DecisionMapper                    (unchanged — 仅消费 FinalDecision)
RunAuditLedger                    (unchanged 结构，承载更大的 input_json/response_json)
```

### 5.2 AnalystOpinion v2 语义模型

| 字段 | 类型 | 语义 | 与 v1 关系 |
|---|---|---|---|
| `schema_version` | 受控 enum `"2.0"` | 用于 step ledger 反序列化路径区分 | 新增 |
| `narrative_type` | 受控 enum | 当前 token 在炒哪类叙事；候选值 `memetic / utility / migration / infra / ip / thematic / unclear`（plan 阶段最终锁定） | 新增 |
| `narrative_thesis` | 自由文本 30-300 字符 | 用一段话描述当前叙事的具体内容，必须能被 supporting_event_ids 支撑 | 新增 |
| `bull_view.strength` | 受控 enum `absent / weak / moderate / strong` | 看多论据的强度 | 新增 |
| `bull_view.thesis_zh` | 自由文本，可空（strength=absent 时） | 看多论据一段话 | 新增 |
| `bull_view.supporting_event_ids` | event_id 列表，可空（strength=absent 时） | 引用具体 tweet 或 history 事件 | 新增 |
| `bear_view.*` | 同 bull_view 三字段 | 看空论据 | 新增 |
| `key_evidence_event_ids` | event_id 列表 | bull/bear/narrative 引用的 ids 并集子集，供 Judge 与公共 evidence_event_ids 一致 | 新增 |
| `route` | 受控 enum（沿用 v1） | route 来自 RoutePolicy，Analyst 仅回显 | 保留 |
| `recommendation` | 受控 enum（沿用 v1） | Analyst 初步推荐 | 保留 |
| `confidence` | float 0..1 | Analyst 初始 confidence | 保留 |
| `summary_zh` | 自由文本短句 | 一句话总结；保留供 backwards-compatible 短摘要消费 | 保留 |
| ~~`evidence: list[str]`~~ | — | 旧 v1 字段 | **删除**（hard cut，由 key_evidence_event_ids + bull/bear.supporting_event_ids 取代） |

### 5.3 DecisionContext 三元组语义

| 段 | 语义 | 数据源 |
|---|---|---|
| `factor_snapshot` | 沿用 v3_social_attention，承载 subject / market / gates / data_health / families / normalization / composite / provenance | unchanged |
| `history_brief` | 同 target 在 24h 时间窗的 deterministic 摘要：仅包含 `project_summary`（项目/主题摘要 + data_gaps）与 `propagation`（传播路径分段 + 关键作者），**不包含 deterministic `bull_bear` 段** | 复用现有 `build_token_agent_brief`，调用后只取 `project_summary` + `propagation` 两段塞进 DecisionContext。Analyst 不应被 deterministic 模板的 bull/bear 锚定；它的 bull_view / bear_view 必须基于 factor_snapshot + new_tweets 自主推理 |
| `new_tweets` | 自上一次成功 run 至本次 enqueue 之间，该 target 的新增 tweets，按 attribution_weight 降序取 top N；每条含 event_id / author_handle / author_followers / received_at_ms / text_clean / is_watched 与可选 social_event_extractions.summary_zh | 复用现有 per-token timeline 查询；N 默认 ≤ 20，plan 阶段以 config 形式可调 |
| `factor_delta` | 本窗口 vs 上一对比窗口的关键变化：mention_delta / mention_delta_pct / unique_authors_delta / watched_authors_delta / compared_window_ms | 从 factor_snapshot.families.social_heat.facts 与上一窗口 snapshot 直接计算，不持久化为新表 |

`last_run_at_ms` 的语义：取同 `candidate_id` 最近一次 `pulse_agent_runs.status='succeeded'` 的 `started_at_ms`；初次或无成功记录时使用 `now - trigger_window_ms` 作为窗口起点。

### 5.4 Critic 审查范围扩展（prompt 增量，schema 不动）

Critic 必须额外审查以下三类问题（仅描述要审查什么，不规定如何描述）：

1. **Narrative coherence**: `narrative_thesis` 是否与 factor_snapshot / history_brief / new_tweets 中的事实一致？是否存在 overclaim（断言"已经形成共识"但 evidence 只有 2-3 个独立作者）？
2. **Evidence existence**: `bull_view.supporting_event_ids` 与 `bear_view.supporting_event_ids` 引用的每个 event_id 是否真实出现在 DecisionContext 的 `history_brief.evidence_event_ids` 或 `new_tweets[].event_id` 集合中？引用的方向是否与该 tweet 的实际语义一致（不能拿空头叙事的 tweet 当成多头 evidence）？
3. **Selective evidence**: bull 与 bear 是否选择性挑证据？例如 history_brief 显示 24h 内出现了 dump signal，但 Analyst bear_view.strength=absent 且未提及该 dump signal——Critic 应记入 weaknesses 并降 confidence_ceiling。

Critic 单向门限保持不变（target-agent-design §5.4）：Critic 在 `CritiqueReport.weaknesses` / `missing_fact_impacts` / `confidence_ceiling` / `should_abstain` 中记录所有审查结果；**Critic 不得**返回任何 `narrative_type` / `narrative_thesis` / `bull_view` / `bear_view` 字段。worker 写入 step 前用 schema validator 强制 reject critic response 中的这些字段。

### 5.5 Judge 与 FinalDecision 不变的契约理由

Judge 的职责是综合 Analyst 与 Critic 给出最终 recommendation / confidence / abstain_reason / summary_zh / invalidation_conditions / residual_risks。这些字段已经覆盖"决策"语义，narrative 与 bull/bear 是"观察"语义，属于 Analyst。把 narrative 引入 FinalDecision 会让 Judge 同时承担观察与决策，违反单一职责，并破坏 CONTRACTS.md 中已稳定的 `decision` block 公共契约。前端 PulseDetailView 已经通过 `stages.analyst.response` 直接消费 Analyst 输出，narrative / bull / bear 在 Analyst step ledger 中可见，不需要冗余到 FinalDecision。

---

## 6. 数据契约要求（semantic 级别）

### 6.1 DecisionContextBuilder 输出契约

- `factor_snapshot` 必须为 `token_factor_snapshot_v3_social_attention`（Token Radar 当前唯一合法版本）。
- `history_brief` 必须 deterministic：同一 `(target_key, snapshot_at_ms)` 输入产生 byte-equal 输出；不调用 LLM；不依赖随机种子或 wall clock 之外的可变状态。
- `new_tweets` 排序契约：按 `attribution_weight` 降序，等权时 `received_at_ms` 降序；条数有硬上限（默认 20，plan 阶段定可调上限）；每条字段集合不变（event_id / author_handle / author_followers / received_at_ms / text_clean / is_watched / extraction_summary_zh?）。
- `factor_delta.compared_window_ms` 必须显式声明（不允许"隐式默认"），保证 replay 时下游能反推对比窗口。
- 三元组整体在 enqueue 时一次性 snapshot 进 `pulse_agent_jobs.context_json`，job retry 看到的 DecisionContext 与首次 enqueue 时 byte-equal。

### 6.2 AnalystOpinion v2 输出契约

- `schema_version = "2.0"` 是 hard cut：worker 写入 step 时不再接受 v1 schema 输出；v1 历史数据保留在 step ledger 但反序列化路径区分。
- 所有 `supporting_event_ids` 与 `key_evidence_event_ids` 必须 ⊂ `decision_context.history_brief.evidence_event_ids ∪ decision_context.new_tweets[].event_id` 的并集。
- 当 `bull_view.strength = absent` 或 `bear_view.strength = absent` 时，对应 `thesis_zh` 必须为空字符串、`supporting_event_ids` 必须为空列表。
- `narrative_thesis` 必须能由 `key_evidence_event_ids` 中至少 1 个 event 支撑（worker 不做语义校验，但 Critic 必须审查）。
- 输出包含 trading execution language（buy / sell / long / short / position / stop loss / target price）的，worker 强制 reject（沿用 phase 0b 已有的 forbidden-language pattern）。

### 6.3 公共 contract 不变性

- `/api/signal-lab/pulse` 列表与 `/api/signal-lab/pulse/<id>` 详情的 `decision` block 字段集合完全不变。
- pulse-detail-redesign-cn 已经设计的 `stages` payload 中 `stages.analyst.response` 会**自然包含** AnalystOpinion v2 的新字段，前端只需要扩展类型定义即可消费，不需要新增 endpoint。
- `pulse_candidates.decision_*` 列与 `decision_json` 不变；narrative / bull / bear 只在 `pulse_agent_run_steps` 落库。

---

## 7. 风险与权衡

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Analyst prompt + output 显著变长，单次 token 成本上升 | 高 | G7 设硬阈值（input p95 ≤ 12K，output p95 ≤ 2K）；plan 阶段以 config 定 `new_tweets` 上限 N 与 `history_brief.summary_zh` 字符上限 M；soft launch 24h 实测，超阈值则下调 N/M |
| Critic 在 narrative + bull/bear + 原数据三个维度审查，可能 anchor 在文采上 | 中 | Critic prompt 明确"只评估事实存在性、引用方向、selective evidence；不评价中文表达"；Critic schema validator 强制 reject 任何 narrative / bull / bear 字段，让 Critic 物理上无法"重写" narrative |
| Hallucination：Analyst 引用不存在的 event_id | 高 | G6 要求 worker 写入前强校验 supporting_event_ids ⊂ DecisionContext id 并集；不通过则 stage 标 status=failed，触发 retry；retry 后仍违例则 abstain（按 phase 0b 已有 retry 路径） |
| bull/bear asymmetric 被滥用（Analyst 偷懒全 absent） | 中 | metric `bull_view.strength=absent AND bear_view.strength=absent` 占比超过 30% 触发 alert；plan 阶段在 Analyst prompt 中加约束"两边同时 absent 仅在 narrative_type=unclear 时允许" |
| history_brief 是 deterministic 模板，对 Analyst 影响不大但 prompt 占位 | 低 | history_brief 是 input，不是 output；LLM 用自己的话重组到 narrative_thesis；模板呆板不会传递到 narrative 输出 |
| AnalystOpinion v1 → v2 hard cut，老 step 行无法用 v2 反序列化 | 中 | 用户偏好 hard cut；plan 阶段确认 7 天历史 step 数量与 replay 频次后再决定，可选 step ledger 添加 schema_version 列做反序列化路径区分；本 spec 推荐 hard cut（v1 step 标记为 legacy，不再 replay） |
| Critic 审查 narrative 时若 Critic 自身 hallucinate（错误判定 narrative overclaim），会无故 abstain | 中 | Critic 仍是单向夸门，只能降权或 abstain，不能上调；Judge 审查 Critic 的 weaknesses 是否真实成立；如 Critic 错误 abstain，下次 trigger（5min cooldown 后）会重跑 |
| schema 大改导致 pulse_agent_run_steps.response_json 占用上升 | 低 | response_json 是 JSONB，单 step 增量约 1-2KB；按 27 trade_candidate/小时 × 24h × 30d 估约 1GB/月，可接受；超出时归档老 step 到冷存 |
| 前端 PulseDetailView 需要适配新字段，但 redesign 还在进行中 | 中 | redesign spec phase 1 已经设计 `stages.analyst.response` 渲染入口；本 spec 落地后前端只需在 `analyst` 卡内增加 narrative / bull / bear 子区块；redesign 与本 spec 可并行推进，互不阻塞 |

---

## 8. 演进路径

### Phase 0b.5（本 spec）

DecisionContextBuilder 喂三元组 + AnalystOpinion v2 输出 narrative / bull / bear + Critic prompt 扩 narrative 审查。30 天稳定运行后产生足够样本。

### Phase 1（独立 spec）

- 基于 phase 0b.5 落地的 narrative_type / bull_view / bear_view 30 天样本，与事后价格 / 流动性 / 回撤回写做 narrative-level calibration（"过去 30 天 narrative_type=memetic 且 bull_view.strength=strong 的 token，48h 后中位回报"）。
- 这是 target-agent-design §12 phase 1 OutcomeCollector / Reflector 的真实输入信号。

### Phase 2（独立 spec）

- narrative calibration 结果进入 prompt context 形成 memory loop；calibration 偏差大的 narrative_type 触发 prompt 调整。
- Token Radar 列表层暴露 narrative_thesis 短句（独立 surface spec，不属于本 spec 范围）。

---

## 9. Open Questions

1. **narrative_type enum 具体取值集合**：本 spec 给出候选 `memetic / utility / migration / infra / ip / thematic / unclear`，plan 阶段需要：(a) 评估这 7 个值能否覆盖近 30 天实际 pulse token 的叙事分布；(b) 锁定最终 enum；(c) 决定是否预留 `other` 兜底值。
2. **`new_tweets` 条数上限 N 默认值**：spec 建议 ≤ 20，plan 阶段需要：(a) 抽样 10-20 个 high_alert token 的 new_tweets 实际分布；(b) 估算 N=20 vs N=10 的 token 成本差；(c) 锁定默认值与 config 名。
3. **AnalystOpinion v1 → v2 是否完全 hard cut**：spec 推荐 hard cut（DROP v1 反序列化路径），plan 阶段需要：(a) 统计当前 step ledger 中 v1 schema 行数；(b) 评估 7 天内是否有 replay v1 step 的实际需求；(c) 如有需求，在 `pulse_agent_run_steps` 加 `schema_version` 列做反序列化路径分流。
4. **history_brief 是否对 source_seed 通道也喂**：source_seed 当前 hard-block 在 CompletenessGate 之前，不进 Analyst。本 spec 假设仅 token_target 通道走新 DecisionContext。plan 阶段需要确认 source_seed 不触达本改动。
5. **bull/bear 同时 absent 的语义边界**：spec 提出 "narrative_type=unclear 时允许"，plan 阶段需要：(a) 评估是否还需要其他场景允许双 absent（如 `decision.route=research_only` 短路时 Analyst 是否被调用）；(b) 锁定双 absent 的合法前置条件。
6. **G6 校验严格度**：spec 要求 supporting_event_ids ⊂ event_id 并集，plan 阶段需要：(a) 评估是否允许引用 history_brief 文本中提到的"narrative point"（非 event_id 的概念引用，例如"过去 KOL 共识"）；(b) 如允许，定义 narrative_point 引用的合法 ID 格式。

---

## 10. 决策日志

| 决策 | 理由 |
|---|---|
| 把 narrative + bull/bear 加在 Analyst 而非 Judge 或新增 stage | 叙事与多空是"观察"语义，与 Analyst 职责一致；放 Judge 会让 Judge 承担观察+决策两个角色；新增 stage 会突破 target-agent-design §5.4 的三阶段定义并增加 33% 成本 |
| 保留 asymmetric bull/bear | 与 §2.1 "agent 只能解释事实，不能补造事实" 一致；强行要求对称会诱导 hallucination |
| Critic schema 不动，只扩 prompt 审查范围 | 与 §2.4 "Critic 是 governor，不是 theater" 一致；如果 Critic 也能产出 narrative / bull / bear，Critic 实质变成第二个 Analyst，违反单一职责 |
| DecisionContext 三元组在 enqueue 时一次性 snapshot 进 context_json | 与 §2.5 replay 优先原则一致；retry / replay 时看到的 DecisionContext byte-equal；不引入新表 |
| history_brief 复用 deterministic builder，不引入 LLM-driven brief | DESIGN_DISCIPLINE §27 "Reuse before create"；deterministic brief 已经稳定输出 schema，作为 input 给 LLM 足够；引入 LLM brief 会引入嵌套 LLM 调用与 phase 1 outcome 域 |
| 不修改 FinalDecision schema 与 public decision block | CONTRACTS.md 的 decision block 已稳定，是 phase 0b hard cut 的结果；narrative / bull / bear 通过 stage replay ledger 暴露给 PulseDetailView 已足够 |
| 不把 narrative / bull / bear 暴露到 Token Radar 列表 | Token Radar 是 scan surface，列表层加 LLM 输出会让 `domains/token_intel/` JOIN pulse 表，违反层次方向；独立 surface spec 在 phase 0b.5 落地后再处理 |
| 不修改 search_agent_brief deterministic 模板 | 保留作 LLM-unavailable 时的 fallback brief；与本 spec 解耦，不形成循环依赖 |
| AnalystOpinion v2 倾向 hard cut DROP v1 反序列化路径 | 用户明确偏好 hard cut；与 phase 0b 删除旧 agent_recommendation_json 的风格一致；plan 阶段最终评估 |
| 不在本 spec 处理 DEX WS / cohort percentile / NULL 直通等 pipeline-current-state 问题 | 那些是独立 spec 的范围；本 spec 假设 LLM 前 gate 通过的 token 才进 Analyst，gate 端的修复不属于 agent runtime contract 演进 |
