# Tasks — Docs and Ops KISS Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/plan.md`
**Worktree**: `.worktrees/docs-ops-kiss-hard-cut/`
**Branch**: `codex/docs-ops-kiss-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records deletion and preservation decisions. |
| Checklist | Every requirement has a direct high-level seam. |
| Analyze | `plan.md` identifies replacement owners before deletion. |
| Implement | Tasks hard-delete old surfaces without aliases or archives. |
| Verify | `verification.md` records focused direct commands. |

## Tasks

### Task 1 — Hard-cut stale documentation and the local subagent factory

- **File(s)**: `docs/`, `scripts/`, `tests/architecture/`, `tests/unit/`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/`, `scripts/`, `tests/architecture/`, `tests/unit/`
- **Conflict set**: `src/parallax/`, `web/`
- **Failing test first**: `tests/architecture/test_docs_surface_contract.py::test_current_docs_surface_contains_only_owned_buckets` rejects the legacy buckets and non-reproducible generated tree.
- **Implementation**: Delete obsolete docs/artifacts and local packet/dispatch/report machinery; retain core SDD evidence validation and completed history.
- **Verification**: `uv run pytest tests/architecture/test_docs_surface_contract.py tests/unit/test_validate_sdd_artifacts.py tests/unit/test_sdd_work_index.py -q`
- **Status**: [x]

### Task 2 — Remove browser/API Ops duplication

- **File(s)**: `src/parallax/app/surfaces/api/http.py`, `src/parallax/app/surfaces/api/schemas.py`, `tests/unit/test_api_ops_contract.py`, `web/src/routes/router.tsx`, `web/src/features/cockpit/`, `web/src/shared/routing/paths.ts`, `web/tests/`, `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `src/parallax/app/surfaces/api/http.py`, `src/parallax/app/surfaces/api/schemas.py`, `tests/unit/test_api_ops_contract.py`, `web/src/routes/router.tsx`, `web/src/features/cockpit/`, `web/src/shared/routing/paths.ts`, `web/tests/`, `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`
- **Removed file(s)**: `src/parallax/app/operations/diagnostics.py`, `src/parallax/app/surfaces/api/routes_ops.py`, `tests/unit/test_ops_diagnostics.py`, `web/src/features/ops/`, `web/src/routes/ops.route.tsx`
- **Conflict set**: `src/parallax/app/operations/queue_health.py`, `src/parallax/app/surfaces/cli/`, `src/parallax/domains/`, `src/parallax/platform/db/`
- **Failing test first**: `tests/unit/test_api_ops_contract.py::test_retired_browser_ops_endpoints_are_not_found` requires ordinary 404 while status remains available.
- **Implementation**: Delete the browser Ops module and dedicated HTTP diagnostics transport; keep status/readiness and direct CLI operations.
- **Verification**: `uv run pytest tests/unit/test_api_ops_contract.py tests/integration/test_cli.py -q && cd web && npm run lint && npm run typecheck`
- **Status**: [x]

### Task 3 — Consolidate canonical docs and close the hard cut

- **File(s)**: `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `docs/generated/`, `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/`
- **Owner**: parent
- **Depends on**: Tasks 1-2
- **Touch set**: `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `docs/generated/`, `docs/sdd/features/completed/2026-07-23-docs-ops-kiss-hard-cut/`
- **Conflict set**: `src/parallax/domains/`, `src/parallax/platform/db/alembic/versions/`, `ops/`
- **Failing test first**: `tests/integration/test_docs_generated.py::test_expected_generated_files` rejects stale non-reproducible generated artifacts.
- **Implementation**: Rewrite README and canonical maps around the retained owners, regenerate contracts, record evidence, and archive the SDD.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check`
- **Status**: [x]
