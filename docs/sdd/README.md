# Spec-Driven Development

Non-trivial work uses one dated feature directory with exactly four files:

```text
docs/sdd/features/
  active/YYYY-MM-DD-<slug>/
    spec.md
    plan.md
    tasks.md
    verification.md
  completed/
```

Canonical project truth remains in root governance docs, domain architecture,
code, tests, and generated contracts. SDD records explain one bounded change.

## Loop

1. Write and approve the spec.
2. Clarify ambiguity and check requirement quality.
3. Write the file-level plan and acceptance commands.
4. Write TDD-ordered tasks with ownership and conflict sets.
5. Analyze spec, plan, and tasks for contradictions.
6. Implement in an isolated worktree.
7. Record successful direct commands against every acceptance criterion.
8. Run the SDD verify gate and move the four files to `completed/`.

Keep active task boards at or below 40 tasks. Split larger work into a successor
feature.

## Commands

```bash
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate clarify
uv run python scripts/check_sdd_gate.py --feature <slug> --gate checklist
uv run python scripts/check_sdd_gate.py --feature <slug> --gate analyze
uv run python scripts/check_sdd_gate.py --feature <slug> --gate implement
uv run python scripts/check_sdd_gate.py --feature <slug> --gate verify
```

The plan selects direct test, lint, build, generated-contract, database, or
browser commands according to risk. Verification may contain multiple command
blocks. Every cited command needs matching exit-code-zero evidence; omitted
lanes are risks, not passes.
Native agent collaboration stays outside the repository. Record ownership,
touch sets, dependencies, and executable evidence in the four artifacts; do not
create packet, handoff, dispatch, or agent-report files.

## Status

All four artifacts share one status. Active records use `Draft`, `Approved`,
`In Progress`, `Review`, or `Blocked`. Completed records use `Verified` or
`Superseded`. A superseded record names an existing successor path.
