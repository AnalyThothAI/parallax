# Spec - Agent Execution Plane Hard Cut

**Status**: Implemented
**Date**: 2026-05-19
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`
- `docs/superpowers/specs/active/2026-05-18-pulse-agent-runtime-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`

## Decision

一次性 hard cut 的目标不是建立一个跨 domain 的 durable agent queue，而是建立一个统一的 **Agent Execution Plane**：

- domain worker 继续拥有 admission、claim、retry、finalize、read-model write；
- domain provider 继续拥有 prompt、input construction、schema、业务 validator、post-processing；
- `integrations/openai_agents` 统一 OpenAI Agents SDK execution envelope、runner、schema wrapper、usage、safety-net、trace、timeout、lane/bulkhead、circuit breaker、request/result audit；
- 现有 `LLMGateway` 收敛为低层 transport/client/trace primitive；
- 不新增 central `agent_tasks` 表，不新增 agent worker，不让 gateway 写任何 domain queue/read model/audit table。

这个取舍符合现有 Kappa/CQRS：PostgreSQL 事实和 domain read model 是业务 truth，agent execution plane 只是外部 provider 调用的控制面。

## Runtime Snapshot

本 spec 基于 2026-05-19 对真实 runtime 的只读检查。`uv run parallax config` 确认 live config 来自 operator-owned paths：

- config: `~/.parallax/config.yaml`
- workers config: `~/.parallax/workers.yaml`
- LLM configured: true
- active model family: `qwen3.6`

真实 DB 和日志显示，当前问题不是单个 worker 的 bug，而是 agent-heavy lanes 共享 provider 压力时没有统一执行面：

- Narrative `token_mention_semantics`: `labeled=227`, `queued=1154`, `semantic_unavailable=68`; 多个 target pending 接近 per-target cap。
- Narrative model runs last 24h: `discussion_digest` 573 done / 204 failed，`mention_semantics` 35 done / 55 failed；失败主要是 timeout。
- Pulse jobs: due pending 约 24，running 2，dead 683，done 3363；当前 backlog 小，但历史 dead/failure 很大。
- Pulse runs last 24h: timeout failed 277；`evidence_debate` failed 249，`decision_maker` failed 172。
- Watchlist runs last 24h: 171 done / 49 failed，p95 latency 约 100s 级别。
- News raw backlog 为 0，当前 news V1 是 deterministic processing；未来 LLM 只能进入 candidate extraction lane。
- App logs 同时出现 LLM 120s timeout、Token Radar projection SQL timeout、watchlist reconcile SQL timeout，说明 provider pressure 与 DB/projection pressure 会互相放大。

## Current Code Facts

2026-05-19 hard cut 后的 runtime foundation：

- `WorkerBase` 已经统一 lifecycle、advisory lock、wake-aware loop、timeout、metrics、status。
- `DBPoolBundle` 已经拆成 `api_pool`, `worker_pool`, `wake_pool`, `tool_pool`, `lock_pool`。
- `worker_session(worker_name)` 设置 `application_name=worker:<name>` 和 statement timeout。
- `LLMGateway` 是 transport-only：负责 `AsyncOpenAI` client、trace export key、shared headers、`trust_env=False`、close；不暴露 `run_with_limits`，不记录 worker/stage metadata，不拥有 lane/global budget。
- `AgentExecutionGateway` 是唯一 OpenAI Agents SDK execution path：负责 `Agent` / `RunConfig` / `Runner.run` envelope、strict schema wrapper、usage、safety-net、trace metadata、timeout、lane bulkhead、RPM、circuit breaker、reservation、request/result audit、telemetry、status snapshot。
- `provider_wiring/openai.py` 是 OpenAI provider composition root；bootstrap 构造一个进程级 `AgentExecutionGateway` 并注入 Social、Watchlist、Narrative、Pulse provider adapters。
- `workers.agent_runtime` 是全局/lane agent 执行策略来源，包含 `pulse.pipeline`, `pulse.evidence_debate`, `pulse.decision_maker`, `narrative.mention_semantics`, `narrative.discussion_digest`, `social.event_enrichment`, `watchlist.handle_summary`, `news.fact_candidate`。
- OpenAI SDK direct construction 被限制在 `integrations/openai_agents/agent_execution_gateway.py`、safety-net runner、schema helper；domain-specific clients 只构造 `AgentStageSpec` 并调用 gateway。
- 没有 central durable `agent_tasks` queue；domain workers 继续拥有 admission、claim、retry、finalize、read-model writes、business validation。

Hard cut 删除了 Pulse、Narrative、Social、Watchlist 四套 client 曾经各自手写的重复 envelope：

- `Agent` / `RunConfig` / `Runner.run`
- model/client construction
- `_api_base`, trace id, hash helpers
- strict schema wrapping
- safety-net fallback
- usage extraction
- request/result audit shape
- failure audit path
- artifact/runtime hash

上述能力现在由 `AgentExecutionGateway` 统一；domain adapters 保留 prompt/input/schema/business validator/post-processing。

## Problem

多个 worker 需要 LLM agent，但它们不是同一个业务队列：

- `MentionSemanticsWorker` 与 `TokenDiscussionDigestWorker` 由 Narrative admission/frontier 驱动；
- `PulseCandidateWorker` 有自己的 edge diff、budget、sealed evidence packet、stage steps、write gate；
- `EnrichmentWorker` 处理 social event semantic extraction；
- `HandleSummaryWorker` 处理 watchlist summary jobs；
- `NewsIntel` 当前 deterministic，未来 LLM fact extraction 必须是 candidate-only，不可直接写事实。

把这些队列强行合并，会制造第二个 truth source，破坏 one-writer。只做 per-worker tuning，又无法解决全局 provider saturation、lane starvation、timeout storm、audit shape drift。

因此问题要在两个层次切开：

1. **Domain job state machines remain local.** 每个 domain 自己决定什么值得处理、何时 claim、如何 finalize、如何写 read model。
2. **Agent execution becomes shared.** 所有 OpenAI agent calls 进入统一 execution plane，获得一致的限流、公平、熔断、超时、trace、usage、audit、schema/run 模板。

## Methodology References

本 spec 借鉴成熟系统方法论，但不引入新的重平台：

- Sidekiq best practices: jobs 使用简单 id、任务应可重复执行、并发要由资源池和 job contract 管住，而不是把复杂对象塞进队列。参考 [Sidekiq Best Practices](https://github.com/sidekiq/sidekiq/wiki/Best-Practices)。
- PostgreSQL `FOR UPDATE SKIP LOCKED`: 适合 queue-like tables 的多消费者抢占，但会给出不一致视图，因此只适合 control plane，不适合作为产品 truth。参考 [PostgreSQL SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html)。
- Circuit breaker: repeated timeout/failure 后快速拒绝，避免重试风暴继续消耗调用方线程、连接和 provider budget。参考 [AWS Circuit Breaker pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html)。
- Temporal workflow/activity 分离: workflow/state 必须可 replay，外部 IO 是 activity。这里不引入 Temporal，但采用同一理念：domain workflow state 在 DB，LLM/provider call 是可审计的 external activity。参考 [Temporal Workflows](https://docs.temporal.io/workflows)。

## First Principles

1. **Facts first.** Agent prose 不直接成为业务事实；事实、audit、read model 仍由 domain repositories 写入 PostgreSQL。
2. **One writer per read model.** Gateway 永远不写 `pulse_candidates`, `token_discussion_digests`, `social_event_extractions`, `watchlist_handle_summaries`, `news_page_rows`。
3. **Provider IO outside DB sessions.** Domain worker materialize input, release worker session, call agent, reopen session to persist result。
4. **Backpressure is not failure.** capacity denied / circuit open 不是 model failure，不能烧掉 domain max attempts。
5. **Started provider call is auditable.** 一旦调用外部 LLM，就必须有统一 request/result audit，包含 usage、latency、trace、parse mode、safety-net、error class。
6. **Lanes need bulkheads.** Bulk Narrative semantics 不能拖死 Pulse decision；Watchlist summary 不能在 provider outage 中反复占满全局 slot。
7. **Business validation stays domain-owned.** Pulse evidence ref verifier、Narrative evidence validation、Social exact-evidence filtering、Watchlist markdown salvage、News fact acceptance 都不进入 gateway。
8. **KISS means one new plane, not one new platform.** 不上 Redis、Temporal、Kafka、LangGraph、central DB queue，除非指标证明 in-process lane control 不够。

## Goals

- G1. 所有 OpenAI Agents SDK execution 经统一 `AgentExecutionGateway`，不再由每个 domain client 手写 `Agent` / `Runner` 模板。
- G2. 所有 LLM lanes 使用统一 lane policy：model、timeout、max concurrency、RPM、priority、circuit breaker、safety-net、attempt-burn semantics。
- G3. 所有 agent calls 产出统一 audit envelope，domain audit tables 继续分开存储但字段语义一致。
- G4. 所有 LLM provider calls 都支持 pre-run request audit，失败路径也能落库。
- G5. capacity denied / circuit open 不消耗 domain provider attempt，不把 backlog 伪装成 model failure。
- G6. Bulk lanes 与 high-value lanes 用 per-lane bulkhead 隔离，避免单一 FIFO semaphore starvation。
- G7. Watchlist prompt/schema 从 OpenAI integration client 移回 domain-owned types/prompts。
- G8. News future LLM lane 只产生 `news_fact_candidates` 或等价 candidate artifact，不直接写 accepted facts。
- G9. architecture tests 防止后续绕过 gateway、绕过 DBPoolBundle、绕过 WorkerBase。
- G10. 旧 worker-runtime spec 中过时的 worker count、pool count、wake 语义不再作为实施依据。

## Non-goals

- N1. 不新增 central durable `agent_tasks` / `agent_runs` 表来替代 domain queues。
- N2. 不合并 `narrative_model_runs`, `pulse_agent_runs`, `model_runs`, `watchlist_handle_summary_runs`。
- N3. 不让 gateway claim jobs、increment attempts、write terminal status、write read models。
- N4. 不把 Pulse 多阶段 pipeline 简化成单次 agent call。
- N5. 不把 business prompts、schemas、validators、evidence builders 移进 integration layer。
- N6. 不引入 Temporal、LangGraph、Celery、Redis、Kafka。
- N7. 不在 provider outage 时自动放宽 Pulse public write gate 或 Narrative semantic quality gate。

## Target Architecture

### Layers

```text
WorkerScheduler / WorkerBase / DBPoolBundle
  -> domain worker
  -> domain admission / claim / context materialization
  -> domain provider adapter
  -> AgentExecutionGateway
  -> LLMGateway transport/client
  -> OpenAI-compatible provider
  -> domain validator / finalizer
  -> domain audit table + read model
```

`AgentExecutionGateway` belongs under `integrations/openai_agents`, not under `domains/*` and not under `WorkerBase`.

`LLMGateway` remains the low-level transport primitive:

- owns `AsyncOpenAI` construction and close;
- owns trace export key setup;
- owns shared headers and `trust_env=False`;
- does not own global/lane hard cap or RPM limiter; those live in
  `AgentExecutionGateway`;
- does not know prompts, schemas, business stages, or DB tables.

`AgentExecutionGateway` owns OpenAI agent execution mechanics:

- builds `OpenAIChatCompletionsModel`;
- builds `Agent`, `RunConfig`, strict output schema;
- calls `Runner.run` or safety-net runner;
- extracts final output and usage;
- normalizes parse mode and safety metadata;
- produces request/result audit;
- applies lane/bulkhead/circuit policy;
- classifies execution errors.

### Domain Integration Points

| Domain worker | Agent lane | Gateway role | Domain-owned role |
| --- | --- | --- | --- |
| `mention_semantics` | `narrative.mention_semantics` | Execute strict batch labeling stage | admission budget, mention queue, labels validation, `narrative_model_runs` |
| `token_discussion_digest` | `narrative.discussion_digest` | Execute strict digest stage | due target selection, context compaction, digest status, `token_discussion_digests` |
| `pulse_candidate` | `pulse.evidence_debate`, `pulse.decision_maker` | Execute each stage with audit | evidence packet, route prompt selection, ref verifier, eval, write gate, job finalization |
| `enrichment` | `social.event_enrichment` | Execute strict social extraction | watched-event job queue, deterministic entities, extraction filtering, `social_event_extractions` |
| `handle_summary` | `watchlist.handle_summary` | Execute strict summary stage | no-input path, watched handle context, markdown salvage, summary write |
| future `news_item_process` | `news.fact_candidate` | Execute candidate extraction only | source item lifecycle, deterministic acceptance/rejection, `news_fact_candidates` |

Non-LLM workers (`narrative_admission`, `news_fetch`, `news_story_projection`, `news_page_projection`, market workers) do not touch `AgentExecutionGateway`.

### Lane Policy

Lane config is operator-tunable in `workers.yaml` under a runtime section, not in repo fixtures and not hidden in `.env`:

```yaml
agent_runtime:
  global_max_concurrency: 4
  global_rpm_limit: 60
  lanes:
    pulse.decision_maker:
      priority: high
      max_concurrency: 1
      timeout_seconds: 120
      circuit_breaker:
        failure_threshold: 5
        window_seconds: 300
        open_seconds: 120
    narrative.mention_semantics:
      priority: bulk
      max_concurrency: 1
      timeout_seconds: 120
    watchlist.handle_summary:
      priority: low
      max_concurrency: 1
      timeout_seconds: 120
```

Exact defaults belong in implementation, but the policy model must support:

- global max concurrency;
- global RPM;
- per-lane max concurrency;
- per-lane timeout;
- per-lane priority or weight;
- circuit breaker threshold/window/open duration;
- execution-started flag for attempt burn decisions;
- model override fallback matching today: Pulse/Narrative/Watchlist can override, Social can use global unless a separate override is added deliberately.

### Capacity Reservation

Workers whose claim path burns attempts or leases must be able to reserve execution capacity before claim:

```text
try_reserve(lane)
  -> no slot: skip claim, report backpressure, do not burn attempt
  -> slot acquired: claim domain job
      -> no job: release reservation
      -> job claimed: materialize input, release DB session, execute, finalize
```

This reservation is in-process and non-durable. It is not a queue and not a source of truth. Its only job is preventing claimed jobs from waiting behind a saturated provider lane until leases expire or attempts are wasted.

Pulse may use a coarse `pulse.pipeline` reservation before claiming a job, then stage-level execution inside the pipeline. The domain still decides how to finalize partial-stage failures.

### Error Taxonomy

`AgentExecutionGateway` classifies errors into stable classes:

| Error class | Provider call started | Attempt burn | Domain mapping |
| --- | --- | --- | --- |
| `capacity_denied` | no | no | keep pending / skipped cycle / backpressure note |
| `circuit_open` | no | no | keep pending / short backoff / degraded status |
| `timeout` | yes | yes | retryable provider failure |
| `rate_limited` | maybe | yes if request started | retryable provider failure and circuit signal |
| `transport_error` | maybe | yes if request started | retryable provider failure |
| `provider_error` | yes | yes | retryable or terminal by domain policy |
| `schema_invalid` | yes | yes | model output failure, possible deterministic repair only in domain |
| `domain_validation_failed` | yes | domain-owned | business rejection, not gateway failure |
| `deterministic_no_input` | no | no | business state, not provider failure |

Gateway never decides final job state. It returns execution facts; domain maps them to its own tables.

### Audit Envelope

Every agent call has a pre-run `AgentExecutionRequestAudit` and post-run `AgentExecutionResultAudit`:

- `provider`
- `backend`
- `model`
- `lane`
- `stage`
- `workflow_name`
- `agent_name`
- `sdk_trace_id`
- `group_id`
- `prompt_version`
- `schema_version`
- `runtime_version`
- `artifact_version_hash`
- `input_hash`
- `output_hash`
- `latency_ms`
- `usage`
- `parse_mode`
- `safety_net`
- `trace_metadata`
- `execution_started`
- `status`
- `error_class`
- `error_message`

Domain audit tables remain separate. They may store the envelope as JSON or unpack selected fields, but `usage` must be top-level and consistent, not buried only inside `trace_metadata`.

`artifact_version_hash` must include enough to distinguish runtime behavior: model id, prompt version, schema version, gateway runtime version, and output schema hash. It must not be only `artifact:{model}`.

### Prompt And Schema Ownership

Allowed:

- domain package owns prompt text, route selection, input payload construction, output Pydantic model, deterministic validators;
- integration package owns provider-compatible schema cleaning and SDK execution;
- shared `StrictJsonOutputSchema` remains provider-compatible for qwen/llama.cpp style backends.

Required cleanup:

- Watchlist prompt/schema move out of `integrations/openai_agents/watchlist_summary_agent_client.py` into `domains/watchlist_intel`;
- Narrative gains pre-call request audit parity;
- Watchlist uses pre-call request audit on failure path;
- Social/Narrative usage extraction becomes top-level audit data;
- safety-net client lifecycle is unified and closed through gateway-owned resources.

## Conceptual Data Flow

```text
Domain due work
  -> optional lane reservation
  -> domain claim/materialize input
  -> release DB session
  -> AgentExecutionGateway.execute(stage_spec)
      -> lane bulkhead
      -> circuit breaker
      -> LLMGateway/OpenAI client
      -> strict schema + safety net
      -> execution audit
  -> domain validation/post-processing
  -> domain audit table
  -> domain job finalization/read model write
```

## Interface Contracts

### AgentStageSpec

Domain-produced immutable stage descriptor:

- lane
- stage
- model override key
- instructions/prompt text
- input payload
- output type
- prompt version
- schema version
- workflow/agent names
- trace metadata
- max turns
- optional tools, only if evidence policy allows them

The gateway executes this descriptor. It does not mutate business inputs.

### AgentExecutionGateway

The gateway exposes:

- pre-run request-audit builder;
- non-blocking capacity reservation;
- stage execution with audit result;
- lane/circuit status for ops/status surfaces;
- close lifecycle for all provider-owned clients and fallback clients.

It does not expose SQL repositories and does not import `domains/*/repositories`.

### Domain Provider Protocols

Existing domain protocols stay meaningful:

- `PulseDecisionProvider.run_decision_pipeline`
- `NarrativeIntelProvider.label_mentions`
- `NarrativeIntelProvider.summarize_discussion`
- `SocialEventEnrichmentProvider.enrich_event`
- `HandleTopicSummaryProvider.summarize_handle`

The OpenAI implementations become thin adapters from domain protocol to one or more `AgentStageSpec` executions.

### Ops Status

Worker status remains under `WorkerBase` / `WorkerScheduler`. Agent execution plane adds operational status only:

- lane open/closed/half-open;
- in-flight per lane;
- rejected due to capacity;
- circuit-open rejections;
- timeouts/errors by class;
- p50/p95 latency by lane/stage;
- usage totals by lane/stage/model.

This status must not become product truth.

## Hard-Cut Boundaries

### Always

- All OpenAI Agents SDK stage execution goes through `AgentExecutionGateway`.
- All provider calls still pass through `LLMGateway` or its renamed low-level equivalent for client, headers, and trace export. Timeout, lane limits, RPM limits, and circuit policy live in `AgentExecutionGateway`.
- Domain workers own admission/claim/finalize.
- Domain repositories own all writes to domain queues, audit tables, facts, and read models.
- Capacity/circuit backpressure does not consume provider attempts.
- Provider-started calls produce audit even on timeout/failure.
- `workers.yaml` is the runtime knob surface for worker/agent execution policies.

### Never

- Never create a cross-domain durable agent queue as the first hard cut.
- Never let gateway write `pulse_agent_jobs`, `pulse_candidates`, `token_mention_semantics`, `token_discussion_digests`, `social_event_extractions`, `watchlist_handle_summaries`, or `news_*` tables.
- Never put business prompts or validators in `app/runtime` or generic gateway code.
- Never hold a `worker_session` open while awaiting external LLM/provider IO.
- Never count hidden Pulse audit rows as public product readiness.
- Never treat News LLM output as accepted facts without deterministic acceptance.

### Ask First

- Adding a durable `agent_execution_attempts` platform table.
- Adding Redis/Celery/Temporal/Kafka.
- Changing domain audit table schemas in a way that breaks existing dashboards.
- Allowing required LLM tool calls for Pulse evidence acquisition.

## Architecture Tests

Add or extend architecture tests to enforce:

- Only `integrations/openai_agents/*` may import `agents.Agent`, `Runner`, `RunConfig`, and output schema SDK primitives.
- Only `app/runtime/llm_gateway.py` or its direct successor may construct `AsyncOpenAI`.
- All OpenAI agent execution helpers must be reachable through `AgentExecutionGateway`; no domain client may call `Runner.run` directly.
- `integrations/openai_agents` must not import domain repositories.
- `app/runtime` and `integrations/openai_agents` must not write domain tables.
- Long-running workers must inherit `WorkerBase`; any `run()` override is explicit allowlist.
- Worker factories remain the only construction path from runtime settings to domain workers.
- No external provider IO occurs inside `RepositorySession` / `worker_session` scopes.
- `create_pool` only appears in `DBPoolBundle`.
- `wakes_on` workers receive `WakeWaiter` through factory wiring.
- New queue-like tables expose queue depth either via `JobQueueDescriptor` or `worker_status` registration.
- `docs/WORKERS.md` and `docs/CONTRACTS.md` worker inventory cannot drift from `worker_registry.py`.

## Acceptance Criteria

- AC1. WHEN `rg "Runner.run|Agent\\(|RunConfig\\(" src/parallax` is run, THEN live execution sites SHALL be limited to `integrations/openai_agents` gateway code and tests.
- AC2. WHEN Pulse, Narrative, Social, or Watchlist OpenAI providers execute, THEN each call SHALL pass through `AgentExecutionGateway`.
- AC3. WHEN a lane has no available capacity, THEN the worker SHALL skip or defer claim and SHALL NOT increment provider attempts.
- AC4. WHEN a circuit is open for a lane, THEN calls SHALL fail fast with `circuit_open`, report operational backpressure, and SHALL NOT call the provider.
- AC5. WHEN a provider call starts and times out, THEN audit SHALL include `execution_started=true`, `error_class=timeout`, latency, model, lane, stage, input hash, and trace id.
- AC6. WHEN a provider call succeeds, THEN audit SHALL include top-level `usage`, output hash, parse mode, safety-net metadata, prompt version, schema version, and artifact version hash.
- AC7. WHEN Watchlist summary fails before response, THEN `watchlist_handle_summary_runs` or equivalent failure path SHALL include request audit parity rather than only a simplified error row.
- AC8. WHEN Narrative provider call fails, THEN `narrative_model_runs` SHALL include request audit parity and stable error taxonomy.
- AC9. WHEN Pulse runs two stages, THEN each stage SHALL have separate execution audit while Pulse remains owner of run/step persistence and write gate.
- AC10. WHEN News adds an LLM lane, THEN output SHALL land as candidate/extraction audit and deterministic domain code SHALL decide accepted facts.
- AC11. WHEN `uv run pytest tests/architecture/test_worker_runtime_contracts.py` is run, THEN gateway/import/session/pool/wake/worker inventory guards SHALL pass.

## Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Gateway becomes a second business orchestrator | High | Architecture tests forbid repository imports and domain table writes. |
| Central durable queue temptation returns | High | First cut uses in-process lane reservations only; reconsider durable table only with measured multi-process coordination failure. |
| Capacity reservation starves low-priority lanes | Medium | Per-lane max concurrency plus priority/weight metrics; tune in `workers.yaml`. |
| Existing dashboards expect old audit shapes | Medium | Keep domain audit tables; add normalized fields while preserving old JSON where needed. |
| Pulse multi-stage semantics get flattened | High | Gateway executes stages only; `PulseCandidateJobService` owns pipeline, verifier, eval, write gate. |
| Capacity denied still burns attempts due to claim-first code | High | Workers with attempt-on-claim must reserve before claim or explicitly map no-start paths to no attempt burn. |
| Safety-net double retries hide true provider health | Medium | Gateway owns retry/safety-net metadata and records parse mode/retry count. |
| `LLMGateway` and `AgentExecutionGateway` split feels abstract | Low | Keep `LLMGateway` tiny: client/transport/trace only. All SDK stage execution, limits, and audit envelopes live in one gateway. |
| Old runtime spec causes implementation drift | Medium | Mark old worker-runtime spec as superseded for worker inventory/pool/wake counts during plan phase. |

## Alternatives Considered

### A. Central durable `agent_tasks` table

Rejected for this cut. It would duplicate `pulse_agent_jobs`, `token_mention_semantics`, `enrichment_jobs`, `watchlist_handle_summary_jobs`, and future news lifecycle state. It creates a second scheduler truth and violates Kappa/CQRS one-writer unless every domain queue is deleted at the same time, which is not KISS.

### B. Tune each worker separately

Rejected as insufficient. Worker-local budgets are still required, but they do not solve global provider timeout storms, lane starvation, inconsistent audit, safety-net lifecycle, or SDK invocation duplication.

### C. Only expand `LLMGateway`

Rejected as too low-level. `LLMGateway` is correctly shaped around transport/client/trace setup. Agent SDK execution needs prompt/schema/audit/stage concepts; putting all of that into a generic runtime object would blur the transport boundary.

### D. Adopt Temporal/LangGraph/Celery

Rejected for now. The project already has PostgreSQL control-plane tables, WorkerBase lifecycle, wake hints, and CQRS read models. The mature lesson to borrow is workflow/activity separation and idempotent queue semantics, not another runtime dependency.

### E. Chosen: in-process Agent Execution Plane

Chosen because it fixes the shared failure mode with the smallest architectural move:

- one new execution abstraction;
- no new durable truth;
- no new worker;
- no new broker;
- no cross-domain queue;
- existing domain providers remain the public seam;
- existing WorkerBase/DBPoolBundle architecture remains valid.

## Evolution Path

Phase 1 hard cut:

- introduce `AgentExecutionGateway`;
- migrate Pulse/Narrative/Social/Watchlist OpenAI clients to it in one PR;
- add lane policy and capacity reservation;
- normalize audit envelope;
- add architecture guards.

Phase 2 cleanup:

- move Watchlist prompt/schema ownership into `watchlist_intel`;
- update stale worker-runtime spec status and docs inventories;
- expose lane status in ops endpoints/metrics;
- tune `workers.yaml` using live latency/error/backpressure data.

Phase 3 only if needed:

- consider durable platform execution attempts for cross-process fairness;
- consider provider-specific model profiles;
- consider News LLM candidate lane;
- consider a real workflow engine only if PostgreSQL control-plane state machines become unmaintainable.
