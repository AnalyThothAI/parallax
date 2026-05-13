# Target Agent Architecture — 统一 Agent Runtime Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-13
**Updated**: 2026-05-14
**Owner**: Codex with Qinghuan
**Scope**: 从第一性原理定义一个可复用的 agent 决策运行时，并把 Signal Pulse 作为 phase 0b 的第一个落地策略。本文是 spec，不包含 SQL、函数签名、文件级任务、prompt 全文或 PR 拆分。
**Harness**: 保留 `openai-agents-python`，使用顺序 stage runner；不迁 LangGraph。
**TradingAgents 参考方式**: 借鉴角色分离、结构化状态、对抗审查、事后反思与记忆循环；不照搬 9+ agent、美股工具链、LangGraph 编排或交易执行 schema。

**Related**:
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/DESIGN_DISCIPLINE.md`
- `docs/RELIABILITY.md`
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`
- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`
- `docs/superpowers/specs/active/2026-05-13-token-radar-pipeline-overcomplexity-audit-cn.md`
- `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md`
- External reference: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)

---

## 一句话结论

可以做统一、成熟、可演进的 agent 方案，但成熟点不在“多放几个 agent”。成熟点是把 agent 变成一个可审计的决策运行时：事实上下文先于模型意见，结构化状态先于聊天记录，确定性 gate 先于 LLM，Critic 是约束器而不是表演式辩论，完整 replay 与 outcome 反思先于 prompt 微调。

Phase 0b 的落地方式是：在 `pulse_lab` 上引入统一 Agent Runtime Core，并把 Signal Pulse 的 token_target 决策拆成 CEX / Meme 两条 route，每条 route 使用 Analyst → Critic → Judge 三阶段；source_seed 这种无 target 的输入不进入资产决策 route，只产生 deterministic research-only / abstain 记录。现有 Pulse recommendation contract hard cut 为 `decision` block，不保留旧 recommendation 兼容层。

## 1. 当前代码事实

### 1.1 已经存在的好边界

- `pulse_lab` 已经是 Signal Pulse 的领域边界，拥有 candidate gate、worker、read model、repository 与 provider protocol。
- `integrations/openai_agents` 已经把 OpenAI Agents SDK 包在 adapter 内，不反向拥有领域逻辑。
- `app/runtime/providers_wiring.py` 是集成层与领域 provider contract 的连接点。
- Token Radar hard cut 已把 public market contract 推向 `market.event_anchor`、`market.decision_latest`、`market.readiness`，这给 agent 决策提供了比旧 live overlay 更清晰的事实入口。
- `PulseCandidateWorker` 已经有 DB job queue、poll catch-up、wake hint、retry attempt、gate-before-persist 的运行形态，适合升级为 stage runner，而不是推倒重来。

### 1.2 仍然不成熟的点

- 当前 Pulse recommendation 是单 agent 调用，`max_turns` 只是单次输出的保护，不是多角色决策机制。
- `request_json` 仍偏向 hash/audit summary，无法完整 replay 每个 stage 当时看到的 prompt、输入与结构化输出。
- 旧 `agent_recommendation_json` 承载了过多语义，route、confidence、abstain reason、stage outcome 没有成为一等公民。
- source_seed 与 token_target 被同一个 agent 语义处理，导致“无 target 的研究线索”和“有 target 的资产决策”没有清晰边界。
- Token Radar 的市场事实已经向新 contract 演进，但 Pulse 决策层还没有把 data completeness 作为 LLM 前置 gate 和 Critic 约束。

### 1.3 根因判断

“agent 不可靠”不是根因，它只是症状。根因是决策系统缺少三个层次：

1. 决策前的事实门控：当 `decision_latest`、cohort status、DEX floor fields 缺失时，应先 deterministic abstain 或降级，而不是让模型自由解释。
2. 决策中的对抗约束：模型需要一个专门找证据漏洞、置信度上限、缺失字段影响的 Critic。
3. 决策后的回放与反思：没有完整 replay，就无法解释为什么错；没有 outcome loop，就无法知道置信度是否校准。

## 2. 第一性原理

### 2.1 事实账本先于 agent 意见

Agent 只能解释事实，不能补造事实。进入 agent 的上下文必须能回答：事实来自哪里、什么时候观测、是否新鲜、缺了什么、缺失是否影响决策。

### 2.2 结构化状态先于聊天历史

TradingAgents 的价值不在多轮对话本身，而在它把分析、研究辩论、交易员、风险管理、组合经理拆成有状态节点。我们在本项目里不需要 LangGraph，但需要同样的结构化中间态：每个 stage 有明确输入、输出、状态转移与审计记录。

### 2.3 确定性 gate 先于 LLM

能用规则判断“不应进入交易候选”的，不应消耗 LLM token。尤其是缺少 `decision_latest`、cohort insufficient、DEX floor unverified、source_seed 未解析 target 这类情况。

### 2.4 Critic 是 governor，不是 theater

Bull/Bear 辩论适合 TradingAgents 的研究演示，但本系统要的是稳定的生产约束。Critic 不应自由翻案；它的职责是发现证据漏洞、设置 confidence ceiling、触发 abstain。

### 2.5 Replay 与 outcome 先于 prompt tuning

Prompt 不是靠感觉改的。每次 run 必须能重放 stage input、prompt、model、output、latency、error；phase 1 再把事后价格/流动性变化写回 outcome，形成 calibration memory。

## 3. 目标

- 建立可复用 Agent Runtime Core：route policy、stage schema、stage runner、run step audit、decision mapping、replay contract。
- Signal Pulse phase 0b 使用 runtime 落地 CEX / Meme 两条 token_target route。
- 每条资产 route 采用 Analyst → Critic → Judge 三阶段，保持顺序、可测、可回放。
- source_seed 保持 pre-target research-only 语义：没有 target 不进入 CEX/Meme 资产决策，也不能产出 high conviction。
- route、recommendation、confidence、abstain_reason、stage_count、decision summary 成为公共 contract 的显式字段。
- 继续保留现有 `pulse_status` 展示语义，但删除旧 recommendation 兼容面，前端改读 `decision`。
- 落地后 high_conviction 不再接近 100%，abstain/error 可观测且有原因。

## 4. 非目标

- 不重写 Token Radar 或 market data pipeline，只定义 agent 对它们的契约要求。
- 不引入 LangGraph、CrewAI、AutoGen 或新的 agent framework。
- 不照搬 TradingAgents 的全角色图、工具集、portfolio manager 或交易执行字段。
- 不在 phase 0b 做 outcome collector、self-consistency、多模型投票、RLHF、fine-tuning。
- 不新增真实下单、仓位、止损、资金管理接口。
- 不把 source_seed 包装成第三条完整资产 route。
- 不把 prompt 全文放进 spec；prompt 是 plan/implementation 产物。

## 5. 目标架构

### 5.1 分层

```text
Signal facts / Token Radar read model / Pulse job queue
  -> DecisionContextBuilder
  -> RoutePolicy
  -> CompletenessGate
  -> Agent Runtime Core
       Stage 1: Analyst
       Stage 2: Critic
       Stage 3: Judge
  -> AgentDecisionRecord
  -> Pulse persistence / read model / HTTP / WS
  -> Phase 1: OutcomeCollector / Reflector / Memory
```

### 5.2 Agent Runtime Core

Runtime Core 是跨策略复用层，职责是编排和审计，不负责市场判断：

- `DecisionContext`: 统一承载 target、event timeline、factor snapshot、market contract、gate result、source ids、trace ids。
- `RoutePolicy`: 决定 context 应走哪条 strategy route，或在没有 target 时停在 research-only/abstain。
- `CompletenessGate`: 在 LLM 前判断是否可以进入 stage runner。
- `StageRunner`: 顺序执行固定 stage，记录每一步的 input、prompt、model、output、usage、latency、status。
- `DecisionMapper`: 把 final decision 映射回领域状态、candidate persistence、public payload。
- `RunAuditLedger`: 保存 run 与 step 级审计，支持 replay。

### 5.3 Signal Pulse Strategy

Signal Pulse 是第一个 runtime strategy：

- `token_target + cex-like market`: CEX route。
- `token_target + dex/meme/new-pair market`: Meme route。
- `source_seed + no resolved target`: research-only / abstain，不进入资产 route。

CEX route 更重视 venue、流动性、OI/funding、BTC-relative context 与 news/event half-life。Meme route 更重视 DEX floor、holders/liquidity/mcap、age、dev/top holder 风险、KOL 单点传播与 cohort 可用性。

### 5.4 三阶段职责

| Stage | 职责 | 不允许做什么 |
|---|---|---|
| Analyst | 基于 route-specific checklist 给初步观点、证据、推荐、置信度 | 不得忽略 hard missing facts；不得把单条 tweet 当成完整 thesis |
| Critic | 找证据漏洞、缺失字段影响、过拟合叙事、confidence ceiling、是否 abstain | 不得反向生成新 thesis；不得上调置信度 |
| Judge | 综合 Analyst 与 Critic，产出 final recommendation、confidence、abstain reason、invalidation conditions | 不得突破 Critic confidence ceiling；不得绕过 pre-LLM gate |

## 6. TradingAgents 的取舍

| TradingAgents 思路 | 本项目采用方式 | 不采用原因 |
|---|---|---|
| 多角色分工 | 保留 Analyst/Critic/Judge 的职责隔离 | 全量 9+ agent 延迟和复杂度过高 |
| Bull/Bear debate | 收敛成 Critic 的 confidence ceiling 与 abstain veto | 生产系统更需要稳定约束，不需要辩论表演 |
| Research Manager / Trader / Risk / Portfolio | phase 0b 不做；phase 2 真实交易前再设计 | 当前是看盘/研究，不是自动下单 |
| LangGraph state machine | 用本项目自己的顺序 stage runner 与 DB ledger | 现有架构已围绕 domain worker/repository，迁图框架收益不够 |
| Structured outputs | 强采用，每个 stage 都必须有结构化输出 | 这是可测试与可回放的核心 |
| Memory / reflection | phase 1 引入 outcome collector + reflector | 没有生产运行样本前，memory 只会放大噪声 |

## 7. 语义模型

以下是语义模型，不是代码签名。

- `DecisionContext`: 决策上下文。包含 run identity、target identity、source scope、factor snapshot、market readiness、event timeline、candidate gate、evidence ids、request metadata。
- `DecisionRoute`: 决策路径。phase 0b 包含 `cex`, `meme`, `research_only`。
- `AgentStageOutput`: 单个 stage 的结构化输出，必须可验证、可序列化、可重放。
- `AnalystOpinion`: 初始观点。包含 route、recommendation、confidence、evidence、summary。
- `CritiqueReport`: 约束报告。包含 weaknesses、missing facts impact、confidence ceiling、should abstain。
- `FinalDecision`: 最终判断。包含 route、recommendation、confidence、abstain reason、summary、invalidation conditions、residual risks。
- `AgentRunStep`: stage 级审计记录。保存输入、prompt、模型、输出、token/latency、状态、错误。
- `DecisionOutcome`: phase 1 事后结果。把最终判断与后续价格、流动性、回撤、人工复盘连接起来。

## 8. Public Contract

### 8.1 Signal Pulse item

现有 `factor_snapshot`、`gate`、`fact_card` 保留。`agent_recommendation` hard cut 删除，新增 `decision` block：

- `route`: `cex` / `meme` / `research_only`
- `recommendation`: `high_conviction` / `trade_candidate` / `watchlist` / `ignore` / `abstain`
- `confidence`: `0..1`
- `abstain_reason`: 缺失时为 null
- `stage_count`: 已完成 stage 数
- `summary_zh`: 面向 UI 的短摘要
- `invalidation_conditions`: 后续翻案条件
- `residual_risks`: 剩余风险

### 8.2 Hard Cut 原则

- 删除旧 `agent_recommendation_json` 的运行时读写，不做双写、别名、fallback 或旧 payload 映射。
- 不把 `abstain` 加进现有 `pulse_status` 的核心枚举；abstain 是 decision 语义，不是 display status。
- 默认 Signal Lab 展示仍由现有 display status 控制，同时默认隐藏 `decision.recommendation=abstain` 的研究噪声。
- API/WS 切到 `decision` 字段；旧客户端需要跟随前端/类型更新。

## 9. 数据契约要求

进入 CEX/Meme route 前，context 必须能表达：

- `market.decision_latest` 是否存在、是否新鲜、缺哪些字段。
- `market.event_anchor` 与当前决策时间的关系。
- `market.readiness` 的 missing/stale/blocker 列表。
- cohort status 是否 `ready`，或是 insufficient/all-tied/no-signal。
- DEX floor 所需 holders、liquidity、market_cap、volume、age 是否已验证。
- source/evidence ids 是否能追溯到原始 event 或 extraction。

如果这些事实不足以支撑 route 的 hard gate，runtime 必须在 LLM 前结束，并写入可审计的 abstain/research-only 决策。

## 10. 验收标准

Phase 0b 完成时必须满足：

- 所有进入 LLM 的 token_target run 都有完整 run step replay 记录。
- source_seed 未解析 target 时不调用 CEX/Meme stage，不产生 high_conviction。
- hard missing `decision_latest`、cohort insufficient/all-tied、DEX floor unverified 时，LLM 前 gate 能 deterministic abstain 或强降级。
- `decision.route`、`decision.recommendation`、`decision.confidence`、`decision.stage_count` 在 public payload 中稳定存在。
- 旧 `agent_recommendation_json` 运行时路径和旧 UI/测试断言移除。
- 7 天 soft launch 后，high_conviction 占比低于 15%，agent run error 低于 5%，abstain 有明确 reason 分布。
- 任取最近一次 run，工程师能从 DB 重建每个 stage 的输入、prompt、输出与失败点。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 三阶段增加延迟和 token 成本 | pre-LLM gate 拦截 source_seed/缺数据样本；stage timeout 与 retry 上限固定 |
| Critic 过严导致全 abstain | route-specific hard/soft gate 分离；soft launch 观察 abstain reason |
| Prompt 变复杂但无法解释 | run step ledger 必须先落地，再调 prompt |
| Public contract 破坏前端 | 同 PR 更新前端类型与 Signal Lab 组件，避免双轨兼容 |
| Runtime Core 抽象过早 | 只抽编排/审计/路由/映射，不抽市场判断 |
| TradingAgents 参考过度 | 明确 phase 0b 不引入 LangGraph、Risk Manager、Portfolio Manager、真实交易 |

## 12. 演进路径

### Phase 0b: 统一 runtime + Signal Pulse strategy

落地 route policy、completeness gate、三阶段 runner、run step replay、public decision block。

### Phase 1: Outcome 与 reflection

新增 outcome collector，把 1h/24h 后的价格、流动性、回撤、人工复盘写回；Reflector 按 route/recommendation/confidence band 生成 calibration memory，作为下一轮 prompt context。

### Phase 2: 半自动交易决策支持

在 phase 1 的校准样本足够后，再设计 trader/risk/portfolio 层。届时才引入 entry thesis、position sizing、risk budget、execution guard，不在 phase 0b 预留胖 schema。

## 13. 决策日志

| 决策 | 理由 |
|---|---|
| 做统一 Agent Runtime，而不是只改 Pulse prompt | prompt 只能改善表层输出，runtime 才能解决 replay、gate、role、outcome 的系统问题 |
| 保留 openai-agents-python | 现有 integrations 已经接入，顺序 stage 足够；迁移框架会扩大风险 |
| CEX/Meme route 只用于 token_target | source_seed 没有资产事实，进入资产 route 会制造伪确定性 |
| 不把 abstain 塞进 `pulse_status` | `pulse_status` 是现有展示/过滤语义，abstain 是 decision 语义；混在一起会破坏 public surface |
| 删除旧 recommendation 兼容层 | 用户明确要求无兼容代码；hard cut 可避免双写、双读和长期语义漂移 |
| Phase 1 才做 reflection | 没有 outcome 数据时反思只是 prompt 自嗨；先把 replay 和 outcome schema 空间留清楚 |
| 借鉴 TradingAgents 但不复制 | 它证明了多角色金融 agent 的理论价值；本项目要的是更小、更可审计、更贴合现有服务边界的生产版本 |
