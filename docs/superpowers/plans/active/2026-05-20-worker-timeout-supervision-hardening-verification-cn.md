# Worker Timeout Supervision Hardening Verification

**Date:** 2026-05-20
**Branch:** `codex/worker-timeout-supervision-hardening`
**Worktree:** `.worktrees/worker-timeout-supervision-hardening`

## Result

Implemented and verified the worker timeout supervision hardening plan with
targeted tests. Full `make check-all` was not run in this pass; see the
commands below for the executed coverage.

## Verified Behavior

- `WorkerBase` soft timeout records one overrun event for the active
  `run_once()` task, keeps waiting for the original task, and exposes
  active task age/status.
- `WorkerBase` hard timeout cancels and awaits the in-flight task before
  returning to the loop, so a replacement task cannot overlap the stuck
  task.
- Worker status payloads expose active task timestamps, age, timeout
  timestamps, and active task count.
- Worker settings are hard-cut from worker-level `timeout_seconds` to
  `soft_timeout_seconds` and `hard_timeout_seconds`.
- `collector` is the only default worker with `hard_timeout_seconds == 0`.
- `AgentExecutionGateway` records `cancelled` audit metadata and releases
  in-flight counters when supervisor cancellation interrupts execution.
- Pulse cancellation cleanup finishes run audit rows, marks/requeues
  claimed jobs according to execution-started state, and re-raises
  cancellation.
- Worker-timeout cleanup is only persisted for cancellation carrying the
  `worker_hard_timeout` reason; ordinary scheduler shutdown cancellation
  propagates without burning retry/job state.
- Pulse timeout cleanup is scoped to the claimed attempt by
  `attempt_count` and `updated_at_ms`, so stale cleanup cannot mutate a
  newer reclaim.
- Narrative cancellation cleanup records failed model runs, backs off or
  retries affected rows, and re-raises cancellation.
- Pulse and Narrative retry deadlines are calculated from actual
  cancellation time, not stale cycle-start time.
- Docs now describe soft, hard, agent stage, and DB statement timeout
  layers.

## Commands Run

```bash
uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_settings.py -q
# 28 passed before implementation baseline
```

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_agent_execution_plane_contracts.py -q
# 60 passed before implementation baseline
```

```bash
uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py tests/unit/test_cli_worker_status_contract.py tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/architecture/test_worker_runtime_contracts.py -q
# 126 passed
```

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/narrative_intel/test_narrative_workers.py -q
# 100 passed
```

```bash
uv run pytest tests/integration/test_worker_advisory_lock_single_writer.py tests/integration/test_worker_missed_wake_recovery.py -q
# 3 passed in 109.30s
```

```bash
uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_agent_execution_plane_contracts.py -q
# 65 passed
```

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py -q
# 8 passed
```

```bash
uv run ruff check <changed python files>
# All checks passed
```

```bash
uv run pytest tests/unit/test_worker_settings.py::test_worker_settings_reject_zero_hard_timeout_for_non_continuous_workers \
  tests/unit/test_worker_base_runtime.py::test_worker_base_soft_timeout_marks_overrun_once_without_resetting_started_at \
  tests/unit/test_worker_base_runtime.py::test_worker_base_hard_timeout_cancels_in_flight_task_and_discards_it \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_before_execution_releases_job_and_finishes_run \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_after_execution_marks_job_failed_or_dead_and_finishes_run \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_plain_cancellation_does_not_persist_worker_timeout_cleanup \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_cleanup_does_not_mutate_newer_claim_attempt \
  tests/unit/domains/narrative_intel/test_narrative_workers.py::test_mention_semantics_worker_persists_cleanup_when_provider_call_is_cancelled \
  tests/unit/domains/narrative_intel/test_narrative_workers.py::test_token_discussion_digest_worker_persists_cleanup_when_provider_call_is_cancelled
# 9 passed in re-review
```

```bash
git diff --check
# passed
```

## Review

- Initial spec re-review found two gaps: non-collector zero hard timeouts
  were still parseable, and soft timeout could re-enter polling for the
  same task when hard timeout was disabled. Both were fixed and covered
  by tests.
- Code quality review found three important issues: retry/backoff
  deadlines used stale cycle-start time, Pulse cleanup was not scoped to
  the claimed attempt, and ordinary shutdown cancellation could be
  persisted as `worker_timeout_cancelled`. These were fixed and covered
  by tests.
- Final re-review passed with `9 passed` on the targeted regression set.

## Config Check

```bash
uv run parallax config
```

Result: failed as expected against the operator-owned
`~/.parallax/workers.yaml` because that file still contains old
worker-level `timeout_seconds` keys.

Observed validation errors were limited to stale worker config keys:

- `defaults.timeout_seconds`
- `collector.timeout_seconds`
- `pulse_candidate.timeout_seconds`
- `news_fetch.timeout_seconds`

Before running this branch against live data, update
`~/.parallax/workers.yaml` to use `soft_timeout_seconds` and
`hard_timeout_seconds` for worker supervision. Agent lane/provider
`timeout_seconds` keys remain valid because they are stage/provider
timeouts, not worker supervision timeouts.

## Known Limitations

- Cooperative cancellation cannot kill a synchronous function already
  running in an `asyncio.to_thread(...)` worker thread. DB statement
  timeout and process-level restart remain the final escalation path for
  stuck synchronous work.
- `make check-all` remains the full completion gate before landing.
