# Spec — Agent Worker Backlog And Pulse Publication Root Fix

**Status**: Implemented
**Date**: 2026-05-19
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/superpowers/plans/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-18-token-narrative-intelligence-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-18-pulse-agent-runtime-hard-cut-cn.md`

## Background

Live runtime config is operator-owned under `~/.parallax/`; repo fixtures and `.env` are not active production truth. This spec therefore treats live backlog observations as runtime symptoms and fixes the worker contracts in source.

Narrative semantics has three expensive steps in one worker pass: reconcile Token Radar admissions, enqueue missing `token_mention_semantics`, then claim due semantic rows for provider labeling. Provider calls were already capped by `provider_batch_size`, but admission enqueueing needed its own budget so source growth cannot outrun labeling capacity indefinitely.

Signal Pulse list/detail intentionally exposes public display rows only. Hidden `hold_publish` rows are audit state, not public product state. The panel can therefore look stale while workers are active if public readiness is not surfaced separately from hidden candidate activity.

Pulse agent jobs also need local pressure control and deterministic repair before validation. Without bounded enqueueing, stale job cleanup, evidence ref canonicalization, and narrow schema normalization, the system can spend provider budget on avoidable retries instead of fresh high-value candidates.

## Problem

The user-visible issue is not simply "frontend says narrative is insufficient." The system had two coupled pressure points:

- Narrative could admit more semantic rows than the provider can label, so `queued` and `retryable_error` rows accumulate and digests remain pending.
- Pulse could keep writing hidden audit/candidate rows while public publication is held by health gates, so the panel looks stale even though the worker is active.

Both failures share the same root shape: agent-heavy workers need bounded admission, bounded retry, deterministic validation repair, compact-enough payloads, and honest read-model status.

## First Principles

1. **Postgres facts remain truth.** Kappa/CQRS material facts and derived read models remain the business source of truth; frontend and API must not infer hidden state by issuing raw ad hoc queries.
2. **Budget before retry.** Reducing low-value admission and per-target queue growth is cheaper than allowing large retry queues to saturate provider calls.
3. **Public Pulse is stricter than hidden audit.** `hidden_hold_publish` remains a safety gate; the fix is to reduce avoidable failures and expose why public rows are absent, not to publish hidden rows.
4. **Repair only deterministic agent output defects.** Schema/ref normalization is allowed only when the packet makes the correction unambiguous; evidence verification remains authoritative.

## Goals

- G1. Narrative semantics enqueue growth is bounded per worker cycle and per target.
- G2. Narrative worker notes expose how many source mentions were enqueued, suppressed by budget, and already pending.
- G3. Token Radar / Token Case can distinguish `pending semantic_labeling_pending` from true insufficient narrative data.
- G4. Signal Pulse health distinguishes total candidates from public-ready candidates.
- G5. Signal Pulse UI can explain `hold_publish` / hidden-only states without showing hidden candidate rows.
- G6. Pulse candidate job growth is bounded per worker cycle, globally, and per window/scope.
- G7. Pulse stale short-window jobs are terminalized so expired work does not keep blocking new work.
- G8. Pulse agent output gets deterministic ref/schema normalization before final validation and records repair metadata.
- G9. No new table or cross-domain platform budget is introduced in this root-fix slice.

## Non-goals

- Do not display `hidden_hold_publish` candidates in the public Pulse list.
- Do not relax Pulse evidence verification or claim validation.
- Do not add a central `agent_runtime_budget` config in this slice.
- Do not add a new Narrative job table; reuse `token_mention_semantics` as the bounded semantic queue.
- Do not auto-reopen terminal `semantic_unavailable` rows without an explicit ops recovery command.
- Do not change sealed Pulse packet hashes when future payload slimming is added.

## Target Architecture

### Narrative Admission Budget

Narrative keeps its existing domain boundary. `MentionSemanticsWorker` performs admission reconciliation, then applies two local gates before `enqueue_missing_mention_semantics`:

- `max_semantic_rows_enqueued_per_cycle`
- `max_pending_semantics_per_target`

These live in `MentionSemanticsWorkerSettings`, not platform-level LLM config. The repository owns the pending count query, and the worker consumes a domain method. Provider claim cap remains `min(batch_size, provider_batch_size)`.

### Narrative Backlog Health

Narrative exposes an authenticated operational health endpoint, `GET /api/status/narrative-health`, backed by a domain query. The public digest payload may include `processing.backlog` so UI/data-gap logic can separate semantic backlog from true source insufficiency.

### Pulse Public Readiness

Pulse keeps the existing public-only read contract. `PulseReadRepository.pulse_summary()` returns total candidates and public/displayable candidate count. `SignalPulseService.health` computes:

- `candidate_count`: all candidate rows in the query surface
- `public_candidate_count`: rows eligible for public list/detail
- `pulse_ready` / `public_ready`: true only when public candidate count is positive
- existing `publish_status`, `reasons`, and hidden/public counters

### Pulse Worker Budget And TTL

`PulseCandidateWorker` applies worker-local caps before enqueueing agent jobs:

- `max_enqueues_per_cycle`
- `max_pending_jobs_global`
- `max_pending_jobs_per_window_scope`
- `stale_job_ttl_by_window_seconds`

The repository owns pending-count and stale-terminalization queries. Defaults keep short-window work fresh without adding a new global LLM scheduler.

### Pulse Agent Output Normalization

Pulse final decision output is normalized before strict model validation:

- evidence refs are canonicalized only when a same-packet unique correction exists;
- narrow schema aliases are repaired into the expected model shape;
- repair/rejection metadata is attached to stage audit output;
- evidence verification remains the final trust boundary.

## Conceptual Data Flow

```text
Token Radar rows
  -> narrative admissions
  -> worker-local admission budget
  -> token_mention_semantics
  -> provider labeling
  -> token_discussion_digests
  -> digest data gaps and narrative-health
  -> Token Radar / Token Case visible status

Pulse evidence packet
  -> worker-local enqueue budget and stale TTL cleanup
  -> agent job
  -> deterministic output normalization
  -> evidence verifier
  -> hidden/public write gate
  -> Pulse freshness health
  -> SignalPulseService health
  -> Signal Lab visible status
```

## Core Models

- `Narrative semantic admission budget`: worker-local settings controlling how many semantic rows can be newly enqueued per cycle and how many pending semantic rows a target may carry.
- `Semantic suppressed budget`: worker note count for source mentions intentionally not enqueued because the target or cycle budget is exhausted.
- `Narrative backlog health`: authenticated operational status for queued/retryable/stale semantic work and digest backlog.
- `Public candidate count`: Pulse health count for rows that are displayable and have a packet hash; this is distinct from total candidate rows, which may include hidden rows.
- `Pulse enqueue budget`: worker-local caps that prevent public/hidden candidate job growth from exploding.
- `Pulse stale job TTL`: deterministic terminalization of expired active jobs by candidate window.
- `Pulse agent output normalization`: deterministic repair metadata applied before strict validation, without weakening evidence verification.

## Interface Contracts

### Worker Settings

`mention_semantics` gains:

- `max_semantic_rows_enqueued_per_cycle`
- `max_pending_semantics_per_target`

`pulse_candidate` gains:

- `max_enqueues_per_cycle`
- `max_pending_jobs_global`
- `max_pending_jobs_per_window_scope`
- `stale_job_ttl_by_window_seconds`

All budget values are positive integers and operator-tunable in `workers.yaml`.

### Worker Notes

`mention_semantics` notes include:

- `admission_semantic_suppressed_budget`
- `admission_semantic_pending_before`
- `admission_semantic_pending_cap_hits`

`pulse_candidate` notes include enqueue suppression and stale terminalization counts for operational diagnosis.

### HTTP / Frontend

`SignalPulseHealth` gains optional:

- `public_ready`
- `public_candidate_count`
- `latest_hidden_hold_candidate_updated_at_ms`

`GET /api/status/narrative-health` returns authenticated Narrative backlog/readiness health.

Digest payloads may include `processing.backlog` so frontend gap copy can avoid calling pending semantic work "insufficient narrative."

## Acceptance Criteria

- AC1. WHEN one Narrative target already has pending semantics and the worker sees more source mentions than its target/cycle budget allows, THEN the worker SHALL enqueue only the allowed rows and report suppressed rows in notes.
- AC2. WHEN `mention_semantics` default worker settings are loaded, THEN they SHALL include the new budget defaults.
- AC3. WHEN Pulse has hidden candidates but no public candidates, THEN `SignalPulseService.health.pulse_ready` and `public_ready` SHALL be false while `candidate_count` still reports total candidates.
- AC4. WHEN Signal Pulse is `hold_publish`, THEN the workbench SHALL render the hold/degraded explanation from `health.publish_status` and `health.reasons`.
- AC5. WHEN Pulse has hidden rows, THEN public list/detail SHALL still omit them.
- AC6. WHEN Pulse active jobs exceed global or window/scope caps, THEN the worker SHALL suppress new enqueueing and report the suppression instead of creating more jobs.
- AC7. WHEN Pulse short-window jobs are stale beyond configured TTL, THEN the repository SHALL terminalize them before/after the cycle.
- AC8. WHEN Pulse agent output contains uniquely repairable evidence ref/schema defects, THEN normalization SHALL repair them and preserve audit metadata before validation.
- AC9. WHEN Narrative backlog exists, THEN authenticated status and digest processing metadata SHALL expose pending/retryable state separately from source insufficiency.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Budget too low starves cold windows | Medium | Keep settings operator-tunable and report suppressed counts. |
| Pending cap ignores useful fresh posts | Medium | Use hot Token Radar admission ordering before budget application. |
| Pulse `candidate_count` semantics confuse UI | Medium | Add explicit `public_candidate_count` and `public_ready`. |
| Hidden Pulse rows leak into public surface | High | Keep `displayable_only=True` and `_is_displayable` filtering unchanged. |
| Ref canonicalization repairs an ambiguous output | High | Only repair unique same-packet matches; preserve verifier rejection otherwise. |
| Stale TTL terminalizes slow but still useful jobs | Medium | TTL is window-scoped and operator-tunable; default only targets `5m`. |

## Evolution Path

Implemented in this slice:

- Narrative admission budget and backlog-aware digest/status surfaces.
- Pulse public readiness health and Signal Lab hold/degraded banner.
- Pulse candidate enqueue caps, pending-count repository methods, and stale job TTL cleanup.
- Pulse deterministic final-output normalization with audit metadata.

Remaining follow-ups:

- compact Pulse agent input view without changing sealed packet hashes;
- explicit ops recovery command for old retryable/terminal Narrative semantic rows;
- only after stable worker-local metrics, reconsider a platform-level LLM budget.

## Alternatives Considered

- Central `agent_runtime_budget` now — rejected because the platform LLM gateway does not know target/window/scope, Pulse health gates, or Narrative admission priority.
- New Narrative job table — rejected because `token_mention_semantics` already carries queue status, retry count, and terminal state.
- Show Pulse hidden rows in UI — rejected because it violates the public write gate and notification contract.
- Only reduce provider batch size — rejected because it lowers timeout risk but does not bound admission growth.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Bound Narrative semantic admission before enqueueing rows. |
| Always | Keep Pulse public list/detail displayable-only. |
| Always | Surface public readiness separately from total hidden/public candidate count. |
| Always | Normalize only deterministic Pulse agent output defects and keep verifier authority. |
| Always | Terminalize stale Pulse jobs by configured window TTL. |
| Ask first | Reopen terminal semantic rows or backfill old retryable rows. |
| Ask first | Promote worker budgets into LLMGateway-level policy. |
| Never | Publish hidden Pulse rows to make the panel look fresh. |
