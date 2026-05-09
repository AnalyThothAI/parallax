# Spec / Plan Templates

These templates encode the lane structure described in `AGENTS.md` and `CLAUDE.md`. Copy a template into the appropriate lane and rename it to a dated slug. Do not edit the templates in place when working on a feature.

## Lanes

| Lane | Path | Purpose |
|------|------|---------|
| Spec | `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` | `Why & what` — the design a reviewer can debate without reading code. |
| Plan | `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` | `How & when` — file:line edits, SQL, migrations, PR breakdown. |
| Tasks | `docs/superpowers/plans/YYYY-MM-DD-<slug>/tasks.md` | TDD-ordered checklist when a plan spans multiple PRs. |
| Verification | `docs/superpowers/plans/YYYY-MM-DD-<slug>/verification.md` | Evidence the work meets the spec before marking complete. |

A small change uses single-file specs and plans. A change that spans more than one PR or needs explicit task ordering uses a directory:

```
docs/superpowers/specs/2026-05-09-gmgn-account-directory-sync/
  spec.md
docs/superpowers/plans/2026-05-09-gmgn-account-directory-sync/
  plan.md
  tasks.md
  verification.md
```

## Naming

- Date prefix: today's date in `YYYY-MM-DD`. Do not back-date.
- Slug: short, intent-focused, kebab-case. `gmgn-account-directory-sync` not `improve-things`. Match the worktree branch slug when one exists.
- One slug per feature. Re-use the same slug across spec, plan, tasks, and verification so the lanes link by name.

## Lifecycle

1. **Brainstorm** — talk to the user, understand the goal. No file yet.
2. **Spec** — copy `spec-template.md`, fill in background / problem / goals / non-goals / acceptance criteria. Get user approval.
3. **Plan** — copy `plan-template.md`, fill in file:line edits, SQL, tests, PR breakdown. Get user approval.
4. **Tasks** (optional) — copy `tasks-template.md` for multi-PR work. Update statuses as you go.
5. **Implement** — work in a `.worktrees/<slug>/` worktree following the plan.
6. **Verify** — fill in `verification-template.md` with command output and diff summary before declaring complete.

The order matters: spec before plan, plan before code, code before verification. Skipping a lane is a smell — push back to the user and ask which lane to fall back to before writing.

## What templates are not

- They are not contracts to copy verbatim. Delete sections that do not apply, but do not invent new top-level headings.
- They are not a substitute for reading existing services. The spec template's "Background" section must cite real `src/` files; otherwise the design is ungrounded.
- They are not exhaustive. ADR (`docs/superpowers/adr/`) and Research (`docs/superpowers/research/`) lanes can be added when a need arises; do not pre-create empty directories.
