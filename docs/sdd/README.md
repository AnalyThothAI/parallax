# Spec-Driven Development

Parallax uses a hard-cut Spec-Driven Development lane for non-trivial coding-agent work. The lane is intentionally small, current, and enforceable by tests.

## Layout

```text
docs/sdd/
  _templates/
  features/
    active/
    completed/
```

Each feature is a dated directory containing exactly four artifacts:

- `spec.md`
- `plan.md`
- `tasks.md`
- `verification.md`

Historical one-off plans are not retained here. Canonical project truth lives in root governance docs, domain `ARCHITECTURE.md` files, code, tests, and generated contracts.

## Loop

1. Define project invariants in canonical docs.
2. Write `spec.md` for the feature intent and acceptance criteria.
3. Clarify ambiguities and run a checklist before planning.
4. Write `plan.md` with file-level edits and verification commands.
5. Write `tasks.md` for TDD-ordered execution.
6. Analyze spec, plan, and tasks for contradictions before implementation.
7. Implement in an isolated `.worktrees/<slug>/` worktree.
8. Fill `verification.md` with evidence, including `make check-all`.
9. Move the feature directory from `active/` to `completed/`.

## Status Rules

Every artifact has a `Status:` line in the first 40 lines. Active feature artifacts use `Draft`, `Approved`, `In Progress`, `Review`, or `Blocked`. Completed feature artifacts use `Verified` or `Superseded`.

Run this check after changing the lane:

```bash
uv run python scripts/regen_sdd_work_index.py --check
```
