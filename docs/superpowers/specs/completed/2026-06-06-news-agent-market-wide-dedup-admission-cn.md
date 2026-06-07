> Superseded on 2026-06-07 by `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md` and `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md`. Do not use this file for current News agent, projection, notification, API, or storage behavior.

# Spec - News Agent 市场级准入与重复/相似过滤优化

**Status**: Draft, pending Qinghuan approval
**Date**: 2026-06-06
**Owner**: Qinghuan / Codex
**Related**:
- `docs/AGENT_EXECUTION.md`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`
- `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-22-equity-event-intel-cn.md`

## Background

News Intel 当前拥有 configured news source ingestion、raw news item facts、deterministic entity/token observations、fact candidates、item-scoped agent briefs 和 News page read model，见 `src/parallax/domains/news_intel/ARCHITECTURE.md:3`。News facts 由 `news_provider_items`、`news_items`、`news_item_entities`、`news_token_mentions`、`news_fact_candidates` 等表承载，provider raw entries 是输入而不是事实，见 `src/parallax/domains/news_intel/ARCHITECTURE.md:15`。

Product agent 的执行平面明确要求：PostgreSQL facts 是 truth，domain workers 自己拥有 admission、claim、retry、finalize、ledger 和 validation；`AgentExecutionGateway` 只负责模型执行机制，见 `docs/AGENT_EXECUTION.md:14` 和 `docs/AGENT_EXECUTION.md:16`。News item brief lane 构造 deterministic packet 后提交给 gateway，并且不在 agent time 运行 News-local research tool loop 或 database retrieval tools，见 `docs/AGENT_EXECUTION.md:30`。因此“先用 actor 去数据库查相似”如果指 LLM agent 带工具查 DB，不符合当前 agent execution contract；如果指 deterministic worker/repository 在 agent 前做 bounded DB 查询，这是正确方向。

当前 item processing 链路在抽实体、token mentions、fact candidates 后，会分类内容、计算 `analysis_admission`、计算 `story_identity`，然后只有通过 `news_item_agent_brief_eligibility` 才会 enqueue `brief_input`，见 `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:99`、`src/parallax/domains/news_intel/runtime/news_item_process_worker.py:114`、`src/parallax/domains/news_intel/runtime/news_item_process_worker.py:120` 和 `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:177`。`brief_input` 当前仍以 `news_item_id` 为 target id，见 `src/parallax/domains/news_intel/runtime/news_projection_work.py:29`。

当前 agent policy 明确把 `analysis_admission_status == admitted` 作为硬 gate，见 `src/parallax/domains/news_intel/services/news_item_agent_policy.py:36`。它还保留了 crypto-specific fallback：score 低于 80 时，只有 score >= 65 且具备 explicit crypto admission basis 才能进入 agent，见 `src/parallax/domains/news_intel/services/news_item_agent_policy.py:45` 和 `src/parallax/domains/news_intel/services/news_item_agent_policy.py:82`。

当前 `decide_news_analysis_admission` 本质是 crypto-native admission。允许 admission 的 classes 包含 `crypto_market`、`security_hack`、`regulation`、`etf_fund_flow`、`exchange_listing`、`protocol_development`、`market_structure`，research context classes 包含 macro/rates/energy/consumer macro，但实际 admitted 条件仍要求 crypto evidence 或 accepted crypto fact，见 `src/parallax/domains/news_intel/services/news_analysis_admission.py:13`、`src/parallax/domains/news_intel/services/news_analysis_admission.py:24` 和 `src/parallax/domains/news_intel/services/news_analysis_admission.py:72`。非 crypto subject 会被判为 `page_only/non_crypto_subject`，provider evidence without crypto 会被判为 `page_only/provider_evidence_only`，见 `src/parallax/domains/news_intel/services/news_analysis_admission.py:80` 和 `src/parallax/domains/news_intel/services/news_analysis_admission.py:82`。

当前 story identity 已经具备一部分 deterministic similarity 能力：OpenNews article key 生成强 story key，strong subject 使用 shifted time bucket，material title fingerprint 使用 shifted time bucket，最后 fallback 到 item-level key，见 `src/parallax/domains/news_intel/services/news_story_identity.py:91`、`src/parallax/domains/news_intel/services/news_story_identity.py:120`、`src/parallax/domains/news_intel/services/news_story_identity.py:138` 和 `src/parallax/domains/news_intel/services/news_story_identity.py:157`。News page read model 也已经是 story-shaped row，row 可以代表 stable `story_key` 或单 item，并携带 compact member/source/provider evidence，见 `src/parallax/domains/news_intel/ARCHITECTURE.md:20`。

当前 docs 仍写着 item processing 只为 admitted crypto-analysis rows admit optional item brief work，见 `src/parallax/domains/news_intel/ARCHITECTURE.md:68` 和 `src/parallax/domains/news_intel/ARCHITECTURE.md:84`。这与新的产品边界冲突：Parallax 的 News agent 应该服务 crypto、美股、宏观、rates、AI semis、energy/geopolitics 等市场新闻，而不是 crypto-only。

2026-06-06 对真实近 8 小时数据的诊断显示：provider score >= 80 的 145 条中，90 条未进入 agent；主要原因是 `page_only/no_crypto_native_evidence` 或 `page_only/non_crypto_subject`，而不是 duplicate。高分未进入 agent 的样本中 duplicate count 基本没有解释力。这说明当前大量 `AGENT SKIP` 是 product admission 设计错误，不是重复过滤在发挥作用。

## Problem

用户希望 80 分以上的市场新闻进入 News agent，只有当它是重复新闻或同一 story 中大量类似更新时才被业务过滤。当前链路把 crypto-specific `analysis_admission` 放在 agent brief 前置门槛，导致美股、宏观、地缘、半导体等高分市场新闻被 `analysis_not_admitted` 过滤；同时真正应该控制成本的 duplicate/similar story gate 不是 agent admission 的主 gate。

## First Principles

1. **News agent 是市场级研究 agent，不是 crypto-only agent。** Crypto、US equities、macro/rates、AI semis、energy/geopolitics 都可以是市场新闻；domain classification 和 market scope 是 metadata，不是 80+ agent admission 的排除条件。

2. **重复/相似识别必须在 agent 前 deterministic 完成。** Product LLM agent 不携带 DB retrieval tools，不在 runtime 自己查相似新闻；bounded DB lookup 应由 News domain service/repository 在 `brief_input` enqueue 前完成，符合 `docs/AGENT_EXECUTION.md:30` 和 `docs/AGENT_EXECUTION.md:36`。

3. **Provider score 是 agent 入口，duplicate/similar 是成本和噪声 gate。** 对 score >= 80 的 processed provider item，默认应该进入 agent candidate set；只允许 exact duplicate、similar story already covered、similar burst without material delta、operational disabled/backpressure 等原因阻止执行。

4. **同一篇新闻和同一事件必须分层。** Exact duplicate 解决“同一篇/同一 payload”，similar story 解决“同一事件多条来源/更新”。Story grouping 可以抑制重复 agent，但不能把不同事实仅凭标题相似静默合并。

5. **Agent output 不是身份事实。** Agent brief 可以解释市场含义，但不能决定两条新闻是否重复；重复证据、story membership、representative target 都必须来自 persisted facts/read models，可重放、可审计。

## Goals

- G1. 对 `provider_signal.score >= 80`、`lifecycle_status=processed`、provider source enabled、published time valid 的新闻，系统 SHALL 默认生成 agent candidate，不因 `analysis_admission_status != admitted`、`non_crypto_subject` 或缺少 crypto evidence 被过滤。
- G2. Agent admission SHALL 只把 score>=80 的市场新闻业务过滤为 `exact_duplicate`、`similar_story_covered`、`similar_story_burst` 或 `materially_superseded` 这类重复/相似原因；operational skip 必须单独标记为 provider/model/capacity/config 问题。
- G3. Exact duplicate SHALL 在 enqueue agent 前识别，使用 provider article id、article-like canonical URL、strong content hash、normalized title/source/time 等 deterministic evidence，并保留 match evidence。
- G4. Similar story SHALL 在 enqueue agent 前识别，使用 `story_key`、entity/target overlap、event class、time bucket、provider score/source role 和 existing representative brief state 判断是否已有足够代表分析。
- G5. 同一 story 中的新 item 如果带来 material delta，系统 SHALL 重新分析 representative target 或生成 story refresh target，而不是因为“相似”被静默跳过。
- G6. `/api/news` 和 item detail SHALL 能解释每条 80+ 新闻的 agent state：ready/pending、exact duplicate、similar covered、similar burst、operational skipped；不再用 `analysis_not_admitted` 解释市场级 80+ skip。
- G7. Backfill/repair SHALL 能把过去窗口里 score>=80 且非 duplicate/similar 的历史 page-only items 重新 enqueue 到 agent brief work。
- G8. Architecture docs and tests SHALL encode “market-wide agent admission + duplicate/similar gate” so crypto-only admission does not regress.

## Non-Goals

- N1. 不引入 LLM agent/actor 在 runtime 使用 DB tools 查询相似新闻。
- N2. 不把 embeddings、vector DB 或 LLM fuzzy dedup 作为第一阶段 identity source；它们未来只能作为 advisory evidence 或 review queue。
- N3. 不在本 spec 中完成 2026-05-28 dedup spec 的完整 canonical item/duplicate edge migration；本 spec 可以先复用现有 `story_key`、provider article key、content hash 和 page row story payload。
- N4. 不删除 `analysis_admission_*` 存量字段，但剩余读取必须显式 allowlist 到 external push eligibility 或 worker diagnostics。News item brief admission、brief input packet、agent skip reason、page `agent_signal` 和默认 item detail contract SHALL NOT 读取它作为兼容路径。
- N5. 不改变 product LLM gateway，不增加 request-time agent execution。
- N6. 不扩展外部 phone push 规则。Phone push 可以继续有更严格 publishability gate；本 spec 只约束 News item brief agent admission。
- N7. 不把所有低分新闻都送入 agent。默认入口仍是 provider score threshold；本 spec 针对 80+ 高分市场新闻的错误过滤。

## Target Architecture

目标架构把当前 `analysis_admission` 从 agent brief 前置门槛中移除，新增一个市场级 agent admission 语义层：`NewsAgentBriefAdmissionPolicy`。它不判断新闻是不是 crypto，而是判断“这条高分市场新闻是否值得生成新的 agent brief”。

一条新闻到达后的合理链路如下：

1. **Fetch writes observation.** Provider fetch/upsert 仍只负责持久化 provider observation 和 normalized news item，不执行 agent，不做 LLM 判断。

2. **Item process builds deterministic evidence.** `NewsItemProcessWorker` 继续抽 entities、token mentions、fact candidates、content classification 和 story identity。Content classification、market scope、crypto/equity/macro labels 都写入 item metadata。

3. **Similarity gate queries DB before agent enqueue.** 在 `brief_input` enqueue 之前，domain service 通过 repository 做 bounded DB lookup：
   - exact duplicate lookup: provider article id、article-like URL、content hash、strong title fingerprint；
   - story candidate lookup: same `story_key`、same normalized material title bucket、same entities/targets/event class in recent window；
   - representative lookup: 当前 story 是否已有 fresh ready/insufficient brief，是否有更高 authority source 或更高 provider score representative；
   - burst lookup: 近 N 分钟同 story high-score item count、source count、duplicate count。

4. **Material delta decides whether similar means skip or refresh.** 相似不等于跳过。只有当新 item 没有 material delta 时才 skip。Material delta 包括：
   - source role 升级，例如从 aggregator/news 到 official/company/regulator/exchange；
   - provider score 明显提升或 provider signal 从 partial 变 ready；
   - 新增 material entities、equity ticker、crypto asset、company、country、regulator、commodity；
   - 新增 accepted/high-confidence fact type；
   - title/body content hash 表明不是同一 payload，且摘要包含新的数字、行动、声明或时间点；
   - story 已有 brief 过期或输入 hash 会发生 material change。

5. **Agent target is representative-first.** 第一阶段可以继续使用 `brief_input` item target，但只能 enqueue representative item 或 material-delta item。后续可以演进为 story-scoped target。无论哪种实现，agent packet 必须携带 story context 和 duplicate/similar evidence，让 brief 解释“这是新事件还是同事件更新”。

6. **Brief worker rechecks market-wide policy.** `NewsItemBriefWorker` claim target 后仍要二次检查 policy，但检查的是 market-wide admission + duplicate/similar freshness，不再检查 `analysis_admission_status == admitted`。

7. **Page projection surfaces explainable status.** `news_page_rows.signal_json.agent_signal` 和 item detail 展示 compact current brief state、admission reason、duplicate/similar evidence、representative id。`AGENT SKIP` 的产品原因应变成 duplicate/similar，而不是 crypto admission。

8. **Prompt and harness are part of the migration.** 这次不能只改 eligibility/policy。当前 `news_item_brief.md` prompt 的 `market_read_zh` 仍要求解释 `crypto-market transmission channels`，所以 market-wide admission 落地时必须同步升级 prompt，让 agent 分析 crypto、US equities、macro/rates、energy/geopolitics、AI semis、private company 等市场传导路径。Prompt 文案改变必须 bump `NEWS_ITEM_BRIEF_PROMPT_VERSION`。如果 input packet 增加 market scope、agent admission、duplicate/similar evidence、material delta 或 representative pointer 字段，必须 bump `NEWS_ITEM_BRIEF_SCHEMA_VERSION`。如果 validator/guardrail 对美股标的、非 crypto target、执行语言、证据 ref 或 unsupported asset 逻辑有变化，必须 bump `NEWS_ITEM_BRIEF_VALIDATOR_VERSION` 和/或 `NEWS_ITEM_BRIEF_GUARDRAIL_VERSION`。

这不是“多一个 LLM actor”。合理设计是“多一个 deterministic similarity gate”。它可以用 actor-like worker 命名和调度方式运行，但它必须是普通 domain worker/service：读 PostgreSQL facts/read models，写 admission/dirty target/read model 状态，保持可重放。

## Conceptual Data Flow

```text
provider fetch
  -> news_provider_items / news_items
  -> news_item_process
  -> entities / token_mentions / fact_candidates / content_classification
  -> story_identity
  -> market-wide agent admission + deterministic duplicate/similar gate
  -> representative brief_input target
  -> news_item_brief
  -> AgentExecutionGateway structured model call
  -> news_item_agent_runs / news_item_agent_briefs
  -> news_page_projection
  -> /api/news + /api/news/items/:id
```

Changed arrows:

- `story_identity -> market-wide agent admission` is the new gate. It replaces crypto admission as the agent decision point.
- `market-wide agent admission -> representative brief_input target` is where duplicate/similar suppression happens.
- `news_item_brief -> AgentExecutionGateway` stays unchanged: no DB tools, no local research loop, no request-time execution.

## Core Models

### Market Scope

Classification metadata describing what market the item touches.

- Examples: `crypto`, `us_equity`, `macro_rates`, `energy_geopolitics`, `ai_semiconductors`, `regulation`, `private_company`, `consumer_macro`, `unknown`.
- Invariant: market scope helps prompt/context/UI, but it does not exclude score>=80 items from agent by itself.

### Exact Duplicate Evidence

Deterministic evidence that an incoming item is the same article/payload as an existing item.

- Fields: `match_type`, `matched_news_item_id`, `matched_story_key`, `confidence`, `evidence`, `policy_version`.
- Strong match types: `same_provider_article_id`, `same_article_url`, `same_content_hash`.
- Medium match types: `same_material_title_same_source_window`, `same_title_same_provider_score_window`.
- Invariant: strong matches can suppress agent directly; medium matches need supporting time/source evidence and must be auditable.

### Similar Story Evidence

Evidence that an incoming item belongs to an already-covered event/story.

- Fields: `story_key`, `representative_news_item_id`, `member_count`, `high_score_member_count`, `source_count`, `fresh_brief_status`, `last_brief_input_hash`, `evidence`.
- Invariant: similar story evidence can suppress duplicate analysis only when material delta is false.

### Material Delta

Deterministic decision describing whether a similar item adds new information.

- Fields: `has_delta`, `delta_reasons`, `source_role_delta`, `score_delta`, `entity_delta`, `fact_delta`, `content_delta`, `brief_staleness_delta`.
- Invariant: `has_delta=true` turns a similar item into `eligible_refresh` rather than skip.

### Agent Brief Admission

Market-wide agent decision envelope.

- Statuses: `eligible`, `eligible_refresh`, `exact_duplicate`, `similar_story_covered`, `similar_story_burst`, `materially_superseded`, `score_below_threshold`, `source_suppressed`, `operational_disabled`, `needs_review`.
- Reasons for score>=80 product skip SHALL be duplicate/similar/superseded only, except operational/source suppression.
- Invariant: no status or reason may encode `no_crypto_native_evidence`, `non_crypto_subject`, or `analysis_not_admitted` as a market-wide agent skip reason.

### Representative Brief Target

The unit submitted to `news_item_brief`.

- First phase shape: `target_kind=item`, `target_id=representative_news_item_id`, with `story_key` and admission evidence in packet metadata.
- Future shape: `target_kind=story`, `target_id=story_key`, when story-scoped brief storage is introduced.
- Invariant: one exact duplicate cluster or similar story without material delta produces at most one fresh current brief per input/artifact hash.

### News Item Brief Harness Contract

The versioned runtime contract for prompt, packet schema, validation, and guardrails.

- Prompt: `news_item_brief.md` must describe a market-wide research agent, not a crypto-only analyst.
- Prompt version: changes from crypto-specific to market-wide instructions SHALL bump `NEWS_ITEM_BRIEF_PROMPT_VERSION`.
- Packet schema: if similarity/admission/material-delta evidence becomes part of `NewsItemBriefInputPacket`, `NEWS_ITEM_BRIEF_SCHEMA_VERSION` SHALL bump and current-brief freshness checks SHALL treat old rows as stale.
- Validator/guardrail: if validation starts recognizing equity/company targets or stricter evidence/execution-language rules, `NEWS_ITEM_BRIEF_VALIDATOR_VERSION` and/or `NEWS_ITEM_BRIEF_GUARDRAIL_VERSION` SHALL bump.
- Fixtures: harness tests SHALL include market-wide examples, including one crypto item, one US equity/company item, one macro/rates item, one similar story without delta, and one similar story with delta.
- Invariant: prompt/schema/validator versions are audit contracts, not comments. Old current briefs with obsolete versions must not masquerade as fresh output for the new market-wide behavior.

## Interface Contracts

### `/api/news`

Rows SHALL expose compact agent state:

- `agent_status`: `ready | pending | insufficient | failed | stale | disabled | exact_duplicate | similar_story_covered | similar_story_burst | materially_superseded`.
- `agent_skip_reason`: present only when no brief will run for this row.
- `agent_representative_news_item_id`: the item whose brief should be read for duplicate/similar rows.
- `agent_similarity`: compact story/duplicate evidence counts and match type.

For score>=80 rows, `agent_skip_reason` SHALL NOT be `analysis_not_admitted`, `no_crypto_native_evidence`, or `non_crypto_subject`.

### `/api/news/items/{news_item_id}`

Item detail SHALL include:

- full current brief when this item is representative;
- representative brief pointer when this item is duplicate/similar;
- exact duplicate evidence;
- similar story evidence;
- material delta decision;
Default item detail contract SHALL NOT include legacy `analysis_admission_*` as an agent state field. Diagnostics-only surfaces MAY expose it under an explicitly labelled legacy/analysis namespace.

### Worker Diagnostics

News worker status and source/status diagnostics SHALL separate:

- score below threshold;
- duplicate exact skip;
- similar story covered skip;
- similar burst skip;
- material delta refresh;
- operational provider/model/capacity skip;
- legacy crypto admission diagnostics.

Diagnostics SHALL support a bounded window query such as last 1h/8h/24h showing score>=80 counts by agent admission reason.

### Prompt And Harness

Implementation SHALL update the News item brief harness together with the chain change:

- `news_item_brief.md` SHALL replace crypto-only transmission guidance with market-wide transmission guidance.
- `NEWS_ITEM_BRIEF_PROMPT_VERSION` SHALL bump when prompt text changes.
- `NewsItemBriefInputPacket` MAY add compact market scope, agent admission, duplicate/similar, material delta, and representative fields; if it does, `NEWS_ITEM_BRIEF_SCHEMA_VERSION` SHALL bump.
- `news_item_brief_material_input_hash` SHALL include any new material packet fields so representative refresh decisions are deterministic.
- Stage specs SHALL continue to route through `AgentExecutionGateway`, with `tools=[]`, no DB retrieval tools, trace metadata, input hash, prompt version, and schema version.
- Unit/integration tests SHALL assert the stage is traceable, prompt is market-wide, no tools/handoffs are present, and stale contract rows are not treated as current.

### Backfill/Repair

An operator repair command or bounded repository method SHALL re-evaluate existing processed items in a time window:

- input: time window, min provider score, dry-run flag;
- output: counts by old reason, new reason, enqueued target count, duplicate/similar suppressed count;
- invariant: no secrets printed, no request-time model execution.

## Acceptance Criteria

- AC1. WHEN a processed provider item has `provider_signal.score >= 80`, valid published time, enabled source, and no exact/similar duplicate evidence THEN system SHALL enqueue or mark pending an agent brief target regardless of `analysis_admission_status`.
- AC2. WHEN a score>=80 US equity, private company, semiconductor, macro, rates, or energy/geopolitics item lacks crypto evidence THEN system SHALL NOT use `analysis_not_admitted`, `no_crypto_native_evidence`, or `non_crypto_subject` as its agent skip reason.
- AC3. WHEN two items share the same valid OpenNews provider article id THEN system SHALL produce one representative agent target and mark later members as `exact_duplicate` with evidence.
- AC4. WHEN two items share the same article-like canonical URL or strong content hash THEN system SHALL produce one representative agent target and expose duplicate evidence in list/detail.
- AC5. WHEN two items only share homepage/live/container URL THEN system SHALL NOT mark them exact duplicates without content/title/time evidence.
- AC6. WHEN a new score>=80 item belongs to a story that already has a fresh representative brief and material delta is false THEN system SHALL skip new model execution with reason `similar_story_covered`.
- AC7. WHEN a story receives many similar score>=80 items inside the configured burst window and none has material delta THEN system SHALL suppress additional item-level agent runs with reason `similar_story_burst`.
- AC8. WHEN a similar story item has material delta such as official source upgrade, new entity/asset/company, new accepted fact, provider score upgrade, or stale representative brief THEN system SHALL enqueue an eligible refresh target.
- AC9. WHEN `NewsItemBriefWorker` rechecks a claimed target THEN it SHALL use market-wide agent admission and duplicate/similar freshness, not `analysis_admission_status == admitted`.
- AC10. WHEN the last 8 hours are re-evaluated with min score 80 THEN every non-operational skip SHALL be attributable to exact duplicate, similar story covered, similar story burst, or materially superseded.
- AC11. WHEN `/api/news` serves a score>=80 row with no current brief THEN the response SHALL explain whether it is pending, duplicate/similar covered, or operationally disabled.
- AC12. WHEN the repair command is run twice on the same window without new data THEN the second run SHALL enqueue zero additional unchanged representative targets.
- AC13. WHEN tests run against fixed fixtures for crypto, US equity, macro, repeated OpenNews article id, same content hash, same story without delta, and same story with delta THEN expected admission statuses SHALL be stable and deterministic.
- AC14. WHEN architecture docs are updated THEN they SHALL no longer describe News item brief as admitted crypto-analysis only.
- AC15. WHEN the agent prompt is inspected THEN it SHALL describe market-wide transmission paths and SHALL NOT describe `market_read_zh` as crypto-market-only.
- AC16. WHEN prompt/schema/validator/guardrail behavior changes THEN the corresponding `NEWS_ITEM_BRIEF_*_VERSION` constant SHALL bump, and current-brief freshness checks SHALL treat obsolete contract rows as stale.
- AC17. WHEN `build_news_item_brief_stage` builds an `AgentStageSpec` THEN it SHALL continue to use `AgentExecutionGateway` semantics with no tools/handoffs, trace metadata, input hash, prompt version, and schema version.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent cost rises because more 80+ market news enters candidate set | High | Use representative-first duplicate/similar gate, score priority, existing lane capacity, burst suppression, and bounded repair dry-runs. |
| Over-suppressing genuinely new updates in same story | High | Require material delta checks; source role upgrade, new facts/entities, stale brief, and score upgrade force refresh. |
| Under-suppressing repeated syndicated headlines | Medium | Strong exact duplicate keys plus material title/source/time medium evidence; expose diagnostics by story/member count. |
| Reintroducing crypto-only logic through old `analysis_admission` callers | High | Unit tests assert score>=80 non-crypto market fixtures are eligible; architecture docs distinguish legacy admission from agent admission. |
| Story key over-merges unrelated items | Medium | Treat story similarity as suppressive only when material delta false; homepage/live URLs never exact by themselves. |
| Worker target churn during backfill | Medium | Dry-run counts first; idempotent enqueue by representative target/input hash; unchanged second repair enqueues zero. |
| Breaking phone push or alert semantics | Medium | Keep external push publishability separate; this spec only changes item brief agent admission. |
| Operator cannot tell why an item skipped | Medium | Add compact `agent_skip_reason`, representative pointer, duplicate/similar evidence, and window diagnostics. |
| Prompt remains crypto-specific after market-wide eligibility | High | Make prompt/harness updates acceptance criteria; bump prompt version and fixture-test US equity/macro outputs. |
| Old current briefs look fresh under the new behavior | High | Bump prompt/schema/validator versions as needed and rely on current-brief contract predicates/input hash to stale old rows. |

## Evolution Path

After this market-wide admission cut lands, the natural next step is to finish the canonical item/duplicate edge architecture from the 2026-05-28 dedup spec so exact duplicate evidence becomes a durable fact ledger instead of living primarily in item/story projection state.

The second expansion is story-scoped agent brief storage: one `story_key` can have a current market brief that updates when material delta arrives. The first cut can keep item-scoped current briefs as long as it enqueues only representative/material-delta items.

Embeddings or LLM-assisted near-duplicate review can be added later as advisory evidence for ambiguous clusters, but deterministic exact keys and material delta rules must remain the source of truth.

## Alternatives Considered

- **LLM actor queries DB for similar news at runtime.** Rejected because current agent execution contract forbids News-local DB retrieval tools at agent time, and because identity/dedup decisions must be deterministic, auditable, and replayable.
- **Rename crypto `analysis_admission` into market admission.** Rejected because the existing code and docs encode crypto-specific basis, negative evidence, and reason names. Safer path is a separate market-wide agent admission policy, then later deprecate or narrow legacy admission.
- **Run agent for every score>=80 item without duplicate/similar gate.** Rejected because it fixes false skips but explodes cost and repeats analysis during news bursts.
- **Use frontend/API filtering to hide duplicate agent rows.** Rejected because model executions would still happen and skip reasons would remain un-auditable.
- **Use `story_key` alone as the only duplicate detector.** Rejected because story similarity and exact duplicate are different concepts; story key can over-group related but distinct updates.
- **Change eligibility but leave prompt/harness unchanged.** Rejected because the current prompt still frames `market_read_zh` around crypto-market transmission, and old prompt/schema versions would make outputs hard to audit.
- **Use embeddings first.** Rejected because current failures are deterministic product gate failures, not semantic search failures.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Score>=80 processed market news becomes an agent candidate unless duplicate/similar/operational evidence says otherwise; duplicate/similar evidence is computed before agent execution; agent never decides item identity; API explains skip reasons; prompt/harness versions are updated with behavior changes. |
| Ask first | Lowering score threshold below 80; making story-scoped brief tables; broadening external phone push rules to all market news; adding embeddings/vector search; deleting legacy `analysis_admission_*`. |
| Never | Filter high-score US equity/macro/private company news because it is not crypto; use coverage tags as hidden crypto admission evidence for agent gating; let an LLM actor query DB and decide duplicates; use request handlers or frontend code to run agents. |
