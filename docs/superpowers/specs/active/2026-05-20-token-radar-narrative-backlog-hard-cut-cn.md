# Spec — Token Radar Narrative Backlog Hard Cut

**Status**: Draft
**Date**: 2026-05-20
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-20-token-radar-narrative-backlog-hard-cut-plan-cn.md`

## Background

Token Radar 的叙事分析链路已经被拆成三类 read model writer：
`NarrativeAdmissionWorker` 写 `narrative_admissions`，`MentionSemanticsWorker`
写 `token_mention_semantics`，`TokenDiscussionDigestWorker` 写
`token_discussion_digests`。这个单 writer 约束来自全局架构 invariant，明确写在
`docs/ARCHITECTURE.md:59-76`。

当前实现里，admission worker 已经从 Token Radar frontier 重建 admission source
set，并写入 source metadata；它在 `narrative_admission_worker.py:47-131` 遍历
window/scope、读取 radar rows、构造 `source_set_for_admission`，然后 upsert
admissions 并 suppress frontier 外目标。

`MentionSemanticsWorker` 仍然在一个 run loop 中同时做 pending prune、claim、
enqueue missing semantics、再次 prune、再次 claim。这个顺序在
`mention_semantics_worker.py:44-60`；它还保留了
`max_pending_source_age_seconds=43200` 的 source-age prune 配置读取和执行路径
`mention_semantics_worker.py:226-238`。默认 runtime 配置把 narrative windows 设为
`5m,1h,4h,24h`，但 mention semantics 的 pending source age 默认只有 12 小时：
`settings.py:741-771` 和 `settings.py:1440-1465`。

`MentionSemanticsWorker` 的 enqueue 路径目前按 admission 扫描 source rows，受
`max_semantic_rows_enqueued_per_cycle=40` 和 `max_pending_semantics_per_target=80`
限制；预算不足时它会把 missing rows 计入
`semantic_suppressed_budget`，但仍把 admission 标记为 scanned：
`mention_semantics_worker.py:241-313`。这会隐藏真实 backlog。

Digest 侧也存在一个结构性误判。`digest_context` 在
`narrative_repository.py:948-989` 用 `LIMIT max_mentions` 读取 prompt sample，同时
`DiscussionDigestService.refresh_decision` 在
`discussion_digest_service.py:45-88` 用 `len(semantic_rows) < source_count` 判定
`semantic_labeling_pending`。由于 `max_mentions_per_digest` 默认是 24
（`settings.py:779-799`），当 source set 大于 prompt cap 时，系统可能把“为了控
prompt 而截断”误判成“语义标签还没完成”。

Digest worker 还会顺序处理最多 25 个 due targets，并对每个 `thresholds_met`
target 发起 LLM 调用；这个串行循环在 `token_discussion_digest_worker.py:55-236`。
当多个 target 同时接近 180 秒 timeout，一轮 worker 会被放大到分钟级甚至十几分钟。

当前 health query 只统计 `token_mention_semantics` 中已有 row 的
`queued/retryable/stale`，见 `narrative_backlog_health_query.py:59-96`，无法显示
“admission source_event_ids 中存在但 semantics 表还没有 row”的真实缺口。公共 read
model 读取 current digest 时也只按 target/window/scope/schema/is_current 查
`token_discussion_digests`，并在 lateral 子查询里统计已有 semantics backlog，见
`narrative_repository.py:1110-1155`；它不会过滤 suppressed admission，也看不到
missing semantics rows。

Deep review 后还确认了两个必须硬切的读路径风险：

- Digest public currentness 如果要求 `source_fingerprint` 匹配 admission，那么
  digest writer 必须把 `context["source_fingerprint"]` 写进 ready/status digest。
  否则新写入 digest 会被新的 public join 自己过滤掉。
- Digest completeness 不能再用 `now - window` 做二次过滤。Admission worker 已经拥有
  source window 选择权；digest worker lag 后再按当前时间裁剪 source ids，会让完整性分母
  漂移，重新制造 hidden backlog。

2026-05-20 live-data 诊断确认了这些代码问题在真实运行中同时出现：

- Token Radar projection 正常，`token_radar_projection` worker 仍持续写 rows。
- `narrative_admission` 正常扫描并 upsert frontier。
- 当前 admitted source rows 约 `6617`，已有 semantics 约 `2188`，missing semantics
  约 `4429`，但 `queued/retryable/stale` semantics 队列为 `0`。
- 当前 digest 里 `pending=185`、`ready=3`；其中 `semantic_labeling_pending` 的
  admitted pending digest 有 72 个，全部 `pending_rows=0`。
- 最近一轮 mention semantics 出现 `enqueue_semantic_inserted=40`、
  `prune_deleted_old_semantics=39`、`claimed=1` 的模式，说明 24h/4h source 被
  12h prune 与小预算组合抵消。
- 当前 pending digest 中存在 source/semantics 已完整且实际 coverage 已达标的样本，
  仍保留 `semantic_labeling_pending`，说明 digest context 的 prompt cap 误判已进入
  read model。

## Problem

Token Radar 的叙事分析在用户看来仍然严重阻塞：大量 token 行显示 pending、
insufficient 或旧的语义缺口，ready digest 极少。系统内部 worker 状态却显示
running/healthy，因为真实 backlog 被表示在 `narrative_admissions.source_event_ids`
和 `token_mention_semantics` 的差集中，而现有 health/read model 只看已有
semantics rows。这个错位会让操作员误判为“LLM 慢”或“Token Radar 坏”，实际根因是
source-set、semantics queue、digest completeness 和 current read model 的契约不一致。

## First Principles

1. **Source facts are not LLM facts.** Source volume 必须来自 material facts 和
   admission source set；semantic coverage 是对 source set 的解释覆盖，不得反向定义
   source count。全局架构要求 facts-first persistence 和 one writer per read model，
   见 `docs/ARCHITECTURE.md:59-76`。
2. **Prompt sample is not completeness.** `max_mentions_per_digest` 是 LLM prompt 预算，
   不是 source-set 或 semantic coverage 的分母。任何 completeness 判断都必须先在
   SQL/context 层对完整 admission source set 聚合，再选择 bounded prompt sample。
   Digest worker 不得用 `now - window` 对 admission source set 做第二次 completeness
   过滤；window 边界只由 admission source projection 决定。
3. **Hard cut means no runtime compatibility.** 本仓库已经定义 hard cut 不保留 runtime
   compatibility layer，见 `docs/ARCHITECTURE.md:82-85`。本修复不得保留旧
   `max_pending_source_age_seconds` prune、旧 current digest fallback、旧
   “缺 semantics row 就假装 queue depth 为 0” 的 runtime 行为。
4. **Agent execution is capacity, not truth.** `AgentExecutionGateway` 管 LLM 执行面，
   domain workers 仍拥有 admission、claim、retry、finalize、read-model writes 和业务
   validation，见 `docs/ARCHITECTURE.md:101-113`。不能通过扩大 LLM timeout 掩盖
   worker 状态机错误。

## Goals

- **G1 — No hidden semantic backlog.** Narrative health 必须同时暴露已有
  `queued/retryable/stale` rows 和 `admitted source rows minus semantics rows` 的
  missing count。验收时 admitted `missing_semantic_rows` 不能再被 `total_pending=0`
  掩盖。
- **G2 — Remove age-prune compatibility path.** Runtime 不再读取或执行
  `max_pending_source_age_seconds`；current admitted source set 内的 missing/pending
  semantics 不因 source age 超过 12h 被 prune。旧 key 从 default workers YAML 和
  tests 中硬切删除。
- **G3 — Budget exhaustion stays due.** 当 semantics enqueue budget 用尽，worker
  不得把仍有 missing semantics 的 admission 推迟完整 interval；必须保留 due 或短
  backoff，并在 notes/health 中暴露 `missing_after_enqueue`。
- **G4 — Digest completeness uses full source set.** Digest context 返回完整 source-set
  聚合计数：`source_event_count`、`semantic_row_count`、`missing_semantic_count`、
  `pending_semantic_count`、`labeled_event_count`、`terminal_unavailable_count`。
  `refresh_decision` 只用这些聚合判断 status，不再用 prompt sample 长度推导 unseen。
  这些聚合不得被 `since_ms`、当前 wall clock、prompt limit 或 LLM retry delay 裁剪。
- **G5 — No suppressed current digests on public read path.** Public Token Radar/Token
  Case narrative hydration 不得返回 suppressed admission 对应的 current digest。被
  suppress 或 source fingerprint 变化的 digest 必须显示为 stale/not ready，直到 digest
  writer 写入新 current row。Read path 必须返回明确 reason：`digest_not_ready`、
  `digest_stale` 或 `not_in_current_frontier`，不能把所有 missing state 折叠成
  `digest_not_ready`。
- **G6 — Bounded LLM amplification.** Digest worker 每轮 LLM 调用数和 provider failure
  数有独立上限；状态-only digest 可以批量处理，但 LLM target 不得让单轮无限串行到
  25 * 180s。这个目标只保证“有界慢”，不承诺单次 180s provider timeout 变成非阻塞；
  真正 durable async LLM job lane 是后续演进。
- **G7 — Formal rebuild/drain.** 上线流程必须通过 ops 命令清理旧状态：删除 current
  frontier 外 queued/retryable semantics、标记 suppressed/stale digest、重建 current
  admissions、drain due semantics/digests。不得依赖手工 SQL。
- **G8 — Tests enforce hard boundaries.** 单元、集成、架构测试必须覆盖：无旧 config
  key、无 source-age prune、health 看到 missing rows、digest prompt cap 不影响
  completeness、suppressed digest 不出现在 public hydration、digest LLM cap 生效。
- **G9 — Digest fingerprint write-through.** Deterministic status digest 和 ready digest
  都必须从 digest context 写入 current admission `source_fingerprint`。Public read path
  的 fingerprint match 必须允许新写入的 matching digest 立即可见。
- **G10 — Realtime wake wiring.** Narrative mention/digest workers 应接入 wake listener，
  让 `token_radar_updated` / `narrative_semantics_updated` 等 wake hints 触发更快 catch-up；
  `NOTIFY` 仍只是 hint，workers 继续按 bounded interval catch-up。

## Non-goals

- 不修改 Token Radar scoring、ranking、factor snapshot、market readiness 或 identity
  resolver。
- 不新增外部数据源，不做人工标注，不训练模型。
- 不承诺所有 token 都生成 ready digest；source 不足、作者不足、semantic coverage 不足
  时仍应诚实返回 insufficient/pending/semantic_unavailable。
- 不把 provider timeout 改写成 ready digest。
- 不通过前端文案隐藏后端状态。
- 不保留旧 runtime compatibility path、旧 config alias、旧 fallback digest 读取。

## Target Architecture

目标架构保留三段 writer，但收紧每段契约：

```text
token_radar_rows + token_radar_projection_coverage
  -> NarrativeAdmissionWorker
       writes narrative_admissions as current source-set projection
  -> MentionSemanticsWorker
       claims existing due rows first
       enqueues missing rows from admitted source sets without age prune
       writes token_mention_semantics
  -> TokenDiscussionDigestWorker
       builds full source-set aggregate + bounded prompt sample
       writes token_discussion_digests
  -> NarrativeReadModel
       hydrates public rows only from admitted current source sets
```

The hard cut removes any runtime behavior where:

- missing semantics can disappear because no row exists in `token_mention_semantics`;
- prompt cap acts as source-set completeness;
- current digest survives public hydration after its admission is suppressed;
- old source-age prune deletes current 24h/4h backlog;
- digest worker serially spends an entire cycle on unbounded LLM attempts.
- digest writer produces rows that cannot pass its own public fingerprint gate.
- narrative workers declare `wakes_on` but only rely on polling for catch-up.

## Conceptual Data Flow

```text
Token Radar latest projection
  -> admitted source set
  -> missing semantics materialized as explicit queue rows
  -> semantic labels or terminal unavailable
  -> full-source aggregate digest decision
  -> bounded LLM digest only when ready
  -> public hydration filtered by admitted current source set
```

Changed arrows:

- `admitted source set -> missing semantics`: no source-age prune; enqueue budget exhaustion
  remains visible and due.
- `semantic labels -> digest decision`: digest uses aggregate counts over full source set, then
  selects a prompt sample.
- `digest -> public hydration`: hydration requires an admitted current source set, not only a
  `token_discussion_digests.is_current=true` row.

No new provider arrows are introduced. No API route writes facts or calls an LLM.

## Core Models

**Narrative admission source set**

- Current source-set projection for `(target_type, target_id, window, scope, schema_version)`.
- Owns `source_event_ids_json`, `source_event_count`, `independent_author_count`,
  `source_fingerprint`, `source_window_start_ms`, `source_window_end_ms`,
  `projection_computed_at_ms`, and scheduling due timestamps.
- Status is only `admitted` or `suppressed`.

**Semantic coverage aggregate**

- Derived at query time from admission source set left joined to
  `token_mention_semantics`.
- Fields: `source_event_count`, `semantic_row_count`, `missing_semantic_count`,
  `pending_semantic_count`, `retryable_semantic_count`, `labeled_event_count`,
  `terminal_unavailable_count`.
- The aggregate is not persisted as a new read model in this spec.

**Prompt sample**

- Bounded subset of labeled mentions sent to the digest LLM.
- It carries `prompt_mention_count` and `prompt_mention_limit`.
- It never determines whether full source-set semantics are complete.

**Digest currentness**

- A digest is public-current only if it is `is_current=true`, matches an admitted source set,
  and its `source_fingerprint` matches the current admission source fingerprint.
- Suppressed or fingerprint-mismatched rows are stale/not ready from public perspective.
- Missing public state is represented as an explicit non-persisted read sentinel with one
  reason: `digest_not_ready`, `digest_stale`, or `not_in_current_frontier`.

## Interface Contracts

**HTTP `/api/status/narrative-health`**

Adds deterministic backlog fields under `semantic_backlog`:

- `missing_semantic_rows`
- `admissions_with_missing_semantics`
- `current_source_rows`
- `semantic_rows_for_current_sources`
- `pending_existing_rows`
- `suppressed_current_digest_count`
- `stale_fingerprint_current_digest_count`

Existing `queued/retryable/stale/unavailable` remain as explicit row-status counts, but
`total_pending` is redefined as existing due rows plus missing rows. This is a hard-cut
contract change; no old total is kept.

**HTTP `/api/token-radar` and Token Case/Search hydration**

Rows with no admitted current digest surface the existing missing digest shape, but the reason
must be truthful:

- `digest_not_ready` when no admitted/current digest exists;
- `digest_stale` when a digest exists but source fingerprint changed;
- `not_in_current_frontier` when only suppressed admission exists.

No fallback to suppressed current digest.

**CLI `uv run gmgn-twitter-intel ops rebuild-narrative-intel`**

The rebuild/drain command becomes the supported operational cleanup path. It must report:

- admissions rebuilt/suppressed;
- queued/retryable semantics deleted outside current source sets;
- missing semantics enqueued;
- digest rows marked stale due to suppressed/fingerprint mismatch;
- cycles run and remaining missing/pending counts.

**Operator config hard cut**

Before starting a new image, live `~/.gmgn-twitter-intel/workers.yaml` must not contain
`max_pending_source_age_seconds`. This is an intentional breaking config cut because
`PerWorkerSettings` rejects unknown keys. The deployment gate is:

```bash
uv run gmgn-twitter-intel config
```

The command must succeed with `workers_config_path` under `~/.gmgn-twitter-intel/`.

## Acceptance Criteria

- **AC1.** WHEN admitted source sets contain events with no matching semantics row THEN
  `/api/status/narrative-health` SHALL report non-zero `missing_semantic_rows` even if
  `queued/retryable/stale` existing rows are zero.
- **AC2.** WHEN a 24h admitted source event is older than 12h but remains in current
  `source_event_ids_json` THEN `MentionSemanticsWorker` SHALL not delete its queued
  semantics due to source age.
- **AC3.** WHEN semantics enqueue budget is exhausted before an admission is fully materialized
  THEN the admission SHALL remain due or receive a short retry due, and health SHALL show
  remaining missing semantics.
- **AC4.** WHEN source count is greater than `max_mentions_per_digest` and all source events
  already have terminal/labeled semantics THEN digest decision SHALL not return
  `semantic_labeling_pending` solely because the prompt sample is capped.
- **AC5.** WHEN an admission is suppressed THEN Token Radar hydration SHALL not return its old
  current digest as public narrative state.
- **AC6.** WHEN `thresholds_met` targets exceed digest `max_llm_calls_per_cycle` THEN
  `TokenDiscussionDigestWorker` SHALL process at most that many LLM calls and defer the
  remaining due targets without marking them failed.
- **AC7.** WHEN live rebuild/drain completes THEN top Token Radar rows SHALL show either a
  recent ready digest or an honest pending/insufficient reason backed by health counts, not
  stale `semantic_labeling_pending` with zero actual pending semantics.
- **AC8.** WHEN tests scan runtime config and worker code THEN no runtime reference to
  `max_pending_source_age_seconds` SHALL remain.
- **AC9.** WHEN a new ready or status digest is written for an admitted source set THEN it SHALL
  persist the admission `source_fingerprint` and be visible through public hydration when the
  fingerprint still matches.
- **AC10.** WHEN an admitted source event is older than `digest_now - window` but remains in
  `source_event_ids_json` THEN digest completeness SHALL still count it in the source-set
  aggregate.
- **AC11.** WHEN public hydration has only a suppressed admission or only a fingerprint-mismatched
  digest THEN it SHALL return `not_in_current_frontier` or `digest_stale` respectively, not a
  generic `digest_not_ready`.
- **AC12.** WHEN narrative workers are constructed in the runtime factory THEN
  `mention_semantics` and `token_discussion_digest` SHALL have wake waiters wired from their
  configured `wakes_on` channels.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Rebuild temporarily drops old current digests, making narrative panels look less populated. | Medium | This is intended hard-cut behavior; public rows must show honest `digest_not_ready` until rebuilt. Run drain on live data immediately after deploy. |
| Removing source-age prune increases semantic backlog for 24h windows. | High | Cap by current admission source set, per-cycle enqueue budget, per-admission enqueue cap, and LLM lane concurrency. Health exposes missing rows so backlog is visible. |
| Digest LLM cap slows ready digest generation. | Medium | It prevents 25-target serial timeout collapse. Status-only pending/insufficient rows still update quickly. |
| Public API contract changes break frontend assumptions about old reason strings. | Medium | Update API contract tests and frontend mapping in the same hard-cut change; no compatibility branch. |
| Suppressed digest filtering hides useful historical context. | Low | Historical rows stay in DB for audit; public read path only represents current frontier. |
| Ops drain mutates live read models incorrectly. | High | Implement dry-run summary first, run integration tests, and verify live health before/after. Avoid manual SQL. |
| Missing `source_fingerprint` write-through makes every new digest invisible. | High | Add service and integration tests proving new ready/status digests pass public hydration after fingerprint filtering. |
| Live `workers.yaml` still contains removed config key. | High | Make operator config update a pre-start gate; do not add runtime alias or compatibility shim. |

## Evolution Path

After this hard cut, the next evolution should be capacity tuning rather than new data models:

- adaptive per-window enqueue budgets;
- separate digest lanes for `5m/1h` hot windows and `4h/24h` cold windows;
- durable async LLM digest jobs if single-call 180s latency remains unacceptable;
- cheaper deterministic digest for high-confidence single-author cases;
- historical narrative explorer that intentionally reads stale/suppressed digests.

Do not foreclose those expansions by reintroducing fallback reads or by mixing historical
digests into current Token Radar hydration.

## Alternatives Considered

- **Only increase LLM timeout/concurrency** — rejected because live data shows missing rows are
  hidden before LLM execution; more timeout would amplify serial digest stalls.
- **Lower semantic coverage threshold** — rejected because it would publish weak digests and
  still leave hidden missing backlog unresolved.
- **Keep 12h prune but exclude 24h windows from narrative** — rejected because Token Radar
  product explicitly serves 24h/4h windows; if a window is supported, source-set semantics must
  be internally consistent.
- **Fallback to last ready digest for suppressed/mismatched admissions** — rejected because it
  violates no runtime compatibility and misrepresents current frontier state.
- **Add a new durable generic agent queue** — rejected because agent execution is an operational
  plane, not product truth; domain facts/read models already define the work.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use admitted source sets as source truth; expose missing semantics; filter public digests by admitted current source set; cap digest LLM calls; clean via ops command. |
| Ask first | Raising provider concurrency beyond current lane limits; changing Token Radar ranking; changing product thresholds such as `min_semantic_coverage`. |
| Never | Keep old source-age prune runtime path; fallback to suppressed/old digest; call providers from API; hide missing source semantics behind `queue_depth=0`; publish ready digest after provider failure. |
