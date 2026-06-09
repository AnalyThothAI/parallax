# Tasks — Macro Intel Workbench Redesign

**Owning plan**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
**Worktree**: `.worktrees/macro-intel-redesign/`

Tasks are TDD-ordered. A task is complete only when its verification command produced the expected output.

## Tasks

### Task 1 — Visual spec and mockup

- **File(s)**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`, `macro-visual-mockup.html`, `macro-visual-mockup.png`
- **Owner**: parent
- **Depends on**: current user goal
- **Touch set**: SDD feature directory only
- **Conflict set**: production code
- **Failing test first**: not applicable; this is the design artifact.
- **Subagent handoff**: not delegated
- **Implementation**: Write the grounded spec and render a visual mockup covering overview, asset dashboard, generic module, rates, and mobile.
- **Verification**: Playwright opens the HTML mockup, confirms 5 frames and no horizontal overflow, and writes PNG preview.
- **Review owner**: parent
- **Status**: [x]

### Task 2 — Workbench grammar tests

- **File(s)**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: macro component/route tests
- **Conflict set**: production macro UI
- **Failing test first**: tests assert new overview, generic leaf, asset, rates, and route navigation grammar before production changes.
- **Subagent handoff**: not delegated
- **Implementation**: Replace old panel-order expectations with spec acceptance criteria.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 3 — Shared workbench model and UI foundation

- **File(s)**: `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/*`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: new macro workbench model/UI files and imports
- **Conflict set**: page migration files unless the tests require a temporary fixture import
- **Failing test first**: Task 2 tests fail because new regions/components are absent.
- **Subagent handoff**: not delegated
- **Implementation**: Add read strip, fact table, evidence lanes, diagnostics summary, and page frame components.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 4 — Overview and generic module migration

- **File(s)**: `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `MacroLeafModulePage.tsx`, `MacroMarketBoard.tsx`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: overview/generic module pages and related page-local CSS
- **Conflict set**: rates page, asset page, correlation page
- **Failing test first**: Task 2 tests for `宏观简报`, `跨域市场板`, `模块简报`, `主市场证据`, `驱动与反证`, `数据诊断`.
- **Subagent handoff**: not delegated
- **Implementation**: Replace old equal-weight panel stacks with the shared workbench grammar.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 5 — Asset dashboard decomposition

- **File(s)**: `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, new asset page subcomponents/model helpers if needed
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: asset overview and asset CSS
- **Conflict set**: generic leaf migration
- **Failing test first**: asset page test asserts market dashboard first, consistent table columns, judgment/correlation/diagnostics order, and no old standalone data-source/data-health regions.
- **Subagent handoff**: not delegated
- **Implementation**: Split the 500-line page into small components and move reusable display derivation into the model layer.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 6 — Rates workbench convergence

- **File(s)**: `web/src/features/macro/ui/rates/*`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: rates model/UI/CSS
- **Conflict set**: generic leaf and asset migrations
- **Failing test first**: rates component tests assert shared read strip, fact evidence, decision lanes, and diagnostics names.
- **Subagent handoff**: not delegated
- **Implementation**: Retain rates-specific visuals while using shared workbench sections.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 7 — Correlation matrix convergence

- **File(s)**: `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`, `web/src/features/macro/ui/correlation/*`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: correlation page/components/CSS
- **Conflict set**: asset correlation preview while Task 5 is active
- **Failing test first**: correlation page test asserts workbench grammar, window controls, matrix, strongest pairs, coverage, and gaps.
- **Subagent handoff**: not delegated
- **Implementation**: Wrap the matrix page in the shared workbench frame and keep shared correlation tables.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroAssetCorrelationPage.test.tsx -x`
- **Review owner**: parent
- **Status**: [x]

### Task 8 — CSS and compatibility deletion

- **File(s)**: `web/src/features/macro/ui/**/*.css`, `web/tests/architecture/macroResponsiveHardCut.test.ts`
- **Owner**: parent
- **Depends on**: Tasks 4-7
- **Touch set**: macro CSS and architecture tests
- **Conflict set**: production TypeScript except import cleanup
- **Failing test first**: architecture test rejects old macro region names/selectors and stale compatibility assumptions.
- **Subagent handoff**: not delegated
- **Implementation**: Remove obsolete selectors, keep owner CSS under budgets, and ensure breakpoint/letter-spacing contracts.
- **Verification**: `cd web && npm run test:architecture && npm run lint:eslint`
- **Review owner**: parent
- **Status**: [x]

### Task 9 — Golden path and full verification

- **File(s)**: `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `docs/sdd/features/active/2026-06-09-macro-intel-redesign/verification.md`
- **Owner**: parent
- **Depends on**: Tasks 2-8
- **Touch set**: macro e2e and verification artifact
- **Conflict set**: production code except bug fixes discovered by e2e
- **Failing test first**: e2e asserts overview command page, asset dashboard, rates page, mobile drawer reachability, and no horizontal overflow.
- **Subagent handoff**: not delegated
- **Implementation**: Update golden paths and record command/manual evidence.
- **Verification**: `cd web && npm run build && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project desktop-1366 --project desktop-1920 --project tablet-834 --project mobile-390 --project mobile-430`
- **Review owner**: parent
- **Status**: [x]

## Final verification

After all tasks are `[x] complete`:

- [x] `cd web && npm run typecheck`
- [x] `cd web && npm run lint:eslint`
- [x] `cd web && npm run test:architecture`
- [x] `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/routes/macro.route.test.tsx`
- [x] `cd web && npm run build`
- [x] `cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project desktop-1366 --project desktop-1920 --project tablet-834 --project mobile-390 --project mobile-430`
- [x] Manual visual check recorded in `verification.md`
- [x] All acceptance criteria from the spec produce expected output.
