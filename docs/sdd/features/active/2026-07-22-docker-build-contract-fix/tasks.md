# Tasks — Docker build contract repair

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/plan.md`
**Worktree**: `.worktrees/docker-build-contract-fix/`
**Branch**: `codex/docker-build-contract-fix`
**Approved by**: user request to build and start the image
**Approved at**: 2026-07-22

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below begin from the failing production type-check. |
| Verify | `verification.md` captures bounded command evidence. |

## Tasks

### Task 1 — Repair production type ownership

- **File(s)**: `web/src/lib/types/index.ts`, `web/src/features/macro/model/macroChartModel.ts`, `web/src/lib/api/client.ts`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `web/src/lib/types/index.ts`, `web/src/features/macro/model/macroChartModel.ts`, `web/src/lib/api/client.ts`
- **Conflict set**: `src/parallax/`; `docs/CONTRACTS.md`
- **Failing test first**: `web/tests/unit/features/macro/macroChartModel.test.ts::production typecheck` — `cd web && npm run typecheck` reproduces the public-export, parameter-order, and news-narrowing failures.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Complete the canonical export, order required/optional parameters, and construct a typed payload from validated data without casts.
- **Verification**: `cd web && npm run typecheck`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: strict TypeScript, no compatibility shape, no `as` escape hatch.
- **On-demand context**: `docs/FRONTEND.md`; affected model/type files.
- **Kill/defer criteria**: stop if a public backend contract change becomes necessary.
- **Eval/repair signal**: remaining compiler diagnostics.
- **Status**: [~]

### Task 2 — Align tests with current contracts

- **File(s)**: `web/tests/component/features/news/NewsPage.test.tsx`, `web/tests/component/features/news/NewsTape.test.tsx`, `web/tests/unit/features/notifications/api/notifications.test.ts`, `web/tests/unit/features/notifications/useNotificationsController.test.tsx`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `web/tests/component/features/news/NewsPage.test.tsx`, `web/tests/component/features/news/NewsTape.test.tsx`, `web/tests/unit/features/notifications/api/notifications.test.ts`, `web/tests/unit/features/notifications/useNotificationsController.test.tsx`
- **Conflict set**: `web/src/`
- **Failing test first**: `web/tests/component/features/news/NewsPage.test.tsx::production typecheck` — `cd web && npm run typecheck` reproduces all fixture errors.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Make fixtures satisfy current required fields and keep intentionally invalid data outside the static contract.
- **Verification**: `cd web && npm run typecheck && npm test -- --run`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: do not weaken production types.
- **On-demand context**: current news and notification types.
- **Kill/defer criteria**: stop if tests reveal a product semantic mismatch.
- **Eval/repair signal**: type-check and Vitest failures.
- **Status**: [ ]

### Task 3 — Build and start the current image

- **File(s)**: `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/verification.md`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/verification.md`
- **Conflict set**: `src/parallax/`; `web/src/`
- **Failing test first**: `web/tests/component/features/news/NewsPage.test.tsx::docker production build` — baseline `make docker-up` failed during `npm run build`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Merge the verified repair to main, rebuild/start Compose, and inspect health/readiness.
- **Verification**: `make docker-up && make docker-status`
- **Review owner**: parent agent
- **Factory lane**: Final integration
- **Deterministic constraints**: use `~/.parallax` config paths; never reveal credential values.
- **On-demand context**: `docs/SETUP.md`, `docs/SECURITY.md`.
- **Kill/defer criteria**: stop on migration failure or persistent readiness failure and report exact diagnostics.
- **Eval/repair signal**: Docker build exit, compose health, `/healthz`, `/readyz`.
- **Status**: [ ]
