# Spec - LiteLLM Native Agent Execution and News High-Score Alert Hard Cut

**Status**: Approved
**Date**: 2026-05-29
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `src/parallax/domains/pulse_lab/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`
- `docs/superpowers/specs/completed/2026-05-05-production-notifications-phase1-phase2-design-cn.md`

## Decision

本设计选择一次性 hard cut，而不是在现有 OpenAI Agents SDK execution plane 外面再套 LiteLLM 兼容层。

目标状态：

- 删除 OpenAI SDK / OpenAI Agents SDK 作为 runtime dependency；
- 删除 `integrations/openai_agents` 作为 live integration package；
- 新的共享执行面只通过 LiteLLM Python SDK 发起 LLM 调用；
- domain worker 继续拥有 admission、claim、retry、finalize、read-model write；
- 共享执行面继续拥有 lane bulkhead、RPM、timeout、circuit breaker、request/result audit、usage、JSON object enforcement、Pydantic validation；
- News 高分告警以 dedup 后的 canonical news item 为身份，以 ready agent brief 为外推前置条件，以 Notifications 事实层为唯一推送出口；
- Narrative analysis workers 可以整体关闭，且关闭后不影响 News 高分总结推送和 Signal Pulse 的基础运行边界；
- Signal Pulse 继续是 token/social/market evidence 的 agent surface，不作为 News 高分推送的 source of truth。

这不是 provider 兼容性改造，而是把项目里的 LLM execution primitive 从 "OpenAI-compatible client + OpenAI Agents SDK vocabulary" 改成 "LiteLLM-native model call + project-owned agent governance vocabulary"。

## Background

当前 worker inventory 的 source of truth 是 `worker_manifest.py`。Agent lane 包括 Narrative `mention_semantics` 和 `token_discussion_digest`、News `news_item_brief`、Pulse `pulse_candidate`、Social `enrichment`、Watchlist `handle_summary`，其中 `narrative_admission` 不是 agent 但会向 narrative analysis 链路写 control-plane targets（`src/parallax/app/runtime/worker_manifest.py:315`, `src/parallax/app/runtime/worker_manifest.py:335`, `src/parallax/app/runtime/worker_manifest.py:361`, `src/parallax/app/runtime/worker_manifest.py:448`, `src/parallax/app/runtime/worker_manifest.py:593`, `src/parallax/app/runtime/worker_manifest.py:636`, `src/parallax/app/runtime/worker_manifest.py:662`）。

当前底层 LLM transport 仍由 `LLMGateway` 构造 `AsyncOpenAI`，并从 `agents` 包设置 tracing export key（`src/parallax/app/runtime/llm_gateway.py:7`, `src/parallax/app/runtime/llm_gateway.py:8`, `src/parallax/app/runtime/llm_gateway.py:15`, `src/parallax/app/runtime/llm_gateway.py:44`）。当前 structured JSON execution 通过 `client.chat.completions.create(..., response_format={"type": "json_object"})` 调用 OpenAI-compatible client（`src/parallax/integrations/openai_agents/structured_output_strategy.py:36`, `src/parallax/integrations/openai_agents/structured_output_strategy.py:59`）。

当前 `AgentExecutionGateway` 已经集中拥有 lane policy、global concurrency、RPM、capacity reservation、request audit、artifact hash、trace id、runtime version、client validation 等治理能力（`src/parallax/integrations/openai_agents/agent_execution_gateway.py:92`, `src/parallax/integrations/openai_agents/agent_execution_gateway.py:112`, `src/parallax/integrations/openai_agents/agent_execution_gateway.py:116`, `src/parallax/integrations/openai_agents/agent_execution_gateway.py:131`, `src/parallax/integrations/openai_agents/agent_execution_gateway.py:179`）。但 audit contract 仍把 backend 写成 `openai_agents_sdk`，runtime version 仍是 `agent-execution-plane-v1`（`src/parallax/platform/agent_execution.py:18`, `src/parallax/platform/agent_execution.py:151`, `src/parallax/platform/agent_execution.py:197`）。

当前 OpenAI provider composition root 把 Narrative、Pulse、Social、Watchlist、News 都接到 `OpenAIAgents*Client` 和 `AgentExecutionGateway`（`src/parallax/app/runtime/provider_wiring/openai.py:10`, `src/parallax/app/runtime/provider_wiring/openai.py:11`, `src/parallax/app/runtime/provider_wiring/openai.py:15`, `src/parallax/app/runtime/provider_wiring/openai.py:16`, `src/parallax/app/runtime/provider_wiring/openai.py:17`, `src/parallax/app/runtime/provider_wiring/openai.py:205`, `src/parallax/app/runtime/provider_wiring/openai.py:215`）。

当前 runtime policy 已经有 lane 模型、timeout、max concurrency 和 RPM 的结构，默认 lanes 包括 `pulse.pipeline`, `pulse.signal_analyst`, `pulse.bear_case`, `pulse.risk_portfolio_judge`, `narrative.mention_semantics`, `narrative.discussion_digest`, `social.event_enrichment`, `watchlist.handle_summary`, `news.item_brief`。News fact candidate 不是 agent lane；事实候选由 `news_item_process` 确定性产生。

当前 dependencies 明确包含 `openai>=2.0.0` 和 `openai-agents>=0.10.5`，还没有 `litellm`（`pyproject.toml:22`, `pyproject.toml:23`）。`apprise` 已经是通知投递依赖（`pyproject.toml:10`）。

News 当前链路已经是 Kappa/CQRS：`news_fetch` 写 provider items / canonical items，`news_item_process` 写 entities/token mentions/fact candidates，`news_story_projection` 写 story read models，`news_item_brief` 写 agent runs/current briefs，`news_page_projection` 写 serving rows（`src/parallax/app/runtime/worker_manifest.py:385`, `src/parallax/app/runtime/worker_manifest.py:400`, `src/parallax/app/runtime/worker_manifest.py:424`, `src/parallax/app/runtime/worker_manifest.py:448`, `src/parallax/app/runtime/worker_manifest.py:468`）。

News dedup 已经存在 canonical item 和 observation edge 汇总：provider item upsert 维护 `news_item_observation_edges`，刷新 canonical item 的 duplicate observation count、source ids、source domains、provider article keys（`src/parallax/domains/news_intel/repositories/news_repository.py:1080`, `src/parallax/domains/news_intel/repositories/news_repository.py:1218`）。

News page projection 当前会把 provider signal、token lanes、fact lanes、agent brief compact envelope 放入 `news_page_rows`，并公开 `agent_status` 和 `agent_brief_computed_at_ms`（`src/parallax/domains/news_intel/services/news_page_projection.py:13`, `src/parallax/domains/news_intel/services/news_page_projection.py:48`, `src/parallax/domains/news_intel/services/news_page_projection.py:57`, `src/parallax/domains/news_intel/services/news_page_projection.py:60`）。但是 `_page_signal` 当前优先返回 provider signal；只有没有 provider signal 且 agent status ready 时才返回 agent signal（`src/parallax/domains/news_intel/services/news_page_projection.py:212`, `src/parallax/domains/news_intel/services/news_page_projection.py:217`, `src/parallax/domains/news_intel/services/news_page_projection.py:234`）。

News API 已经支持 `min_score` filter；它读取 `news_page_rows.signal_json ->> 'score'`，因此当前高分筛选实际主要筛 provider score（`src/parallax/app/surfaces/api/routes_news.py:17`, `src/parallax/app/surfaces/api/routes_news.py:24`, `src/parallax/domains/news_intel/repositories/news_repository.py:1504`, `src/parallax/domains/news_intel/repositories/news_repository.py:3380`）。

News item brief schema 已经具备中文 summary、market read、bull/bear view、affected assets、watch triggers、data gaps 和 no-execution-language 约束（`src/parallax/domains/news_intel/types/news_item_brief.py:63`, `src/parallax/domains/news_intel/types/news_item_brief.py:172`, `src/parallax/domains/news_intel/types/news_item_brief.py:189`）。但 `NewsItemBriefWorker` 当前遇到 provider signal 会直接 skip，所以 OpenNews provider-scored high-signal items 不会进入 agent brief 生成（`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:49`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:131`）。

Notifications 当前已经是 durable fact + delivery adapter 模型：rule engine 生成 candidates，worker insert notification facts 并 enqueue external deliveries，delivery worker 通过 Apprise 或 PushDeer 投递（`src/parallax/domains/notifications/services/notification_rules.py:36`, `src/parallax/domains/notifications/runtime/notification_worker.py:30`, `src/parallax/domains/notifications/runtime/notification_worker.py:82`, `src/parallax/domains/notifications/runtime/notification_delivery.py:21`, `src/parallax/domains/notifications/runtime/notification_delivery.py:65`）。当前 rule engine 没有 News rule，只评估 watched account、token flow、Signal Pulse（`src/parallax/domains/notifications/services/notification_rules.py:52`, `src/parallax/domains/notifications/services/notification_rules.py:64`）。

Notification repository 当前有 generic `dedup_key` 幂等插入，但 semantic duplicate 和 external cooldown 逻辑是 Pulse-specific（`src/parallax/domains/notifications/repositories/notification_repository.py:22`, `src/parallax/domains/notifications/repositories/notification_repository.py:49`, `src/parallax/domains/notifications/repositories/notification_repository.py:146`, `src/parallax/domains/notifications/repositories/notification_repository.py:173`）。

Pulse candidate gate 当前是 token/social/market read model 的独立产品门控，trade candidate 阈值为 72，high conviction 阈值为 78，不是 News provider score >85 的同一语义空间（`src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py:42`, `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py:50`）。

LiteLLM 当前 Python SDK 支持 `acompletion(model=..., messages=...)` 异步调用，接受 `timeout`, `response_format`, `base_url`, `api_key`, `max_tokens` 等 OpenAI-style 参数，并返回 OpenAI Chat Completions 形状的 response，包含 `choices` 和 `usage`。因此项目不需要手写 provider-specific HTTP client，也不需要保留 OpenAI SDK 才能得到 JSON object call shape。

2026-05-29 的真实 runtime 只读诊断显示，agent lane 堆积主要来自 provider timeout/522，而不是单个 domain worker admission 逻辑。News serving dedup 当前没有可见重复 serving rows，但 `score >= 85` 的 News rows 基本来自 provider score 且 agent status pending。这个快照直接暴露了两个结构性问题：LLM transport 出错会拖垮所有 agent lanes；News high-score provider items 被当前 brief worker 的 provider-signal skip 排除在 agent summary 之外。

## Problem

系统现在同时存在三类错位：底层 LLM 接入仍绑定 OpenAI/OpenAI Agents SDK，导致 LiteLLM 只能作为兼容 base URL 而不是原生 execution primitive；News 高分是 provider signal，但 provider-scored item 当前不会生成 agent brief，无法满足 "score >85 的 agent 总结后推送"；Notifications 有 durable 推送事实层，但没有 News high-signal rule，也没有跨 rule 的稳定 semantic signature 去支持 News dedup 和 external cooldown。结果是 agent backlog、News 高分、Signal Pulse、叙事分析和推送系统各自存在能力，却没有一条干净的产品链路把高分 News 变成低噪音、可审计、去重后的 agent 摘要推送。

## First Principles

1. **Hard cut means one live execution path.** Runtime 中只能有 LiteLLM-native LLM execution path；不能保留 OpenAI SDK path、OpenAI Agents SDK path、OpenAI-compatible adapter path、proxy-only path 或 hidden fallback path。
2. **Project owns governance, LiteLLM owns provider IO.** LiteLLM 负责 provider routing、request dispatch、OpenAI-style response normalization；项目负责 lane policy、capacity reservation、audit envelope、schema validation、domain finalization 和 read-model writes。
3. **Domain queues remain local.** News、Pulse、Narrative、Social、Watchlist 的 admission、claim、attempt burn、terminal state、read model 写入仍由各自 domain worker 拥有；共享执行面不新增 durable central `agent_tasks` truth source。
4. **Provider score is not agent summary.** OpenNews provider score 可以触发 agent brief priority 和 alert eligibility，但不能替代 ready agent brief 进行外部推送。
5. **News alert identity is canonical, not observation-level.** 高分 News 推送以 canonical `news_item_id` / canonical article identity 为第一身份；duplicate observations 只增加 evidence/source count，不产生多条外部推送。
6. **Notifications are product facts.** In-app、WebSocket、PushDeer、Telegram、Apprise 都只是 notification fact 的 projection 或 delivery；任何 News 高分推送必须先成为 durable notification。
7. **Bulk narrative is optional context, not alert dependency.** Narrative semantics/digest 可以关闭；News high-signal alert 和 Pulse base operation 不依赖它们的当前 freshness。
8. **Pulse and News scores are different currencies.** Pulse `rank_score`/`score_band` 和 News provider score/agent brief decision 不混用。二者可以互相引用 evidence，但不能互相代替门控。

## Goals

- G1. Runtime source and direct project dependencies no longer include OpenAI/OpenAI Agents SDK as an execution path: no direct `openai` / `openai-agents` dependency, no live source import of `openai.AsyncOpenAI`, `agents.*`, `OpenAIAgents*`, or `integrations.openai_agents`. `openai` may still appear only as a transitive dependency of LiteLLM in `uv.lock`.
- G2. All agent-like LLM calls across News, Pulse, Narrative, Social, Watchlist, Search/Equity if enabled, execute through one LiteLLM-native shared execution plane.
- G3. Existing lane semantics survive the hard cut: global max concurrency, global RPM, per-lane concurrency, per-lane RPM, per-lane timeout, circuit breaker, no-start backpressure, execution-started attempt semantics, usage extraction, and request/result audit remain observable.
- G4. A News item with provider score above the configured high-signal threshold is eligible for prioritized `news.item_brief` execution even when it already has provider signal; provider signal becomes input/evidence, not a skip condition.
- G5. External News high-signal push is created only when the canonical item has a publishable ready agent brief, passes deterministic content/source/token-impact filters, and has not already emitted the same stable semantic alert signature within its cooldown.
- G6. Duplicate provider observations for the same canonical News item produce one notification with aggregated source/duplicate metadata, not multiple phone pushes.
- G7. Narrative workers can be disabled as a group without producing hidden dependency failures in News high-signal summary, News high-signal notification, or Signal Pulse candidate evaluation.
- G8. Signal Pulse remains evaluated on its own evidence packet and gate; News high-score alert does not require Pulse publication and does not write `pulse_candidates`.
- G9. Ops surfaces show LiteLLM backend identity, lane health, provider error classes, terminal reason buckets, and News high-signal alert suppression reasons without exposing secrets.
- G10. The hard cut is measurable: architecture checks can reject old OpenAI/OpenAI Agents SDK imports, old backend audit strings, provider-signal brief skip semantics, and Pulse-specific-only notification semantic dedupe.

## Non-goals

- N1. No LiteLLM Proxy as the primary runtime path. The target uses LiteLLM Python SDK directly.
- N2. No compatibility adapter that preserves `LLMGateway.openai_client()` semantics.
- N3. No dual execution mode such as `provider=openai|litellm` in production runtime. Migration happens by hard cut, not by a long-lived feature flag.
- N4. No central durable `agent_tasks` table replacing domain queues.
- N5. No request-time LLM execution from `/api/news`, notification APIs, WebSocket handlers, or frontend.
- N6. No external push using provider summary alone. Provider signal may create pending/in-app visibility but cannot masquerade as agent brief.
- N7. No direct PushDeer/Telegram/Apprise call from News workers.
- N8. No News worker writing Pulse read models or Pulse worker writing News notification facts.
- N9. No automatic trading instruction, target price, stop loss, position size, leverage, or execution permission in News or Pulse push payloads.
- N10. No attempt to repair all historical dead Pulse/Narrative jobs as part of this spec; replay and cleanup belong in a later plan or verification artifact.

## Target Architecture

### 1. LiteLLM-Native Model Execution Plane

The shared execution plane moves out of `integrations/openai_agents` into provider-neutral naming. Its live provider call is LiteLLM SDK `acompletion`, not OpenAI SDK, not OpenAI Agents SDK, and not a project-written HTTP client.

The plane owns:

- model/lane resolution from runtime config;
- per-lane and global capacity reservation;
- RPM accounting;
- circuit breaker state;
- timeout and cancellation handling;
- JSON object request mode;
- application-side Pydantic validation and validation retries;
- usage extraction from LiteLLM's normalized OpenAI-style response;
- request/result audit envelope;
- trace/correlation ids owned by the app, not by OpenAI Agents SDK;
- status snapshot for ops.

The plane does not own:

- domain job claiming;
- attempt counters;
- dirty target lifecycle;
- read model writes;
- prompt authorship;
- business validation;
- notification creation;
- Pulse write gate decisions.

The audit vocabulary changes from OpenAI-specific to project/provider-neutral:

- provider: `litellm`;
- backend: `litellm_sdk`;
- provider family: the resolved LiteLLM provider or operator alias;
- output strategy: `json_object`;
- schema enforcement: `client_validate`;
- runtime version: a new LiteLLM-native execution runtime version.

### 2. Domain Agent Ports

Domain packages continue to define their own provider protocols and typed payloads. Implementations become LiteLLM-backed but do not expose LiteLLM objects to domain code.

News keeps its `NewsItemBriefInputPacket`, `NewsItemBriefPayload`, validation rules, evidence refs, no-execution-language guardrail, and run ledger semantics. Pulse keeps evidence packet, route selection, stage plan, claim/evidence verifier, recommendation clipping, and write gate. Narrative keeps mention label and digest domain validators. Social enrichment and Watchlist summary keep their own input compaction and finalization.

The hard cut removes "OpenAI" from implementation names and audit identity. Domain concepts may still use the word "agent" where it means "LLM-backed analytical worker", but integration code no longer references OpenAI Agents SDK.

### 3. Agent Runtime Lanes and Operational Tiers

Runtime lanes remain explicit. The target policy distinguishes product-critical lanes from bulk analytical lanes:

- `core_alert`: News high-signal brief and notification-critical model calls.
- `decision_surface`: Pulse decision stages.
- `bulk_analysis`: Narrative mention semantics, discussion digest, watchlist summaries.
- `enrichment`: Social event extraction.

This tiering is configuration semantics, not a new queue. It lets operators disable narrative analysis as a group while leaving News high-signal and Pulse surfaces independently runnable.

Narrative shutdown target:

```text
narrative_admission disabled
mention_semantics disabled
token_discussion_digest disabled
```

When this tier is off, no new narrative admission or digest dirty targets should be generated. Existing terminal/backlog rows remain inspectable but do not gate News or Pulse.

### 4. News High-Signal Summary Chain

The target News chain is:

```text
news_fetch
  -> news_provider_items / news_items / news_item_observation_edges
  -> news_item_process
  -> news_item_entities / news_token_mentions / news_fact_candidates / content_class
  -> news_story_projection
  -> news_story_groups / news_story_members
  -> high-signal brief priority selection
  -> news_item_brief via LiteLLM execution plane
  -> news_item_agent_runs / news_item_agent_briefs
  -> news_page_projection
  -> news_page_rows with provider_score + agent_brief envelope
  -> notification_rule: news_high_signal
  -> notifications / notification_deliveries
  -> in-app / WebSocket / external delivery
```

Provider signal is treated as structured input:

- provider score and direction can establish candidate priority;
- provider token impacts can support token-impact filters;
- provider summary can be shown as provider metadata;
- provider summary cannot be used as external push body when agent brief is missing.

The `news.item_brief` worker target state does not skip provider-scored items. High-score provider items are the first items that should get agent briefs because they are the only items eligible for external high-signal push.

### 5. News High-Signal Alert Rule

The notification rule is conceptually named `news_high_signal`. It reads committed News read models and emits `NotificationCandidate` only for canonical page rows that satisfy all of the following:

- provider or final signal score is at or above the configured threshold;
- canonical item is enabled and not a zero-edge artifact;
- source is enabled and not failing source hygiene;
- content class is allowlisted, or the item has token impacts / resolved token lanes strong enough to override low-signal content class;
- agent brief status is `ready`;
- agent brief has publishable Chinese summary and market read;
- alert signature has not already been emitted inside the external cooldown.

Default product posture:

- external push threshold starts at 85 and still requires a ready agent brief;
- in-app candidate visibility uses 85 so operators can inspect pending/ready items;
- external push requires ready agent brief;
- failed/insufficient/pending agent status is visible in payload metadata but does not create phone push.

### 6. Stable Dedup and Aggregation

News dedup happens at two levels:

1. Canonical News identity collapses provider observations into one `news_item_id`.
2. Notification semantic signature collapses repeated high-signal publication of the same canonical item and alert meaning.

The stable external signature includes:

- rule id;
- canonical item identity;
- score band;
- direction;
- decision class;
- affected asset identities or unresolved asset symbols;
- source trust/source role class;
- cooldown bucket.

The signature excludes:

- free-text summary;
- agent run id;
- prompt/model version;
- exact evidence quote order;
- duplicate observation count;
- fetched timestamp.

Duplicate observations update the existing notification's aggregate metadata and source refs. They do not create another external delivery unless the semantic signature changes in a material way after cooldown.

Notification repository should generalize semantic dedupe and external cooldown beyond Pulse, rather than adding a second News-only special case.

### 7. Signal Pulse Boundary

Signal Pulse remains a separate decision surface:

- It may consume News facts or News alerts as optional evidence in a future design.
- It does not gate News high-score push.
- News high-score push does not write Pulse candidates.
- Pulse notifications continue to use Pulse status, score band, and decision payload.
- Pulse health must be fixed before relying on Pulse as a trading desk surface, but that is not required for News high-signal alerts.

## Conceptual Data Flow

```text
provider data
  -> committed facts
  -> deterministic projections
  -> domain agent input packet
  -> LiteLLM-native execution plane
  -> domain validation + run ledger
  -> current read model
  -> notification rule
  -> notification fact
  -> delivery adapter
```

Changed arrows:

- `domain agent input packet -> LiteLLM-native execution plane`: replaces OpenAI/OpenAI Agents SDK execution entirely.
- `provider signal -> news_item_brief`: provider signal becomes prioritization/evidence input instead of skip reason.
- `news_page_rows -> notification_rule`: adds News high-signal rule using committed read models.
- `notification_rule -> notification repository`: extends semantic dedupe to News signatures.

No new central model queue is introduced. Domain workers remain the source of job lifecycle truth.

## Core Models

### `ModelExecutionCall`

Semantic request envelope for one LLM call.

- lane and stage;
- workflow and agent name;
- model alias resolved by runtime policy;
- messages or prompt/input payload;
- output schema identity;
- response mode;
- timeout and retry semantics;
- trace metadata;
- input hash;
- artifact hash.

Invariant: this envelope contains no secret values and no database connection/session handles.

### `ModelExecutionAudit`

Provider-neutral request/result audit.

- provider `litellm`;
- backend `litellm_sdk`;
- resolved model;
- lane and stage;
- input/output hashes;
- artifact/runtime versions;
- usage;
- latency;
- execution_started;
- error class;
- validation metadata;
- trace/correlation ids.

Invariant: every started provider call has a result or error audit; no-start capacity/circuit outcomes are audit-visible without burning provider attempts.

### `AgentLaneTier`

Operational grouping over existing lanes.

- `core_alert`;
- `decision_surface`;
- `bulk_analysis`;
- `enrichment`.

Invariant: tier disablement prevents new claims/admissions for that tier but does not mutate historical facts or delete terminal rows.

### `NewsHighSignalCandidate`

Read-side candidate for the notification rule.

- canonical news item identity;
- provider score and score band;
- provider direction;
- content class and tags;
- source role/trust/provider health;
- duplicate observation count and source domains;
- token impacts and resolved token lanes;
- agent brief status and decision class;
- agent brief Chinese summary/market read;
- occurrence time.

Invariant: candidate eligibility is deterministic from committed facts/read models and never runs an LLM inside the rule evaluation.

### `NewsHighSignalNotificationPayload`

Notification payload for a publishable high-score News alert.

- stable semantic signature;
- canonical item identity;
- title/headline;
- Chinese agent summary;
- Chinese market read;
- direction and decision class;
- affected assets;
- score band and provider score;
- source/domain/trust metadata;
- duplicate/source aggregation;
- suppression reasons when in-app only;
- source links and internal navigation target.

Invariant: external body uses agent brief text; provider summary may be included only as provider metadata.

### `NotificationSemanticSignature`

Generalized dedupe signature for semantic notification families.

- rule id;
- product identity;
- material state;
- cooldown bucket;
- external eligibility class.

Invariant: free text and run ids are excluded so model wording changes do not spam the operator.

## Interface Contracts

### Configuration

Runtime config expresses LiteLLM as the only LLM execution backend. Operator-owned config remains the source of truth; `.env`, fixtures, and repository examples are not live config.

Configuration semantics:

- one global LiteLLM API key/base URL/model default area;
- per-lane model aliases and provider params through runtime policy;
- no `openai_agents` backend selector;
- no dual `openai` vs `litellm` production mode;
- tier/group disablement for narrative analysis;
- News high-signal rule threshold, content/source filters, cooldown, channels, and external severity threshold.

Secrets remain redacted in config/ops output.

### Runtime and Ops

Worker status exposes:

- LiteLLM backend identity;
- lane/tier status;
- queue depth;
- due/running/failed/terminal counts;
- capacity denied and circuit open counts;
- provider error buckets;
- News high-signal eligible/pending-ready/ready/suppressed counters;
- notification external cooldown/suppression counts.

Provider raw error text is bounded and redacted.

### HTTP and WebSocket

`GET /api/news` remains read-only and may continue to support score filtering. The response contract distinguishes:

- provider score and provider signal;
- agent brief status and agent brief summary;
- alert eligibility/suppression state when available.

`GET /api/news/items/{news_item_id}` returns full agent brief envelope and latest alert metadata if a notification exists.

Notification APIs and WebSocket payloads continue to publish durable notification facts. They do not execute News agent briefs at request time.

### Notification Rule

`news_high_signal` emits durable notification facts through the existing notification worker lifecycle.

Expected behavior:

- in-app notifications can show ready high-signal News and optionally pending high-score inspection rows;
- external delivery is only enqueued for ready, deduped, eligible News alerts;
- semantic duplicate aggregation updates existing notification metadata;
- external cooldown duplicate suppresses phone push but may keep in-app aggregation.

## Acceptance Criteria

- AC1. WHEN runtime source is scanned for live OpenAI/OpenAI Agents SDK imports THEN no production source SHALL import `openai`, `agents`, `integrations.openai_agents`, `AsyncOpenAI`, `Agent`, `RunConfig`, or `Runner`.
- AC2. WHEN any domain worker needs an LLM call THEN it SHALL call the shared LiteLLM-native execution plane through its domain provider port and SHALL NOT construct provider clients itself.
- AC3. WHEN LiteLLM returns an OpenAI-style response with valid JSON object content THEN the execution plane SHALL validate it with the domain output schema, record usage/latency/audit, and return a typed payload to the domain worker.
- AC4. WHEN LiteLLM returns invalid JSON or schema-invalid content THEN the execution plane/domain validator SHALL record a failed run audit and SHALL NOT publish a ready current brief or notification.
- AC5. WHEN a News item has provider score above the high-signal threshold and provider signal exists THEN the News brief worker SHALL treat the provider signal as input/priority and SHALL NOT skip the item because provider signal exists.
- AC6. WHEN a high-score News item has no ready agent brief THEN external notification delivery SHALL NOT be enqueued for that item.
- AC7. WHEN a high-score News item has a ready agent brief and passes deterministic filters THEN `news_high_signal` SHALL create at most one durable notification per stable semantic signature/cooldown.
- AC8. WHEN multiple provider observations collapse into the same canonical News item THEN external push SHALL be emitted at most once and duplicate/source metadata SHALL aggregate onto the same notification family.
- AC9. WHEN narrative tier workers are disabled THEN no new narrative admission/semantics/digest work SHALL be claimed, and News high-signal brief/notification workers SHALL remain independently runnable.
- AC10. WHEN Signal Pulse is degraded or has no fresh public candidates THEN News high-signal push SHALL continue to operate from News facts/read models and SHALL NOT require Pulse publication.
- AC11. WHEN Notifications are globally disabled THEN News high-signal rule SHALL produce no notification facts or deliveries while News brief generation can still run.
- AC12. WHEN ops/config diagnostics are run against live operator config THEN they SHALL report paths, enabled booleans, backend/lane status, and redacted diagnostics without printing secret values.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| LiteLLM provider behavior differs by model, especially JSON mode support. | High | Keep application-side schema validation mandatory, keep per-lane provider params explicit, and make invalid schema a non-publishable outcome. |
| Removing OpenAI/OpenAI Agents SDK breaks existing agent tests and prompts unexpectedly. | High | Hard cut must update architecture contracts and all domain provider clients in the same branch; no old package remains as fallback. |
| News high-score provider signal is noisy, especially low-signal macro/geopolitical items. | High | External push requires ready agent brief plus content/source/token-impact filters; default external threshold is 85 with stable semantic/cooldown dedupe. |
| Agent brief backlog delays high-score push. | Medium | High-score News items get priority in brief selection; pending high-score rows can be visible in-app but do not external push. |
| Generalizing notification semantic dedupe regresses existing Pulse notification behavior. | Medium | Keep Pulse signature semantics equivalent while moving the abstraction from Pulse-specific helpers to shared notification signature policy. |
| Narrative shutdown hides useful context for Pulse. | Medium | Narrative remains optional context; Pulse evidence packet must tolerate missing digest and surface data gaps rather than failing. |
| No compatibility path makes rollback harder. | Medium | Rollback is branch/deploy rollback, not runtime dual mode. Verification must include smoke calls for each active lane before enabling external delivery. |
| External channels receive too much text or unsupported markdown. | Low | Notification payload has compact title/body, provider-specific delivery remains inside existing delivery adapter contracts. |

## Evolution Path

After this hard cut, the next natural expansions are:

- add News story-level agent digest for clusters after item-level high-signal alert proves useful;
- allow Pulse evidence packets to reference ready News high-signal briefs as optional exogenous catalyst evidence;
- add source-quality-aware alert thresholds once source quality rows have enough live history;
- add model/provider cost reports by lane using LiteLLM usage and project audit rows;
- add offline replay/eval for News high-signal alerts using historical canonical items and notification outcomes.

Do not foreclose multi-provider routing, but keep routing in LiteLLM/runtime policy rather than resurrecting provider-specific SDK clients.

## Alternatives Considered

- **LiteLLM Proxy with existing OpenAI SDK base URL**: rejected because it preserves the old OpenAI SDK/OpenAI Agents SDK runtime shape and makes LiteLLM a compatibility shim instead of the execution primitive.
- **Keep `LLMGateway.openai_client()` and replace only `base_url`**: rejected because it leaves old import contracts, audit backend strings, and client construction rules in place.
- **Introduce a central durable `agent_tasks` queue**: rejected because domain queues already encode business lifecycle and one-writer ownership; a central queue would create a second truth source.
- **Use provider summary as fallback external push body**: rejected because the product request is agent summary plus push, and provider text cannot be audited with the project's evidence-ref and no-execution-language validator.
- **Make Signal Pulse the source of News high-score push**: rejected because Pulse score and News provider score are different semantic spaces and current Pulse health should not block News alerts.
- **Create a new News alert worker**: rejected for the first cut because Notifications already owns durable notification facts and delivery lifecycle. A new worker is only justified later if rule evaluation cost or volume outgrows the existing notification worker.
- **Keep Narrative workers on by default for context richness**: rejected for the alert critical path because current LLM provider failures show bulk analysis can starve more valuable lanes. Narrative can be re-enabled after LiteLLM-native execution and lane health are stable.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use LiteLLM SDK as the only runtime LLM provider call path. |
| Always | Keep domain job lifecycle and read-model writes inside domain workers/repositories. |
| Always | Require ready News agent brief before external News high-signal push. |
| Always | Dedup News alert by canonical item and stable semantic signature, not by raw provider observation. |
| Always | Keep provider score, agent brief, and notification payload as distinct concepts. |
| Ask first | Changing default external threshold below 90 without token-impact/source filters. |
| Ask first | Re-enabling Narrative bulk analysis after the LiteLLM hard cut if provider health remains degraded. |
| Ask first | Feeding News high-signal briefs into Pulse evidence packets. |
| Never | Keep OpenAI/OpenAI Agents SDK runtime fallback. |
| Never | Execute an LLM from API handlers, WebSocket handlers, or frontend. |
| Never | External-push provider summaries as if they were agent summaries. |
| Never | Let News write Pulse candidates or Pulse write News notification facts. |
| Never | Print API keys, push URLs, provider secrets, or raw secret-bearing config in diagnostics. |
