# Verification — Macro Live Evidence Lenses and DeepAgents Research Separation

**Status**: In Progress
**Date**: 2026-07-24
**Owning spec**: `docs/sdd/features/active/2026-07-24-macro-live-evidence-lenses/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-24-macro-live-evidence-lenses/plan.md`
**Branch**: `codex/deepagents-macro-hard-cut`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Approved by**: user and GitHub Issue #8
**Approved at**: 2026-07-24

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Live dashboard and research card. | Pass | Route/component tests and four-viewport browser tests render six category cards plus compact persisted research context. |
| AC2 - Six complete detail routes. | Pass | All six routes hard-load with summary cards, selectable history, searchable complete rows, and source/timing fields in four viewports. |
| AC3 - Separated immutable research route. | Pass | `/macro/research` continues to render the persisted completed-session artifact; live detail pages contain only a link. |
| AC4 - Persisted-only API. | Pass | API tests spy on one repository session and prove zero provider/model/write execution; unknown views, windows, query tokens, and extra parameters fail explicitly. |
| AC5 - 108 metadata concepts plus uncatalogued facts. | Pass | Catalog unit test proves exactly 108 unique presentation concepts across six views; dashboard tests preserve bounded uncatalogued facts. |
| AC6 - Exact clocks and row-local availability. | Pass | Unit/API/UI tests preserve source timestamp, observation date, received time, request read time, read health, and missing rows independently. |
| AC7 - Transparent calculations without semantic labels. | Pass | Unit and architecture tests cover disclosed difference/return/spread/accounting/correlation formulas and forbid deterministic direction/confidence/readiness/gate fields. |
| AC8 - No projection or judgment regression. | Pass | Architecture/migration tests prove retired judgment, snapshot, projection, generic model gateway, and compatibility surfaces remain deleted. |
| AC9 - DeepAgents capability preserved. | Pass | Existing topology, checkpoint, native filesystem/execute, subagent, citation, immutable publication, and replay tests pass unchanged. |
| AC10 - Responsive and interactive browser behavior. | Pass | Playwright reports 32/32 across 1366, 1920, 834, and 390 widths; auto/manual refresh, URL window, hard loads, final-table reachability, and overflow are covered. |
| AC11 - Generated contracts and docs aligned. | Pass | OpenAPI, TypeScript types, DB schema, SDD index, canonical docs, and mirrored routers were regenerated and pass drift/docs tests. |
| AC12 - Main merge and production image verification. | In progress | Implementation pending. |

## Verification commands

- `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/test_api_macro_contract.py tests/unit/test_api_openapi_exact_contracts.py tests/unit/test_docs_contract.py tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q` — 68 passed.
- `make regen-contract && make docs-generated` — regenerated OpenAPI, TypeScript types, DB schema, CLI help, score versions, WebSocket protocol, and SDD work index.
- `make check` — ruff, formatting, mypy over 515 source files, frontend type/lint/architecture/format, 2,429 Python unit/architecture/contract tests passed, one opt-in live provider drift test skipped, and compileall passed.
- `cd web && npm test -- --run` — 71 files / 272 tests passed.
- `cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list` — 32 tests passed across all four configured viewport projects.
- `git diff --check` — passed.

```text
$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed before task completion.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q
6 passed in 0.02s.
exit code: 0

$ uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
25 passed in 2.52s.
exit code: 0

$ cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx
2 files and 13 tests passed.
exit code: 0

$ test -f web/tests/routes/macro.route.test.tsx && (cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx)
2 files and 13 tests passed.
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_docs_contract.py -q
6 passed in 1.04s.
exit code: 0

$ make check
Ruff/format/mypy/frontend checks passed; 2,429 tests passed and one opt-in live provider-drift test skipped; compileall passed.
exit code: 0

$ cd web && npm test -- --run
71 files and 272 tests passed.
exit code: 0

$ cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list
32 tests passed across desktop-1366, desktop-1920, tablet-834, and mobile-390.
exit code: 0

$ git diff --check
No whitespace errors.
exit code: 0
```

## Deviations

None recorded.

## Risks observed

- The target branch contains the full uncommitted DeepAgents hard cut, so the
  final audit must verify both that work and this product correction together.

## Follow-ups

None recorded.
