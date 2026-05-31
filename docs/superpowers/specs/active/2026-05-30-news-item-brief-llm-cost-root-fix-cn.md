# Spec - News Item Brief LLM Cost Root Fix

**Status**: Draft, engineering review applied; hard-cut implementation required
**Date**: 2026-05-30
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`
- `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-29-litellm-native-agent-news-alert-hard-cut-cn.md`

## Decision

`news_item_brief` 的 LLM currentness 必须基于可解释的业务材料变化，而不是 provider refetch / worker runtime metadata。

目标状态：

- unchanged canonical news item 只生成一次 agent brief；
- `input_hash` 只覆盖 prompt 真正需要的材料字段；
- brief freshness watermark 只由 item material content、token mentions、fact candidates、context items 等 LLM 输入材料推进；
- provider fetch timestamp、generic `news_items.updated_at_ms`、lease/update/retry metadata 不能让 ready brief 失效；
- provider quota/balance outage 被识别为 lane/provider backpressure，不能形成每 10s/provider-started failed run 风暴；
- dirty targets 只做 wake hints，不做永久 failed queue；失败必须 bounded retry 后 terminalize/evict；
- 不保留运行时兼容分支：新 semantic identity 一次 hard cut 成为唯一真相；
- 保留真实内容更新、token/fact/context 变化时重新 brief 的能力；story projection 已 hard cut，不再作为 page 或 brief 的运行输入。

## Background

本 spec 基于 operator-owned live runtime config 和 live PostgreSQL 只读诊断，不使用仓库 fixtures 作为真实运行依据。`uv run parallax config` 已确认 `config_path=/Users/qinghuan/.parallax/config.yaml`，`workers_config_path=/Users/qinghuan/.parallax/workers.yaml`；诊断只报告路径、布尔和非 secret 字段。

当前 live worker config 中，`news_item_brief` 是主要还在运行的 LLM 消耗点：enabled、interval 10s、batch size 1、lane `news.item_brief`。`narrative_admission`、`mention_semantics`、`token_discussion_digest`、`pulse_candidate` 当前 disabled，因此本轮成本根因优先收敛在 News item brief 链路。

News fetch 写 canonical `news_items` 时，`ON CONFLICT` 分支会在 `replace_representative` 时替换 representative payload 的 `fetched_at_ms`，且无条件把 `updated_at_ms` 写成 `EXCLUDED.updated_at_ms`（`src/parallax/domains/news_intel/repositories/news_repository.py:940`, `src/parallax/domains/news_intel/repositories/news_repository.py:993`, `src/parallax/domains/news_intel/repositories/news_repository.py:1025`）。这意味着同一个 provider item 被重复抓取，即使 title/summary/body/content_hash 未变，也可能推动 `fetched_at_ms` 和 `updated_at_ms`。

News fetch 对 written items 只 enqueue `page`；context written 会 enqueue `page` 和 `brief_input`。News item process 在 item 被处理后会写 entities、token mentions、fact candidates、content classification、processed marker，并在 `_dirty_targets_for_processed_item` 中按 `needs_agent_brief` enqueue `brief_input`。

OpenNews / 6551 ingest 只把 `/open/news_search` 结果映射为 provider article、source key、URL/title/text、`aiRating` summary、provider signal/token impacts、timestamp 和 raw payload；不会返回生产级业务 story。当前实现 hard-cut 本地 story projection，不保留 runtime worker、wake、API route、page/story schema 或 dirty target 队列。

News story projection 曾为 affected item enqueue downstream `page` 和 `brief_input`，并把 `source_watermark_ms` 设置为 projection runtime `now`。这条链路本身不直接调用 LLM，但会让 `brief_input` target 重新进入 dirty queue，是 story 变化放大 brief LLM 消耗的根因之一；本轮按 hard cut 删除。

Dirty target repository 的 enqueue conflict 会更新 payload hash/source watermark、选择更早 due time，并清空 `last_error`（`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:90`, `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:103`, `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:108`, `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:145`）。`mark_error` 又要求 queued row 的 payload hash、lease owner、attempt count 都和 claimed key 一致才会更新 retry state（`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:264`, `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:306`, `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:318`）。当 upstream 重复 enqueue 且 payload/watermark 变化时，attempt/error accounting 容易被刷新或绕开。

`load_items_for_brief_targets` 曾把 `source_updated_at_ms` 定义为 `GREATEST(items.updated_at_ms, stories.updated_at_ms, mention_updates, fact_updates, context_updates, story_member_updates)`（`src/parallax/domains/news_intel/repositories/news_repository.py:2212`, `src/parallax/domains/news_intel/repositories/news_repository.py:2228`）。其中 `items.updated_at_ms` 已被 fetch upsert 刷新，story timestamps 又是 projection/read-model churn，二者都不能代表 LLM 输入材料变化。

`NewsItemBriefNewsItem` schema 包含 `fetched_at_ms`（`src/parallax/domains/news_intel/types/news_item_brief.py:99`, `src/parallax/domains/news_intel/types/news_item_brief.py:108`）。`build_news_item_brief_input_packet` 把 `item.fetched_at_ms` 放进 packet，并对整个 packet 的 JSON dump 计算 `input_hash`（`src/parallax/domains/news_intel/services/news_item_brief_input.py:44`, `src/parallax/domains/news_intel/services/news_item_brief_input.py:51`, `src/parallax/domains/news_intel/services/news_item_brief_input.py:99`）。

Agent stage 也直接把 `packet.model_dump(mode="json", exclude={"input_hash"})` 作为 provider input payload（`src/parallax/domains/news_intel/services/news_item_brief_runtime.py:21`, `src/parallax/domains/news_intel/services/news_item_brief_runtime.py:27`）。因此仅稳定 `packet.input_hash` 不够；provider/audit stage payload 也必须使用同一份 semantic material payload，否则 stage/gateway audit hash 仍可能携带 volatile `fetched_at_ms`。

`NewsItemBriefWorker.run_once` 会 claim `brief_input` target、load candidates、build packet，然后调用 `_current_brief_is_fresh`；只有 current brief status 非 failed、input hash 相等、artifact version 相等、`computed_at_ms >= source_updated_at_ms` 才跳过 LLM（`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:122`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:131`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:612`）。因此 `fetched_at_ms` 改变会让 input hash 不相等，`items.updated_at_ms` 改变会让 source freshness 失败，两者任一都能触发重复 LLM。

Provider failure 路径会记录 failed run 并 upsert failed current brief；如果 error 被认为 execution started，则 dirty target 按 retry interval 和 attempt limit 处理（`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:276`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:294`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:319`）。LiteLLM/provider error classifier 目前只识别 rate limit、timeout/transport/connection，其余一律 `PROVIDER_ERROR`（`src/parallax/integrations/model_execution/execution_gateway.py:735`）。`Insufficient Balance` 因此会进入 generic provider failure，而不是明确的 quota/backpressure。

## Live Evidence Snapshot

截至 2026-05-30 晚间 Asia/Shanghai 的只读诊断显示：

- `news_item_agent_runs` 最近 24h 约 2,815 次 provider-started run，其中 2,117 次有 usage，合计约 12.5M tokens。
- 当天 00:00 以来 News brief 约 2,133 次 run，约 9.67M tokens；Pulse/legacy 消耗主要发生在早上 disabled 前，不是当前快速消耗的主因。
- 正常成功窗口 `2026-05-30 10:00-18:17 Asia/Shanghai`：275 条 news item，53 条 agent-eligible item，实际 1,500 次 run、1,418 次 usage run、约 9.02M tokens、46 个 distinct news item、1,068 个 distinct input hash。
- 该窗口约 33 条 news/hour，agent-eligible density 约 6.4 条/hour。按当前平均每次 brief 约 6,360 tokens，理想 one-brief-per-eligible-item 是约 40.7k tokens/hour、约 0.98M tokens/day。
- 当前正常窗口观察到约 1.09M tokens/hour，折算约 26M tokens/day，是理想 currentness 的约 26-27 倍。
- sub-agent DB 复核显示，正常窗口 top 14 个 `>=10` calls 的 item 占 97.0% calls、98.0% tokens，说明成本集中在少数 repeated rebrief，不是全量新闻密度。
- top repeated item `news-item-3a6725b9e00ea2610d9239bcd312e65f` 约 396 次 run、396 个 input hash、1 个 packet id、约 2.93M tokens；抽样显示 content_hash/title/summary/body/provider signal 稳定，`fetched_at_ms` 每次变化；story 是本地 page context，不应进入 brief input identity。
- 另一个 top item `news-item-a6f2...` 约 212 次 run 但只有 1 个 input hash/packet id，说明即使 hash 没变，`items.updated_at_ms -> source_updated_at_ms` 也能单独让 freshness 失败。
- 余额耗尽后最近失败 error bucket 主要是 `litellm.BadRequestError: OpenAIException - Insufficient Balance`；同一 item 在 1h 内出现 10+ 次 failed run。
- 当前 dirty backlog 复核为 1,609 个 due `brief_input` target、0 leased；若直接按 6,360 tokens/run drain，backlog alone 可再消耗约 10M tokens。

这些数字需要由本轮 sub-agent 最终复核并更新到 verification artifact，但已足够确认问题不是新闻密度本身，而是 currentness identity 被 volatile metadata 放大。

## Problem

`news_item_brief` 把抓取时间和 generic row update time 当成 LLM 输入身份与 freshness 的一部分，导致同一篇内容不变的 canonical news item 在每次 provider refetch / story projection / dirty target refresh 后反复进入 LLM。正常新闻密度下，系统应接近 one brief per eligible article；实际却按 refetch/projection churn 放大到 20x 以上。余额耗尽后，provider quota error 又被当作普通 provider failure 继续快速尝试，进一步制造 audit noise 和 queue churn。

## First Principles

1. **Fact truth remains PostgreSQL material facts.** Provider raw frames 和 fetch metadata 是输入观测，不是 agent brief 的业务事实；News Kappa/CQRS 的 read model/agent result 必须从 canonical material facts 重建。

2. **Agent input identity must be semantic.** `input_hash` 只应覆盖 prompt 和 validator 会使用的业务材料：content hash/title/summary/body excerpt/canonical URL/published time/source identity/provider signal/token impacts/token mentions/fact candidates/context item bodies/agent config。Fetch time、story projection state、lease time、worker run time、dirty target retry fields 不属于语义身份。

3. **Freshness watermark must be material.** Current brief 是否 stale 应由 material content/facts/context 的 last-material-change 推进，而不是 by-row `updated_at_ms`、story projection membership 或 projection runtime `now`。

4. **Provider capacity failures are control-plane state.** `Insufficient Balance`、quota、auth/config 类错误不代表单个 news item 的内容不可 brief，也不应快速消耗 attempt/run ledger；它们应打开 lane/provider cooldown，并尽量在 provider call 前变成 no-start backpressure。

## Goals

- **G1 - Stop unchanged rebriefs.** 当同一 canonical item 的 content hash、provider signal、token/fact/context material inputs 未变时，连续 refetch/projection/dirty enqueue 不得产生新的 provider-started `news_item_agent_runs`。
- **G2 - Stabilize input hash.** 仅 `fetched_at_ms`、`news_items.updated_at_ms`、dirty target due/lease/error/attempt 变化时，`NewsItemBriefInputPacket.input_hash` 必须保持不变。
- **G3 - Material freshness only.** `source_updated_at_ms` 不得直接使用 fetch-updated `news_items.updated_at_ms`；真实 material change 仍必须让 current brief stale。
- **G4 - Cost envelope.** 在当前新闻密度约 6-7 条 eligible news/hour 下，steady-state News brief 消耗目标是接近 40k-80k tokens/hour；如果没有 backlog/replay，不得继续维持 1M tokens/hour 量级。
- **G5 - Quota outage cooldown.** `Insufficient Balance`/quota/auth 类 provider error 必须进入明确 error class 或 backpressure class，并触发长 cooldown/circuit，避免同一 item 在 1h 内重复 provider-started 失败。
- **G6 - No permanent failed dirty queue.** `brief_input` dirty target 必须在本次 material hash 被处理、判定 fresh、或 bounded failure terminalize 后离开 hot queue；相同 material hash 不得因为 failed/current/error row 常驻而反复 due。
- **G7 - Hard cut only.** 运行时代码不得包含 legacy hash compatibility branch。历史 current brief 若需要保留，必须通过一次性 backfill/recompute 在部署期改成新 semantic hash。
- **G8 - Observable regression guard.** 测试和 ops 诊断必须能证明 unchanged article 不再 rebrief，并能给出 token/hour、runs/item、input_hash/item、quota error retry rate、terminalized/evicted target count。

## Non-goals

- 不改变 News high-signal alert 产品语义，不用 provider summary 替代 agent brief。
- 不降低 `news_item_brief` prompt、schema、validator、no-execution-language guardrail。
- 不把 News dirty target lifecycle 移入 central agent queue。
- 不自动修改 operator-owned `~/.parallax/config.yaml` 或 `workers.yaml`。
- 不清理所有历史 run 或重写 historical usage ledger；历史 rows 仅用于诊断和回归对比。
- 不在 runtime freshness gate 中保留 legacy hash fallback、旧 packet fallback、双写 hash、shadow hash 兼容路径。

## Target Architecture

目标链路：

```text
news_fetch
  -> news_items / observation_edges
  -> news_item_process material facts
  -> news_item_process/context writes enqueue brief_input dirty target
  -> load brief candidate with material_source_updated_at_ms
  -> build semantic input packet and stable input_hash
  -> current brief freshness gate
      -> unchanged: mark dirty target done, no provider call
      -> changed: call LiteLLM lane once
  -> news_item_agent_runs / current brief
  -> news_page_projection / notifications
```

`news_fetch` 仍可更新 fetch metadata 和 observation edges。`news_item_process` 仍负责 material facts。`news_story_projection` 不再是运行链路；关键变化是 `news_item_brief` 的 staleness/readiness 不再把 fetch/runtime/projection metadata 当作 semantic input。

## Conceptual Data Flow

```text
provider observation
  -> canonical item upsert
     -> material content status
     -> observation metadata
  -> deterministic process facts
  -> page projection + context material
  -> dirty target wake hint
  -> semantic packet hash + material watermark
  -> LLM only if semantic packet changed or material watermark advanced
```

`NOTIFY` 和 dirty target 仍只是 wake hint；每个 worker 仍 re-read DB。区别在于 `news_item_brief` 在读取 DB 后会用 semantic identity 去 collapse wake churn。

## Core Models

### Semantic Brief Input

`SemanticBriefInput` 是 `NewsItemBriefInputPacket` 中会影响 model output 的字段集合。它包括：

- article identity: `news_item_id`, canonical URL, title, summary, body excerpt, published time, content hash;
- source identity and trust metadata;
- provider signal and provider token impacts, with stable ordering and bounded aggregation;
- token mentions and fact candidates, stable sorted;
- context items: ids, type, author, canonical URL, bounded body excerpt, published time, engagement if prompt uses it;
- agent config: prompt/schema/validator/guardrail/artifact hash.

It excludes:

- `fetched_at_ms`;
- generic `news_items.updated_at_ms`;
- dirty target `updated_at_ms`, `due_at_ms`, lease owner, attempt count, last error;
- run id, started/finished timestamps, provider latency, trace metadata.

### Material Freshness Watermark

`material_source_updated_at_ms` is the latest timestamp among material facts that can change the packet or model output. It may use:

- item processed/content-material timestamp, not fetch-updated row timestamp;
- max token mention created/updated timestamp;
- max fact candidate updated timestamp;
- max context item created/updated timestamp;
- no story membership/group timestamp; story projection is no longer an active read model or brief packet input.

If no separate material timestamp exists, the implementation should derive freshness from existing stable material rows first. A DB migration is optional, not assumed by this spec.

### Provider Quota Backpressure

Provider quota/balance/auth/config failures are lane/provider capacity state. They should be represented distinctly from model output failure and from item-level validation failure. The worker may record an ops audit event, but should avoid marking a specific current brief as permanently failed for content reasons.

## Interface Contracts

No public HTTP, WebSocket, or frontend contract changes are required for the root fix.

Ops/CLI diagnostics may add read-only fields or reports:

- News LLM tokens by worker/model/status/window;
- runs per distinct news item;
- input hashes per news item;
- quota/balance/provider error buckets;
- due dirty target count and oldest due age;
- predicted steady-state tokens/hour from current eligible news density.

Any new ops output must redact secrets and follow existing config diagnostics rules.

## Acceptance Criteria

- **AC1.** WHEN a processed news item is refetched with only `fetched_at_ms` and `news_items.updated_at_ms` changed THEN `build_news_item_brief_input_packet(...).input_hash` SHALL remain unchanged.
- **AC2.** WHEN a ready current brief has matching semantic input hash and no material facts changed THEN `NewsItemBriefWorker` SHALL mark the `brief_input` dirty target done without calling the provider.
- **AC3.** WHEN title/summary/body/content_hash/provider signal/token mentions/fact candidates/context items materially change THEN the current brief SHALL become stale and the worker MAY call the provider once for the new semantic packet. Story membership SHALL NOT exist in the active runtime contract.
- **AC4.** WHEN provider returns `Insufficient Balance` or equivalent quota/balance/auth error THEN the execution plane SHALL classify it as quota/capacity/backpressure, open or extend lane cooldown, and prevent rapid repeated provider-started failures for the same target.
- **AC5.** WHEN there are no material changes and the eligible news density is about 6-7/hour THEN steady-state News item brief usage SHALL trend near one model call per eligible item, not one call per fetch/projection enqueue.
- **AC6.** WHEN regression tests mutate only volatile metadata THEN no new `news_item_agent_runs` row with `execution_started=true` SHALL be inserted.
- **AC7.** WHEN regression tests mutate a material fact THEN exactly one new run SHALL be inserted and the current brief SHALL store the new input hash.
- **AC8.** WHEN provider/model/domain validation fails after bounded attempts THEN the dirty target SHALL be removed from due queue and a terminal event/current terminal state SHALL explain the failure.
- **AC9.** WHEN provider quota/balance outage is active THEN the worker SHALL not claim every dirty target; provider health/circuit SHALL block before queue claim whenever possible.
- **AC10.** WHEN implementation is reviewed THEN no runtime branch SHALL recompute legacy hashes from historical packets to decide freshness.

## Proposed Root Fix

### P0 - Stable input identity

Remove `fetched_at_ms` from the semantic packet hash and from the provider-visible stage input. Prefer deleting it from `NewsItemBriefNewsItem`; if an audit/debug timestamp is needed, it must live outside the model-visible semantic packet and outside every hash.

Preferred implementation direction:

- add one helper such as `news_item_brief_material_input_payload(...)` / `news_item_brief_material_input_hash(...)`;
- use that helper for `packet.input_hash`, `AgentStageSpec.input_payload`, and any gateway/audit stage hash;
- exclude volatile paths at the helper boundary, at minimum `news_item.fetched_at_ms`, generic row timestamps, run ids, generated timestamps, UUIDs, attempt/lease metadata;
- add a unit test proving two packets with identical content and different `fetched_at_ms` have identical `input_hash`.

### P0 - Material freshness watermark

Change `load_items_for_brief_targets` so `source_updated_at_ms` does not use `items.updated_at_ms` or projection-only `stories.updated_at_ms` directly. Use semantic input hash equality as the primary freshness gate; keep source watermark as auxiliary ordering/diagnostic state based on material rows.

Preferred implementation direction:

- replace `items.updated_at_ms` with a content/process material timestamp;
- remove story group/member joins from the brief candidate loader; story group updates are not consumed by active runtime projections;
- change `_current_brief_is_fresh` to require `current.input_hash == packet.input_hash` plus exact artifact/prompt/schema/validator version match; do not let volatile `source_updated_at_ms` override a matching semantic hash;
- no runtime compatibility fallback for historical hashes. If historical ready briefs must be preserved, run a one-time deployment backfill that rewrites `news_item_agent_briefs.input_hash` to the new semantic hash and then delete that backfill path;
- ensure context/fact/token changes still advance freshness.

### P0 - Provider quota/backpressure classification

Extend provider error classification to recognize balance/quota/auth/config strings and exception shapes. Treat them as capacity/backpressure for retry policy and lane circuit. The worker should avoid item-level failed current brief churn when the provider cannot serve any item.

Preferred implementation direction:

- add explicit error class such as `QUOTA_EXHAUSTED` or map to no-start backpressure if supported by existing `AgentExecutionErrorClass`;
- increase cooldown for quota/balance errors beyond the normal 60s backpressure cooldown;
- treat quota exhausted as no-start/backpressure in `NewsItemBriefWorker`, so it does not write a failed current brief, notify downstream, or create repeated item-level provider-started failed rows;
- preserve an ops-visible error bucket without burning per-item execution attempt repeatedly.

### P0 - Hard-cut deployment, no runtime compatibility

Do not keep runtime compatibility for old hashes. Current tables already have enough audit and current-state fields to do a hard cut:

- `news_item_agent_briefs.input_hash` stores the current semantic identity;
- `news_item_agent_runs.request_json` can support a one-time operator/deployment backfill if preserving historical ready briefs matters;
- `news_projection_dirty_targets` already carries payload/source watermark/retry state;
- `news_item_agent_runs.error_class` is free text, so `quota_exhausted` does not require DDL if the platform enum adds it in code.

Deployment choices:

- Preferred hard cut: run a one-time backfill that recomputes current ready brief `input_hash` with the new semantic helper, then ship code with no legacy branch.
- Acceptable hard cut: do not backfill; allow existing current briefs to be treated stale once, but keep provider disabled or low-RPM until the duplicate queue has been collapsed. This is more expensive and should only be used if backfill is unsafe.
- Not allowed: runtime freshness code that says "if current hash mismatches, load historical request_json and compare old material hash."

### P0 - Dirty target terminalization and hot-queue eviction

Dirty targets are wake hints, not a durable failed queue. A target must leave `news_projection_dirty_targets` after it is evaluated for the current semantic hash. Long-lived failure state belongs in run/current audit and `worker_queue_terminal_events`, not in a forever-due dirty row.

Preferred implementation direction:

- if current semantic hash is fresh, `mark_done` deletes the dirty target;
- if provider quota/backpressure is active before claim, do not claim dirty targets at all;
- if a target is already claimed and provider outage is discovered, record lane/provider health, release or terminalize at lane level, and avoid per-item failed current writes;
- if a provider/model/domain failure is attributable to the item or output, retry only within bounded attempts, then terminalize via `worker_queue_terminal_events` and delete the dirty target;
- unchanged re-enqueue must not resurrect terminalized targets unless material hash/source fingerprint changes or an operator explicitly retries terminal events;
- remove `last_error` as a reason for hot-queue residency; it can exist for debugging during a short lease/retry window only.

### P1 - Cross-agent identity audit

After News P0, audit every enabled LLM lane for the same anti-pattern: provider/run/queue metadata included in input hash or freshness. This is not required to fix the current burn, but it prevents recurrence.

Known review results:

- News item brief has the confirmed production bug: `fetched_at_ms` in packet hash plus `items.updated_at_ms` in freshness.
- Narrative mention semantics hashes claimed DB rows before building the request, and claimed rows include queue metadata such as `lease_owner` and `attempt_count` (`src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py:113`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py:729`). That is a similar identity-boundary bug in audit/run identity, even if the worker is currently disabled.
- Narrative discussion digest hashes `sealed_context`; it must be checked for generated timestamps and queue metadata before re-enabling.
- Pulse uses evidence packet/fingerprint cost guard and terminal jobs, so it is less exposed to the exact News duplicate bug, but its no-start sets still need `quota_exhausted` added.
- The shared `AgentExecutionGateway` quota classification affects every agent lane, so provider balance/auth/quota handling must be fixed centrally, not only in News.

### P1 - Cost diagnostics

Add a read-only report that computes:

- eligible news/hour;
- expected one-brief tokens/hour from recent average usage;
- actual tokens/hour;
- amplification factor;
- top news items by runs/input_hashes/tokens;
- provider quota/balance failure rate.

This is not required to stop the leak, but it makes future regressions visible before balance is exhausted.

## Test Plan

- Unit: packet hash stable when only `fetched_at_ms` changes.
- Unit: `AgentStageSpec.input_payload` uses the same material payload as `packet.input_hash` and does not include volatile `fetched_at_ms`.
- Unit: packet hash changes when title/summary/body/content_hash/provider signal/token/fact/context semantic input changes, and active code has no story membership input.
- Repository integration: `load_items_for_brief_targets` returns unchanged `source_updated_at_ms` after pure refetch metadata update.
- Worker integration: ready current brief + volatile metadata dirty target produces `mark_done` and no provider `brief_item` call.
- Worker integration: material fact update produces one provider call and updates current brief.
- Worker integration: quota exhausted follows backpressure path, does not upsert failed current brief, and does not wake downstream projections.
- Worker integration: after max attempts for item-attributable provider/model/domain failure, dirty target is terminalized/evicted and no longer appears in due queue.
- Worker integration: unchanged re-enqueue after terminalization does not resurrect the target; material hash change or explicit terminal retry does.
- Gateway unit: `Insufficient Balance`, quota exceeded, unauthorized/auth/config errors classify into quota/capacity/backpressure bucket.
- Gateway unit: quota exhausted opens the lane circuit; the next reservation/execute attempt fails before provider call.
- Dirty target repository unit/integration: dirty target has bounded retry semantics and terminal events; `last_error` alone cannot keep a row permanently due.
- Architecture test: no runtime code path may compare historical/legacy packet hashes for freshness.
- Cross-agent architecture test: enabled LLM lanes must compute input hash from provider-visible semantic payload, not claimed row/lease/attempt metadata.
- Ops query smoke: diagnostics report top amplification rows and expected vs actual tokens without exposing secrets.

## Rollout And Verification

1. Before code change, capture baseline:
   - last 1h/6h/24h News item brief runs, tokens, distinct items, distinct input hashes;
   - due `brief_input` backlog;
   - top repeated items;
   - quota/balance failure rate.
2. Ship P0 stable hash, material freshness, terminalization, and quota classification tests together. This is one hard-cut patch, not staged compatibility.
3. If preserving old ready briefs is required, run the one-time backfill before enabling the worker; otherwise accept one-time stale treatment under low RPM.
4. Run a dry worker pass or integration test on unchanged items and prove dirty targets are marked done/terminalized without provider calls.
5. After deploy, monitor:
   - tokens/hour should fall from about 1M/hour to tens of thousands/hour once old backlog is drained or skipped;
   - input_hashes per unchanged item should be 1;
   - repeated failed provider-started runs for `Insufficient Balance` should stop.
   - due `brief_input` dirty targets should not contain old provider/domain failures indefinitely.

Immediate operator stopgap, if balance is still draining before code ships:

- disable `news_item_brief` in operator `workers.yaml`, or temporarily reduce the `news.item_brief` lane RPM to 1;
- keep `news_fetch`, `news_item_process`, and `news_page_projection` running so deterministic News surfaces continue;
- after balance is restored and the fix ships, re-enable `news_item_brief` and verify unchanged backlog is marked done without provider calls.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Real article update is missed because freshness is too narrow. | High | Tests must mutate every semantic input class and prove stale behavior. |
| Story projection accidentally returns to the hot path. | Medium | Remove `news_story_projection`, `news_story_updated`, story dirty targets, story API route, and story schema; tests should assert the absence rather than a compatibility fallback. |
| Context item engagement changes are prompt-relevant but not included in watermark. | Medium | Decide whether engagement is semantic; if included in packet, include it in hash/freshness tests. |
| Quota error hidden as generic BadRequest in LiteLLM wrapper. | High | Classify by exception type, HTTP status, provider body, and message substrings. |
| Dirty target backlog drains slowly even after fix. | Medium | Stable freshness gate should mark unchanged targets done without provider; ops report must track backlog burn-down. |
| Historical failed current brief prevents fresh skip. | Medium | Freshness currently returns false for status `failed`; quota/backpressure should not keep writing item-level failed current briefs for provider-wide outage. |
| Hash algorithm change triggers a one-time full rebrief. | High | Use one-time deployment backfill or run the worker under low RPM; never keep runtime compatibility branches. |
| Gateway audit hash diverges from worker persisted hash. | Medium | Use one material payload helper for packet hash and `AgentStageSpec.input_payload`. |
| Terminalized dirty targets hide recoverable work. | Medium | Terminalization key must include semantic material hash; material change or explicit terminal retry can re-enqueue. |
| Same bug recurs in Narrative when re-enabled. | Medium | Add cross-agent architecture test for semantic payload hashing before enabling narrative lanes. |

## Alternatives Considered

- **Disable `news_item_brief` worker temporarily.** This stops spend immediately but does not fix the root; high-signal News alerts still need ready agent briefs.
- **Raise provider score threshold.** This reduces eligible article count but not the 20x duplicate amplification; normal density is already low enough.
- **Add a hard daily token budget only.** Budgeting is useful as a guardrail, but without stable identity it will just cap useful work after duplicate spend.
- **Use `news_items.updated_at_ms` as material truth.** Rejected because live evidence shows it changes on refetch even when content hash and prompt-visible content do not.
- **Runtime legacy hash fallback.** Rejected because it preserves the same class of identity ambiguity and leaves a permanent compatibility path in the freshness gate.
- **Add a new durable central agent queue.** Rejected for this root fix; News already has a domain dirty target queue and currentness gate, and the bug is in identity/freshness semantics.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Collapse unchanged item refetch/projection churn before provider call. |
| Always | Treat provider quota/balance outage as provider/lane state, not article content failure. |
| Always | Preserve true material changes as rebrief triggers. |
| Always | Terminalize or evict bounded failures from the hot dirty queue. |
| Ask first | Any migration that adds new material timestamp columns or rewrites historical rows. |
| Ask first | Any operator config change under `~/.parallax/`. |
| Never | Print secrets, API keys, or raw credential values. |
| Never | Use provider fetch timestamp as LLM semantic input identity. |
| Never | Keep runtime legacy hash fallback or dual freshness semantics. |
| Never | Let `last_error` / failed dirty target rows stay due forever for unchanged material input. |
| Never | Hide validation/source-quality failures by loosening public output gates. |
