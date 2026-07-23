# Workflow

> **Scope.** Owns the spec → plan → tasks → verification lane and worktree
> policy. Design rules live in `DESIGN_DISCIPLINE.md`; test selection lives in
> `TESTING.md`.

## Lane sequence

Trivial single-file low-risk edits may go direct. Everything else uses one
feature directory under `docs/sdd/features/active/YYYY-MM-DD-<slug>/` with
exactly four artifacts:

| Artifact | Purpose |
|----------|---------|
| `spec.md` | Why and what. |
| `plan.md` | How, touched files, and acceptance commands. |
| `tasks.md` | TDD-ordered work and ownership. |
| `verification.md` | Acceptance evidence, risks, and deviations. |

Templates live in `docs/sdd/_templates/`. Active task boards are bounded to 40
structured tasks; split larger work into a successor feature.

For production or ambiguous work, use:

```text
spec -> clarify -> checklist -> plan -> tasks -> analyze -> implement -> verify
```

Get explicit approval at lane boundaries unless the user delegated the whole
goal. When implementation changes the contract, update and re-analyze the
artifacts before continuing.

## Verification

The plan selects direct commands proportional to the changed seam and risk.
There is no repository-wide completion command or mandatory coverage metric.

A `Verified` record must:

- map every spec acceptance criterion to a successful recorded command;
- mark every task `[x]`;
- record deviations, omitted lanes, and remaining risks honestly;
- keep generated artifacts current when the change touches them;
- pass the SDD validator and selected verify gate.

Use the direct lane commands in `TESTING.md`. Record command, relevant output,
and exit status in `verification.md`. A command that was not run is not passing
evidence.

```bash
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate verify
```

The other non-mutating lifecycle checks remain available:

```bash
uv run python scripts/check_sdd_gate.py --feature <slug> --gate clarify
uv run python scripts/check_sdd_gate.py --feature <slug> --gate checklist
uv run python scripts/check_sdd_gate.py --feature <slug> --gate analyze
uv run python scripts/check_sdd_gate.py --feature <slug> --gate implement
uv run python scripts/check_sdd_gate.py --all-active
```

When verification is complete, move the entire feature directory from
`features/active/` to `features/completed/` in the same change.

SDD artifacts are working records. If they disagree with canonical docs, domain
architecture, generated contracts, or code, update or supersede the SDD before
using it.

## Worktree policy

Coding agents work in an isolated git worktree:

- Default location: `.worktrees/<branch-slug>/`.
- Create from `main` unless the user names another base.
- Before editing, inspect `git worktree list`, `git status --short`, and
  `git branch --show-current`.
- Changes touching `src/` or `tests/` require a worktree.
- Existing worktrees belong to their current tasks.

Trivial single-file documentation edits may use the main checkout when they do
not overlap existing work.
