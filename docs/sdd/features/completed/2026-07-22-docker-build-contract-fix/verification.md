# Verification — Docker build contract repair

**Status**: Verified
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/completed/2026-07-22-docker-build-contract-fix/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-22-docker-build-contract-fix/plan.md`
**Branch**: `codex/docker-build-contract-fix`
**Worktree**: `.worktrees/docker-build-contract-fix/`
**Approved by**: user request to build and start the image
**Approved at**: 2026-07-22
**Diff**: commit `81fb87ba` — 12 files changed, 388 insertions, 14 deletions.

The plan and spec are the contract. Evidence is filled after the bounded verification commands complete.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - production type-check/build | Pass | `npm run typecheck` and `npm run build` exited 0. |
| AC2 - frontend behavioural/architecture gates | Pass | `npm test -- --run` and `npm run lint` exited 0. |
| AC3 - Docker healthy/ready | Pass | `make docker-status` exited 0 after the final main image built successfully. |

Deviations from spec:

- None observed.

Deviations from plan:

- None observed.

## Verification commands

The repository-wide `make check-all` completion transcript is intentionally not claimed yet.

```text
$ make check-all
not run for this bounded Docker build repair
exit code: not run
```

Current regression receipt after the later Macro hard cut removed the historical
chart model:

```text
$ PATH=/Users/qinghuan/Documents/code/parallax/web/node_modules/.bin:$PATH npm --prefix web test -- --run /Users/qinghuan/Documents/code/parallax/.worktrees/macro-evidence-ai-hard-cut/web/tests/unit/features/cockpit/model/statusCurrentContract.test.ts
Test Files  1 passed (1)
Tests       4 passed (4)
exit code: 0
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not run | repository gate | In Progress |
| branch | Not run | repository gate | In Progress |

## Skipped tests

Not yet measured in this feature run.

## E2E golden path

- [x] `/readyz` returned 200
- [x] Docker service is healthy
- [x] Current image was rebuilt from repaired `main`

Broad event/WS E2E is outside this bounded repair.

## Completion gate

The retired aggregate completion gate is not required; direct evidence above
closes this bounded repair.

## Other commands run

```text
$ npm run typecheck
TypeScript completed with zero errors
exit code: 0

$ npm test -- --run
105 files passed; 748 tests passed
exit code: 0

$ npm run lint
ESLint passed; 180 architecture tests passed
exit code: 0

$ npm run build
Vite production build completed
exit code: 0

$ test -f web/tests/unit/features/macro/model/macroChartModel.test.ts && cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts
15 targeted macro model tests passed
exit code: 0

$ test -f web/tests/component/features/news/NewsPage.test.tsx && cd web && npm test -- --run tests/component/features/news/NewsPage.test.tsx
targeted NewsPage tests passed
exit code: 0

$ make docker-status
app and PostgreSQL healthy; migration 20260722_0187 ready
exit code: 0
```

## Diff summary

- Production contract repair: three source files and four typed fixture files.
- SDD execution record and generated index.

Migrations applied:

- None introduced by this repair.

Schema or contract changes:

- None; static code and fixtures are aligned to the existing current contract.

## Risks observed

- The standard frontend test/lint lane did not catch production type-check drift; evaluate a consolidated verification gate separately.

## Follow-ups

- Perform a separate evidence-driven backend/frontend KISS complexity audit after live startup.
