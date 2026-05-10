# Dedupe Root Fix Second Pass Verification

**Date**: 2026-05-10
**Worktree**: `.worktrees/dedupe-root-fix/`
**Branch**: `codex/dedupe-root-fix`

## Commands

- Red tests before implementation:
  - `GMGN_TEST_POSTGRES_DSN='postgresql://postgres:postgres@127.0.0.1:55433/gmgn_twitter_intel_test' uv run pytest tests/test_notification_repository.py::test_insert_notification_does_not_recount_same_source_conflicts tests/test_notification_repository.py::test_insert_notification_aggregates_each_source_once_per_dedup_key tests/test_notification_repository.py::test_insert_notification_suppresses_same_pulse_source_status_with_different_key -q`
    - Result: 3 failed, proving poll-cycle recount and same Pulse source/status re-delivery.
  - `uv run pytest tests/test_pulse_candidate_worker.py::test_cooldown_does_not_bypass_for_inferred_token_watch_status_rank tests/test_pulse_candidate_worker.py::test_recent_dead_job_blocks_reenqueue_without_candidate -q`
    - Result: 2 failed, proving inferred-status cooldown bypass and dead-job requeue.
- `GMGN_TEST_POSTGRES_DSN='postgresql://postgres:postgres@127.0.0.1:55433/gmgn_twitter_intel_test' uv run pytest tests/test_notification_repository.py -q`
  - Result: 7 passed.
- `GMGN_TEST_POSTGRES_DSN='postgresql://postgres:postgres@127.0.0.1:55433/gmgn_twitter_intel_test' uv run pytest tests/test_pulse_repository.py -q`
  - Result: 15 passed.
- `GMGN_TEST_POSTGRES_DSN='postgresql://postgres:postgres@127.0.0.1:55433/gmgn_twitter_intel_test' uv run pytest tests/test_notification_worker.py -q`
  - Result: 5 passed.
- `uv run pytest tests/test_notification_rules.py tests/test_settings.py tests/test_pulse_candidate_worker.py -q`
  - Result: 44 passed.
- `uv run ruff check .`
  - Result: all checks passed.
- `uv run pytest`
  - Result: 396 passed, 139 skipped.
- `uv run python -m compileall src tests`
  - Result: passed.

The temporary PostgreSQL container used for focused repository tests was stopped after verification.

## Diff Summary

- `NotificationRepository.insert_notification()` now aggregates only once per source ref and suppresses same Signal Pulse source/status rows even if the generated key changes.
- `PulseCandidateWorker` no longer treats inferred `token_watch` status as a cooldown bypass and now blocks recent terminal jobs when no materialized candidate exists.
- Regression tests cover poll-cycle recount, source-once aggregation, Signal Pulse source/status re-delivery, inferred-status reruns, and dead-job requeue.

## Risks

- Existing duplicate notification rows already delivered in production are not deleted or marked read by this change.
- The internal `_aggregation_source_refs` payload field is used to avoid schema churn; it is capped to the latest 100 source refs per aggregate row.
