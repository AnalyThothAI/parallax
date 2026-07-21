# Verification — Macro Intel Workbench Redesign

**Status**: Superseded
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/plan.md`
**Branch**: `codex/macro-intel-redesign`
**Worktree**: `.worktrees/macro-intel-redesign/`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Superseded by**: `docs/sdd/features/completed/2026-06-11-executable-harness-followup/`
**Diff**: final implementation slice committed on `codex/macro-intel-redesign`

This file records the Macro Intel frontend redesign implementation: shared workbench model/components, overview and generic leaf migration, rates naming/diagnostics convergence, asset overview decomposition, correlation detail convergence, CSS/compatibility deletion, golden-path coverage, and visual review screenshots.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — Overview first-screen desk brief | Met | Overview renders `宏观简报`, `跨域市场板`, `传导链`, `数据诊断`; component, route, e2e, and screenshot evidence pass. |
| AC2 — Asset dashboard first | Met | Asset page renders `市场仪表盘`, `今日判断`, `60日相关性`, `数据诊断`; dashboard now keeps all five asset groups visible even when data is sparse. |
| AC3 — Generic leaf workbench grammar | Met | Generic leaf renders `模块简报`, `主市场证据`, `驱动与反证`, `数据诊断`; old standalone metric/source/health regions are absent. |
| AC4 — Rates shares grammar | Met | Rates renders `利率简报`, `关键事实`, `利率主图`, `决策支持`, `利率明细`, `数据诊断`; raw backend keys are excluded before diagnostics. |
| AC5 — Correlation matrix workbench grammar | Met | Correlation detail renders `相关性简报`, `相关性矩阵`, `相关性证据`, `数据诊断`; matrix and pair evidence use shared correlation components. |
| AC6 — No overflow at target viewports | Met | Macro responsive audit passes across its internal route/viewport matrix; macro-terminal passes desktop, tablet, and mobile projects. |
| AC7 — No retired selectors/compat assumptions | Met | Current macro frontend architecture harness now rejects retired primitive files and old macro metric/read/evidence/health/transmission selectors; lint/architecture passes. |
| AC8 — Visual mockup exists and renders | Superseded | Legacy visual/mockup attachments were removed by the SDD four-artifact hard cut; successor record owns current harness evidence. |

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

Final implementation verification:

```text
$ cd web && npm run lint:eslint
eslint --max-warnings=0 exited 0

$ cd web && npm run test:architecture
Test Files  11 passed (11)
Tests  65 passed (65)

$ cd web && npm run typecheck
tsc --noEmit exited 0

$ cd web && npm test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/routes/macro.route.test.tsx
Test Files  5 passed (5)
Tests  37 passed (37)

$ cd web && npm run build
tsc --noEmit exited 0
vite build exited 0
Warning observed: Some chunks are larger than 500 kB after minification.

$ cd web && npx playwright test tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 --project=desktop-1920 --project=tablet-834 --project=mobile-390 --project=mobile-430
13 passed, 12 skipped

$ cd web && npx playwright test tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
```

## Coverage

Targeted macro component, route, unit, architecture, build, and Playwright coverage was exercised. Final closeout uses repository `make check` only; per user instruction on 2026-06-09, integration tests and full `make check-all` were not continued because they were too time-consuming.

Repository non-integration gate:

```text
$ PATH=/opt/homebrew/bin:$PATH make check
External make-check output attachment removed by the SDD four-artifact hard cut.
exit code: 0
```

Full-gate note:

```text
$ PATH=/opt/homebrew/bin:$PATH make check-all
Stopped during tests/integration after the user said: "不要跑集成测试了 太耗时了"
No full `make check-all` pass is claimed.
```

## Skipped tests

Not skipped in unit/component/route/lint runs. The macro terminal Playwright command intentionally skipped desktop-only tests in the mobile project and mobile-only tests in the desktop project.

## E2E golden path

Macro terminal now asserts overview, asset, and rates workbench grammar across `desktop-1366`, `desktop-1920`, `tablet-834`, `mobile-390`, and `mobile-430`. Desktop-only and mobile-only tests intentionally skip non-target projects. Macro responsive audit passed for `desktop-1366`; that spec iterates its own product/hidden route and viewport matrix.

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

Rendered preview and actual implementation screenshot attachments were removed by
the SDD four-artifact hard cut; current evidence belongs in the successor
record.

Manual visual review:

- Overview: first viewport gives a clear desk brief followed by the cross-domain market board.
- Asset dashboard: all five asset groups are visible in a stable market-dashboard frame; sparse data is shown as group-level empty states instead of collapsing the page shape.
- Rates: rates-specific navigation and facts remain visible while the shared read/diagnostics grammar is preserved.
- Correlation: matrix, summary, and pair evidence are readable with no overlap.
- Mobile asset page: macro shell, tabs, asset dashboard, and first market group are contained without horizontal document overflow.

Reference comparison:

```text
$ curl -I -L -A 'Mozilla/5.0 ... Chrome/126 Safari/537.36' https://timsun.net/assets/
HTTP/2 200

$ curl -sL -A 'Mozilla/5.0 ... Chrome/126 Safari/537.36' https://timsun.net/assets/ | rg -n '<h[1-4]|<section|资产|相关|交叉分析'
Observed asset groups, cross-asset correlation section, and cross-analysis prose.
```

Comparison note attachment removed by the SDD four-artifact hard cut.

Local browser tooling note:

- Browser/DevTools MCP calls timed out in this Codex session.
- Playwright CLI was used instead for real-browser verification with the repository mock API.

## Diff summary

Design-stage files changed:

- `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/spec.md`
- `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/plan.md`
- `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/tasks.md`
- `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`

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
- Stabilized the asset dashboard model so equities, bonds, commodities, FX, and crypto groups always render; sparse groups show explicit empty rows.
- Adjusted the asset dashboard layout so desktop group tables expose code, name, latest, daily change, and date without hiding key columns behind horizontal scroll.
- Removed retired macro primitives: `MacroMetricStrip`, `MacroReadPanel`, `MacroEvidencePanel`, `MacroDataHealthPanel`, and `MacroTransmissionPanel`.
- Deleted `macroMetricStrip.css`, reduced `macroPanel.css` to panel ownership only, and moved asset diagnostics health styles into `macroAssetOverview.css`.
- Strengthened `macroResponsiveHardCut.test.ts` so retired macro primitive files and generic metric/read/evidence/health/transmission selectors fail architecture tests.
- Updated responsive Playwright label-fragmentation checks to inspect the new table/read surfaces instead of the deleted metric strip compatibility marker.
- Updated component, route, unit, and E2E tests for the new IA.

Schema or contract changes that consumers must be aware of:

- None planned.

## Risks observed

- The visual companion server script did not emit a session directory in the Codex PTY, so the visual稿 was produced as a committed local HTML/PNG artifact instead.
- `timsun.net/assets/` shows ETF/options/positioning depth that Parallax does not yet expose. Adding those surfaces requires backend/product scope beyond this frontend redesign.
- Full `make check-all` was intentionally not completed per user instruction on 2026-06-09; integration, backend e2e, golden, and coverage gates are not used as final evidence for this closeout.

## Follow-ups

- Consider a backend/product follow-up for ETF/options/positioning macro asset depth.
- Re-run integration/golden only if explicitly needed later; skipped here by user request.
