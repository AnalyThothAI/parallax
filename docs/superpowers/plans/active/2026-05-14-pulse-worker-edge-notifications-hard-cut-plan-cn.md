# Pulse Worker Edge Notifications Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Signal Pulse worker 与通知链路 hard cut 成 edge-state 驱动：只在 token_target 状态跳变时入队，删除 `source_seed` / `theme_watch` 兼容面，强制 closed-form agent outcome，并让 Signal Pulse 通知按 edge signature 去重。

**Architecture:** `pulse_lab` 继续拥有 candidate gate、edge detector、job queue、agent audit ledger、read model；`notifications` 只消费 Pulse read model，不参与 scoring 或 provider 调用。Edge 前态写入 `pulse_candidate_edge_state`，预算写入 `pulse_candidate_run_budget`，public candidate 仍写 `pulse_candidates`。

**Tech Stack:** Python 3.13, PostgreSQL, Alembic, psycopg JSONB, pytest, ruff, FastAPI/OpenAPI generated types, React/Vitest frontend types.

---

## Status

**Status**: In Progress
**Date**: 2026-05-14
**Owning spec**: `docs/superpowers/specs/active/2026-05-14-pulse-worker-architecture-cn.md`
**Worktree**: `.worktrees/pulse-worker-edge-notifications-hard-cut/`
**Branch**: `codex/pulse-worker-edge-notifications-hard-cut`

## Pre-flight

- [x] Spec is approved by user request on 2026-05-14.
- [x] Worktree exists at `.worktrees/pulse-worker-edge-notifications-hard-cut/`.
- [x] `git branch --show-current` returns `codex/pulse-worker-edge-notifications-hard-cut`.
- [x] Baseline `uv run ruff check .` passes.
- [x] Baseline targeted tests pass: `uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_notification_rules.py -q`.

Known-failing baseline tests: none in the targeted baseline.

## Invariants

- [ ] No compatibility aliases, fallback readers, old enum support, or dual writes.
- [ ] No direct source-led Pulse candidates; Pulse worker only enqueues `token_target`.
- [ ] No new provider calls or scoring in API/CLI/notification surfaces.
- [ ] No raw SQL outside repositories, queries, app runtime, or migrations.
- [ ] No secrets or raw auth material in run step prompts or trace metadata.
- [ ] `abstain` remains decision semantics, not a `pulse_status`.

## File-level Edits

### Storage / migrations

Add `src/parallax/platform/db/alembic/versions/20260514_0041_pulse_worker_edge_notifications_hard_cut.py`.

The hard-cut migration runs after `20260514_0040_repair_pulse_agent_job_cooldown.py`; `0040` repairs old deployments that still miss `cooldown_until_ms`, and `0041` immediately removes that field from the final runtime schema.

Upgrade must:

```sql
UPDATE pulse_agent_runs
SET outcome = CASE
  WHEN status = 'running' THEN 'running'
  WHEN status = 'failed' THEN 'failed'
  WHEN status = 'done' AND response_json->>'recommendation' = 'abstain'
    AND COALESCE(response_json->>'abstain_reason', '') = 'critic_veto'
    THEN 'abstain_critic_veto'
  WHEN status = 'done' AND response_json->>'recommendation' = 'abstain'
    AND COALESCE(response_json->>'abstain_reason', '') IN ('data_completeness_blocked','research_only_no_resolved_target')
    THEN 'abstain_insufficient_data'
  WHEN status = 'done' AND response_json->>'recommendation' = 'abstain'
    THEN 'abstain'
  WHEN status = 'done' THEN 'completed'
  ELSE 'failed'
END
WHERE outcome = 'pending';

DELETE FROM pulse_agent_jobs
WHERE candidate_type = 'source_seed'
   OR context_json->>'candidate_type' = 'source_seed'
   OR context_json #>> '{factor_snapshot,subject,target_type}' = 'source_seed';

DELETE FROM pulse_candidates
WHERE candidate_type = 'source_seed'
   OR pulse_status = 'theme_watch'
   OR factor_snapshot_json #>> '{subject,target_type}' = 'source_seed';

CREATE TABLE IF NOT EXISTS pulse_candidate_edge_state (
  candidate_id TEXT PRIMARY KEY,
  candidate_type TEXT NOT NULL CHECK (candidate_type = 'token_target'),
  target_type TEXT NOT NULL CHECK (target_type IN ('Asset','CexToken')),
  target_id TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  pulse_version TEXT NOT NULL,
  gate_version TEXT NOT NULL,
  latest_observed_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_processed_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_edge_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_budget_rejected_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_job_id TEXT,
  last_agent_run_id TEXT,
  first_seen_at_ms BIGINT NOT NULL,
  latest_observed_at_ms BIGINT NOT NULL,
  last_processed_at_ms BIGINT,
  last_budget_rejected_at_ms BIGINT
);

CREATE INDEX IF NOT EXISTS idx_pulse_candidate_edge_state_target
  ON pulse_candidate_edge_state(target_type, target_id, latest_observed_at_ms DESC);

CREATE TABLE IF NOT EXISTS pulse_candidate_run_budget (
  candidate_id TEXT NOT NULL,
  hour_bucket_ms BIGINT NOT NULL,
  enqueue_count BIGINT NOT NULL DEFAULT 0,
  last_enqueued_at_ms BIGINT NOT NULL,
  last_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY(candidate_id, hour_bucket_ms)
);

CREATE INDEX IF NOT EXISTS idx_pulse_candidate_run_budget_hour
  ON pulse_candidate_run_budget(hour_bucket_ms);

ALTER TABLE pulse_candidates
  ADD COLUMN IF NOT EXISTS last_edge_events_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE pulse_agent_runs
  ALTER COLUMN outcome DROP DEFAULT;

ALTER TABLE pulse_agent_runs
  DROP CONSTRAINT IF EXISTS chk_pulse_agent_runs_outcome;
ALTER TABLE pulse_agent_runs
  ADD CONSTRAINT chk_pulse_agent_runs_outcome
  CHECK (outcome IN ('running','completed','abstain','abstain_critic_veto','abstain_insufficient_data','failed'));

ALTER TABLE pulse_candidates
  DROP CONSTRAINT IF EXISTS chk_pulse_candidates_candidate_type;
ALTER TABLE pulse_candidates
  ADD CONSTRAINT chk_pulse_candidates_candidate_type
  CHECK (candidate_type = 'token_target');

ALTER TABLE pulse_candidates
  DROP CONSTRAINT IF EXISTS chk_pulse_candidates_pulse_status;
ALTER TABLE pulse_candidates
  ADD CONSTRAINT chk_pulse_candidates_pulse_status
  CHECK (pulse_status IN ('trade_candidate','token_watch','risk_rejected_high_info','blocked_low_information'));

DROP INDEX IF EXISTS idx_pulse_agent_jobs_claim;
ALTER TABLE pulse_agent_jobs DROP COLUMN IF EXISTS cooldown_until_ms;
CREATE INDEX IF NOT EXISTS idx_pulse_agent_jobs_claim
  ON pulse_agent_jobs(status, next_run_at_ms, priority DESC, created_at_ms ASC, job_id ASC)
  WHERE status IN ('pending','failed','running');

DROP INDEX IF EXISTS idx_notification_deliveries_claim;
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_claim
  ON notification_deliveries(next_run_at_ms ASC, created_at_ms ASC, delivery_id ASC)
  WHERE status IN ('pending','failed','running');
```

Downgrade may recreate dropped columns and looser constraints, but does not restore deleted `source_seed` / `theme_watch` rows.

### `src/parallax/domains/pulse_lab/interfaces.py`

- Remove `source_seed` from `CANDIDATE_TYPES` and `CandidateType`.
- Remove `theme_watch` from `PULSE_STATUSES`, `DISPLAY_PULSE_STATUSES`, `PulseStatus`, and `DisplayPulseStatus`.
- Bump `PULSE_GATE_VERSION` to a new edge-state version so existing rows generate `pulse_version_bumped` once.

### `src/parallax/domains/pulse_lab/services/pulse_edge_events.py`

Create this file.

Definitions:

- `PulseEdgeState`: frozen dataclass with `candidate_id`, `pulse_version`, `gate_version`, `target_type`, `target_id`, `pulse_status`, `score_band`, `candidate_score_bucket`, `recommended_decision`, `hard_risks`, `watched_confirmation`, `route`, `trigger_signature`.
- `PulseEdgeEvent`: `Literal["pulse_status_changed","score_band_crossed","hard_risk_added","recommended_decision_changed","watched_emerged","pulse_version_bumped"]`.
- `build_pulse_edge_state(...) -> PulseEdgeState`.
- `diff_pulse_edge_events(previous: Mapping[str, Any] | None, current: PulseEdgeState) -> list[str]`.
- `edge_signature(candidate_id: str, events: Sequence[str], state: PulseEdgeState) -> str`.

Expected behavior:

- Empty previous state returns `["pulse_status_changed"]`.
- Version or gate mismatch returns `pulse_version_bumped`.
- New hard risk returns `hard_risk_added`.
- watched false -> true returns `watched_emerged`; true -> false does not.
- Exact count changes are not represented.

### `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`

Modify:

- Remove `theme_watch` from display status SQL/constants.
- Remove `cooldown_until_ms` from `enqueue_job`, insert SQL, conflict update SQL, and `claim_due_job`.
- Change `insert_agent_run(... outcome: str = "running" ...)`.
- Change `finish_agent_run(run_id, status, *, outcome: str, ...)`; no optional outcome, no SQL `COALESCE`.
- Add `last_edge_events_json` to `upsert_candidate`.
- Add:
  - `edge_state_by_candidate(candidate_id: str) -> dict[str, Any] | None`
  - `record_edge_observation(...) -> dict[str, Any]`
  - `claim_edge_budget(...) -> bool`
  - `mark_edge_job_enqueued(candidate_id, job_id, events, state, now_ms, commit=True)`
  - `mark_edge_run_finished(candidate_id, run_id, now_ms, commit=True)`
- `pulse_summary` no longer counts `theme_watch`.

### `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`

Modify:

- Remove `_PLAYBOOK_STATUSES` `theme_watch`.
- Delete `_COOLDOWN_MS`, `_cooldown_active`, `_cooldown_bypass`, `_cooldown_ms`, `_terminal_job_blocks_reenqueue`, `_source_context`, `_source_candidate_id`, `_source_trigger_signature`, `_source_timeline_signature`, `_source_seed_factor_snapshot`, `_source_trigger_metrics`, `_inferred_status`, and source-event scan loop.
- Change `PulseTriggerThresholds.min_rank_score` default from `70` to `45`.
- `_is_asset_trigger` returns true when target exists, factor snapshot exists, and `recommended_decision in {"high_alert","watch"}` or `rank_score >= min_rank_score` or watched confirmation exists.
- `_enqueue_if_due`:
  1. Blocks active pending/running/failed jobs with attempts left.
  2. Computes gate and route before enqueue.
  3. Builds edge state.
  4. Records latest observed state.
  5. Diffs against last processed state.
  6. Skips if no events.
  7. Claims budget.
  8. Enqueues job with `edge_events` and `edge_state` in context.
  9. Marks edge job enqueued.
- `_run_job`:
  - Inserts initial run with `outcome="running"`.
  - Success calls `finish_agent_run(..., outcome=_run_outcome(...))`.
  - Failure calls `finish_agent_run(..., outcome="failed")`.
  - Candidate upsert passes `last_edge_events_json`.
  - After success/failure, updates edge run finished if run was inserted.
- `_narrative_type_from_context` always returns `direct_token` unless existing token target facts imply a better current enum.

### `src/parallax/domains/pulse_lab/services/agent_routing.py`

- Delete special `candidate_type == "source_seed"` research-only route.
- Research-only route remains allowed only for deterministic completeness hard block, not source seed compatibility.
- Update tests so no source_seed route is accepted.

### `src/parallax/domains/pulse_lab/services/agent_runtime.py`

- Keep `research_only` route in manifest for deterministic gate short-circuit.
- Remove contract text/tests that say source_seed stays research_only.

### `src/parallax/domains/pulse_lab/services/agent_eval.py`

- Remove source_seed-specific violation rules.
- Keep route/completeness audit checks.

### `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`

- Remove `theme_watch` from summary/display status constants.
- Add `last_edge_events` to `pulse_item_from_row`.
- Ensure `_is_displayable` accepts only `trade_candidate`, `token_watch`, `risk_rejected_high_info` and non-abstain decisions.

### `src/parallax/app/surfaces/api/http.py`

- Remove `theme_watch` from `SIGNAL_PULSE_STATUSES`.
- API `status=theme_watch` must return `invalid_status`.

### `src/parallax/platform/config/settings.py`

- Remove `theme_watch` from sample config and `_default_notification_rule_payloads()`.
- Keep user-provided `statuses` parsing generic, but notification rules will ignore unsupported statuses under hard-cut validation.

### `src/parallax/domains/notifications/services/notification_rules.py`

- Remove `theme_watch` from defaults, severity map, and cooldown map.
- `_signal_pulse_candidates` should skip unsupported statuses.
- `_pulse_notification_signature` includes:
  - `last_edge_events_json`
  - candidate id
  - pulse status
  - score band
  - route/recommendation
  - factor fingerprint
  - latest evidence bucket
- `_pulse_payload` includes `edge_events`.
- `_pulse_body` prints an edge line when available.
- `_has_resolved_pulse_target` only rejects missing target; no source_seed compatibility set.

### `src/parallax/domains/notifications/repositories/notification_repository.py`

- Change `_pulse_source_status_duplicate` to `_pulse_signature_duplicate`.
- Duplicate lookup requires `payload_json->>'notification_signature' = incoming_signature`.
- Add `running_timeout_ms` constructor arg, default 300_000.
- `claim_next_delivery` first marks stale running with exhausted attempts as `dead`, then can claim stale running with attempts left.
- Claim SQL includes `status = 'running' AND last_attempt_at_ms < stale_before AND attempt_count < max_attempts`.

### Frontend

Modify:

- `web/src/lib/types/frontend-contracts.ts`
- `web/src/features/signal-lab/state/signalLabRouteState.ts`
- `web/src/features/signal-lab/ui/SignalLabWorkbench.tsx`
- `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- `web/src/features/signal-lab/api/useSignalLabCompactQuery.ts`
- `web/src/features/signal-lab/model/pulseDetail.ts`
- fixtures/tests referencing `theme_watch`

Changes:

- Remove `theme_watch` from `SignalPulseStatus`.
- Remove theme summary pill/tab/count.
- Add optional `last_edge_events?: string[]`.
- Detail status labeling has no `theme_watch` branch.

### Docs / generated artifacts

Modify:

- `docs/ARCHITECTURE.md`: Signal Pulse worker uses edge-state ledger.
- `docs/CONTRACTS.md`: remove `theme_watch`/`source_seed`, add `last_edge_events`.
- `docs/RELIABILITY.md`: no pending outcome; notification stale running reclaim.
- `docs/generated/db-schema.md`: regenerate or update via project command.
- `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts`: regenerate via project command if available.

## TDD Tasks

### Task 1 — Edge Event Service

- [ ] Add unit tests in `tests/unit/test_pulse_edge_events.py`:
  - `test_first_observed_state_emits_status_changed`
  - `test_unchanged_state_emits_no_events`
  - `test_score_band_change_emits_score_band_crossed`
  - `test_new_hard_risk_emits_hard_risk_added`
  - `test_recommended_decision_change_emits_event`
  - `test_watched_confirmation_emergence_emits_event`
  - `test_version_change_emits_pulse_version_bumped`
  - `test_exact_author_or_mention_count_is_not_part_of_state`
- [ ] Run and confirm fail:
  `uv run pytest tests/unit/test_pulse_edge_events.py -q`
- [ ] Implement `pulse_edge_events.py`.
- [ ] Run and confirm pass:
  `uv run pytest tests/unit/test_pulse_edge_events.py -q`

### Task 2 — Repository Schema and Methods

- [ ] Add/modify integration tests:
  - `tests/integration/test_pulse_repository.py::test_edge_state_and_budget_round_trip`
  - `tests/integration/test_pulse_repository.py::test_edge_budget_rejects_fourth_enqueue_in_same_hour`
  - `tests/integration/test_pulse_repository.py::test_finish_agent_run_requires_closed_form_outcome`
  - `tests/integration/test_pulse_repository.py::test_candidate_type_and_status_hard_cut_constraints`
  - `tests/integration/test_pulse_repository.py::test_pulse_summary_excludes_theme_watch`
- [ ] Run and confirm fail:
  `uv run pytest tests/integration/test_pulse_repository.py -q`
- [ ] Add migration and repository implementation.
- [ ] Run and confirm pass:
  `uv run pytest tests/integration/test_pulse_repository.py -q`

### Task 3 — Worker Edge Enqueue

- [ ] Update/add worker tests:
  - `test_source_seed_events_are_not_enqueued_or_persisted`
  - `test_unchanged_edge_state_does_not_enqueue`
  - `test_edge_status_change_enqueues_once`
  - `test_edge_budget_blocks_fourth_enqueue`
  - `test_budget_rejection_preserves_latest_observed_state`
  - `test_failed_agent_run_finishes_with_failed_outcome`
  - `test_successful_candidate_persists_last_edge_events`
- [ ] Run and confirm fail:
  `uv run pytest tests/unit/test_pulse_candidate_worker.py -q`
- [ ] Implement worker changes.
- [ ] Run and confirm pass:
  `uv run pytest tests/unit/test_pulse_candidate_worker.py -q`

### Task 4 — Routing and Harness Cleanup

- [ ] Update tests:
  - `tests/unit/test_pulse_agent_routing.py`
  - `tests/unit/test_pulse_agent_runtime.py`
  - `tests/unit/test_pulse_agent_decision.py`
- [ ] Remove source_seed assumptions.
- [ ] Run:
  `uv run pytest tests/unit/test_pulse_agent_routing.py tests/unit/test_pulse_agent_runtime.py tests/unit/test_pulse_agent_decision.py -q`

### Task 5 — Notification Edge Semantics

- [ ] Add/modify tests:
  - `tests/unit/test_notification_rules.py::test_signal_pulse_notification_payload_includes_edge_events`
  - `tests/unit/test_notification_rules.py::test_signal_pulse_notifications_exclude_theme_watch`
  - `tests/integration/test_notification_repository.py::test_signal_pulse_duplicate_requires_same_notification_signature`
  - `tests/integration/test_notification_repository.py::test_stale_running_delivery_is_reclaimed_when_attempts_remain`
  - `tests/integration/test_notification_repository.py::test_stale_running_delivery_is_dead_when_attempts_exhausted`
- [ ] Run and confirm fail:
  `uv run pytest tests/unit/test_notification_rules.py tests/integration/test_notification_repository.py -q`
- [ ] Implement notification changes.
- [ ] Run and confirm pass:
  `uv run pytest tests/unit/test_notification_rules.py tests/integration/test_notification_repository.py -q`

### Task 6 — API / Frontend Hard Cut

- [ ] Update API tests:
  - `tests/integration/test_api_http.py::test_signal_pulse_rejects_theme_watch_status`
  - Update summary expectations to remove `theme_watch`.
- [ ] Update frontend tests/types/fixtures for no `theme_watch`.
- [ ] Run:
  `uv run pytest tests/integration/test_api_http.py -q`
  `cd web && npm test -- --run`

### Task 7 — Architecture and Generated Docs

- [ ] Update `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/RELIABILITY.md`.
- [ ] Regenerate contracts/docs:
  - `make docs-generated`
  - `make regen-contract`
- [ ] Run architecture tests:
  `uv run pytest tests/architecture -q`

## Rollout Order

1. Apply Alembic migration.
2. Deploy code that no longer references `cooldown_until_ms`, `source_seed`, `theme_watch`, or `pending outcome`.
3. Start single ASGI worker as usual.
4. Observe `/api/status` pulse and notification blocks.
5. Run post-deploy SQL metric queries from the spec acceptance section.

## Rollback

1. Stop worker process.
2. Revert code commit.
3. Alembic downgrade one revision if needed.
4. Restart process.
5. Deleted legacy `source_seed` / `theme_watch` Pulse rows are not restored; upstream event/resolution audit remains available.

## Acceptance Test Commands

- Edge unit tests:
  `uv run pytest tests/unit/test_pulse_edge_events.py -q`
- Pulse worker:
  `uv run pytest tests/unit/test_pulse_candidate_worker.py -q`
- Pulse repository:
  `uv run pytest tests/integration/test_pulse_repository.py -q`
- Notifications:
  `uv run pytest tests/unit/test_notification_rules.py tests/integration/test_notification_repository.py tests/integration/test_notification_delivery.py -q`
- API:
  `uv run pytest tests/integration/test_api_http.py -q`
- Frontend:
  `cd web && npm test -- --run`
- Full gate:
  `make check-all`

## Verification

Create or update `docs/superpowers/plans/active/2026-05-14-pulse-worker-edge-notifications-hard-cut-verification-cn.md` before claiming completion. The verification artefact must include full `make check-all` output, Coverage, Skipped tests, E2E golden path, and residual risks.
