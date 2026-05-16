# Pulse Agent Desk 架构重设计（KISS hard cut v2）

- **状态**: Draft v2, awaiting review
- **作者**: aaurix（with Claude Opus 4.7 architectural review + 3-way independent audit）
- **日期**: 2026-05-16
- **v2 变更要点**: v1 被 3 路 reviewer 审出 14 个 high-severity 缺陷与 KISS 过度设计。v2 采纳 Reviewer 推荐的 3 个架构层收敛：(1) Reflector + Outcome 回路独立 phase 2 spec；(2) NarrativeBriefWorker 砍掉（Investigator 工具直接查）；(3) Playbook 字段降级（删 sizing_band / key_observation_levels / playbook_type 5 enum）。同时把 markdown_report、6→3 工具、grader rule 收敛一并打包。
- **取代**: `2026-05-13-target-agent-architecture-design-cn.md`、`2026-05-14-pulse-decision-context-narrative-cn.md`、`2026-05-14-pulse-detail-redesign-cn.md` 的 Agent Runtime / stage 字段约定 / detail 渲染契约。`2026-05-16-unified-agent-worker-runtime-cn.md` §5.1 M1 schema hard fix 作为本 spec 的前置依赖保留。
- **关联**:
  - `docs/ARCHITECTURE.md` Kappa/CQRS 边界
  - `docs/CONTRACTS.md` Signal Pulse decision block
  - `docs/DESIGN_DISCIPLINE.md` reuse-before-create / hard-cut 原则
  - `docs/RELIABILITY.md` audit ledger 规则
  - `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
  - External reference: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- **不在范围**: SQL 语句、Pydantic 字段名细节、prompt 全文、PR 拆分、文件级 diff、迁移命令。这些是 plan 与 implementation 的产物。

---

## 一句话结论

把现有 `Analyst → Critic → Judge` 三 stage 单 LLM 通道，hard cut 改为 **`Investigator → DecisionMaker`** 两调用架构。Investigator 带 3 个核心工具基于事实追问，输出结构化多空 observation；DecisionMaker 综合并产出含 narrative + 文本 playbook 的 FinalDecision。**Phase 1 净增 0 张新表、0 个新 worker、0 个 deferred 调用**，所有改动局限在 `pulse_lab` + `integrations/openai_agents` + `notifications` 三个域。Outcome 回路与叙事预聚合表留给独立 phase 2 spec。

---

## 1. 当前代码事实

### 1.1 已稳定的好边界（必须保留）

- `pulse_lab` 域边界与 `integrations/openai_agents` adapter 分离，agent client 不持有领域 SQL（per ARCHITECTURE.md）
- `PulseCandidateWorker` 已有 DB job queue、edge state、run budget、advisory_lock 单冷写、wake-hint + interval 双触发
- `pulse_agent_run_steps` 是完整 replay ledger：input / prompt / response / usage / latency 每个 stage 落库
- `pulse_candidates` 主表已包含完整决策列（`decision_route / decision_recommendation / decision_confidence / decision_abstain_reason / decision_stage_count / decision_json`），**本身就是 append-update 形态的决策 ledger**，不需额外 ledger 表
- `pulse_agent_eval_cases` + `agent_harness_eval` 已有 deterministic grader 闭环
- 14 worker Kappa/CQRS pipeline 持续产出 events / token_intents / market_ticks / enriched_events / token_radar_rows
- pre-LLM `_factor_completeness` + `hard_blocked` gate 已实装，缺数据 candidate 不消耗 LLM token
- `2026-05-16-unified-agent-worker-runtime-cn.md` §5.1 M1 schema hard fix 已设计完，作为本 spec 前置依赖

### 1.2 仍不成熟的架构性缺陷

| # | 缺陷 | 根因层级 |
|---|---|---|
| **C1** | Analyst 看到的是预压扁的 `factor_snapshot` blob，`tools=[]`，无法基于事实追问 | 架构：感知层与推理层完全切断 |
| **C2** | Critic 角色是"否决器"而不是"Bear 研究员"，90% veto 导致三 stage 退化为单 stage（24h 实测：1580 analyst → 1385 critic → 124 judge）| 架构：误把对抗约束当成 governor |
| **C3** | FinalDecision 输出 summary_zh + invalidation_conditions + residual_risks 是"研究报告"，不是"可操作监控清单" | 架构：缺 trader 视角的 playbook 字段 |
| **C5** | Notify body 渲染时丢弃 `payload_json` 80% 信息（route/recommendation/confidence/invalidation/residual/evidence 全在 payload 但 markdown body 只出 5 行）| 渲染：surface 把 decision 当文档不当 playbook |

> **v1 的 C4（outcome 回路缺失）移到 phase 2 独立 spec**。本 spec phase 1 不解决，因为：(a) outcome 信号在 meme/1h horizon 下噪声大，未验证 ROI；(b) past_context 在 reflection 积累前 7-14 天为空，phase 1 价值不可评估；(c) 把 outcome 与 reflection 独立 spec 让 phase 1 PR 收敛 30% 代码量。

### 1.3 真实生产数据（2026-05-16 实查）

- 24h 决策分布：abstain 95% / trade_candidate 0.6% / high_conviction 1 条
- `pulse_candidates.narrative_type`: 1516/1516 行全是 `'direct_token'`（占位死字段）
- `asset_profiles.description`: 5359 ready 行 / 0 非空（GMGN provider 未拉此字段）
- `factor_snapshot.families.semantic_catalyst.facts.llm_covered_mentions = 0`（enrichment 没回写）
- AnalystOpinion v1 schema：`{route, recommendation, confidence, summary_zh, evidence: list[str]}`，无 narrative/bull/bear/playbook 一等公民

### 1.4 根因判断

"agent 输出无交易指引、无叙事、推送过简" 不是 prompt 缺词或 schema 缺字段的表层问题。它是**认知架构不完整**：完整的研究→决策→执行闭环被压缩成了一个 LLM + 一个 veto 阀，**缺 tools + 缺 playbook 字段 + 渲染层丢信息**三件叠加，所以无论怎么调 prompt 都触不到天花板。

---

## 2. 第一性原理（4 条，phase 1 范围）

### 2.1 Agent 必须能基于事实追问，不是消费 pre-computed snapshot

`factor_snapshot` 是 worker 层的预聚合结果，承载"全局可计算的事实"。决策时需要的"个例化追问"（24h 内 KOL 提的具体内容、原始 tweet 文本、官方 description）无法预聚合，必须以 **tool call** 形式让 agent 按需查询。否则 agent 永远只能"看图说话"。

### 2.2 多空是 observation，不是 stage

Bull / Bear 是同一份事实的两个视角。把它们拆成两个独立 agent 多轮辩论（TradingAgents 范式）对**单 ticker / 单决策周期 / 模拟交易**场景值得；对**高吞吐 / 实时流 / 无下单 / 单一研究目标**的 gmgn，让一个模型在一个 turn 内同时输出 bull_view + bear_view 已经覆盖核心价值，不需要拆 stage。

### 2.3 决策输出必须是 playbook 不是报告

合规约束禁止 buy / sell / position 语言，但**不等于禁止可执行性**。可执行的研究产物是 **playbook 文本指引**：监控信号（watch_signals）+ 退场触发（exit_triggers）+ 监控窗口（monitoring_horizon）。**不引入价格字段、不引入 sizing 等级**——这些已逼近"伪交易指令"，phase 1 不验证其价值，phase 2 数据驱动再决定。

### 2.4 KISS：phase 1 边界划在最小可验证增量

Phase 1 要验证的核心命题是 "Investigator (带 tools) + DecisionMaker (双视角 + playbook) 能否产出比现有 3 stage 更有交易指引价值的 signal"。其它（outcome 回路、reflection、narrative 预聚合、playbook 类型学）都是独立维度，独立 spec 验证。

---

## 3. TradingAgents 的取舍

TradingAgents 11 角色覆盖的是 "模拟交易公司" 全栈职能（4 分析师 + 2 研究员 + 1 经理 + 1 交易员 + 3 风控 + 1 PM）。gmgn 不下单 + 高吞吐 + 短决策周期，**只需要 2 个角色**（Investigator + DecisionMaker）就能覆盖 phase 1 需求。

借鉴：
- **Tools-using analyst**：Investigator 必须带 tools（TradingAgents A2）
- **结构化输出只在决策点**：Investigator 自由 + DecisionMaker 强 schema（TradingAgents A7）
- **State 是显式累积型工件**：`pulse_agent_run_steps` 每 stage 一行 ledger（TradingAgents A1）

明确不引入：
- LangGraph framework
- Bull/Bear 多轮 stage 辩论
- Risk persona 多角色
- Multi-model deep/quick 分层
- **Outcome reflection memory loop**（移到 phase 2 独立 spec）

---

## 4. 目标架构

### 4.1 分层

```
[Provider 感知层 — 不动]
  GMGN WS / OKX DEX WS / X / market tick / asset identity ...
       │
       ▼
[Curator 层 — 不增 worker]
  TokenRadarProjectionWorker  (现有)
  EnrichmentWorker           (现有)
  (Phase 2 候选：NarrativeBriefWorker)
       │
       ▼
[Pulse Candidate Worker — 入队/edge/budget 机制不动]
  pre-LLM CompletenessGate    (现有 _factor_completeness, 保留)
  RoutePolicy                 (现有, 保留)
       │
       ▼
[Agent Desk Runtime — 本 spec 改造区]
  Stage 1: Investigator       (带 3 个工具, 输出 InvestigationReport)
  Stage 2: DecisionMaker      (无 tool, 输出 FinalDecision)
       │
       ▼
[Decision Persistence — 不增表]
  pulse_candidates             (现有, decision_json 字段扩展)
  pulse_agent_run_steps        (现有, stage 枚举改)
       │
       ▼
[Surface 层 — 渲染重写]
  NotificationRuleEngine       (现有, _pulse_body 重写为 SurfaceCard)
  Signal Pulse Detail          (前端, 渲染 InvestigationReport + FinalDecision)
  Token Radar Item Page        (前端, 加 Narrative / Bull-Bear / Playbook 卡，独立 surface spec)
       │
       ▼
[Phase 2 候选 — 独立 spec]
  pulse_decision_log + decision_outcomes 表
  OutcomeWorker + Reflector
  past_context loader
  NarrativeBriefWorker
  Playbook 字段类型学 enum 化
```

**Worker 数量净增 0**。**新表净增 0**。Phase 1 改动局限于：
1. `pulse_lab/types` 类型 hard cut
2. `pulse_lab/prompts` prompts 文件化
3. `integrations/openai_agents/tools` 新增 3 个只读 SQL 工具函数（不是 worker）
4. `integrations/openai_agents/pulse_decision_agent_client` 编排重写
5. `pulse_lab/runtime/pulse_candidate_worker` 调新 client
6. `pulse_lab/repositories/pulse_repository` + `pulse_lab/read_models/signal_pulse_service` 字段映射
7. `notifications/services/notification_rules` body 重写
8. GMGN provider description 字段补抽
9. alembic 一个 migration（DROP narrative_type 列 + 改 stage CHECK）

### 4.2 两个角色的职责契约

| 角色 | 输入 | 工具 | 输出形式 | 模型 | 调用形态 |
|---|---|---|---|---|---|
| **Investigator** | route, target, factor_snapshot 摘要, completeness | 3 个核心只读 SQL 工具（详 §4.3）| 全结构化 InvestigationReport（无自由 markdown 字段）| 同 model（qwen3.6）| 1 次 `Runner.run`，turn 上限通过 worker 侧 tool counter 而非 max_turns 控制 |
| **DecisionMaker** | Investigator 完整输出, route, factor_snapshot 摘要 | 1 个 fallback 工具（`get_target_recent_tweets`），用于 Investigator observation 不足时补查 | 全结构化 FinalDecision | 同 model | 1 次 `Runner.run`，max_turns=3 |

**每候选同步 LLM 调用 = Investigator + DecisionMaker = 2 次 Runner.run**（Investigator 内部多 turn 计 Investigator 一次 Runner）。**无 deferred 调用**。

对比当前 3 stage：调用次数从 3 → 2，**总成本同量级**；但 Investigator 含 tool round-trip，预期 input token p95 5K → 12K（含 tool result），latency p95 22s → 50s（仍 < worker 60s timeout）。

### 4.3 Investigator 工具集（3 个，phase 1 最小集）

工具是只读 SQL 函数包装为 `@function_tool`，agent 按 prompt 内 checklist 自行调用。**禁止外部 HTTP**，仅本地 PG。**禁止接 user-input 字符串拼 SQL**，所有参数 typed。

| 工具 | 语义 | 数据源 |
|---|---|---|
| `get_target_recent_tweets` | target 24h 内全部 tweet 原文（按 attribution_weight 排序），每条含 `event_id / author_handle / followers / received_at_ms / text_clean / tweet_url`（从 `events.event_payload_json->>'url'` 提取，supporting_event_ids 校验白名单来源）| `events` + `token_intent_resolutions` |
| `get_target_price_action` | target 在过去 N 小时的 OHLCV + 流动性轨迹 + 当前价/24h 变化/24h volume/holders | `market_ticks` + `asset_market_snapshots` |
| `get_official_token_profile` | GMGN 官方 name / description / twitter / website / created_at 等元数据 | `asset_profiles`（依赖 Task 2 GMGN provider fix description）|

**Phase 2 候选工具**（不在本 spec 范围）：`get_token_holder_distribution / get_kol_call_history / get_peer_narrative_tokens`，依赖额外数据准备（dev 钱包识别、KOL alpha 历史、跨 target narrative 聚合），phase 1 不上。

### 4.4 Tool budget 约束

**KISS 修正**：不用 SDK `max_turns` 作为 tool call 上限（reviewer 指出 1 turn 含多个 parallel tool calls）。

- 在 worker 侧维护 `RunContext.usage.tool_calls_count` 计数器，每个 tool wrapper 共享并自增
- 超过 `pulse_candidate.investigator_max_tool_calls[route]`（默认 cex=3, meme=5）时抛 `ToolBudgetExceeded`，终止 Run
- SDK `max_turns` 单独配，默认 5（覆盖 reasoning + tool + final）
- 单 tool result 大小 ≤ 4KB；总 tool budget ≤ 12KB（5 × 2.4KB 平均）

### 4.5 Pre-LLM Gate 保留

`_factor_completeness` + `hard_blocked` 不动。当前 hard_blockers（`research_only_no_resolved_target / decision_latest_missing / dex_floor_unverified / cohort_insufficient / cohort_all_tied / cohort_no_signal / data_completeness_below_hard_gate`）继续 deterministic 拦截，**不消耗 Investigator 调用**。pre-LLM gate 拒绝的 candidate 直接落 `research_only_gate` 类型 audit row。

---

## 5. 数据契约变更（hard cut，不双写）

### 5.1 Schema 改动总览

| 表 / 列 | 改动 | 理由 |
|---|---|---|
| `pulse_candidates.narrative_type` | **DROP 列** | 1516/1516 = `direct_token` 死字段，被 FinalDecision.narrative_archetype 取代 |
| `pulse_agent_run_steps.stage` 枚举 CHECK | hard cut 改为 `investigator / decision_maker / research_only_gate` | 旧 `analyst / critic / judge` 删除。**用 `NOT VALID` 子句避免触发全表扫描**（reviewer A1 指出 immediate validate 会让 migration 失败） |
| `pulse_candidates.decision_json` JSONB | schema 扩字段（见 §5.2），不需 ALTER COLUMN | 容纳 narrative + bull/bear + playbook |
| `AnalystOpinion / CritiqueReport` 类型 | **DELETE** | 替代为 `InvestigationReport` |
| `FinalDecision` Pydantic | 字段扩展（见 §5.2）| hard cut，schema_version bump 到 `pulse-decision-v2` |
| `asset_profiles.description` | provider fix（不是 schema 改）| GMGN provider 加 description 字段映射 |

**净增表 0；DROP 列 1；ALTER CHECK 1**。Migration downgrade 同样用 `NOT VALID` 保证可逆。

### 5.2 FinalDecision 字段（语义级，非 Pydantic 全签名）

保留（不变）：
- `route`（cex / meme / research_only）
- `recommendation`（high_conviction / trade_candidate / watchlist / ignore / abstain）
- `confidence`（0..1）
- `abstain_reason`（str | null）
- `summary_zh`（短句, 总结）
- `invalidation_conditions`（list[str]）
- `residual_risks`（list[str]）
- `evidence_event_ids`（list[str]）

新增（phase 1）：
- `narrative_archetype: str`（**free-text，phase 1 不锁 enum**；长度 ≤ 20 字符。Phase 2 看 30 天分布后再 enum 化。reviewer B.2 推荐）
- `narrative_thesis_zh: str`（30-300 字符，叙事一段话）
- `bull_view: {strength, thesis_zh, supporting_event_ids}`
- `bear_view: {strength, thesis_zh, supporting_event_ids}`
- `playbook: {watch_signals, exit_triggers, monitoring_horizon, has_playbook}`
  - `watch_signals: list[str]` — 要关注什么事件
  - `exit_triggers: list[str]` — 什么事件出现剧本失效
  - `monitoring_horizon: enum` — `1h / 4h / 24h`
  - `has_playbook: bool` — 二分；recommendation=abstain 时强制 false，watch_signals 和 exit_triggers 必须为空
  - **不引入** `sizing_band / playbook_type 5 enum / key_observation_levels (含 price)`（reviewer B.3 指出过早 + 接近交易指令）

`bull_view.strength` 与 `bear_view.strength` 沿用 4 档 enum `absent / weak / moderate / strong`（向后扩展空间），但 **phase 1 系统消费只用二分**（≠absent vs absent）。grader 和 UI 渲染都按二分处理。

asymmetric 允许：strength=absent 时 thesis 与 supporting_ids 必须为空。`narrative_archetype` 文本为空字符串时允许双 absent。

### 5.3 InvestigationReport 字段（语义级，全结构化）

**KISS 修正：删除 `markdown_report` 自由文本字段**（reviewer A.5 指出与结构化字段必然不一致，让 DecisionMaker 仲裁是反模式）。

- `narrative_archetype_candidate: str`（free-text 同 §5.2）
- `narrative_observation_zh: str`（30-300 字符，叙事观察一段话）
- `bull_observation: {strength, thesis_zh, supporting_event_ids}`（同 BullBearView 形状）
- `bear_observation: {strength, thesis_zh, supporting_event_ids}`
- `data_gaps: list[str]`（Investigator 自己声明哪些事实没查到）

**移除**：`tool_call_summary` 字段不再让模型输出（reviewer B1 指出模型会编造）。改由 worker 从 `RunResult.raw_responses` 提取写到 `pulse_agent_run_steps.input_json.tool_calls`。

注意：Investigator 输出的是 **observation**，不是 recommendation；不输出 confidence / route / recommendation 字段。

### 5.4 Hallucination guard 设计

reviewer B2 指出 v1 设计"supporting_event_ids ⊂ tool result event_ids 并集"在 SDK final_output 模式下技术不可实现（提取深 nested tool result 复杂、每个 tool result key 不一）。

**v2 修正**：每个 tool 返回值遵循统一 Protocol `ToolResult`：
```python
class ToolResult(Protocol):
    data: dict[str, Any]
    contributed_event_ids: list[str]   # 该 tool 调用产生的可引用 event_id 集合
```

worker 维护 `RunContext.contributed_event_ids: set[str]`，每次 tool 调用后并入。Investigator 输出 `supporting_event_ids` 必须 ⊂ `contributed_event_ids ∪ context.evidence_event_ids ∪ context.source_event_ids`。违反则 stage 标 `status=failed`，触发现有 retry 路径。

`get_target_recent_tweets` 是核心工具，返回 tweets 列表时每个 tweet 的 event_id 加入 `contributed_event_ids`，覆盖 90% supporting evidence 来源。

---

## 6. Surface 升级（hard cut）

### 6.1 Notification body 重写为 SurfaceCard

`notification_rules.py:_pulse_body` 整体重写。**删除现有实现**，不保留旧 markdown 模板。新 body 结构（语义级）：

1. **Header**: `${symbol} · {route} · {recommendation} · conf {pct}`
2. **Narrative 段**: `narrative_archetype` 中文标签 + `narrative_thesis_zh`
3. **Bull 段**（strength≠absent 时）: 强度标签 + `thesis_zh` + 证据 deep-link
4. **Bear 段**（strength≠absent 时）: 同 Bull
5. **Playbook 段**（has_playbook=true 时）: watch_signals + exit_triggers + monitoring_horizon
6. **Links 段**: GMGN / X Search / Pulse Detail

整体 body 长度上限 ~1500-2500 字符。

**降级顺序修正**（reviewer D1 指出 v1 顺序反了，Playbook 是最有价值的不能先砍）：
- **始终保**：Header + Recommendation + Playbook + Links
- **先降**：Bull/Bear 段（先 bear 后 bull）
- **次降**：Narrative 段

### 6.2 evidence event_id → tweet URL 映射

reviewer D2 指出 v1 缺设计。本 spec 在 `get_target_recent_tweets` 工具返回每条 tweet 时**已含 `tweet_url`**（从 `events.event_payload_json->>'url'` 提取）。Surface card 渲染时通过 worker 在持久化前把 `evidence_event_ids` JOIN 一次 `events` 表生成 `evidence_event_url_map`，写入 `decision_json.evidence_event_urls`。Surface card 渲染时直接读。

若 `events.event_payload_json` 缺 `url` 字段（数据腐蚀），降级为"显示 @handle 文本，不出 deep link"。

### 6.3 Notification dedup signature 修正

reviewer D3 指出当前 signature hash 整 decision_json 会因 narrative_thesis_zh 自由文本微变导致重复推送，或不更新 signature 让 bull/bear 状态变化不触发。

**v2 修正**：`_pulse_notification_signature` 只 hash **稳定的决策维度**：
- `recommendation`
- `bull_view.strength`
- `bear_view.strength`
- `narrative_archetype`
- `has_playbook`
- 不含任何自由文本（thesis_zh / narrative_thesis_zh / summary_zh）

### 6.4 前端 Signal Pulse Detail + 历史详情兼容

reviewer B2 指出删 stage 名后历史 run（stage ∈ {analyst, critic, judge}）会让 detail 页空白。

**v2 修正**：前端 PulseDetailView 加 legacy 占位卡：
- 老 stage（analyst/critic/judge）渲染为"legacy stage"，显示 stage 名 + status + latency + 简要响应摘要，不做完整结构解析
- 新 stage（investigator/decision_maker）走完整渲染
- 保证 7 天历史 pulse 仍可读

---

## 7. Hard Cut 列表（不保留兼容性代码）

| # | 删除项 | 替代 |
|---|---|---|
| H1 | `pulse_candidates.narrative_type` 列 | FinalDecision.narrative_archetype (decision_json) |
| H2 | `AnalystOpinion / CritiqueReport` Pydantic 类 | `InvestigationReport` |
| H3 | `FinalDecision` v1 字段集合 | 扩字段后 schema_version bump |
| H4 | `pulse_agent_run_steps.stage` 旧枚举 `analyst / critic / judge` | 新枚举 `investigator / decision_maker / research_only_gate` |
| H5 | `pulse_stage_prompts.py` 内 `_ROUTE_FOCUS / _STAGE_FOCUS / pulse_stage_prompt` 函数 | `domains/pulse_lab/prompts/{investigator,decision_maker}.md` 文件化 |
| H6 | `pulse_decision_agent_client.py` 的 `_run_stage` 三阶段编排逻辑 | 新 `run_investigation_then_decision` 两 stage 编排 |
| H7 | `notification_rules._pulse_body` 现有实现 | 新 SurfaceCard 渲染器 |
| H8 | Critic veto 路径 + `pulse_agent_runs.outcome='abstain_critic_veto'` 历史值消费 | bull/bear 在 Investigator 内部消化；enum 历史值保留作只读，新写禁用 |
| H9 | `pulse_agent_eval_cases` v1 grader rules | v2 grader rules（5 项，见 §10）|
| H10 | 前端 `narrative_type` 字段消费 + analyst/critic/judge 硬编码渲染分支 | `narrative_archetype` (free-text) + legacy 占位卡 + investigator/decision_maker 渲染 |

**所有 H 项要求一次性 hard cut**：单 PR 合入、无 dual-write、无 feature flag、无新旧并存灰度。回滚靠 git revert + alembic downgrade（plan 阶段明确停服务→downgrade→revert→启服务的顺序）。

**v2 新增删除项 H8/H9/H10** 是 reviewer 链路分析后发现的隐性兼容代码，必须同 PR 一并删。

---

## 8. 非目标（明确不做）

- ❌ 不引入 LangGraph / CrewAI / autogen
- ❌ 不引入 multi-provider 自动 fallback / multi-model 分层
- ❌ 不引入 risk persona 多角色辩论
- ❌ 不引入 Bull/Bear 多轮 stage 拆分
- ❌ 不引入下单 / 仓位 / 止损 / 目标价等执行性字段
- ❌ **不引入 outcome 回路 / Reflector / past_context loader / decision_outcomes 表 / pulse_decision_log 独立表**（phase 2 独立 spec）
- ❌ **不引入 NarrativeBriefWorker / narrative_briefs 表 / /narrative-brief endpoint**（phase 2 独立 spec；Investigator 工具直接查源表）
- ❌ **不引入 sizing_band / key_observation_levels / playbook_type 5 enum**（phase 2 数据驱动后决定）
- ❌ **不锁 narrative_archetype enum**（phase 1 free-text，phase 2 enum 化）
- ❌ 不破坏 Kappa/CQRS：events 仍是 only truth
- ❌ 不破坏单冷写：现有 14 worker 边界全部保留
- ❌ 不引入 pgvector / 向量检索
- ❌ 不保留任何 v1 ↔ v2 兼容层、dual-write、enum 双枚举
- ❌ 不动 `pulse_status` 现有展示语义
- ❌ 不动 enrichment / handle_summary 两个其它 agent

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Investigator tool call 失控导致 token 与 latency 暴涨 | 高 | worker 侧 `ToolBudgetExceeded` 硬上限（§4.4）；单 tool result ≤ 4KB；总 budget ≤ 12KB |
| Investigator 输出 hallucinate event_id | 高 | §5.4 `ToolResult.contributed_event_ids` Protocol + worker 写入前 set 包含检查；违反 → stage failed + retry |
| 删 critic 后失去 high_conviction 上限约束 | 中 | FinalDecision 验证器硬约束：`recommendation=high_conviction` 要求 `bull/bear.strength ∈ ("moderate","strong")` AND `evidence_event_ids ≥ 3` |
| llama.cpp GBNF 不支持 `min_length / max_length` | 中 | length 约束**只在 `@field_validator`**，不依赖 grammar；prompt 文本内强约束；InstructorSafetyNet retry 上限 plan 阶段写明 |
| 老 audit 行 stage ∈ 旧 enum 让历史详情空白 | 中 | §6.4 前端 legacy 占位卡 |
| Surface body 字符上限触碰 PushDeer / Telegram 限制 | 中 | §6.1 降级顺序明确（先 Bear 后 Bull 后 Narrative，始终保 Playbook） |
| 单 PR 合入面过大 | 中 | plan 阶段拆 10 个可独立 review 的子任务；合入次序约束 hard cut；revert 走停服务→downgrade→revert→启服务四步 |
| DecisionMaker 失去兜底能力 → Investigator 错误锚定 | 中 | DecisionMaker 接 1 个 fallback 工具 `get_target_recent_tweets`（§4.2），max_turns=3，在 InvestigationReport observation 不足时补查 |
| GMGN provider description 5359 行老数据不 backfill | 中 | Investigator 工具 `get_official_token_profile` 处理 description=null 情况；plan 阶段决定是否加 admin 命令强制 refresh |
| `_FORBIDDEN_EXECUTION_RE` 误伤新字段名 | 低 | 因 v2 删了 sizing_band / playbook_type enum 值 / key_observation_levels，候选字段值大幅缩减；plan 阶段 regex 反测 |
| 第一波部署 narrative_archetype free-text 杂乱无序 | 低 | 接受作为 phase 1 学习成本；phase 2 spec 抽样 30 天数据后 enum 化 |

---

## 10. 验收（falsifiable）

### 10.1 架构形态验收（PR 合入即验证）

| ID | 验收 |
|---|---|
| F1 | `pulse_agent_run_steps.stage` 不再出现 `analyst / critic / judge`；新值仅 `investigator / decision_maker / research_only_gate` |
| F2 | Investigator 每个 ok step 的 `input_json.tool_calls` 字段（worker 写入）非空且至少 1 个工具被调用（hard_blocked 除外）|
| F3 | FinalDecision 完整含 `narrative_archetype / narrative_thesis_zh / bull_view / bear_view / playbook` 五块字段 |
| F4 | API `/api/signal-lab/pulse/<id>` 返回 decision 含新 5 块字段 |
| F5 | `notification_rules._pulse_body` 输出 body 含 Narrative / Bull / Bear / Playbook 至少 4 段（asymmetric absent 段可缺）|
| F6 | `pulse_candidates.narrative_type` 列已 DROP |
| F7 | `AnalystOpinion / CritiqueReport` 类不再被 import |
| F8 | 老 stage 行（analyst/critic/judge）在前端 PulseDetailView 渲染为 legacy 占位卡，无 JS error |

### 10.2 质量验收（7 天 soft launch 后）

| ID | 验收 metric |
|---|---|
| Q1 | 24h `trade_candidate + high_conviction` 决策占比从 1.1% → 8-15%（吃到 tool + bull/bear 红利）|
| Q2 | `abstain` 占比从 95% → 50-65%（更均衡）；abstain_reason 不允许单一 reason >40% |
| Q3 | `high_conviction` 占比 < 15%（不允许新架构倒向另一极端）|
| Q4 | DecisionMaker 输出含非 absent bull_view 与非 absent bear_view 同时存在的比例 ≥ 40% |
| Q5 | Investigator 平均 tool call 数 2-4 次（不滥用也不为零） |
| Q6 | 单 candidate 总 token p95：input ≤ 18K，output ≤ 2.5K |
| Q7 | 单 candidate 总同步 latency p95 ≤ 60s |
| Q8 | Notification body 平均长度从 ~400 → ~1200 字符；用户主观评估"看推送就知道该做什么"|
| Q9 | 7 天后 narrative_archetype free-text 取值分布抽样 200 个，输入 phase 2 enum 化决策 |

### 10.3 v1 中 Q5/Q6/R1/R2/R3 因依赖 outcome 回路全部移到 phase 2 spec 验收

---

## 11. 演进路径

### 11.1 Phase 1（本 spec）— 一次性 hard cut

依赖图：
```
Phase 0 (前置, 不在本 spec)：
  unified-agent-worker-runtime-cn §5.1 M1 schema hard fix 必须先合入

Phase 1 (本 spec)：
  1. Provider fix (asset_profiles.description)
  2. Schema migration (DROP narrative_type + stage CHECK 改, NOT VALID)
  3. Pydantic types hard cut (DELETE v1, NEW InvestigationReport, EXTEND FinalDecision)
  4. Prompts 文件化
  5. 3 个 Investigator tools
  6. Agent client 两 stage 重写 (+ tool counter + hallucination guard + DecisionMaker fallback tool)
  7. pulse_candidate_worker 接新 client
  8. signal_pulse_service / pulse_repository 字段映射
  9. SurfaceCard notification 重写
  10. eval grader v2 (5 项)
  全部 10 块同一 release，git revert 整体可回滚
```

### 11.2 Phase 2 候选（独立 specs，顺序无强约束）

- **2026-XX-pulse-outcome-reflection-spec**：pulse_decision_log + decision_outcomes 表 + OutcomeWorker + Reflector + past_context loader。需要 phase 1 跑 14 天积累足够 candidate 样本后启动。
- **2026-XX-pulse-narrative-brief-spec**：NarrativeBriefWorker + narrative_briefs 表 + /narrative-brief endpoint。先看 phase 1 Investigator 工具是否覆盖足够，再决定是否预聚合。
- **2026-XX-pulse-playbook-typology-spec**：抽样 phase 1 watch_signals/exit_triggers 实际分布后，决定是否引入 playbook_type / sizing_band enum。
- **2026-XX-pulse-narrative-archetype-enum-spec**：抽样 phase 1 narrative_archetype free-text 30 天分布后 enum 化。
- **2026-XX-pulse-investigator-tools-expansion**：根据 phase 1 使用数据决定加哪些 tool（如 KOL history / peer comparison / holder distribution）。
- **2026-XX-pulse-token-radar-item-ui-spec**：前端 Token Radar item 页加 3 张卡。

---

## 12. Open Questions（plan 阶段必须锁定）

v2 收敛大量 OQ：

1. **Investigator tool call 上限**：默认 cex=3, meme=5。plan 阶段抽样估算实际分布锁定。
2. **DecisionMaker fallback tool 是否启用**：默认启用 `get_target_recent_tweets`，max_turns=3。plan 阶段验证 InvestigationReport observation 充分性后决定是否禁用。
3. **prompt 文件命名**：`prompts/{investigator,decision_maker}.md`（单文件 route 内联分支）vs `prompts/{role}_{route}.md`（多文件）。推荐前者。plan 阶段定。
4. **GMGN provider description backfill**：默认不 backfill，新拉的 profile 进库即填。plan 阶段决定是否加 admin 命令强制 refresh 现有 5359 行。
5. **`_FORBIDDEN_EXECUTION_RE` 反测候选**：playbook 字段已大幅简化（无价格、无 sizing 等级），但仍需对 `narrative_archetype` 候选值 + `watch_signals / exit_triggers` 文本走一次 regex 反测；plan 阶段做并记录。
6. **`pulse_agent_runs.outcome` enum 中 `abstain_critic_veto` 处置**：保留作历史只读 vs DROP CHECK 重建。推荐保留（新写禁用，老行可读）。plan 阶段最终定。

v1 的 OQ-3（past_context 窗口）、OQ-4（log retention）、OQ-5（OutcomeWorker 节奏）随 outcome 回路移到 phase 2 spec。

---

## 13. 决策日志

| 决策 | 理由 |
|---|---|
| 角色数从 v1 三角色（Investigator/DecisionMaker/Reflector）收敛到 v2 二角色 | reviewer P2-1：outcome 回路 phase 1 无法验证 ROI（1h horizon 信号噪声大、前 7-14 天 reflection 空），移到 phase 2 让 phase 1 收敛 30% 代码 |
| 删除 NarrativeBriefWorker / narrative_briefs 表 / endpoint | reviewer P2-2：与 spec §2.1 自相矛盾（"agent 基于事实追问"≠预聚合 snapshot）；Investigator 工具 `get_target_recent_tweets` 已直接看原始 tweets |
| Playbook 字段降级（删 sizing_band / key_observation_levels / playbook_type 5 enum，留 watch_signals + exit_triggers + monitoring_horizon + has_playbook 二分）| reviewer P2-3：sizing 5 档无数据必 mode collapse；价格字段接近交易指令；5 enum 无数据支撑 phase 2 数据驱动再 enum |
| 删除 InvestigationReport.markdown_report | reviewer A.5 / B.4：markdown + 结构化字段必然不一致；让 DecisionMaker 仲裁是反模式；结构化字段已覆盖 bull/bear observation |
| Investigator 工具 6 → 3 | reviewer A.3：phase 1 验证"能调工具"足够；KOL history / peer / holder distribution 依赖额外数据准备且 ROI 未验证 |
| narrative_archetype phase 1 free-text 不锁 enum | reviewer B.2：7 enum 必漏（airdrop_chase / fork / dev_revival 等），二次 alembic 改 CHECK 成本高；phase 2 数据驱动 enum 化 |
| BullBearView.strength 保留 4 档 enum 但 phase 1 系统只用二分 | KISS 但保留未来扩展空间；改 4 档→2 档需要后续二次 schema migration，保留 4 档 phase 2 直接消费 |
| DecisionMaker 接 1 个 fallback tool（`get_target_recent_tweets`），max_turns=3 | reviewer B.4：DecisionMaker tools=[] 让所有错锚定 Investigator；1 个 fallback tool 兜底成本可控 |
| Tool budget 控制改为 worker 侧 counter，不用 SDK `max_turns` | reviewer B.6：max_turns 与 tool call 数量不等价（1 turn 含多 parallel call）；worker 侧 counter 才是真硬约束 |
| InvestigationReport 删 `tool_call_summary` 字段，改由 worker 从 RunResult 提取 | reviewer B.1：让模型 echo 元数据浪费 token、qwen3.6 会乱填、为 hallucination guard 反向作弊 |
| Hallucination guard 改为 ToolResult Protocol + worker 维护 contributed_event_ids set | reviewer B.2：v1 设计"⊂ tool result event_ids 并集"在 SDK final_output 下技术不可实现；Protocol 化让 worker 可 deterministic 提取 |
| Surface body 降级顺序：先 Bear 后 Bull 后 Narrative，始终保 Playbook | reviewer D.1：Playbook 是用户最需要的执行指引；v1 顺序反了等于回到 C3 缺陷 |
| evidence event_id → tweet URL 映射在 worker 持久化前生成 evidence_event_urls 写入 decision_json | reviewer D.2：deep-link 不能在 surface render 时才查；提前生成保证渲染 deterministic |
| Notification signature 只 hash 稳定决策维度（不含自由文本）| reviewer D.3：含自由文本会因微变重复推送；纯结构维度让 bull/bear 状态变化触发刷新但文字微调不刷屏 |
| 老 stage audit 行渲染为 legacy 占位卡 | reviewer B.2：用户打开历史 pulse 不能空白；占位卡显示 stage 名 + status + latency 但不解析 response_json |
| 不增任何新表（pulse_candidates 已是决策 ledger）| reviewer A.1：v1 引入 pulse_decision_log 是为 outcome reflection 服务，砍掉 outcome 后多余 |
| 不增任何新 worker | 删 OutcomeWorker（outcome 移 phase 2）+ 删 NarrativeBriefWorker（工具替代）= 净增 0 worker |
| 保留 openai-agents-python 不迁 LangGraph | 用户 feedback-agent-harness-choice 决策；顺序 stage 足够 |
| 单 provider qwen3.6 不引入 multi-provider | 用户 2026-05-16 决策 |
| 单一 hard cut 而非并存灰度 | 用户偏好 hard cut；并存灰度引入双 schema / 双 prompt 维护负担 |
| 不动 Kappa/CQRS、不动 14 个 worker 边界 | 项目核心架构原则 |
| 不动 enrichment / handle_summary agent | 独立失败模式与升级路径；独立 spec 处理 |
