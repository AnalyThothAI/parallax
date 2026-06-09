# Verification — Macro Intel Workbench Redesign

**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
**Branch**: `codex/macro-intel-redesign`
**Diff**: third implementation slice pending commit

The full redesign is not complete. This file records implementation progress through the third slice: shared workbench model/components, overview and generic leaf migration, rates naming/diagnostics convergence, asset overview decomposition, correlation detail convergence, CSS/compatibility deletion, and updated macro tests.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — Overview first-screen desk brief | Partial | Overview now renders `宏观简报`, `跨域市场板`, `传导链`, `数据诊断`; component and route tests pass. |
| AC2 — Asset dashboard first | Partial | Asset page keeps `市场仪表盘`, `今日判断`, `60日相关性`, `数据诊断`; 509-line page was split into model plus owner UI components. |
| AC3 — Generic leaf workbench grammar | Partial | Generic leaf now renders `模块简报`, `主市场证据`, `驱动与反证`, `数据诊断`; old standalone metric/source/health regions removed from leaf page. |
| AC4 — Rates shares grammar | Partial | Rates regions renamed to `利率简报`, `利率主图`, `数据诊断`; diagnostics/source detail now live in one diagnostics region. |
| AC5 — Correlation matrix workbench grammar | Partial | Correlation detail now renders `相关性简报`, `相关性矩阵`, `相关性证据`, `数据诊断`; component and route tests pass. |
| AC6 — No overflow at target viewports | Partial | Macro responsive audit passes across its internal route/viewport matrix. |
| AC7 — No retired selectors/compat assumptions | Met for current macro frontend | Architecture harness now rejects retired primitive files and old macro metric/read/evidence/health/transmission selectors; lint/architecture passes. |
| AC8 — Visual mockup exists and renders | Partial | See visual mockup check below. |

Deviations from spec:

- None approved.

Deviations from plan:

- None approved.

## Verification commands

```text
$ cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx
Test Files  2 passed (2)
Tests  16 passed (16)

$ cd web && npm test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx
Test Files  1 passed (1)
Tests  15 passed (15)

$ cd web && npm test -- --run tests/component/features/macro tests/unit/features/macro tests/routes/macro.route.test.tsx
Test Files  18 passed (18)
Tests  100 passed (100)

$ cd web && npm run lint
Test Files  11 passed (11)
Tests  64 passed (64)

$ cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 --project=mobile-390
4 passed, 4 skipped

$ cd web && npx playwright test tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
```

Second-slice verification:

```text
$ cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx tests/routes/macro.route.test.tsx
Test Files  3 passed (3)
Tests  18 passed (18)

$ cd web && npm test -- --run tests/component/features/macro tests/unit/features/macro tests/routes/macro.route.test.tsx
Test Files  18 passed (18)
Tests  100 passed (100)

$ cd web && npm run lint
Test Files  11 passed (11)
Tests  64 passed (64)

$ cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 --project=mobile-390
4 passed, 4 skipped

$ cd web && npx playwright test tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
```

Third-slice CSS/compatibility deletion verification:

```text
$ cd web && npx vitest run tests/architecture/macroResponsiveHardCut.test.ts
Test Files  1 passed (1)
Tests  5 passed (5)

$ cd web && npm run lint
Test Files  11 passed (11)
Tests  65 passed (65)

$ cd web && npm run typecheck
tsc --noEmit exited 0

$ cd web && npm test -- --run tests/component/features/macro tests/unit/features/macro tests/routes/macro.route.test.tsx
Test Files  17 passed (17)
Tests  98 passed (98)

$ cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 --project=mobile-390
4 passed, 4 skipped

$ cd web && npx playwright test tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
```

## Coverage

Targeted macro component, route, unit, architecture, and Playwright coverage was exercised. Full completion gates remain open because final full-gate build/e2e coverage, manual visual review, and SDD completion movement are not finished.

## Skipped tests

Not skipped in unit/component/route/lint runs. The macro terminal Playwright command intentionally skipped desktop-only tests in the mobile project and mobile-only tests in the desktop project.

## E2E golden path

Macro terminal desktop/mobile sample passed. Macro responsive audit passed for `desktop-1366`; that spec iterates its own product/hidden route and viewport matrix.

## Other commands run

Visual mockup render check:

```text
$ node --input-type=module <playwright file-open script>
{
  "title": "Macro Intel Workbench Visual Mockup",
  "sectionCount": 5,
  "horizontalOverflow": false,
  "bodyHeight": 4002
}
exit code: 0
```

Rendered preview:

- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.png`

Reference comparison:

```text
$ curl -I -L -A 'Mozilla/5.0 ... Chrome/126 Safari/537.36' https://timsun.net/assets/
HTTP/2 200

$ curl -sL -A 'Mozilla/5.0 ... Chrome/126 Safari/537.36' https://timsun.net/assets/ | rg -n '<h[1-4]|<section|资产|相关|交叉分析'
Observed asset groups, cross-asset correlation section, and cross-analysis prose.
```

Comparison notes:

- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/timsun-assets-comparison.md`

Local browser tooling note:

- Browser/DevTools MCP calls timed out in this Codex session.
- Playwright CLI was used instead for real-browser verification with the repository mock API.

## Diff summary

Design-stage files changed:

- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/tasks.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/verification.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.png`

Migrations applied in this slice:

- Added `web/src/features/macro/model/macroWorkbenchModel.ts`.
- Added `web/src/features/macro/ui/workbench/` brief, driver, diagnostics components and CSS.
- Added `web/src/features/macro/model/macroAssetOverviewModel.ts`.
- Added `web/src/features/macro/model/macroAssetOverviewTypes.ts`.
- Added `web/src/features/macro/ui/assets/` asset dashboard, daily brief, correlation preview, diagnostics components and owner CSS.
- Added `web/src/features/macro/ui/correlation/CorrelationRead.tsx`.
- Migrated `MacroOverviewModulePage.tsx` to four clear regions.
- Migrated `MacroLeafModulePage.tsx` to four clear regions and folded extra tables into `主市场证据`.
- Reduced `MacroAssetOverviewPage.tsx` from a 509-line mixed component to a 119-line page orchestration component.
- Consolidated rates diagnostics into a single `数据诊断` region and aligned rates labels with the shared grammar.
- Migrated `MacroMatrixPage.tsx` to `相关性简报`, `相关性矩阵`, `相关性证据`, and `数据诊断`.
- Removed retired macro primitives: `MacroMetricStrip`, `MacroReadPanel`, `MacroEvidencePanel`, `MacroDataHealthPanel`, and `MacroTransmissionPanel`.
- Deleted `macroMetricStrip.css`, reduced `macroPanel.css` to panel ownership only, and moved asset diagnostics health styles into `macroAssetOverview.css`.
- Strengthened `macroResponsiveHardCut.test.ts` so retired macro primitive files and generic metric/read/evidence/health/transmission selectors fail architecture tests.
- Updated responsive Playwright label-fragmentation checks to inspect the new table/read surfaces instead of the deleted metric strip compatibility marker.
- Updated component, route, unit, and E2E tests for the new IA.

Schema or contract changes that consumers must be aware of:

- None planned.

## Risks observed

- The visual companion server script did not emit a session directory in the Codex PTY, so the visual稿 was produced as a committed local HTML/PNG artifact instead.
- `timsun.net/assets/` shows ETF/options/positioning depth and a heatmap correlation view that Parallax does not yet expose.
- Full visual parity is not the target, but our first-screen density and analyst narrative still need refinement beyond testable IA.

## Follow-ups

- Execute Task 9, remaining visual refinement, and full verification gates before any completion claim.
- After implementation verification, decide whether this SDD directory should move to `docs/sdd/features/completed/`.
