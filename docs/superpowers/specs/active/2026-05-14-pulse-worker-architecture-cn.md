# Pulse Worker Architecture — Edge-Triggered 重设计 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-14
**Owner**: Claude with Qinghuan
**Scope**: 从第一性原理重设计 `PulseCandidateWorker` 的入队节流、状态机、持久化与异常路径。本文是 spec，不含 SQL 完整 migration、文件级任务、prompt、PR 拆分。
**Harness**: 保留 `openai-agents-python`；不动 agent 内部，只动 worker 层。

**Related**:

- `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`（agent runtime 重设计；本 spec 是它的前置工作）
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`（数据契约缺口诊断；与本 spec 互补，本 spec 不重复其内容）
- `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`（早期 hard cut；本 spec 在其 schema 基础上继续 hard cut）
- `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/RELIABILITY.md`

---

## 一句话结论

把 `PulseCandidateWorker` 从"轮询 + bypass cooldown"模式改成 **edge-triggered 状态机**：worker 不再"每分钟扫一遍所有 token 看要不要重跑"，而是只在 token 的状态发生**真实跳变**时入队一次。配套把 `outcome` 字段从默认值改成强制回填、把 `source_seed` 从无 target 资产决策路径中移除、把死状态（`theme_watch`）从枚举里删掉、把 `token_watch` 这档真正激活、把 `decision_route` 在版本跃迁时强制重算、把 `notification_deliveries` 的 stale-lease 回收补完。落地后这份 spec 是 `target-agent-architecture-design` 的前置工作——agent runtime 收到的是一个干净的候选池。

## 1. 当前事实（2026-05-14 实测）

24h 数据快照（实测查得）：

| 维度 | 数值 |
|---|---|
| `pulse_agent_jobs` 总量 | 750（done 709 + dead 40 + running 1） |
| `pulse_agent_runs` 总量 | **5879** |
| `pulse_candidates` 总量 | 295 |
| job → run 倍数 | 7.8× |
| 单 candidate 最高 run 数 | TROLL **474 次**，其中 failed 239、completed 8 |
| 端到端 job 时延 | p50 10 分钟，p90 4.6 小时，max 69 小时 |
| stage 失败率 | analyst 29%，critic 33%，judge 17% |
| 候选池 `blocked_low_information / source_seed` 占比 | **52%**（153/295） |
| `outcome=pending` 但 status≠running 的 agent_runs | **5142**（done 2972 + failed 2170） |
| `subject.target_market_type` 与 `decision_route` 矛盾的 candidates | 51 |
| `pulse_status='token_watch'` 行数 | **0**（死区） |
| `pulse_status='theme_watch'` 行数 | **0**（代码 0 处真实路径） |
| `notification_deliveries` 卡 running > 1h | 2（TAU、NICHEBABY，53 小时） |

## 2. 第一性原理

延续 `2026-05-13-target-agent-architecture-design-cn.md` 的五条原则（事实账本、结构化状态、确定性 gate、Critic governor、Replay/outcome），在 worker 层补三条：

### 2.1 Worker 是 edge-detector，不是 polling-loop

Worker 的本质职责是"响应世界的变化"，不是"周期性问世界要新答案"。同一个 token 在状态没变时被重复入队是 bug，不是 feature。Cooldown 是"限频"，不是"防重复"——这俩概念在当前实现里被混为一谈：`_cooldown_active` 限频，但 `_cooldown_bypass` 又允许"watched_mentions 增减""independent_authors 增减"这类**数值变化**绕过限频，结果是 hot token 实质上不被节流。Edge-trigger 是 first-class 机制；cooldown 退化为"防抖"二线兜底。

### 2.2 每条 worker 写入必须有 closed-form outcome

`pulse_agent_runs` 这种表的每一行都代表"agent 干完了一次活"。这个"活"必须以 closed-form 落库：成功 → `outcome=completed/abstain/abstain_critic_veto/abstain_insufficient_data`，失败 → `outcome=failed`。`pending` 这个值只能存在于 run 还在跑的瞬间，**不能**是 `finished_at_ms IS NOT NULL` 时 `outcome='pending'`。schema 在 design 层就应该把这个不可能状态消掉（NOT NULL + CHECK）。

### 2.3 候选池 = 复核台，而非历史归档

`pulse_candidates` 不是 audit log，是给人和 agent 看的"当前值得复核的目标"。任何 deterministic 100% abstain 的记录都不该进这张表——它没有信息价值，只增加噪声成本。`source_seed identity_unresolved` 这种属于"前置数据不够"，应该在 ingestion 层就被打回，不应包装成 fake snapshot 让 worker 走完整流程后落 153 条空壳。

> 与 `target-agent-architecture-design-cn.md` 的协调：该 spec 写 "source_seed 这种无 target 的输入不进入资产决策 route，只产生 deterministic research-only / abstain 记录"。本 spec 更激进——**不产生记录**，理由见 2.3。冲突以本 spec 为准。target-agent-arch 落地时不再需要 research_only route 处理 source_seed。

## 3. 目标

1. **入队节流改 edge-trigger**：定义 6 个状态跳变事件，只在跳变时入队；同一 candidate 在同一 `pulse_status` 上 24h 内 agent run p95 ≤ 5 次（当前 0–474）。
2. **outcome 强制写**：`finish_agent_run` 把 outcome 列变成必传参数，删默认值 `pending`；done/pending 这种自相矛盾的状态在 schema 层消失。
3. **source_seed hard gate**：identity 未解析在 worker 入口直接 return None，不入队、不写候选记录；候选池噪声占比从 52% 降至 < 5%。
4. **状态机精简 + 死区激活**：删除 `theme_watch`；通过把 `_is_asset_trigger` 起点从 70 下调到 45 真正激活 `token_watch`；`score_band` 保留 4 档语义（high_conviction / watch / speculative / blocked）由 gate 单一来源。
5. **routing 版本化**：`upsert_candidate` 在 `pulse_version` 或 `gate_version` 跃迁时强制重算 `decision_route`/`score_band`/`pulse_status`，避免历史漂移残留。
6. **stale-lease 覆盖 notification 通道**：`notification_deliveries` 的 claim 索引补上 `running` 状态，TAU/NICHEBABY 那种孤儿不再出现。

## 4. 非目标

- 不重设计 agent 内部（analyst → critic → judge 仍由 `target-agent-architecture-design-cn.md` 负责）。
- 不改 token_radar 数据契约（`pulse-agent-pipeline-current-state-cn.md` 等已覆盖）。
- 不引入 OutcomeCollector / Reflector / Memory（target-agent-arch phase 1 范畴）。
- 不换 agent harness。
- 不在本次落地加 dashboards / alerting，监控随后单独 spec。
- 不做 dual-write 兼容层；按 hard cut 偏好处理旧数据。

## 5. 目标架构

### 5.1 Worker 主流程（edge-detector 形态）

```text
WakeBus.token_radar_updated (LISTEN, 已有)
        │
        ▼
PulseCandidateWorker.scan_triggers_once
   for each (window, scope) in (1h, all):
     rows = token_radar.latest_rows()
     for row in rows:
        ① next_state := compute_next_state(row.factor_snapshot)
        ② prev_state := pulse_candidates.snapshot_for(candidate_id)
        ③ events := diff(prev_state, next_state)
        ④ if events == ∅: skip          # 无跳变,不入队
        ⑤ if not budget_ok(candidate_id, now_ms): skip  # 兜底节流
        ⑥ enqueue_job(events=events, ...)
   for each social event:
     if not source_event_is_signal(event): skip
     if event.identity_resolution.status != 'resolved': skip   # hard cut 2.3
     → fold into asset path (target_id 已知, 走 token_target 流程)
```

### 5.2 跳变事件定义（6 个 edge events）

| 事件 | 触发条件 | 设计理由 |
|---|---|---|
| `pulse_status_changed` | 上次 vs 本次 `pulse_status` 不同（含从无记录的首次） | 状态机驱动的最强信号 |
| `score_band_crossed` | `candidate_score` 跨越 45 或 72 阈值 | gate 边界跃迁，agent 输入语境质变 |
| `hard_risk_added` | `gate_reasons_json` 出现之前没有的元素 | 新风险出现必须复核 |
| `recommended_decision_changed` | `composite.recommended_decision` 跳变（high_alert ↔ watch ↔ discard） | 上游 Token Radar 自己改了判断 |
| `watched_emerged` | `watched_mentions` 从 0 变 > 0 | 信号从"无人看"到"有人看"的首次确认 |
| `pulse_version_bumped` | `PULSE_VERSION` 或 `PULSE_GATE_VERSION` 变化 | 代码升级后强制重算，不留 stale 记录 |

**故意不触发的**：`watched_mentions` 数量增减、`independent_authors` 数量增减、cooldown 到期、轮询周期。这正是 TROLL 474 次的根因——把"数字变化"当成"状态变化"。

### 5.3 节流双层机制（同时生效）

**第一层（主体）edge detection**：见 5.2。无跳变就不入队。

**第二层（兜底）per-candidate 1h token bucket**：防止 6 个 edge events 设计漏了导致雪崩。同 candidate 1h 内 ≤ 3 次入队（含跳变事件），超出转为静默观察——写 `pulse_candidate_run_budget` 计数表，**不**写候选记录、**不**调 agent。3 次/小时是基于"edge 设计正确时绝大多数 candidate 每小时 0–1 次跳变"的安全余量；如果触顶频繁说明 5.2 的 event 定义有问题，会通过指标反向暴露。

**移除**：现有 `_cooldown_active` + `_cooldown_bypass` + `_terminal_job_blocks_reenqueue` + `_COOLDOWN_MS` 整块逻辑（`pulse_candidate_worker.py:904-942` + `974-990` + `61-67`）全部删除。

### 5.4 Schema 变更（hard cut，无 dual-write）

新建 `pulse_candidate_run_budget`：

```text
CREATE TABLE pulse_candidate_run_budget (
    candidate_id TEXT NOT NULL,
    hour_bucket_ms BIGINT NOT NULL,        -- floor(now_ms / 3600000) * 3600000
    enqueue_count INT NOT NULL DEFAULT 0,
    last_enqueued_at_ms BIGINT NOT NULL,
    last_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (candidate_id, hour_bucket_ms)
);
CREATE INDEX idx_pulse_run_budget_hour ON pulse_candidate_run_budget (hour_bucket_ms);
```

`pulse_agent_runs.outcome` 改 NOT NULL + CHECK：

```text
-- backfill: 旧 done/pending 行按 response_json 内 recommendation 字段判定
UPDATE pulse_agent_runs
   SET outcome = CASE
     WHEN status='done' AND response_json->>'recommendation' IS NOT NULL THEN 'completed'
     WHEN status='done' THEN 'failed'
     WHEN status='failed' THEN 'failed'
     ELSE outcome
   END
 WHERE outcome='pending' AND status IN ('done','failed');

ALTER TABLE pulse_agent_runs
  ALTER COLUMN outcome DROP DEFAULT,
  ADD CONSTRAINT pulse_agent_runs_outcome_chk
    CHECK (outcome IN ('completed','abstain','abstain_critic_veto',
                       'abstain_insufficient_data','failed','running')),
  ALTER COLUMN outcome SET NOT NULL;
```

`pulse_candidates` 加 `last_edge_events_json`（debug + 可观测）：

```text
ALTER TABLE pulse_candidates
  ADD COLUMN last_edge_events_json JSONB NOT NULL DEFAULT '[]'::jsonb;
```

`notification_deliveries` claim 索引覆盖 running：

```text
DROP INDEX idx_notification_deliveries_claim;
CREATE INDEX idx_notification_deliveries_claim
  ON notification_deliveries (next_run_at_ms, created_at_ms, delivery_id)
  WHERE status IN ('pending','failed','running');
```

启动时 stale-lease 回收：worker 启动 hook 把 `running` 且 `last_attempt_at_ms < now - lease_timeout_ms`（5 分钟）的 delivery 回滚到 `pending`。

**删字段（hard cut）**：

- 从 `pulse_status` 允许值里移除 `theme_watch`（代码 3 处 dead 引用：`_PLAYBOOK_STATUSES`、`_COOLDOWN_MS`、`_inferred_status`，全部删）。
- 不删 `score_band` 任何值（保留 4 档语义，通过激活 `token_watch` 让 `watch`/`speculative` 真正出现）。
- 删 `candidate_type='source_seed'` 在 worker 端的入队路径；旧 153 条记录一次性 SQL DELETE。

### 5.5 持久化路径强约束

`finish_agent_run(run_id, outcome, ...)` 把 `outcome` 从可选参数改成必传位置参数。Python 函数签名层 + SQL CHECK 双重约束。worker 在 `_run_job` 的成功/失败路径都必须显式传 outcome：

- 成功路径（worker:608-619）：`outcome=_run_outcome(final_decision, completeness_blocked=...)`，结果属于 `{completed, abstain, abstain_critic_veto, abstain_insufficient_data}` 之一。
- 失败路径（worker:715-721）：`outcome='failed'`，必须传。

`upsert_candidate` 增加版本判定：写入前比对库里 row 的 `pulse_version` 和 `gate_version`，发现旧版本时**先重算**（用当前代码版本的 gate + routing）再写。这修 B5 的 51 条 routing 漂移。

### 5.6 source_seed 路径处理

`_source_context`（worker:381-420）改成：

```text
def _source_context(self, event, *, now_ms):
    if not _source_event_is_signal(event):
        return None
    resolved_target = _resolved_target_from_event(event)
    if resolved_target is None:
        return None        # hard cut: identity 未解析不入队
    # 解析成功 -> 当 token_target 走, 复用 _asset_context 的 factor_snapshot 构造
    return self._asset_context_from_source(event, resolved_target, now_ms=now_ms)
```

`_source_seed_factor_snapshot`（worker:1211-1264）整段函数删除。`candidate_type='source_seed'` 取消，社交事件直接走 `token_target` 路径，从这里开始它们看起来跟 token_radar 产生的候选完全一致——同一份 factor_snapshot、同一套 gate、同一套 routing。

### 5.7 异常路径

- agent stage 失败：现有 try/except + attempt 推进 + dead 转入逻辑保留（worker:684-723）。
- LLM JSON 解析失败：通过 `target-agent-architecture-design-cn.md` 上 structured output 解决，**不在本 spec 范围**。
- worker 进程被杀：`claim_due_job` 的 pulse job stale-lease 回收（`pulse_repository`）现有逻辑保留；notification 通道按 5.4 补 stale claim 索引和启动 hook。

## 6. 迁移路径

5 个 hard cut，串行实施：

| 顺序 | Cut 名 | 内容 | 风险 |
|---|---|---|---|
| 1 | **outcome NOT NULL backfill** | SQL backfill 旧 5142 条 pending → completed/failed；`finish_agent_run` 改强制 outcome | 低 |
| 2 | **删 source_seed 路径** | `_source_context` 改 identity-required；`_source_seed_factor_snapshot` 删；旧 153 条候选 DELETE | 中 |
| 3 | **edge-trigger 入队** | `_enqueue_if_due` 改 diff 算法；删 cooldown 整块；加 `pulse_candidate_run_budget` 表 + 计数；`pulse_candidates` 加 `last_edge_events_json` | 高 |
| 4 | **状态机精简 + routing 版本化** | DROP `theme_watch`；`_is_asset_trigger` 起点 70 → 45；`upsert_candidate` 版本判定；51 条漂移 candidate `decision_route` SET NULL 触发下次扫描重算 | 中 |
| 5 | **notification stale-lease** | `notification_deliveries` 索引覆盖 running；worker 启动 hook 回收 2 条卡死孤儿 | 低 |

**Cut 间依赖**：1 → 2 → 3 → 4 → 5 严格串行。Cut 1 单独可发；Cut 3 必须跟 Cut 4 同 release（版本号变更需要 edge 重算配合）。

**回滚原则**：每个 cut 独立可 revert。Schema 变更（Cut 1/3/4/5）都通过 alembic downgrade 路径回退；代码变更通过 git revert 单 PR 回退。

## 7. 验收指标

落地后 7 天观测，全部由 SQL 一次性查得：

| 指标 | 当前 | 目标 |
|---|---|---|
| 单 candidate 24h agent run p95 | 0–474 | ≤ 5 |
| `pulse_candidates` `blocked_low_information` 占比 | 52% | < 5% |
| `outcome='pending'` AND status IN ('done','failed') | 5142 | 0 |
| `subject.market_type` 与 `decision_route` 矛盾行数 | 51 | 0 |
| `pulse_status='theme_watch'` 行数 + 代码引用数 | 0 + 3 | 0 + 0 |
| `pulse_status='token_watch'` 行数 | 0 | > 0 |
| `notification_deliveries` 卡 running > 1h | 2 | 0 |
| `agent_runs` 总量 / `candidates` 总量 | 19.9 | < 3 |
| 端到端 job p90 时延 | 4.6h | < 5min |

**回归保护**：

- 现有 `tests/unit/domains/pulse_lab/` 全套通过。
- 新增 edge diff 算法 6 个 unit test（每个 edge event 一个）+ budget bucket 3 个 test（不触顶 / 触顶丢弃 / 跨小时重置）+ outcome NOT NULL 强制 1 个 test。
- 现有 `tests/component/features/signal-lab/` 全套通过；前端读取 `pulse_candidates` 字段无 breaking。
- 落地前在 staging 全量回放历史 24h 上游数据，对照 edge events 触发分布与 `agent_runs` 数量比预期。

## 8. 公共 Contract 变更

| 字段 | 变更类型 | 影响面 |
|---|---|---|
| `pulse_agent_runs.outcome` | NOT NULL + CHECK 收紧 | 内部 + replay |
| `pulse_candidates.last_edge_events_json` | 新增 NOT NULL DEFAULT | 前端可选展示 |
| `pulse_status` 允许值 | 移除 `theme_watch` | 内部 + 前端 enum |
| `candidate_type` 允许值 | 移除 `source_seed` | 内部 + 前端 enum |
| `pulse_candidate_run_budget` | 新表 | 仅 worker 内部 |
| `finish_agent_run` Python 签名 | `outcome` 改必传 | 仅 worker 调用方 |
| `notification_deliveries` claim 索引 | 覆盖 running | 仅运行时性能 |

前端 enum 收敛（`theme_watch` / `source_seed` 移除）需要同步 `web/src/features/signal-lab/` 内类型与展示分支。这是 hard cut 的一部分，**不**保留旧 enum 兜底分支。

## 9. 已知风险

1. **edge events 设计漏项**：6 个 event 若漏掉真实重要跳变（如"流动性掉破阈值"），会出现"应该重算但没重算"的 stale candidate。缓解：第 7 节 staging 24h 回放对照分布；触底通过 token bucket 数据反推遗漏类型。
2. **identity 解析延迟导致 source_seed 流失**：原来 source_seed 至少留个 audit record，新设计完全丢弃。缓解：identity 解析失败本身在 `token_intel.token_intent_resolutions` 表有完整 audit，不依赖 pulse_candidates。
3. **token_watch 激活后 LLM 调用量上升**：起点从 70 降到 45 会引入更多候选。缓解：edge-trigger + token bucket 双层节流是主体；预期净调用量仍下降（TROLL 重跑爆炸的省下来）。
4. **schema 破坏性变更影响下游**：notification_rules / 前端 enum 都依赖移除的枚举值。缓解：第 8 节列出的所有消费点同 release 改齐，hard cut 不留兼容层。
