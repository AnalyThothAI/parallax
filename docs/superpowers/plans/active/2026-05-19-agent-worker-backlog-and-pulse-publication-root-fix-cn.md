# Plan — Agent Worker Backlog And Pulse Publication Root Fix

**Status**: Complete
**Date**: 2026-05-19
**Owning spec**: `docs/superpowers/specs/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
**Worktree**: `.worktrees/agent-worker-backlog-root-fix/`
**Branch**: `codex/agent-worker-backlog-root-fix`

## Pre-flight

- [x] Worktree exists at `.worktrees/agent-worker-backlog-root-fix/`.
- [x] `git branch --show-current` returns `codex/agent-worker-backlog-root-fix`.
- [x] Existing Narrative stopgap diff was carried into the worktree from the dirty main checkout.
- [x] Worker subagents reviewed and landed independent slices for Pulse normalization, Pulse job budgeting, and Narrative health.
- [x] Affected backend, frontend, schema, lint, and diff checks were recorded.

Known-failing baseline tests:

- None confirmed. Targeted red tests were added and observed failing before implementation for the first local slice.

## Landed Changes

### Narrative Admission And Digest Truth

- `MentionSemanticsWorkerSettings` gained `max_semantic_rows_enqueued_per_cycle` and `max_pending_semantics_per_target`.
- `default_workers_yaml()` now emits the Narrative admission budget defaults.
- `NarrativeRepository.pending_mention_semantics_count()` lets the worker count queued/retryable/stale semantic rows before admission.
- `MentionSemanticsWorker` now bounds semantic admission by cycle budget and per-target pending cap, while keeping provider claim cap as `min(batch_size, provider_batch_size)`.
- `DiscussionDigestService` and read-model serialization now expose pending semantic backlog as processing state instead of labeling it as true source insufficiency.

### Narrative Operational Health

- Added `NarrativeBacklogHealthQuery`.
- Added authenticated `GET /api/status/narrative-health`.
- Updated API schema, OpenAPI, frontend generated types, and contract docs.
- Added coverage for backlog-health query, API contract, read model, and frontend data-gap copy.

### Pulse Public Readiness

- `PulseReadRepository.pulse_summary()` now distinguishes total candidates from displayable/public candidates.
- `SignalPulseService.health` derives `pulse_ready` / `public_ready` from public candidate count, not hidden total count.
- Pulse freshness health includes latest hidden-hold candidate timestamp.
- Signal Lab renders hold/degraded/hidden-only health state without exposing hidden rows.

### Pulse Job Budget And Stale Cleanup

- `PulseCandidateWorkerSettings` gained positive budget settings:
  - `max_enqueues_per_cycle`
  - `max_pending_jobs_global`
  - `max_pending_jobs_per_window_scope`
  - `stale_job_ttl_by_window_seconds`
- `PulseCandidateWorker` suppresses enqueueing when cycle/global/window-scope caps are reached.
- `PulseJobsRepository` can count pending jobs and terminalize stale active jobs by window TTL.
- Defaults terminalize stale `5m` jobs after 300 seconds.

### Pulse Agent Output Normalization

- Added `agent_output_normalization.py`.
- `PulseDecisionAgentClient` now normalizes final decision output before strict validation.
- The normalizer repairs uniquely resolvable same-packet evidence ref typos and narrow schema aliases.
- Correction/rejection metadata is preserved in stage audit output.
- Existing claim evidence verification remains the trust boundary.

## Files Touched

- `docs/CONTRACTS.md`
- `docs/generated/openapi.json`
- `docs/superpowers/specs/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
- `docs/superpowers/plans/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_status.py`
- `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/read_models/narrative_read_model.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/queries/pulse_freshness_health_queries.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_output_normalization.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- affected backend tests under `tests/unit` and `tests/integration`
- affected frontend tests and generated types under `web/`

## Rollout Order

1. Merge/deploy code without migration.
2. Restart workers so `workers.yaml` defaults/overrides are loaded.
3. Check `mention_semantics` worker notes for suppressed budget and pending caps.
4. Check authenticated `/api/status/narrative-health` for semantic/digest backlog.
5. Check `/api/signal-lab/pulse` health for `publish_status`, `public_candidate_count`, `public_ready`, and hidden-hold timestamps.
6. Watch Pulse candidate worker notes for enqueue suppression and stale terminalization counts.

## Rollback

- Revert code deploy or tune worker budgets in `~/.gmgn-twitter-intel/workers.yaml`.
- No schema migration rollback is needed.
- If Narrative suppresses too aggressively, raise `max_semantic_rows_enqueued_per_cycle` or `max_pending_semantics_per_target`.
- If Pulse falls behind, raise `max_enqueues_per_cycle`, `max_pending_jobs_global`, or `max_pending_jobs_per_window_scope`; if short-window jobs are terminalized too early, raise the relevant TTL.

## Acceptance Coverage

- Narrative admission budget and per-target pending cap: `tests/unit/domains/narrative_intel/test_narrative_workers.py`.
- Narrative digest pending/backlog truth: `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`, `tests/unit/domains/narrative_intel/test_narrative_read_model.py`.
- Narrative health API/query: `tests/unit/domains/narrative_intel/test_narrative_backlog_health.py`, `tests/unit/test_api_narrative_contract.py`.
- Pulse hidden-only/public-ready health: `tests/unit/test_signal_pulse_service.py`, `tests/unit/test_api_signal_pulse_contract.py`.
- Pulse repository counts and stale job terminalization: `tests/integration/test_pulse_repositories.py`.
- Pulse worker enqueue caps/TTL: `tests/unit/test_pulse_candidate_worker.py`.
- Pulse output normalization: `tests/unit/domains/pulse_lab/test_agent_output_normalization.py`, `tests/unit/test_pulse_decision_agent_client.py`.
- Worker config defaults/validation: `tests/unit/test_worker_settings.py`.
- Signal Lab health banner/data-gap copy: `web/tests/component/features/signal-lab/ui/SignalLabWorkbench.test.tsx`, `web/tests/unit/shared/model/narrativeDataGaps.test.ts`.

## Verification

Commands run before the final documentation/config polish:

```text
uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/unit/test_api_narrative_contract.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/integration/test_narrative_repository.py tests/unit/domains/pulse_lab/test_agent_output_normalization.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_claim_evidence_verifier.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repositories.py tests/unit/test_worker_settings.py tests/unit/test_signal_pulse_service.py tests/unit/test_api_signal_pulse_contract.py tests/contract/test_openapi_drift.py -q
148 passed

uv run ruff check .
All checks passed

cd web && npm test -- --run tests/component/features/signal-lab/ui/SignalLabWorkbench.test.tsx tests/component/features/signal-lab/ui/SignalLabPulse.test.tsx tests/unit/shared/model/narrativeDataGaps.test.ts
3 files, 4 tests passed

cd web && npm run typecheck
passed

cd web && npm run lint
passed

git diff --check
passed
```

Final polish verification after this plan update:

```text
uv run pytest tests/unit/test_worker_settings.py tests/unit/test_pulse_candidate_worker.py -q
35 passed

uv run ruff check src/gmgn_twitter_intel/platform/config/settings.py src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py tests/unit/test_worker_settings.py docs/superpowers/specs/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md docs/superpowers/plans/active/2026-05-19-agent-worker-backlog-and-pulse-publication-root-fix-cn.md
All checks passed

git diff --check
passed
```

Skipped:

- Full `make check-all` was not run in this turn due scope and time.
- Browser E2E was not run; UI changes are component-covered and do not alter routing or network query semantics.

## Remaining Follow-ups

- Compact Pulse agent input view without changing sealed packet hashes.
- Add explicit ops recovery command for old retryable/terminal Narrative semantic rows.
- Reconsider a platform-level LLM budget only after worker-local metrics are stable in live runtime.
