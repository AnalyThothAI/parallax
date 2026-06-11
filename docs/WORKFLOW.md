# Workflow

> **Scope.** Owns the spec → plan → tasks → verification lane mechanics, the worktree policy, and the completion gates. Design rules (spec vs plan boundary, audit, reuse, complexity, scoring) live in `DESIGN_DISCIPLINE.md`.

## Lane sequence

Trivial single-file low-risk edits may go direct. Everything else uses one feature
directory under `docs/sdd/features/active/YYYY-MM-DD-<slug>/` with exactly four
artifacts:

| Artifact | Path | When |
|----------|------|------|
| Spec | `spec.md` | Before any non-trivial implementation; answers *why & what*. |
| Plan | `plan.md` | After spec approval; answers *how & when* with file:line edits. |
| Tasks | `tasks.md` | Before implementation; gives a TDD-ordered checklist and handoff boundaries. |
| Verification | `verification.md` | Before declaring completion or opening a PR. |

Templates live at `docs/sdd/_templates/`. Copy all four templates into the
feature directory. Naming: `YYYY-MM-DD-<kebab-slug>` matching today's date; keep
slugs short and intent-focused. Do not add screenshots, mockups, logs, notes, or
other attachments under the feature directory; the SDD validator reports
`unexpected-artifact` for anything beyond the four canonical artifacts.

For production features or ambiguous work, run the full SDD loop:

```text
spec -> clarify -> checklist -> plan -> tasks -> analyze -> implement -> verify
```

Use `clarify` to resolve requirement ambiguity, `checklist` to validate
requirements quality, and `analyze` to check consistency across spec, plan, and
tasks before implementation starts. Repeat analysis after implementation when
the diff changes the contract.

The loop is executable. Feature records must carry machine-readable
`Approved by`, `Approved at`, `Worktree`, `Branch`, `Touch set`, `Conflict set`,
task verification, and review-owner fields. `uv run python
scripts/validate_sdd_artifacts.py` fails false `Verified` records,
missing gate sections, prose-only `Superseded` successors, incomplete task
coordination fields, and overlapping active touch sets without an explicit
coordination rule.

Active feature records are bounded execution loops, not unbounded project
ledgers. Keep each active `tasks.md` at or below 40 structured tasks. If the
work needs more than 40 structured tasks, split or supersede the active record
and continue in a successor feature; the validator reports
`active-feature-too-large` before oversized active boards can satisfy the
harness.

Each production-feature gate can also be checked directly before moving to the
next lane:

```bash
uv run python scripts/check_sdd_gate.py --feature <slug> --gate clarify
uv run python scripts/check_sdd_gate.py --feature <slug> --gate checklist
uv run python scripts/check_sdd_gate.py --feature <slug> --gate analyze
uv run python scripts/check_sdd_gate.py --feature <slug> --gate implement
uv run python scripts/check_sdd_gate.py --feature <slug> --gate verify
make check-sdd-completion FEATURE=<slug>
```

`verify` is the final evidence gate: it runs full feature-level SDD artifact
validation, then checks `verification.md` for a final `make check-all` command
block, completed Spec compliance rows, skip accounting, zero skipped tests, and
contradiction-free completion evidence before a completion claim; every task in
the feature must be `[x]`. `make check-sdd-completion FEATURE=<slug>` is the
Make target for final completion: it reruns `make check-all` in the current
checkout and then runs the single-feature verify gate. Record its output under
`## Completion gate`, not inside the final `## Verification commands`
transcript. `make check-all` still produces the final command transcript and
also runs the non-mutating all-active pre-verify gate sweep:

```bash
uv run python scripts/check_sdd_gate.py --all-active
```

When work ships and verification is recorded, move the whole feature directory
from `features/active/` to `features/completed/` in the same PR.

SDD artifacts are working records, not canonical runtime documentation. If an
SDD file disagrees with `AGENTS.md`, this document, `ARCHITECTURE.md`,
`WORKERS.md`, the owning domain `ARCHITECTURE.md`, or code, trust the canonical
docs/code and update or supersede the SDD record before using it. Do not infer
current worker behavior from planning artifacts without re-auditing the
implementation.

Get explicit user approval at each lane boundary; do not write the next lane
until the prior is approved, unless the user has already delegated the full
goal and asked the agent to continue autonomously.

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
- `uv run python scripts/validate_sdd_artifacts.py` exited 0, and
  `uv run python scripts/regen_sdd_work_index.py --check` exited 0.
- `make check-all` exited 0 in the worktree, AND the verification artefact contains
  its full output (no abridging) plus the new `Coverage`, `Skipped tests`, and
  `E2E golden path` sections.
- The final `Skipped tests` section reports `Number of skipped tests in the run above: 0`.
- `make check-sdd-completion FEATURE=<slug>` exited 0 for this feature, recorded
  under `## Completion gate` rather than `## Verification commands`.
- The diff was reviewed against the plan.
- UI flows genuinely outside `make check-all` coverage were exercised manually
  and recorded under `Other commands run`.
- Remaining risks and follow-ups are listed and, if non-trivial, appended to
  `docs/TECH_DEBT.md`.

If any of the above cannot be satisfied, surface the gap rather than claiming completion.
