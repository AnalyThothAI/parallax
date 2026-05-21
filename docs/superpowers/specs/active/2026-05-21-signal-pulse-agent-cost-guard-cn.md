# Spec - Signal Pulse Agent Cost Guard And Hybrid Model Routing

**Status**: Implemented and verified in `codex/signal-pulse-agent-cost-guard`
**Date**: 2026-05-21
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `docs/superpowers/specs/active/2026-05-18-pulse-signal-evidence-architecture-recovery-cn.md`
- `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-20-pulse-1h-4h-research-committee-cn.md`
- `docs/superpowers/plans/active/2026-05-21-signal-pulse-agent-cost-guard-plan-cn.md`

## Background

This spec is based on the operator-owned live runtime config and live PostgreSQL
data, not repository fixtures. `uv run gmgn-twitter-intel config` reported
`config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml` and
`workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`; no
secrets were printed.

Signal Pulse currently has a correctly separated Kappa/CQRS shape: the worker
reads Token Radar rows, admits agent jobs, executes bounded LLM stages, and
writes rebuildable Pulse read models. `PulseCandidateWorker.scan_triggers_once`
iterates configured `windows` and `scopes`, reads `token_radar.latest_rows`,
builds a `PulseCandidateContext`, and calls `_enqueue_if_due`:
`src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:139-201`.
`_enqueue_if_due` builds the gate and edge state, asks `PulseAdmissionPolicy`,
claims admission budget, enqueues a `pulse_agent_jobs` row, and records the
edge job:
`src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:335-418`.

Admission and execution are not one budget today. `PulseAdmissionPolicy` blocks
active jobs, unchanged state, and repeated recent failure, but immediately
admits escalation, hard-risk, and material evidence changes:
`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py:33-53`.
The repository budget counts accepted enqueue operations by candidate and target
hour bucket in `claim_pulse_admission`:
`src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_admission_repository.py:158-254`.
Once a job exists, retries are controlled by the jobs repository, not by the
admission budget. `claim_due_job` increments `attempt_count` when a pending or
failed job is claimed:
`src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py:137-208`.
`release_running_job_for_backpressure` puts the same job back to `pending`,
schedules it 30 seconds later by default, and decrements `attempt_count`:
`src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py:321-357`.

The job service inserts a `pulse_agent_runs` audit row before LLM stages run.
It builds the evidence packet, evaluates the completeness gate, constructs
runtime/audit metadata, inserts the run and deterministic pre-stage steps, and
only then either returns a deterministic abstain for hard-blocked evidence or
calls the LLM pipeline:
`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:149-279`.
When a no-start child lane backpressure exception happens after run insertion,
the service marks the run as `skipped/backpressure_*` and releases the job for
retry:
`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:530-628`.

The current Pulse agent client is a three-stage packet-only committee:
`signal_analyst`, `bear_case`, and `risk_portfolio_judge`. It always attempts
those stages in order when evidence is not hard-blocked:
`src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:181-336`.
Each stage maps to a lane through `_stage_lane` and calls
`AgentExecutionGateway.execute`:
`src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:420-542`.
Contract-stage failures such as invalid JSON, schema invalid, and refs outside
`allowed_evidence_refs` are converted to abstain decisions, but only after the
model call has already happened:
`src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:716-742`.

The execution gateway has in-memory lane circuit breakers. Provider, schema,
and timeout failures call `record_lane_failure`, which opens the lane when the
failure threshold is reached:
`src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py:372-453`.
Reservation rejects an open circuit before provider execution:
`src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py:162-178`
and
`src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py:563-565`.
This protects the provider but does not by itself prevent Pulse from claiming
and repeatedly releasing the same DB job every 30 seconds.

Write gating is intentionally strict. Claim verification failures and
deterministic eval failures become `hidden_invalid_output`:
`src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py:51-69`.
Source-quality failures become `hidden_source_quality`:
`src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py:70-78`.
The source-quality evaluator already identifies single-author, low-effective
author, high top-author-share, duplicate-text, and watched-only risk:
`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_source_quality.py:23-78`.
However, source quality is evaluated after the LLM stages in the current job
service:
`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:356-375`.

Live data on 2026-05-21, Asia/Shanghai, showed the cost/performance leak:

| Window | Runs | External model steps | Backpressure skipped runs | Hidden invalid runs |
|---|---:|---:|---:|---:|
| Last 4h | 533 | 353 | 344 | 105 |
| Last 24h | 1108 | 962 | 392 | about 357 |

The last 4h had 344 `backpressure_circuit_open` runs with 0 external steps and
0ms latency. Those are control-plane retries, not paid model calls, but they
consume worker cycles and make run health noisy. In the same 4h, all 353
external Pulse steps used `deepseek-v4-flash`. In the last 24h, rows hidden as
`hidden_invalid_output` consumed roughly 9.5M reported model tokens, while
public `display_token_watch` rows consumed roughly 230k. DeepSeek token use was
dominated by hidden/invalid or non-public work, not by visible product output.

The live runtime config default model is `qwen3.6`, but all Pulse lanes were
configured as `deepseek-v4-flash`: `pulse.pipeline`, `pulse.signal_analyst`,
`pulse.bear_case`, and `pulse.risk_portfolio_judge`. Historical rows also show
`qwen3.6` is slower and less stable for final judging: it is acceptable for free
research/shadow analysis, but should not be the only model behind public
trade/watch publication.

## Problem

Signal Pulse lacks an execution-level cost firewall between deterministic
product eligibility and paid LLM judgment. As a result, hidden, invalid,
source-quality-blocked, or provider-unavailable paths can still claim jobs,
insert runs, call paid stages, retry quickly, and only later be hidden by the
write gate. The user-visible product is protected by strict gates, but the
system pays most of its model budget on rows that never become useful public
Pulse output.

## First Principles

1. **Product truth stays PostgreSQL-first and domain-owned.** Agent execution
   may classify capacity and provider behavior, but Pulse admission, jobs, run
   audit, eval, and read-model writes stay in the Pulse domain. The existing
   worker and repositories already enforce this split:
   `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:139-201`,
   `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py:137-208`.

2. **No-start backpressure is not a business attempt.** The platform already
   models `execution_started` on `AgentExecutionError`:
   `src/gmgn_twitter_intel/platform/agent_execution.py:254-267`. If a provider
   was not called, Pulse may record pressure diagnostics, but must not burn paid
   retry budget or generate high-frequency skipped audit noise.

3. **DeepSeek is a scarce judge, Qwen is a free research worker.** Qwen3.6 can
   summarize and challenge evidence cheaply. DeepSeek should be reserved for
   final public-eligible risk/portfolio judgment. Public display quality must
   not be lowered to save cost.

4. **Deterministic gates must run before paid judgment whenever possible.**
   Evidence completeness, source quality, gate ceiling, and previous identical
   runtime/input fingerprints are known before final LLM judgment. The design
   must use those facts before spending DeepSeek.

5. **A cost optimization that changes public candidates is not acceptable.**
   The change is successful only if replay/dry-run proves public
   `display_trade_candidate` and `display_token_watch` rows are preserved, or
   any difference is explicitly explained as a bug fix.

## Goals

- **G1 - Cut DeepSeek spend without hurting public output.** In a last-24h
  dry-run report, predicted DeepSeek token use for Pulse must drop by at least
  70%, while public `display_trade_candidate` and `display_token_watch`
  candidates do not decrease.
- **G2 - Stop paid calls for non-public paths.** Rows that deterministic gates
  classify as evidence-hard-blocked, source-quality-hidden, gate-ceiling-hidden,
  or duplicate-fingerprint reuse must not call DeepSeek. They may produce a
  deterministic audit result or a Qwen-only shadow result.
- **G3 - Use Qwen3.6 for free research stages.** `pulse.signal_analyst` and
  `pulse.bear_case` must use `qwen3.6` by default. `pulse.risk_portfolio_judge`
  remains `deepseek-v4-flash` only for public-eligible final judgment.
- **G4 - Reduce backpressure audit loops.** During circuit-open or provider
  configuration/balance outage, Pulse must reduce `backpressure_circuit_open`
  run rows by at least 90% versus the current 30-second retry loop, measured by
  a focused test and live follow-up report.
- **G5 - Add fingerprint reuse.** If the same candidate, trigger signature,
  timeline signature, evidence packet hash, runtime hash, and model-route plan
  already has a terminal result inside the configured TTL, Pulse must reuse or
  suppress rather than re-run the same LLM work.
- **G6 - Separate control-plane pressure from provider failure.** Auth,
  insufficient balance, lane circuit-open, capacity-denied, and rate-limited
  no-start cases must be surfaced as provider/lane cooldown or backpressure,
  not as repeated model-output failures.
- **G7 - Make the savings observable.** Operators must be able to see Pulse
  model calls by stage/model/status, DeepSeek calls saved, Qwen calls, reused
  fingerprints, cooldown suppressions, hidden-invalid token avoided, and public
  candidate deltas in a read-only report.

## Non-goals

- Do not relax `ClaimEvidenceVerifier`, deterministic eval, write gate, source
  quality, or public display contracts to make rows publish.
- Do not replace DeepSeek entirely with Qwen for public final judgment.
- Do not introduce a central durable agent-task queue or move Pulse business
  state into the platform gateway.
- Do not change Token Radar scoring, entity identity resolution, market tick
  ingestion, or Signal Lab frontend product semantics except for optional
  diagnostics.
- Do not mutate operator-owned runtime config automatically. The implementation
  may update repository defaults and document the operator config changes.

## Target Architecture

The target architecture adds a Pulse-owned cost guard between evidence packet
construction and LLM execution:

```text
Token Radar row
  -> Pulse admission and DB job claim
  -> evidence packet + evidence completeness gate
  -> source quality + gate ceiling + fingerprint + lane health cost guard
      -> deterministic no-LLM result
      -> cached/reused result
      -> qwen3.6 research only
      -> qwen3.6 research + deepseek final judge
  -> verifier / clipper / deterministic eval / write gate
  -> pulse_candidates / run audit / ops report
```

`PulseCandidateJobService` remains the orchestrator for Pulse audit and writes.
It will still insert evidence and run audit, but it must run the cost guard
before calling the LLM pipeline. The guard returns a route decision with an
explicit reason, such as `deterministic_evidence_block`,
`source_quality_hidden`, `duplicate_fingerprint`, `provider_cooldown`,
`qwen_research_only`, or `deepseek_public_judge`.

`OpenAIAgentsPulseDecisionClient` remains the stage executor, but it must accept
a stage policy:

- `research_only`: run Qwen signal/bear stages and produce a non-public
  abstain/ignore without DeepSeek.
- `public_judge`: run Qwen signal/bear stages and DeepSeek judge.
- `no_llm`: return no stage audits beyond deterministic stages.

The platform gateway remains the provider execution boundary. It may expose
cooldown metadata and lane status, but Pulse decides how to release or suppress
domain jobs.

## Conceptual Data Flow

```text
pulse_agent_jobs
  -> claim
  -> evidence_packet
  -> CostGuardDecision
      -> no_llm finalize
      -> reuse previous terminal run
      -> qwen signal/bear
      -> deepseek risk_portfolio_judge when public-eligible
  -> eval/write_gate
  -> read model + cost report counters
```

Changed arrows:

- `evidence_packet -> LLM committee` now passes through `CostGuardDecision`.
- `circuit_open -> release job after 30s` becomes `lane/provider cooldown ->
  delayed release or pre-run suppression`.
- `hidden/source-quality/invalid rows -> DeepSeek judge` is removed unless the
  row is public-eligible and needs final judgment.

## Core Models

### `PulseCostGuardDecision`

Semantic fields:

- `action`: one of `no_llm_finalize`, `reuse_terminal_run`,
  `qwen_research_only`, `qwen_research_deepseek_judge`, `provider_cooldown`.
- `reason`: stable machine-readable reason for audit and reports.
- `public_eligible`: whether the current packet can possibly produce public
  `display_trade_candidate` or `display_token_watch`.
- `deepseek_allowed`: true only when public final judgment is needed.
- `qwen_allowed`: true when free research is useful and provider health allows
  it.
- `fingerprint`: normalized runtime/input fingerprint.
- `cooldown_until_ms`: optional lane/provider cooldown deadline.
- `audit_json`: redacted diagnostic payload safe for `trace_metadata_json`.

### `PulseRunFingerprint`

Semantic fields:

- `candidate_id`
- `trigger_signature`
- `timeline_signature`
- `evidence_packet_hash`
- `runtime_hash`
- `stage_plan_hash`
- `route`

Invariant: a terminal fingerprint may be reused only when it belongs to the
same candidate/window/scope target and the same stage plan. DeepSeek and
Qwen-only plans must not share a cache key.

### `PulseLaneCostSummary`

Semantic fields:

- `stage`
- `model`
- `status`
- `calls`
- `tokens`
- `latency_p50_ms`
- `latency_p95_ms`
- `hidden_invalid_tokens`
- `deepseek_calls_saved`
- `duplicate_suppressions`
- `cooldown_suppressions`

This is a read/report model, not business truth.

## Interface Contracts

No Signal Lab public HTTP response shape changes are required for the primary
product surface. Public candidate semantics are intentionally preserved:
`display_trade_candidate` and `display_token_watch` remain public; hidden and
invalid statuses remain hidden.

The work may add one operator-facing, read-only report surface:

- CLI/script command: generate a Signal Pulse agent cost report for a lookback
  window.
- Input: lookback hours and optional dry-run flag.
- Output: markdown/JSON with redacted config paths, run counts, stage/model
  calls, token totals, duplicate fingerprint suppressions, provider cooldown
  suppressions, predicted DeepSeek savings, and public candidate delta.
- Idempotency: read-only. Running the report multiple times must not write to
  business tables.

If `/api/ops/diagnostics` is extended, it must expose only aggregate lane
status and counters, never prompts, raw provider payloads, API keys, or DSNs.

## Acceptance Criteria

- **AC1.** WHEN the last-24h dry-run report is generated THEN the system SHALL
  show predicted DeepSeek token reduction >= 70% and public
  `display_trade_candidate` / `display_token_watch` candidate count delta >= 0.
- **AC2.** WHEN a Pulse job is evidence-hard-blocked before LLM THEN the system
  SHALL finish the run with deterministic audit stages and SHALL NOT create
  `signal_analyst`, `bear_case`, or `risk_portfolio_judge` external steps.
- **AC3.** WHEN a Pulse job fails source quality before public eligibility THEN
  the system SHALL NOT call DeepSeek and SHALL preserve hidden/public write-gate
  semantics.
- **AC4.** WHEN the same terminal fingerprint is observed inside the reuse TTL
  THEN the system SHALL suppress or reuse prior work and SHALL NOT call Qwen or
  DeepSeek again for that fingerprint.
- **AC5.** WHEN a child lane is circuit-open before provider execution THEN the
  system SHALL release or delay the job according to lane/provider cooldown and
  SHALL NOT insert high-frequency skipped run rows every 30 seconds.
- **AC6.** WHEN `pulse.signal_analyst` and `pulse.bear_case` are configured as
  `qwen3.6` and `pulse.risk_portfolio_judge` as `deepseek-v4-flash` THEN stage
  audit rows SHALL reflect those models accurately.
- **AC7.** WHEN Qwen research fails for a non-public path THEN the system SHALL
  not fallback to DeepSeek. WHEN Qwen research fails for a public-eligible path
  THEN the system MAY fallback to DeepSeek only if configured and budget allows.
- **AC8.** WHEN provider auth or insufficient-balance errors occur THEN Pulse
  SHALL enter provider/lane cooldown and SHALL NOT fan the same outage across
  many jobs as repeated paid attempts.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cost guard accidentally suppresses a real public candidate. | High | Start with dry-run report; enforce only when replay proves public trade/watch delta is non-negative. |
| Qwen research is slower and causes worker backlog. | Medium | Qwen runs only on bounded research lanes; DeepSeek judge remains gated; report p95 latency by model/stage. |
| Fingerprint reuse serves stale results after material evidence changes. | High | Include `trigger_signature`, `timeline_signature`, `evidence_packet_hash`, `runtime_hash`, and `stage_plan_hash` in the fingerprint. |
| Provider cooldown hides genuine recovery. | Medium | Cooldown uses bounded TTL and is reset by successful started calls; ops report shows active cooldown reasons. |
| Moving source quality before LLM changes hidden audit text. | Medium | Preserve write-gate statuses; only skip expensive stages when public outcome is already impossible. |
| Adding platform cooldown storage violates domain ownership. | Medium | Prefer Pulse-owned release/cooldown decisions using gateway status; if storage is needed, store only operational lane health, not business jobs. |

## Evolution Path

After this change, the next useful expansion is per-domain model-budget policy:
daily DeepSeek call caps, priority overrides for watchlist assets, and explicit
SLO alerts for hidden-invalid token waste. The design should not foreclose
future offline evaluation, but it must not require a central agent-task queue.

## Alternatives Considered

- **Config-only lane switch**: change `signal_analyst` and `bear_case` to
  Qwen3.6 in `workers.yaml`. Rejected as insufficient because it does not stop
  repeated backpressure rows, duplicate fingerprints, or DeepSeek judge calls
  on non-public paths.

- **All-Qwen Pulse**: run every stage on Qwen3.6. Rejected because live data
  shows Qwen is slower and less reliable for final judgment; product quality
  would likely suffer.

- **Disable Pulse agent until provider recovers**: cheapest short-term answer,
  but rejected because it stops useful public candidates and does not fix the
  architecture.

- **Central durable agent queue**: rejected because it violates the existing
  project boundary that domains own admission, retries, and business writes.

- **Prompt-only invalid-output fix**: rejected because `hidden_invalid_output`
  is only one symptom. The larger issue is paid calls happening after the system
  already has enough deterministic information to know the row will not publish.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve public write-gate semantics, evidence verification, and Pulse single-writer ownership. |
| Always | Use Qwen3.6 for cheap research where product risk is low; reserve DeepSeek for public-eligible final judgment. |
| Always | Produce dry-run evidence before enabling enforcement. |
| Ask first | Changing operator-owned `~/.gmgn-twitter-intel/workers.yaml` values. |
| Ask first | Introducing persistent platform-level lane cooldown storage if Pulse-owned cooldown release is not enough. |
| Never | Print secrets, DSNs with passwords, prompts containing sensitive payloads, or raw API keys in reports. |
| Never | Relax eval/write gates to reduce invalid output counts. |
| Never | Route hidden/non-public rows through DeepSeek just to produce nicer hidden summaries. |
