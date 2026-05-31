# Dedupe Root Fix Second Pass Implementation Plan

**Status**: Complete
**Date**: 2026-05-10
**Owning spec**: `docs/superpowers/specs/completed/2026-05-05-production-notifications-phase1-phase2-design-cn.md`
**Worktree**: `.worktrees/dedupe-root-fix/`
**Branch**: `codex/dedupe-root-fix`

## Pre-flight

- [x] Worktree exists at `.worktrees/dedupe-root-fix/` and `git branch --show-current` matches `codex/dedupe-root-fix`.
- [x] Production DB audit identified the second-pass root cause.
- [x] Failing regression tests demonstrate the duplicate-count and rerun failures before implementation.
- [x] `uv run ruff check .` passes.
- [x] `uv run pytest` passes.
- [x] `uv run python -m compileall src tests` passes.

Known-failing baseline tests:

- None expected before adding the new regressions.

## Root Cause

- `NotificationRepository.insert_notification()` increments `occurrence_count` and updates `updated_at_ms` on every `dedup_key` conflict. The rule engine scans sliding windows, so the same source row is re-emitted on every poll; counts like `1031` in roughly 30 minutes prove the code is counting poll cycles, not new occurrences.
- The Signal Pulse notification key changed from signature-based to status/bucket-based. Because the repository only enforced `dedup_key`, the same `rule_id + source_table + source_id + pulse_status` was emitted as a new notification after deployment. Production data showed 67 of 70 post-deploy high Signal Pulse pushes had an older notification for the same Pulse candidate and status.
- `PulseCandidateWorker._cooldown_bypass()` infers `token_watch` for almost every asset trigger. Existing `risk_rejected_high_info` or `blocked_low_information` candidates therefore bypass cooldown on normal metric churn, which requeues jobs after a recent terminal run.
- Dead jobs without a materialized candidate have no cooldown guard. Once their signature changes, they can be re-enqueued immediately and burn another attempt set.

## File-level Edits

### `src/parallax/storage/notification_repository.py`

- Change `insert_notification()` conflict handling from unconditional aggregate update to source-aware aggregation:
  - Insert payload stores a small internal `_aggregation_source_refs` list.
  - On `dedup_key` conflict, lock the existing row and update only when the incoming source ref is new.
  - If the source ref is already present, return `None` without changing `occurrence_count`, `last_seen_at_ms`, `payload_json`, or `updated_at_ms`.
- Before creating a new row, check the semantic source identity for an existing row:
  - Generic source identity: same `rule_id`, `source_table`, and `source_id`.
  - For Pulse payloads, include `payload_json->>'pulse_status'` so real status changes can still create a new alert.
  - This is a root invariant, not a legacy key fallback: one user-visible source/status alert should not be re-delivered only because key construction changed.

### `src/parallax/pipeline/pulse_candidate_worker.py`

- Remove `_STATUS_RANK` based bypass from `_cooldown_bypass()`. Keep explicit material bypasses only: trade eligibility, first watched confirmation, +5 independent authors, new chase risk, and new hard risks.
- Add a terminal-job cooldown check for `done` and `dead` jobs when no existing candidate cooldown is available.
- Keep active `pending`, `running`, and retryable `failed` jobs blocking requeue as they do now.

### Tests

- `tests/test_notification_repository.py::test_insert_notification_does_not_recount_same_source_conflicts`
  Asserts repeated polls of the same source do not increment count or refresh the row.
- `tests/test_notification_repository.py::test_insert_notification_aggregates_each_source_once_per_dedup_key`
  Asserts a semantic bucket counts each source once, even if earlier sources reappear in later polls.
- `tests/test_notification_repository.py::test_insert_notification_suppresses_same_pulse_source_status_with_different_key`
  Asserts source/status identity prevents a new row when key construction changes.
- `tests/test_pulse_candidate_worker.py::test_cooldown_does_not_bypass_for_inferred_token_watch_status_rank`
  Asserts a recent risk/blocked candidate is not requeued merely because current metrics infer `token_watch`.
- `tests/test_pulse_candidate_worker.py::test_recent_dead_job_blocks_reenqueue_without_candidate`
  Asserts dead jobs have a cooldown even when no candidate row exists.

## Rollout Order

1. Add failing regression tests and verify they fail.
2. Implement source-aware notification aggregation.
3. Implement Pulse cooldown tightening.
4. Run focused tests.
5. Run full verification.
6. Merge to `main` and rebuild Docker.
7. Smoke-check `/readyz`, notification rows, and Pulse run rates after rebuild.

## Rollback

- Code rollback is a normal `git revert` of the merge commit.
- No schema migration is planned.
- Do not delete or rewrite existing production notifications automatically; any cleanup of already-delivered duplicate notifications should be a separate explicit operator decision.

## Acceptance Test Commands

- `uv run pytest tests/test_notification_repository.py::test_insert_notification_does_not_recount_same_source_conflicts -q`
- `uv run pytest tests/test_notification_repository.py::test_insert_notification_aggregates_each_source_once_per_dedup_key -q`
- `uv run pytest tests/test_notification_repository.py::test_insert_notification_suppresses_same_pulse_source_status_with_different_key -q`
- `uv run pytest tests/test_pulse_candidate_worker.py::test_cooldown_does_not_bypass_for_inferred_token_watch_status_rank -q`
- `uv run pytest tests/test_pulse_candidate_worker.py::test_recent_dead_job_blocks_reenqueue_without_candidate -q`
- `uv run ruff check .`
- `uv run pytest`
- `uv run python -m compileall src tests`

## Verification

See `docs/superpowers/plans/completed/2026-05-10-dedupe-root-fix-second-pass-verification.md`.
