# Workflow

> **Scope.** Owns the spec → plan → tasks → verification lane mechanics, the worktree policy, and the completion gates. Design rules (spec vs plan boundary, audit, reuse, complexity, scoring) live in `DESIGN_DISCIPLINE.md`.

## Lane sequence

Trivial single-file low-risk edits may go direct. Everything else uses the lanes below.

| Lane | Path | When |
|------|------|------|
| Spec | `docs/superpowers/specs/active/YYYY-MM-DD-<slug>.md` (or `…/<slug>/spec.md` for very large work) | Before any non-trivial implementation; answers *why & what*. |
| Plan | `docs/superpowers/plans/active/YYYY-MM-DD-<slug>.md` (or `…/<slug>/plan.md`) | After spec approval; answers *how & when* with file:line edits. |
| Tasks | `…/<slug>/tasks.md` | When a plan needs ordered TDD checklists across multiple PRs. |
| Verification | `…/<slug>/verification.md` (or a "Verification" section in a single-file plan) | Before declaring completion or opening a PR. |

Templates live at `docs/superpowers/_templates/`. Copy a template into the appropriate `active/` folder and rename to the dated slug. Naming: `YYYY-MM-DD-<kebab-slug>` matching today's date; keep slugs short and intent-focused.

When work ships and verification is recorded, move both the spec and the plan from `active/` to `completed/`. This is a manual step performed in the same PR that records verification.

Get explicit user approval at each lane boundary; do not write the next lane until the prior is approved.

## Worktree policy

Coding agents MUST work in an isolated git worktree, not the main checkout.

- Default location: `.worktrees/<branch-slug>/` at the repo root. The directory is gitignored.
- Create with: `git worktree add .worktrees/<slug> -b <branch> main` (branch from `main` unless the user names a different base).
- Before any edit verify: `git worktree list`, `git status --short`, `git branch --show-current`.
- Trivial single-file low-risk doc edits may go direct in the main checkout. Anything touching `src/` or `tests/` uses a worktree.
- Existing worktrees in `.worktrees/` belong to other tasks; do not edit them unless explicitly asked.

## Completion gates

Do not claim a task is complete, fixed, or passing until all of the following
are true and have been written into the verification artefact:

- The implementation matches the approved spec; deviations are documented.
- `make check-all` exited 0 in the worktree, AND the verification artefact contains
  its full output (no abridging) plus the new `Coverage`, `Skipped tests`, and
  `E2E golden path` sections.
- The diff was reviewed against the plan.
- UI flows genuinely outside `make check-all` coverage were exercised manually
  and recorded under `Other commands run`.
- Remaining risks and follow-ups are listed and, if non-trivial, appended to
  `docs/TECH_DEBT.md`.

If any of the above cannot be satisfied, surface the gap rather than claiming completion.
