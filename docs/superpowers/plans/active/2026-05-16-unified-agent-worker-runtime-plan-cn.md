# Unified Agent + Worker Runtime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft  
**Date:** 2026-05-16  
**Owning spec:** `docs/superpowers/specs/active/2026-05-16-unified-agent-worker-runtime-cn.md`  
**Worktree:** `.worktrees/unified-agent-runtime/`  
**Branch:** `unified-agent-runtime`

**Goal:** 把 pulse / social_event / watchlist 三个 agent 链路从 34% 失败率、90% critic veto、52% JSON 解析错的"半坏"生产状态，**用最小改动面**修到 <3% 失败率、合理 critic 阈值、可在线监控可回滚的状态。保留 qwen3.6 via big9er.com 不切 provider；引入 `jsonref`（schema 展平）+ `instructor`（safety net）两个轻量依赖。

**Architecture:** 不动 worker 调度、不动 PostgreSQL Kappa/CQRS 边界。改动集中在 `integrations/openai_agents/` 三个 client + `agent_decision.py` 输出类型 + `pulse_lab/services/agent_harness.py` 的 harness_hash 计算自动响应；新增 `instructor_safety_net.py` 一个文件；alembic 一次性加 2 列。worker 层只在 pulse_candidate / enrichment / handle_summary 三处加 `safety_net.run_with_safety_net(...)` 调用点。

**Tech stack:** Python 3.13, openai-agents 0.16.1, Pydantic v2, jsonref, instructor, psycopg, Alembic, qwen3.6 via big9er.com (llama.cpp b8779).

---

## Pre-flight

- [ ] Spec `2026-05-16-unified-agent-worker-runtime-cn.md` approved.
- [ ] Worktree exists at `.worktrees/unified-agent-runtime/` and `git branch --show-current` matches `unified-agent-runtime`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest tests/` 全绿（已知 PG-dependent 测试在 docker postgres 起好后通过；不在 docker 环境的开发机允许 skip）.
- [ ] DB 可达：`docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "select count(*) from pulse_agent_runs;"` 返回 7,848+ 行。
- [ ] big9er.com 健康：执行 spec §4.1 中的 curl 测试，返回 `{"name":"test","supply":1000}` 且 system_fingerprint 以 `b8779-` 开头。
- [ ] 安装新增依赖：`uv add jsonref instructor` 并提交 `uv.lock`。

**Known-failing baseline tests**（不阻塞 PR 合并，但要在 PR 描述里列出）：
- 无预期 known-fail，发现立即报告。

---

## Current-State Analysis（事实证据）

按 spec §2、§3 的内容**重新落地**为可被代码评审者直接核对的 file:line + DB 查询结果。本节不重述 spec，只列证据。

### A. SDK 调用链证据

- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:54-79` 定义 `_JsonOutputSchema`：
  - L60 `self._schema = AgentOutputSchema(output_type, strict_json_schema=False)` — 显式禁用 strict。
  - L71-72 `is_strict_json_schema(self) -> bool: return False` — SDK 据此把 `response_format.json_schema.strict` 发为 `false`。
  - L55-56 docstring 自承"relies on the model following the prompt, not on the provider honoring strict json_schema"，证明此设计是**故意为之**（基于"qwen 不支持 strict" 的错误假设）。
- `.venv/lib/python3.13/site-packages/agents/models/chatcmpl_converter.py:97-111` SDK 内部 `Converter.convert_response_format` 把 `output_schema` 翻译成 `{"type":"json_schema","json_schema":{"name":"final_output","strict":<is_strict>, "schema":...}}`，证明 SDK 链路本身**正确发送**了 response_format，问题在我们传的 `strict=False`。
- `.venv/lib/python3.13/site-packages/agents/models/openai_chatcompletions.py:362` 是 `response_format` 实际下发到 `chat.completions.create()` 的调用点。

### B. Pydantic schema 证据

- `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`:
  - L22-39 `AnalystOpinion(BaseModel)`：5 字段，`model_config = ConfigDict(extra="forbid")`，`confidence: float = Field(ge=0, le=1)`。
  - L42-54 `CritiqueReport(BaseModel)`：5 字段，同 `extra="forbid"`，含 `confidence_ceiling: float = Field(ge=0, le=1)`、`should_abstain: bool`。
  - L57-93 `FinalDecision(BaseModel)`：8 字段，同 `extra="forbid"`，含 `abstain_reason: str | None`（nullable union）、conditional 校验 `if recommendation==abstain ⇒ abstain_reason 必填`、`if recommendation!=abstain ⇒ evidence_event_ids 或 residual_risks 至少一个`。
- `python3 -c "from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import AnalystOpinion; import json; print(json.dumps(AnalystOpinion.model_json_schema(), indent=2))"` 输出含 `"$defs"`、`"$ref"`（DecisionRoute 等 Literal 被 Pydantic 抽出公共定义）。这是 llama.cpp #21228 silent fail 的触发条件。

### C. 上游能力实证（big9er.com / llama.cpp b8779）

- 模型实际身份：`Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`，server fingerprint `b8779-75f3bc94e`。
- **测试 1**（inline schema + strict=true）：返回严格合法 enum `recommendation: "ignore"`、无 markdown fence、所有 required 字段在。证明 strict mode 在 llama.cpp 端**实际工作**。
- **测试 2**（无 response_format）：返回 `recommendation: "HIGH_RISK_AVOID"` — **自创非法 enum**。证明软约束不可靠。
- **测试 3**（inline schema + strict=true + 故意 system prompt 要求 `schema_version` 字段 + `recommendation=research`）：llama.cpp **完全忽略 prompt 指令**，按 schema 输出 `trade_candidate`。证明 grammar 比 prompt 指令优先级高。
- Curl 命令归档：见 spec §4.1。复现命令：
  ```bash
  curl -sS https://big9er.com/v1/chat/completions \
    -H "Authorization: Bearer $BIG9ER_API_KEY" \
    -d '{"model":"qwen3.6","messages":[{"role":"user","content":"返回 {\"x\":42}"}],
         "response_format":{"type":"json_schema","json_schema":{"name":"t","strict":true,
         "schema":{"type":"object","properties":{"x":{"type":"integer"}},
         "required":["x"],"additionalProperties":false}}},"max_tokens":50}'
  ```

### D. 生产 DB 证据（2026-05-16 查询）

- `select count(*), status from pulse_agent_runs group by status;` → done=5149, failed=2700（失败率 34%）。
- `select route, outcome, count(*) from pulse_agent_runs group by 1,2 order by 1,3 desc;`：cex 全部 abstain_insufficient_data（808）；meme 1349 failed + 1256 critic_veto + 117 completed + 317 insufficient + 1 running；research_only 2653 done + 1351 failed.
- 失败错误 Top10 由 `select left(error,120), count(*) from pulse_agent_runs where status='failed' group by 1 order by 2 desc limit 10;` 取出，前 9 行有 1,400+ 行是 `Invalid JSON when parsing` 系列（带 `schema_version` 或 `recommendation: research` 等幻觉字段）。
- Critic 流转：`select stage, status, count(*) from pulse_agent_run_steps where route='meme' group by 1,2 order by 1,2;` → analyst 1849 ok / 406 failed → critic 1390 ok / 459 failed → judge 117 ok / 17 failed。Critic veto 率 = 1256 / 1390 = **90.4%**。
- usage 填充率：`select count(*) filter (where usage_json='{}'::jsonb), count(*) from pulse_agent_run_steps;` → 3350 empty / 5363 total = 62% 空（empty 几乎全部是 failed step）。successful step 都有 `{"requests":1,"input_tokens":4280,"output_tokens":355,"input_tokens_details":{"cached_tokens":4276}}` 结构，cache hit 实证 ~13%。
- `pulse_agent_eval_cases` / `_results` 表均存在（2,494 行），harness_hash 索引到 `pulse_agent_harness_versions` (2 行)。`agent_harness_eval.py:57` 的 `grade_pulse_deterministic_eval_case()` 包含 5 项检查并产 violation list。**这条说明 eval 设施已在线，不需要从零搭建**。

### E. Worker 层证据

- `docs/WORKERS.md` 14 worker 全部 `WorkerBase` 子类。`pulse_candidate` / `enrichment` / `handle_summary` 是直接调 LLM 的 3 个。
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:493-505` agent timeout 路径：`await asyncio.wait_for(...)` → 异常先 raise → outer except mark_job_failed → 受 `statement_timeout_seconds=30` 约束，超时时 mark_failed 自身会失败 → 44 个 `stale_running_timeout` 实例由此而来。
- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py` lease 机制（lease_expires_at_ms）只在下一次 `claim_next_summary_job()` 时回收过期项，缺主动 reclaim。

### F. 上游 GitHub issue 证据

- llama.cpp **忽略 strict 子字段、fail-open**：
  - https://github.com/ggml-org/llama.cpp/issues/19051（closed as not planned，确认不会修）
  - https://github.com/ggml-org/llama.cpp/issues/21228（$ref/$defs silent fail，2026-03-31）
  - https://github.com/ggml-org/llama.cpp/issues/20221（markdown fence 触发 grammar 撞墙）
  - https://github.com/ggml-org/llama.cpp/issues/20345（**enable_thinking=true 时 grammar 完全失效**）
- llama.cpp grammars/README.md：明示浮点 `minimum/maximum` 不强制；conditional schema 不支持。
- DeepSeek 仅 json_object 不支持 json_schema：https://api-docs.deepseek.com/api/create-chat-completion（与本 plan 无直接关系，但 §5.3 O6 设计参考用）。

---

## Design Corrections To Apply Before Coding

落地前需要修正的几个 spec 措辞 / 假设：

1. **`enable_thinking` 注入路径需先实测**。spec §5.1 M1.d 给了两个候选注入点（`ModelSettings.extra_args` 或 `AsyncOpenAI.default_query`），但 openai-agents-python 0.16.1 的 `ModelSettings` 是否真支持 `extra_args` 字段未确认。**第一步**：在 worktree 起好后跑 `python -c "from agents import ModelSettings; print(ModelSettings.model_fields)"` 看字段。如果没有，退到 `AsyncOpenAI(default_query={"chat_template_kwargs": '{"enable_thinking": false}'})`。如果 `default_query` 也不行（OpenAI Chat Completions 不接 query string），最后手段是 monkey-patch `OpenAIChatCompletionsModel._fetch_response` 在 payload dict 里加 `chat_template_kwargs`. 三选其一，PR 描述记录选择。
2. **jsonref 输出验证**。`jsonref.replace_refs(schema, proxies=False, lazy_load=False)` 应返回纯 dict 无 jsonref 代理对象，否则 `json.dumps()` 序列化会失败。PR 1 加单测：取 `AnalystOpinion.model_json_schema()` → replace_refs → `json.dumps()` 验证可序列化且**不含 `$ref` 字符串**。
3. **`extra="forbid"` → `extra="ignore"` 不放弃业务约束**。Pydantic `@model_validator(mode="after")` 仍执行（如 `FinalDecision._validate_decision` 的 abstain/evidence 互斥规则），所以业务层强制不变；只是 schema 外字段不再 fail validation。代码审查重点。
4. **Instructor 与 SDK 共用同一 `AsyncOpenAI` 实例**：`instructor.from_openai(client)` 会 patch 该 client 的 `chat.completions.create`。若同一 client 也被 SDK 用，可能影响 SDK 调用。**对策**：safety net 用**独立的** `AsyncOpenAI` 实例（base_url / api_key 同源，对象不同）。
5. **Audit 字段写入路径**：M1b 新加 `safety_net_used` / `safety_net_retries` 两列要在 `pulse_candidate_worker.py:568-584` 写入 `pulse_agent_run_steps` 的逻辑里同步更新；不能漏写。
6. **harness_hash 必须手动 bump（已确认）**：读了 `agent_harness.py:18-71` 的 `build_pulse_harness_manifest()`，输入只看 `PULSE_DECISION_PROMPT_VERSION` / `PULSE_DECISION_SCHEMA_VERSION` / `PULSE_GATE_VERSION` / model / timeout —— **不**含 `is_strict_json_schema` 或 `extra` 行为。所以 PR 1 必须在 `domains/pulse_lab/interfaces.py` 把 `PULSE_DECISION_SCHEMA_VERSION` 从 `"pulse_decision_v1"` 升到 `"pulse_decision_v2"`，否则 PR 1 前后的 run 全部混在同一 `harness_hash` 下，eval 表无法 diff baseline vs candidate。
7. **`StageRunAudit` 用 `extra="forbid"`**（`agent_decision.py:97`）。PR 1 的 audit_extra dict 含 `safety_net_used` / `safety_net_retries` / `parse_mode` 三键，**塞进 `trace_metadata_json` jsonb 安全**（jsonb 内部无 Pydantic 约束）。但 PR 2 把这 3 字段提到顶层 DB 列后，`StageRunAudit` 必须同步加 3 个 Pydantic 字段（带默认值），否则 `pulse_candidate_worker.py:473` 等构造点会爆 `extra inputs not permitted`。PR 1 与 PR 2 衔接时务必协调。
8. **`social_event_extraction.py:83,91,102` 也有 `extra="forbid"`**（spec M1.b 漏点）。同样改成 `extra="ignore"`，否则 SocialEventAgent 仍会因模型幻觉字段失败。**PR 1 必须包含**。
9. **3 个已有测试断言反方向**：`tests/test_pulse_decision_agent_client.py:260,267,275` 当前断言 `_JsonOutputSchema(AnalystOpinion).is_strict_json_schema() is False`。PR 1 同 commit 翻为 `is True`，并新加 `assert "$ref" not in json.dumps(schema.json_schema())` 验证展平。
10. **`<think>` 残留兜底**：若 M1.d enable_thinking 注入路径不生效（fallback 没拦到 server-side），qwen3.6 仍会在 `summary_zh` 等字段里输出 `<think>...</think>` 字面文本，前端 markdown 渲染会直暴给用户。PR 1 给 `agent_decision.py:_clean_text()` 加 `re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()`，是 cheap 但严肃的兜底。
11. **`_runner` mock 返回类型变化**：现有 `tests/unit/test_pulse_decision_agent_client.py` 等用 `FakeRunner` 返回 `RunResult` 对象给 `_runner.run(...)`。PR 1 把调用换成 `safety_net.run_with_safety_net(...)` 返回 `(final_output, audit_extra)` tuple。所有相关测试 mock 必须改成 mock `safety_net`（推荐）或保留 `_runner` mock 而在 client 内做兼容（不推荐，增加分支）。
12. **safety_net 与 `llm_gateway.run_with_timeout` 嵌套顺序**：当前三 client 形如 `await self._llm_gateway.run_with_timeout(lambda: self._runner.run(...))`。PR 1 改为：**gateway 包 safety_net**——`await self._llm_gateway.run_with_timeout(lambda: self._safety_net.run_with_safety_net(...))`。这样 timeout 同时 cover 主路径与 Instructor reask，行为可预测；不要反过来包，否则 reask 路径不受 timeout 保护。
13. **`SELECT * FROM model_runs` / `pulse_*` 表 8 处使用**：`enrichment_repository.py:293,354` 与 `pulse_repository.py:252,265,819,879,943,999,1198`。PR 2 加列后这些 dict 自动多键，调用者都是按 key 取值（未发现 `**unpack`），**安全**。前端不直接读 audit 列，**无 frontend 暴露风险**。但 PR 7 接 OTel / Langfuse 仪表盘时若直接 dump dict，新键会自动暴露——OK，符合预期。

---

## PR breakdown

| # | Name | 包含 | Wave | 依赖 |
|---|---|---|---|---|
| **PR 1** | Schema 层 hard fix + Instructor safety net（核心） | M1.a, M1.b, M1.c, M1.d, M1b | Wave 2 + 3 合并 | 无 |
| **PR 2** | Audit 列 migration + 写入 | `safety_net_used`/`safety_net_retries`/`parse_mode` 列 | Wave 1.5 | 无（可与 PR 1 并行） |
| **PR 3** | 三 client 共享 utils + Social/Watchlist 补 output_type 与 retry | M2, M3, M7 | Wave 1 | 无 |
| **PR 4** | Worker lease / stale 回收 | M4, M5 | Wave 1 | 无 |
| **PR 5** | request_json 全文持久化 + 跨 worker correlation_id | M6, M8 | Wave 1 | M6 不依赖 PR 1，但建议 PR 1 落定后再做以便 trace 联调 |
| **PR 6** | Eval suite 覆盖 failed run + CLI `pulse eval-diff` | S2, S3 | Wave 4 | PR 1 + PR 5 |
| **PR 7** | OTel GenAI tracing + Langfuse v4 docker compose | S1 | Wave 4 | PR 5 |
| **PR 8** | Prompt 文件化 | S4 | Wave 4 | PR 6 |
| **PR 9** | Critic veto 阈值化 + completeness gate 复用 | S6, S7 | Wave 5 | PR 6 + 1 周 baseline 数据 |

**关键约束**：
- **PR 1 必须把 M1.a/b/c/d 全部合并发**。spec §8 明确"单独翻 strict 而不展平 $ref 会触发 llama.cpp silent fail"，拆开做没有意义。
- PR 6（eval diff CLI）依赖 PR 1 上线后**1 周 baseline 数据**才能 calibrate threshold，不要在 PR 1 当周做。
- PR 9（critic 阈值化）要在 PR 6 给出的 eval diff 数据基础上调参，不要"凭感觉"调。

下面只详细列 **PR 1** 和 **PR 2** 的文件级 edits（核心修复）。PR 3-9 给到大纲级，每个 PR 自己时再展开成子 plan。

---

## PR 1 — Schema 层 hard fix + Instructor safety net

### 文件级 edits

#### `pyproject.toml`

- 在 `[project.dependencies]` 段加：
  ```toml
  "jsonref>=1.1.0",
  "instructor>=1.5.0",
  ```
- 执行 `uv lock` 重新生成 `uv.lock`。

#### `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`

- L54-79：**整个 `_JsonOutputSchema` 类替换**。

新代码（保留原 docstring 风格，强调修复原理）：
```python
class _JsonOutputSchema(AgentOutputSchemaBase):
    """qwen3.6 + llama.cpp 兼容版结构化输出 schema。

    设计：
    - strict_json_schema=True：SDK 发 response_format strict=true 给上游。
    - jsonref 展平 $ref/$defs：避免 llama.cpp #21228 silent fail-open。
    - validate_json 保留宽容提取：吸收模型偶发的 prose-before-json。
    """

    def __init__(self, output_type: type[Any]) -> None:
        self._schema = AgentOutputSchema(output_type, strict_json_schema=True)
        raw = self._schema.json_schema()
        self._flat = jsonref.replace_refs(raw, proxies=False, lazy_load=False)

    def is_plain_text(self) -> bool:
        return self._schema.is_plain_text()

    def name(self) -> str:
        return self._schema.name()

    def json_schema(self) -> dict[str, Any]:
        return self._flat

    def is_strict_json_schema(self) -> bool:
        return True

    def validate_json(self, json_str: str) -> Any:
        text = str(json_str or "")
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else text
        return self._schema.validate_json(candidate)
```

- 文件顶部 `import jsonref` 加进 import 段。

- L162-235 `_run_stage()` 内部构造 `Agent(...)`：保留 `output_type=_JsonOutputSchema(output_type)`。**不动**调用形态。

- L361-385 `_build_model()`：在创建 `OpenAIChatCompletionsModel(...)` 之前给 `AsyncOpenAI(...)` 加 `default_query` 或在 `ModelSettings` 加 `extra_args`，按 Design Correction §1 实测决定。**实测命令**：
  ```bash
  cd .worktrees/unified-agent-runtime
  uv run python -c "from agents import ModelSettings; print(sorted(ModelSettings.model_fields.keys()))"
  ```
  - 若输出含 `extra_args`：在 `_build_model()` 返回前包 `model_settings = ModelSettings(extra_args={"chat_template_kwargs": {"enable_thinking": False}})`，并把 `model_settings` 传给所有 `Agent(...)` 构造。
  - 若不含：用 `AsyncOpenAI(base_url=..., api_key=..., default_query=None)` + 在 `_runner.run()` 调用前 monkey-patch `client.chat.completions.create` 注入 `extra_body={"chat_template_kwargs":{"enable_thinking":False}}`（OpenAI Python SDK ≥1.40 支持 `extra_body`）。

- **新增 import**：`from openai.types.chat.completion_create_params import CompletionCreateParams` (仅当用 extra_body 路径)。

#### `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`

- L100-145 构造 `Agent`：
  - 把 `OpenAIResponsesModel(...)` 改成 `OpenAIChatCompletionsModel(...)`（Responses API 只 OpenAI 原生有，qwen3.6 不能用）
  - 给 Agent 加 `output_type=_JsonOutputSchema(SocialEventPayload)`（即复用 pulse 那个 wrapper，建议把它移到 `_shared.py` 一并 PR 3 收敛）
  - 给 `Agent(...)` 加 `model_settings=ModelSettings(...)` 含 enable_thinking 路径
- L143 `model_settings=ModelSettings(max_retries=0, ...)` 改为复用 PR 3 的 `default_model_retry_settings()`（PR 3 落地之前先就地写 `max_retries=2` 占位）。

#### `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py`

- L103-108 构造 `Agent`：
  - 加 `output_type=_JsonOutputSchema(WatchlistHandleSummaryPayload)` （之前完全没传 output_type！）
  - `OpenAIResponsesModel` → `OpenAIChatCompletionsModel`
  - 加 `model_settings` enable_thinking + retry
- L226-248 `_coerce_summary_payload`：保留逻辑，**但** 在 markdown 路径触发时给 audit 加 `"parse_mode": "markdown_fallback"` 字段（PR 2 的列）；非 markdown 路径写 `"parse_mode": "strict"`。

#### `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`

- L23 `AnalystOpinion.model_config`：`extra="forbid"` → `extra="ignore"`。
- L43 `CritiqueReport.model_config`：同上。
- L58 `FinalDecision.model_config`：同上。
- L27 `AnalystOpinion.confidence`：保留 `Field(ge=0, le=1)`，但**新增** field_validator clamp：
  ```python
  @field_validator("confidence", mode="after")
  @classmethod
  def _clamp_confidence(cls, value: float) -> float:
      return max(0.0, min(1.0, float(value)))
  ```
- L48 `CritiqueReport.confidence_ceiling`：同样加 `_clamp_confidence_ceiling` validator。
- L62 `FinalDecision.confidence`：同样加 clamp validator。
- L137 `_clean_text(value: str)`：加 `<think>` 残留剥离（Design Correction §10）：
  ```python
  def _clean_text(value: str) -> str:
      stripped = re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL)
      return stripped.strip()
  ```
  保留原来的 `.strip()` 行为，仅在前面加 `<think>...</think>` 剥离。文件顶部已 `import re`，不动 imports。

#### `src/gmgn_twitter_intel/domains/pulse_lab/interfaces.py`

- 找到 `PULSE_DECISION_SCHEMA_VERSION = "pulse_decision_v1"`，改为 `"pulse_decision_v2"`（Design Correction §6）。这一改动让 `pulse_harness_hash()` 自动 bump，eval 表自动按新 harness 隔离 PR 1 前后的数据。
- 同时**不**升 `PULSE_DECISION_PROMPT_VERSION`（PR 1 没改 prompt 文字）。
- 同时**不**升 `PULSE_GATE_VERSION`（PR 1 没改 gate 逻辑）。

#### `src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py`

- L83 `ExtractedEntity`（或类似类）`model_config`：`extra="forbid"` → `"ignore"`。
- L91 同上（第二个 BaseModel 子类）。
- L102 `SocialEventPayload.model_config`：`extra="forbid"` → `"ignore"`。
- 业务约束保留（如有 `@model_validator` 不动）。Design Correction §8。

#### `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`（新文件，~90 行）

```python
"""Instructor-backed safety net for openai-agents-python SDK call failures.

设计原则：
- 不参与正常成功路径。SDK Runner.run 成功直接 return。
- 只在 ModelBehaviorError / Pydantic ValidationError 时启动。
- 用独立的 AsyncOpenAI 实例避免污染 SDK 主路径。
"""
from __future__ import annotations

import logging
from typing import Any

import instructor
from agents import Agent, RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from openai import AsyncOpenAI
from pydantic import ValidationError

_logger = logging.getLogger(__name__)


class InstructorSafetyNet:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_retries: int = 2,
        enabled: bool = True,
    ) -> None:
        # 独立 client，避免 patch 污染 SDK 主路径
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._inst = instructor.from_openai(self._client, mode=instructor.Mode.JSON)
        self._model = model
        self._max_retries = max_retries
        self._enabled = enabled

    async def run_with_safety_net(
        self,
        *,
        agent: Agent,
        input_payload: Any,
        run_config: RunConfig,
    ) -> tuple[Any, dict[str, Any]]:
        """主路径：SDK Runner.run. 失败兜底：Instructor reask."""
        try:
            result = await Runner.run(
                agent, input_payload, run_config=run_config, max_turns=1
            )
            return result.final_output, {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
            }
        except (ModelBehaviorError, ValidationError) as exc:
            if not self._enabled:
                raise
            _logger.warning(
                "agent_output_invalid_falling_back_to_instructor agent=%s err=%s",
                getattr(agent, "name", "?"),
                str(exc)[:200],
            )
            messages = self._rebuild_messages(agent, input_payload, str(exc))
            obj = await self._inst.chat.completions.create(
                model=self._model,
                messages=messages,
                response_model=type(agent.output_type._schema._output_type)  # noqa
                if hasattr(agent.output_type, "_schema") else agent.output_type,
                max_retries=self._max_retries,
            )
            return obj, {
                "safety_net_used": True,
                "safety_net_retries": self._max_retries,
                "parse_mode": "instructor_reask",
            }

    @staticmethod
    def _rebuild_messages(agent: Agent, input_payload: Any, error_text: str) -> list[dict]:
        """从 Agent.instructions + 原 input 重建 messages；附加 error 让 instructor reask."""
        system = str(getattr(agent, "instructions", "") or "")
        user = input_payload if isinstance(input_payload, str) else str(input_payload)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {
                "role": "user",
                "content": (
                    f"Your previous response failed schema validation: {error_text[:500]}. "
                    "Return JSON that matches the schema exactly. No markdown fences."
                ),
            },
        ]
```

#### `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`（调用点）

- L162-235 `_run_stage()`：把 `result = await self._runner.run(...)` 替换为 `final_output, audit_extra = await self._safety_net.run_with_safety_net(...)`，将 `audit_extra` 合并入 `StageRunAudit.trace_metadata_json` 与新增 `safety_net_used` / `safety_net_retries` 字段。
- `OpenAIAgentsPulseDecisionClient.__init__` 加 `safety_net: InstructorSafetyNet | None = None` 参数，default None 时构造一个（用同 base_url/api_key/model）。

#### `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`

- 找到 `OpenAIAgentsPulseDecisionClient(...)` 构造点（grep 已知是 `providers_wiring.py:34` import，~ `:296` 包装 client）。在构造前实例化：
  ```python
  pulse_safety_net = InstructorSafetyNet(
      base_url=settings.llm.base_url,
      api_key=settings.llm.api_key,
      model=settings.llm.pulse_agent_model,
      max_retries=settings.llm.instructor_max_retries,
      enabled=settings.llm.instructor_safety_net_enabled,
  )
  pulse_client = OpenAIAgentsPulseDecisionClient(..., safety_net=pulse_safety_net)
  ```
- 同样为 social_event / watchlist 构造各自的 SafetyNet 实例（用各自 model）。

#### `src/gmgn_twitter_intel/app/settings.py`

- `LlmConfig` 加字段：
  ```python
  instructor_safety_net_enabled: bool = True
  instructor_max_retries: int = 2
  ```
- `~/.gmgn-twitter-intel/config.yaml` 文档样例（**不**写入用户 home，只在 README 里）：
  ```yaml
  llm:
    instructor_safety_net_enabled: true
    instructor_max_retries: 2
  ```

### Tests（PR 1 必加）

#### Unit

- `tests/integrations/openai_agents/test_json_output_schema.py::test_replace_refs_flattens_ref` —
  取 `FinalDecision.model_json_schema()` → `_JsonOutputSchema(FinalDecision).json_schema()`，断言：
  - 返回结果可 `json.dumps()` 序列化无异常
  - 字符串内 `"$ref"` 出现 0 次
  - `"$defs"` 出现 0 次（已展平）
  - 字段 `route.enum == ["cex","meme","research_only"]` 仍在
- `test_is_strict_json_schema_returns_true` — 断言 `_JsonOutputSchema(AnalystOpinion).is_strict_json_schema() is True`
- `test_validate_json_extracts_balanced_block` — 喂 `"prose before {\"route\":\"meme\",...} prose after"` → 正常返回 `AnalystOpinion`
- `test_clamp_confidence_above_one` — Pydantic 构造 `AnalystOpinion(confidence=1.5, ...)` 不抛 ValidationError 且 `.confidence == 1.0`
- `test_extra_ignore_drops_unknown_field` — 构造 `AnalystOpinion(**valid_data, schema_version="x")` 不抛 ValidationError 且 `.schema_version` 不存在
- `test_clean_text_strips_think_block` — `_clean_text("<think>aaa</think>real content")` 返回 `"real content"`（Design Correction §10）
- `test_social_event_payload_extra_ignore` — 构造 `SocialEventPayload(**valid_data, schema_version="x")` 不抛 ValidationError（Design Correction §8）

#### 必须翻转的已有测试

- `tests/test_pulse_decision_agent_client.py:260` — `assert schema.is_strict_json_schema() is False` → `is True`
- `tests/test_pulse_decision_agent_client.py:267,275` — 同上路径上 schema 实例的断言保留 schema 类型校验，但取消所有 `is False` 假设
- 同时加：在 `:260` 那个测试里追加 `assert "$ref" not in json.dumps(schema.json_schema())` 验证 jsonref 展平生效

#### _runner mock 改造（Design Correction §11）

- `tests/unit/test_pulse_decision_agent_client.py` / `test_social_event_agent_client.py` / `test_watchlist_summary_agent_client.py`：把 `FakeRunner.run(...)` 返回 `RunResult(...)` 改为 mock `FakeSafetyNet.run_with_safety_net(...)` 返回 `(final_output, {"safety_net_used": False, "safety_net_retries": 0, "parse_mode": "strict"})` tuple。Client 构造时注入 `safety_net=FakeSafetyNet()` 而不是 `runner=FakeRunner()`。

#### Integration（需要 live big9er.com，标记为 `@pytest.mark.live_llm`）

- `tests/integrations/openai_agents/test_pulse_pipeline_live.py::test_analyst_strict_enforces_enum` —
  喂 system prompt 显式要求 `recommendation="research"`（非法 enum），断言返回的 `AnalystOpinion.recommendation` ∈ {trade_candidate, watchlist, ignore}。
- `test_pulse_pipeline_safety_net_triggers_on_truncated` —
  喂 max_tokens 极小让模型输出被截断 → SDK 抛 `ModelBehaviorError` → safety net 接 → 重试 max_retries=2 内成功。断言返回 audit `safety_net_used=True`。
- `test_pulse_pipeline_safety_net_disabled_propagates` — 同上但 `enabled=False`，断言异常上抛不被吞。

### Migration（无）

PR 1 不动 DB schema。新加的 `safety_net_used`/`retries` 是 PR 2 的事。PR 1 阶段先把这两字段写到 `trace_metadata_json` 里（jsonb），PR 2 alembic 落定后切到独立列。

### 验证（PR 1 内）

- [ ] `uv run ruff check .` pass
- [ ] `uv run pytest tests/integrations/openai_agents/ -k 'not live_llm'` pass
- [ ] `uv run pytest tests/integrations/openai_agents/ -m live_llm`（live test，需 BIG9ER_API_KEY）pass
- [ ] 启动应用、`docker compose up -d`、跑 1 小时
- [ ] DB 查询验证：
  ```sql
  -- 取 PR 1 部署后 1 小时的 run
  WITH recent AS (
    SELECT * FROM pulse_agent_runs WHERE started_at_ms > <deploy_ts_ms>
  )
  SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status='failed') AS failed,
    COUNT(*) FILTER (WHERE error LIKE 'Invalid JSON%') AS invalid_json,
    COUNT(*) FILTER (WHERE trace_metadata_json->>'safety_net_used'='true') AS used_safety_net
  FROM recent;
  ```
  期望：`invalid_json / total <= 0.05`、`used_safety_net / total <= 0.30`。

---

## PR 2 — Audit columns migration

### 文件

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260516_NNNN_agent_safety_net_audit.py`（新 revision）

  ```python
  """agent safety_net audit fields

  Revision ID: <auto>
  Revises: <head>
  Create Date: 2026-05-16 ...
  """
  from alembic import op
  import sqlalchemy as sa

  revision = "<auto>"
  down_revision = "<latest_head>"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.add_column(
          "pulse_agent_run_steps",
          sa.Column("safety_net_used", sa.Boolean(), nullable=False, server_default=sa.false()),
      )
      op.add_column(
          "pulse_agent_run_steps",
          sa.Column("safety_net_retries", sa.Integer(), nullable=False, server_default="0"),
      )
      op.add_column(
          "pulse_agent_run_steps",
          sa.Column("parse_mode", sa.Text(), nullable=False, server_default="strict"),
      )
      # 同样给 model_runs（social_event）和 watchlist_handle_summary_runs 加
      op.add_column("model_runs", sa.Column("safety_net_used", sa.Boolean(), nullable=False, server_default=sa.false()))
      op.add_column("model_runs", sa.Column("safety_net_retries", sa.Integer(), nullable=False, server_default="0"))
      op.add_column("model_runs", sa.Column("parse_mode", sa.Text(), nullable=False, server_default="strict"))
      op.add_column("watchlist_handle_summary_runs", sa.Column("safety_net_used", sa.Boolean(), nullable=False, server_default=sa.false()))
      op.add_column("watchlist_handle_summary_runs", sa.Column("safety_net_retries", sa.Integer(), nullable=False, server_default="0"))
      op.add_column("watchlist_handle_summary_runs", sa.Column("parse_mode", sa.Text(), nullable=False, server_default="strict"))


  def downgrade() -> None:
      for tbl in ("pulse_agent_run_steps", "model_runs", "watchlist_handle_summary_runs"):
          op.drop_column(tbl, "parse_mode")
          op.drop_column(tbl, "safety_net_retries")
          op.drop_column(tbl, "safety_net_used")
  ```

### 写入点（PR 2 紧随 PR 1 合入）

- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`（grep `insert_agent_run_step` 找位置）：写入 `pulse_agent_run_steps` 时把 `audit_extra` 里的三字段直接 map 到独立列。
- `src/gmgn_twitter_intel/domains/social_enrichment/repositories/enrichment_repository.py:221` `complete_social_event_job` 同上 map 到 `model_runs`。
- `src/gmgn_twitter_intel/domains/watchlist_intel/repositories/watchlist_intel_repository.py` `insert_summary_run` 同上。

### Migration acceptance

```bash
uv run alembic upgrade head
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "\d pulse_agent_run_steps" | grep -E "safety_net|parse_mode"
# 期望看到 3 行新列定义
```

### Rollback

```bash
uv run alembic downgrade -1
```

3 张表的 3 列被 drop。**不会**丢失任何业务数据（这些列是新增的 audit，老数据没有它们）。

---

## PR 3 — 三 client 共享 utils + Social/Watchlist 补 output_type 与 retry

### 文件

- `src/gmgn_twitter_intel/integrations/openai_agents/_shared.py`（新文件）：
  - 抽 `_api_base`、`_is_openai_base_url`、`_sha256`、`_trace_id`（统一截 32 hex）、`setup_tracing_once`
  - 抽 `default_model_retry_settings()` 返回 `ModelRetrySettings(max_retries=2, backoff={...}, policy=retry_policies.any(...))` 与 `pulse_decision_agent_client.py:378-383` 配置一致
  - 把 PR 1 写的 `_JsonOutputSchema` 也搬到这里（PR 1 写在 pulse 文件里只是过渡，PR 3 上移）
  - 抽 `build_audit_dict(...)` 公共 audit dict 构造器
- 三 client 改 import 从 `_shared` 拿。
- LOC 期望：3 client 总和减少 ≥30%（spec §7.1 M7 验收）。

### Tests

- `tests/integrations/openai_agents/test_shared_utils.py::test_default_retry_settings_covers_429_5xx`
- `tests/integrations/openai_agents/test_shared_utils.py::test_trace_id_is_deterministic_from_run_id`

---

## PR 4 — Worker lease / stale 回收

### 文件

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:493-505`：超时路径调整为先 mark_failed（独立连接 + statement_timeout 短）再 raise（spec M4）
- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`：新增 `_reclaim_expired_leases_once()` 每 `run_once` 头部扫一次（spec M5）
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`：`mark_stale_agent_runs_failed` 改用独立事务 + 独立 statement_timeout

### Tests

- `tests/domains/pulse_lab/test_pulse_candidate_worker_timeout.py::test_agent_timeout_marks_job_failed_within_timeout`（模拟 agent timeout，断言 job status='failed' 且无 `stale_running_timeout` error）
- `tests/domains/watchlist_intel/test_handle_summary_lease.py::test_expired_lease_reclaimed_on_next_run_once`

---

## PR 5 — request_json 全文 + 跨 worker correlation_id

### 文件

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:426`：`request_json` 从 `{context_hash}` 改为 `{context_hash, context, factor_snapshot}`，过 `_sanitize_for_audit()`（新增于 `_shared.py`）剥 secret 模式
- `src/gmgn_twitter_intel/platform/db/alembic/versions/<next>_correlation_id_columns.py`：在 `events`/`enrichment_jobs`/`pulse_agent_jobs`/`watchlist_handle_summary_jobs`/`*_runs` 加 `correlation_id text` nullable
- `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py` 生成 `uuid7()` 写入 events.correlation_id
- 所有下游 enqueue 路径透传

### Tests

- `tests/domains/pulse_lab/test_pulse_request_json_replay.py::test_request_json_full_text_replays_prompt`
- `tests/integration/test_correlation_id_propagates_end_to_end.py::test_event_to_pulse_to_watchlist_share_correlation_id`

---

## PR 6 — Eval suite 覆盖 failed run + CLI eval-diff

### 文件

- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_harness.py`：`build_pulse_deterministic_eval_case` 加 fail run 分支（spec S2）
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_harness_eval.py:57`：`grade_pulse_deterministic_eval_case` 加 `reason_class` violation 类型
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:548-619`：失败路径也调 `build_pulse_deterministic_eval_case` 写入 eval 表
- `src/gmgn_twitter_intel/app/cli.py` 新加 `pulse eval-diff` 命令

### Acceptance

```bash
uv run gmgn-twitter-intel pulse eval-diff --since 7d --baseline harness_hash=sha256:... --candidate harness_hash=sha256:...
# 期望输出 markdown 表，per-rule pass rate diff
```

---

## PR 7 — OTel GenAI tracing + Langfuse v4

### 文件

- `docker-compose.yml`：加 langfuse-v4 service（postgres backend 复用现有 PG 实例新 db）
- `src/gmgn_twitter_intel/platform/observability/otel_setup.py`：新文件，set OTLP exporter 到 langfuse
- 三 agent client 在 `Runner.run` 前后包 OTel span，attach 业务属性 `run_id / candidate_id / route / harness_hash / safety_net_used / parse_mode`

### Acceptance

```bash
# 部署后访问
open http://localhost:3001  # langfuse v4 UI
# 期望：能看到 pulse pipeline trace，三 stage 同一 trace_id，每 stage span 含 gen_ai.usage.input_tokens / cached_input_tokens
```

---

## PR 8 — Prompt 文件化

### 文件

- `src/gmgn_twitter_intel/domains/pulse_lab/prompts/{analyst,critic,judge}_{cex,meme,research_only}.md` 9 个新文件
- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_stage_prompts.py:pulse_stage_prompt()`：改为 `load_prompt(path).render(**context)`

### Tests

- `tests/integrations/openai_agents/test_pulse_stage_prompts_files.py::test_all_route_stage_files_exist`
- `tests/integrations/openai_agents/test_pulse_stage_prompts_files.py::test_loaded_prompt_renders_without_kwargs_error`

---

## PR 9 — Critic veto 阈值化 + completeness gate 复用

### 前置硬性要求

PR 1+2+3 上线 ≥7 天，`pulse_agent_eval_cases` 含 ≥1,000 个 post-fix sample，PR 6 的 CLI 能跑出 baseline。

### 文件

- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`：critic 不再 binary veto，改为把 `confidence_ceiling` clamp 到 judge 输出（spec S6）
- `src/gmgn_twitter_intel/domains/_shared/completeness_gate.py`（新文件，从 `pulse_candidate_worker._factor_completeness` 抽）
- enrichment / watchlist worker 在调 agent 前先打分（spec S7）

---

## Rollout order

1. **PR 1 + PR 2 一起合**（PR 2 是 migration，PR 1 是逻辑改造，独立列写入由 PR 2 完成，PR 1 期间 audit 字段写 jsonb）。
2. 应用 migration：`uv run alembic upgrade head`
3. Deploy 新代码：`docker compose build app && docker compose up -d`
4. **24 小时观察期**：
   - SQL 查询 §"PR 1 内验证" 块
   - 期望 `invalid_json / total <= 0.05`、`used_safety_net / total <= 0.30`
5. 满足后 PR 3-5 并行合（互不依赖）
6. PR 6-8 串行合
7. PR 9 等 PR 6 满 7 天再合

## Rollback

- **PR 1 回滚**：单行改 `_JsonOutputSchema.is_strict_json_schema` 返回 `False`、`json_schema()` 改回 `self._schema.json_schema()`（不展平）。redeploy。
- **PR 2 回滚**：`uv run alembic downgrade -1`，3 张表 drop 3 列。
- **PR 1 + PR 2 同时回滚**：先回滚 app（PR 1 revert + deploy）再回 migration。
- **不可回滚**：jsonref 依赖一旦引入不必移除（无 transitive 风险）。

## Acceptance test commands

Mapping spec §7 验收条件到具体命令：

### 必修（M1, M1b, M2-M8）

```bash
# M1.a strict + jsonref（spec §7.1）
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE error LIKE 'Invalid JSON%') AS invalid_json,
  ROUND(100.0 * COUNT(*) FILTER (WHERE error LIKE 'Invalid JSON%') / COUNT(*), 1) AS invalid_pct
FROM pulse_agent_runs
WHERE started_at_ms > (EXTRACT(EPOCH FROM now() - interval '7 days')*1000)::bigint
  AND harness_version = 'pulse-decision-harness-v2';  -- 新 harness
"
# 期望: invalid_pct < 5.0
```

```bash
# M1.b extra=ignore - schema_version 不再触发错误
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT COUNT(*) FROM pulse_agent_runs
WHERE error LIKE '%schema_version%' AND started_at_ms > <deploy_ts_ms>;
"
# 期望: 0
```

```bash
# M1.c confidence clamp - 全部 in [0,1]
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT MIN((response_json->>'confidence')::float), MAX((response_json->>'confidence')::float)
FROM pulse_agent_run_steps WHERE status='ok' AND started_at_ms > <deploy_ts_ms>;
"
# 期望: min >= 0, max <= 1
```

```bash
# M1.d enable_thinking=false - 输出无 <think> 残留
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT COUNT(*) FROM pulse_agent_run_steps
WHERE response_json::text LIKE '%<think>%' AND started_at_ms > <deploy_ts_ms>;
"
# 期望: 0
```

```bash
# M1b Instructor safety net - 命中率 < 10%
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT
  COUNT(*) FILTER (WHERE safety_net_used) AS used,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE safety_net_used) / COUNT(*), 1) AS used_pct
FROM pulse_agent_run_steps
WHERE started_at_ms > (EXTRACT(EPOCH FROM now() - interval '7 days')*1000)::bigint;
"
# 期望: used_pct < 10.0（首周 < 25.0 即可，稳定后必须 < 10.0）
```

### 应修（S1-S4, S6, S7）

PR 6-9 各自的 acceptance 在对应 PR 段内。

## Verification

完整验证 artefact 在 PR 全部合入后建立 `docs/superpowers/plans/active/2026-05-16-unified-agent-worker-runtime-verification-cn.md`，包含：

1. PR 1+2 合并 24h / 7d / 30d 三个时间窗的失败率对比表
2. safety_net 命中率时序图（如果稳定 >30% 触发复盘条款）
3. eval pass rate post-fix vs pre-fix（来自 PR 6 CLI）
4. token cost 对比（M1.d 关 thinking 后 output token 应下降）
5. 用 §7.3 的"全局指标"表填实际值

verification artefact 必须存在才能宣告本 plan 完成。

---

## 风险登记（开工前签字）

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| **A1**：`enable_thinking=false` 注入不生效 | `ModelSettings.extra_args` 不存在且 `default_query` 不传到上游 | Design Correction §1 三选一，PR 1 把选择和验证命令写进 PR 描述 |
| **A2**：jsonref 展平后的 schema 太大触发 token 浪费 | flat schema > 5KB 重复写入每次 prompt | PR 1 测时记录 schema size 写到 trace_metadata，若 >5KB 在 PR 1 内加压缩（删 `title`/`description` 等冗余字段） |
| **A3**：Instructor patch 污染主路径 | safety_net 用错 client 实例，patch 到 SDK 主路径 | Design Correction §4 强制独立 AsyncOpenAI 实例，PR 1 加单测 `test_safety_net_does_not_patch_main_client` |
| **A4**：harness_hash 不 bump 导致新老数据混在一起 | `agent_harness.py` 计算 hash 输入不含 strict / extra 行为 | Design Correction §6 PR 1 阶段检查；若不 bump 则手动 bump `PULSE_DECISION_SCHEMA_VERSION` 一次性触发 |
| **A5**：PR 1 部署后失败率短期上升 | 任何 silent 假设被 break | 24h 观察窗 + 单行回滚预案；如果 24h 失败率 > 部署前 + 5%，立即 revert PR 1 并复盘 |
| **A6**：Critic 阈值化（PR 9）后过度激进 → high_conviction 占比反弹 | S6 阈值选太低 | PR 9 上线前用 PR 6 的 eval-diff CLI 做 dry run；上线后 24h 监控 `pulse_candidates.decision_json->>'recommendation'` 分布，超过 high_conviction > 10% 触发回滚 |

签字（每行打勾后可开工）：
- [ ] Spec 作者确认 §5 方案细节
- [ ] 实施人确认 Pre-flight 全过
- [ ] 评审人确认 PR breakdown 与依赖图
- [ ] 运维确认 docker compose / alembic / Langfuse v4 部署可行
