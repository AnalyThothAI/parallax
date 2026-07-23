# Tasks — Token Radar Content Age and Tape Frontend Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut/plan.md`
**Worktree**: `.worktrees/token-radar-content-age-hard-cut/`
**Branch**: `codex/token-radar-content-age-hard-cut`
**Approved by**: user and GitHub Issue #7
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records the user-approved semantic boundaries. |
| Checklist | `spec.md` includes a testable requirement checklist and acceptance criteria. |
| Analyze | `plan.md` records current owners, risks, test seams, rollout, and rollback. |
| Implement | Tasks are ordered behavioral contract first, implementation second, verification last. |
| Verify | `verification.md` will contain command receipts only after successful execution. |

## Tasks

### Task 1 — Establish the active SDD and failing contracts

- **File(s)**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut`, `docs/generated/sdd-work-index.md`, `web/tests/routes/live-radar.route.test.tsx`, `web/tests/component/shared/socket/IntelSocketProvider.test.tsx`, `web/tests/architecture`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut`, `docs/generated/sdd-work-index.md`, `web/tests/routes/live-radar.route.test.tsx`, `web/tests/component/shared/socket/IntelSocketProvider.test.tsx`, `web/tests/architecture`
- **Conflict set**: `web/src`
- **Failing test first**: `tests/routes/live-radar.route.test.tsx::advances_current_view_content_age_without_extra_requests`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Encode Issue #7 in active SDD and add external-behavior expectations before production edits.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py`
- **Review owner**: parent
- **Factory lane**: Spec/tests
- **Deterministic constraints**: one route-level state machine; no source assertions outside the narrow hard-cut boundary.
- **On-demand context**: Issue #7, `docs/DEVELOPMENT.md`, `docs/FRONTEND.md`
- **Kill/defer criteria**: repair contradictory identity, cache, or accessibility semantics before implementation.
- **Eval/repair signal**: SDD validator and focused Vitest failures.
- **Status**: [x]

### Task 2 — Implement exact Radar content-age and refresh health

- **File(s)**: `web/src/features/live/api/useTokenRadarQuery.ts`, `web/src/features/live/api/useLiveRadarRouteData.ts`, `web/src/features/live/model`, `web/src/features/live/ui/TokenRadarTable.tsx`, `web/src/features/live/ui/LiveRadar.tsx`, `web/src/features/live/ui/live.css`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `web/src/features/live/api/useTokenRadarQuery.ts`, `web/src/features/live/api/useLiveRadarRouteData.ts`, `web/src/features/live/model`, `web/src/features/live/ui/TokenRadarTable.tsx`, `web/src/features/live/ui/LiveRadar.tsx`, `web/src/features/live/ui/live.css`
- **Conflict set**: `web/src/shared/socket`, `web/src/routes/live.route.tsx`
- **Failing test first**: `tests/routes/live-radar.route.test.tsx::advances_current_view_content_age_without_extra_requests`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Record current-identity true HTTP success, preserve last-good frames, derive status, and render a one-second non-interactive two-row header.
- **Verification**: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- **Review owner**: parent
- **Factory lane**: Frontend domain implementation
- **Deterministic constraints**: unchanged query-cache shape and ten-second cadence; no age alert threshold or network side effect.
- **On-demand context**: token-radar generated types and live-market cache patch implementation
- **Kill/defer criteria**: do not claim healthy from placeholder data or cache patch timestamps.
- **Eval/repair signal**: fake-clock, identity, row-preservation, and accessibility failures.
- **Status**: [x]

### Task 3 — Hard-delete frontend Tape and narrow the socket

- **File(s)**: `web/src/routes/live.route.tsx`, `web/src/routes/shellChromeData.ts`, `web/src/app`, `web/src/features/live`, `web/src/shared/socket`, `web/src/shared/query/queryKeys.ts`, `web/tests`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `web/src/routes/live.route.tsx`, `web/src/routes/shellChromeData.ts`, `web/src/app`, `web/src/features/live`, `web/src/shared/socket`, `web/src/shared/query/queryKeys.ts`, `web/tests`
- **Conflict set**: `src/parallax`
- **Failing test first**: `tests/component/shared/socket/IntelSocketProvider.test.tsx::subscribes_without_replay_or_event_storage`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Remove recent/Tape/event/mobile-task frontend ownership, send replay zero, ignore event messages, and preserve notification/market behavior.
- **Verification**: `cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx tests/architecture/liveRadarTapeHardCut.test.ts`
- **Review owner**: parent
- **Factory lane**: Frontend architecture hard cut
- **Deterministic constraints**: no backend recent/event/replay source edits and no compatibility wrappers.
- **On-demand context**: socket market-target and cache-patch tests
- **Kill/defer criteria**: restore any notification or market-target regression before deleting the replaced path.
- **Eval/repair signal**: focused socket, architecture, route, and type failures.
- **Status**: [x]

### Task 4 — Align responsive browser behavior and canonical docs

- **File(s)**: `web/src/features/live/ui/live.css`, `web/tests/e2e/golden-paths/live-cold-load.spec.ts`, `web/tests/e2e/golden-paths/mobile-shell.spec.ts`, `web/tests/e2e`, `docs/FRONTEND.md`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/live/ui/live.css`, `web/tests/e2e/golden-paths/live-cold-load.spec.ts`, `web/tests/e2e/golden-paths/mobile-shell.spec.ts`, `docs/FRONTEND.md`
- **Conflict set**: `web/src/routes`; `src/parallax`
- **Failing test first**: `tests/e2e/golden-paths/live-cold-load.spec.ts::live_cold_load`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Make Radar full height, remove task-bar space, preserve final-row reachability, and document the page-local status contract.
- **Verification**: `cd web && npm run test:e2e -- tests/e2e/golden-paths/live-cold-load.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390`
- **Review owner**: parent
- **Factory lane**: Browser/docs
- **Deterministic constraints**: no fifth viewport, no unrelated screenshot churn, no CSS ownership bypass.
- **On-demand context**: current Playwright mock API and layout helpers
- **Kill/defer criteria**: repair overflow, hidden status, or unreachable final rows before accepting snapshots.
- **Eval/repair signal**: request log, overflow, reachability, and snapshot failures.
- **Status**: [x]

### Task 5 — Complete requirement-by-requirement verification

- **File(s)**: `web/src`, `web/tests`, `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut`, `docs/generated/sdd-work-index.md`, `tests/unit`
- **Owner**: parent
- **Depends on**: Task 4
- **Touch set**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `web/src`; `tests/unit`
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Run focused/full frontend and selected backend gates, audit every AC and residual name, record exact evidence, and move the feature directory to completed.
- **Verification**: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- **Review owner**: parent
- **Factory lane**: Final integration
- **Deterministic constraints**: no completion from static scan or narrow tests alone; report omitted lanes honestly.
- **On-demand context**: final diff and all prior command receipts
- **Kill/defer criteria**: keep the goal active while any acceptance criterion lacks direct evidence.
- **Eval/repair signal**: full suite, browser, residual, documentation, and SDD gate failures.
- **Status**: [x]
