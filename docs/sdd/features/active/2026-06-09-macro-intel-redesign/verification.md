# Verification — Macro Intel Workbench Redesign

**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
**Branch**: `codex/macro-intel-redesign`
**Diff**: pending implementation

The redesign is not complete. This file currently records design-stage evidence only.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — Overview first-screen desk brief | Pending | Implementation not migrated yet. |
| AC2 — Asset dashboard first | Pending | Implementation partially exists but must be refactored and verified against final grammar. |
| AC3 — Generic leaf workbench grammar | Pending | Old leaf stack still exists. |
| AC4 — Rates shares grammar | Pending | Rates still uses separate grammar. |
| AC5 — Correlation matrix workbench grammar | Pending | Correlation shares table components but not final workbench frame. |
| AC6 — No overflow at target viewports | Pending | Final implementation not migrated yet. |
| AC7 — No retired selectors/compat assumptions | Pending | Old route test assumptions still exist. |
| AC8 — Visual mockup exists and renders | Partial | See visual mockup check below. |

Deviations from spec:

- None approved.

Deviations from plan:

- None approved.

## Verification commands

Full completion verification has not run.

```text
$ make check-all
not run; implementation is pending.
```

## Coverage

Not measured yet. Frontend redesign work will use targeted component, route, architecture, typecheck, build, and Playwright gates before any completion claim.

## Skipped tests

Not measured yet.

## E2E golden path

Not measured yet.

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

## Diff summary

Design-stage files changed:

- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/spec.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/plan.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/tasks.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/verification.md`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`
- `docs/sdd/features/active/2026-06-09-macro-intel-redesign/macro-visual-mockup.png`

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- None planned.

## Risks observed

- The visual companion server script did not emit a session directory in the Codex PTY, so the visual稿 was produced as a committed local HTML/PNG artifact instead.
- Current route tests still preserve a stale "no macro module nav on mobile/tablet" assumption.
- Current generic leaf pages remain old equal-weight panel stacks until implementation tasks run.

## Follow-ups

- Execute Tasks 2-9 before any completion claim.
- After implementation verification, decide whether this SDD directory should move to `docs/sdd/features/completed/`.
