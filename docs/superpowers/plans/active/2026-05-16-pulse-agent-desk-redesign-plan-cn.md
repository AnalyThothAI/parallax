# Pulse Agent Desk 重设计 — 实施 Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**: 按 owning spec v2 把 Pulse Decision Pipeline 从 `Analyst → Critic → Judge` 三 stage 单 LLM 通道 hard cut 改为 `Investigator → DecisionMaker` 两调用架构。Investigator 带 3 个核心工具基于事实追问，输出结构化多空 observation；DecisionMaker 综合并产出含 narrative + 文本 playbook 的 FinalDecision。**Phase 1 净增 0 张新表、0 个新 worker、0 个 deferred 调用**。

**v2 变更**：v1 plan 被 3 路 reviewer 审出 14 high-severity bug。v2 内联修复全部 5 个 P0 阻塞 + 11 个 P1 必修。task 从 15 缩到 12，移除 outcome / NarrativeBriefWorker / 复杂 playbook 字段相关任务（独立 phase 2 spec）。

**Architecture**: `pulse_lab` 拥有领域决策、gate、worker、repository、read model；`integrations/openai_agents` 只实现 OpenAI Agents SDK adapter + 工具函数。不增 worker、不增表。

**Tech Stack**: Python 3.13, PostgreSQL, Alembic, Pydantic v2, openai-agents-python SDK, pytest, ruff, React/Vitest 触达前端类型 + legacy 占位卡。

---

## Status

- **Status**: Implementation complete; local verification passed 2026-05-17. See `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-verification-cn.md`.
- **Date**: 2026-05-16
- **Owning spec**: `docs/superpowers/specs/active/2026-05-16-pulse-agent-desk-redesign-cn.md` (v2)
- **Worktree**: `.worktrees/pulse-agent-desk-redesign/`
- **Branch**: `codex/pulse-agent-desk-redesign`
- **Prerequisite**: `2026-05-16-unified-agent-worker-runtime-cn.md` §5.1 M1 schema hard fix（jsonref 展平 + strict + extra=ignore + enable_thinking=false）必须先合入 main。本 plan 不重复 M1 工作。

---

## Pre-flight

- [ ] 确认 prerequisite 已合入 main:
  ```bash
  cd /Users/qinghuan/Documents/code/parallax
  grep -n "is_strict_json_schema" src/parallax/integrations/openai_agents/pulse_decision_agent_client.py
  # 应看到 return True，且 import 含 jsonref。若未合入，停手做 M1。
  ```
- [ ] Create worktree:
  ```bash
  git worktree add .worktrees/pulse-agent-desk-redesign -b codex/pulse-agent-desk-redesign main
  cd .worktrees/pulse-agent-desk-redesign
  ```
- [ ] Verify clean workspace + baseline 测试:
  ```bash
  git status --short
  uv run ruff check .
  uv run pytest -x --timeout=60
  cd web && npm test -- --run && cd ..
  ```
- [ ] DB snapshot:
  ```bash
  mkdir -p ~/.parallax/backups
  docker exec parallax-postgres-1 pg_dump -U parallax_app -d parallax -Fc -f /tmp/pre-desk-redesign.dump
  docker cp parallax-postgres-1:/tmp/pre-desk-redesign.dump ~/.parallax/backups/
  ```

---

## Open Questions（实施前必须锁定）

写入 `docs/generated/pulse-agent-desk-decisions.md`：

- [ ] **OQ-1 Investigator tool call 上限**：默认 cex=3, meme=5。抽样近 30 天 pulse_agent_run_steps 估算 analyst stage 实际"信息追问需求"分布后锁定。
- [ ] **OQ-2 DecisionMaker fallback tool**：默认启用 `get_target_recent_tweets`, max_turns=3。plan 阶段决定是否禁用（若 InvestigationReport observation 充分）。
- [ ] **OQ-3 GMGN description backfill**：默认不做，新 profile 即时填。若 Phase 1 上线后 30% Investigator 拿到 description=null 影响输出，启动 admin 命令补 refresh。
- [ ] **OQ-4 `_FORBIDDEN_EXECUTION_RE` 反测**：对 `watch_signals / exit_triggers` 文本样本 + `monitoring_horizon` enum 跑一次 regex 反测，记录无误伤：
  ```bash
  uv run python -c "
  from parallax.domains.pulse_lab.types.agent_decision import contains_trading_execution_instruction
  cases = ['1h', '4h', '24h', 'has_playbook',
           'watch_signals', 'exit_triggers', 'monitoring_horizon',
           '关注 watched_author 接力', '流动性回撤 >20% 触发退出',
           '提及量停止增长', '关键作者抛售']
  for c in cases:
      r = contains_trading_execution_instruction(c)
      print(f'{r}\t{c}')
  "
  # 任何 True 都说明字段值需改名
  ```
- [ ] **OQ-5 `abstain_critic_veto` enum 值处置**：推荐保留（新写禁用、老行可读、不动 CHECK）。锁定。
- [ ] **OQ-6 prompt 文件命名**：推荐 `prompts/{investigator,decision_maker}.md` 单文件 route 段内联。锁定。

提交决策文档后再进入 Task 1。

---

## Invariants（hard cut 一次性，不双写；v2 新增 13 条采纳 reviewer P0/P1 修正）

### 原 invariants（保留）

- [ ] 不引入 LangGraph / CrewAI / autogen / 任何新 agent framework
- [ ] 不引入 multi-provider 自动 fallback / multi-model 分层
- [ ] 不引入 buy / sell / position / stop loss / target price / leverage 等执行性字段
- [ ] 不破坏 Kappa/CQRS：events / token_intents / market_ticks / asset_identity_* 仍是 only truth
- [ ] 不破坏单冷写边界：现有 14 worker 不动
- [ ] 不修改 `SocialEventExtractionAgent / WatchlistHandleSummaryAgent` 及其 worker
- [ ] 不修改 `_factor_completeness` / `hard_blocked` pre-LLM gate
- [ ] 不修改 `pulse_candidate_worker` 的 job queue / edge state / run budget / advisory lock 机制；只换 LLM call 部分
- [ ] 不保留 `AnalystOpinion / CritiqueReport / FinalDecision v1` 任一兼容层
- [ ] 不保留 `pulse_stage_prompts.py` 的 `_ROUTE_FOCUS / _STAGE_FOCUS / pulse_stage_prompt` 函数
- [ ] 不保留 `pulse_candidates.narrative_type` 列
- [ ] 不在 Token Radar 列表读路径 JOIN 任何 pulse 表
- [ ] 不动 `pulse_status` 现有展示语义
- [ ] 所有 prompt 把 selected posts / usernames / URLs / quoted text 当 data 不是 instruction

### v2 新增 invariants（采纳 reviewer 修正）

- [ ] **[P0-1]** alembic `ALTER TABLE ADD CONSTRAINT CHECK` 必须用 `NOT VALID` 子句，不能 immediate validate；downgrade 同样 NOT VALID。否则现有 24h 1580+ 老 stage 行会触发 migration 报错
- [ ] **[P0-2]** DROP `pulse_candidates.narrative_type` 必须**先**修以下文件的 INSERT/SELECT 引用，再 alembic 执行 DROP，二者**同 task 内同 PR 一次性提交**：
  - `domains/pulse_lab/runtime/pulse_candidate_worker.py:586,1041`
  - `domains/pulse_lab/repositories/pulse_repository.py:599,635,660,698`
  - `domains/pulse_lab/read_models/signal_pulse_service.py:163`
  - `domains/notifications/services/notification_rules.py:527`
- [ ] **[P0-3]** 新 worker 注册时必须在 `platform/config/settings.py::WorkersSettings`（extra="forbid"）和 `default_workers_yaml()` 模板同步加 Field。**v2 不新增 worker** → 此约束在本 plan 不触发但保留为模板规范
- [ ] **[P0-4]** `signal_pulse_service.py:_stages_for` 的 empty dict keys 必须同步改新 enum；否则新 stage 行被静默丢弃
- [ ] **[P0-5]** `signal_pulse_service._decision()` 必须扩展字段集合，暴露 `narrative_archetype / narrative_thesis_zh / bull_view / bear_view / playbook / evidence_event_urls` 到 API；否则前端 UI 卡无数据
- [ ] **[P0-6]** Tool call 上限通过 worker 侧 `RunContext.usage.tool_calls_count` 控制，**不**通过 SDK `max_turns`（1 turn 含多 parallel call）
- [ ] **[P1-1]** `InvestigationReport` 不含 `tool_call_summary` 字段；tool 元数据由 worker 从 `RunResult.raw_responses` 提取写到 `pulse_agent_run_steps.input_json.tool_calls`
- [ ] **[P1-2]** Hallucination guard 通过 `ToolResult` Protocol + worker 维护的 `contributed_event_ids` set 实现，**不**靠 deep nested raw_responses 提取
- [ ] **[P1-6]** SurfaceCard 降级顺序：先 Bear 后 Bull 后 Narrative，**始终保 Playbook + Header + Recommendation + Links**
- [ ] **[P1-7]** `evidence_event_urls` 在 worker 持久化决策前**预先 build**（JOIN `events.event_payload_json->>'url'`），写入 `decision_json.evidence_event_urls`。Surface card 直接读，不在渲染时查
- [ ] **[P1-8]** Notification signature 只 hash 稳定决策维度（recommendation / bull_view.strength / bear_view.strength / narrative_archetype / has_playbook），**不**含任何自由文本
- [ ] **[P1-9]** 三个新 Pydantic 字段长度约束（`narrative_thesis_zh` 30-300 / `narrative_archetype` ≤20 / `bull_view.thesis_zh` 非 absent 时非空）必须在 `@field_validator` 实现，**不**依赖 llama.cpp GBNF
- [ ] **[P1-10]** `2026-05-14-pulse-detail-redesign-cn.md` spec 在本 PR 合入时同步移到 `completed/`，因为本 spec stage 名变更隐式 obsolete 它
- [ ] **[P1-11]** 老 stage audit 行（stage ∈ analyst/critic/judge）在前端 PulseDetailView 渲染为 legacy 占位卡（stage 名 + status + latency 不解析 response_json），不报 JS error
- [ ] **[P1-12]** Rollback 步骤强制四步：停服务 → alembic downgrade → git revert → 启服务

---

## Current Code Anchors

| Area | Current anchor | Plan stance |
|---|---|---|
| Agent types | `src/parallax/domains/pulse_lab/types/agent_decision.py` | DELETE `AnalystOpinion / CritiqueReport`；NEW `InvestigationReport / BullBearView / TradePlaybook / ToolResult Protocol`；EXTEND `FinalDecision` |
| Stage prompts | `src/parallax/integrations/openai_agents/pulse_stage_prompts.py` | DELETE 整文件；NEW `src/parallax/domains/pulse_lab/prompts/{investigator,decision_maker}.md` + loader |
| Agent client | `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py` | DELETE `_run_stage` 三 stage 编排；NEW `run_investigation_then_decision`；wire tools + tool counter + hallucination guard |
| Worker | `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py` | 保留 queue/edge/budget；改 `_run_job` 调新 client + 删 narrative_type 写入 + build evidence_event_urls |
| Repository | `src/parallax/domains/pulse_lab/repositories/pulse_repository.py` | 删 narrative_type 列引用；扩 stage 枚举 |
| Read model | `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py` | `_stages_for` keys 改新枚举（**P0-4**）；`_decision()` 暴露新字段（**P0-5**）；删 narrative_type 读 |
| Eval grader | `src/parallax/domains/pulse_lab/services/agent_eval.py` | Hard cut grader 改为 v2（5 项）；v1 case 走 `status='legacy_skipped'` 不 panic |
| Notification | `src/parallax/domains/notifications/services/notification_rules.py` | DELETE `_pulse_body` 现有；NEW SurfaceCard 渲染器；signature 改为只 hash 稳定维度；删 narrative_type 写入 payload |
| GMGN provider | `src/parallax/integrations/gmgn/` (T1 grep 定位) | 加 `description` 字段映射 |
| Tools 目录 | （新建）`src/parallax/integrations/openai_agents/tools/` | NEW 3 个 `@function_tool` 包装的只读 SQL 函数 + `ToolResult` Protocol |
| Frontend | `web/src/lib/types/frontend-contracts.ts`, `web/src/features/signal-lab/model/pulseDetail.ts`, `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx` | 删 narrative_type；改 stage enum；扩 decision 字段；加 legacy 占位卡 |
| Frontend fixture/test | `web/src/features/signal-lab/test/fixtures/titty-pulse.ts`, `web/tests/component/...`, `web/tests/e2e/support/mockApi.ts` | 更新 fixture 无 narrative_type；新 stage 测试 |
| Migration | `src/parallax/platform/db/alembic/versions/` | 新 revision `20260516_NNNN_pulse_agent_desk_redesign.py`（NOT VALID CHECK）|
| Superseded spec | `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md` | 同 PR 移到 `completed/` |

---

## File-level Edits

### Task 1 — GMGN provider description 拉取修复

**Files:**
- Modify: `src/parallax/integrations/gmgn/` 下 GMGN profile 拉取文件（T1 内 grep 定位）
- Modify tests: 相关 unit test

- [ ] grep 定位:
  ```bash
  grep -rn "asset_profiles" src/parallax/integrations/gmgn/ | head -10
  grep -rn "description\|raw_payload" src/parallax/integrations/gmgn/ | head -10
  ```
- [ ] 找到 GMGN profile API response JSON 实际 key（curl + jq 确认是 `description / desc / about / token_info.description` 哪个）
- [ ] 在 mapper 加 description 提取（限长 ≤ 2000 字符）
- [ ] 同时检查 `twitter_username / twitter_url / website_url` 字段是否有 mapping 错位（DB 实测 LUCY 的 `twitter_username` 含 status URL 异常）；如有 bug 一并修
- [ ] 不做 backfill；新拉的进库即填

**Tests:**
- [ ] unit test `test_*_profile_client.py::test_description_extracted` (给 mock GMGN JSON → 校验 description 字段)
- [ ] 已有 profile worker integration test 至少 1 happy path 不退化

**Verification:**
```bash
uv run pytest tests/unit/integrations/gmgn/ -v
# 启 worker 跑 5 分钟看新 row 的 description 填充
docker exec parallax-postgres-1 psql -U parallax_app -d parallax -c "
  SELECT count(*) FILTER (WHERE description IS NOT NULL AND description != ''),
         count(*) AS total
  FROM asset_profiles
  WHERE status='ready' AND updated_at_ms > (extract(epoch from now() - interval '10 minutes') * 1000)::bigint;"
```

---

### Task 2 — `narrative_type` 列原子 hard cut + stage CHECK 改

**[P0-1, P0-2, P0-4 内联修复] 这是单 task 内强制原子的最大改动；必须 6 个文件同 commit 一起改，否则任一文件单独 merge 都会让 worker INSERT 报 column does not exist。**

**Files:**
- Add: `src/parallax/platform/db/alembic/versions/20260516_NNNN_pulse_agent_desk_redesign.py`（NNNN 取下一个连号）
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`（删 `narrative_type=_narrative_type_from_context(...)` 调用与导入）
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`（删 narrative_type 列 INSERT/SELECT，4 处）
- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`（删 narrative_type 读，1 处；改 `_stages_for` empty dict keys 为 `investigator/decision_maker/research_only_gate`）
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`（删 `_pulse_payload` 中 narrative_type 写入，1 处）
- Modify tests: `tests/unit/test_notification_rules.py`, `tests/unit/test_signal_pulse_service.py`, `tests/integration/test_pulse_repository.py`, `tests/integration/test_api_http.py`（11+ 处 narrative_type fixture 全删）

**alembic 操作清单**：

- [ ] alembic upgrade DROP 列:
  ```sql
  ALTER TABLE pulse_candidates DROP COLUMN narrative_type;
  ```
- [ ] alembic upgrade 改 stage CHECK，**带 `NOT VALID`**（reviewer P0-1）:
  ```sql
  ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT pulse_agent_run_steps_stage_check;
  ALTER TABLE pulse_agent_run_steps
    ADD CONSTRAINT pulse_agent_run_steps_stage_check
    CHECK (stage IN ('investigator', 'decision_maker', 'research_only_gate'))
    NOT VALID;
  -- NOT VALID 让 PG 不全表扫描验证老 analyst/critic/judge 行，仅约束新写
  ```
- [ ] alembic downgrade RESTORE 列 + 旧 CHECK，**同样 NOT VALID**:
  ```sql
  ALTER TABLE pulse_candidates ADD COLUMN narrative_type TEXT NOT NULL DEFAULT 'direct_token';
  ALTER TABLE pulse_agent_run_steps DROP CONSTRAINT pulse_agent_run_steps_stage_check;
  ALTER TABLE pulse_agent_run_steps
    ADD CONSTRAINT pulse_agent_run_steps_stage_check
    CHECK (stage IN ('analyst', 'critic', 'judge', 'research_only_gate'))
    NOT VALID;
  ```

**代码改动清单**（必须 commit 一起改）：

- [ ] `pulse_candidate_worker.py:586`：删 `narrative_type=...` kwarg；删 `_narrative_type_from_context` 函数（确认仅此一处使用）
- [ ] `pulse_candidate_worker.py:1041`：同上检查
- [ ] `pulse_repository.py:599`：upsert SQL 中删 `narrative_type` 列
- [ ] `pulse_repository.py:635`：INSERT 列名删
- [ ] `pulse_repository.py:660`：SELECT 列名删
- [ ] `pulse_repository.py:698`：同上检查
- [ ] `signal_pulse_service.py:163`：删 `"narrative_type": row.get("narrative_type")`
- [ ] `signal_pulse_service.py:84-86`：`_stages_for` empty dict 改 keys 为 `{"investigator": None, "decision_maker": None, "research_only_gate": None}`
- [ ] `notification_rules.py:527`：`_pulse_payload` 删 `"narrative_type": row.get("narrative_type")` 字段（不影响 dedup signature，因为 P1-8 改后 signature 不读它）

**测试改动清单**：

- [ ] `tests/integration/test_pulse_repository.py:1053,1071,1082,1207,1233`：删 fixture 中 `narrative_type='...'` 行
- [ ] `tests/integration/test_api_http.py:245,1103,1139,1188,1633`：同上
- [ ] `tests/unit/test_notification_rules.py:836`：同上
- [ ] `tests/unit/test_signal_pulse_service.py:244,372`：同上 + 加 stages dict keys 新枚举断言
- [ ] 新增 test `tests/integration/test_alembic_migrations.py::test_stage_check_not_valid`:
  - 创建一行 `stage='analyst'` 老数据
  - upgrade → 不报错（NOT VALID）
  - 试 INSERT 新行 `stage='analyst'` → CHECK violation
  - 试 INSERT 新行 `stage='investigator'` → 成功
- [ ] alembic 双向测试:
  - upgrade head → downgrade -1 → upgrade head

**Verification:**
```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run pytest tests/integration/test_alembic_migrations.py tests/integration/test_pulse_repository.py -v
grep -rn "narrative_type" src/ tests/ | grep -v "completed/" | grep -v "\.bak"
# 期望 0 行
```

---

### Task 3 — Pydantic types hard cut（InvestigationReport + extended FinalDecision + ToolResult Protocol）

**[H2/H3/H8/P1-2/P1-9 内联]**

**Files:**
- Modify (重写): `src/parallax/domains/pulse_lab/types/agent_decision.py`
- Modify: `src/parallax/domains/pulse_lab/interfaces.py`（schema_version bump 到 `pulse-decision-v2`）
- Add: `src/parallax/integrations/openai_agents/tools/__init__.py`（含 `ToolResult` Protocol）
- Add tests: `tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py`

- [ ] DELETE 类 `AnalystOpinion`, `CritiqueReport`（spec H2，不留 alias）
- [ ] `StageName` 改为 `Literal["investigator", "decision_maker", "research_only_gate"]`（spec H4 类型层）
- [ ] DEFINE `ToolResult` Protocol（在 tools/__init__.py）:
  ```python
  from typing import Protocol, Any
  class ToolResult(Protocol):
      data: dict[str, Any]
      contributed_event_ids: list[str]
  ```
- [ ] NEW `BullBearView`:
  - `strength: Literal["absent","weak","moderate","strong"]`
  - `thesis_zh: str = ""`
  - `supporting_event_ids: list[str] = []`
  - `@model_validator`：absent 时 thesis 与 supporting_ids 必须空；非 absent 时必须非空
- [ ] NEW `TradePlaybook`（简化 v2 字段）:
  - `watch_signals: list[str]`
  - `exit_triggers: list[str]`
  - `monitoring_horizon: Literal["1h","4h","24h"]`
  - `has_playbook: bool`
  - `@model_validator`：`has_playbook=False` 时 watch/exit 必须为空列表
  - `@model_validator`：`_reject_execution_language` 全字段 grep
- [ ] NEW `InvestigationReport`（无 markdown_report，无 tool_call_summary）:
  - `narrative_archetype_candidate: str` + `@field_validator` 长度 ≤ 20
  - `narrative_observation_zh: str` + `@field_validator` 长度 30-300
  - `bull_observation: BullBearView`
  - `bear_observation: BullBearView`
  - `data_gaps: list[str]`
  - `@model_validator`：`narrative_archetype_candidate=""` 时允许双 absent；非空时至少一边非 absent
  - `@model_validator`：`_reject_execution_language` 全字段
- [ ] EXTEND `FinalDecision`，保留现有 8 字段 + 新增 5 字段（spec §5.2）:
  - `narrative_archetype: str` + `@field_validator` 长度 ≤ 20（free-text, phase 1）
  - `narrative_thesis_zh: str` + `@field_validator` 长度 30-300
  - `bull_view: BullBearView`
  - `bear_view: BullBearView`
  - `playbook: TradePlaybook`
  - `evidence_event_urls: dict[str, str]`（event_id → tweet_url，worker 持久化前填）
  - `@model_validator` 强约束：
    - `abstain` 必须有 abstain_reason（已有）
    - 非 abstain 必须有 evidence_event_ids 或 residual_risks（已有）
    - `recommendation=high_conviction` → `bull_view.strength ∈ ("moderate","strong")` AND `bear_view.strength ∈ ("moderate","strong")` AND `len(evidence_event_ids) >= 3`
    - `narrative_archetype="" or narrative_archetype="unclear"` → `recommendation != "high_conviction"`
    - `recommendation="abstain"` → `playbook.has_playbook == False`
- [ ] Bump `PULSE_DECISION_SCHEMA_VERSION = "pulse-decision-v2"`, `PULSE_DECISION_PROMPT_VERSION = "pulse-decision-prompt-v2"`

**Tests:**
- [ ] `test_agent_decision_v2_schema.py`:
  - `BullBearView`: absent + empty ✅ / absent + non-empty ❌ / moderate + empty supporting ❌
  - `TradePlaybook`: has_playbook=false + watch_signals 非空 ❌ / has_playbook=true + watch_signals 空 ✅（允许只有 exit_triggers）
  - `TradePlaybook`: 含 "buy" / "sell" 字样 ❌（reject_execution_language）
  - `InvestigationReport`: archetype="" + 双 absent ✅ / archetype="memetic" + 双 absent ❌ / asymmetric bull=strong + bear=absent ✅
  - `FinalDecision`: high_conviction + bear=absent ❌
  - `FinalDecision`: high_conviction + bull=strong + bear=strong + evidence < 3 ❌
  - `FinalDecision`: high_conviction + 三条都满足 ✅
  - `FinalDecision`: recommendation=abstain + has_playbook=true ❌
  - `FinalDecision`: archetype="unclear" + recommendation=high_conviction ❌
  - Round-trip：model_validate(model_dump(...)) 字段一致
- [ ] 跑 OQ-4 反测脚本

**Verification:**
```bash
uv run pytest tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py -v
grep -rn "AnalystOpinion\|CritiqueReport" src/ tests/ | grep -v "test_agent_decision_v2"
# 期望 0 行
```

---

### Task 4 — Investigator tools（3 个 + ToolResult 实现）

**Files:**
- Add: `src/parallax/integrations/openai_agents/tools/recent_tweets.py`
- Add: `src/parallax/integrations/openai_agents/tools/price_action.py`
- Add: `src/parallax/integrations/openai_agents/tools/official_profile.py`
- Add tests: `tests/unit/integrations/openai_agents/tools/test_*.py`

每个工具 = `@function_tool` 装饰的 async 函数 + 返回符合 `ToolResult` Protocol 的 dataclass。**禁止 user-input SQL 拼接**；所有参数 typed。

- [ ] **get_target_recent_tweets**:
  ```python
  @dataclass
  class RecentTweetsResult:
      data: dict[str, Any]                  # 含 tweets list
      contributed_event_ids: list[str]      # tweets 列表的全部 event_id

  @function_tool
  async def get_target_recent_tweets(
      ctx: RunContext, target_id: str, limit: int = 15
  ) -> RecentTweetsResult:
      """Return recent tweets, top by attribution weight. Each tweet contains event_id / handle / followers / text / tweet_url."""
      # events JOIN token_intent_resolutions WHERE target_id=$1 ORDER BY attribution_weight DESC, received_at_ms DESC
      # tweet_url 从 events.event_payload_json->>'url' 提取
      # 写入 ctx.usage.contributed_event_ids
  ```
- [ ] **get_target_price_action**:
  ```python
  @function_tool
  async def get_target_price_action(
      ctx: RunContext, target_id: str, hours: int = 24
  ) -> PriceActionResult:
      """Return OHLCV + liquidity + current/24h_change/24h_volume/holders."""
      # market_ticks WHERE target_id=$1 + asset_market_snapshots latest
  ```
  - `contributed_event_ids` 为空（价格不产生 event 引用）
- [ ] **get_official_token_profile**:
  ```python
  @function_tool
  async def get_official_token_profile(
      ctx: RunContext, target_id: str
  ) -> OfficialProfileResult:
      """Return GMGN official metadata."""
      # asset_profiles WHERE asset_id=$target_id AND status='ready'
  ```
  - `contributed_event_ids` 为空
- [ ] 每个工具内 result.data 限大小 ≤ 4KB；超限 truncate 加 `truncated: true`
- [ ] 失败（target 不存在）返回 `{"data": {"error": "..."}, "contributed_event_ids": []}` 不抛
- [ ] 工具用 **独立 read-only PG pool**（max_size=3，新增到 `db_pool_bundle.py`）（reviewer E.3）
- [ ] **[P0-6] Tool counter**：在工具入口处自增 `ctx.usage.tool_calls_count`，超 `pulse_candidate.investigator_max_tool_calls[route]` 时抛 `ToolBudgetExceeded`

**Tests:**
- [ ] 每工具 unit test：happy path / target 不存在 / 4KB 上限触发
- [ ] integration test：3 tools 起 fake RunContext 调用，contributed_event_ids 正确累积
- [ ] tool counter test：超上限抛 ToolBudgetExceeded

**Verification:**
```bash
uv run pytest tests/unit/integrations/openai_agents/tools/ -v
grep -rn "@function_tool" src/parallax/integrations/openai_agents/tools/ | wc -l
# 应为 3
```

---

### Task 5 — Prompts 文件化

**Files:**
- DELETE: `src/parallax/integrations/openai_agents/pulse_stage_prompts.py`
- Add: `src/parallax/domains/pulse_lab/prompts/investigator.md`
- Add: `src/parallax/domains/pulse_lab/prompts/decision_maker.md`
- Add: `src/parallax/domains/pulse_lab/services/prompt_loader.py`
- Add tests: `tests/unit/domains/pulse_lab/test_prompt_loader.py`

- [ ] DELETE 整文件 `pulse_stage_prompts.py`（spec H5）
- [ ] 建 `prompt_loader.py`:
  ```python
  PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

  def load_prompt(role: str, route: DecisionRoute) -> str:
      path = PROMPTS_DIR / f"{role}.md"
      text = path.read_text(encoding="utf-8")
      return _render_route_section(text, route)   # 单文件内 route 段落分支
  ```
- [ ] 写 `investigator.md`：
  - System prefix：anti-injection（参考现有 `pulse_stage_prompts.py:24-32`）
  - 角色定位：研究员，基于事实查证
  - 3 个工具列表与调用指南
  - InvestigationReport 输出字段语义
  - bull/bear observation 是观察不是推荐；asymmetric 允许；archetype="" 双 absent 允许
  - 明确禁止 buy/sell/position 等执行性语言
  - Route 段（cex 重 venue/event；meme 重 DEX floor/cohort）
  - **[P1-9] markdown 提示模型 markdown_thesis 长度 30-300（不能依赖 GBNF）**
- [ ] 写 `decision_maker.md`：
  - 角色定位：综合判断者 + playbook 设计者
  - 输入：InvestigationReport + 1 个 fallback tool (`get_target_recent_tweets`)
  - 输出 FinalDecision 字段语义
  - **high_conviction 硬约束** 重述
  - playbook 字段语义（watch_signals/exit_triggers/monitoring_horizon/has_playbook 二分）
  - **明确禁止价格 / 仓位 / 等级**
  - Route 段
- [ ] 缓存友好排布：static prefix 放最前（≥ 4KB），dynamic context 放最后；**InvestigationReport 在 prompt 中先于任何 dynamic 字段**（P1-5）

**Tests:**
- [ ] `test_prompt_loader.py`:
  - `load_prompt("investigator", "meme")` 含 "meme" 关键词
  - `load_prompt("investigator", "cex")` 含 "cex" 关键词
  - `load_prompt("decision_maker", "meme")` 含 "playbook" 关键词
  - 两个 prompt 都含 anti-injection prefix
  - 文件总长度 ≥ 4KB（缓存友好）

**Verification:**
```bash
uv run pytest tests/unit/domains/pulse_lab/test_prompt_loader.py -v
grep -rn "pulse_stage_prompts\|_ROUTE_FOCUS\|_STAGE_FOCUS" src/ tests/
# 期望 0 行
```

---

### Task 6 — Agent client 重写（两 stage 编排 + tool counter + hallucination guard）

**[H6/P1-2/P1-6/B.4 内联]**

**Files:**
- Modify (重写): `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/parallax/domains/pulse_lab/providers.py`（provider protocol 接口签名）
- Modify: `src/parallax/app/runtime/providers_wiring.py`（注入 tools list）
- Modify: `src/parallax/domains/pulse_lab/services/agent_runtime.py`（manifest stages 改 `["investigator","decision_maker"]`）
- Add tests: `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`

- [ ] DELETE `_run_stage`, `run_decision_pipeline`, critic veto 分支（spec H6/H8）
- [ ] NEW `run_investigation_then_decision`:
  ```python
  async def run_investigation_then_decision(
      self, *, context, run_id, job, route, completeness, harness,
  ) -> PulseDecisionAgentResult:
      audit = self._request_audit(...)
      run_ctx = self._build_run_context(route)   # 含 tool_counter, contributed_event_ids set

      # Stage 1: Investigator (带 tools)
      inv_step = await self._run_investigator(run_ctx, route, context, ...)
      if inv_step.status != "ok": raise PulseStageFailure(...)
      investigation = InvestigationReport.model_validate(inv_step.response_json)
      self._validate_supporting_ids(investigation, run_ctx)   # P1-2 hallucination guard

      # Stage 2: DecisionMaker (带 1 个 fallback tool)
      dec_step = await self._run_decision_maker(run_ctx, route, context, investigation, ...)
      if dec_step.status != "ok": raise PulseStageFailure(...)
      final = FinalDecision.model_validate(dec_step.response_json)

      # 在持久化前 build evidence_event_urls
      final = await self._enrich_evidence_urls(final, target_id=...)   # P1-7

      return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=(inv_step, dec_step))
  ```
- [ ] `_run_investigator`:
  - prompt: `load_prompt("investigator", route)`
  - Agent `tools=[get_target_recent_tweets, get_target_price_action, get_official_token_profile]`
  - `max_turns=5`（SDK 限制；真正的 tool budget 通过 counter）
  - `output_type=InvestigationReport`
  - 复用现有 `_JsonOutputSchema` strict + jsonref（M1 prerequisite）+ Instructor safety_net
  - **从 `RunResult.raw_responses` 提取实际 tool_calls 写到 `step.input_json.tool_calls`**（P1-1）
- [ ] `_run_decision_maker`:
  - prompt: `load_prompt("decision_maker", route)`
  - Agent `tools=[get_target_recent_tweets]`（fallback；OQ-2 决定是否禁用）
  - `max_turns=3`
  - `output_type=FinalDecision`
- [ ] `_validate_supporting_ids(investigation, run_ctx)`（P1-2 hallucination guard）:
  ```python
  allowed = run_ctx.contributed_event_ids | set(context.get("evidence_event_ids", [])) | set(context.get("source_event_ids", []))
  for view_name in ("bull_observation", "bear_observation"):
      view = getattr(investigation, view_name)
      if view.strength == "absent": continue
      unknown = set(view.supporting_event_ids) - allowed
      if unknown:
          raise ValueError(f"{view_name}.supporting_event_ids contains unknown ids: {unknown}")
  ```
- [ ] `_enrich_evidence_urls(final, target_id)`（P1-7）:
  - JOIN `events.event_payload_json->>'url'` for final.evidence_event_ids
  - 缺 url 的 event_id 不进 dict（surface card 降级）
  - 写入 final.evidence_event_urls
- [ ] `agent_runtime.build_pulse_runtime_manifest` 更新：
  - `stages: ["investigator", "decision_maker"]`
  - `runtime.tool_names_by_stage` 是唯一工具契约；“tools enabled” 表示该 stage 工具列表非空，没有单独 bool
  - 自然 bump `runtime_hash`（grader v2 通过 runtime_hash 隔离 v1 case）

**Tests:**
- [ ] `test_pulse_decision_two_stage.py`:
  - Fake Runner happy path → 返回 PulseDecisionAgentResult，两个 stage_audits
  - Investigator fail → DecisionMaker 不调；raise PulseStageFailure(audits=1)
  - DecisionMaker fail → raise PulseStageFailure(audits=2)
  - **Hallucination guard**：Investigator 输出 supporting_event_ids 含未在 contributed_event_ids 的 → raise ValueError
  - **Tool budget**：fake 工具调 6 次（cex max=3）→ ToolBudgetExceeded
  - **evidence_event_urls**：含 5 ids 其中 3 在 events 表有 url → final.evidence_event_urls 含 3 项
- [ ] FakeRunResult fixture 在 `tests/conftest.py` 共用，含 `final_output / raw_responses / context_wrapper / usage` 完整 shape（P1 reviewer E2）

**Verification:**
```bash
uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py -v
grep -rn "_run_stage\|critic\|judge\|veto" src/parallax/integrations/openai_agents/pulse_decision_agent_client.py
# 期望 0 行
```

---

### Task 7 — pulse_candidate_worker 接新 client + signal_pulse_service 字段映射

**[P0-5 内联]**

**Files:**
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/services/decision_mapping.py`
- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`（P0-5 `_decision()` 扩字段）
- Add tests: `tests/integration/test_pulse_candidate_worker_v2.py`

- [ ] `_run_job` 调 `provider.run_investigation_then_decision`，不传 past_context（phase 1 不引入）
- [ ] worker run_audit metric 加：`investigation_tool_calls_count`（从 stage_audit input_json.tool_calls 提取）
- [ ] `decision_mapping.map_final_decision_to_candidate_row`：把新字段 (narrative_archetype / narrative_thesis_zh / bull_view / bear_view / playbook / evidence_event_urls) 一并写入 `decision_json`
- [ ] **[P0-5] `signal_pulse_service._decision()`** 扩展返回字段集合：
  ```python
  def _decision(row):
      decision = _dict(row.get("decision_json"))
      return {
          "route": ...,                              # 现有
          "recommendation": ...,                     # 现有
          "confidence": ...,                         # 现有
          "abstain_reason": ...,                     # 现有
          "stage_count": ...,                        # 现有
          "summary_zh": ...,                         # 现有
          "invalidation_conditions": ...,            # 现有
          "residual_risks": ...,                     # 现有
          "evidence_event_ids": ...,                 # 现有
          "narrative_archetype": decision.get("narrative_archetype", ""),       # 新
          "narrative_thesis_zh": decision.get("narrative_thesis_zh", ""),       # 新
          "bull_view": decision.get("bull_view"),                                # 新
          "bear_view": decision.get("bear_view"),                                # 新
          "playbook": decision.get("playbook"),                                  # 新
          "evidence_event_urls": decision.get("evidence_event_urls", {}),        # 新
      }
  ```

**Tests:**
- [ ] `test_pulse_candidate_worker_v2.py`:
  - happy path：worker 处理 1 candidate → pulse_candidates 行有完整 decision_json + pulse_agent_run_steps 两行 (investigator + decision_maker)
  - signal_pulse_service.get_pulse_detail 返回含新 6 字段
  - Investigator fail → 不写 decision；pulse_agent_runs.outcome='failed'
  - DecisionMaker fail → 同上

**Verification:**
```bash
uv run pytest tests/integration/test_pulse_candidate_worker_v2.py -v
docker exec parallax-postgres-1 psql -U parallax_app -d parallax -c "
  SELECT array_agg(DISTINCT stage) FROM pulse_agent_run_steps
  WHERE started_at_ms > (extract(epoch from now() - interval '5 minutes') * 1000)::bigint;"
# 应只含 investigator / decision_maker
```

---

### Task 8 — Notification SurfaceCard 重写

**[H7/P1-6/P1-7/P1-8 内联]**

**Files:**
- Modify (重写): `src/parallax/domains/notifications/services/notification_rules.py`
- Add: `src/parallax/domains/notifications/services/pulse_surface_card.py`
- Modify tests: `tests/unit/test_notification_rules.py`
- Add tests: `tests/unit/test_pulse_surface_card.py`

- [ ] DELETE 现有 `_pulse_body` 实现（spec H7）
- [ ] NEW `pulse_surface_card.render(row, decision) -> str`:
  - Header: `${symbol} · {route} · {recommendation} · conf {pct}`
  - Narrative 段（含 narrative_archetype + narrative_thesis_zh）
  - Bull 段（strength≠absent；含 deep-link 通过 `decision.evidence_event_urls`）
  - Bear 段（同 Bull）
  - Playbook 段（has_playbook=true 时；含 watch_signals / exit_triggers / monitoring_horizon）
  - Links 段（GMGN / X Search / Pulse Detail）
- [ ] **[P1-6] 降级顺序**：超长时按以下顺序砍段，始终保 Header + Recommendation + Playbook + Links：
  1. 先砍 Bear 段
  2. 再砍 Bull 段
  3. 再砍 Narrative 段
- [ ] body 长度上限 ~2500 字符
- [ ] **[P1-8] signature 改写**：`_pulse_notification_signature` 只 hash：
  ```python
  payload = {
      "candidate_id": ...,
      "pulse_status": ...,
      "decision_route": decision.get("route"),
      "decision_recommendation": decision.get("recommendation"),
      "bull_strength": decision.get("bull_view",{}).get("strength"),
      "bear_strength": decision.get("bear_view",{}).get("strength"),
      "narrative_archetype": decision.get("narrative_archetype"),
      "has_playbook": decision.get("playbook",{}).get("has_playbook"),
      "score_band": ...,
      "gates": ...,
  }
  # 不含任何 thesis_zh / narrative_thesis_zh / summary_zh 自由文本
  ```

**Tests:**
- [ ] `test_pulse_surface_card.py`:
  - happy path：完整 FinalDecision + asset_profile → 渲染含 6 块 markdown
  - asymmetric bull=absent → Bull 段缺；Bear 段在
  - 双 absent + archetype="" → Bull/Bear 都缺
  - 超长触发：保留 Header + Playbook + Links，砍 Bear 后 Bull 后 Narrative
  - deep link 正确（GMGN url 含 chain+address, X 含 $symbol；tweet URL 从 evidence_event_urls 读）
  - evidence_event_urls 缺 url 的 event_id 降级为 @handle 文本无链接
- [ ] `test_notification_rules.py`:
  - signature 不含 thesis_zh，narrative_thesis_zh 微变不触发新 dedup_key
  - signature 含 bull_strength 变化，bull absent→strong 触发新 dedup_key

**Verification:**
```bash
uv run pytest tests/unit/test_notification_rules.py tests/unit/test_pulse_surface_card.py -v
docker exec parallax-postgres-1 psql -U parallax_app -d parallax -c "
  SELECT length(body) FROM notifications
  WHERE rule_id='signal_pulse_candidate' ORDER BY last_seen_at_ms DESC LIMIT 3;"
# body length 应 >800
```

---

### Task 9 — 前端类型 + legacy 占位卡

**[P1-11/H10 内联]**

**Files:**
- Modify: `web/src/lib/types/frontend-contracts.ts`（PulseDecision 字段；SignalPulseStageName / SignalPulseStages 改新枚举；删 narrative_type 字段）
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts:858-871`（stages 消费改新枚举 + 老 stage fallback）
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx:38-46`（渲染 investigator/decision_maker；老 stage 渲染为 legacy 占位卡）
- Modify: `web/src/features/signal-lab/test/fixtures/titty-pulse.ts:101`（删 narrative_type；改 stages）
- Modify: `web/tests/component/.../PulseDetailRoutePage.routing.test.tsx`
- Modify: `web/tests/e2e/support/mockApi.ts:524`

- [ ] `frontend-contracts.ts`:
  - `SignalPulseStageName` 改为 `'investigator' | 'decision_maker' | 'research_only_gate'`
  - `SignalPulseStages` 字段从 analyst/critic/judge 改 investigator/decision_maker
  - **删除** `narrative_type` 字段
  - `PulseDecision` 加 6 字段：`narrative_archetype / narrative_thesis_zh / bull_view / bear_view / playbook / evidence_event_urls`
  - 都标可选（`?:`），缺时前端 fallback 显示 "—"
- [ ] `pulseDetail.ts`:
  - 消费 `stages.investigator.response / stages.decision_maker.response`
  - **legacy fallback**：如果 stages 含 `stages.analyst / stages.critic / stages.judge`（老 run），渲染为 LegacyStageCard
- [ ] `PulseAgentRail.tsx`:
  - 新 stage 渲染分支
  - 老 stage 检测 → 渲染 LegacyStageCard（show stage 名 + status + latency + 简要 response 摘要不解析结构）
- [ ] 新增 3 个 UI 卡（Narrative / Bull-Bear / Playbook）的渲染**留独立 frontend spec**；本 task **不实现 UI 卡**，只保证 TS 类型扩展 + build 通过 + legacy 占位卡

**Tests:**
- [ ] `web/tests/` 下涉及 pulse stages 的 component test 改新枚举
- [ ] 新增 test：老 stage data 渲染为 legacy 占位卡，无 JS error
- [ ] `cd web && npm run build`（必须通过）

**Verification:**
```bash
cd web && npm test -- --run && npm run build
grep -rn "narrative_type" web/src/ web/tests/
# 期望 0 行
grep -rn "'analyst'\|'critic'\|'judge'\"analyst\"\|\"critic\"\|\"judge\"" web/src/ | grep -v "legacy"
# 期望 0 行（legacy 渲染分支可保留 string 用于判断）
```

---

### Task 10 — Eval grader v2 + cross-domain grep 防御

**[H9/G.1 内联]**

**Files:**
- Modify: `src/parallax/domains/pulse_lab/services/agent_eval.py`
- Modify tests: `tests/unit/domains/pulse_lab/test_agent_eval.py`
- Modify (归档): mv `docs/superpowers/specs/active/2026-05-14-pulse-detail-redesign-cn.md` → `docs/superpowers/specs/completed/`
- Modify: `docs/CONTRACTS.md`（Signal Pulse decision block 加 narrative/bull/bear/playbook）
- Modify: `docs/RELIABILITY.md`（Pulse Audit Ledger stage 枚举改）
- Modify: `src/parallax/domains/pulse_lab/ARCHITECTURE.md`（Stage Map 三 stage → 两 stage）

- [ ] DELETE v1 grader rules
- [ ] NEW v2 grader rules（5 项，KISS 收敛）:
  - **R1** `stages_present`: stage_audits 含 `investigator` 且 status='ok'，且含 `decision_maker` 且 status='ok'（除非 hard_blocked）
  - **R2** `tool_calls_present`: investigator step `input_json.tool_calls` ≥1（除非 hard_blocked）
  - **R3** `evidence_subset`: final.evidence_event_ids ⊂ investigator.bull_observation.supporting_event_ids ∪ bear_observation.supporting_event_ids ∪ context.evidence_event_ids
  - **R4** `high_conviction_constraint`: recommendation=high_conviction 必须 bull/bear 都 ≥moderate 且 evidence ≥3
  - **R5** `playbook_consistent`: recommendation=abstain → playbook.has_playbook=false AND watch_signals/exit_triggers 为空
- [ ] **defensive dispatch**：grader 检测 case shape，v1 case（缺 narrative/bull/bear keys）返回 `status='legacy_skipped'` 不 panic（reviewer G.1）
- [ ] grader version `pulse-deterministic-eval-v3`
- [ ] 文档更新（CONTRACTS / RELIABILITY / ARCHITECTURE）
- [ ] **归档 2026-05-14-pulse-detail-redesign-cn.md** 到 `completed/`（P1-10）
- [ ] **Cross-domain grep 防御**（最终扫，应为 0）:
  ```bash
  for pattern in \
      "AnalystOpinion" "CritiqueReport" \
      "pulse_stage_prompt" "_ROUTE_FOCUS" "_STAGE_FOCUS" \
      "narrative_type" \
      "stage='analyst'" "stage='critic'" "stage='judge'" \
      '"analyst"' '"critic"' '"judge"' \
      "agent_recommendation"; do
    echo "=== $pattern ==="
    grep -rn "$pattern" src/ tests/ 2>/dev/null | grep -v "completed/" | grep -v "\.bak" | grep -v "test_legacy" | grep -v "legacy_skipped"
  done
  ```
- [ ] 期望除 `pulse_agent_runs.outcome='abstain_critic_veto'` 历史 enum 值的只读使用（OQ-5 决策保留）外，src/ tests/ 应为 0

**Tests:**
- [ ] `test_agent_eval.py`:
  - 5 个 rule 各 happy + fail case
  - v1 case → `status='legacy_skipped'`，不 raise
  - 完整 v2 PulseDecisionPayload pass 5 rules

**Verification:**
```bash
uv run pytest tests/unit/domains/pulse_lab/test_agent_eval.py -v
# grep 防御
```

---

### Task 11 — E2E 集成测试

**[E.3 内联]**

**Files:**
- Add: `tests/integration/test_pulse_desk_e2e.py`

- [ ] 单一 e2e 测试覆盖完整流水线:
  - 起测试 DB（pytest-docker 或现有 conftest fixture）
  - Stub LLM provider 返回 fixture InvestigationReport + FinalDecision JSON
  - Stub 3 个工具返回 fixture data
  - 触发 pulse_candidate_worker 处理 1 个 candidate
  - **断言全部**：
    - `pulse_candidates` 行写入，decision_json 含 6 个新字段
    - `pulse_agent_run_steps` 写 2 行（investigator + decision_maker），stage 名正确
    - signal_pulse_service.get_pulse_detail 返回新字段
    - notification 行写入，body 含 6 段，dedup_key 稳定
- [ ] 测试时间预算 ≤ 60s
- [ ] 加 `pytest.mark.integration` marker

**Verification:**
```bash
uv run pytest tests/integration/test_pulse_desk_e2e.py -v --timeout=60
```

---

### Task 12 — Verification + Acceptance Sign-off

依序跑:

- [ ] Ruff lint: `uv run ruff check .`
- [ ] Pytest 全套: `uv run pytest --timeout=120 -x`
- [ ] Web 测试: `cd web && npm test -- --run && npm run build`
- [ ] Alembic 双向: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] Grep 防御（Task 10）全 0
- [ ] 起完整服务跑 30 分钟实测:
  ```sql
  -- F1: stage 分布
  SELECT stage, status, count(*) FROM pulse_agent_run_steps
  WHERE started_at_ms > (extract(epoch from now() - interval '30 minutes') * 1000)::bigint
  GROUP BY 1,2 ORDER BY 1,2;
  -- 应只含新 stage

  -- F2: tool calls 非空
  SELECT
    count(*) FILTER (WHERE jsonb_array_length(coalesce(input_json->'tool_calls','[]'::jsonb)) > 0) AS has_tools,
    count(*) AS total
  FROM pulse_agent_run_steps
  WHERE stage='investigator' AND status='ok'
    AND started_at_ms > (extract(epoch from now() - interval '30 minutes') * 1000)::bigint;

  -- F3: FinalDecision 含新字段
  SELECT
    count(*) FILTER (WHERE decision_json ? 'narrative_archetype') AS has_archetype,
    count(*) FILTER (WHERE decision_json ? 'playbook') AS has_playbook,
    count(*) FILTER (WHERE decision_json->'bull_view'->>'strength' IS NOT NULL) AS has_bull,
    count(*) FILTER (WHERE decision_json ? 'evidence_event_urls') AS has_urls,
    count(*)
  FROM pulse_candidates
  WHERE updated_at_ms > (extract(epoch from now() - interval '30 minutes') * 1000)::bigint;

  -- F5: notification body 平均长度
  SELECT avg(length(body)), max(length(body)), min(length(body))
  FROM notifications
  WHERE rule_id='signal_pulse_candidate'
    AND last_seen_at_ms > (extract(epoch from now() - interval '30 minutes') * 1000)::bigint;
  ```
- [ ] 写 verification 文档:
  - 位置: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-verification-cn.md`
  - 跑上面 SQL 实测值 + spec §10.1 F1-F8 通过情况 + 截图 1-2 张 notification body

---

## Rollback Strategy（**[P1-12] 四步强制顺序**）

出问题时按以下顺序：
1. **停服务**（避免 v2 代码读老 schema 或反之）
2. `uv run alembic downgrade -1`（恢复 schema，NOT VALID 不报错）
3. `git revert <commit>`（恢复代码）
4. **启服务**

不要颠倒顺序。prerequisite (M1 schema hard fix) 独立不一起 revert。DB 备份在 Pre-flight 已拍。

---

## Acceptance Sign-off

PR 描述包含以下确认：

- [ ] spec §10.1 F1-F8 全部 falsifiable 条目实测通过（粘 SQL 输出）
- [ ] Task 10 grep 防御输出 0
- [ ] ruff + pytest + web build 全绿
- [ ] alembic 双向通过
- [ ] OQ-1 至 OQ-6 决策记入 `docs/generated/pulse-agent-desk-decisions.md`
- [ ] `pulse-agent-desk-redesign-verification-cn.md` 已写
- [ ] 至少 1 个真实 notification body 截图（含 6 段结构）
- [ ] 至少 1 个真实 pulse_agent_run_steps 老 stage 行（analyst/critic/judge）在前端 PulseDetailView 渲染为 legacy 占位卡的截图
- [ ] PR description 列出 Task 1-12 全部完成 checkbox

7 天 soft launch 后回填 spec §10.2 Q1-Q9 quality metrics 到 verification 文档；同时抽样 200 个 narrative_archetype free-text 输出供 phase 2 enum 化 spec 使用。

---

## v1 → v2 关键差异速查

| 项 | v1 | v2 |
|---|---|---|
| 角色数 | 3 (Investigator/DecisionMaker/Reflector) | **2** (Investigator/DecisionMaker) |
| 新表 | 3 (pulse_decision_log/decision_outcomes/narrative_briefs) | **0** |
| 新 worker | 2 (NarrativeBriefWorker/OutcomeWorker) | **0** |
| Investigator 工具数 | 6 | **3** |
| InvestigationReport.markdown_report | 有 | **删除**（reviewer A.5）|
| InvestigationReport.tool_call_summary | 有 | **删除**，worker 从 RunResult 提取（reviewer B.1）|
| Playbook 字段 | `playbook_type` 5 enum + `sizing_band` 5 enum + `key_observation_levels`（含价格）| `has_playbook` 二分 + watch_signals + exit_triggers + monitoring_horizon |
| narrative_archetype | 7 enum 锁定 | **free-text**（reviewer B.2）|
| BullBearView.strength | 4 enum | 保留 4 enum，phase 1 系统只消费二分 |
| Tool budget 控制 | SDK max_turns（错的）| worker 侧 counter（reviewer P0-6）|
| Hallucination guard | "⊂ tool result"（不可实现）| ToolResult Protocol + contributed_event_ids set |
| evidence_event_urls | 不在 schema | worker 持久化前 build 写入 decision_json |
| Notification signature | hash 整 decision_json | 只 hash 稳定维度（reviewer P1-8）|
| Surface 降级顺序 | 先 Playbook | 始终保 Playbook，先砍 Bear（reviewer D.1）|
| ALTER CHECK | immediate validate（错的）| NOT VALID（reviewer P0-1）|
| narrative_type DROP | Task 14 grep 兜底（晚）| Task 2 同 task 原子改 6 文件（reviewer P0-2）|
| `_stages_for` keys | 未列改动 | Task 7 显式改（reviewer P0-4）|
| `_decision()` 字段 | 未列扩展 | Task 7 显式扩 6 字段（reviewer P0-5）|
| Past context loader | phase 1 | 移到 phase 2 |
| E2E 集成测试 | 无 | Task 11 必须有（reviewer E.3）|
| Task 数 | 15 | **12** |
