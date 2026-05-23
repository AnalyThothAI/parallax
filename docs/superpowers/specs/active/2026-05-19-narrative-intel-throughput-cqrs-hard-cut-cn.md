# Spec — Narrative Intelligence Throughput CQRS Hard Cut

**Status**: Draft, awaiting review
**Date**: 2026-05-19
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-18-token-narrative-intelligence-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-18-token-narrative-intelligence-hard-cut-plan-cn.md`

## 一句话

把 Narrative Intelligence 从"Token Radar 旁路增强"硬切成一条严格 Kappa/CQRS 的独立解释流水线：最新 Radar projection 只做 admission frontier，material facts 生成 source set，独立 admission worker 写 `narrative_admissions`，semantics worker 只写 `token_mention_semantics`，digest worker 只写 `token_discussion_digests`，并用 source set + left-joined semantics 判定 `pending | insufficient | ready`。上线时正式清理历史积压，不保留旧 runtime 兼容路径。

## 当前事故判断

2026-05-19 对本地真实运行做过一次诊断。按项目规则先运行 `uv run gmgn-twitter-intel config`，确认 live-data 配置来自 operator-owned 文件：

- `config_path`: `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path`: `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`

诊断结论不是 Token Radar projection 坏了。`token_radar_projection` 仍在产出新鲜 rows，问题集中在 Narrative Intelligence 的 admission、semantic labeling 和 digest 状态判定。

关键运行证据：

- `/api/status/narrative-health?since_hours=4` 显示 semantic backlog 非常大：`total_pending=11386`，其中 `queued=9441`、`retryable=1945`、`unavailable=3`。
- 最近 4 小时 `mention_semantics` 只有 `success=1`、`failure=8`、`timeout=8`；`discussion_digest` 有成功但也有 failure/timeout。
- Token Radar top rows 没有大面积 ready digest：`1h/all` top20 中 `insufficient=7`、`pending=13`；`4h/all` top20 中 `insufficient=3`、`pending=17`；`24h/all` top20 中 `insufficient=1`、`pending=19`。
- retryable 错误主要是 provider 连接或超时：`TimeoutError:` 约 1924 条，`APIConnectionError: Connection error.` 约 14 条。
- `mention_semantics` worker 最近一次迭代扫描/调度成本远大于产出：`processed=10`、`labeled=10`，但 notes 里有 `admission_radar_rows=1600`、`admission_due_admissions=200`、`admission_source_mentions=5439`、`admission_semantic_inserted=5`、`admission_semantic_existing=35`、`admission_semantic_suppressed_budget=5399`、`admission_semantic_pending_before=14495`，iteration duration p99 约 843 秒。

这说明系统不是"没有数据"，而是把三个不同问题混成了一个 worker 热路径：

1. admission/source-set 重建；
2. semantic queue 填充；
3. provider labeling 执行。

这违反了项目已经写明的 Kappa/CQRS 约束：facts 是唯一业务真相，derived read model 每个只有一个 runtime writer，`NOTIFY` 只是 wake hint，API/request path 不能补写事实或临时跑 provider。

## 根因结论

这不是单纯"清 backlog"能解决的问题。清 backlog 只会让症状短暂好转，下一轮高流量或 provider timeout 仍会复发。

根因有四层。

**R1: Source truth 被 semantic coverage 反向定义。** 当前 `digest_context` 用 `token_mention_semantics` rows 数量作为 `source_event_count`。当语义标签缺失时，系统把"尚未标注"误判成"没有足够 source"，于是 digest 输出 `low_source_volume -> insufficient`，前端显示"叙事样本不足"。这从第一性原则上是错的：source volume 来自 material facts/source set，不来自 LLM 标签表。

**R2: Admission frontier 没有绑定最新 Radar projection batch。** 当前 admission query 按 `computed_at_ms DESC, rank ASC LIMIT N` 取 rows，但没有先通过 `token_radar_projection_coverage` 锁定 `(projection_version, window, scope)` 的 latest ready `computed_at_ms`。在多窗口、多历史批次、稀疏当前批次下，worker 会把历史 rows 混入 admission，导致 source set 和 queue 膨胀。

**R3: Worker 把控制面扫描和执行面 labeling 串在同一轮里。** `MentionSemanticsWorker.run_once_async` 先 `_reconcile_admissions_and_enqueue_sync`，再 `_claim_due_rows_sync`。当 admission/source scan 巨大时，worker 大部分时间花在扫描和排队上，只剩很小 batch 给 provider；provider 又超时，backlog 进一步滚大。

**R4: 2026-05-18 spec 方向正确，但没有把硬边界写到足够强。** 它要求新增 `narrative_intel` 域、per-mention semantics、discussion digest、Pulse 只做 overlay，这些方向是对的。但它没有强制规定：

- admission 必须以 latest Radar projection coverage 为 frontier；
- source set 必须独立于 semantic rows；
- `narrative_admissions` 必须有自己的单一 writer；
- `MentionSemanticsWorker` 不得扫描 source facts 或写 admission；
- digest status 必须区分 source 不足和 semantic labeling pending；
- backlog drain/rebuild 必须作为正式运维流程，而不是手工 SQL。

因此最终判断是：**既有落地没有严格执行 Kappa/CQRS，也暴露了原 spec 缺少操作性硬约束。** 本 spec 是对 2026-05-18 spec 的根因补强，不是新增一个并行产品方向。

## 非协商约束

- 不保留旧 runtime compatibility path。
- 不在 API request path 跑 provider、写 read model、补 admission、补 queue。
- 不让 Pulse 成为 Radar/Digest 上游。
- 不把 `token_mention_semantics` 当 source truth。
- 不用历史 Radar rows 补当前 admission frontier。
- 不用手工 SQL 作为长期修复；清理积压必须通过正式 rebuild/drain 流程表达。
- 不把多个 read model 的写入塞回一个 worker。
- 不为了快速显示 ready digest 而降低 evidence refs 或 semantic coverage 的可审计要求。

## Goals

- **G1 Current frontier admission.** Narrative admission 只来自 latest ready Radar projection batch，按 `(projection_version, window, scope, computed_at_ms)` 明确绑定，不能跨历史批次取 rows。
- **G2 Source set first.** `narrative_admissions` 存储当前 token/window/scope 的 source set metadata：source event ids、source count、independent author count、source window、source fingerprint、projection computed_at。这个 source set 来自 material facts 和当前 Radar frontier，不来自 semantic labels。
- **G3 Single writer split.** 新增 `NarrativeAdmissionWorker` 作为 `narrative_admissions` 唯一 writer；`MentionSemanticsWorker` 只写 `token_mention_semantics`；`TokenDiscussionDigestWorker` 只写 `token_discussion_digests`。
- **G4 Claim-first semantic execution.** Semantics worker 先 claim due semantic rows 并执行 provider labeling；只有当 backlog 低于水位时，才从 current admissions 的 source set 中 enqueue missing semantics。它不再扫描 token_intent_resolutions 生成 source_mentions。
- **G5 Correct digest status.** Digest context 由 admission source set left join semantics 构造。source 足够但 semantics 未覆盖时必须是 `pending/semantic_labeling_pending`，不能是 `insufficient/low_source_volume`。
- **G6 Backpressure is correctness.** Provider timeout、retryable backlog、pending cap hit 必须阻止系统伪装成 ready 或 insufficient。状态要诚实表达为 pending/unavailable，并在 health endpoint 暴露 backlog 和 throughput。
- **G7 Formal backlog drain.** 上线后用正式 ops/rebuild 命令清掉历史错误 admission 和不再属于 current source set 的 queued/retryable semantics，重建 current frontier，不把历史积压带入新状态机。
- **G8 Architecture tests.** 用测试守住 worker ownership、latest projection admission、source-count-from-source-set、request-path no writes/no provider 这些边界。

## Non-goals

- 不改 Token Radar ranking、factor snapshot、market gate 或 projection scoring。
- 不扩大数据源，不新增人工标注或训练流程。
- 不承诺每个 token 都有 ready digest；低信息 token 应显示真实 `insufficient`。
- 不把 provider 超时包装成"叙事不足"。
- 不做前端文案层面的遮羞修复。
- 不保留旧 digest/status 映射兼容层。

## Target Architecture

目标是把 Narrative Intelligence 拆成三段独立 CQRS read-model flow。

```text
material facts
  events / token_intent_resolutions / enriched_events / market_ticks
        |
        v
token_intel TokenRadarProjectionWorker
  writes token_radar_current_rows + token_radar_projection_coverage
        |
        | latest ready coverage is admission frontier only
        v
narrative_intel NarrativeAdmissionWorker
  reads latest radar frontier + material source facts
  writes narrative_admissions
        |
        | source set ids, no provider
        v
narrative_intel MentionSemanticsWorker
  reads narrative_admissions source sets
  writes token_mention_semantics
        |
        | labels left-joined to source set
        v
narrative_intel TokenDiscussionDigestWorker
  reads narrative_admissions + token_mention_semantics
  writes token_discussion_digests
        |
        v
API read composition -> Token Radar / Token Case / semantic timeline
```

Ownership table:

| Read model / state | Writer | Readers |
|---|---|---|
| `token_radar_current_rows` | `TokenRadarProjectionWorker` | API, NarrativeAdmissionWorker, Pulse |
| `token_radar_projection_coverage` | `TokenRadarProjectionWorker` | API, NarrativeAdmissionWorker |
| `narrative_admissions` | `NarrativeAdmissionWorker` | MentionSemanticsWorker, TokenDiscussionDigestWorker, health query |
| `token_mention_semantics` | `MentionSemanticsWorker` | Digest worker, timeline read model, health query |
| `token_discussion_digests` | `TokenDiscussionDigestWorker` | API, Token Case, Token Radar composition, Pulse evidence builder |
| `narrative_model_runs` | `MentionSemanticsWorker`, `TokenDiscussionDigestWorker` for their own stages | audit/health only |

`narrative_model_runs` is audit state, not product truth. Product truth remains facts and current read models.

## Admission Frontier

Admission must start from `token_radar_projection_coverage`, not from a free scan over historical Radar snapshots.

Required query shape:

```sql
WITH latest AS (
  SELECT computed_at_ms
  FROM token_radar_projection_coverage
  WHERE projection_version = :projection_version
    AND "window" = :window
    AND scope = :scope
    AND status = 'ready'
    AND computed_at_ms IS NOT NULL
)
SELECT rows.*
FROM token_radar_current_rows AS rows
JOIN latest ON latest.computed_at_ms = rows.computed_at_ms
WHERE rows.projection_version = :projection_version
  AND rows."window" = :window
  AND rows.scope = :scope
  AND rows.target_type IS NOT NULL
  AND rows.target_id IS NOT NULL
ORDER BY rows.rank ASC
LIMIT :limit;
```

If coverage is missing, failed, stale, or has `computed_at_ms IS NULL`, admission worker does not backfill from history. It records a skipped reason and waits for the next interval/wake.

No carry set in this fix. Carrying historical rows is how old admissions leak into current backlog. If Token Case later needs user-demand admission, that must be a separate explicit control-plane contract with TTL, not an implicit historic Radar fallback.

## Source Set Contract

`narrative_admissions` becomes the source-set projection, not just a scheduling row.

Required fields after hard cut:

| Field | Meaning |
|---|---|
| `projection_computed_at_ms` | latest Radar projection batch that admitted this target |
| `source_window_start_ms` | source window start for this admission |
| `source_window_end_ms` | source window end, normally projection computed_at |
| `source_event_ids_json` | bounded source event ids for this target/window/scope |
| `source_event_count` | count from source set, independent of semantics |
| `independent_author_count` | author count from source events |
| `source_fingerprint` | deterministic fingerprint of source event ids and source max received time |
| `last_radar_rank` / `last_rank_score` | admission priority metadata only |
| `status` | `admitted` or `suppressed` |

Source set generation uses material facts:

- `events`
- `token_intent_resolutions`
- current target identity from resolution facts
- `events.received_at_ms` bounded by window
- `events.is_watched` when scope is `matched`

`token_radar_current_rows.source_event_ids_json` may be used as an admission seed or priority hint, but not as the only source of source volume if it is capped or partial. The source set query owns this expansion and must be bounded by config.

## Worker State Machines

### NarrativeAdmissionWorker

Responsibilities:

- read latest ready coverage per configured `(window, scope)`;
- read current Radar rows from exactly that projection batch;
- build bounded source sets from facts;
- upsert `narrative_admissions`;
- suppress admissions no longer in the current frontier;
- emit wake hint for semantics/digest workers.

It never calls LLM providers and never writes semantics/digests.

### MentionSemanticsWorker

Responsibilities:

- claim due `token_mention_semantics` rows with `FOR UPDATE SKIP LOCKED`;
- send bounded batches to provider;
- write labels, retryable errors, or terminal `semantic_unavailable`;
- enqueue missing semantics only from `narrative_admissions.source_event_ids_json`, and only when queued/retryable backlog is below configured waterline.

It must not:

- call `admitted_radar_rows`;
- call `source_mentions_for_admission`;
- upsert or update `narrative_admissions`;
- spend a provider cycle scanning thousands of source mentions.

### TokenDiscussionDigestWorker

Responsibilities:

- claim due admitted targets;
- build digest context from admission source set left join current semantics;
- write current digest with honest status;
- call provider only when source volume and semantic coverage thresholds are met;
- record failed provider runs without turning provider failure into `insufficient`.

It must not enqueue semantics or mutate admissions except its own digest due timestamp if that timestamp remains in admission scheduling state.

## Digest Status Rules

Digest status is a product contract, not a UI convenience.

| Condition | Status | Reason |
|---|---|---|
| no current admission/source set | `pending` or absent | `not_admitted` |
| `source_event_count < min_source_mentions` | `insufficient` | `low_source_volume` |
| `independent_author_count < min_independent_authors` | `insufficient` | `low_independent_author_count` |
| source sufficient, semantics missing/unseen/retryable | `pending` | `semantic_labeling_pending` |
| source sufficient, provider circuit open | `pending` | `semantic_provider_backpressure` |
| source sufficient, all attempted and terminal unavailable | `semantic_unavailable` | `semantic_provider_unavailable` |
| source sufficient, coverage below threshold and no pending/unseen | `insufficient` | `low_semantic_coverage` |
| coverage met and digest provider succeeds | `ready` | `thresholds_met` |
| source fingerprint changed while old ready exists | `pending` or `ready` for new fingerprint | never silently reuse old ready |

The important hard cut: **`low_source_volume` can only be produced from source set count, never from `len(token_mention_semantics)`**.

## Backpressure And Provider Failure

Provider failure is not a data-quality judgment. It is execution state.

Required runtime behavior:

- expose timeout/error ratios per stage in status/health;
- use exponential backoff or bounded retry for `retryable_error`;
- terminalize after max attempts as `semantic_unavailable`;
- stop enqueueing new semantic rows when pending backlog exceeds waterline;
- prioritize current Radar frontier rows over obsolete historical queued rows;
- record worker notes separately for admission, enqueue, claim, provider latency, labels written.

`mention_semantics` iteration SLO after fix:

- admission/source-set rebuild is not part of provider-label iteration;
- provider-label iteration should not spend minutes before claiming due rows;
- p95 non-provider control time should be measured in seconds, not hundreds of seconds.

## Backlog Drain / Rebuild

Backlog cleanup is part of the fix, but it is not the fix.

After deploying the hard cut, run a formal operator command that performs this sequence inside a transaction or resumable job:

1. pause narrative workers or acquire their advisory locks;
2. rebuild current `narrative_admissions` from latest Radar coverage;
3. suppress or delete obsolete admissions outside the current frontier;
4. delete queued/retryable/stale `token_mention_semantics` rows whose `(event_id, target_type, target_id, schema_version)` is not referenced by current admissions;
5. reset retryable rows referenced by current admissions to immediate retry if retry backoff came from the old coupled loop;
6. mark current digests whose source fingerprint no longer matches admission as stale or replace with pending status;
7. resume workers and monitor pending backlog, timeout ratio, and top Radar digest statuses.

This command is allowed to modify rebuildable read models. It must not delete material facts (`events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, `enriched_events`).

## API And Frontend Contract

API surfaces remain read-only composition.

Token Radar row narrative payload must expose:

- `discussion_digest.status`;
- `data_gaps[].reason`;
- `source_event_count`;
- `labeled_event_count`;
- `semantic_coverage`;
- `computed_at_ms`;
- `source_fingerprint` or equivalent freshness marker.

Frontend copy must distinguish:

- source truly insufficient: "叙事样本不足";
- source sufficient but semantics pending: "叙事分析中";
- provider unavailable: "叙事分析暂不可用";
- stale digest: "叙事待刷新";

This is not a text-only patch: UI text must reflect backend state produced by correct source/digest logic.

## Acceptance Criteria

- Admission query is proven by test to only read rows from latest ready `token_radar_projection_coverage` batch.
- `NarrativeAdmissionWorker` is the only runtime writer of `narrative_admissions`.
- `MentionSemanticsWorker` no longer calls Radar admission query or source facts scan; it only consumes admission source sets and writes semantics.
- Digest context uses admission/source facts as source count and left joins semantics.
- With a source set of 10 events and zero semantic labels, `DiscussionDigestService.refresh_decision` returns `pending/semantic_labeling_pending`, not `insufficient/low_source_volume`.
- With 2 source events below threshold and 2 labels, it returns `insufficient/low_source_volume`.
- Top Radar rows no longer show broad `insufficient` when source set meets threshold but semantics are pending.
- Narrative health exposes current admission count, current source event count, queued/retryable/unavailable semantics, timeout/error counts, label throughput, digest status counts, and backlog waterline hits.
- Formal drain/rebuild command removes obsolete queued/retryable backlog without touching material facts.
- Architecture tests fail if API request handlers call provider, write narrative read models, or import write repositories directly.

## Verification Commands

Minimum local verification:

```bash
uv run ruff check src/gmgn_twitter_intel/domains/narrative_intel tests/unit/domains/narrative_intel tests/integration/test_narrative_repository.py
uv run pytest tests/unit/domains/narrative_intel -q
uv run pytest tests/integration/test_narrative_repository.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_src_domain_architecture.py -q
uv run pytest tests/unit/test_api_narrative_contract.py tests/integration/test_api_http.py -q
```

Live-data verification must start by confirming config paths:

```bash
uv run gmgn-twitter-intel config
```

Then inspect authenticated status endpoints without printing secrets:

- `/api/status/narrative-health?since_hours=4`
- `/api/status`
- `/api/token-radar?window=1h&scope=all`
- `/api/token-radar?window=4h&scope=all`
- `/api/token-radar?window=24h&scope=all`

Expected live outcome after drain and at least one worker cycle:

- `mention_semantics` worker notes no longer report thousands of `admission_source_mentions` per small provider batch;
- pending backlog decreases or is bounded by waterline;
- Radar top rows with sufficient source sets show `pending` while labeling catches up, then `ready`;
- `insufficient` is limited to actual low-source or low-author rows.

## Rollout

1. Implement schema/code hard cut on a branch.
2. Run local/unit/integration/architecture tests.
3. Deploy with narrative workers paused.
4. Run migration.
5. Run formal narrative rebuild/drain command.
6. Resume `NarrativeAdmissionWorker`.
7. Resume `MentionSemanticsWorker`.
8. Resume `TokenDiscussionDigestWorker`.
9. Monitor narrative health until backlog and top-row statuses stabilize.

Rollback is database backup + code rollback. Do not add runtime compatibility switches to keep old admission/digest behavior alive.
