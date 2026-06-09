# Plan — Macro Intel Workbench Redesign

**Status**: Draft
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
**Worktree**: `.worktrees/macro-intel-redesign/`
**Branch**: `codex/macro-intel-redesign`

## Pre-flight

- [x] Worktree exists at `.worktrees/macro-intel-redesign/` and `git branch --show-current` returns `codex/macro-intel-redesign`.
- [x] Visual mockup exists at `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`.
- [ ] Spec reviewed against implementation before final verification.
- [ ] Baseline frontend checks recorded.

Baseline issue resolved in first implementation slice:

- `web/tests/routes/macro.route.test.tsx` now asserts macro module navigation reachability/active state on mobile/tablet instead of preserving the old absence assumption.

## File-level edits

### SDD artifacts

- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`: product architecture and acceptance criteria.
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`: overall visual mockup for overview, asset dashboard, generic module, rates, and mobile.
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.png`: rendered preview generated from the HTML mockup.
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/verification.md`: final command output and manual UI evidence.

### `web/src/features/macro/ui/workbench/`

Create a new workbench UI folder that owns the common macro product grammar.

- `MacroWorkbenchPage.tsx`: shell-internal page layout component for read strip, module navigation slot, main grid, and diagnostics placement.
  - Props: title metadata, `children`, optional rail/subnav, optional diagnostics summary.
- `MacroReadStrip.tsx`: first-screen read summary with headline, explanation, regime/readiness/as-of/action facts.
- `MacroFactTable.tsx`: compact table for market rows and facts using TanStack table where sorting matters; simple semantic table when rows are already ordered.
- `MacroEvidenceLanes.tsx`: grouped evidence/decision lanes for confirmations, contradictions, watch triggers, invalidations, and module-specific groups.
- `MacroDiagnosticsSummary.tsx`: compact module health summary plus expandable/detail section for sources and gaps.
- `macroWorkbench.css`: common workbench layout and typography. It must stay under 500 lines and use only `.macro-workbench-*` selectors.

### `web/src/features/macro/model/`

- `macroWorkbenchModel.ts`: pure transformation layer from `MacroModuleView` to workbench semantic objects. It must not fetch, score, or mutate.
  - Build read strip view.
  - Build diagnostics summary view.
  - Build evidence lane view.
  - Build market rows from module tables.
- `macroModulePresentation.ts`: keep only generic scalar/table helpers that remain useful; move page-specific derivations into `macroWorkbenchModel.ts`.
- `macroRatesWorkbenchModel.ts`: keep rates-specific calculations but return shared read/diagnostic/evidence shapes where possible.

### `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`

- Replace the current equal-weight panel stack at lines 24-54 with the overview command page grammar.
- First region: `宏观简报`.
- Second region: `跨域市场板`.
- Supporting regions: `传导链`, `数据诊断`.
- Remove overview use of `MacroMetricStrip` as a standalone panel; facts should be embedded in the read strip or market board.

### `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`

- Split the current 500-line component into:
  - asset page orchestration component.
  - asset group market board component.
  - daily brief component.
  - diagnostics adapter.
- Keep the market-dashboard-first order but align visual hierarchy with the mockup.
- Remove local parsing/formatting that belongs in the model layer when it is reused by tests or other pages.

### `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`

- Replace the old sequence at lines 35-84 with generic module workbench grammar.
- Delete the standalone `关键指标`, `数据来源`, and `模块数据健康` regions as first-class equal panels.
- New ordered regions: `模块简报`, `主市场证据`, `驱动与反证`, `数据诊断`.
- Detail/source tables remain available inside diagnostics or a lower detail section.

### `web/src/features/macro/ui/rates/`

- `MacroRatesModulePage.tsx`: adopt shared workbench slots while retaining rates-specific subnav and primary visual.
- `RatesMarketRead.tsx`, `RatesFactStrip.tsx`, `RatesDecisionSupport.tsx`, `RatesDiagnosticsPanel.tsx`: reduce custom layout duplication by using shared read strip, fact table, evidence lanes, and diagnostics where semantics match.
- `macroRatesWorkbench.css`: remove styles that duplicate shared workbench CSS; keep only rates-specific chart and subnav styles.

### `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`

- Keep shared correlation table components.
- Adopt workbench page frame and diagnostics styling.
- Ensure window controls remain accessible and visible in the header/action slot.

### CSS cleanup

- `web/src/features/macro/ui/pages/macroPages.css`: keep only page-specific asset/market styles; move shared layout to `macroWorkbench.css`.
- `web/src/features/macro/ui/primitives/macroPanel.css`: stop carrying macro page layout semantics that move to workbench.
- `web/src/features/macro/ui/shell/macroShell.css`: keep shell/navigation only.
- Architecture tests must explicitly reject retired selectors introduced by this hard cut.

### Tests

- `web/tests/component/features/macro/MacroModulePages.test.tsx`: update expected region order for overview, asset, generic leaf, and rates pages.
- `web/tests/component/features/macro/MacroShell.test.tsx`: keep module navigation assertions and add mobile/tablet semantics if needed.
- `web/tests/routes/macro.route.test.tsx`: replace old no-module-nav assertions with reachability/active-state assertions.
- `web/tests/component/features/macro/MacroAssetCorrelationPage.test.tsx`: assert matrix page uses workbench grammar.
- `web/tests/architecture/macroResponsiveHardCut.test.ts`: add retired selector/test assumptions to guard against compatibility backslide.
- `web/tests/e2e/golden-paths/macro-terminal.spec.ts`: update golden paths for overview command page, asset dashboard, generic leaf, rates page, and no horizontal overflow.

## PR breakdown

1. **PR 1 — Visual spec and workbench foundation**: SDD artifacts, visual mockup, workbench model/components, CSS shell.
2. **PR 2 — Page migration**: overview, asset, generic leaf, rates, matrix page replacements.
3. **PR 3 — Old code deletion and verification**: remove retired primitives/selectors/tests, run full gates, record verification.

The current branch may implement these in one working sequence, but the diff should remain reviewable by these slices.

## Rollout order

1. Merge frontend-only workbench and page changes.
2. Build production bundle.
3. Verify macro golden paths across desktop, tablet, and mobile Playwright projects.
4. Record manual UI evidence in `verification.md`.

No backend rollout or migration is required.

## Rollback

Rollback is a normal git revert of the frontend commits. Since no backend contracts change, reverting restores the prior macro page grammar and tests. The visual SDD artifacts can remain as superseded planning records if the implementation is reverted.

## Acceptance test commands

- AC1-AC5: `cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx tests/component/features/macro/MacroShell.test.tsx`
- AC6: `cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project desktop-1366 --project desktop-1920 --project tablet-834 --project mobile-390 --project mobile-430`
- AC7: `cd web && npm run test:architecture && npm run lint:eslint && npm run typecheck`
- AC8: `cd web && node <local visual mockup screenshot script>` or equivalent Playwright file-open check recorded in `verification.md`.
- Production bundle: `cd web && npm run build`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-09-macro-intel-redesign/verification.md`. The feature is not complete until that artifact contains command output, UI evidence, remaining risks, and the diff review against this plan.
