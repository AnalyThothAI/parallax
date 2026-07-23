# Verification — Docs and Ops KISS Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/plan.md`
**Branch**: `codex/docs-ops-kiss-hard-cut`
**Worktree**: `.worktrees/docs-ops-kiss-hard-cut/`
**Approved by**: user
**Approved at**: 2026-07-23
**Diff**: Hard-cut stale docs/generated artifacts, local agent coordination scripts, and browser/API Ops; consolidate current owners.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Current docs surface only. | Pass | `uv run pytest tests/architecture/test_docs_surface_contract.py tests/integration/test_docs_generated.py -q` exited 0 with 9 passed. |
| AC2 - Concise README entry point. | Pass | `uv run pytest tests/architecture/test_docs_surface_contract.py -q` exited 0 with 5 passed. |
| AC3 - Browser/API Ops retired. | Pass | `uv run pytest tests/unit/test_api_ops_contract.py tests/integration/test_cli.py -q && cd web && npm run lint && npm run typecheck` exited 0 with 14 backend tests, 2 subtests, 75 frontend architecture tests, lint, and typecheck passed. |
| AC4 - Native SDD workflow only. | Pass | `uv run pytest tests/unit/test_validate_sdd_artifacts.py tests/unit/test_sdd_work_index.py -q` exited 0 with 7 passed. |
| AC5 - Lifecycle and generated contracts close. | Pass | `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check` exited 0. |

Deviations from spec:

- None.

Deviations from plan:

- None.

## Verification commands

```text
$ uv run pytest tests/architecture/test_docs_surface_contract.py tests/integration/test_docs_generated.py -q
9 passed in 43.77s
exit code: 0

$ uv run pytest tests/architecture/test_docs_surface_contract.py -q
5 passed in 0.03s
exit code: 0

$ uv run pytest tests/unit/test_api_ops_contract.py tests/integration/test_cli.py -q && cd web && npm run lint && npm run typecheck
14 passed, 2 subtests passed; ESLint passed; 75 architecture tests passed; TypeScript passed
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py tests/unit/test_sdd_work_index.py -q
7 passed in 8.12s
exit code: 0

$ uv run pytest tests/architecture/test_docs_surface_contract.py tests/unit/test_validate_sdd_artifacts.py tests/unit/test_sdd_work_index.py -q
12 passed in 5.12s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check
SDD artifact validation passed
exit code: 0

$ uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py -q
8 passed in 113.04s
exit code: 0

$ uv run pytest tests/unit/test_queue_health.py tests/unit/test_cli.py tests/integration/test_cli.py -q
21 passed, 2 subtests passed in 184.06s
exit code: 0

$ npm run test -- --run tests/component/features/cockpit/ui/CockpitTopbar.test.tsx tests/unit/routes/shellChromeData.test.ts && npm run build
4 passed; production bundle built successfully
exit code: 0
```

## Diff summary

- Reduced root documentation to seven current owners plus scoped references,
  generated contracts, and SDD history.
- Reduced `docs/generated/` from mixed historical artifacts to seven
  reproducible files.
- Replaced eight overlapping workflow/worker/reliability documents with
  `DEVELOPMENT.md` and `OPERATIONS.md`; README is 144 lines.
- Deleted the local context/dispatch/report harness and reduced the generated
  SDD index to active work.
- Deleted dedicated Ops diagnostics API/schemas and the React Ops feature while
  preserving status/readiness, CLI Ops, and queue health.

## Risks observed

- Full repository `make check`, golden tests, and browser E2E were not run.
  Focused API/CLI, PostgreSQL integration, frontend architecture/component,
  typecheck, lint, and production-build checks crossed the changed seams.
- No database schema, migration, provider, worker, or material-fact behavior
  changed, so migration/golden lanes were not applicable.

## Follow-ups

- None.
