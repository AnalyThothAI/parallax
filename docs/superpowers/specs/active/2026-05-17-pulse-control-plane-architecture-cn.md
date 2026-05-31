# Signal Pulse KISS Control Plane Spec

**Status**: Revised KISS draft
**Date**: 2026-05-17
**Owner**: Codex with Qinghuan
**Scope**: Replace the broad Route B design with the smallest control-plane slice that fixes the real failure modes found in code review: noisy external pushes, cross-window/scope agent amplification, non-atomic admission, failed-run loops, and legacy public compatibility drift.

**References**:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `src/parallax/domains/pulse_lab/ARCHITECTURE.md`
- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/parallax/domains/notifications/services/notification_rules.py`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/agents_sdk/agent_improvement_loop.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/How_to_use_guardrails.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/evaluation/use-cases/structured-outputs-evaluation.ipynb`

---

## Decision

Keep the current Kappa/CQRS architecture and the existing workers. Add a small deterministic control layer in the existing Pulse worker and notification rule engine:

```text
Token Radar row
  -> edge diff
  -> materiality policy
  -> atomic target+candidate admission
  -> existing two-stage agent
  -> candidate read model
  -> in-app notification row
  -> stricter external push eligibility
```

No new worker. No new notification-intents table. No frontend throttling. No parallel specialist agents. No broad UI redesign.

---

## Current Facts

Read-only runtime diagnostics used the operator-owned config:

- `config_path`: `/Users/qinghuan/.parallax/config.yaml`
- `workers_config_path`: `/Users/qinghuan/.parallax/workers.yaml`

Safe observed facts:

- Pulse scans `5m`, `1h`, `4h`, `24h` across `all` and `matched`.
- Signal Pulse notifications are configured for `in_app` and `pushdeer`.
- Operator config still contains unsupported `theme_watch`.
- `signal_pulse_candidate.cooldown_seconds = 900` exists but Signal Pulse external push does not use it.
- 24h diagnostics showed `5m/all` dominates Pulse agent runs, and a single target can fan out across multiple candidate ids.

Code review found four core problems:

1. `_enqueue_if_due` marks an edge as processed when the job is enqueued, not when the agent run succeeds. A dead job can make the same edge disappear forever.
2. Admission writes are not atomic. Observation, budget claim, enqueue, and edge update are separate repository calls.
3. Budget is candidate/hour only. Because candidate ids include `window` and `scope`, one target can multiply across candidate ids.
4. Signal Pulse uses one notification signature and one channel set for both in-app and PushDeer. External push inherits in-app churn and ignores cooldown.

---

## Goals

- Bound agent work at the target level without changing the worker topology.
- Preserve in-app Signal Pulse history while making PushDeer escalation/cooldown gated.
- Never consume budget without a durable job.
- Never mark an edge processed until the agent path has reached a terminal result.
- Remove public legacy stage compatibility from the v2 surface; historical DB rows may remain for audit.
- Make failure loops visible and bounded without adding a new failure table.

## Non-Goals

- Do not redesign Signal Lab or Notification Drawer.
- Do not add `notification_intents`.
- Do not split Signal Pulse into multiple notification rules.
- Do not replace `Investigator -> DecisionMaker`.
- Do not introduce a 24h target budget in the first pass; hourly target budget is enough to prove the control point.
- Do not build a general alert-manager abstraction.

---

## KISS Architecture

### 1. Pulse Admission Policy

Add one small service:

```python
PulseAdmissionPolicy.classify(previous_state, current_state, existing_job) -> PulseAdmissionDecision
```

The decision has only:

```text
action: suppress | enqueue_agent
reason: unchanged | active_job | retryable_failed_job | score_band_pending | material_edge | escalation
edge_events: list[str]
```

Rules:

- unchanged state suppresses.
- active `pending` / `running` / retryable `failed` job suppresses.
- upward `pulse_status_changed` or upward `recommended_decision_changed` enqueues.
- first displayable observation enqueues.
- `score_band_crossed` alone is pending until seen twice consecutively.
- `hard_risk_added` enqueues for read-model accuracy, but does not by itself make PushDeer eligible.

This service should live beside `pulse_edge_events.py`. It should not call the DB or the LLM.

### 2. Atomic Admission Repository Method

Add one repository method:

```python
claim_pulse_admission(
    *,
    candidate_id: str,
    target_type: str,
    target_id: str,
    hour_bucket_ms: int,
    now_ms: int,
    target_limit: int,
    candidate_limit: int,
    job_payload: dict[str, Any],
    edge_state: dict[str, Any],
    edge_events: list[str],
) -> PulseAdmissionClaim
```

`job_payload` is a typed dict in implementation, but it should contain only the existing `enqueue_job` inputs. Do not invent a second job abstraction.

It must run in one DB transaction and either:

- records the observation,
- claims target/hour budget,
- claims candidate/hour budget,
- enqueues the job,
- records `last_job_id` and `last_edge_events_json`,
- returns accepted,

or:

- records the observation and suppression reason,
- increments no budget counter,
- creates no job,
- returns rejected.

The method must not write `last_processed_state_json`. That field is updated only after the agent run succeeds or after a deterministic hard-block result is persisted.

Required new table:

```sql
CREATE TABLE pulse_target_run_budget (
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  hour_bucket_ms BIGINT NOT NULL,
  enqueue_count BIGINT NOT NULL DEFAULT 0,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY(target_type, target_id, hour_bucket_ms)
);
```

Required `pulse_candidate_edge_state` additions:

```sql
last_suppressed_reason TEXT,
last_suppressed_at_ms BIGINT,
pending_score_band TEXT,
pending_score_band_count BIGINT NOT NULL DEFAULT 0
```

### 3. Edge Processing Semantics

Current behavior:

```text
edge diff -> enqueue -> mark processed
```

New behavior:

```text
edge diff -> admit -> enqueue -> mark admitted
agent success -> mark processed
agent terminal failure -> keep previous processed state
```

If a job dies after max attempts, the same current edge remains eligible for re-admission after budget/circuit-breaker policy allows it. This is intentional: failed work should not erase the edge.

### 4. External Push Policy

Keep one `signal_pulse_candidate` rule, but produce two signatures:

```text
in_app_signature:
  candidate_id
  pulse_status
  score_band
  decision route/recommendation
  stable playbook shape
  gate max decision

external_push_signature:
  target_type
  target_id
  alert_class
  status_escalation_level
  recommendation_escalation_level
  cooldown_bucket
  pulse_version
  gate_version
```

`NotificationCandidate.payload` must include:

```json
{
  "notification_signature": "sha256:...",
  "in_app_signature": "sha256:...",
  "external_push_signature": "sha256:... or null",
  "external_push_eligible": true,
  "external_push_suppression_reason": null
}
```

Row identity for Signal Pulse becomes:

```text
rule_id + in_app_signature + (external_push_signature or "in_app")
```

This avoids a new table while allowing:

- in-app material history,
- one PushDeer per target/alert/cooldown bucket,
- no PushDeer for score-band-only churn,
- no PushDeer duplication across `all` and `matched`.

Channel policy:

- If `external_push_eligible = false`, strip all non-`in_app` channels before insertion.
- If `external_push_eligible = true`, keep configured channels.
- External eligibility requires high/critical severity, resolved target, escalation, and cooldown bucket not already represented by the external signature.

`risk_rejected_high_info` is in-app only unless a later explicit product decision says otherwise.

### 5. Failure Loop Control

No new failure table.

Normalize failures into a small code stored in:

- `pulse_agent_runs.trace_metadata_json.failure_reason`
- `pulse_agent_jobs.last_error`

Initial codes:

```text
schema_validation_failed
unknown_evidence_id
tool_budget_exceeded
timeout
provider_rate_limited
provider_unavailable
stale_running_timeout
unexpected_exception
```

Before admission, suppress non-escalation work if the same target has at least 3 failures in the current hour for:

- `schema_validation_failed`
- `unknown_evidence_id`

Escalations bypass the failure circuit breaker but still consume target/candidate budget.

Failed runs should create deterministic eval cases with:

- context,
- failed stage audits,
- normalized failure reason,
- expected outcome: `fail`.

### 6. Harness Manifest

The harness hash must move when operationally meaningful harness behavior moves. Extend the manifest with:

- stage names,
- actual `max_turns_per_stage`,
- tool names by stage,
- route tool budgets,
- safety-net enabled flag,
- validators enabled,
- deterministic grader version,
- failure taxonomy version.

Do not add model-specific prompt caching logic in this pass. Only persist usage if the SDK provides it.

### 7. Public Contract Cleanup

`analyst`, `critic`, and `judge` are historical DB stage names, not v2 public contract.

Required cleanup:

- Remove them from `SignalPulseStages` API schema.
- Remove them from the frontend `SignalPulseStages` type and detail rail view model.
- Remove placeholder UI copy for old three-stage runs.
- Keep DB rows queryable through repository/debug tooling; do not expose them as first-class public fields.
- Public runtime and frontend stage surfaces enumerate only `investigator`, `decision_maker`, and `research_only_gate`.

`theme_watch` must not be accepted for Signal Pulse notification execution. The KISS path is:

1. Clean the operator config before the next live run.
2. Keep config validation in `NotificationsConfig.parse_rules` so unsupported Signal Pulse statuses fail fast during parsing.

---

## Rollout

### Phase 1: Quiet PushDeer

Implement external push policy in `NotificationRuleEngine` and `NotificationRepository`.

Success:

- Signal Pulse `cooldown_seconds` is used for external push.
- PushDeer uses target/cooldown signature.
- Score-band-only churn never PushDeer.
- In-app rows still appear for material Signal Pulse changes.

### Phase 2: Bound Agent Admission

Implement `PulseAdmissionPolicy`, `pulse_target_run_budget`, and atomic `claim_pulse_admission`.

Success:

- No budget is consumed without a job.
- Failed jobs do not erase the edge.
- One target cannot fan out across 4 windows x 2 scopes inside the same hour.

### Phase 3: Stop Failure Loops

Add normalized failure reasons, target/hour failure circuit breaker, and failed-run eval cases.

Success:

- Validation/evidence loops are bounded to 3 per target/hour.
- Failed runs are queryable by normalized reason.
- Eval data includes both success and failure paths.

### Phase 4: Remove Public Legacy Stage Compatibility

Remove public `analyst` / `critic` / `judge` fields and frontend placeholders.

Success:

- v2 public contract only exposes `investigator`, `decision_maker`, and `research_only_gate`.
- Historical DB rows remain queryable but no longer shape runtime/frontend logic.

---

## Acceptance Metrics

Measured after 48h and again after 7d:

| Metric | Target |
|---|---:|
| Signal Pulse PushDeer duplicate for same target/alert/cooldown bucket | 0 |
| Signal Pulse PushDeer from score-band-only churn | 0 |
| Candidate 24h agent run p95 | <= 5 |
| Single target 24h agent runs | <= 12 |
| `5m/all` share of Pulse agent runs | < 50% |
| Budget consumed without job | 0 |
| Dead job causing edge disappearance | 0 repro cases |
| Validation/evidence failure loops per target/hour | <= 3 |
| `theme_watch` accepted in Signal Pulse config | 0 |
| Public `analyst` / `critic` / `judge` stage fields | 0 |

---

## Required Tests

Unit:

- `PulseAdmissionPolicy` suppresses unchanged state.
- `PulseAdmissionPolicy` keeps score-band-only churn pending until confirmed twice.
- upward status/recommendation escalation enqueues immediately.
- atomic admission rejects target budget without consuming candidate budget.
- atomic admission rejects candidate budget without consuming target budget.
- failed job does not update `last_processed_state_json`.
- successful run updates `last_processed_state_json`.
- external push signature ignores bull/bear/playbook microchanges.
- Signal Pulse cooldown suppresses PushDeer but keeps in-app.
- unsupported Signal Pulse status raises config validation error.

Integration:

- `PulseCandidateWorker.scan_triggers_once` admits only one target/hour when the same target appears in multiple window/scope rows.
- `NotificationWorker.process_once` inserts in-app row without delivery when `external_push_eligible=false`.
- `NotificationWorker.process_once` enqueues PushDeer exactly once for the same target/alert/cooldown bucket.
- repeated `unknown_evidence_id` failures trigger failure circuit breaker.
- failed run creates deterministic eval case.

Contract/frontend:

- OpenAPI/frontend types expose only v2 stage names.
- Pulse detail renders v2 stage and decision surface without legacy placeholder cards.

---

## Implementation Plan

Use: `docs/superpowers/plans/active/2026-05-17-pulse-control-plane-kiss-plan-cn.md`.
