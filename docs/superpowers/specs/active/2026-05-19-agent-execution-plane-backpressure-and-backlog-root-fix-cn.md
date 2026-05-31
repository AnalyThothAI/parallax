# Spec - Agent Execution Plane Backpressure And Backlog Root Fix

**Status**: Draft
**Date**: 2026-05-19
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-plan-cn.md`

## Background

The 2026-05-19 Agent Execution Plane hard cut made the correct architectural move:
the project does not introduce a central durable `agent_tasks` queue; domain
workers keep owning admission, claim, retry, finalization, read-model writes, and
business validation, while `AgentExecutionGateway` owns OpenAI Agents SDK
execution mechanics. The owning spec states this split explicitly in
`docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md:20-28`.

Current service bootstrap builds one process-level `LLMGateway` and one
`AgentExecutionGateway` when any LLM-backed lane is configured, then passes that
gateway into provider wiring (`src/parallax/app/runtime/bootstrap.py:100-111`).
Provider wiring injects the same gateway into Social, Narrative, Pulse, and
Watchlist providers (`src/parallax/app/runtime/provider_wiring/__init__.py:33-76`).
The gateway itself owns request audit construction
(`src/parallax/integrations/openai_agents/agent_execution_gateway.py:90-117`),
non-blocking reservation (`src/parallax/integrations/openai_agents/agent_execution_gateway.py:119-163`),
stage execution (`src/parallax/integrations/openai_agents/agent_execution_gateway.py:165-205`),
timeout audit (`src/parallax/integrations/openai_agents/agent_execution_gateway.py:207-229`),
lane status (`src/parallax/integrations/openai_agents/agent_execution_gateway.py:335-352`),
and SDK `Agent` / `RunConfig` construction
(`src/parallax/integrations/openai_agents/agent_execution_gateway.py:358-388`).

The project already has hard architecture guards for the central execution
boundary. `tests/architecture/test_agent_execution_plane_contracts.py:81-122`
fails if domain-specific OpenAI clients call `Agent`, `RunConfig`, `Runner.run`,
or construct `AsyncOpenAI` outside the allowed gateway / low-level transport
files. This proves the hard cut removed the worst duplicate SDK-envelope shape.

However, the cut did not finish the operational semantics that matter for LLM
performance and backlog. Agent lane settings declare `priority`, per-lane
`max_concurrency`, per-lane `timeout_seconds`, and per-lane `rpm_limit`
(`src/parallax/platform/config/settings.py:548-567`), but the gateway
currently applies only global RPM through `_global_limiter`
(`src/parallax/integrations/openai_agents/agent_execution_gateway.py:201`).
The configured `priority` and per-lane `rpm_limit` fields are not yet active
scheduling controls.

Pulse has a correctness/performance hazard. `PulseCandidateWorker` reserves
`pulse.pipeline` before claiming `pulse_agent_jobs`, because claim increments
`attempt_count` in `PulseJobsRepository.claim_due_job`
(`src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:172-175`).
That pre-claim reservation happens in
`src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:212-247`.
The actual provider stages then execute as `pulse.evidence_debate` and
`pulse.decision_maker` (`src/parallax/integrations/openai_agents/pulse_decision_agent_client.py:358-377`).
Because `try_reserve()` currently consumes both global and lane semaphore for
every lane, a single Pulse job can hold a global slot for `pulse.pipeline` and
then need a second global slot for the first stage. With
`global_max_concurrency=1`, this self-denies the stage as `capacity_denied`;
with higher global limits, it halves effective capacity under load.

Pulse also has a timeout mismatch. The lane config gives `pulse.pipeline`
`timeout_seconds=240` (`src/parallax/platform/config/settings.py:560`),
but `OpenAIAgentsPulseDecisionClient.timeout_seconds` returns a hard-coded
120 seconds (`src/parallax/integrations/openai_agents/pulse_decision_agent_client.py:80-82`).
`PulseCandidateJobService` wraps the whole two-stage pipeline in that provider
timeout (`src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py:243-255`),
so a slow but valid two-stage LLM pipeline can be cut off before the configured
pipeline lane budget.

Narrative has mostly moved in the right direction. The active throughput spec
requires independent admission, semantics, and digest workers
(`docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md:16-18`).
Current code has `NarrativeAdmissionWorker` reading the latest Radar frontier
and material source facts into `narrative_admissions`
(`src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py:62-121`).
`MentionSemanticsWorker` claims due semantic rows before enqueueing missing
rows (`src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py:44-59`)
and only enqueues missing rows from admissions
(`src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py:246-272`).
`DiscussionDigestService.refresh_decision()` now treats source volume as a
source-set property and returns `pending/semantic_labeling_pending` when source
is sufficient but semantics are not ready
(`src/parallax/domains/narrative_intel/services/discussion_digest_service.py:42-73`).

The remaining Narrative gap is no-start backpressure. `MentionSemanticsWorker`
turns any provider exception into per-row failures
(`src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py:80-128`),
and `complete_mention_semantics_batch()` increments retry count for retryable
failures (`src/parallax/domains/narrative_intel/repositories/narrative_repository.py:714-734`).
If `AgentExecutionGateway` rejects a call before provider execution starts
(`capacity_denied` or `circuit_open`), that path can still look like a provider
failure and burn semantic retry budget. This violates the hard-cut invariant
that backpressure is not failure
(`docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md:103-112`).

Ops visibility exists but is incomplete. `/api/status` includes
`agent_execution` from the gateway status snapshot
(`src/parallax/app/runtime/app.py:150-184`), and telemetry records
agent execution calls, duration, in-flight gauges, and backpressure counters
(`src/parallax/app/runtime/telemetry.py:59-78`). The richer ops
diagnostics aggregator currently composes providers, workers, queues, and
domains (`src/parallax/app/runtime/ops_diagnostics.py:63-92`), but
does not yet surface agent lane state, per-lane pressure, or no-start rejection
health as a first-class operator section.

There is also a cleanup smell: `src/parallax/integrations/openai_agents/agent_execution_types.py`
duplicates the live definitions in `src/parallax/platform/agent_execution.py`.
The live imports use `platform.agent_execution`; the integration-local duplicate
is not a runtime compatibility path today, but it is a misleading stale surface.

## Problem

The unified gateway centralizes SDK execution, but its current reservation,
timeout, backpressure, and observability semantics are not yet strong enough
for heavy-tailed LLM latency and multi-lane backlog. Pulse can self-deny or
halve global capacity by double-reserving, Narrative can burn retries on
no-start backpressure, configured lane priority/RPM does not fully control
execution, and operators cannot yet see agent-lane pressure in the same place
they inspect worker and queue backlog.

## First Principles

1. **Execution plane is not workflow truth.** PostgreSQL domain facts, queues,
   audit tables, and read models remain the business state. The gateway may
   admit, execute, classify, and audit LLM calls; it must not claim jobs, write
   domain tables, decide final job status, or invent product readiness.

2. **A provider call has three states, not two.** `planned` means a domain has
   work; `execution_started=false` means the provider was not called and domain
   attempts must not burn. If the domain already incremented an attempt while
   claiming a running job, the no-start path must compensate that claim
   increment or release the lease through an attempt-preserving method.
   `execution_started=true` means a timeout, schema failure, provider rate
   limit, transport error, or provider error is part of the retry/error budget.

3. **Capacity reservation is a scarce-resource contract.** A claim reservation
   protects a domain from burning an attempt without execution capacity. It must
   not require a second global slot when the same logical workflow starts its
   stages. Stage lane bulkheads should isolate `pulse.evidence_debate` from
   `pulse.decision_maker`, but they should not double-count the same pipeline
   against global LLM concurrency.

4. **LLM latency is heavy-tailed.** A two-stage pipeline cannot be bounded by a
   single hard-coded 120s timeout when lane policy allocates 120s per stage and
   240s to the pipeline. Timeouts must come from `workers.agent_runtime`, and
   nested timeouts must be monotonic: an outer workflow timeout cannot be
   shorter than its configured inner stage budget plus persistence/grace time.
   Gateway stage timeout is the authoritative provider-started timeout; worker
   wrappers must not cancel first and erase gateway audit.

5. **Rate limiting is admission pressure, not hidden work.** A per-lane RPM
   limit must not become an invisible in-process queue that holds lane/global
   semaphores while sleeping for a token. If a rate token is unavailable beyond
   a bounded admission budget, the gateway should surface no-start
   `rate_limited` backpressure, not fake provider latency.

6. **Backlog is arrival rate minus service rate.** Narrative and Pulse backlog
   are not solved by moving SDK calls into one gateway. Admission growth, queue
   waterlines, stale cleanup, no-start retry semantics, and provider throughput
   must all line up so the system degrades as `pending/backpressure`, not as
   fake `insufficient`, fake model failure, or silent dead jobs.

## Goals

- **G1. Pulse global-capacity correctness.** A Pulse job that reserves
  `pulse.pipeline` before claim must be able to execute `pulse.evidence_debate`
  and `pulse.decision_maker` without acquiring a second global slot for each
  stage. A test with `global_max_concurrency=1` must prove the first stage is
  not rejected as `capacity_denied` solely because the pipeline reservation is
  held.
- **G2. No-start does not burn attempts.** `capacity_denied` and `circuit_open`
  with `execution_started=false` must not increase Pulse job attempts,
  Narrative semantic retry counts, Watchlist summary attempts, or Social
  enrichment attempts. For job queues whose claim already increments
  `attempt_count`, the no-start release path must compensate that increment or
  use an attempt-preserving release method. Workers may record backpressure notes
  and leave work due/pending.
- **G3. Lane timeouts are authoritative.** Pulse pipeline timeout must come from
  `workers.agent_runtime.lanes["pulse.pipeline"].timeout_seconds`, and stage
  timeouts must come from their stage lanes. Hard-coded provider timeout fallbacks
  cannot be lower than lane policy, and outer worker timeouts must not fire
  before gateway can emit started/failed audit.
- **G4. Lane RPM is active without becoming a hidden queue.** Per-lane
  `rpm_limit` must become an active limiter or no-start `rate_limited`
  admission check. A request waiting only for RPM must be observable separately
  from provider-running calls and must not permanently occupy scarce lane/global
  capacity. `priority` must be surfaced as a policy label only unless a future
  queued arbiter exists; runtime docs and ops payloads must not imply strict
  priority scheduling that the in-process non-blocking reservation API cannot
  guarantee.
- **G5. Agent ops visibility is first-class.** `/api/ops/diagnostics` must expose
  agent execution lane status, in-flight counts, capacity denials, circuit-open
  denials, timeout counts, rate-limit pressure, oldest in-flight/reservation
  ages, recent/last event timestamps, and policy knobs without secrets.
- **G6. Narrative backlog remains bounded after drain.** The existing
  `ops rebuild-narrative-intel --drain` path must be part of rollout, and health
  evidence must show source-sufficient rows as `pending/semantic_labeling_pending`
  during catch-up rather than `insufficient/low_source_volume`.
- **G7. Stale execution-plane types are removed.** There must be one source of
  truth for `AgentStageSpec`, `AgentExecutionErrorClass`, reservation types, and
  hashing helpers.
- **G8. Architecture tests prevent regression.** Tests must fail if SDK execution
  bypasses the gateway, if no-start backpressure burns domain attempts, if Pulse
  double-reserves global capacity, or if `agent_runtime` settings drift from
  gateway behavior.

## Non-goals

- Do not create a central durable `agent_tasks`, `agent_runs`, Redis queue,
  Celery worker, Temporal workflow, Kafka topic, or LangGraph runtime.
- Do not merge domain audit tables (`narrative_model_runs`, `pulse_agent_runs`,
  `model_runs`, `watchlist_handle_summary_runs`).
- Do not relax Pulse evidence verification, hidden/public write gates, or
  claim validation to make the UI look fresh.
- Do not treat provider timeout or circuit-open state as insufficient narrative
  evidence.
- Do not add LLM fact extraction to News in this slice.
- Do not change Token Radar scoring or candidate admission thresholds except
  where Pulse/Narrative consume the existing read models honestly.

## Target Architecture

The target architecture keeps the hard-cut shape but clarifies reservation
semantics:

```text
domain worker
  -> optional claim reservation
       - checks lane/global pressure
       - does not become product truth
       - does not write DB
  -> domain claim/materialize input
  -> provider adapter builds AgentStageSpec
  -> AgentExecutionGateway.execute(...)
       - uses existing global reservation for parent pipeline when present
       - acquires only the concrete stage lane semaphore
       - applies global RPM and per-lane RPM without hidden semaphore sleeps
       - classifies no-start vs started failures
       - returns request/result audit
  -> domain validator/finalizer
  -> domain audit table + read model
```

For Pulse, `pulse.pipeline` is a parent claim reservation. It exists because
`pulse_agent_jobs.claim_due_job()` increments `attempt_count`. That parent
reservation holds the global execution slot across the logical workflow and
enforces the pipeline lane concurrency. Individual stages acquire and release
their own stage lane semaphores, but reuse the parent global slot. This prevents
both no-capacity claim and double global accounting.

For Social and Watchlist, claim reservation and execution lane are the same
lane, so the current reservation can still be passed directly into
`execute(stage, reservation=reservation)`. Once a same-lane reservation is
accepted, `execute()` must trust that admission decision and must not do a second
pre-run circuit check that can burn an already-claimed attempt. Parent Pulse
execution is different: it must still check the concrete child stage lane
circuit/capacity because the parent reservation did not reserve that child
bulkhead.

For Narrative, the workers do not currently reserve before claim because their
queue rows are semantic work items and no-start must not mutate retry count. The
target contract is explicit handling of `AgentExecutionError` where
`execution_started=false`: record worker backpressure notes and leave claimed
semantic rows eligible for later processing without incrementing retry count.

For lane scheduling, the gateway owns:

- global max concurrency;
- global RPM;
- per-lane max concurrency;
- per-lane RPM;
- per-lane timeout;
- circuit breaker;
- no-start rate-limit classification when limiter capacity is unavailable
  without a bounded wait;
- priority label exposure without pretending to provide strict scheduling;
- status snapshot for `/api/status` and `/api/ops/diagnostics`.

Domain workers own:

- which job rows are worth processing;
- whether a no-start result leaves a job pending, releases a lease, or schedules
  a short retry;
- started-call retry/failure policies;
- domain audit persistence;
- product read model writes.

## Conceptual Data Flow

```text
Token Radar / Watchlist / Social / Pulse due work
  -> domain queue/admission state
  -> claim reservation or no-start classification
  -> LLM stage execution through AgentExecutionGateway
  -> domain validator and audit table
  -> read model / public surface
```

Changed arrows:

- Pulse changes from `pipeline reservation -> stage reservation with new global
  slot` to `pipeline parent reservation -> stage lane reservation with inherited
  global slot`.
- Narrative changes from `any provider exception -> retryable semantic failure`
  to `execution_started=false -> backpressure/no attempt burn` and
  `execution_started=true -> retryable or terminal provider failure`.
- Ops changes from worker/queue/domain-only diagnostics to worker/queue/domain
  plus agent-lane pressure.

## Core Models

**Agent reservation scope**: a reservation records whether it owns a global slot,
which lane it owns, whether it is a parent pipeline reservation, and whether it
is active. Parent reservations may be reused by child stage execution without
re-acquiring global capacity.

**Execution-started flag**: audit truth that separates no-start backpressure from
provider failures. Domain code must branch on this flag before mutating retry or
attempt counters.

**Lane policy**: runtime-configured execution policy loaded from
`workers.agent_runtime`. Policy includes priority, max concurrency, timeout,
RPM, and circuit breaker. The implementation must not expose policy fields that
are ignored at runtime.

**Agent lane diagnostics**: read-only operational payload containing lane policy,
in-flight count, capacity-denied count, circuit-open count, timeout count, and
recent execution counters. It is not product truth.

**Narrative drain evidence**: formal operator result from
`ops rebuild-narrative-intel --drain`, plus `/api/status/narrative-health`
showing bounded pending/retryable/unavailable semantics after rebuild.

## Interface Contracts

### Gateway API

`AgentExecutionGateway` must expose:

- request-audit builder;
- non-blocking reservation for a lane;
- execution using a matching reservation;
- execution using a parent/global reservation plus a child stage lane;
- status snapshot including policy and counters;
- close lifecycle for safety-net and low-level clients.

No gateway method may import domain repositories or write domain tables.

### Domain Provider Protocols

Existing provider protocols remain the domain boundary:

- `PulseDecisionProvider.run_decision_pipeline(...)`
- `NarrativeIntelProvider.label_mentions(...)`
- `NarrativeIntelProvider.summarize_discussion(...)`
- `SocialEventEnrichmentProvider.enrich_event(...)`
- `HandleTopicSummaryProvider.summarize_handle(...)`

Pulse provider protocol must gain a way to accept a parent pipeline reservation
or a pipeline execution context from `PulseCandidateWorker` through
`PulseCandidateJobService` into `OpenAIAgentsPulseDecisionClient`.

Pulse no-start metadata must not be lost inside `StageRunAudit`. If an
`AgentExecutionError` has `execution_started=false`, the Pulse client must either
propagate that typed exception to `PulseCandidateJobService` or wrap it in
`PulseStageFailure` with explicit `agent_error_class`, `execution_started`, and
`agent_audit` fields. Plain error strings are not sufficient for backpressure
classification.

Narrative provider failures must preserve `AgentExecutionError.error_class`,
`execution_started`, and audit payload so the worker can distinguish no-start
from started provider failures.

### Ops HTTP

`GET /api/status` continues returning lightweight readiness plus
`agent_execution`.

`GET /api/ops/diagnostics` must add an `agent_execution` section with:

- `status`;
- `global_max_concurrency`;
- `global_in_flight`;
- `global_rpm_limit`;
- `lanes[]` with lane, priority, max concurrency, timeout, rpm limit,
  in-flight/reserved count, provider-running count when available, rpm-waiting
  count when available, circuit state/open-until, capacity-denied total,
  circuit-open total, timeout total, recent deltas or last timestamps, and
  oldest in-flight/reservation age;
- no secrets, prompts, raw model inputs, or raw model outputs.

### CLI / Ops

`uv run parallax ops rebuild-narrative-intel --drain` remains the
formal Narrative drain/rebuild entry point for this rollout. The verification
contract must record its sanitized JSON result, not manual SQL.

## Acceptance Criteria

- **AC1.** WHEN `AgentExecutionGateway` has `global_max_concurrency=1` and a
  Pulse pipeline parent reservation is held, THEN executing the first Pulse
  stage with that parent reservation SHALL NOT return `capacity_denied` solely
  because the parent holds the global slot.
- **AC2.** WHEN Pulse stage execution is denied before provider start, THEN
  `pulse_agent_jobs.attempt_count` SHALL be the same after release as it was
  before the no-start claim, and the job SHALL be released or rescheduled as
  backpressure rather than dead provider failure.
- **AC3.** WHEN Narrative mention semantics receives `AgentExecutionError` with
  `execution_started=false` and `error_class=capacity_denied` or `circuit_open`,
  THEN `token_mention_semantics.retry_count` SHALL NOT increment and the worker
  SHALL report backpressure in notes.
- **AC4.** WHEN a provider call starts and times out, THEN audit SHALL include
  `execution_started=true`, `error_class=timeout`, lane, stage, latency, model,
  trace id, input hash, and top-level usage if available.
- **AC5.** WHEN `workers.agent_runtime.lanes.pulse.pipeline.timeout_seconds`
  is configured to 240, THEN the outer Pulse pipeline timeout SHALL be no lower
  than the configured pipeline timeout plus explicit grace or SHALL be removed in
  favor of gateway stage timeouts; stage timeouts SHALL use their stage lane
  values.
- **AC6.** WHEN a lane has `rpm_limit=1`, THEN two started executions in that
  lane SHALL be separated by the lane limiter even if global RPM is higher, and
  the limiter path SHALL NOT hold scarce lane/global capacity while sleeping for
  an unbounded token wait.
- **AC7.** WHEN a lane has `priority=high` or `priority=bulk`, THEN status and
  docs SHALL describe that value as a policy label, not as a strict scheduler
  guarantee, unless a future queued arbiter is introduced.
- **AC8.** WHEN `/api/ops/diagnostics` is requested with valid auth, THEN it
  SHALL include sanitized agent lane status and counters without prompts,
  provider API keys, raw inputs, or raw outputs, and overall diagnostics SHALL
  include agent execution status in blocked/degraded/ok aggregation.
- **AC9.** WHEN `ops rebuild-narrative-intel --drain` runs after deployment,
  THEN obsolete current-frontier queued/retryable Narrative semantics SHALL be
  removed or reset through the formal command, not manual SQL.
- **AC10.** WHEN source set is sufficient but semantics are pending, THEN Token
  Radar / Token Case narrative status SHALL remain `pending` with
  `semantic_labeling_pending`, not `insufficient/low_source_volume`.
- **AC11.** WHEN repository search is run after the fix, THEN there SHALL be no
  production import of the stale `integrations/openai_agents/agent_execution_types.py`.
- **AC12.** WHEN Social or Watchlist has claimed a job and the gateway returns
  no-start `capacity_denied`, `circuit_open`, or `rate_limited`, THEN the job
  SHALL be released/rescheduled without a net `attempt_count` increase and
  without a failed provider model-run audit.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Parent reservation leaks a global slot | High | Reservation owns explicit active/release state; tests assert release after success, failure, and cancellation. |
| Parent reservation bypasses stage bulkheads | High | Child execution must still acquire the concrete stage lane semaphore; only global acquisition is inherited. |
| No-start handling leaves claimed jobs stuck running | High | Domain repositories must expose explicit backpressure release/reschedule methods or reuse existing fail/retry paths without incrementing attempts where possible. |
| No-start release decrements attempts more than once | High | Release methods must guard by running status, lease/run identity, and current attempt count. |
| Pulse run remains `running` after job backpressure release | High | No-start Pulse paths must close or skip the current `pulse_agent_runs` row and may require a narrow outcome-constraint migration. |
| Per-lane RPM creates a hidden semaphore queue | High | Limiter waits must be bounded/observable and must not count as provider-running work while holding scarce capacity. |
| Outer worker timeout cancels before gateway audit | High | Gateway owns stage timeout; any outer workflow timeout must include explicit grace or be removed. |
| Priority-aware admission becomes a scheduler platform | Medium | Keep it in-process and policy-only; do not add a durable central queue. |
| Narrative drain deletes useful current rows | Medium | Drain command uses current admissions/source fingerprints and never touches material facts. |
| Per-lane RPM slows recovery too much | Medium | Defaults keep lane RPM unset; only configured lanes get lane limiter. |
| `priority` is mistaken for strict scheduling | Medium | Treat it as an explicit policy label in status/docs; defer real priority scheduling to a separate queued-arbiter spec. |
| Ops panel exposes sensitive inputs | High | Return counters and policy only; tests scan for prompt/input/output/api-key-like fields. |

## Evolution Path

After this fix, the next useful expansion is durable cross-process fairness only
if multiple service processes run the same LLM lanes and measurements show
in-process priority/RPM is insufficient. That would be a separate spec and must
not smuggle in a central business queue. Another possible expansion is
provider-specific model profiles, but only after lane-level timeout/RPM metrics
show model-family-specific behavior.

## Alternatives Considered

- **Delete `pulse.pipeline` reservation.** Rejected because
  `pulse_agent_jobs.claim_due_job()` increments `attempt_count`; without a
  pre-claim capacity guard, provider saturation burns attempts and creates dead
  jobs.
- **Keep pipeline reservation and raise global concurrency.** Rejected because
  it masks double accounting and still halves effective global capacity.
- **Make Pulse one monolithic gateway stage.** Rejected because Pulse business
  semantics are explicitly two-stage (`evidence_debate`, `decision_maker`) with
  separate audits and evidence verification.
- **Central durable agent queue.** Rejected for the same reason as the hard-cut
  spec: it duplicates domain queues and creates a second truth source.
- **Only tune Narrative budgets.** Rejected because budgets reduce growth but
  do not fix no-start retry burn, Pulse double reservation, or lane policy drift.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Keep gateway as execution control plane only; keep domain state machines local; classify no-start separately from provider-started failures; inherit parent global slot for Pulse stages; run formal Narrative drain during rollout. |
| Ask first | Add durable cross-process agent execution tables; alter public Pulse write gates; change Narrative semantic quality thresholds; add News LLM fact extraction. |
| Never | Add central `agent_tasks`; write domain read models from gateway; treat provider backpressure as insufficient data; print or expose secrets/prompts/raw LLM payloads in ops surfaces. |
