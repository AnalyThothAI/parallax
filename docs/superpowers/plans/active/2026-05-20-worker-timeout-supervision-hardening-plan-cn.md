# Worker Timeout Supervision Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-20
**Owning spec:** Inline user-approved audit direction from the 2026-05-20 worker timeout supervision review thread; no separate spec artifact exists yet.
**Worktree:** `.worktrees/worker-timeout-supervision-hardening/`
**Branch:** `codex/worker-timeout-supervision-hardening`

**Goal:** Make worker timeout semantics explicit and production-safe so blocked provider, DB, or agent calls cannot silently pin a worker slot while preserving PostgreSQL-first retry/audit correctness.

**Architecture:** Split ambiguous worker timeout behavior into soft observation, cooperative hard cancellation, and durable domain cleanup. `WorkerBase` owns task age, timeout state, cancellation, and status telemetry; domain workers own claim/lease/audit recovery when cancellation interrupts their state machines. Agent stage timeouts remain owned by `AgentExecutionGateway`, but supervisor cancellation becomes an auditable cancellation path instead of a lost `CancelledError`.

**Tech Stack:** Python 3.13, asyncio, psycopg3, PostgreSQL, OpenAI Agents SDK through `AgentExecutionGateway`, Pydantic v2, pytest, ruff, FastAPI status schemas.

---

## Scope

- In:
  - `WorkerBase` timeout semantics, active-task age, soft-timeout reporting, cooperative hard cancellation, and status payload fields.
  - Agent gateway cancellation audit metadata for supervisor-driven cancellation.
  - Pulse job cancellation cleanup for claimed `pulse_agent_jobs` and `pulse_agent_runs`.
  - Narrative mention semantics and discussion digest cancellation cleanup.
  - Worker settings defaults and architecture guards preventing zero total timeouts on non-continuous agent workers.
  - Docs for worker lifecycle, reliability, and industrial timeout layering.
- Out:
  - Replacing the runtime with Celery, Temporal, or a durable external worker engine.
  - Introducing a central durable agent queue.
  - Changing Token Radar scoring, Pulse write-gate policy, or narrative product semantics unrelated to timeout/cancellation.
  - Killing Python threads directly; uncancellable sync work is handled by DB statement timeouts and process-level liveness escalation.

## Current Evidence

- `WorkerBase` currently waits with `asyncio.wait_for(asyncio.shield(task), timeout=...)`, so soft timeout does not cancel the underlying `run_once` task.
- `WorkerBase.run()` refreshes `last_started_at_ms` before each wait attempt, even when it is still waiting for the same old `run_once_task`.
- `tests/unit/test_worker_base_runtime.py::test_worker_base_timeout_does_not_start_overlapping_run_once` encodes the current soft-timeout/no-overlap behavior.
- `tests/unit/test_worker_settings.py` currently asserts `mention_semantics.timeout_seconds == 0`, `token_discussion_digest.timeout_seconds == 0`, and `pulse_candidate.timeout_seconds == 0`.
- `PulseCandidateJobService.run_job()` catches `Exception`, not `asyncio.CancelledError`; supervisor cancellation would bypass its failure cleanup.
- `MentionSemanticsWorker` and `TokenDiscussionDigestWorker` also catch `Exception` around provider calls, not `asyncio.CancelledError`.
- `AgentExecutionGateway.execute()` records lane timeout when its own `wait_for` expires, but supervisor cancellation from outside is not converted into a result audit.

## Target Timeout Model

Use three distinct concepts:

| Concept | Owner | Meaning | Expected effect |
|---|---|---|---|
| Soft timeout | `WorkerBase` | A `run_once` has exceeded expected duration. | Mark one overrun event, expose active age, keep waiting unless hard timeout is configured. |
| Hard timeout | `WorkerBase` + domain worker | The `run_once` must stop cooperatively. | Cancel task, wait for cleanup, discard task, return to backoff without overlapping a new task. |
| Stage timeout | `AgentExecutionGateway` or local provider wrapper | A provider/agent stage exceeded its execution budget. | Return typed provider timeout and let domain retry/audit policy run. |

`timeout_seconds` is renamed at the settings boundary:

```python
soft_timeout_seconds: float = Field(default=120.0, ge=0)
hard_timeout_seconds: float = Field(default=0.0, ge=0)
```

The only workers allowed to keep `hard_timeout_seconds == 0` are continuous stream workers with their own watchdog or provider-disconnect lifecycle. The initial allowlist is `collector` only unless implementation evidence proves another worker is truly continuous and cancellable through a bounded cycle.

## Pre-flight

- [ ] Read this plan completely.
- [ ] Create an isolated worktree:
  ```bash
  git worktree add .worktrees/worker-timeout-supervision-hardening -b codex/worker-timeout-supervision-hardening main
  cd .worktrees/worker-timeout-supervision-hardening
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/worker-timeout-supervision-hardening`; expected status: clean.
- [ ] Confirm live config paths before any real-data check:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Report paths and redacted booleans only.
- [ ] Capture current worker timeout baseline:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_settings.py -q
  ```
  Expected before implementation: current tests pass and still encode the old soft-timeout semantics.
- [ ] Capture architecture baseline:
  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_agent_execution_plane_contracts.py -q
  ```

## File Structure

### Runtime Core

- Modify `src/parallax/app/runtime/worker_base.py`
  - Add explicit active-task fields:
    ```python
    self.active_run_once_started_at_ms: int | None = None
    self.active_run_once_soft_timed_out_at_ms: int | None = None
    self.active_run_once_hard_timed_out_at_ms: int | None = None
    self._soft_timeout_reported_for_task: set[int] = set()
    ```
  - Add `WorkerRunSoftTimeout` and `WorkerRunHardTimeout` exception classes local to this module.
  - Add properties `soft_timeout_seconds` and `hard_timeout_seconds`.
  - Update `WorkerStatus` to include:
    ```python
    active_run_once_started_at_ms: int | None
    active_run_once_age_ms: int | None
    active_run_once_soft_timed_out_at_ms: int | None
    active_run_once_hard_timed_out_at_ms: int | None
    active_run_once_count: int
    ```
  - Ensure `last_started_at_ms` changes only when a new `run_once` task is created.
  - Ensure soft timeout is recorded once per task, not once per wait loop.
  - Ensure hard timeout cancels and gathers the current task before a new task can be created.

- Modify `src/parallax/app/runtime/worker_scheduler.py`
  - Treat hard-timeout status as a liveness failure in `unhealthy_reasons()`.
  - Keep readiness-style soft timeout as degraded health without stopping the scheduler task.

- Modify `src/parallax/app/surfaces/api/schemas.py`
  - Add the new worker status fields to `WorkerStatusData` if the schema is explicit.

### Settings

- Modify `src/parallax/platform/config/settings.py`
  - Replace `PerWorkerSettings.timeout_seconds` with `soft_timeout_seconds` and `hard_timeout_seconds`.
  - Update default `workers.yaml` output.
  - Set finite defaults:
    ```yaml
    narrative_admission:
      soft_timeout_seconds: 180.0
      hard_timeout_seconds: 300.0
    mention_semantics:
      soft_timeout_seconds: 240.0
      hard_timeout_seconds: 300.0
    token_discussion_digest:
      soft_timeout_seconds: 570.0
      hard_timeout_seconds: 660.0
    pulse_candidate:
      soft_timeout_seconds: 540.0
      hard_timeout_seconds: 660.0
    ```
  - Keep `collector` with `soft_timeout_seconds: 0.0` and `hard_timeout_seconds: 0.0`.
  - For existing non-agent workers, set `soft_timeout_seconds` to the previous `timeout_seconds` default and `hard_timeout_seconds` to `soft_timeout_seconds + 60` unless a worker already has a tighter provider/lease deadline.

### Agent Execution

- Modify `src/parallax/platform/agent_execution.py`
  - Add a cancellation-specific error class:
    ```python
    CANCELLED = "cancelled"
    ```
  - Add `AgentExecutionCancelled(asyncio.CancelledError)` carrying the gateway audit:
    ```python
    class AgentExecutionCancelled(asyncio.CancelledError):
        def __init__(self, message: str, *, audit: AgentExecutionResultAudit | None, execution_started: bool) -> None:
            super().__init__(message)
            self.audit = audit
            self.execution_started = bool(execution_started)
    ```

- Modify `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
  - Add `except asyncio.CancelledError` in `execute()` before `except Exception`.
  - Build failed audit with `error_class=AgentExecutionErrorClass.CANCELLED`.
  - Record execution telemetry.
  - Release provider-running and reservation counters in `finally`.
  - Raise `AgentExecutionCancelled(...)` so cancellation still propagates as cancellation.

### Pulse Domain Cleanup

- Modify `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py`
  - Add:
    ```python
    def mark_job_cancelled_by_worker_timeout(
        self,
        job: dict[str, Any],
        *,
        now_ms: int,
        execution_started: bool,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        ...
    ```
  - If `execution_started` is false, set job back to `pending`, decrement the claim attempt with `GREATEST(0, attempt_count - 1)`, set a short retry delay, and store `last_error='worker_timeout_before_execution'`.
  - If `execution_started` is true, set job to `failed` or `dead` using the existing attempt/max-attempt rule and store `last_error='worker_timeout_after_execution'`.

- Modify `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
  - Catch `asyncio.CancelledError` separately.
  - If `run_started` is true and a `pulse_agent_runs` row exists, finish it as `status='failed'`, `outcome='worker_timeout'`, and trace metadata `{"failure_reason": "worker_timeout_cancelled"}`.
  - Call `mark_job_cancelled_by_worker_timeout(...)`.
  - Re-raise the cancellation.
  - Wrap the pipeline call with the configured `pulse.pipeline` stage timeout if no outer pipeline wait is currently enforced:
    ```python
    result = await asyncio.wait_for(
        self.decision_client.run_decision_pipeline(...),
        timeout=self._pipeline_timeout_seconds(),
    )
    ```

- Modify `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Reduce the blast radius of hard cancellation by adding a process-job budget:
    ```python
    max_agent_jobs_per_cycle: int = max(1, int(getattr(self.settings, "max_agent_jobs_per_cycle", 2) or 2))
    ```
  - Use `min(self.batch_size, self.max_agent_jobs_per_cycle)` for `process_due_jobs_once_async()`.
  - Keep trigger scanning budget separate from agent job execution budget.

### Narrative Domain Cleanup

- Modify `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
  - Catch `asyncio.CancelledError` around `self.provider.label_mentions(...)`.
  - Record a failed `narrative_model_runs` row with `status='failed'`, `error='worker_timeout_cancelled'`, and trace metadata including `error_type='CancelledError'`.
  - Complete the claimed semantic rows as retryable failures with `next_retry_at_ms = now + provider_failure_backoff_seconds`.
  - Re-raise the cancellation.

- Modify `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - Catch `asyncio.CancelledError` around `self.provider.summarize_discussion(...)`.
  - Record a failed `narrative_model_runs` row with `error='worker_timeout_cancelled'`.
  - Mark the target admission `next_digest_due_at_ms` using provider failure backoff so it does not hot-loop immediately.
  - Re-raise the cancellation.

- Modify `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`
  - Reuse existing completion methods when possible.
  - Add only narrow helper methods if an existing method cannot express cancellation without pretending it was a provider schema failure.

### Tests

- Modify `tests/unit/test_worker_base_runtime.py`
  - Replace the current “timeout keeps waiting old task and eventually succeeds” assertion with explicit soft-timeout behavior.
  - Add hard-timeout cancellation tests.
  - Add status age tests.

- Modify `tests/unit/test_worker_settings.py`
  - Assert the new `soft_timeout_seconds` and `hard_timeout_seconds` defaults.
  - Assert agent-heavy workers no longer default to zero hard timeout.

- Modify `tests/architecture/test_worker_runtime_contracts.py`
  - Add an allowlist guard:
    ```python
    ZERO_HARD_TIMEOUT_ALLOWLIST = {"collector"}
    ```
  - Fail when any other canonical worker has `hard_timeout_seconds == 0`.

- Modify `tests/unit/test_pulse_candidate_worker.py`
  - Add a cancellation test proving a claimed pulse job is not left running after supervisor cancellation.

- Modify `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`
  - Add a test for `CancelledError` after run start: `pulse_agent_runs` is failed with `worker_timeout`, and the job is failed/dead according to attempt count.
  - Add a test for `CancelledError` before run start: job returns to pending and claim attempt is compensated.

- Modify `tests/unit/domains/narrative_intel/test_narrative_workers.py`
  - Add mention semantics cancellation test: failed model run row is recorded and semantic rows become retryable.
  - Add digest cancellation test: failed model run row is recorded and admission is backed off.

- Modify `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
  - Add cancellation audit test for `AgentExecutionCancelled`.

### Docs

- Modify `docs/WORKERS.md`
  - Document soft timeout, hard timeout, and stage timeout as separate layers.
  - Document that non-continuous workers must have finite hard timeout.

- Modify `docs/RELIABILITY.md`
  - Add cancellation safety invariant: hard timeout is cooperative and domains must persist retry/audit cleanup before re-raising cancellation.
  - Add note that `asyncio.to_thread` cancellation does not kill synchronous DB work; statement timeout and process liveness escalation remain required.

- Modify `docs/WORKER_FLOW.md`
  - Update worker lifecycle diagram with active task age, soft timeout, hard cancel, and cleanup.

## PR Breakdown

1. **PR 1 - WorkerBase Timeout Semantics**
   - Owns `worker_base.py`, `worker_scheduler.py`, worker status schema, and WorkerBase tests.
   - Mergeable after soft/hard semantics and status fields are tested.

2. **PR 2 - Settings And Architecture Guards**
   - Owns `settings.py`, default `workers.yaml`, worker settings tests, and architecture guard.
   - Depends on PR 1 because config fields are consumed by `WorkerBase`.

3. **PR 3 - Agent Gateway Cancellation Audit**
   - Owns `agent_execution.py`, `agent_execution_gateway.py`, and gateway tests.
   - Mergeable after cancellation propagates as cancellation and releases counters/reservations.

4. **PR 4 - Pulse Cancellation Cleanup**
   - Owns Pulse job repository, job service, worker budget, and Pulse tests.
   - Depends on PR 1 and PR 3.

5. **PR 5 - Narrative Cancellation Cleanup**
   - Owns narrative workers, narrow repository helpers, and narrative tests.
   - Depends on PR 1 and PR 3.

6. **PR 6 - Docs And Operational Verification**
   - Owns docs and final verification artifact.
   - Runs full check suite and records live-data diagnostic commands with redacted config paths.

## Task 1 - WorkerBase Soft Timeout Is Observable Only Once

**Files:**

- Modify: `tests/unit/test_worker_base_runtime.py`
- Modify: `src/parallax/app/runtime/worker_base.py`

- [ ] **Step 1: Write failing soft-timeout status test**

  Add test `test_worker_base_soft_timeout_marks_overrun_once_without_resetting_started_at`.

  Test shape:
  ```python
  class SlowThenStopWorker(WorkerBase):
      async def run_once(self) -> WorkerResult:
          self.first_started_at_ms_seen = self.last_started_at_ms
          await asyncio.sleep(0.03)
          await self.stop()
          return WorkerResult(processed=1)
  ```

  Required assertions:
  ```python
  assert worker.calls == 1
  assert worker.last_started_at_ms == worker.first_started_at_ms_seen
  assert telemetry.jobs.count(("slow_status", "failed", 1)) == 1
  assert worker.status_payload()["active_run_once_age_ms"] is None
  ```

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_soft_timeout_marks_overrun_once_without_resetting_started_at -q
  ```
  Expected before implementation: FAIL because the current loop reports repeated timeout attempts and updates `last_started_at_ms` before every wait.

- [ ] **Step 2: Implement active task timestamps**

  In `_create_run_once_task()`, set:
  ```python
  self.last_started_at_ms = _now_ms()
  self.active_run_once_started_at_ms = self.last_started_at_ms
  self.active_run_once_soft_timed_out_at_ms = None
  self.active_run_once_hard_timed_out_at_ms = None
  ```

  Remove the unconditional `self.last_started_at_ms = _now_ms()` from the outer loop before `_create_run_once_task()`.

- [ ] **Step 3: Implement one-shot soft timeout handling**

  In `_run_once_with_timeout()`, when soft timeout fires:
  ```python
  if id(task) not in self._soft_timeout_reported_for_task:
      self._soft_timeout_reported_for_task.add(id(task))
      self.active_run_once_soft_timed_out_at_ms = _now_ms()
      raise WorkerRunSoftTimeout(...)
  raise WorkerRunSoftTimeout(...)
  ```

  In `run()`, only record failed-iteration metrics for the first soft timeout of a task. Subsequent soft-timeout waits should keep `last_error` and status current without inflating failed job counts.

- [ ] **Step 4: Clear active task fields on task completion**

  In `_discard_run_once_task()`, after removing the task from `_run_once_tasks`, clear active fields when no tasks remain:
  ```python
  if not self._run_once_tasks:
      self.active_run_once_started_at_ms = None
      self.active_run_once_soft_timed_out_at_ms = None
      self.active_run_once_hard_timed_out_at_ms = None
  self._soft_timeout_reported_for_task.discard(id(task))
  ```

- [ ] **Step 5: Verify soft timeout behavior**

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_soft_timeout_marks_overrun_once_without_resetting_started_at -q
  uv run pytest tests/unit/test_worker_base_runtime.py -q
  ```
  Expected: all WorkerBase runtime tests pass after updating old assertions to the new semantics.

## Task 2 - WorkerBase Hard Timeout Cancels Without Overlap

**Files:**

- Modify: `tests/unit/test_worker_base_runtime.py`
- Modify: `src/parallax/app/runtime/worker_base.py`

- [ ] **Step 1: Write failing hard-timeout cancellation test**

  Add test `test_worker_base_hard_timeout_cancels_in_flight_task_and_discards_it`.

  Test worker:
  ```python
  class HardTimedWorker(WorkerBase):
      async def run_once(self) -> WorkerResult:
          self.calls += 1
          self.active += 1
          self.max_active = max(self.max_active, self.active)
          try:
              await asyncio.sleep(10)
          except asyncio.CancelledError:
              self.cancelled = True
              await self.stop()
              raise
          finally:
              self.active -= 1
  ```

  Required assertions:
  ```python
  assert worker.cancelled is True
  assert worker.max_active == 1
  assert worker._run_once_tasks == set()
  assert "WorkerRunHardTimeout" in (worker.last_error or "")
  ```

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_hard_timeout_cancels_in_flight_task_and_discards_it -q
  ```
  Expected before implementation: FAIL because current timeout keeps the shielded task alive.

- [ ] **Step 2: Add hard timeout properties**

  In `WorkerBase`:
  ```python
  @property
  def soft_timeout_seconds(self) -> float:
      return max(0.0, float(getattr(self.settings, "soft_timeout_seconds", getattr(self.settings, "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))))

  @property
  def hard_timeout_seconds(self) -> float:
      return max(0.0, float(getattr(self.settings, "hard_timeout_seconds", 0.0)))
  ```

  The fallback to `timeout_seconds` is only an implementation bridge while settings are migrated in Task 4; remove the fallback in the same PR that updates all settings and tests.

- [ ] **Step 3: Implement hard timeout deadline**

  Compute task age from `active_run_once_started_at_ms`. If `hard_timeout_seconds > 0` and age exceeds the hard deadline:
  ```python
  self.active_run_once_hard_timed_out_at_ms = _now_ms()
  await self._cancel_run_once_task(task)
  raise WorkerRunHardTimeout(...)
  ```

  The cancellation path must await `_cancel_run_once_task(task)` before returning to the outer loop.

- [ ] **Step 4: Ensure no overlap after hard timeout**

  Add assertion in the test that `max_active == 1`. The implementation must not create a fresh `run_once` until the cancelled task is gathered and discarded.

- [ ] **Step 5: Verify hard timeout behavior**

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_hard_timeout_cancels_in_flight_task_and_discards_it -q
  uv run pytest tests/unit/test_worker_base_runtime.py -q
  ```

## Task 3 - Worker Status And Scheduler Health

**Files:**

- Modify: `src/parallax/app/runtime/worker_base.py`
- Modify: `src/parallax/app/runtime/worker_scheduler.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `tests/unit/test_worker_base_runtime.py`
- Modify: `tests/unit/test_worker_scheduler.py`
- Modify: `tests/unit/test_cli_worker_status_contract.py`

- [ ] **Step 1: Add status payload test**

  Add a WorkerBase test that starts a slow worker, waits until soft timeout is set, then asserts:
  ```python
  payload = worker.status_payload()
  assert payload["active_run_once_started_at_ms"] is not None
  assert payload["active_run_once_age_ms"] > 0
  assert payload["active_run_once_soft_timed_out_at_ms"] is not None
  assert payload["active_run_once_count"] == 1
  ```

- [ ] **Step 2: Extend WorkerStatus dataclass**

  Add the new fields and compute `active_run_once_age_ms` from `_now_ms() - active_run_once_started_at_ms` when active.

- [ ] **Step 3: Extend scheduler unhealthy reasons**

  In `WorkerScheduler.unhealthy_reasons()`, append:
  ```python
  worker:{name}:hard_timeout
  ```
  when `active_run_once_hard_timed_out_at_ms` is set or `last_error` starts with `WorkerRunHardTimeout`.

- [ ] **Step 4: Update API/CLI schema tests**

  Update status schema expectations so clients can see active age and timeout state.

- [ ] **Step 5: Verify status contracts**

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py tests/unit/test_cli_worker_status_contract.py -q
  ```

## Task 4 - Settings Hard Cut And Zero-Timeout Guard

**Files:**

- Modify: `src/parallax/platform/config/settings.py`
- Modify: `tests/unit/test_worker_settings.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `docs/generated/cli-help.md` only if CLI config output changes.

- [ ] **Step 1: Write failing settings tests**

  In `tests/unit/test_worker_settings.py`, replace old assertions with:
  ```python
  assert settings.mention_semantics.soft_timeout_seconds == 240
  assert settings.mention_semantics.hard_timeout_seconds == 300
  assert settings.token_discussion_digest.soft_timeout_seconds == 570
  assert settings.token_discussion_digest.hard_timeout_seconds == 660
  assert settings.pulse_candidate.soft_timeout_seconds == 540
  assert settings.pulse_candidate.hard_timeout_seconds == 660
  assert settings.collector.hard_timeout_seconds == 0
  ```

- [ ] **Step 2: Add architecture guard**

  In `tests/architecture/test_worker_runtime_contracts.py`, load `WorkersSettings(**yaml.safe_load(default_workers_yaml()))` and assert:
  ```python
  ZERO_HARD_TIMEOUT_ALLOWLIST = {"collector"}
  for worker_key in CANONICAL_WORKER_NAMES:
      hard_timeout = getattr(getattr(settings, worker_key), "hard_timeout_seconds")
      if worker_key not in ZERO_HARD_TIMEOUT_ALLOWLIST:
          assert hard_timeout > 0, f"{worker_key} must have a finite hard timeout"
  ```

- [ ] **Step 3: Update settings models**

  Add `soft_timeout_seconds` and `hard_timeout_seconds` to `PerWorkerSettings`. Remove `timeout_seconds` from generated defaults and tests after all runtime reads use the new names.

- [ ] **Step 4: Update default YAML block**

  Replace every `timeout_seconds:` entry in `default_workers_yaml()` with the new explicit fields.

- [ ] **Step 5: Verify settings hard cut**

  Run:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

## Task 5 - Agent Gateway Cancellation Audit

**Files:**

- Modify: `src/parallax/platform/agent_execution.py`
- Modify: `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`

- [ ] **Step 1: Write failing gateway cancellation test**

  Add `test_gateway_supervisor_cancellation_records_cancelled_audit_and_releases_reservation`.

  Fake runner:
  ```python
  class SlowRunner:
      async def run(self, *args, **kwargs):
          await asyncio.sleep(10)
  ```

  Test flow:
  ```python
  task = asyncio.create_task(gateway.execute(stage))
  await asyncio.sleep(0)
  task.cancel()
  result = await asyncio.gather(task, return_exceptions=True)
  exc = result[0]
  assert isinstance(exc, AgentExecutionCancelled)
  assert exc.audit.error_class == AgentExecutionErrorClass.CANCELLED
  assert gateway.status_snapshot()["global_in_flight"] == 0
  ```

- [ ] **Step 2: Add cancellation types**

  Add `AgentExecutionErrorClass.CANCELLED` and `AgentExecutionCancelled`.

- [ ] **Step 3: Catch cancellation in gateway**

  Add `except asyncio.CancelledError as exc` before `except Exception` in `execute()`, create failed audit, record telemetry, and raise `AgentExecutionCancelled(...) from exc`.

- [ ] **Step 4: Verify gateway cancellation**

  Run:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_gateway_supervisor_cancellation_records_cancelled_audit_and_releases_reservation -q
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
  ```

## Task 6 - Pulse Cancellation Cleanup

**Files:**

- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`

- [ ] **Step 1: Add repository tests for cancellation states**

  Add tests proving:
  - before execution started, `mark_job_cancelled_by_worker_timeout(..., execution_started=False)` returns job to pending and decrements attempt count;
  - after execution started, it stores failed/dead according to `attempt_count >= max_attempts`.

- [ ] **Step 2: Add job-service cancellation test**

  Fake a provider that raises `AgentExecutionCancelled` from `run_decision_pipeline(...)`. Assert:
  ```python
  assert repos.pulse_runs.finished_runs[0]["outcome"] == "worker_timeout"
  assert repos.pulse_jobs.cancelled_jobs[0]["execution_started"] is True
  ```

- [ ] **Step 3: Implement repository method**

  Use a single `UPDATE ... WHERE job_id = %s AND status = 'running' RETURNING *` statement for each branch. Keep it idempotent if the job was already finished by a concurrent cleanup.

- [ ] **Step 4: Implement service cancellation cleanup**

  In `PulseCandidateJobService.run_job()`, catch cancellation, finish run when present, call repository cleanup, and re-raise.

- [ ] **Step 5: Add Pulse worker budget setting**

  Add `max_agent_jobs_per_cycle: int = Field(default=2, ge=1)` to `PulseCandidateWorkerSettings` and use it to bound `process_due_jobs_once_async()`.

- [ ] **Step 6: Verify Pulse cleanup**

  Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py -q
  ```

## Task 7 - Narrative Cancellation Cleanup

**Files:**

- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`
- Modify: `tests/unit/domains/narrative_intel/test_narrative_workers.py`

- [ ] **Step 1: Add mention semantics cancellation test**

  Fake provider:
  ```python
  class CancellingNarrativeProvider:
      async def label_mentions(self, *, run_id, request):
          raise AgentExecutionCancelled("cancelled", audit=None, execution_started=True)
  ```

  Assert a failed model run is recorded and semantic rows become retryable with `worker_timeout_cancelled`.

- [ ] **Step 2: Add digest cancellation test**

  Fake `summarize_discussion(...)` to raise `AgentExecutionCancelled`. Assert failed model run is recorded and `mark_admissions_digest_scanned` backs off the admission.

- [ ] **Step 3: Implement mention semantics cleanup**

  Add `except asyncio.CancelledError as exc` around provider call. Use existing `_record_completion_sync()` with failure rows built from `_provider_failure_for_row(...)`, but set error text to `worker_timeout_cancelled`.

- [ ] **Step 4: Implement digest cleanup**

  Add `except asyncio.CancelledError as exc` around provider call. Use `_record_failed_run_sync()` and `_mark_digest_scanned_sync()` with `_provider_failure_next_due_at_ms(...)`, then re-raise.

- [ ] **Step 5: Verify narrative cleanup**

  Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```

## Task 8 - Documentation And Operational Runbook

**Files:**

- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/TECH_DEBT.md` only if implementation leaves follow-up work outside this plan.

- [ ] **Step 1: Update WORKERS lifecycle section**

  Add a timeout layering paragraph:
  ```text
  Worker soft timeout is an overrun signal. Worker hard timeout is a cooperative cancellation boundary. Agent lane timeout is a provider execution boundary. DB statement timeout is the final guard for synchronous SQL.
  ```

- [ ] **Step 2: Update RELIABILITY cancellation invariant**

  Document that hard timeout cleanup must persist retry/audit state before re-raising cancellation, and that `asyncio.to_thread` cannot forcibly kill the underlying sync function.

- [ ] **Step 3: Update WORKER_FLOW state-machine section**

  Add a state flow:
  ```text
  idle -> active -> soft_timed_out -> hard_cancelling -> cleanup_persisted -> backoff -> active
  ```

- [ ] **Step 4: Verify docs stay linked**

  Run:
  ```bash
  uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

## Rollout Order

1. Merge WorkerBase/status semantics.
2. Merge settings hard cut and update operator `~/.parallax/workers.yaml`.
3. Merge gateway cancellation audit.
4. Merge Pulse cleanup.
5. Merge Narrative cleanup.
6. Restart the foreground service or Docker app process after settings change.
7. Observe `/readyz`, `/api/status`, and `/api/ops/diagnostics` for active task ages and hard-timeout failures.

## Rollback

- Runtime code rollback: revert the PRs in reverse order.
- Config rollback: restore previous `workers.yaml` only with the matching previous code version. Do not run new code with old `timeout_seconds` keys after the settings hard cut.
- Data cleanup rollback:
  - Pulse jobs marked `worker_timeout_before_execution` are retryable and can be picked up by the next cycle.
  - Pulse jobs marked `worker_timeout_after_execution` follow existing max-attempt rules.
  - Narrative rows marked retryable by worker timeout re-enter the normal retry path at `next_retry_at_ms`.
- If synchronous DB work remains stuck after cooperative cancellation, restart the process; Python cannot safely kill the already-running `asyncio.to_thread` worker thread.

## Acceptance Test Commands

- Worker runtime:
  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py -q
  ```
- Settings and guards:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/architecture/test_worker_runtime_contracts.py -q
  ```
- Agent gateway:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
  ```
- Pulse:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py -q
  ```
- Narrative:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
- Full completion gate:
  ```bash
  make check-all
  ```

## Verification

Create verification evidence at `docs/superpowers/plans/active/2026-05-20-worker-timeout-supervision-hardening-verification-cn.md` before declaring implementation complete.

The verification artifact must include:

- full `make check-all` output;
- old versus new WorkerBase timeout test summary;
- sanitized `uv run parallax config` output showing active config paths;
- `/api/status` sample showing new active age fields;
- any observed stuck-thread or statement-timeout limitations;
- follow-ups appended to `docs/TECH_DEBT.md` if hard process restart supervision remains outside this plan.
