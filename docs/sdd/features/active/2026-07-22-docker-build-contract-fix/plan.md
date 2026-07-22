# Plan — Docker build contract repair

**Status**: Review
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/spec.md`
**Worktree**: `.worktrees/docker-build-contract-fix/`
**Branch**: `codex/docker-build-contract-fix`
**Approved by**: user request to build and start the image
**Approved at**: 2026-07-22

## Pre-flight

- [x] Spec is approved.
- [x] Worktree exists and branch is `codex/docker-build-contract-fix`.
- [x] Baseline backend lint/tests are inherited from commit `62a1b2ac`.
- [x] Known failing baseline: `npm run build` reports nine TypeScript contract errors.

Known-failing baseline tests:

- No behavioural test failures; the production type-check fails before Vite build.

## File-level edits

### Frontend production contracts

- `web/src/lib/types/index.ts`: export the existing `WorkerStatusData` canonical type.
- `web/src/features/macro/model/macroChartModel.ts`: place the required minimum-point argument before the optional payload.
- `web/src/lib/api/client.ts`: return the news agent payload with its validated status value.

### Frontend typed fixtures

- `web/tests/component/features/news/NewsPage.test.tsx`: express the complete current news source and classification shape.
- `web/tests/component/features/news/NewsTape.test.tsx`: express the same current row shape and narrow optional status overrides.
- `web/tests/unit/features/notifications/api/notifications.test.ts`: inject a retired field as runtime unknown data rather than claiming it is typed.
- `web/tests/unit/features/notifications/useNotificationsController.test.tsx`: type the empty live-notification input.

### Storage / migrations

- None.

### Tests

- Existing tests remain the behavioural contract; `npm run typecheck` is the failing-first reproduction and regression gate.

## PR breakdown

1. **PR 1 — build contract repair**: all listed static contract and fixture edits; mergeable as one atomic build fix.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: each baseline compiler diagnostic has one explicit owner above. |
| Plan preserves canonical architecture boundaries. | Pass: existing current contracts and boundary validators remain owners. |
| Compatibility code or old files are not retained. | Pass: no alias, optional retired field, or fallback shape is added. |
| Parallel touch/conflict sets are explicit. | Pass: single parent owns the bounded frontend touch set. |

## Rollout order

1. Repair strict frontend contract errors in the isolated worktree.
2. Run type-check, tests, architecture harness, lint, and production build.
3. Commit and merge the atomic repair to `main`.
4. Rebuild/start Docker from `main` and check health/readiness.

## Rollback

Revert the atomic commit and rebuild the previous image. There are no migrations, persisted-data changes, or irreversible steps.

## Acceptance test commands

- AC1: `cd web && npm run typecheck && npm run build`
- AC2: `cd web && npm run lint && npm run test:architecture && npm test -- --run`
- AC3: `make docker-up && make docker-status && curl --fail http://localhost:8765/healthz && curl --fail http://localhost:8765/readyz`

## Verification

Evidence is recorded in `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/verification.md`. This bounded repair will remain in Review unless the repository-wide no-skip completion gate is run successfully.
