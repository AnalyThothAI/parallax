# Plan — Docs and Ops KISS Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/spec.md`
**Worktree**: `.worktrees/docs-ops-kiss-hard-cut/`
**Branch**: `codex/docs-ops-kiss-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-23

## Pre-flight

- [x] Current main and root worktree state inspected.
- [x] Isolated worktree created from `main@416f8be8`.
- [x] Three task-complete Review SDDs passed the direct-evidence verify gate.

Known-failing baseline tests:

- None known in the focused documentation, API Ops, or frontend architecture
  seams.

## File-level edits

### Documentation tree

- Delete `docs/mockups/`, `docs/prototypes/`, `docs/reviews/`, stale internal
  references, and non-reproducible `docs/generated/` artifacts.
- Keep completed SDDs as history and reduce `sdd-work-index.md` to active work.
- Replace fragmented worker/reliability/debug docs with one concise
  `docs/OPERATIONS.md`.
- Replace workflow/design/testing/playbook duplication with one concise
  `docs/DEVELOPMENT.md`.
- Rewrite README and router maps to the new owners.

### Agent/SDD harness

- Delete context-packet, dispatch, mode-constraint, and subagent-report scripts.
- Remove their validator rules, issue codes, templates, and generated receipts.
- Keep core SDD structure, acceptance mapping, task completion, active conflict
  detection, and successful command evidence.

### Ops hard cut

- Remove `routes_ops.py`, the API-only diagnostics operation, and Ops response
  schemas.
- Remove the React Ops route, feature bundle, fixtures, styles, navigation,
  topbar button, and tests.
- Keep runtime status/readiness, CLI `ops`, and queue-health implementation.
- Regenerate OpenAPI and frontend types.

### Lifecycle cleanup

- Move the backend KISS, Docker build, and News retention SDDs from `active` to
  `completed` after their recorded direct evidence passes verify.
- Add focused negative-contract tests for retired Ops routes and documentation
  buckets.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: docs, SDD harness, backend API, frontend route, contracts, and tests cover G1-G5. |
| Replacement owners are explicit. | Pass: status/readiness plus CLI replace browser/API Ops; canonical docs replace artifact buckets. |
| Compatibility code is avoided. | Pass: retired routes return ordinary 404 and deleted docs are not archived elsewhere. |
| Material runtime boundaries are preserved. | Pass: facts, workers, migrations, providers, CLI Ops, and queue health remain unchanged. |

## Rollout order

1. Add focused failing contracts for the target docs and Ops surfaces.
2. Delete stale docs/generated/factory artifacts.
3. Remove browser/API Ops and regenerate contracts.
4. Consolidate canonical docs and README.
5. Run focused verification, residual scans, and SDD lifecycle validation.

## Rollback

Revert the feature commit. No database or provider state changes are involved.

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_docs_surface_contract.py tests/integration/test_docs_generated.py -q`
- AC2: `uv run pytest tests/architecture/test_docs_surface_contract.py -q`
- AC3: `uv run pytest tests/unit/test_api_ops_contract.py tests/integration/test_cli.py -q && cd web && npm run lint && npm run typecheck`
- AC4: `uv run pytest tests/unit/test_validate_sdd_artifacts.py tests/unit/test_sdd_work_index.py -q`
- AC5: `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check`

## Verification

Verification evidence lives in
`docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/verification.md`.
