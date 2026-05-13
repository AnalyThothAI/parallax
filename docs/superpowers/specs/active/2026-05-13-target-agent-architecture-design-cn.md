# Target Agent Architecture — 决策层顶层设计 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-13
**Owner**: Claude with Qinghuan
**Scope**: 决策层（agent split + 可靠性 + harness 用法）顶层架构 + 分阶段路线图。**不**包含数据 pipeline 内部实现、prompt 文本细节、phase 2 交易/风控/仓位。
**Approach 选定**: B 平衡 — 5-stage 决策流水线 + Light 可靠性 + 数据契约 + phase 1 接口预留
**Harness**: 保留 openai-agents-python（不迁 LangGraph），顺序 `Runner.run` 替代 handoff
**Trading 目标**: phase 0 看盘/研究 → 6-9 月后 phase 1 半自动决策支持（phase 2 仅 roadmap 不预留 schema）

**Related**:
- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`
- `docs/superpowers/specs/active/2026-05-13-token-radar-pipeline-overcomplexity-audit-cn.md`
- `docs/superpowers/plans/active/2026-05-12-signal-lab-pulse-decision-facts-hard-cut-plan-cn.md`
- `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md`
- 外部参考：TauricResearch/TradingAgents（架构借鉴），openai/openai-agents-python（底座）

---

## 一句话结论

把当前**单 agent + max_turns=3 + tools=[]** 的 pulse pipeline 拆成 **2 条 asset-class-aware route × 3 stage (Analyst → Critic → Judge)**，前置一个纯函数 EventRouter + 数据完整度 gate；新增 `pulse_agent_run_steps` 表存完整 prompt/response 替代 sha256 hash；置信度从 JSONB 提到一等公民列；Critic 阶段专责"数据缺失/证据薄弱"的反驳并只能下调不能翻案。Harness 保留 openai-agents-python，顺序 `Runner.run()` 替代 handoff（pipeline 静态用 handoff 是 over-engineering）。Phase 0b 实施 ~3-4 周，phase 1 outcome collector / self-consistency / Reflector 仅留接口不写代码。

## 1. 背景与问题陈述

### 1.1 现状（基于代码审计）

| 维度 | 现状定位 |
|---|---|
| Agent 数 | 1 个 LLM agent（`pulse_recommendation_agent_client.py:128`），`max_turns=3`，`tools=[]`，单调用 |
| Asset-class 差异化 | 仅 `_gates()` 一个 DEX 分支（`factor_snapshot.py:326`）；prompt 对 CEX 和 meme 一视同仁 |
| 置信度 | 埋在 `agent_recommendation_json` JSONB，前端无法直接 filter |
| 审计 | `pulse_agent_runs.request_json = {"context_hash": sha256}`，prompt 真实内容**无法回放**（`pulse_candidate_worker.py:426`） |
| Cross-check | 无；幻觉/数据缺失无对抗机制 |
| Worker 编排 | 60s poll loop（`pulse_candidate_worker.py:135`），DB job queue |

### 1.2 症状

- 最近 27/27 candidate **全部** 为 `trade_candidate / high_conviction`（symbol-lab-pulse spec 实测）
- NICHEBABY (mcap=16,691 USD)、LAB 等按规则应被 floor 拒绝却未被拒（market-data-pipeline-gap spec）
- 无 prompt replay → 无法 debug 单次错判 → 无法迭代 prompt → 不可能可靠

### 1.3 根因分层

**这是关键诊断点**：症状叙事是"agent 不可靠"，但根因不在 agent 模型选错或 harness 选错。根因分两层：

- **数据层（active spec/plan 处理）**：`_market()` 硬编码 None、`_gates()` 对 NULL `continue`、cohort percentile 把"全员都坏"洗成 50、`LivePriceGateway` 默认关闭
- **决策层（本 spec 处理）**：单 agent 无 cross-check、置信度无门控、CEX 和 meme 共 prompt、无 replay 不能迭代、abstain 语义缺失

**先后顺序**：先把数据层修齐（phase 0a，落地 3 个 active plan），再做决策层改造（phase 0b，本 spec）。否则更聪明的 agent 灌进 garbage 也只会输出 garbage。

### 1.4 外部参考要点（不抄全套）

- **TradingAgents**（TauricResearch）：4 层 9+ agent / Bull-Bear 辩论 / Deferred Reflection vs SPY benchmark / LangGraph + Pydantic。值得借鉴：**对抗作 cross-check**、**事后 grounding**、**结构化输出**。不抄：9 agent / 30-120s 延迟 / 美股专属数据层 / 无置信度门控。
- **agency-agents**（msitarzewski）：本质是 Markdown persona 库（144 文件，96% Shell 脚本），无 runtime、无状态、无可观测性，有 prompt-injection issue。**不**作为 harness 底座；个别 prompt 文本可作素材。

## 2. 目标与非目标

### 2.1 目标（phase 0b 范围）

1. 决策层按 asset class 拆 route：CEX route 和 meme route 各自独立 prompt / schema / gate
2. 每条 route 内 3-stage cross-check：Analyst → Critic → Judge
3. 显式 `confidence ∈ [0,1]` + `abstain_reason` 一等公民
4. 完整 prompt / response replay log（替代 sha256 hash）
5. 数据完整度 gate（pre-LLM）省 token 并杜绝"无数据下结论"
6. 落地后 high_conviction 比例 < 15%（vs 现状 100%），abstain 5-30%，error < 5%

### 2.2 非目标（明确**不**做）

- 数据 pipeline 内部实现（3 个 active plan 的事）
- prompt 文本细节（落到 implementation plan）
- 仓位管理 / 风控预算 / 实际下单接口（phase 2）
- Backtest 框架 / 离线 eval harness（phase 1+）
- 多 LLM provider 投票（短期只用 OpenAI）
- 主动学习 / RLHF / fine-tuning
- 实时 calibration（采集和使用都推到 phase 1）
- 内部多次 sampling（self-consistency 仅留接口，phase 1 才打开）
- 迁 LangGraph / autogen / crewai 等其他 framework
- 在 schema 层预留 phase 2 字段（KISS：phase 2 才 `ALTER TABLE`）

## 3. 顶层架构

### 3.1 拓扑

```
GMGN WS → CollectorService → events
  ↓
SocialEventExtractionAgent          ← 现状保留，本 spec 不动
  ↓
social_event_extractions
  ↓
PulseDispatchWorker (60s loop)      ← 沿用现有 PulseCandidateWorker，仅改编排
  ↓
pulse_agent_jobs
  ↓
────────────────────────────────────
[新] routing.py (纯函数，非 LLM)
      route_event()              ← 按 target_market_type 路由
      compute_completeness()     ← 完整度 < hard gate → abstain，不调 LLM
   ↓                 ↓
CEX route         Meme route
1. CexAnalyst     1. MemeAnalyst
2. CexCritic      2. MemeCritic     ← 反驳：数据完整度 + 证据强度
3. CexJudge       3. MemeJudge
────────────────────────────────────
  ↓
FinalDecision (增强 Pydantic schema)
  ↓
pulse_candidates  +  [新] pulse_agent_run_steps
  ↓
WS publish / GET /api/signal-lab/pulse
```

### 3.2 与现状的关键差异

| 维度 | 现状 | 本设计 |
|---|---|---|
| Agent 数 | 1（`pulse_recommendation_agent_client.py:128`） | 6 LLM 阶段 = 2 route × 3 stage（EventRouter / CompletenessGate 纯函数） |
| Asset-class 差异化 | 仅 `_gates()` 一个 DEX 分支 | route 完全独立：prompt / schema / gate / abstain 规则 |
| 置信度 | 埋在 `agent_recommendation_json` JSONB | 一等公民列 `pulse_candidates.confidence FLOAT NOT NULL` |
| 审计 | `request_json` 仅 sha256 hash | `pulse_agent_run_steps` 存每 stage 完整 prompt / response / tokens / latency |
| Cross-check | 无 | Critic 必填 `weaknesses` + `confidence_ceiling` |
| Abstain 语义 | 隐式（无候选时不写 row） | 显式：`pulse_candidates.pulse_status = 'abstain'` + `abstain_reason` |

### 3.3 边界（**不**动的部分）

- `SocialEventExtractionAgent` / `enrichment_worker` 完全不改——本 spec 不扩散
- 数据 pipeline 内部实现交给 active plan；本 spec 只对它**提契约**（§4）
- `pulse_candidates.score_band` / WS 协议向前兼容——只追加字段、不删旧字段
- `pulse_agent_runs.request_json` 退役（hard cut，hash 字段没人读）

### 3.4 命名

- 6 个 LLM stage：`CexAnalyst` / `CexCritic` / `CexJudge` / `MemeAnalyst` / `MemeCritic` / `MemeJudge`
- 共享 base prompt 模板 + 各自 asset-class-specific 节
- 统一 Pydantic schema：`AnalystOpinion` / `CritiqueReport` / `FinalDecision`，差异通过 `route ∈ {"cex","meme"}` 字段体现

## 4. 数据契约

### 4.1 为什么需要

数据契约的作用是**让数据 pipeline 知道决策层期望什么**。不修内部实现（那是 active spec 的事），它定接口。没契约就出现"数据层认为修完了、agent 拿到还是错"——这就是当前 27/27 false high_conviction 的真正结构性病灶。

### 4.2 DEX / meme route 必填字段

| 字段 | 类型 | NOT NULL | Freshness SLO |
|---|---|---|---|
| `holders` | int | ✓ | ≤ 5 min |
| `liquidity_usd` | decimal > 0 | ✓ | ≤ 5 min |
| `market_cap_usd` | decimal > 0 | ✓ | ≤ 5 min |
| `volume_24h_usd` | decimal ≥ 0 | ✓ | ≤ 5 min |
| `price_usd` | decimal > 0 | ✓ | ≤ 60 s |
| `asset_age_seconds` | int | ✓ | n/a |
| `dex_pair_address` + `chain` | str | ✓ | n/a |
| `dev_holdings_pct` / `top10_holders_pct` | decimal ∈ [0,1] | optional | ≤ 30 min |

### 4.3 CEX route 必填字段

| 字段 | NOT NULL | Freshness SLO |
|---|---|---|
| `price_usd` | ✓ | ≤ 30 s |
| `volume_24h_usd` | ✓ | ≤ 5 min |
| `venue_id` + `pair_symbol` | ✓ | n/a |
| `market_cap_usd` | ✗（CEX bluechip 不可靠） | ≤ 1 h |
| `open_interest_usd` / `funding_rate` | optional (perp) | ≤ 5 min / 1 h |

### 4.4 Trace 格式（两 route 共用）

`factor_snapshot.market` 中每个数值字段展开为：

```json
{
  "holders": {
    "value": 1234,
    "source_provider": "gmgn",
    "observed_at": "2026-05-13T14:30:12Z",
    "observation_id": "obs:gmgn:..."
  }
}
```

用途：Critic 可以引用具体 `observation_id` 反驳；replay 时可重建当时输入。

### 4.5 完整度评分

`data_completeness ∈ [0,1]` = NOT NULL 必填字段中 freshness 在 SLO 内的比例。

按 route 配置两档阈值（meme 数据天然缺，宽松；CEX 严格）：

| Route | Hard gate（< 此值 → abstain，不调 LLM） | Soft warning（< 此值 → Critic prompt 加压） |
|---|---|---|
| meme | 0.6 | 0.8 |
| cex | 0.8 | 0.95 |

`compute_completeness` 在调 LLM **之前**计算 `data_completeness`，PulseDispatchWorker 按上表分支。

### 4.6 与现有 active spec 的耦合（验收）

本 spec **不**重写数据 pipeline，但给三个 active plan 加一条**从下游需求倒推的验收**：

> 落地后，在 `trade_candidate eligible=True` 这批样本上：
> - meme route 上 `data_completeness ≥ 0.6` 占比 ≥ **80%**
> - cex route 上 `data_completeness ≥ 0.8` 占比 ≥ **95%**
>
> 不满足则 active plan 视为未达验收。

## 5. 决策层 stage-by-stage 设计

### 5.1 共用 Pydantic schema（KISS 后版本）

```python
class AnalystOpinion(BaseModel):
    route: Literal["cex", "meme"]
    summary_zh: str
    evidence: list[str]                # 自由文本，可内嵌 obs:... 引用
    recommendation: Literal["trade_candidate", "watchlist", "ignore"]
    confidence: float                  # ∈ [0,1]

class CritiqueReport(BaseModel):
    weaknesses: list[str]              # 合并 bullish_holes / bearish_holes
    confidence_ceiling: float          # ∈ [0,1]
    should_abstain: bool

class FinalDecision(BaseModel):
    route: Literal["cex", "meme"]
    recommendation: Literal["high_conviction", "trade_candidate",
                            "watchlist", "ignore", "abstain"]
    confidence: float
    abstain_reason: str | None         # 仅 abstain 时填
    summary_zh: str
    invalidation_conditions: list[str] # 何时翻案
    residual_risks: list[str]
    evidence_event_ids: list[str]      # 沿用现有字段供前端
```

KISS 取舍：丢掉 `class_specific_evidence: dict`（自由 dict 难约束）、丢掉单独 `Evidence` 类型（list[str] 内嵌 obs 即可）、丢掉 phase 2 字段（到时再 ALTER）。

### 5.2 Stage 矩阵

| Stage | 输入 | 输出 | 关键约束 |
|---|---|---|---|
| **Analyst** (Cex/Meme) | `factor_snapshot` + `data_completeness` + `missing_fields` + 同 chain 同 asset 24h 历史 | `AnalystOpinion` | **Prompt 强制**："若 NOT NULL 必填字段缺，`recommendation` 必须是 `ignore` 或 `watchlist`，禁止 `trade_candidate`" |
| **Critic** (Cex/Meme) | `AnalystOpinion` + `factor_snapshot` + `missing_fields` | `CritiqueReport` | **Critic 不能反向推翻 Analyst，只能下调置信度** —— 它是约束而非二审。`confidence_ceiling` 是 Judge 计算 `confidence` 的上限 |
| **Judge** (Cex/Meme) | `AnalystOpinion` + `CritiqueReport` | `FinalDecision` | `confidence = min(analyst.confidence, critic.ceiling)`；`critic.should_abstain → recommendation="abstain"`；Judge **必须**给 `invalidation_conditions` 和 `residual_risks`（可解释性强约束） |

### 5.3 Confidence → recommendation 映射

```
confidence ∈ [0.00, 0.40)  → ignore
            [0.40, 0.55)   → watchlist
            [0.55, 0.75)   → trade_candidate
            [0.75, 1.00]   → high_conviction
should_abstain = True 或 data_completeness < hard gate → abstain
```

`high_conviction` 阈值故意设到 0.75 而非 0.5——当前 27/27 全 high_conviction 的根因之一就是没有阈值梯度，全堆在最高档。

### 5.4 Route-specific prompt 要点（"勘察清单"，prompt 全文在 implementation plan）

**CEX Analyst / Critic 必查**：
- venue 集中度（是不是单交易所做市）
- funding rate / OI 是否与同期 BTC funding 同向
- 是否把 listing pump 当 fundamentals
- 时间尺度：hours-days，**禁止做分钟级判断**

**Meme Analyst / Critic 必查**：
- `dev_holdings_pct` 缺失时**禁止**基于 holders 数推 rug 风险
- `asset_age_seconds < 3600` 时 cohort signal 默认不可靠（pool 太新无 baseline）
- Twitter 单 KOL 无多源 confirm 时压 ceiling ≤ 0.5
- 时间尺度：minutes-hours

### 5.5 与现状的具体替换

| 现状 | 替换为 |
|---|---|
| `pulse_recommendation_agent_client.py:128` 单 client | 拆 6 个 client（共享 `make_stage_agent` factory） |
| `PulseRecommendationOutputSchema`（埋 confidence） | 拆 `AnalystOpinion` / `CritiqueReport` / `FinalDecision` |
| `pulse_candidates.agent_recommendation_json` | 同 + `pulse_candidates.confidence` 一等公民列 + `pulse_candidates.route` 列 |
| 无 critic 反驳 | Critic 必填 `weaknesses` + `confidence_ceiling` |
| `score_band` 直接由 score 算 | `score_band` 由 `recommendation` enum 映射，**和 confidence 阈值绑定** |

## 6. 可靠性层

按 Approach B：phase 0 实施 **Light**，phase 1 入口仅预留接口。

### 6.1 Phase 0 · Light（实施）

#### 6.1.1 完整 replay log（最重要的一刀）

新增表替换 `pulse_agent_runs.request_json = {"context_hash": ...}`：

```sql
CREATE TABLE pulse_agent_run_steps (
  id              BIGSERIAL PRIMARY KEY,
  run_id          UUID NOT NULL REFERENCES pulse_agent_runs(id) ON DELETE CASCADE,
  stage           TEXT NOT NULL CHECK (stage IN ('analyst','critic','judge')),
  route           TEXT NOT NULL CHECK (route IN ('cex','meme')),
  model_id        TEXT NOT NULL,
  prompt          TEXT NOT NULL,        -- 完整 prompt，不再 hash
  response_json   JSONB NOT NULL,       -- 完整结构化 output
  input_tokens    INT,
  output_tokens   INT,
  latency_ms      INT,
  status          TEXT NOT NULL CHECK (status IN ('ok','failed','timeout')),
  error_text      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, stage)
);
CREATE INDEX idx_pulse_agent_run_steps_run_id ON pulse_agent_run_steps(run_id);
```

第一性理由：debug 不出"为啥 NICHEBABY 被判 high_conviction"就是因为 prompt 不可重建。**没有 replay = 不可能迭代 prompt = 不可能可靠**。

#### 6.1.2 显式 confidence + abstain

- `pulse_candidates.confidence FLOAT NOT NULL`（从 JSONB 提到一等公民列）
- `pulse_candidates.route TEXT NOT NULL CHECK (route IN ('cex','meme'))`
- `pulse_candidates.pulse_status` 枚举加 `'abstain'`
- `pulse_candidates.abstain_reason TEXT NULL`
- `pulse_agent_runs.outcome` 枚举加 `'abstain_insufficient_data'` / `'abstain_critic_veto'` / `'error'`
- 前端 default filter 不显示 abstain，但**库里保留**——后续 calibration 的样本

### 6.2 Phase 1 · Medium（仅说明，不实施，不在本 spec schema 中预留）

待 phase 1 入口条件满足后，新 spec 处理：
- `OutcomeCollectorWorker` + `pulse_decision_outcomes` 表 → 1h / 24h 价格回填
- `PulseDispatchWorker.sample_n > 1` → 并发 N 次同 route，aggregate（mean confidence、mode recommendation、方差 > 0.2 强降 watchlist）
- Reflector：读历史 outcomes，按 `(route, recommendation, confidence_band)` 算实际命中率，输出 markdown → 下次 prompt 注入

### 6.3 KISS 边界（明确**不**做）

- 多 LLM provider 投票
- 实时 calibration
- 主动学习 / fine-tuning / RLHF
- 跨 asset 的 cohort-level reflection（先单 asset 闭环跑稳）
- 在 phase 0 预留 phase 1/2 schema 字段（KISS：到时 `ALTER TABLE`）

## 7. Harness 落地（openai-agents-python 内）

### 7.1 核心选择：顺序 `Runner.run()`，不用 handoff

openai-agents-python 的 `handoff` 为"agent 自决定下一步给谁"设计（dynamic）。我们的 pipeline 是**静态 5 stage 固定顺序**——用 handoff 是 over-engineering。

KISS 路径：每个 LLM stage = 一个 `Agent` + 一次 `Runner.run(..., max_turns=1)`，stage 之间用普通 Python 顺序串。`EventRouter` / `CompletenessGate` 是纯函数，连 Agent 都不是。

### 7.2 代码骨架

```python
# pulse_stages/shared.py
from agents import Agent
from pydantic import BaseModel

def make_stage_agent(name: str, instructions_path: str,
                      output_type: type[BaseModel]) -> Agent:
    return Agent(
        name=name,
        instructions=load_prompt(instructions_path),
        output_type=output_type,
        tools=[],
    )

# pulse_stages/analyst.py
cex_analyst   = make_stage_agent("CexAnalyst",  "cex_analyst.md",  AnalystOpinion)
meme_analyst  = make_stage_agent("MemeAnalyst", "meme_analyst.md", AnalystOpinion)

# 同理 critic.py / judge.py 各 2 个 Agent

@dataclass(frozen=True)
class RoutePipeline:
    analyst: Agent
    critic:  Agent
    judge:   Agent

PIPELINES: dict[str, RoutePipeline] = {
    "cex":  RoutePipeline(cex_analyst,  cex_critic,  cex_judge),
    "meme": RoutePipeline(meme_analyst, meme_critic, meme_judge),
}
```

### 7.3 PulseDispatchWorker（沿用 `PulseCandidateWorker`，仅改 `process_job`）

```python
async def process_job(self, job: PulseAgentJob) -> None:
    snapshot   = await self._load_factor_snapshot(job.context_hash)
    route      = route_event(snapshot)                          # 纯函数
    completeness, missing = compute_completeness(snapshot, route)
    run_id     = await self._create_run(job.id, route)

    if completeness < GATE_HARD[route]:                         # meme 0.6 / cex 0.8
        await self._write_abstain(run_id, "insufficient_data", missing)
        return

    pl = PIPELINES[route]

    a_in  = build_analyst_input(snapshot, missing, completeness)
    a_out = await self._run_stage_with_retry(pl.analyst, a_in,
                                              run_id, "analyst", route)
    if a_out is None:
        return                                                  # error 已写库

    c_in  = build_critic_input(a_out.final_output, snapshot, missing)
    c_out = await self._run_stage_with_retry(pl.critic, c_in,
                                              run_id, "critic", route)
    if c_out is None:
        return

    if c_out.final_output.should_abstain:
        await self._write_abstain(run_id, "critic_veto",
                                  c_out.final_output.weaknesses)
        return

    j_in  = build_judge_input(a_out.final_output, c_out.final_output)
    j_out = await self._run_stage_with_retry(pl.judge, j_in,
                                              run_id, "judge", route)
    if j_out is None:
        return

    await self._upsert_pulse_candidate(run_id, j_out.final_output)
```

### 7.4 错误处理 + 重试

- 每 stage 30s timeout
- `_run_stage_with_retry` 实现 `max_retry=2` + 指数退避 **2s / 8s / 30s**
- 重试期间不切 model（保持可重现）
- 3 次都失败 → `pulse_agent_run_steps.status='failed'` + `pulse_agent_runs.outcome='error'`，跳过后续 stage，整 run 失败
- 60s poll loop 不重复 claim 已失败的 job（避免 token 烧穿）；需要重跑则人工 re-queue

### 7.5 文件结构

```
src/gmgn_twitter_intel/integrations/openai_agents/
├── pulse_pipeline_runner.py            (现 pulse_recommendation_agent_client.py 重命名+大改)
├── pulse_stages/
│   ├── shared.py        ← make_stage_agent + Pydantic schemas
│   ├── analyst.py       ← CexAnalyst, MemeAnalyst
│   ├── critic.py        ← CexCritic, MemeCritic
│   └── judge.py         ← CexJudge, MemeJudge
├── routing.py           ← route_event + compute_completeness 纯函数
└── prompts/
    ├── cex_analyst.md     cex_critic.md     cex_judge.md
    └── meme_analyst.md    meme_critic.md    meme_judge.md
```

### 7.6 与 SocialEventExtractionAgent 共存

`social_event_agent_client.py` 不动，继续走 `enrichment_worker`。两条 worker 互不知道对方，通过 DB 表（`social_event_extractions` → `pulse_agent_jobs`）解耦。

## 8. 路线图

### 8.1 Phase 0a · 数据层先行（不在本 spec 范围）

落地三个 active plan：
- `2026-05-12-signal-lab-pulse-decision-facts-hard-cut-plan-cn.md`
- `2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md`
- `2026-05-12-market-data-pipeline-gap-cn.md` 提及的修复

**验收**：见 §4.6。

### 8.2 Phase 0b · 决策层实施（本 spec 范围，~3-4 周）

依赖 phase 0a 至少完成"`_market()` 不再硬编码 None"。按顺序，每步独立 commit + verify：

1. **Schema migration**（1-2 天）
   - `pulse_candidates.confidence`、`pulse_candidates.route`、`pulse_candidates.abstain_reason`、`pulse_status += 'abstain'`
   - 新建 `pulse_agent_run_steps` + FK 索引
   - `pulse_agent_runs.outcome` enum 增值
   - `pulse_agent_runs.request_json` 字段保留但停止写入（hard cut 退役）

2. **EventRouter + 完整度纯函数**（1 天）
   - `routing.py` + `compute_completeness` + fixture 单测覆盖

3. **6 stage Agent + 6 prompt 文件**（3-5 天）
   - 先 analyst（最关键，定 Output schema），再 critic（验证下调机制），再 judge（验证综合规则）
   - 每 prompt 配 ~5 golden fixture（输入 snapshot → 期望 output 形态）

4. **PulseDispatchWorker 改造**（2 天）
   - 替换 `process_job` 编排
   - 实现 `_run_stage_with_retry`（max_retry=2 + 2s/8s/30s 退避）
   - replay log 写入 `pulse_agent_run_steps`

5. **端到端测试**（2 天）
   - 5 个 path：cex happy / meme happy / insufficient_data / critic_veto / error
   - 修 `docs/TECH_DEBT.md:52-54` 列的 3 个失败 integration test

6. **Soft launch**（7 天）
   - 跑生产数据，前端继续显示
   - 人工 review confidence 分布 + abstain reasons
   - 期望：abstain 5-30%、high_conviction < 15%

### 8.3 Phase 1 入口条件（不预设时间）

- Phase 0b 已运行 ≥ 30 天
- `pulse_agent_runs.outcome = 'error'` 占比 < 5%
- abstain_insufficient_data 比例连续 7 天波动 < 30%
- 人工 review：high_conviction 事后看 ≥ 50% 合理

### 8.4 Phase 1 范围（不在本 spec）

`OutcomeCollectorWorker` + `pulse_decision_outcomes` 表 + Reflector / memory injection (TradingAgents pattern) + `sample_n > 1` self-consistency。

### 8.5 Phase 2 范围（仅 roadmap，不预留 schema）

KISS：phase 2 才考虑 `entry_thesis` / `stop_loss` / `position_size` 等字段，到时再 `ALTER TABLE`（Postgres add column 极便宜，预留反而养肥 schema）。

### 8.6 跨 spec 依赖

```
[active] signal-lab-pulse-decision-facts-hard-cut-plan
[active] token-radar-kappa-cqrs-hard-cut-plan
[active] market-data-pipeline-gap              → phase 0a
            ↓
[本 spec] 2026-05-13-target-agent-architecture-design-cn  → phase 0b 设计
            ↓
[未来 plan] phase 0b implementation plan        ← 由 writing-plans 阶段产出
            ↓
[未来 spec] phase 1 calibration + self-consistency
[未来 spec] phase 2 trading interface
```

## 9. 整体验收

Phase 0b 完成判定（全部达到才算 spec 落地完成）：

1. 6 个 stage agent 生产 ≥ 7 天
2. `pulse_agent_run_steps` 完整 prompt/response 100% 入库（无 hash-only 行）
3. `pulse_candidates.confidence` / `route` 100% 非 NULL
4. **指标分布**：
   - high_conviction 比例 < 15%（vs 现状 100%）
   - abstain 5-30%
   - error < 5%
5. 现有 3 个 integration test 通过（TECH_DEBT 列）+ 新增 5 path 端到端 test 通过

## 10. 决策日志（why this, not that）

| 决策 | 理由 |
|---|---|
| 留在 openai-agents-python 不迁 LangGraph | 用户偏好不引入大依赖；现有两个 agent client 是 `max_turns=1-3` 单调用，迁移成本不划算；顺序 `Runner.run()` 在静态 pipeline 下足够 |
| 3-stage Analyst→Critic→Judge 而非 Bull/Bear 多轮辩论 | TradingAgents 风格 5-10 calls × 30-60s 成本高、与 openai-agents-python 拼起来费劲；3 stage 在性价比上是 Pareto 前沿 |
| Critic 只能下调不能翻案 | Critic 翻案会增加结果震荡；约束模型对决策稳定性优于二审 |
| Confidence 阈值梯度 0.40/0.55/0.75 拉开 | 现状 27/27 全 high_conviction 的根因之一就是无梯度；强行拉开会迫使 prompt 校准 |
| 顺序 `Runner.run()` 不用 handoff | Handoff 为动态路由设计，静态 pipeline 用 handoff 是 over-engineering |
| 砍 outcome collector from phase 0 | KISS；phase 0 是看盘模式，人工判断足够；phase 1 入口再加 |
| 不预留 phase 2 schema | KISS；Postgres `ALTER TABLE ADD COLUMN` 极便宜，预留反而养肥 schema |
| `pulse_agent_runs.request_json` 退役 | Hard cut；hash 字段没人读，新表 `pulse_agent_run_steps` 取代 |
| 完整度阈值按 route 分（meme 0.6/0.8，cex 0.8/0.95） | meme 数据天然缺，对它太严 = 全 abstain；CEX 数据稳，应严 |
| 不抄 agency-agents 任何东西作为底座 | 它是 Markdown persona 库（96% Shell 脚本），无 runtime、无状态、无可观测性，有 prompt-injection issue |

---

**下一步**：本 spec review 通过后，进入 `writing-plans` 阶段产出 phase 0b 的 implementation plan，按 §8.2 的 6 步细化到任务级。
