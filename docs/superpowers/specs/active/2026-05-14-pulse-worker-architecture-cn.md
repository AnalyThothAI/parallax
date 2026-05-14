# Pulse Worker Architecture — Edge-State Hard Cut Spec

**Status**: Approved for hard-cut implementation
**Date**: 2026-05-14
**Owner**: Codex with Qinghuan
**Scope**: 重设计 Signal Pulse worker 的入队触发、状态账本、持久化 outcome、source-led 输入边界，以及 Signal Pulse 通知链路。本文是 spec；文件级步骤与 SQL 细节见配套 plan。
**Harness**: 保留 `openai-agents-python` 与现有 Analyst → Critic → Judge stage runner；不改 agent 内部 prompt / stage schema。

**Related**:

- `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`
- `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`
- `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/RELIABILITY.md`

---

## 一句话结论

把 Signal Pulse 从“轮询 + signature/cooldown”改成 **edge-state 驱动的 token_target 决策队列**。worker 只在 token 的结构化状态发生真实跳变时入队；状态前态不再借用 `pulse_candidates`，而是写入独立 `pulse_candidate_edge_state`。`source_seed` 和 `theme_watch` 从运行时、schema、API、通知、前端中硬删除。`pulse_agent_runs.outcome` 不再允许 `pending`，运行中为 `running`，结束必须落 closed-form outcome。通知链路改为 edge signature 级去重，delivery claim 原子回收 stale running。

这次不保留兼容性代码：不 dual write，不 fallback 旧 enum，不把 source-led fake snapshot 包成候选，不继续支持 cooldown 字段。

## 1. 当前事实

2026-05-14 的 24h 实测显示：

| 维度 | 数值 |
|---|---|
| `pulse_agent_jobs` 总量 | 750（done 709 + dead 40 + running 1） |
| `pulse_agent_runs` 总量 | 5879 |
| `pulse_candidates` 总量 | 295 |
| job → run 倍数 | 7.8x |
| 单 candidate 最高 run 数 | TROLL 474 次，其中 failed 239、completed 8 |
| 端到端 job 时延 | p50 10 分钟，p90 4.6 小时，max 69 小时 |
| stage 失败率 | analyst 29%，critic 33%，judge 17% |
| 候选池 `blocked_low_information / source_seed` 占比 | 52%（153/295） |
| `outcome='pending'` 但 status != running 的 agent_runs | 5142 |
| `subject.target_market_type` 与 `decision_route` 矛盾的 candidates | 51 |
| `pulse_status='token_watch'` 行数 | 0 |
| `pulse_status='theme_watch'` 行数 | 0；但代码/API/前端仍保留 enum |
| `notification_deliveries` 卡 running > 1h | 2（TAU、NICHEBABY，53 小时） |

代码审计对应点：

- `PulseCandidateWorker._source_context` 会构造 `candidate_type='source_seed'` 且无 target 的 fake factor snapshot。
- `_cooldown_active` / `_cooldown_bypass` 把数值变化当状态跳变，hot token 实际不被节流。
- `finish_agent_run` 的 `outcome` 是可选参数，失败路径没有显式写 `failed`。
- `theme_watch` 仍存在于 `pulse_lab.interfaces`、read model、API status parser、notification rules、frontend enum。
- `notification_deliveries.claim_next_delivery` 不 reclaim stale `running`，claim index 也不覆盖 `running`。
- `NotificationRepository._pulse_source_status_duplicate` 按 source/status 聚合，会吞掉同一 candidate 同一 status 下的新 edge。

## 2. 第一性原则

### 2.1 Worker 是 edge detector，不是 polling loop

Pulse worker 响应世界状态变化。轮询只负责补偿 missed wake hints，不是触发 agent 的理由。同一 token 在状态未跳变时重复入队是 bug。Cooldown 只能作为预算兜底，不是正确性机制。

### 2.2 Edge state 是事实账本，不是候选展示

`pulse_candidates` 是产品读模型，只保存当前值得复核的候选。它不是 edge detector 的前态来源，因为失败 run、dead job、abstain 短路、预算拒绝都可能没有更新候选。worker 必须拥有独立 `pulse_candidate_edge_state`：

- `latest_observed_state_json`: 最新扫描看到的状态。
- `last_processed_state_json`: 上一次成功入队/预算接受时的前态。
- `last_edge_events_json`: 上次触发的 edge events。
- `last_job_id` / `last_agent_run_id`: 与 audit ledger 对齐。

这保证失败路径不会把“首次触发”无限重放，也保证候选展示策略不会反向影响队列正确性。

### 2.3 每条 run 必须 closed-form outcome

`pulse_agent_runs` 是 audit ledger。运行中 outcome 是 `running`；结束后只能是 `completed`、`abstain`、`abstain_critic_veto`、`abstain_insufficient_data`、`failed`。`pending` 不是合法业务状态，schema 与 Python 签名都要禁止。

### 2.4 无 target 的 source-led 输入不进入 Pulse 候选池

watched-account social-event extraction 仍属于 `social_enrichment` / `closed_loop_harness`。Signal Pulse 只做有确定性 market target 的 token_target 决策。`source_seed identity_unresolved` 不写 `pulse_agent_jobs`、不写 `pulse_candidates`、不写 fake factor snapshot。identity 失败的审计留在 token intent / resolution / harness 链路。

### 2.5 通知消费 edge，不消费轮询噪声

Signal Pulse 通知不是“每个 status 每个时间桶提醒一次”，而是“每个真实 edge 提醒一次”。同 status 下新增 hard risk、recommended decision 改变、版本跃迁都必须能独立发通知；同一 edge 反复被扫描不能重复通知。

## 3. 目标

1. **Edge-state 入队**：只在结构化 edge events 出现时入队；同 candidate 24h run p95 <= 5。
2. **Run budget 兜底**：每 candidate 每小时最多 3 次入队；触顶只更新 observed state，不写候选、不调 agent。
3. **Closed-form outcome**：删 `pending` outcome；`finish_agent_run` 必传 outcome；done/failed + pending 在 schema 层不可能出现。
4. **删除 source_seed / theme_watch**：运行时、schema check、API、notification、frontend enum 同步硬切。
5. **激活 token_watch**：Pulse trigger 起点从 rank 70 降到 gate token_watch 45；`token_watch` 由 edge + budget 控制成本。
6. **Notification edge-native**：Signal Pulse 通知按 `candidate_id + notification_signature` 去重，payload 暴露 `edge_events`。
7. **Delivery stale lease**：delivery claim 原子 reclaim stale `running`，不依赖人工或启动一次性 hook。

## 4. 非目标

- 不重写 Token Radar factor snapshot、market contract 或 factor formula。
- 不修改 OpenAI Agents SDK stage 内部、不换 LangGraph/CrewAI/AutoGen。
- 不新增真实交易、仓位、止损、目标价或执行接口。
- 不引入 dashboard、alert manager、memory/reflection。
- 不保留 `source_seed`、`theme_watch`、`pending outcome`、cooldown 字段或旧 notification 聚合语义。

## 5. 目标架构

### 5.1 数据流

```text
Token Radar latest rows
  -> PulseCandidateWorker scan
  -> gate_pulse_candidate_from_factor_snapshot
  -> build_edge_state
  -> pulse_candidate_edge_state diff
  -> pulse_candidate_run_budget claim
  -> pulse_agent_jobs enqueue
  -> Pulse decision runtime
  -> pulse_agent_runs / pulse_agent_run_steps
  -> pulse_candidates current read model
  -> NotificationRuleEngine reads displayable pulse candidates
  -> notification_signature includes edge events
  -> notification_deliveries external delivery queue
```

Source-led social events do **not** branch directly into Pulse. They can still become Signal Pulse inputs later if Token Radar resolves them into a token target and emits a normal factor snapshot.

### 5.2 Edge state

Each scan computes a canonical next state:

```text
candidate_id
pulse_version
gate_version
target_type
target_id
pulse_status
score_band
candidate_score_bucket
recommended_decision
hard_risks
watched_confirmation
route
trigger_signature
```

Canonical state intentionally excludes raw counts such as exact watched mention count and exact independent author count. Those values remain in `factor_snapshot_json` for explanation, but do not trigger runs by themselves.

### 5.3 Edge events

| Event | Condition |
|---|---|
| `pulse_status_changed` | Previous status differs, including first accepted state. |
| `score_band_crossed` | Score band changes across high_conviction / watch / speculative / blocked. |
| `hard_risk_added` | New gate/hard risk appears. |
| `recommended_decision_changed` | Token Radar `composite.recommended_decision` changes. |
| `watched_emerged` | watched confirmation changes from false to true. |
| `pulse_version_bumped` | `pulse_version` or `gate_version` changes. |

Non-events: exact mention-count deltas, exact author-count deltas, cooldown expiry, periodic scan, unchanged failed job.

### 5.4 Budget semantics

`pulse_candidate_run_budget` enforces candidate/hour budget atomically in repository SQL. When budget allows, worker writes `last_processed_state_json = latest_observed_state_json` and enqueues. When budget rejects, worker updates only `latest_observed_state_json`, `last_budget_rejected_at_ms`, and `last_budget_rejected_events_json`.

This prevents both failure loops and silent state loss: after the hour resets, if the latest observed state still differs from last processed state, a new edge can be admitted.

### 5.5 Persistence hard cut

Required storage contract:

- `pulse_agent_jobs` no longer has `cooldown_until_ms`.
- `pulse_agent_runs.outcome` has no default and must satisfy:
  `running|completed|abstain|abstain_critic_veto|abstain_insufficient_data|failed`.
- `pulse_candidates.candidate_type` only permits `token_target`.
- `pulse_candidates.pulse_status` excludes `theme_watch`.
- `pulse_candidates.last_edge_events_json` is non-null.
- `pulse_candidate_edge_state` and `pulse_candidate_run_budget` are internal worker tables.
- `notification_deliveries` claim index includes `running`.

Old `source_seed` candidates/jobs are deleted by migration. Old `theme_watch` candidates/jobs are deleted by migration. Old `pending` run outcomes are backfilled before the check is applied.

### 5.6 Notification contract

Signal Pulse notification payload gains:

- `edge_events`: last edge events from the candidate.
- `notification_signature`: hash of candidate id, pulse status, score band, route, recommendation, edge events, factor fingerprint, and latest evidence bucket.

Notification insertion considers a row duplicate only if rule/source/signature match. Same candidate and same status with different edge signature is a new notification.

Delivery worker claim reclaims stale `running` rows inside `claim_next_delivery`:

- stale + attempts left -> claim again as `running`, incrementing attempt count.
- stale + attempts exhausted -> mark `dead`.

## 6. Public Contract Changes

| Surface | Change |
|---|---|
| Config defaults | `signal_pulse_candidate.statuses` no longer includes `theme_watch`. |
| API query status | `theme_watch` returns `invalid_status`. |
| Signal Pulse item | `candidate_type` is always `token_target`; `pulse_status` excludes `theme_watch`; `last_edge_events` is exposed. |
| Signal Pulse summary | no `theme_watch` key. |
| Frontend types | `SignalPulseStatus` excludes `theme_watch`; UI filters remove the theme tab/pill. |
| Notifications | Signal Pulse payload includes `edge_events`; dedup semantics are edge signature based. |
| DB | No `source_seed`, no `theme_watch`, no `pending` outcome, no job cooldown column. |

## 7. Migration Strategy

This is one hard-cut release with ordered migration inside one Alembic revision:

1. Backfill run outcomes.
2. Delete `source_seed` and `theme_watch` Pulse jobs/candidates.
3. Add edge state and run budget tables.
4. Add `last_edge_events_json`.
5. Add check constraints for candidate type, status, outcome, and route/recommendation if missing.
6. Drop `cooldown_until_ms`.
7. Replace notification claim index.

Rollback is a code revert plus Alembic downgrade. Downgrade may recreate `cooldown_until_ms` and reintroduce looser checks, but deleted legacy `source_seed` rows are intentionally not restored.

## 8. Acceptance Metrics

Measured after 7 days:

| Metric | Target |
|---|---|
| Candidate 24h agent run p95 | <= 5 |
| `outcome='pending'` rows | 0 |
| `source_seed` Pulse jobs/candidates | 0 |
| `theme_watch` runtime/API/frontend references | 0 |
| `token_watch` candidates | > 0 when eligible rows exist |
| `notification_deliveries` running > 1h | 0 |
| Signal Pulse notification duplicates for same edge | 0 |
| Agent runs / candidates | < 3 |
| Job p90 latency | < 5 min |

## 9. Risks

1. **Missed edge event**: Important state changes may not trigger. Mitigation: `latest_observed_state_json` preserves skipped state and budget rejection events; metrics can reveal frequent budget misses or stale processed state.
2. **token_watch cost increase**: Lower trigger threshold admits more tokens. Mitigation: edge-state + 3/hour budget should reduce total calls despite broader first eligibility.
3. **source-led product expectation changes**: Theme-like source intelligence disappears from Signal Pulse. Mitigation: source-led intelligence remains queryable in social events / attention seeds / harness; Signal Pulse is explicitly token_target only.
4. **Frontend enum breakage**: Hard cut removes values. Mitigation: same release updates generated/openapi/frontend local types and UI filters.
5. **Migration data loss for legacy candidates**: `source_seed` / `theme_watch` rows are deleted. This is intentional under hard-cut policy; durable evidence remains in upstream tables.
