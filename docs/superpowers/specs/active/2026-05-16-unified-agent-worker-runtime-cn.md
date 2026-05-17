# 统一 Agent 与 Worker 运行时改造（生产闭环版）

- **状态**: Draft, awaiting review
- **作者**: aaurix（with Claude Opus 4.7 audit）
- **日期**: 2026-05-16
- **取代**: 本 spec 合并并取代 `2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`、`2026-05-13-target-agent-architecture-design-cn.md`、`2026-05-14-pulse-worker-architecture-cn.md` 三份 spec 的 agent / worker 部分。原三份保留为历史文档。
- **关联代码**:
  - `src/gmgn_twitter_intel/app/runtime/worker_base.py`、`worker_registry.py`、`worker_scheduler.py`
  - `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
  - `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
  - `src/gmgn_twitter_intel/integrations/openai_agents/{pulse_decision_agent_client,social_event_agent_client,watchlist_summary_agent_client,pulse_stage_prompts}.py`
  - `src/gmgn_twitter_intel/domains/pulse_lab/services/{agent_runtime,agent_eval}.py`

---

## 1. 背景

项目把 GMGN 公开 WebSocket 的 token 提及流，经过 14 个 worker 串联的 Kappa/CQRS pipeline，最终通过 3 个 OpenAI Agents SDK driver 输出三类决策：

| Agent | Worker | 用途 | 调用形态 |
|---|---|---|---|
| `PulseDecisionAgent` | `pulse_candidate` | 给每个 candidate 三 stage（analyst → critic → judge）决策 | 顺序 `Runner.run(max_turns=1)` × 3 |
| `SocialEventAgent` | `enrichment` | 从社交事件抽取 signal payload | 单 `Runner.run(max_turns=1)` |
| `WatchlistHandleSummaryAgent` | `handle_summary` | 对某 handle 最近 N 个 signal 出 ZH 摘要 | 单 `Runner.run(max_turns=1)` |

历史上有三份 spec 各自描述这个 pipeline 的不同切面（数据契约缺口 / 顶层 Agent Runtime / Worker 入队限流），它们之间互相引用但**没有一份能直接对应到当前生产数据**。这份 spec 用真实生产数据替代叙事，给出一份合一的改造方案。

**用户口径明确**：保留 `openai-agents-python`、不迁 LangGraph、multi-stage 用顺序 `Runner.run` 而不是 handoff（参见 memory `feedback-agent-harness-choice`）。模型当前是 `qwen3.6` via `https://big9er.com/v1` 代理（OpenAI 兼容的 Chat Completions 接口）。

---

## 2. 事实证据（结构层）

### 2.1 Worker 清单（14 个）

来源：`docs/WORKERS.md` + `app/runtime/worker_registry.py` + `~/.gmgn-twitter-intel/workers.yaml`。全部 `WorkerBase` 子类，由 `WorkerScheduler` 统一启停。

```
collector (continuous WS)
  └─→ ingestion 写 events / token_intents / asset_identity 等事实表
        ├─→ token_capture_tier (poll 30s)
        ├─→ resolution_refresh (poll 30s, NIL/AMBIGUOUS keys)
        ├─→ asset_profile_refresh (poll 60s)
        ├─→ market_tick_stream (WS event-driven) ──┐
        ├─→ market_tick_poll (poll 15s)            │
        ├─→ live_price_gateway (in-mem only)       │
        ↓                                          │
        token_radar_projection (10s, advisory_lock 2026051501)
        └─ wake: market_tick_written / resolution_updated
        ↓
        pulse_candidate (60s, advisory_lock 2026051502)  ← Agent #1
        └─ wake: token_radar_updated
        ↓
        enrichment (2s, concurrency=4)  ← Agent #2
        ↓
        handle_summary (2s)  ← Agent #3
        ↓
        notification_rule (5s) + notification_delivery (5s)

旁路：harness_ops (60s) — closed loop shadow tracking
```

唯一冷写者（SINGLE_WRITER advisory_lock）：`token_radar_projection`、`pulse_candidate`。其他 worker 用 `FOR UPDATE SKIP LOCKED` 行级乐观并发。**没有任何 worker 写 heartbeat / worker_runs 心跳表**——生死只能从其主输出表的 `updated_at_ms` 反推。

### 2.2 Agent 清单（3 个，全部 single-call + Pydantic `output_type`）

| 维度 | PulseDecisionAgent | SocialEventAgent | WatchlistHandleSummaryAgent |
|---|---|---|---|
| 文件 | `pulse_decision_agent_client.py` | `social_event_agent_client.py` | `watchlist_summary_agent_client.py` |
| Stage 数 | 3（analyst+critic+judge） | 1 | 1 |
| Pydantic `output_type` | ✅ 每 stage | ✅ `SocialEventPayload` | ❌ **未传给 Agent**，靠 `_coerce_summary_payload` markdown fallback |
| `ModelRetrySettings` | ✅ `max_retries=2` 覆盖 408/409/429/5xx | ❌ `max_retries=0` | ❌ `max_retries=0` |
| Model backend | `OpenAIChatCompletionsModel`（兼容 qwen） | `OpenAIResponsesModel` | `OpenAIResponsesModel` |
| 输出 audit 表 | `pulse_agent_runs` + `pulse_agent_run_steps` | `model_runs` | `watchlist_handle_summary_runs` |
| Trace 串联 | `sdk_trace_id = _trace_id(run_id)`，run_id 含 attempt + ms | 同上，但 run_id 每次 invoke 重算（含 `_now_ms()`），跨 retry 不同 | 同上 |
| 共性 copy-paste | `_api_base / _is_openai_base_url / _sha256 / _trace_id` + tracing init 三处重复 | 同左 | 同左 |

### 2.3 Eval / Audit / Harness 设施现状（已存在的部分）

| 资源 | 位置 | 状态 |
|---|---|---|
| `pulse_agent_runtime_versions` 表 | DB | ✅ 2 行（manifest 含 stages / framework / gate_policy / hard_blockers / eval_metadata），runtime_hash 来自 `agent_runtime.py` |
| `pulse_agent_eval_cases` 表 | DB | ✅ 2,494 行，每个成功 run 自动构造一份 deterministic case |
| `pulse_agent_eval_results` 表 | DB | ✅ 2,494 行，2500 pass / 3 fail（fail 都是 `final_route_mismatch`） |
| `grade_pulse_deterministic_eval_case()` | `pulse_lab/services/agent_eval.py:57` | ✅ 5 项检查：route 一致 / recommendation 一致 / hard_blocked→abstain / non_abstain 有 evidence-or-residual / critic ceiling / 无 trading 执行语 / 无失败 stage |
| `pulse_candidate_edge_state` 表 | DB | ✅ 979 行，按 `candidate_id` 跟踪 last_edge_signature / last_job_id / last_agent_run_id（Phase 0b worker 已落地） |
| `pulse_candidate_run_budget` 表 | DB | ✅ 1,393 行，每 candidate 每小时 3 次硬上限 |
| `_factor_completeness` + `hard_blocked` 字段 | `pulse_candidate_worker.py` + `agent_runtime.py` | ✅ 已实装 pre-LLM gate，cex 全部 hard-block 走 `research_only_gate` 不调 LLM |

**这意味着** 历史 spec 里被列为"未落地"的相当一部分（eval suite / harness versioning / edge state / run budget / pre-LLM gate）实际上已在线运行。问题不在"基础设施缺失"，而在"基础设施被劣质模型 + 失衡 prompt 拖累"。

---

## 3. 真实数据分析（来自生产 DB 查询，2026-05-16）

> 查询命令、SQL、原始结果保留在 PR 描述里。下面是关键数字。

### 3.1 整体吞吐 — 健康

| 指标 | 24h | 1h | 状态 |
|---|---|---|---|
| `pulse_agent_runs` 新增 | 1,868 | 172 | ✅ healthy |
| `social_event_extractions` 新增 | 188 | 8 | ⚠️ 较慢，可能 enrichment_jobs 堆积 |
| `watchlist_handle_summary_runs` 新增 | 134 | 4 | ✅ |

**结论**：worker 没有卡断，pipeline 在持续产出。

### 3.2 Agent 质量 — 严重失衡

```
pulse_agent_runs by route × outcome:
  cex            | abstain_insufficient_data  |   808  (100% — 数据层 NULL 触发 hard-block)
  meme           | failed                     | 1,349  (44%)
  meme           | abstain_critic_veto        | 1,256  (41%)
  meme           | abstain_insufficient_data  |   317  (10%)
  meme           | completed                  |   117  (4%)    ← 唯一真正三 stage 输出
  meme           | running                    |     1  (orphan, lease 未回收)
  research_only  | failed                     | 1,351  (34%)
  research_only  | completed                  | 2,653  (66%)
```

```
stage 流转（meme route, 重建）：
  analyst:  1,849 ok / 406 failed   (18% 失败)
  critic:   1,390 ok / 459 failed   (25% 失败) -> 1,256/1,390 = 90% 进 veto
  judge:    117 ok / 17 failed      (13% 失败)
  最终成功: 117 / 3,040 = 3.85%
```

```
pulse_candidates.decision_json -> recommendation 分布（n=1,022 有 decision）：
  abstain          | 971  (95%)
  ignore           |  32
  trade_candidate  |  10
  watchlist        |   9
  high_conviction  |   1  ← 与 2026-05-13 时点 "27/27 high_conviction" 形成完全相反的失衡
```

### 3.3 失败根因 Top 10（`pulse_agent_runs.error` 文本聚类）

| 错误 | 次数 | 类别 |
|---|---|---|
| `Invalid JSON when parsing { "schema_version":"pulse_recommendation_v1", "recommendation":"research" ...` | 533 | **模型输出违反 Pydantic schema** |
| `Invalid JSON when parsing { ..., "recommendation":"trade_candidate" ...` | 484 | 同上 |
| `Error code: 530 - ... 'code': 'internal_server_error' ...` | 249 | **上游 (big9er.com / Cloudflare 1033) 不可用** |
| `analyst stage failed: ModelBehaviorError: Invalid JSON when parsing { "route":"meme", "recommendation":"trade_cand...` | 151 | 同 #1 |
| 同上变种 `recommendation: watchlist` | 80 | 同 #1 |
| 同上变种 single-quote | 61 | 同 #1 |
| `Agents SDK request timed out after 120s` | 61 | **agent 调用超时** |
| 同上 `watchlist` 变种 | 45 | 同 #1 |
| `stale_running_timeout` | 44 | **worker lease 过期被回收** |
| `critic stage failed: ModelBehaviorError: Invalid JSON ...` | 31 | 同 #1 |

> 数据：**JSON schema 违反 = 1,400+ 失败 ≈ 52% 失败份额**（注意：错误样本里的 `schema_version: pulse_recommendation_v1` 字段并**不在** Pydantic schema 中，是模型按 system prompt 文字描述吐出的幻觉字段；`extra="forbid"` 拒收触发 fail。根因不在模型不够聪明，在项目 schema 层配置——见 §5.0/§5.1）。Cloudflare 530 ≈ 9%。timeout ≈ 4%。

**enrichment（SocialEventAgent）同样症状**：953 failed / 3,264 total = 29%，错误前 5 名有 320 个 120s timeout、248 个 530、174 个 30s timeout、74 个 ` ```json ` markdown fence 包裹导致解析失败。

**watchlist（WatchlistHandleSummaryAgent）**：56 failed / 239 total = 23%，主因 33 个 530、6 个 503 `auth_unavailable: no auth available (providers=vllm, model=...)` — 说明 big9er.com 是多 backend 代理（curl 实测命中 llama.cpp `b8779-75f3bc94e`，错误样本暗示也有 vllm 实例），偶发不可用源于 backend 路由层。

### 3.4 失败率时序（pulse, 按天）

| 日期 | total | failed | fail % |
|---|---|---|---|
| 2026-05-16 (今日, 部分) | 400 | 53 | 13.3% |
| 2026-05-15 | 1,541 | 341 | 22.1% |
| **2026-05-14** | **1,913** | **955** | **49.9%** |
| **2026-05-13** | **1,779** | **825** | **46.4%** |
| 2026-05-12 | 2,102 | 483 | 23.0% |
| 2026-05-11 | 123 | 43 | 35.0% |

**结论**：5-13/14 时期 ~50% 失败，目前已降到 13-22% 但仍远高于生产可接受水平。趋势改善来自 5-15 时期 pre-LLM hard-block 命中（cex route 100% abstain 不调 LLM）+ run_budget 限流；但 **模型调用层失败率本身没改善**——一旦调到 LLM，仍有 ~30% 概率 JSON 失败。后续调研（§5.0）确认这 30% 不是 qwen3.6 模型本身的问题，是项目 `_JsonOutputSchema.is_strict_json_schema=False` + Pydantic `$ref` + llama.cpp silent fail-open 三层叠加，可以用 §5.1 M1 hard fix。

### 3.5 Cost & Latency

**Pulse meme route，2,019 个有 usage 数据的 step**：

| 维度 | 值 |
|---|---|
| Input tokens 总计 | 10,474,368 |
| Output tokens 总计 | 688,325 |
| Cached input tokens | 1,348,987（cache hit ≈ 12.9%） |
| 平均每 step input | ~5,188 tokens |
| 平均每 step output | ~341 tokens |

> 验证了 OpenAI 兼容 prompt caching 在 qwen3.6 + big9er.com 链路工作，第二次同 prefix 命中可省 90%。但当前 cache hit 只有 12.9%——意味着 system prompt 没有放在最稳定的前缀位置，或者 cache TTL 太短被 invalidate 了。

**Latency p50 / p95 / p99（ok stages, ms）**：

| stage | p50 | p95 | p99 | max | n |
|---|---|---|---|---|---|
| analyst | 8,093 | 29,594 | 42,019 | 93,500 | 1,851 |
| critic | 6,528 | 27,396 | 36,554 | 61,776 | 1,392 |
| judge | 13,788 | 34,926 | 40,252 | 45,800 | 117 |

> p95 一致在 27-35 秒。120s timeout 主要被 cloudflare 530 + 偶发 vllm 排队拖到。p50 ~8s 单 stage，三 stage 串行 p50 ~22-28s 单决策——这是**人类可接受**但**机器作为下游消费者偏慢**的延迟。

### 3.6 Eval suite — 已在线但事实上失效

- 2,494 cases / 2,494 results / 2,500 "pass" / 3 "fail"
- 3 fail 全部是 `final_route_mismatch`（agent 输出的 `route` 字段不等于 runtime route，例如 worker 决定走 meme 但 agent 在输出里写了 `cex`）
- **隐含问题**：grader 只在 status='done' 的 run 上跑（2,700 个 failed run 完全不进 eval），所以"99.88% pass" 实际上是"我们只评估了能产出合法 JSON 的 run"——典型 survivor bias

---

## 4. 原理：生产级 single-call agent 的最小闭环

### 4.1 业界 2026 共识 + cookbook 范式（适用本架构）

| 主题 | 共识 | 本项目映射 |
|---|---|---|
| **Eval-driven** | outcome + trajectory + cost/latency 三类 grader；regression suite 防回退 | 现有 `agent_eval` 是 outcome grader 雏形；缺 cost/latency grader 与"在 failed run 上也跑校验"路径 |
| **Structured output** | strict mode + flat schema (<30 字段) + `@field_validator` 语义校验 + pin model 版本 | qwen3.6 + llama.cpp **支持** strict mode（curl 实证），但项目代码 `is_strict_json_schema=False` 主动禁用了；同时 Pydantic 自动 `$ref` 让 llama.cpp silent fail-open。修复见 §5.1 M1.a-d |
| **Observability (OTel GenAI)** | OTel GenAI SemConv + Langfuse v4 + 业务属性 attach to span | 当前只有 OpenAI Agents SDK 内置 trace；`sdk_trace_id` 串到 DB 但**跨 worker 无 correlation_id**——collector → projection → pulse 链断 |
| **Cost** | tiered routing + prompt caching shared prefix | 已有 13% cache hit；单 provider 决策下 tiered routing 不适用，留作 O-level 未来扩展 |
| **Guardrails** | input/output guardrail + tripwire；hallucination check | 已有 deterministic grader 但**只在事后**，没有 pre-output guardrail；critic stage 是 in-prompt critic 不算 SDK guardrail |
| **Reliability** | SDK retry + 业务层 retry + lease 回收 + circuit breaker | Pulse 有 SDK retry；Social/Watchlist 无；lease 回收依赖下次 claim（44 个 `stale_running_timeout` 印证有阻塞） |
| **Memory** | stateless 任务用 prompt-level few-shot retrieval，不引入 long-term memory | 当前无；可以从 `pulse_agent_run_steps` 历史挖 in-context examples |
| **Multi-LLM ensemble** | 仅高风险场景；优先 self-consistency 同模型 n=3 | 不需要；保留单 provider 决策 |

### 4.2 Cookbook 关键启示（来自 `multi-agent-portfolio-collaboration` + `building_reliable_agents_memory_compaction` + `eval_driven_system_design`）

1. **Prompt 文件化**：portfolio 把每个角色的 prompt 拆到 `prompts/*.md`，从 `load_prompt("pm_base.md")` 加载。本项目把所有 prompt 写在 `pulse_stage_prompts.py` 的 f-string 里，无法 diff / A/B / git blame。
2. **Tracing 文件化 fallback**：portfolio 用 `FileSpanExporter` 把 SDK trace 直接写本地 `logs/agent_traces.jsonl`，**不依赖** 第三方 (Langfuse)。本项目当前完全没接 OTel，但 OpenAI Agents SDK 提供了同样的 hook。
3. **Artifact-as-truth**：reliable_agents 强调 memo / artifact 是 ground truth，context 只是工作状态。`pulse_agent_run_steps.prompt_text + response_json + usage_json` 已经是这个模式的良好实现（只需把 hash-only 的 `pulse_agent_jobs.request_json` 补成全文）。
4. **Dataset-driven iteration**：eval_driven 强调一次 prompt 改动要在固定 dataset 上跑 grader，再决定 rollout。本项目 `pulse_agent_eval_cases` 表结构已支持，但缺一个 **CLI/CI workflow** 把"取最近 N 个 case → 改 prompt 跑一遍 → 对比 fail rate"做成命令。

### 4.3 与本项目的硬性约束的关系

- **不迁 LangGraph**：cookbook 的 portfolio 用 `agent-as-tool + parallel_tool_calls=True`。本项目 stage 之间有依赖（critic 依赖 analyst 输出），顺序 `Runner.run` 是正确选择，不需要切到 agent-as-tool。
- **保留 qwen3.6 + big9er.com**（2026-05-16 决策，见 §5.0）。不切 OpenAI、不做 multi-provider 自动 fallback。
- **不引入 long-term agent memory**：每个 candidate 处理是 stateless 短任务，无需 MemGPT 风格 memory。

---

## 5. 方案

### 5.0 决策：保留 qwen3.6 + big9er.com，靠 schema 层 hard fix + Instructor 兜底

用户 2026-05-16 明确决策：**保留 qwen3.6 via big9er.com（llama.cpp 后端）作为单一 provider**。不切 OpenAI、不引入 multi-provider 自动 FallbackModel。

依据来自 4 路实证调研（curl 直测 big9er.com + SDK 源码读取 + DB 真实失败样本 + 上游 issue 调研），1,400+ JSON 失败的真正机制**不是** "qwen 模型不行"，而是 SDK + Pydantic + llama.cpp 的三层 silent fail 叠加：

| 层 | 现状 | 证据 |
|---|---|---|
| **SDK** | `pulse_decision_agent_client.py:60` 显式 `AgentOutputSchema(output_type, strict_json_schema=False)`，`:71-72` `is_strict_json_schema()` 永远返回 False | 代码读取 |
| **Pydantic** | `model_json_schema()` 自动生成含 `$ref/$defs` 的 schema | 标准 Pydantic 行为 |
| **llama.cpp** | 忽略 `strict` 子字段；GBNF 转换碰 `$ref` silent fail-open，返回 HTTP 200 + 自由文本 | issue #21228 / #19051 |
| **模型行为** | grammar 没真正约束 → 输出可能含 markdown fence、幻觉字段、非法 enum | DB 失败样本 + curl 对比测试 |

**curl 实测**：用 inline schema（无 $ref）+ `strict=true` 给 big9er.com，llama.cpp **强制 enum 合法**；故意让 prompt 要求添加 schema 里没有的字段，llama.cpp **完全忽略 prompt 指令**按 schema 输出。这证明：

> **strict + inline schema 在 qwen3.6 + llama.cpp 链路上是 work 的，是项目代码主动禁用了它。**

**修复路径分两层**：

1. **结构层硬修**（§5.1 M1）：打开 strict、把 schema $ref 展平 inline、Pydantic `extra` 放宽、关 thinking 模式。预期消灭 1,400 个 JSON 失败的 80-90%。
2. **safety net 兜底**（§5.1 M1b）：剩余的 fail-open 边缘情况（thinking 漏开、模型偶发幻觉）用 Instructor 在 SDK 抛 `ModelBehaviorError`/`ValidationError` 后 reask 重试。预期把残留失败率压到 <2%。

**架构层不做**的：

- ❌ Multi-provider auto FallbackModel（用户 2026-05-16 否决——"感觉不可控"）
- ❌ Per-route tiered model routing（单 provider 用不上）
- ❌ 切 OpenAI 原生 strict mode（成本+迁移面+脱离 big9er.com 价格）
- ✅ ModelRegistry / per-agent-role 配置 → 移到 §5.3 **O-level** 作为未来扩展点（不阻塞本次修复）

这条决策让 §5 的修复面**显著收窄**：只动 agent client 内部 + 引一个 jsonref 一个 instructor 库，不动 worker 调度、不动配置 schema 结构、不动 provider 抽象层。

### 5.1 必修（确定的代码层缺陷）

每项给文件、行号或函数名，方案直接可执行。

**M1. Schema 层 hard fix：让 SDK 真发 strict + 把 schema $ref 展平 + Pydantic 放宽 extra + 关 qwen thinking**  

四个改动必须**一起**做，单独做任一个都不能消灭 1,400 个 JSON 失败。

**M1.a — 翻 strict 开关 + $ref 展平**：改写 `pulse_decision_agent_client.py:54-79` 的 `_JsonOutputSchema` 类。

```python
# 新增依赖: jsonref（~10KB，纯 Python，无传递依赖）
import jsonref
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase

class _JsonOutputSchema(AgentOutputSchemaBase):
    """qwen3.6 via big9er.com (llama.cpp) 兼容版结构化输出。

    关键设计：
    - strict_json_schema=True，让 SDK 发 response_format strict=true
    - 用 jsonref 把 $ref/$defs 展平成 inline schema，避免 llama.cpp GBNF
      转换 $ref silent fail-open (issue #21228)
    """
    def __init__(self, output_type: type[Any]) -> None:
        self._schema = AgentOutputSchema(output_type, strict_json_schema=True)
        raw = self._schema.json_schema()
        # replace_refs(proxies=False, lazy_load=False) 产生纯 dict，无 jsonref 代理对象
        self._flat = jsonref.replace_refs(raw, proxies=False, lazy_load=False)

    def is_plain_text(self) -> bool: return self._schema.is_plain_text()
    def name(self) -> str: return self._schema.name()
    def json_schema(self) -> dict[str, Any]: return self._flat
    def is_strict_json_schema(self) -> bool: return True
    def validate_json(self, json_str: str) -> Any:
        # 保留宽容提取：模型偶发吐 prose-then-{...}，提取首尾平衡块再 validate
        text = str(json_str or "")
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start:end+1] if start != -1 and end > start else text
        return self._schema.validate_json(candidate)
```

**M1.b — Pydantic `extra="forbid"` → `extra="ignore"`**：`agent_decision.py:23,43,58` 把三个 `ConfigDict(extra="forbid")` 改成 `extra="ignore"`。语义不退化（业务约束仍由 `@model_validator` 强制），只是模型偶发吐 schema 外字段时不再被拒收。

**M1.c — confidence float range 加 Pydantic clamp**：`agent_decision.py:27,48,62` 的 `confidence: float = Field(ge=0, le=1)` 因 GBNF 对 float 不强制范围（llama.cpp grammar README 明示），加 `@field_validator` 兜底：
```python
@field_validator("confidence", mode="after")
@classmethod
def _clamp_confidence(cls, v: float) -> float:
    return max(0.0, min(1.0, float(v)))
```

**M1.d — 关 qwen thinking 模式**：qwen3.6 是 reasoning 变种，prompt 头部的 `/no_think` 是软指令，硬约束要发 `chat_template_kwargs.enable_thinking=False`。llama.cpp issue #20345 证实：thinking 开启时 grammar enforcement **完全失效**。

`pulse_decision_agent_client.py` 在 build `Agent(...)` 时传 `ModelSettings(extra_args={"chat_template_kwargs": {"enable_thinking": False}})`；同样改 `social_event_agent_client.py` 和 `watchlist_summary_agent_client.py`。若当前 SDK 0.16.1 的 `ModelSettings` 不支持 `extra_args` 字段，退到给 `AsyncOpenAI` 加 `default_query={"chat_template_kwargs": '{"enable_thinking": false}'}`（PR 实施时验证一次）。

> 注：因 `social_event_agent_client.py` 和 `watchlist_summary_agent_client.py` 当前用 `OpenAIResponsesModel`（Responses API 只 OpenAI 原生有），M1 同时要把这两个换成 `OpenAIChatCompletionsModel` 才能用 qwen。这是前置必要改造，不算新增工作量。

**M1b. Instructor safety net（方案 C：外层兜底）**  

引入 `instructor` 库（`pip install instructor`）。**不**把 instructor 当主路径，**只**在 SDK 抛 `ModelBehaviorError` 或 Pydantic `ValidationError` 时启动，最多 reask 2 次。

新建 `integrations/openai_agents/instructor_safety_net.py`：

```python
import instructor
from agents import Runner
from agents.exceptions import ModelBehaviorError
from pydantic import ValidationError
from openai import AsyncOpenAI

class InstructorSafetyNet:
    def __init__(self, openai_client: AsyncOpenAI, *, max_retries: int = 2):
        self._client = openai_client
        self._inst = instructor.from_openai(openai_client, mode=instructor.Mode.JSON)
        self._max_retries = max_retries

    async def run_with_safety_net(
        self, *, agent: Agent, input_payload: str, run_config: RunConfig, model: str
    ) -> tuple[Any, dict]:
        """Returns (final_output, audit_extra). audit_extra 含 used_safety_net/retry_count."""
        try:
            result = await Runner.run(agent, input_payload, run_config=run_config, max_turns=1)
            return result.final_output, {"used_safety_net": False, "retry_count": 0}
        except (ModelBehaviorError, ValidationError) as e:
            messages = _rebuild_messages_from_agent(agent, input_payload, error_text=str(e))
            obj = await self._inst.chat.completions.create(
                model=model,
                messages=messages,
                response_model=agent.output_type,
                max_retries=self._max_retries,
            )
            return obj, {"used_safety_net": True, "retry_count": self._max_retries}
```

每次 fallback 触发都写入 `pulse_agent_run_steps.trace_metadata_json.used_safety_net=true`，便于事后看命中率。如果 safety net 命中率长期 >30%，说明 M1.a-d 没修干净，再决策是否升级到方案 A（把 Instructor 提到主路径）。

三个 agent client 改用 `safety_net.run_with_safety_net(...)` 替代直接 `Runner.run(...)`。仅 ~5 行 diff 每个 client。

> Audit 字段扩展：`pulse_agent_run_steps` 表新加 `safety_net_used boolean default false`、`safety_net_retries int default 0` 两列，alembic migration 一次性。

**M2. Watchlist agent 必须传 `output_type`**  
`watchlist_summary_agent_client.py:103-108` 构造 `Agent(...)` 时传 `output_type=WatchlistHandleSummaryPayload`。保留 `_coerce_summary_payload` 但只作为 `parse_mode="markdown_fallback"` 路径，触发时**写入 audit `agent_run_audit.parse_mode` 字段并写 warning log**，不再静默把 markdown 当合法输出。

**M3. Social / Watchlist 补 `ModelRetrySettings`**  
抽 `integrations/openai_agents/_shared.py:default_model_retry_settings()`（覆盖 408/409/429/500/502/503/504，max_retries=2，backoff exponential），三个 client 复用。`social_event_agent_client.py:143` 与 `watchlist_summary_agent_client.py` 同段都接入。

**M4. Pulse stale_running_timeout 的根因修复**  
`pulse_candidate_worker.py:493-505` 的 `await asyncio.wait_for(...)` 超时时，**先** `update pulse_agent_jobs set status='failed', last_error='timeout' where job_id=...`（独立事务，statement_timeout 短），**再** raise。当前序是先 raise 后才在 outer except 里 mark_failed，配合 statement_timeout 30s 会导致 mark_failed 自身超时。

**M5. Watchlist lease 自动回收**  
`handle_summary_worker.py` 增加 `_reclaim_expired_leases_once()` 方法，每个 `run_once` 开头扫一次 `watchlist_handle_summary_jobs where status='running' and lease_expires_at_ms < now`，重置 status='failed' + attempt_count 不动。同时把 pulse 的 `mark_stale_agent_runs_failed` 改为同一模式，独立事务、独立 statement_timeout。

**M6. `pulse_agent_jobs.request_json` 存全文**  
`pulse_candidate_worker.py:426` 把 `{"context_hash": ...}` 改为存 `{"context_hash": ..., "context": context, "factor_snapshot": snapshot}`。在序列化前用 `sanitize_for_audit()`（新加）剥离 OpenAI key、telegram token 等 secret 模式。Migration 一次性 backfill 不需要，新数据从这次开始全文存。

**M7. 统一 3 个 agent client 的 audit / trace / utils**  
新建 `integrations/openai_agents/_shared.py`，把 `_api_base / _is_openai_base_url / _sha256 / _trace_id / build_audit_dict / setup_tracing_once` 全部上移。三个 client import 即可。同时统一 `_trace_id` 截取长度（pulse 用 24 hex，其他 32 hex）。

**M8. 跨 worker correlation_id**  
在 `ingestion` 写 events 时生成一个 `pipeline_correlation_id = uuid7()`，写入 `events.metadata_json` 与下游所有派生记录（`enrichment_jobs`、`pulse_agent_jobs`、`watchlist_handle_summary_jobs`、各自的 `*_runs`）。新加列 `correlation_id text`（nullable backfilled 时为 NULL），有它就能从一条原始 frame 反查到最终 pulse decision。

### 5.2 应修（2026 业界共识必备）

**S1. OpenTelemetry GenAI SemConv tracing**  
新建 `platform/observability/otel_setup.py`，按 OTel GenAI SemConv 给 `Runner.run` 加 span：`gen_ai.system / gen_ai.request.model / gen_ai.usage.input_tokens / cached_input_tokens / output_tokens / gen_ai.response.finish_reason`，并 attach 业务属性 `run_id / candidate_id / route / runtime_hash / parse_mode / validation_passed`。OTLP 直发到本地 Langfuse v4（docker 起一个），不接外部云服务。pulse 三 stage 共享 trace_id 串成 pipeline trace。

**S2. Eval suite 改为也覆盖 failed run**  
`pulse_candidate_worker.py:548-619` 当前只在 stage_audits 非空时 `build_pulse_deterministic_eval_case`。改为：**任何 run（包括 status=failed）** 都构造 eval_case，对 failed run 加一项专用 violation `run_failed_<reason_class>`（reason_class ∈ {json_parse_error, upstream_530, timeout, stage_failed}）。`grade_pulse_deterministic_eval_case` 同步加 reason_class 的兜底分支。这样 2,700 个 failed run 也进 eval 表，"pass rate"指标才真实。

**S3. CLI: `gmgn-twitter-intel pulse eval-diff`**  
新加命令：取最近 N 个 eval_case，让用户输入新 prompt 文件路径或新 model id，重跑 grader，diff 老 vs 新 pass rate 与 per-rule 违规数。基础设施都在（runtime_hash + eval_case input_json + grader 函数），只缺 CLI wrapper。决策"prompt 改动是否 rollout"靠这条命令。

**S4. Prompt 文件化**  
迁 `pulse_stage_prompts.py` 的 f-string 模板到 `src/gmgn_twitter_intel/domains/pulse_lab/prompts/{analyst,critic,judge}_{cex,meme,research_only}.md`。`pulse_stage_prompt(route, stage)` 改为 `load_prompt(path).render(**context)`。git diff prompt 文件比 diff python f-string 易读 10×。

**S6. Output guardrail：critic veto 阈值化**  
当前 critic 90% 全否决，等于把三 stage 退化为单 stage。在 `pulse_decision_agent_client.py` 加一项配置：当 critic `should_abstain=True` **且** `confidence_ceiling > 0.6` 时，**不** veto 而是把 ceiling 应用到 judge 输出。即"critic 的弱否决不再杀决策"，让 judge 在低 confidence 域继续工作。具体阈值用 §S3 的 CLI 调出。

**S7. Pre-LLM completeness gate 复用到 enrichment / watchlist**  
`pulse_candidate_worker._factor_completeness()` 是 pulse 独有的 pre-LLM 拦截。enrichment / watchlist 没有同等机制：低质量输入（空 entities / 1 个事件）会直接调 agent，产 garbage 输出。抽 `domains/_shared/completeness_gate.py`，每个 worker 在调 agent 前先打分，分数低于阈值直接写 abstain audit 不调 LLM。

### 5.3 可选（高 ROI 但非必需）

**O1. Few-shot retrieval**：对每个新 candidate，用 `pgvector` 取 `pulse_agent_eval_cases` 里最近 5-10 个同 `route + recommendation` 的 historical case 塞进 analyst prompt 作为 in-context example。需要先建 pgvector embedding。

**O2. Cost ceiling**：在 `pulse_candidate_run_budget` 旁加一张 `pulse_agent_cost_budget(candidate_id, daily_token_cap, daily_token_spent_at_ms)`。每 run 写 `usage_json` 时累加，超限直接 abstain（单 provider 下没有便宜 model 可降级；若来日启用 §5.3 O6 ModelRegistry，再加 model 降级逻辑）。

**O3. Self-consistency (n=3)**：仅当 §S3 CLI diff 发现某 stage（如 judge）输出方差大时启用。`Runner.run` 调三次取众数（recommendation 多数投票，confidence median）。代价 ×3 token，仅用于高价值 stage。

**O4. Prompt-cache 友好排布**：当前 cache hit 12.9%。把 `pulse_stage_prompts.py` 的内容重组为「[静态 schema 描述 5KB] + [route_focus 1KB] + [stage_focus 1KB] + [动态 context 1.5KB]」，让静态前缀 ≥4KB 触发 caching；按 OpenAI 文档把 `cache_control: ephemeral` 加到 system block 末尾。理论 cache hit 可冲到 60-80%。

**O5. Prompt regression CI gate**：在 `Makefile` 加 `make pulse-eval-regression`：取最近 200 case，跑当前 prompt + grader，要求 pass rate ≥ 95%。接 GitHub Actions（用户已表态 lint/test 链路有缺口，参见 memory `project-harness-gaps`，本项目尚无 CI，这步要等 CI 平台搭好后再做）。

**O6. ModelRegistry + per-agent-role 配置**（仅扩展点，本期不实施）：

当前配置层 `Settings.llm` 是单一 `{base_url, api_key, model, pulse_agent_model}`。如果将来需要让 pulse analyst 用 qwen3.6、critic 用 deepseek-chat 这种 per-stage 异构（**不是** 自动 fallback），可以：

```yaml
llm:
  providers:
    qwen_big9er:
      base_url: https://big9er.com/v1
      api_key_env: BIG9ER_API_KEY
      backend: chat_completions
      capabilities: { strict_json_schema_grammar: true, json_object_only: false }
  agent_models:
    pulse_decision.analyst: { provider: qwen_big9er, model: qwen3.6 }
    pulse_decision.critic:  { provider: qwen_big9er, model: qwen3.6 }
    pulse_decision.judge:   { provider: qwen_big9er, model: qwen3.6 }
    social_event:           { provider: qwen_big9er, model: qwen3.6 }
    watchlist_summary:      { provider: qwen_big9er, model: qwen3.6 }
```

新增 `integrations/openai_agents/model_registry.py`（~80 行）暴露 `registry.for_role(role) -> Model`，三个 agent client 从 registry 取 model。**不**做 `FallbackModel` 自动切换——切 provider 应该是显式的配置变更，不是运行时自动行为。

本期保留现状（单一 `llm.pulse_agent_model` 字段），只在 §5.1 M1 改 schema 层。当未来要做异构时再启用本扩展点。

### 5.4 不要做（明确避免）

- **不**迁 LangGraph / autogen / crewai（用户 2026-05-13 已决定）
- **不**把 pulse decision 改 agent-as-tool / handoff（顺序依赖是本质，cookbook portfolio 是不同问题）
- **不**切 OpenAI 原生 strict 或其它 provider（用户 2026-05-16 决定保留 qwen3.6）
- **不**做 `FallbackModel` 自动 provider 切换（用户 2026-05-16："感觉不可控"——切 provider 应是显式配置变更）
- **不**做 tiered model routing（per-route 不同 model）—— 单 provider 用不上，移到 §5.3 O6 留作未来扩展
- **不**做跨 vendor ensemble（成本 ×N，crypto signal 非性命攸关）
- **不**做 MemGPT-style long-term agent memory（stateless 任务用 RAG over Postgres 替代）
- **不**保留 `agent_recommendation_json` 旧字段（旧 spec 提过的 hard cut 仍生效）
- **不**给非 reasoning 任务开 extended thinking / o3 reasoning model（pulse 三 stage 都不是多步对账，开了浪费 + 容易 thinking-token-trap）；qwen3.6 是 reasoning 变种，M1.d 显式关 thinking

---

## 6. 数据迁移与回滚

- **M1 schema 层 hard fix**：不动 DB schema。`runtime_hash` 会因 `is_strict_json_schema=True` + jsonref 展平后的 schema 变化自动 bump 到新值（`agent_runtime.py` 已基于 schema 内容算 hash），eval 表自动按新 harness 隔离记录。旧 runtime_hash 的 eval_case/result 保留不删。
- **M1b Instructor safety net**：纯新增模块 + `pulse_agent_run_steps` 加两列 `safety_net_used boolean default false`、`safety_net_retries int default 0`。alembic migration 一次性 add column，老行 NULL/default 不影响读。
- **M6 pulse_agent_jobs.request_json 全文**：**不**回填，新数据从 PR 合入开始全文，老数据保留 hash-only。Replay 工具兼容两种 shape（先查 context 全文，回退到通过 context_hash 重建）。
- **M8 events.correlation_id**：新加 nullable 列，已有数据 NULL 即可，不影响读路径。下游表（`enrichment_jobs`/`pulse_agent_jobs`/`watchlist_handle_summary_jobs`/`*_runs`）同样加 nullable 列。
- **Watchlist lease 自动回收（M5）**：纯新增方法，不动既有 schema。
- **OTel（S1）**：完全新增组件，可灰度（默认 disabled，配置开启）。
- **Pydantic `extra="ignore"` 改动（M1.b）**：行为放宽，不可能产生新的 validation error，相对现状只可能少拒收。可以直接 hard cut，无 dual-write。

**回滚策略**：M1 一旦发现 JSON 失败率不降反升（不应当发生，但兜底），把 `_JsonOutputSchema.is_strict_json_schema()` 临时改回 `False`、`json_schema()` 返回 `self._schema.json_schema()`（不展平）。这是 1 行 revert。Instructor safety net 失效时把配置 `instructor_safety_net.enabled=false` 即可全旁路。

## 7. 验证 / 验收

### 7.1 必修验收（M1, M1b, M2-M8）

| 项 | 验收条件 |
|---|---|
| **M1.a strict + jsonref** | 1 周观察 `pulse_agent_runs.error` 中 `Invalid JSON when parsing` 占比从 ≥52% 降到 <5%；`schema_version` 字段在错误样本中**不再出现** |
| **M1.b extra=ignore** | 不再因模型吐多余字段产生 `extra inputs not permitted` 类型的 Pydantic 错 |
| **M1.c confidence clamp** | `pulse_agent_run_steps.response_json->>'confidence'` 全部在 [0, 1]；`@field_validator` 在 metric 里能看到 clamp 触发次数 |
| **M1.d enable_thinking=false** | qwen3.6 输出不再含 `<think>...</think>` 残留；prompt cache hit 从 13% 提升（thinking 关后前缀更稳定）|
| **M1b Instructor safety net** | `pulse_agent_run_steps.safety_net_used=true` 命中率 <10%（如果 >30% 说明 M1.a-d 漏修，需复盘） |
| M2 Watchlist `output_type` | `watchlist_handle_summary_runs.response_json` 100% 通过 Pydantic 校验；`parse_mode='markdown_fallback'` 次数日 <5 |
| M3 Social/Watchlist retry | 530/timeout 失败率减半 |
| M4/M5 stale lease | `pulse_agent_runs.error='stale_running_timeout'` 数从 44/总 降至 <5/周；`watchlist_handle_summary_jobs.status='running'` 不再有超 5min 的行 |
| M6 全文 request | 任取 5 个 pulse_agent_jobs row，能从 request_json 完整重放出 prompt（与 pulse_agent_run_steps.prompt_text 字节一致） |
| M7 共享 helper | 3 个 client 文件 LOC 总和减少 ≥30% |
| M8 correlation_id | 任取一条 events 行，能 join 出对应 enrichment_jobs / pulse_agent_jobs / watchlist 链 |

### 7.2 应修验收（S1-S4, S6, S7）

| 项 | 验收条件 |
|---|---|
| S1 OTel | Langfuse v4 仪表盘能看到三 stage 单 trace；token / latency / cost 三件套全有；业务属性 attach |
| S2 eval 覆盖 failed | `pulse_agent_eval_results` 行数 ≈ `pulse_agent_runs` 行数（含 failed） |
| S3 CLI | `gmgn-twitter-intel pulse eval-diff --since 7d --prompt-file=new.md` 输出 diff 表 |
| S4 prompt 文件化 | `pulse_stage_prompts.py` 不再含 ROUTE_FOCUS / STAGE_FOCUS dict，全部 markdown 模板 |
| S6 critic 阈值化 | `pulse_agent_runs.outcome='completed'` 占比从 ~4% (meme) 升到 ≥15%；critic veto 占比从 90% → 60-70% |
| S7 completeness gate 扩展 | enrichment 失败率从 29% → <10%（因为低质量输入不再触发 timeout/JSON 错） |

### 7.3 可观察的全局指标（每日聚合）

实施完 M1 + M1b 后应当看到（M2-M8 + S 系列再叠加）：
- pulse 失败率 22% → <3%（M1.a-d 干掉 JSON 类失败；M1b 兜底剩余）
- pulse meme 成功决策占比 4% → ≥15%（依赖 S6 critic 阈值化）
- pulse_candidates abstain 占比 95% → 50-65%（更均衡的决策分布）
- enrichment 失败率 29% → <8%
- watchlist 失败率 23% → <8%
- 每日总 token cost：当前 ~11M input + 0.7M output；M1b 失败率降低会减少重试 token，O4 prompt cache 友好排布触发更高 hit rate；预期日成本同量级或下降
- `safety_net_used=true` 命中率：稳定 <10%；首周可能 15-25% 反映 M1.a-d 还在 settle

---

## 8. 实施依赖与顺序

依赖图（→ 表示前置）：

```
M1.a-d (schema hard fix) ─→ M1b (Instructor safety net)
                              ↓
                            S2 (eval 覆盖 failed) ─→ S3 (CLI eval-diff)
                              ↓
                            S6 (critic 阈值化, 依赖更可靠输出后才能调阈值)

M2/M3 (output_type + retry) ─→ S4 (prompt 文件化)
                                   ↓
M7 (共享 helper)  ─→ M8 (correlation_id) ─→ S1 (OTel tracing) ─→ S7 (completeness gate 扩展)

M4/M5 (stale lease 回收)   独立，可并行
M6 (全文 request_json)    独立，可并行
```

**推荐节奏（不分配工时，仅依赖序）**：

1. **第一波 — 代码 hygiene**（独立 PR，可并行）：M2, M3, M4, M5, M6, M7。纯代码改造，不动行为。
2. **第二波 — schema hard fix（核心）**：M1.a + M1.b + M1.c + M1.d 一起合一个 PR（**不要拆**：单独翻 strict 而不展平 $ref 会触发 llama.cpp silent fail；单独展平 $ref 而不翻 strict 不产生效果）。合入后 1-2 天观察 `Invalid JSON when parsing` 占比变化。
3. **第三波 — safety net 兜底**：M1b。M1 稳定后部署，记录命中率作为 M1 修复度的 KPI。
4. **第四波 — 可观察性**：M8 → S1 → S4 → S2 → S3。
5. **第五波 — 基于数据调优**：S6 (critic 阈值化) → S7 (completeness gate 扩展)。
6. **第六波 — 可选**：O1-O6 按 ROI 排队。O6（ModelRegistry）只在确实需要 per-agent-role 异构模型时启动。

**严格规则**：
- 第二波之前**不应**调 prompt / critic 阈值——当前数据被 schema fail 污染，调任何 prompt 都不能稳健评估。
- 第二波合入后**不应**在 1 周内再动 prompt——给 baseline 稳定时间，让 `pulse_agent_eval_results` 积累足够的 post-fix sample，§S3 的 CLI 才有 diff 基础。
- 第三波 Instructor 引入后**必须**监控 `safety_net_used` 命中率作为质量信号，**不**让它静默常态化（>30% 就说明 M1 没修干净要复盘，不是 acceptable steady state）。

---

## 9. 历史 spec 的处理

- `2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md` — 移到 `docs/superpowers/specs/completed/`，作为根因诊断历史档案保留
- `2026-05-13-target-agent-architecture-design-cn.md` — 同上，其 Agent Runtime Core 设计概念被本 spec §5.0-5.2 吸收
- `2026-05-14-pulse-worker-architecture-cn.md` — **保留在 active**，因为其 worker 入队 / edge state / run budget / 通知去重子项**已部分落地**，剩余项（`source_seed/theme_watch` 删除 / `cooldown_until_ms` 移除 / delivery stale lease）继续按那份 spec 执行。本 spec **不** 重写 worker 入队层，仅在 agent client + worker 调 agent 段引入改造。

如果 PR 评审者觉得有冲突，本 spec 优先（日期更新 + 用了真实 DB 数据）。
