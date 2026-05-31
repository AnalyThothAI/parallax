# Agent Execution Plane Backpressure And Backlog Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-19
**Owning spec:** `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-cn.md`
**Worktree:** `.worktrees/agent-execution-plane-backpressure-root-fix/`
**Branch:** `codex/agent-execution-plane-backpressure-root-fix`

**Goal:** Finish the unified Agent Execution Plane by fixing Pulse parent/stage reservation, no-start backpressure semantics, lane-policy drift, agent-lane ops visibility, stale type cleanup, and Narrative backlog rollout.

**Architecture:** Keep domain job state machines local and PostgreSQL-first. `AgentExecutionGateway` remains the only OpenAI Agents SDK execution path, but gains parent reservation semantics for multi-stage workflows and active per-lane RPM without hidden semaphore sleeps. Domains map gateway `execution_started=false` to backpressure/no-attempt-burn; if claim already incremented attempts, domains compensate that claim or release through an attempt-preserving method. Started calls continue through existing retry/audit policies.

**Tech Stack:** Python 3.13, Pydantic v2, openai-agents, AsyncOpenAI, aiolimiter, psycopg, FastAPI, pytest, ruff, PostgreSQL.

---

## Scope

- In:
  - Gateway reservation semantics, timeout/RPM policy behavior, and status snapshot.
  - Pulse pipeline reservation and timeout contract.
  - Narrative/Social/Watchlist/Pulse no-start backpressure handling, including
    attempt-count compensation for queues that increment attempts during claim.
  - Ops diagnostics agent-lane section.
  - Stale `agent_execution_types.py` / `agent_hashing.py` cleanup.
  - Formal Narrative drain verification.
- Out:
  - Central durable agent queue.
  - Public Pulse write-gate relaxation.
  - Token Radar scoring changes.
  - News LLM fact extraction.
  - Strict priority scheduling without a queued arbiter.

## Pre-flight

- [ ] Read the owning spec completely:
  ```bash
  sed -n '1,360p' docs/superpowers/specs/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-cn.md
  ```

- [ ] Create an isolated worktree:
  ```bash
  git worktree add .worktrees/agent-execution-plane-backpressure-root-fix -b codex/agent-execution-plane-backpressure-root-fix main
  cd .worktrees/agent-execution-plane-backpressure-root-fix
  ```

- [ ] Verify branch and clean status:
  ```bash
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/agent-execution-plane-backpressure-root-fix`; expected status: clean.

- [ ] Confirm live config paths before any live-data verification:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Do not print secrets.

- [ ] Run baseline tests:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture/test_agent_execution_plane_contracts.py -q
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
  uv run pytest tests/unit/test_pulse_candidate_worker.py::test_process_due_jobs_does_not_claim_when_agent_capacity_denied -q
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  ```

## File Structure

### Gateway / Platform

- Modify `src/parallax/platform/agent_execution.py`
  - Extend `AgentCapacityReservation` with parent/child lane semantics and explicit global ownership.
  - Keep this as the only live source for agent execution value types.

- Modify `src/parallax/platform/agent_hashing.py`
  - Keep as the only live hashing helper module.

- Delete `src/parallax/integrations/openai_agents/agent_execution_types.py`
  - Remove duplicate stale type definitions.

- Delete `src/parallax/integrations/openai_agents/agent_hashing.py`
  - Remove duplicate stale hashing helpers if no imports remain after the previous cleanup.

- Modify `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
  - Add parent reservation execution path.
  - Add per-lane RPM limiters without holding scarce capacity during unbounded limiter waits.
  - Preserve global limiter and per-lane bulkhead behavior.
  - Expand status snapshot with policy fields and clear `priority_label`.

### Pulse

- Modify `src/parallax/domains/pulse_lab/providers.py`
  - Allow `PulseDecisionProvider.try_reserve_execution(...)` to accept child lanes/scope.
  - Allow `PulseDecisionProvider.run_decision_pipeline(...)` to accept a parent pipeline reservation.

- Modify `src/parallax/app/runtime/provider_wiring/openai.py`
  - Expose pipeline timeout from `settings.workers.agent_runtime`.

- Modify `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py`
  - Pass the parent reservation to both Pulse stages.
  - Use stage lane timeouts from gateway and provider pipeline timeout from policy.
  - Preserve no-start `AgentExecutionError` metadata instead of collapsing it into an untyped failed stage audit.

- Modify `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
  - Accept parent reservation from worker.
  - Use configured pipeline timeout.
  - Map no-start `AgentExecutionError` to job backpressure/release instead of provider failure.

- Modify `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Create a parent reservation with allowed child lanes.
  - Pass it into `job_service.run_job(...)`.

- Modify `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py`
  - Add a narrow no-start release/reschedule method that compensates the claim attempt increment.

- Modify Pulse run outcome schema/migration only if a new non-provider backpressure outcome is required to avoid leaving `pulse_agent_runs` running.

### Narrative / Social / Watchlist

- Modify `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
  - Branch on no-start `AgentExecutionError` before building row failures.

- Modify `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - Branch on no-start `AgentExecutionError` and mark the admission for short backoff without writing a failed model run as provider failure.

- Modify `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
  - Branch on no-start errors and release/reschedule jobs without burning attempts.

- Modify `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
  - Branch on no-start errors and release/reschedule jobs without burning attempts.

- Modify repositories only if needed:
  - `src/parallax/domains/social_enrichment/repositories/*.py`
  - `src/parallax/domains/watchlist_intel/repositories/*.py`
  - Social and Watchlist claims already increment attempts; release methods must clear running/lease state and compensate that claim increment.
  - Keep methods named around domain language, e.g. `release_job_for_backpressure(...)`.

### Ops / Docs / Tests

- Modify `src/parallax/app/runtime/ops_diagnostics.py`
  - Add `agent_execution` section.

- Modify `src/parallax/app/surfaces/api/schemas.py`
  - Add loose named schemas if existing ops schemas need explicit fields.

- Modify docs:
  - `docs/ARCHITECTURE.md`
  - `docs/WORKERS.md`
  - `docs/RELIABILITY.md`
  - This plan and owning spec if implementation decisions change.

- Add / modify tests:
  - `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
  - `tests/unit/test_pulse_candidate_worker.py`
  - `tests/unit/domains/narrative_intel/test_narrative_workers.py`
  - `tests/unit/test_enrichment_worker_runtime.py`
  - `tests/unit/domains/watchlist_intel/test_handle_summary_worker.py`
  - `tests/unit/test_ops_diagnostics.py`
  - `tests/architecture/test_agent_execution_plane_contracts.py`

## PR Breakdown

1. **PR 1 - Gateway Semantics And Guardrails**
   - Add failing tests for Pulse parent reservation with `global_max_concurrency=1`, per-lane RPM, and stale duplicate modules.
   - Implement parent reservation and per-lane RPM/no-start rate limit without hidden limiter queues under semaphores.
   - Delete duplicate type/hash modules.

2. **PR 2 - Pulse Parent Reservation And Timeout**
   - Thread parent reservation from worker to job service to OpenAI Pulse client.
   - Use `pulse.pipeline` policy timeout for outer pipeline.
   - Preserve Pulse no-start typed metadata through stage/client failures.
   - Add no-start backpressure release/reschedule for Pulse jobs and close any already inserted Pulse agent run as backpressure, not provider failure.

3. **PR 3 - No-Start Backpressure Across Lanes**
   - Narrative mention semantics and digest: no-start does not increment retry counts or write fake provider failures.
   - Social and Watchlist: no-start does not burn job attempts.
   - Add unit tests for each lane.

4. **PR 4 - Ops Visibility And Docs**
   - Add `agent_execution` section to `/api/ops/diagnostics`.
   - Document `priority` as policy label, not strict scheduling.
   - Update architecture/reliability docs and verification notes.

5. **PR 5 - Narrative Drain Rollout Evidence**
   - Run formal drain/rebuild in the target environment.
   - Capture sanitized health evidence.
   - Complete verification artifact.

## Task 1 - Gateway Parent Reservation Tests

**Files:**

- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`

- [ ] **Step 1: Add a failing test for Pulse parent reservation**

  Add a test that constructs `AgentExecutionGateway` with `global_max_concurrency=1`,
  reserves `pulse.pipeline` with child lanes, and executes an `AgentStageSpec`
  for `pulse.evidence_debate` using the parent reservation. Use an injected fake
  runner so no network call occurs.

  Required assertion:
  ```python
  assert parent.acquired is True
  assert result.audit.status == AgentExecutionStatus.DONE
  assert gateway.status_snapshot()["global_in_flight"] == 1
  ```

  Run:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_parent_pipeline_reservation_reuses_global_slot_for_child_stage -q
  ```
  Expected before implementation: FAIL because `execute()` rejects a reservation whose lane differs from the stage lane or because the child stage cannot acquire global capacity.

- [ ] **Step 2: Add a failing test for per-lane RPM**

  Add a test with `global_rpm_limit=1000` and lane policy
  `AgentLanePolicy(max_concurrency=1, rpm_limit=1)`. Prefer an injected limiter
  or fake clock so this test does not sleep for a real minute. Assert two
  started provider calls honor lane RPM and that limiter waiting is not reported
  as provider-running work.

  Run:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_lane_rpm_limit_applies_even_when_global_rpm_is_high -q
  ```
  Expected before implementation: FAIL because only `_global_limiter` is used.

- [ ] **Step 3: Add stale-module architecture guard**

  Extend `tests/architecture/test_agent_execution_plane_contracts.py` with:

  ```python
  def test_agent_execution_types_have_single_live_source() -> None:
      stale = OPENAI_AGENTS / "agent_execution_types.py"
      assert not stale.exists()

  def test_agent_hashing_has_single_live_source() -> None:
      stale = OPENAI_AGENTS / "agent_hashing.py"
      assert not stale.exists()
  ```

  Run:
  ```bash
  uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_types_have_single_live_source -q
  ```
  Expected before cleanup: FAIL.

## Task 2 - Gateway Parent Reservation Implementation

**Files:**

- Modify: `src/parallax/platform/agent_execution.py`
- Modify: `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
- Delete: `src/parallax/integrations/openai_agents/agent_execution_types.py`
- Delete: `src/parallax/integrations/openai_agents/agent_hashing.py`

- [ ] **Step 1: Extend `AgentCapacityReservation`**

  Add fields:

  ```python
  owns_global: bool = True
  child_lanes: tuple[str, ...] = ()
  scope: str = "execution"
  ```

  Keep `active` and `release()` semantics unchanged except that release must
  only release resources actually acquired by the reservation callback.

- [ ] **Step 2: Extend `try_reserve` signature**

  In `AgentExecutionGateway`, change:

  ```python
  def try_reserve(self, lane: str) -> AgentCapacityReservation:
  ```

  to:

  ```python
  def try_reserve(
      self,
      lane: str,
      *,
      child_lanes: tuple[str, ...] = (),
      scope: str = "execution",
  ) -> AgentCapacityReservation:
  ```

  Parent pipeline callers will pass:

  ```python
  child_lanes=("pulse.evidence_debate", "pulse.decision_maker")
  scope="parent"
  ```

- [ ] **Step 3: Add child-lane execution path**

  Extend `execute()` to accept:

  ```python
  parent_reservation: AgentCapacityReservation | None = None
  ```

  Rules:

  - `reservation` and `parent_reservation` are mutually exclusive.
  - `reservation` must still match `stage.lane`.
  - A valid same-lane `reservation` is the admission decision; do not re-check
    circuit before the provider call and create a post-claim no-start.
  - `parent_reservation` must be active, owner-issued, `owns_global=True`, and
    `scope="parent"`.
  - `parent_reservation` must have
    `stage.lane in parent_reservation.child_lanes`.
  - Child execution must acquire the stage lane semaphore only.
  - Child execution must still check the child lane circuit and child lane
    semaphore because the parent did not reserve the child bulkhead.
  - Child execution must not acquire or release global semaphore.
  - Parent reservation remains owned and released by the caller.

- [ ] **Step 4: Add internal lane-only reservation helper**

  Add a private helper:

  ```python
  def _try_reserve_lane_only(self, lane: str) -> AgentCapacityReservation:
      lane_key = str(lane)
      lane_state = self._lane_state(lane_key)

      if self._is_circuit_open(lane_key, lane_state):
          lane_state.circuit_open_total += 1
          self._record_backpressure(
              lane_key,
              AgentExecutionErrorClass.CIRCUIT_OPEN,
          )
          return AgentCapacityReservation(
              lane=lane_key,
              acquired=False,
              reason=AgentExecutionErrorClass.CIRCUIT_OPEN,
              owns_global=False,
          )

      if not _try_acquire_nowait(lane_state.semaphore):
          lane_state.capacity_denied_total += 1
          self._record_backpressure(
              lane_key,
              AgentExecutionErrorClass.CAPACITY_DENIED,
          )
          return AgentCapacityReservation(
              lane=lane_key,
              acquired=False,
              reason=AgentExecutionErrorClass.CAPACITY_DENIED,
              owns_global=False,
          )

      released = False

      def release() -> None:
          nonlocal released
          if released:
              return
          released = True
          lane_state.semaphore.release()

      return AgentCapacityReservation(
          lane=lane_key,
          acquired=True,
          owns_global=False,
          _release=release,
          _owner_token=self._reservation_owner_token,
      )
  ```

  It checks lane circuit state and lane semaphore, increments lane
  `capacity_denied_total` on denial, and returns a reservation with
  `owns_global=False`.

- [ ] **Step 5: Add per-lane RPM limiters without hidden queues**

  In `__init__`, build:

  ```python
  self._lane_limiters = {
      lane: AsyncLimiter(policy.rpm_limit, 60)
      for lane, policy in self._policy.lanes.items()
      if policy.rpm_limit is not None
  }
  ```

  Do not let work hold lane/global semaphores while it waits unboundedly for RPM.
  Use one of these two patterns and test the chosen behavior:

  - check limiter availability before scarce-capacity reservation and return
    no-start `RATE_LIMITED` when no token is available within a bounded budget; or
  - wait for limiter before `_record_in_flight()` / provider-running accounting
    and expose `rpm_waiting_count` separately.

  Do not implement this shape:

  ```python
  # Bad: this sleeps under acquired semaphores and makes rate-limit wait
  # look like provider-running work.
  reservation = self.try_reserve(stage.lane)
  async with self._global_limiter:
      async with lane_limiter:
          return await self._run_stage(stage, audit, runner_entered=runner_entered)
  ```

- [ ] **Step 6: Expand `status_snapshot()`**

  Each lane payload must include:

  ```python
  {
      "priority_label": lane_state.policy.priority,
      "rpm_limit": lane_state.policy.rpm_limit,
      "max_concurrency": lane_state.policy.max_concurrency,
      "timeout_seconds": float(lane_state.policy.timeout_seconds),
      "in_flight": _in_flight(lane_state.semaphore),
      "provider_running": lane_state.provider_running_count,
      "rpm_waiting_count": lane_state.rpm_waiting_count,
      "circuit_state": (
          "open" if lane_state.circuit_open_until > now else "closed"
      ),
      "circuit_open_until_ms": _monotonic_deadline_to_epoch_ms(
          lane_state.circuit_open_until
      ),
      "capacity_denied_total": lane_state.capacity_denied_total,
      "circuit_open_total": lane_state.circuit_open_total,
      "timeout_total": lane_state.timeout_total,
      "last_denied_at_ms": lane_state.last_denied_at_ms,
      "last_timeout_at_ms": lane_state.last_timeout_at_ms,
      "oldest_in_flight_age_ms": lane_state.oldest_in_flight_age_ms,
  }
  ```

  The top-level payload must include `global_rpm_limit`. Keep `/api/status`
  compatible by preserving the current `lanes` dictionary shape; ops diagnostics
  may transform it into a list for rendering.

- [ ] **Step 7: Add release/cancel regression tests**

  Add tests that parent/child reservations release correctly after success,
  `AgentExecutionError`, generic exception, and cancellation. Assert
  `global_in_flight` and lane `in_flight` return to zero.

- [ ] **Step 8: Delete stale duplicate modules and update imports**

  Delete:

  ```text
  src/parallax/integrations/openai_agents/agent_execution_types.py
  src/parallax/integrations/openai_agents/agent_hashing.py
  ```

  Run:

  ```bash
  rg -n "integrations\\.openai_agents\\.agent_execution_types|integrations\\.openai_agents\\.agent_hashing" src tests
  ```

  Expected: no output.

- [ ] **Step 9: Verify gateway tests**

  Run:

  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py tests/architecture/test_agent_execution_plane_contracts.py -q
  ```

  Expected: PASS.

## Task 3 - Pulse Parent Reservation And Timeout

**Files:**

- Modify: `src/parallax/domains/pulse_lab/providers.py`
- Modify: `src/parallax/app/runtime/provider_wiring/openai.py`
- Modify: `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/unit/test_pulse_decision_agent_client.py`

- [ ] **Step 1: Add failing Pulse worker test for parent reservation**

  Extend the fake gateway/client tests so:

  - worker reserves `pulse.pipeline` with
    `child_lanes=("pulse.evidence_debate", "pulse.decision_maker")` and
    `scope="parent"`;
  - job service receives that parent reservation;
  - Pulse client executes child stages with the parent pipeline reservation;
  - no child stage calls `try_reserve("pulse.evidence_debate")` for global.

  Run:

  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py::test_pulse_pipeline_parent_reservation_is_passed_to_stage_execution -q
  ```

  Expected before implementation: FAIL.

- [ ] **Step 2: Extend provider protocol reservation methods**

  In `PulseDecisionProvider.try_reserve_execution(...)`, add:

  ```python
  def try_reserve_execution(
      self,
      lane: str,
      *,
      child_lanes: tuple[str, ...] = (),
      scope: str = "execution",
  ) -> AgentCapacityReservation:
      pass
  ```

  Thread those keywords through `OpenAIPulseDecisionProvider` and
  `OpenAIAgentsPulseDecisionClient.try_reserve_execution(...)`.

  In `PulseDecisionProvider.run_decision_pipeline(...)`, add:

  ```python
  parent_reservation: AgentCapacityReservation | None = None
  ```

  Keep default `None` so tests and fake providers can migrate incrementally.

- [ ] **Step 3: Add configured pipeline timeout to provider wrapper**

  In `OpenAIPulseDecisionProvider`, store `pipeline_timeout_seconds`.
  Build it in `openai_pulse_decision_provider(...)` from:

  ```python
  settings.workers.agent_runtime.lanes["pulse.pipeline"].timeout_seconds
  ```

  The provider property `timeout_seconds` must return that value.

- [ ] **Step 4: Thread parent reservation through job service**

  Change:

  ```python
  await self.job_service.run_job(job, context, now_ms=resolved_now_ms)
  ```

  to:

  ```python
  await self.job_service.run_job(
      job,
      context,
      now_ms=resolved_now_ms,
      parent_reservation=reservation,
  )
  ```

  Add the same keyword to `PulseCandidateJobService.run_job(...)`.

- [ ] **Step 5: Use parent reservation in Pulse client stages**

  In `OpenAIAgentsPulseDecisionClient.run_decision_pipeline(...)`, accept
  `parent_reservation`. Pass it into `_run_evidence_debate(...)`,
  `_run_decision_maker(...)`, `_run_stage(...)`, and finally:

  To keep existing fake gateways easy to migrate, call with the keyword only
  when a parent reservation is present:

  ```python
  if parent_reservation is None:
      execution = await self._agent_gateway.execute(stage_spec)
  else:
      execution = await self._agent_gateway.execute(
          stage_spec,
          parent_reservation=parent_reservation,
      )
  ```

- [ ] **Step 6: Preserve Pulse no-start typed metadata**

  Current `OpenAIAgentsPulseDecisionClient._run_stage(...)` catches
  `AgentExecutionError` and converts it to `StageRunAudit`, which loses stable
  no-start classification. Fix this before changing `PulseCandidateJobService`.

  Choose one implementation and cover it with tests:

  - re-raise no-start `AgentExecutionError` directly and attach any partial
    stage audits to a domain exception; or
  - extend `PulseStageFailure` with:

    ```python
    agent_error_class: AgentExecutionErrorClass | None = None
    execution_started: bool | None = None
    agent_audit: dict[str, Any] | None = None
    ```

    and include the same values in the failed/skipped stage audit
    `trace_metadata_json`.

  Required classification:

  ```text
  no-start backpressure =
    execution_started is False
    and error_class in {capacity_denied, circuit_open, rate_limited}
  ```

  Started timeouts/schema/provider/transport failures must keep the current
  Pulse stage-failure path.

- [ ] **Step 7: Handle Pulse no-start backpressure**

  In `PulseCandidateJobService`, when `PulseStageFailure` or an
  `AgentExecutionError` audit shows `execution_started=false` with
  `capacity_denied`, `circuit_open`, or `rate_limited`, call a repository method
  that reschedules the current `pulse_agent_jobs` row and compensates the claim
  attempt increment.

  Also close the already-created `pulse_agent_runs` row. Do not leave it
  `status='running'`, and do not classify the run as a provider failure. If the
  current `pulse_agent_runs.outcome` constraint cannot represent backpressure,
  add a narrow Alembic migration for:

  ```text
  backpressure_capacity_denied
  backpressure_circuit_open
  backpressure_rate_limited
  ```

  Then finish the run with `status='skipped'` or the closest existing
  non-provider terminal status and a trace metadata patch containing
  `{"agent_backpressure": true, "agent_error_class": reason}`.

  If no existing method preserves attempts, add:

  ```python
  def release_running_job_for_backpressure(
      self,
      job: dict[str, Any],
      *,
      reason: str,
      now_ms: int,
      delay_ms: int = 30_000,
  ) -> None:
      self.conn.execute(
          """
          UPDATE pulse_agent_jobs
          SET status = 'pending',
              next_run_at_ms = %s,
              last_error = %s,
              attempt_count = GREATEST(0, attempt_count - 1),
              updated_at_ms = %s
          WHERE job_id = %s
            AND status = 'running'
            AND attempt_count = %s
          """,
          (
              int(now_ms) + int(delay_ms),
              str(reason),
              int(now_ms),
              str(job["job_id"]),
              int(job.get("attempt_count") or 0),
          ),
      )
      _commit_if_available(self.conn)
  ```

  SQL must set `status='pending'`, `next_run_at_ms=now_ms + delay_ms`,
  `last_error=reason`, `updated_at_ms=now_ms`, and must leave the persisted
  attempt count equal to the value before this no-start claim. Guard the update
  with current `attempt_count` / lease identity where available so repeated
  release calls cannot decrement more than once.

- [ ] **Step 8: Verify Pulse timeout policy**

  Add test:

  ```bash
  uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py::test_pulse_provider_uses_agent_runtime_pipeline_timeout -q
  ```

  Expected: provider timeout is no lower than
  `workers.agent_runtime.lanes["pulse.pipeline"].timeout_seconds`. If keeping an
  outer `asyncio.wait_for`, add explicit grace so it cannot fire before gateway
  stage timeout/audit. Removing the outer wait and relying on stage lane
  timeouts is also acceptable.

- [ ] **Step 9: Verify Pulse tests**

  Run:

  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_decision_agent_client.py -q
  ```

  Expected: PASS.

## Task 4 - No-Start Backpressure In Narrative, Social, And Watchlist

**Files:**

- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
- Modify: `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Modify repository files only where no attempt-preserving release method exists.
- Modify tests listed below.

- [ ] **Step 1: Add shared local helper pattern in each worker**

  Do not create a cross-domain utility package. Use a tiny local helper in each
  worker or an owning-domain helper:

  ```python
  def _is_agent_no_start_backpressure(exc: Exception) -> bool:
      error_class = getattr(exc, "error_class", None)
      execution_started = bool(getattr(exc, "execution_started", True))
      value = getattr(error_class, "value", error_class)
      return not execution_started and value in {
          "capacity_denied",
          "circuit_open",
          "rate_limited",
      }
  ```

- [ ] **Step 2: Narrative mention semantics no-start path**

  Before constructing failures in the generic exception branch, add:

  ```python
  if _is_agent_no_start_backpressure(exc):
      return WorkerResult(
          skipped=len(rows),
          notes={
              "claimed": len(rows),
              "agent_backpressure": getattr(getattr(exc, "error_class", None), "value", "capacity_denied"),
              "agent_backpressure_capacity_denied": 1,
          },
      )
  ```

  The implementation must not call `complete_mention_semantics_batch(...)` for
  this path and must not write a failed `narrative_model_runs` row. The rows
  stay `queued` / `retryable_error` / `stale` and remain eligible for the next
  bounded catch-up cycle.

- [ ] **Step 3: Narrative digest no-start path**

  In `TokenDiscussionDigestWorker`, if summarize fails before execution starts:

  - do not write a failed `narrative_model_runs` row as provider failure;
  - mark the admission digest scan with a short next due time;
  - increment `pending`, not `failed`;
  - record `refresh_reasons["agent_backpressure"]`.
  - preserve current `token_discussion_digests` status as pending/backpressure
    context rather than `insufficient`.

- [ ] **Step 4: Social and Watchlist no-start paths**

  In Social and Watchlist workers, if execution is denied after claim but before
  provider start:

  - call a domain repository method that releases/reschedules and compensates
    the claim-time `attempt_count + 1`;
  - return/record skipped or backpressure, not failed provider error;
  - include `agent_backpressure` notes.

  Repository methods should clear `running`/lease state, set a short
  `next_run_at_ms`, store a compact `last_error` such as
  `agent_backpressure:capacity_denied`, and leave the persisted attempt count
  equal to the value before the no-start claim.

- [ ] **Step 5: Harden Narrative completion transaction and targeting**

  While touching Narrative no-start paths, fix the adjacent completion hazard:

  - record `narrative_model_runs` and `complete_mention_semantics_batch(...)` in
    one repository session/transaction instead of committing the run first and
    labels second;
  - update mention semantics rows by `semantic_id` when available, or by the
    full unique identity including `schema_version` / text fingerprint, not only
    `(event_id, target_type, target_id)`.

- [ ] **Step 6: Add tests**

  Add or update:

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_mention_semantics_capacity_denied_does_not_increment_retry_count -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_digest_capacity_denied_marks_pending_not_failed -q
  uv run pytest tests/unit/test_enrichment_worker_runtime.py::test_enrichment_worker_no_start_after_claim_releases_without_attempt_burn -q
  uv run pytest tests/unit/domains/watchlist_intel/test_handle_summary_worker.py::test_handle_summary_no_start_after_claim_releases_without_attempt_burn -q
  uv run pytest tests/integration/test_narrative_repository.py::test_complete_mention_semantics_targets_current_semantic_identity -q
  ```

  Expected after implementation: PASS.

## Task 5 - Ops Diagnostics Agent Execution Section

**Files:**

- Modify: `src/parallax/app/runtime/ops_diagnostics.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py` if needed.
- Modify: `tests/unit/test_ops_diagnostics.py`
- Modify frontend ops model only if strict typing requires it:
  - `web/src/features/ops/model/*`
  - `web/src/features/ops/ui/OpsDiagnosticsPage.tsx`

- [ ] **Step 1: Add backend payload**

  In `ops_diagnostics(...)`, read:

  ```python
  gateway = getattr(runtime, "agent_execution_gateway", None)
  snapshot = gateway.status_snapshot() if gateway is not None else None
  ```

  Add top-level:

  ```python
  "agent_execution": _agent_execution_payload(runtime)
  ```

  Payload must contain only policy/counter/status fields.

- [ ] **Step 2: Add diagnostic fields needed for attribution**

  The section must be able to distinguish:

  - capacity pressure: global/lane available slots, denied totals, recent/last
    denial timestamps, denial reason split when available;
  - circuit pressure: `circuit_state`, `circuit_open_until_ms`,
    failure count in window when available;
  - RPM pressure: lane/global `rpm_limit`, `rpm_waiting_count`,
    recent/last rate-limited denial;
  - provider latency: provider-running count, timeout totals/recent,
    oldest in-flight age, last success/timeout when available;
  - parent reservations: parent reservations in flight or oldest parent
    reservation age when available.

- [ ] **Step 3: Add classification**

  Agent section status:

  - `disabled` when no gateway is configured;
  - `blocked` when any lane circuit is open for a configured high-value lane;
  - `degraded` when any lane has recent capacity denials, rate-limited
    no-starts, RPM wait pressure, or timeouts;
  - `ok` otherwise.

  Do not classify from lifetime totals alone. Use recent-window fields,
  `last_*_at_ms`, or a sampled delta; otherwise one old timeout would keep the
  section degraded forever.

  Include this section in `/api/ops/diagnostics.overall` status aggregation.

- [ ] **Step 4: Add tests for sanitization and classification**

  Test that payload does not include keys matching:

  ```python
  {"api_key", "secret", "password", "token", "prompt", "input_payload", "output"}
  ```

  Run:

  ```bash
  uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_includes_sanitized_agent_execution_section -q
  uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_overall_includes_agent_execution_status -q
  uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_agent_execution_degraded_requires_recent_signal -q
  ```

- [ ] **Step 5: Update frontend only if needed**

  If current `OpsDiagnosticsPage` renders unknown top-level sections dynamically,
  no frontend edit is required. If it uses explicit section lists, add an
  `Agent` lane row with compact counters.

## Task 6 - Docs And Priority Contract Cleanup

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/CONTRACTS.md` if ops payload changes are contract-level.
- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`

- [ ] **Step 1: Document parent reservation**

  Update Agent Execution Plane sections to state:

  - `pulse.pipeline` is a parent claim reservation;
  - child Pulse stages reuse the parent global slot and acquire only stage lane bulkheads;
  - no-start backpressure does not burn attempts.

- [ ] **Step 2: Document priority honestly**

  Replace any text implying strict scheduling priority with:

  ```text
  priority is an operator-facing policy label in this in-process reservation model;
  strict priority scheduling requires a queued arbiter and is out of scope.
  ```

- [ ] **Step 3: Run docs/architecture tests**

  ```bash
  uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q
  ```

## Task 7 - Narrative Drain And Live Verification Runbook

**Files:**

- Create: `docs/superpowers/plans/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-verification-cn.md`

- [ ] **Step 1: Confirm live config paths**

  ```bash
  uv run parallax config
  ```

  Record only:

  - config path;
  - workers config path;
  - LLM configured boolean;
  - model family without secrets.

- [ ] **Step 2: Capture pre-drain health**

  Use authenticated local API or CLI-safe diagnostics. Do not print secrets.

  Required endpoints:

  - `/api/status`
  - `/api/status/narrative-health?since_hours=4`
  - `/api/ops/diagnostics?since_hours=4`
  - Prometheus summary for `gmgn_agent_execution_*` if metrics are enabled.

  Save t0 counts for:

  - worker `last_finished_at_ms`;
  - claimed/processed/skipped notes for LLM workers;
  - Narrative oldest due age and total pending/retryable semantics;
  - Pulse due/running/dead job counts and latest run finish age;
  - agent lane capacity/circuit/RPM/timeout fields.

- [ ] **Step 3: Run formal Narrative drain**

  ```bash
  uv run parallax ops rebuild-narrative-intel --window 1h --scope all --drain --cycles 2
  uv run parallax ops rebuild-narrative-intel --window 4h --scope all --drain --cycles 2
  uv run parallax ops rebuild-narrative-intel --window 24h --scope all --drain --cycles 2
  ```

  Expected: JSON `ok=true`, no manual SQL, no secret output.

- [ ] **Step 4: Capture post-drain health**

  Re-check:

  - total pending/retryable semantics;
  - semantic unavailable count;
  - digest reason counts;
  - top Token Radar narrative statuses.
  - agent lane in-flight/provider-running/RPM/circuit/capacity fields;
  - worker `last_finished_at_ms` and recent processed/claimed deltas.

  Expected: source-sufficient rows show `pending/semantic_labeling_pending`
  while labeling catches up; `insufficient/low_source_volume` appears only for
  actually low-source source sets.

- [ ] **Step 5: Observe two worker intervals**

  Capture t1 and t2 separated by at least two configured intervals of the slowest
  involved LLM worker. A successful runbook must show one of:

  - claimed/processed/model-run success deltas increasing; or
  - no due work and source/admission counts proving no data; or
  - a clear attributed blocker in agent diagnostics: capacity, circuit, RPM, DB
    queue/claim, publish gate, or provider latency.

  It is not sufficient to say "worker ran once"; oldest due age must not grow
  unbounded without an attribution.

- [ ] **Step 6: Save verification artifact**

  Create the verification document with:

  - commands run;
  - sanitized outputs or summarized counts;
  - failed commands and environment gaps;
  - final residual risks.

## Rollout Order

1. Merge PR 1 gateway semantics and guardrails.
2. Merge PR 2 Pulse parent reservation and timeout fix.
3. Merge PR 3 no-start backpressure handling.
4. Merge PR 4 ops/docs visibility.
5. Deploy with workers enabled but monitor `/api/status` and `/api/ops/diagnostics`.
6. Run formal Narrative drain/rebuild commands.
7. Observe at least two full worker intervals for:
   - Pulse no `capacity_denied` self-denial;
   - no-start paths not increasing retry/attempt counts;
   - worker `last_finished_at_ms` and claimed/processed deltas advancing when
     due work exists;
   - agent lane status attributing any remaining stall to capacity, circuit,
     RPM, DB claim, publish gate, no data, or provider latency.

## Rollback

- Code rollback is safe because this plan does not add a new durable central
  queue or new business fact table.
- Do not roll back by manually editing `pulse_agent_jobs` or
  `token_mention_semantics`.
- If Narrative drain removed rebuildable queued rows incorrectly, rerun
  `ops rebuild-narrative-intel` from material facts and current Radar frontier.
- If parent reservation leaks capacity, stop LLM-backed workers, deploy rollback,
  then restart workers. The gateway state is in-process only.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_parent_pipeline_reservation_reuses_global_slot_for_child_stage -q
  ```

- AC2:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py::test_pulse_no_start_backpressure_reschedules_without_extra_attempt_burn -q
  ```

- AC3:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_mention_semantics_capacity_denied_does_not_increment_retry_count -q
  ```

- AC4:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_timeout_audit_marks_execution_started_true -q
  ```

- AC5:
  ```bash
  uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py::test_pulse_provider_uses_agent_runtime_pipeline_timeout -q
  ```

- AC6:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_lane_rpm_limit_applies_even_when_global_rpm_is_high -q
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py::test_lane_rpm_wait_does_not_hold_capacity_as_provider_running -q
  ```

- AC7:
  ```bash
  rg -n "strict priority|priority scheduling|priority-aware" docs src/parallax | grep -v backpressure-and-backlog-root-fix || true
  ```
  Expected: no production docs claim strict priority scheduling.

- AC8:
  ```bash
  uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_includes_sanitized_agent_execution_section -q
  uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_overall_includes_agent_execution_status -q
  ```

- AC9:
  ```bash
  uv run parallax ops rebuild-narrative-intel --window 1h --scope all --drain --cycles 1
  ```
  Expected: JSON `ok=true`, no manual SQL.

- AC10:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_refresh_decision_uses_source_set_count_when_semantic_rows_are_missing -q
  ```

- AC11:
  ```bash
  rg -n "integrations\\.openai_agents\\.agent_execution_types|integrations\\.openai_agents\\.agent_hashing" src tests
  ```
  Expected: no output.

- AC12:
  ```bash
  uv run pytest tests/unit/test_enrichment_worker_runtime.py::test_enrichment_worker_no_start_after_claim_releases_without_attempt_burn -q
  uv run pytest tests/unit/domains/watchlist_intel/test_handle_summary_worker.py::test_handle_summary_no_start_after_claim_releases_without_attempt_burn -q
  ```

## Final Verification

Run the focused suite:

```bash
uv run ruff check src/parallax tests
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_decision_agent_client.py -q
uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
uv run pytest tests/unit/test_enrichment_worker_runtime.py tests/unit/domains/watchlist_intel/test_handle_summary_worker.py -q
uv run pytest tests/unit/test_ops_diagnostics.py -q
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q
```

If PostgreSQL-backed integration tests are available:

```bash
uv run pytest tests/integration/test_narrative_repository.py tests/integration/test_api_http.py -q
```

Before declaring complete, create and fill:

```text
docs/superpowers/plans/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-verification-cn.md
```

The verification artifact must include command outputs, live-data config path
confirmation, sanitized Narrative drain evidence, and residual risks.
