# Verification — Macro Intel Workbench Redesign

**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
**Branch**: `codex/macro-intel-redesign`
**Diff**: first implementation slice pending commit

The full redesign is not complete. This file records the first implementation slice: shared workbench model/components, overview and generic leaf migration, rates naming/diagnostics convergence, and updated macro tests.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — Overview first-screen desk brief | Partial | Overview now renders `宏观简报`, `跨域市场板`, `传导链`, `数据诊断`; component and route tests pass. |
| AC2 — Asset dashboard first | Partial | Existing asset landing tests still pass; component decomposition is not done yet. |
| AC3 — Generic leaf workbench grammar | Partial | Generic leaf now renders `模块简报`, `主市场证据`, `驱动与反证`, `数据诊断`; old standalone metric/source/health regions removed from leaf page. |
| AC4 — Rates shares grammar | Partial | Rates regions renamed to `利率简报`, `利率主图`, `数据诊断`; diagnostics/source detail now live in one diagnostics region. |
| AC5 — Correlation matrix workbench grammar | Pending | Correlation shares table components but not final workbench frame. |
| AC6 — No overflow at target viewports | Partial | Macro responsive audit passes across its internal route/viewport matrix. |
| AC7 — No retired selectors/compat assumptions | Partial | Lint/architecture harness passes; full old compatibility deletion is still pending. |
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

## Coverage

Targeted macro component, route, unit, architecture, and Playwright coverage was exercised. Full completion gates remain open because asset decomposition, matrix convergence, and full old-code deletion are not finished.

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
- Migrated `MacroOverviewModulePage.tsx` to four clear regions.
- Migrated `MacroLeafModulePage.tsx` to four clear regions and folded extra tables into `主市场证据`.
- Consolidated rates diagnostics into a single `数据诊断` region and aligned rates labels with the shared grammar.
- Updated component, route, unit, and E2E tests for the new IA.

Schema or contract changes that consumers must be aware of:

- None planned.

## Risks observed

- The visual companion server script did not emit a session directory in the Codex PTY, so the visual稿 was produced as a committed local HTML/PNG artifact instead.
- Asset overview remains a large component and still needs decomposition.
- Correlation matrix has not been migrated into the shared workbench grammar.
- Some old primitives remain because asset/matrix pages still use them; complete deletion should wait until remaining migrations land.

## Follow-ups

- Execute Tasks 5, 7, 8, and the remaining full verification gates before any completion claim.
- After implementation verification, decide whether this SDD directory should move to `docs/sdd/features/completed/`.
