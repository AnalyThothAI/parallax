# SDD Templates

These templates encode the feature-directory workflow described in `docs/WORKFLOW.md`.
Copy the full set into one dated feature directory; do not edit templates in place.

## Feature Directory

```text
docs/sdd/features/active/YYYY-MM-DD-<slug>/
  spec.md
  plan.md
  tasks.md
  verification.md
```

Move the whole directory to `docs/sdd/features/completed/` only after verification is recorded.
Run `uv run python scripts/validate_sdd_artifacts.py` and `uv run python scripts/regen_sdd_work_index.py --check`
after changing any copied feature record.
Keep feature directories to these four files only; screenshots, mockups, logs,
notes, and other attachments fail as `unexpected-artifact`.

## Artifact Roles

| File | Purpose |
|------|---------|
| `spec.md` | Why and what. Product/system intent, goals, non-goals, acceptance criteria. |
| `plan.md` | How and when. File-level edits, SQL, rollout, rollback, test commands. |
| `tasks.md` | TDD-ordered task checklist and subagent handoff boundaries. |
| `verification.md` | Evidence that the spec and plan were satisfied. |

## Naming

- Date prefix: today's date in `YYYY-MM-DD`. Do not back-date.
- Slug: short, intent-focused, kebab-case.
- Use one slug per feature and keep all four artifacts in the same directory.

## Lifecycle

1. **Brainstorm** - understand the goal and scope.
2. **Spec** - fill `spec.md`; get approval before planning.
3. **Clarify / checklist** - resolve ambiguous requirements before plan work.
4. **Plan** - fill `plan.md`; cite exact files and tests.
5. **Tasks** - fill `tasks.md` for multi-step work; keep it TDD-ordered.
6. **Analyze** - check spec, plan, and tasks for contradictions before implementation.
7. **Implement** - work in a `.worktrees/<slug>/` worktree.
8. **Verify** - fill `verification.md` with successful commands selected by the
   plan and mapped to every acceptance criterion.
9. **Complete** - move the full feature directory from `active/` to `completed/`.

## Status Discipline

Every artifact must include a `Status:` line in the first 40 lines. Active feature artifacts use
`Draft`, `Approved`, `In Progress`, `Review`, or `Blocked`. Completed feature artifacts use
`Verified` or `Superseded`.
When an artifact is `Superseded`, fill `**Superseded by**:` with an existing
repo path to the successor SDD record; prose references are ignored by the
validator.
