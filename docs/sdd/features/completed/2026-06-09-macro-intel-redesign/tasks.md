# Tasks - Macro Intel Workbench Redesign

**Status**: Superseded
**Owning plan**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/plan.md`
**Worktree**: `.worktrees/macro-intel-redesign/`
**Branch**: `codex/macro-intel-redesign`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Superseded by**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/`

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | Superseded spec records current successor ownership. |
| Checklist | Superseded spec keeps the current requirement checklist table. |
| Analyze | Superseded plan records the successor-owned Analyze Gate. |
| Implement | Historical macro tasks remain structured and marked `[!]` because successor work owns current harness evidence. |
| Verify | Verification artifact retains historical command output without claiming current completion. |

## Tasks

### Task 1 - Visual spec and mockup

- **File(s)**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/spec.md`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/spec.md`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroModulePages.test.tsx::macro_workbench_contract` - historical design target for macro workbench grammar.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Spec/plan
- **Deterministic constraints**: Historical design evidence must remain in the four canonical SDD artifacts only.
- **On-demand context**: `docs/FRONTEND.md`, `docs/DESIGN_DISCIPLINE.md`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`.
- **Kill/defer criteria**: Stop if old visual attachments or compatibility archives are required.
- **Eval/repair signal**: unexpected-artifact or missing successor metadata.
- **Implementation**: Write the grounded spec and visual target for overview, asset dashboard, generic module, rates, and mobile.
- **Verification**: `cd web && node --input-type=module scripts/render-macro-workbench-mockup.mjs`
- **Review owner**: parent
- **Status**: [!]

### Task 2 - Workbench grammar tests

- **File(s)**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroModulePages.test.tsx::macro_workbench_contract` - historical grammar assertions preceded production changes.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests describe visible macro workbench grammar rather than old panel order.
- **On-demand context**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`.
- **Kill/defer criteria**: Stop if route tests preserve retired mobile navigation assumptions.
- **Eval/repair signal**: stale component expectation or route navigation compatibility drift.
- **Implementation**: Replace old panel-order expectations with spec acceptance criteria.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 3 - Shared workbench model and UI foundation

- **File(s)**: `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroModulePages.test.tsx::macro_workbench_contract` - historical tests failed before shared workbench components existed.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: View models remain pure display derivation and do not fetch, score, or mutate macro reads.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`.
- **Kill/defer criteria**: Stop if UI components recompute backend macro conclusions.
- **Eval/repair signal**: frontend data ownership drift or macro architecture test failure.
- **Implementation**: Add read strip, fact table, evidence lanes, diagnostics summary, and page-frame components.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 4 - Overview and generic module migration

- **File(s)**: `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/pages/MacroMarketBoard.tsx`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/pages/MacroMarketBoard.tsx`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroModulePages.test.tsx::macro_workbench_contract` - historical tests asserted new macro regions before migration.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Overview and generic pages use the shared workbench grammar and avoid equal-weight legacy panel stacks.
- **On-demand context**: `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`.
- **Kill/defer criteria**: Stop if old standalone metric/source/health regions must remain visible as compatibility surfaces.
- **Eval/repair signal**: old region labels, stale route tests, or macro page grammar drift.
- **Implementation**: Replace old equal-weight panel stacks with shared workbench regions.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 5 - Asset dashboard decomposition

- **File(s)**: `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/model/macroAssetOverviewModel.ts`, `web/src/features/macro/ui/assets`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/model/macroAssetOverviewModel.ts`, `web/src/features/macro/ui/assets`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroModulePages.test.tsx::macro_workbench_contract` - historical asset assertions required dashboard-first rendering.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Asset page orchestration stays small and reusable derivation moves into model helpers.
- **On-demand context**: `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `docs/FRONTEND.md`.
- **Kill/defer criteria**: Stop if local parsing remains mixed into the page component.
- **Eval/repair signal**: oversized asset page, stale compatibility selectors, or dashboard group collapse.
- **Implementation**: Split the asset page into dashboard, daily brief, correlation preview, and diagnostics components.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 6 - Rates workbench convergence

- **File(s)**: `web/src/features/macro/ui/rates`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/macro/ui/rates`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx::macro_rates_workbench_contract` - historical rates tests asserted shared read and diagnostics grammar.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Rates can keep specialized charts while sharing read, fact, evidence, and diagnostics semantics.
- **On-demand context**: `web/src/features/macro/ui/rates`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`.
- **Kill/defer criteria**: Stop if rates-specific CSS duplicates shared workbench layout without semantic need.
- **Eval/repair signal**: rates label drift, duplicated diagnostics, or raw backend keys in UI.
- **Implementation**: Retain rates-specific visuals while using shared workbench sections.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 7 - Correlation matrix convergence

- **File(s)**: `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`, `web/src/features/macro/ui/correlation`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`, `web/src/features/macro/ui/correlation`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/component/features/macro/MacroAssetCorrelationPage.test.tsx::macro_correlation_workbench_contract` - historical correlation tests asserted matrix workspace grammar.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Correlation page keeps matrix controls accessible and uses shared diagnostics semantics.
- **On-demand context**: `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`, `web/src/features/macro/ui/correlation`.
- **Kill/defer criteria**: Stop if matrix controls or strongest-pair evidence become hidden behind decorative layout.
- **Eval/repair signal**: correlation page grammar drift or inaccessible window controls.
- **Implementation**: Wrap the matrix page in the shared workbench frame and keep shared correlation tables.
- **Verification**: `cd web && npm test -- --run tests/component/features/macro/MacroAssetCorrelationPage.test.tsx -x`
- **Review owner**: parent
- **Status**: [!]

### Task 8 - CSS and compatibility deletion

- **File(s)**: `web/src/features/macro/ui/pages/macroPages.css`, `web/src/features/macro/ui/primitives/macroPanel.css`, `web/tests/architecture/macroResponsiveHardCut.test.ts`
- **Owner**: parent
- **Depends on**: Tasks 4-7
- **Touch set**: `web/src/features/macro/ui/pages/macroPages.css`, `web/src/features/macro/ui/primitives/macroPanel.css`, `web/tests/architecture/macroResponsiveHardCut.test.ts`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/architecture/macroResponsiveHardCut.test.ts::macro_responsive_hard_cut_contract` - historical architecture test rejected retired macro selectors and stale compatibility assumptions.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Retired macro primitive files and old selectors cannot return as compatibility surfaces.
- **On-demand context**: `docs/FRONTEND.md`, `web/tests/architecture/macroResponsiveHardCut.test.ts`.
- **Kill/defer criteria**: Stop if retired selectors must remain for old snapshots or routes.
- **Eval/repair signal**: retired selector hits, owner CSS drift, or frontend architecture harness failure.
- **Implementation**: Remove obsolete selectors, keep owner CSS under budgets, and assert hard-cut selectors in architecture tests.
- **Verification**: `cd web && npm run test:architecture && npm run lint:eslint`
- **Review owner**: parent
- **Status**: [!]

### Task 9 - Golden path and full verification

- **File(s)**: `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`
- **Owner**: parent
- **Depends on**: Tasks 2-8
- **Touch set**: `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-11-executable-harness-followup for successor-owned harness evidence.
- **Failing test first**: `web/tests/e2e/golden-paths/macro-terminal.spec.ts::macro_terminal_contract` - historical golden path asserted overview, asset, rates, mobile drawer, and no overflow.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Final integration
- **Deterministic constraints**: Historical runtime evidence remains in verification.md and does not claim current make-check-all completion.
- **On-demand context**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`, `web/tests/e2e/golden-paths/macro-terminal.spec.ts`.
- **Kill/defer criteria**: Stop if integration or golden reruns are required for this superseded record.
- **Eval/repair signal**: runtime evidence ambiguity, skipped-test confusion, or final completion claim drift.
- **Implementation**: Record golden-path and repository-gate evidence in the verification artifact.
- **Verification**: `cd web && npm run build && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project desktop-1366 --project desktop-1920 --project tablet-834 --project mobile-390 --project mobile-430`
- **Review owner**: parent
- **Status**: [!]
