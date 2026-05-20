# Spec — Token Narrative Epoch Product Semantics Hard Cut

**Status**: Draft, awaiting review
**Date**: 2026-05-20
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-20-token-radar-narrative-backlog-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-14-token-case-redesign-cn.md`
- `docs/superpowers/specs/active/2026-05-20-pulse-1h-4h-research-committee-cn.md`

## 一句话

把 Token Radar / Token Case 的叙事层从“每次最新 source fingerprint 都必须立即
LLM ready”硬切成“稳定 narrative epoch + last-ready snapshot + current delta”的产品语义：
Radar 负责发现，Token Case 负责可读案卷，Narrative Digest 负责已封口时间段的讨论总结，
Pulse 负责高价值研究判断。系统不再追逐每分钟移动目标，也不再用旧 digest 兼容 fallback；
旧 digest 若被展示，必须作为显式的 last-ready snapshot，并带有当前增量缺口。

## Background

当前系统已经把 Token Radar 叙事链路拆成三个 read-model writer：

```text
token_radar_rows
  -> NarrativeAdmissionWorker writes narrative_admissions
  -> MentionSemanticsWorker writes token_mention_semantics
  -> TokenDiscussionDigestWorker writes token_discussion_digests
  -> API / Token Radar / Token Case hydration
```

这次 hard cut 修复了几个真实问题：source set 不再由 semantic rows 反向定义，24h source
不再被 12h prune 删除，digest completeness 不再用 prompt sample 长度判断，health 能看到
`admitted source rows - semantics rows` 的 missing backlog。

但这只解决了“链路错误”。产品层仍有一个更深的错位：

- 用户希望在 Radar row 和 Token Case 二级页持续看到一个 token 的 24h 总结、主要叙事、
  多空观点和新增变化。
- 系统当前把 public current digest 绑定到最新 admission `source_fingerprint`。只要新 tweet
  进来，fingerprint 就变；旧 digest 立刻不再 current；新 digest 又必须等 semantics coverage、
  digest LLM、引用校验。
- 结果是活跃 token 越活跃，越容易长期显示 `pending` / `digest_stale` / `semantic_labeling_pending`。
  这不是用户理解里的“最新信息更多”，而是产品上看起来“叙事一直不可用”。

这个错位不能靠提高 LLM timeout 或更大 batch 解决。LLM 只是放大延迟；根因是系统把
“当前 source frontier”误当成“必须立即可发布的 narrative snapshot”。

## Problem

Token Radar 的发现节奏和 Narrative Digest 的研究节奏不是同一个节奏。

Radar 是 scanner。它可以每 5m/1h/4h/24h 投影排序，快速告诉用户“谁值得看”。这个投影是
高频、可重建、可替换的。

Narrative Digest 是 reader-facing summary。它回答“这段时间里大家到底在说什么、偏多还是偏空、
有哪些证据和反证”。这个输出需要 source set 稳定、semantic labels 完整、LLM 引用可校验。它不应该
因为每分钟新增一个 source event 就把上一版可读总结从产品上抹掉。

当前 public currentness 语义过于机械：

```text
latest admission source_fingerprint == digest.source_fingerprint
  -> show digest
else
  -> digest_stale / digest_not_ready
```

这个规则在数据审计上严格，但在产品体验上错误。正确产品语义应该是：

```text
last ready digest 是已封口 epoch 的可读结论；
current admission source set 是正在变化的事实 frontier；
二者差集是 current delta；
当 delta 未达到 material threshold 时，不重跑 digest；
当 delta 达到 threshold 时，显示 last ready + updating delta，异步生成下一版 digest。
```

## First Principles

1. **Radar answers “what surfaced now”.** Token Radar 是发现器，不是研究员。它必须保持
   快速、确定性、可重建。Radar rank 不等待 LLM digest，也不从 digest 文本反推 rank。

2. **Token Case answers “what do we know so far”.** Token Case 二级页是案卷。案卷可以展示
   last-ready narrative snapshot，同时诚实标注“有 N 条新增 source 正在分析”。案卷不能因为
   新增信息未完成 LLM 而退化成空白。

3. **Narrative Digest summarizes a sealed epoch.** Digest 不是无限滚动的实时字幕。它总结一个
   已封口的 source set。封口规则来自 deterministic epoch policy，不来自每分钟 projection tick。

4. **Current delta is first-class product state.** last-ready digest 与 current admission 的差集
   不是兼容 fallback，也不是隐藏 backlog；它是用户应该看到的产品状态：`updating`。

5. **LLM execution is capacity, not truth.** LLM 可以总结 sealed facts，但不能定义 source truth、
   不能补事实、不能决定一个 digest 是否 current。currentness 由 epoch policy、source set 和
   fingerprint/delta 计算。

6. **No runtime compatibility.** 不保留旧 exact-fingerprint-only hydration fallback，不保留旧 reason
   折叠，不保留旧 source-age prune，不保留旧字段 alias。旧行为一次 hard cut 到新产品语义。

7. **Do not chase every-minute targets.** 新 source event 不等于新 digest job。只有 material change、
   epoch TTL、窗口封口或用户显式查看触发的 priority 才能推进下一版 digest。

## Product Semantics

### Surfaces

| Surface | Primary Question | Narrative Behavior |
|---|---|---|
| Token Radar | “现在哪些 token 值得点开？” | 显示 compact why-now。可用 last-ready digest 标题，但必须带 currentness badge：`current` / `updating` / `stale` / `not_ready`。Radar 不等待 digest。 |
| Token Case | “这个 token 过去 24h/4h/1h 到底发生了什么？” | 展示 last-ready snapshot 作为案卷主叙事；右侧/顶部展示 current delta、semantic coverage、pending source count、last refreshed time。 |
| Token Posts / Timeline | “证据原文是什么？” | 直接展示当前 source/timeline facts 和 per-post semantics；未标注 post 显示 `semantic_not_ready`，不影响已 ready digest 可读性。 |
| Signal Pulse | “这是否是研究/交易候选？” | 使用 sealed evidence packet。可引用 ready digest 作为 context，但最终判断仍以 packet facts 和 refs 为准。stale/updating digest 不能作为唯一支持证据。 |
| Ops Health | “为什么叙事没刷新？” | 显示 current source rows、missing semantics、pending rows、last-ready epoch age、material-delta count、digest LLM defer/failure counts。 |

### Window Semantics

| Window | Product Role | LLM Digest Policy |
|---|---|---|
| `5m` | Detection / raw scanner. 适合发现突发，不适合总结叙事。 | 不生成 discussion digest。Radar 显示 social/market facts 和 `narrative_not_supported_for_window`。 |
| `1h` | Developing story. 适合早期确认。 | material delta 或 10-15 分钟 epoch cadence 后生成 digest。 |
| `4h` | Narrative formation. 适合判断扩散质量。 | material delta 或 30 分钟 epoch cadence 后生成 digest。 |
| `24h` | Token Case daily summary. 适合二级详情页主总结。 | material delta 或 2 小时 epoch cadence 后生成 digest。 |

5m 不再进入 Narrative Digest LLM lane。它仍保留 Token Radar scoring、market gates、social heat。
这是 hard cut，不提供“5m digest fallback”。

### Currentness States

Public `discussion_digest` 新增 `currentness` 对象，替代旧的“只有 exact fingerprint 才能显示”的隐式规则。

```json
{
  "status": "ready | pending | insufficient | semantic_unavailable | stale",
  "currentness": {
    "display_status": "current | updating | stale | not_ready | out_of_frontier | unsupported_window",
    "epoch_id": "string or null",
    "epoch_policy_version": "token-narrative-epoch-v1",
    "ready_source_fingerprint": "string or null",
    "current_source_fingerprint": "string or null",
    "ready_source_event_count": 42,
    "current_source_event_count": 51,
    "delta_source_event_count": 9,
    "delta_independent_author_count": 3,
    "delta_since_ms": 1770000000000,
    "last_ready_computed_at_ms": 1770000300000,
    "next_refresh_due_at_ms": 1770001200000,
    "reason": "fingerprint_match | digest_updating | material_delta_due | no_ready_digest | not_in_current_frontier | unsupported_window"
  }
}
```

State meanings:

| display_status | Meaning | User-Facing Copy |
|---|---|---|
| `current` | Ready digest source fingerprint matches current admission epoch. | “叙事已更新” |
| `updating` | Last-ready digest exists, current source set has new material or non-material delta. | “叙事更新中 · +N posts” |
| `stale` | Last-ready digest exists but epoch TTL expired or target left frontier; still useful only as historical context. | “上一版叙事 · 已过期” |
| `not_ready` | No ready digest exists for this target/window/scope. | Use pending/insufficient/data gap reason. |
| `out_of_frontier` | Target has no current admission for this surface. | “不在当前雷达前沿” |
| `unsupported_window` | Window intentionally has no digest, especially `5m`. | “5m 仅显示实时信号” |

## Goals

- **G1 — Hard-cut public narrative currentness.** Public hydration no longer hides all fingerprint
  mismatch as generic `digest_stale`. It returns a first-class `currentness` contract with
  current source counts, ready source counts, delta counts, and display status.

- **G2 — Keep last-ready snapshot readable.** Token Radar and Token Case may display last-ready
  digest when current source fingerprint changed, but only with `display_status=updating|stale`
  and explicit delta metadata. This is the new product contract, not compatibility fallback.

- **G3 — Stop minute-chasing.** Digest worker does not create a new LLM digest job for every
  admission source fingerprint. It only refreshes when `NarrativeEpochPolicy` says the delta is
  material or the cadence/TTL requires a new epoch.

- **G4 — Remove 5m digest lane.** `5m` remains a Radar scoring window but is not a Narrative Digest
  LLM window. Public 5m rows return `unsupported_window` currentness, not pending digest backlog.

- **G5 — Define material delta.** A delta becomes material when at least one configured threshold
  is met: new independent authors, new watched seed plus public corroboration, large source count
  change, stance/valence mix shift after semantics, market move threshold, or max staleness TTL.

- **G6 — Preserve CQRS ownership.** `TokenRadarProjectionWorker` still owns `token_radar_rows`.
  `NarrativeAdmissionWorker` owns source-set admission. `MentionSemanticsWorker` owns per-mention
  labels. `TokenDiscussionDigestWorker` owns digest rows and epoch metadata. API routes do not write.

- **G7 — Token Case becomes the canonical narrative surface.** Token Case defaults to `24h/all`
  narrative summary when available, with 4h/1h as selectable detail. The page must remain useful
  when digest is updating.

- **G8 — Pulse treats updating digest as context only.** Pulse evidence packets may include
  last-ready digest metadata, but non-abstain decisions must cite packet facts/current source refs,
  not rely solely on stale digest prose.

- **G9 — Ops health explains freshness.** `/api/status/narrative-health` reports epoch freshness,
  last-ready ages, material delta backlog, unsupported 5m count, and digest jobs deferred by
  epoch policy separately from LLM capacity failures.

- **G10 — No old compatibility branches.** No old reason aliases, no hidden exact-fingerprint
  fallback path, no request-time provider calls, no “if old field missing then synthesize narrative”.

## Non-Goals

- 不修改 Token Radar ranking、factor snapshot scoring、identity resolver、market tick persistence。
- 不让 API request path 跑 LLM、写 admission、写 semantics、写 digest。
- 不承诺所有 token 都有 ready digest。无 source、低独立作者、低语义覆盖仍显示真实 insufficient/pending。
- 不新增外部数据源，不训练模型，不做人工标注。
- 不把 Pulse 改成每个 token 都跑的研究员。Pulse 仍只服务高价值 1h/4h candidates。
- 不保留旧 public digest shape 作为 fallback。前端和 API contract 必须同 PR hard cut。
- 不追逐每分钟 source fingerprint；新增一条 tweet 默认只进入 delta，不默认触发 digest LLM。

## Target Architecture

```text
Token Radar projection
  -> current source frontier
  -> NarrativeAdmissionWorker
       writes narrative_admissions(source_event_ids_json, current_source_fingerprint)
  -> MentionSemanticsWorker
       labels current/admitted source rows
  -> NarrativeEpochPolicy
       decides no-op | deterministic status | refresh_digest
  -> TokenDiscussionDigestWorker
       writes token_discussion_digests with epoch metadata and source_event_ids_json
  -> NarrativeReadModel
       composes last-ready snapshot + current admission delta + currentness
  -> Token Radar / Token Case / Search / Pulse context
```

### Model Changes

`token_discussion_digests` gains epoch metadata:

- `epoch_id`
- `epoch_policy_version`
- `source_event_ids_json`
- `source_window_start_ms`
- `source_window_end_ms`
- `epoch_closed_at_ms`
- `display_current_until_ms`
- `refresh_reason`

`narrative_admissions` remains the current source-set projection and keeps:

- `source_event_ids_json`
- `source_fingerprint`
- `source_event_count`
- `independent_author_count`
- `source_window_start_ms`
- `source_window_end_ms`
- `next_semantics_due_at_ms`
- `next_digest_due_at_ms`

No separate central `agent_tasks` or generic narrative job table is introduced.

### NarrativeEpochPolicy

Create a deterministic service in `domains/narrative_intel/services/`:

```text
NarrativeEpochPolicy.evaluate(admission, last_ready_digest, semantic_coverage, market_context)
  -> unsupported_window
  -> no_ready_digest
  -> no_material_delta
  -> material_delta_due
  -> ttl_refresh_due
  -> semantic_pending
  -> insufficient
```

Default hard-cut policy:

| Window | Min New Sources | Min New Authors | Max Epoch Age | Notes |
|---|---:|---:|---:|---|
| `5m` | n/a | n/a | n/a | unsupported for digest |
| `1h` | 3 | 2 | 15m | early story |
| `4h` | 5 | 2 | 30m | formation |
| `24h` | 8 | 3 | 2h | daily case summary |

Additional material triggers:

- watched source appears and at least one public non-watched author corroborates;
- semantic stance mix shifts by >= 20 percentage points after labeling;
- attention valence mix shifts by >= 20 percentage points;
- price moves >= 12% since last ready digest epoch;
- previous digest status was `semantic_unavailable` and now coverage is sufficient;
- current token case page is actively selected and no ready digest exists, subject to per-cycle
  on-demand budget. This is a priority hint only; it does not write from API.

### Digest Worker Behavior

`TokenDiscussionDigestWorker` no longer treats every due admission as “try to refresh digest”.

For each due target:

1. Build current admission context and semantic coverage aggregate.
2. Load last ready digest for the same target/window/scope, regardless of source fingerprint.
3. Run `NarrativeEpochPolicy`.
4. If `unsupported_window`, do not write `token_discussion_digests`; the read model returns a
   deterministic unsupported sentinel and the worker does not call LLM.
5. If `no_material_delta`, mark digest scanned and keep last-ready display.
6. If source/semantic thresholds fail and no ready digest exists, write status digest.
7. If source/semantic thresholds fail but ready digest exists, keep ready digest as `updating`
   and expose current gap metadata; do not replace it with a worse status row.
8. If `material_delta_due` or `ttl_refresh_due`, seal a new epoch from current source set and
   call digest LLM under existing LLM caps.
9. Persist digest with epoch metadata and `source_event_ids_json`.

### Public Read Model

`NarrativeReadModel.current_digests_for_targets` becomes `current_narrative_snapshots_for_targets`.

It returns one public snapshot per target:

- exact matching ready digest -> `display_status=current`;
- last ready digest plus current admission delta -> `display_status=updating`;
- last ready digest but target no longer admitted -> `display_status=stale|out_of_frontier`;
- no ready digest but current admission exists -> status digest / sentinel with `display_status=not_ready`;
- unsupported window -> `display_status=unsupported_window`.

This hard-cuts the old rule that public rows must only return fingerprint-matched digests. The new
rule is more explicit and stricter from a product perspective because every mismatch is labeled and
quantified.

## Interface Contracts

### `/api/token-radar`

Rows continue to expose `discussion_digest`, but `discussion_digest.currentness` is required.

For `window=5m`, `discussion_digest` is present with:

```json
{
  "status": "pending",
  "data_gaps": [{"reason": "narrative_not_supported_for_window"}],
  "currentness": {
    "display_status": "unsupported_window",
    "reason": "unsupported_window"
  }
}
```

For `1h/4h/24h`, rows may show last-ready digest with:

```json
{
  "status": "ready",
  "headline_zh": "...",
  "dominant_narrative": {...},
  "bull_bear": {...},
  "currentness": {
    "display_status": "updating",
    "reason": "digest_updating",
    "delta_source_event_count": 6,
    "delta_independent_author_count": 2
  },
  "data_gaps": [{"reason": "digest_updating", "delta_source_event_count": 6}]
}
```

### `/api/token-case`

Token Case must treat narrative as a case snapshot, not a binary current/missing value.

Required sections:

- `discussion_digest`: last-ready or current status with `currentness`;
- `narrative_delta`: compact object derived from currentness for top-level UI;
- `posts.items[].semantic`: per-post current semantics or `semantic_not_ready`;
- `timeline.summary`: current facts, independent of digest freshness.

Default Token Case narrative window is `24h/all` when route does not specify otherwise.

### `/api/status/narrative-health`

Add:

- `epoch_policy_version`
- `unsupported_window_admissions`
- `last_ready_digest_count`
- `updating_snapshot_count`
- `material_delta_due_count`
- `no_material_delta_deferred_count`
- `last_ready_p50_age_ms`
- `last_ready_p95_age_ms`
- `delta_source_rows`
- `delta_independent_authors`
- `digest_refresh_due_by_window`
- `digest_refresh_deferred_by_epoch_policy`

Existing missing semantics fields remain. `missing_semantic_rows` is still source-set truth; epoch
policy does not hide real backlog.

### Frontend

Frontend must not synthesize narrative from factor snapshots or raw post text.

Required display changes:

- Token Radar compact narrative cell:
  - `current`: normal title/detail;
  - `updating`: show last-ready title + “更新中 +N” badge;
  - `stale`: show last-ready title + “上一版” badge;
  - `not_ready`: use data gap label;
  - `unsupported_window`: “5m 实时信号”.

- Token Case hero / summary:
  - show last-ready computed time;
  - show current delta count;
  - show semantic coverage;
  - never blank the narrative section when last-ready exists.

No old frontend reason labels are kept as compatibility aliases. Update `narrativeDataGaps.ts`
to the new reason set.

## Acceptance Criteria

- **AC1.** WHEN a target has a ready 24h digest and then receives one new source event THEN
  public Token Case SHALL continue showing the ready digest with
  `currentness.display_status="updating"` and `delta_source_event_count=1`; it SHALL NOT return
  generic `digest_stale` or blank narrative.

- **AC2.** WHEN the same target receives source delta below material thresholds THEN
  `TokenDiscussionDigestWorker` SHALL not call the digest LLM solely because the source fingerprint
  changed; health SHALL count it under `no_material_delta_deferred_count`.

- **AC3.** WHEN source delta meets the material threshold for its window THEN the digest worker SHALL
  seal a new epoch, persist `epoch_id` and `source_event_ids_json`, and call the digest LLM subject
  to `max_llm_calls_per_cycle`.

- **AC4.** WHEN `window=5m` is requested from `/api/token-radar` THEN rows SHALL expose
  `currentness.display_status="unsupported_window"` and no digest LLM work SHALL be enqueued for
  5m.

- **AC5.** WHEN a target has no ready digest but has current admitted source rows THEN public
  hydration SHALL return `display_status="not_ready"` with specific reason
  `semantic_labeling_pending`, `low_source_volume`, `low_independent_author_count`,
  `low_semantic_coverage`, or `no_ready_digest`.

- **AC6.** WHEN a target leaves the Radar frontier THEN Token Radar SHALL show
  `out_of_frontier` if it somehow appears in that surface; Token Case MAY show the last-ready
  digest as stale historical context with `display_status="stale"`, not as current.

- **AC7.** WHEN Pulse builds an evidence packet and only an updating digest is available THEN the
  packet MAY include it as context, but non-abstain decisions SHALL cite current packet refs and
  not rely solely on the digest text.

- **AC8.** WHEN public API schemas are regenerated THEN `discussion_digest.currentness` SHALL be
  required in generated frontend types; no frontend code SHALL branch on removed old reason aliases.

- **AC9.** WHEN narrative health is queried THEN operators SHALL be able to distinguish:
  missing semantics, LLM capacity defer, epoch-policy defer, unsupported 5m, no ready digest, and
  stale/out-of-frontier snapshots.

- **AC10.** WHEN tests scan runtime code THEN there SHALL be no request-path provider calls, no API
  writes to narrative tables, no old source-age prune, no exact-fingerprint-only public hydration
  path, and no old digest fallback helper.

## Test Plan

### Unit

- `NarrativeEpochPolicy`:
  - unsupported 5m;
  - no ready digest -> due when thresholds met;
  - one new event below threshold -> no material delta;
  - new authors above threshold -> material delta;
  - TTL expiry -> refresh due;
  - market move threshold -> refresh due.

- `DiscussionDigestService`:
  - ready digest writes epoch metadata and source ids;
  - status digest preserves `currentness`;
  - prompt cap does not affect epoch completeness.

- `NarrativeReadModel`:
  - exact fingerprint -> current;
  - mismatched but last ready exists -> updating;
  - suppressed admission -> out_of_frontier/stale;
  - no ready -> not_ready;
  - 5m -> unsupported_window.

### Integration

- Seed current admission + ready digest + new source event; assert public hydration returns
  last-ready digest with delta metadata.
- Seed below-threshold delta; run digest worker; assert no LLM call and next due uses epoch policy.
- Seed material delta; run digest worker with fake provider; assert new epoch digest is written.
- Seed 5m admissions; run digest worker; assert no 5m LLM calls or ready digest writes.

### Contract / Frontend

- Regenerate OpenAPI and frontend types.
- Update Token Radar compact case tests for `current/updating/stale/not_ready/unsupported_window`.
- Update Token Case view model tests for last-ready + current delta display.
- Update data-gap label tests for new reason set.

### Architecture

- Enforce single-writer ownership for new digest epoch metadata.
- Enforce API routes do not import providers or write repositories.
- Enforce no old exact-fingerprint-only hydration helper remains.
- Enforce no 5m digest worker enqueue path.

## Rollout

1. Merge schema and code hard cut in one branch.
2. Regenerate contracts and update frontend in the same branch.
3. Run narrative rebuild/drain to populate source-set truth under current code.
4. Backfill epoch metadata for existing ready digests by treating each current ready digest as
   `epoch_policy_version="legacy-import-for-hard-cut"` only inside migration output, then immediately
   rewrite with current policy on first refresh. Runtime code must not branch on that string.
5. Verify `/api/status/narrative-health` has epoch fields and no hidden missing backlog.
6. Verify Token Radar 5m rows show unsupported narrative, while 1h/4h/24h rows show currentness.
7. Verify Token Case 24h remains readable for active tokens with new delta.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Showing last-ready digest may be mistaken as fully current. | High | Mandatory `currentness.display_status`, delta badge, and data gap. UI must make updating/stale visible. |
| Epoch thresholds too high hide meaningful changes. | Medium | Start conservative per window, expose deferred counts, tune in workers.yaml after live observation. |
| Epoch thresholds too low reintroduce minute-chasing. | High | Hard cap LLM calls and add tests proving below-threshold fingerprint changes do not call LLM. |
| 5m users expect narrative text. | Medium | Product copy: 5m is scanner only; 1h/4h/24h are narrative windows. |
| Pulse consumes stale prose incorrectly. | High | Evidence packet marks digest context currentness; verifier requires current refs for non-abstain decisions. |
| Backfill/migration makes old digest look current. | High | Runtime currentness always compares current admission and digest source ids; migration labels do not bypass policy. |

## Alternatives Considered

- **Keep exact fingerprint matching only** — rejected because active tokens become permanently pending
  from the user perspective.
- **Increase LLM concurrency / timeout** — rejected because it treats capacity symptoms, not the
  product semantics problem.
- **Generate digest for every new source event** — rejected because it chases a moving target and
  guarantees backlog under live social flow.
- **Hide digest until exact current ready exists** — rejected because Token Case becomes blank during
  the moments users most want to inspect it.
- **Put last-ready digest in a separate historical tab only** — rejected because the primary case
  needs a readable summary, but the summary must be visibly labeled as updating/stale.
- **Add a generic central agent queue** — rejected because domain source sets and read models remain
  the product truth; agent execution is operational capacity.

## Boundaries

| Class | Behaviour |
|---|---|
| Always | Show currentness; preserve last-ready snapshot as explicit product state; compute delta from source sets; gate LLM by epoch policy; keep Radar scoring independent. |
| Ask first | Changing material thresholds after live evaluation; adding user-demand priority beyond read-only route hints; showing stale digest inside Pulse public cards. |
| Never | Reintroduce old runtime compatibility; treat last-ready digest as current without badge; call providers from API; generate 5m digest; enqueue digest LLM for every fingerprint change; synthesize narrative text on frontend. |
