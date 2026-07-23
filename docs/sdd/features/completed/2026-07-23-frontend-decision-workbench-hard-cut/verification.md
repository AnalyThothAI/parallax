# Verification — Parallax Frontend Decision Workbench Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/plan.md`
**Branch**: `codex/frontend-decision-workbench-hard-cut`
**Worktree**: `.worktrees/frontend-decision-workbench-hard-cut/`
**Approved by**: delegated user goal and GitHub Issue #5
**Approved at**: 2026-07-23
**Diff**: final rebased hard cut changes 165 tracked files, with retired production files deleted rather than wrapped.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - One Parallax design contract and no old visual compatibility. | Pass | `make check` exited 0; `cd web && npm test -- --run` exited 0; the architecture suite rejects the retired Obsidian files, selectors, tokens, and aliases. |
| AC2 - Task-first shell and stable routes. | Pass | `cd web && npm test -- --run` exited 0 and the four-project Playwright command exited 0 with the five primary destinations and stable route matrix. |
| AC3 - Macro first-screen three-band decision budget. | Pass | `cd web && npm run test:e2e -- tests/e2e/golden-paths/frontend-workbench.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390` exited 0 and accepted the bounded 1920/1366 Macro Overview screenshots. |
| AC4 - Distinct no-shock and insufficient states. | Pass | `make check` exited 0 with the Macro domain/API scenarios; the running operator API returned `no_dominant_shock` separately from the fixture-covered insufficient state. |
| AC5 - Exact eight-lane typed map. | Pass | `make check` exited 0; the live authenticated API smoke returned exactly the ordered eight lane IDs under `macro_decision_v2`. |
| AC6 - Five completed-session comparison without look-ahead. | Pass | The focused real-PostgreSQL Macro migration/projection command exited 0 and the unit calendar/rule suite inside `make check` exited 0. |
| AC7 - Local lane degradation. | Pass | `make check` exited 0 with normal/no-shock/insufficient/local-degradation scenarios; the running Overview displayed gaps only beside affected lanes. |
| AC8 - No holdings/trade/size/score/probability/LLM output. | Pass | `make check` exited 0 with backend/frontend negative guards; live browser inspection found no buy/sell, position, stop, or target instruction. |
| AC9 - One current six-document snapshot and zero-write replay. | Pass | `uv run pytest tests/integration/domains/macro_intel tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/integration/test_macro_decision_workbench_migration.py tests/unit/test_api_macro_contract.py -q` exited 0 and the operator worker published one v2 snapshot from the existing writer. |
| AC10 - Persisted direct reads and no frontend inference. | Pass | `make check` exited 0 with strict API/repository/frontend ownership tests; the live Overview loaded from one authenticated page read after worker publication. |
| AC11 - Progressive audit disclosure with local exceptions. | Pass | `cd web && npm test -- --run` and the four-project Playwright command exited 0; live Overview kept audit collapsed while showing local gaps inline. |
| AC12 - Five explicit domain drilldowns. | Pass | `cd web && npm test -- --run` and the four-project Playwright command exited 0 across all five bespoke Macro routes. |
| AC13 - Complete chart semantics. | Pass | `cd web && npm run test:e2e -- tests/e2e/golden-paths/frontend-workbench.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390` exited 0; live Cross Asset rendered nine SVGs with 20/60-session controls, unit, source, and as-of labels. |
| AC14 - Four-viewport responsive product behavior. | Pass | `cd web && npm run test:e2e -- tests/e2e/golden-paths/frontend-workbench.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390` exited 0 across exactly 1920, 1366, 834, and 390 with 8 passing checks and 36 bounded snapshots. |
| AC15 - Shared state language and partial preservation. | Pass | `cd web && npm test -- --run` exited 0 with 293 tests covering route, component, loading, unavailable, and degraded behavior. |
| AC16 - Projection/API/types/fixtures/docs hard cut. | Pass | `make check` and the focused real-PostgreSQL Macro migration/projection command exited 0; OpenAPI drift, exact schemas, generated TypeScript, migration, and canonical docs agree on v2. |
| AC17 - Focused seams, image/runtime, visual evidence, and final audit. | Pass | `make docker-up`, `make docker-status`, the live authenticated Macro API smoke, `make check`, full frontend Vitest, four-project Playwright, and the final SDD validator/gate commands all exited 0. |

Deviations from spec:

- None. The user-approved final clarification replaces a repository-wide integration regression with the focused Macro PostgreSQL seam plus actual image/runtime validation.

Deviations from plan:

- `make test-integration` was explicitly interrupted at 32% on 2026-07-23 at the user's direction because the broad suite may contain stale tests. It is not reported as passing. The already-green focused 16-test Macro PostgreSQL seam was retained, and the final gate used the built operator image, `0192` migration, real v2 worker rebuild, authenticated API, and visible browser.

## Verification commands

```text
$ make check
Ruff and format passed.
mypy: Success: no issues found in 523 source files.
Frontend typecheck, ESLint, architecture 70/70, and format passed.
Python unit/architecture/contract: 2571 passed, 1 opt-in provider-drift skipped.
exit code: 0

$ uv run pytest tests/integration/domains/macro_intel tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/integration/test_macro_decision_workbench_migration.py tests/unit/test_api_macro_contract.py -q
16 passed
exit code: 0

$ uv run pytest tests/contract/test_openapi_drift.py -q
4 passed
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
6 passed
exit code: 0

$ test -f tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py && test -f tests/integration/domains/macro_intel/test_macro_evidence_projection.py && test -f web/tests/component/features/cockpit/ui/AppSidebar.test.tsx && test -f web/tests/routes/live-radar.route.test.tsx && test -f web/tests/routes/macro.route.test.tsx && test -f web/tests/e2e/golden-paths/frontend-workbench.spec.ts
All task-bound failing-test paths exist and are covered by the adjacent successful suite commands.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py -q
243 passed
exit code: 0

$ cd web && npm test -- --run
Test Files 73 passed (73)
Tests 293 passed (293)
exit code: 0

$ cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx && npm run lint && npm run typecheck
AppSidebar: 6 passed; architecture: 70 passed; ESLint and TypeScript passed.
exit code: 0

$ cd web && npm test -- --run tests/routes/live-radar.route.test.tsx
4 passed
exit code: 0

$ cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroDecisionHardCut.test.ts
30 passed
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/frontend-workbench.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390
8 passed; scan, case, monitoring, and six decision-oriented Macro pages matched all four viewport baselines.
exit code: 0

$ make docker-up
Production frontend: 1930 modules transformed.
Images parallax-app, parallax-migrate, and parallax-postgres-observability built.
Migration container validated revision 20260723_0192 and exited successfully.
Application container started.
exit code: 0

$ make docker-status
PostgreSQL and app containers healthy.
/readyz reports migration_version=expected_migration_version=20260723_0192 and composition ok.
exit code: 0

$ docker compose exec -T app parallax macro status
facts_max_observed_at=2026-07-23; projection_behind_facts resolved after the worker iteration.
macrodata-cli 0.1.22 exposes every required series and bundle.
exit code: 0

$ bootstrap_json="$(curl -fsS http://127.0.0.1:8765/api/bootstrap)"; api_token="$(printf '%s' "$bootstrap_json" | jq -r '.data.ws_token')"; curl -fsS -H "Authorization: Bearer $api_token" http://127.0.0.1:8765/api/macro/overview | jq
ok=true; projection_version=macro_decision_v2; lane_count=8; key_change_count=3;
nearest_catalyst and core_invalidation present.
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
SDD work index is current.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-23-frontend-decision-workbench-hard-cut --gate verify
verify gate passed.
exit code: 0
```

Additional live browser receipt:

- `http://127.0.0.1:8765/macro`: decision archetype, eight lanes, no horizontal overflow, no prohibited trade text, and zero console errors.
- `http://127.0.0.1:8765/macro/cross-asset`: decision archetype, nine SVGs, no horizontal overflow, and zero console errors.

## Diff summary

- Macro domain/API: `macro_decision_v2`, exact shock/lane/change/catalyst/invalidation schemas, completed-session comparison, local degradation, and derived-only revision `0192`.
- Frontend: one Parallax token system and shell, four page archetypes, fixed eight-lane Overview, five explicit chart drilldowns, progressive audit, and hard deletion of the Obsidian/evidence-first production contract.
- Verification: strict generated contracts, normal/no-shock/insufficient/local-degradation fixtures, exact four-viewport visual matrix, 36 screenshot baselines, non-empty migration coverage, and actual Docker/runtime receipts.
- Documentation: frontend, architecture, contracts, development, Macro domain map, and this completed SDD describe the same supported product.

## Risks observed

- Revision `0192` was applied to the local operator PostgreSQL volume. It is deliberately irreversible but deletes only rebuildable v1 derived rows; material `macro_observations` were preserved and the real worker rebuilt v2.
- The repository-wide integration regression was not completed and is not claimed. Focused Macro real-PostgreSQL checks and actual runtime behavior are the approved completion seam.

## Follow-ups

- None for this hard cut. Any LLM interpretation, personalized portfolio view, trading instruction, or sizing capability requires a separate spec.
