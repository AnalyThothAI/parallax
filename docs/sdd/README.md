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
Any extra file or subdirectory under a feature record fails the executable
harness as `unexpected-artifact`.

## Loop

1. Define project invariants in canonical docs.
2. Write `spec.md` for the feature intent and acceptance criteria.
3. Clarify ambiguities and run a checklist before planning.
4. Write `plan.md` with file-level edits and verification commands.
5. Write `tasks.md` for TDD-ordered execution.
6. Analyze spec, plan, and tasks for contradictions before implementation.
7. Generate a bounded context packet and dry-run handoff before any subagent handoff.
8. Validate any returned subagent report and record `Subagent report` plus `Review result` on the task.
9. Implement in an isolated `.worktrees/<slug>/` worktree.
10. Fill `verification.md` with evidence, including `make check-all`.
11. Move the feature directory from `active/` to `completed/`.

Run the executable harness after changing any SDD record:

```bash
uv run python scripts/validate_sdd_artifacts.py --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate clarify --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate checklist --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate analyze --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate implement --check
uv run python scripts/check_sdd_gate.py --all-active --check
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode read-only
uv run python scripts/dispatch_sdd_task.py --feature <slug> --task <number> --mode read-only
uv run python scripts/validate_subagent_report.py --feature <slug> --task <number> --mode read-only --report <report.md>
```

The gate checker gives the Spec Kit-style `clarify`, `checklist`, `analyze`,
and `implement` lanes first-class non-mutating checks. `make check-all` runs
the all-active gate sweep before generated index freshness. The full validator
still rejects false `Verified` records, missing gate sections, missing approval
metadata, incomplete task coordination fields, and active touch-set conflicts
without an explicit coordination rule.

## Status Rules

Every artifact has a `Status:` line in the first 40 lines. Active feature artifacts use `Draft`, `Approved`, `In Progress`, `Review`, or `Blocked`. Completed feature artifacts use `Verified` or `Superseded`.
Every artifact in a `Superseded` feature must also include `**Superseded by**:`
with an existing repo path to the successor SDD record; prose references do not
count.

Run this check after changing the lane:

```bash
uv run python scripts/validate_sdd_artifacts.py --check
uv run python scripts/regen_sdd_work_index.py --check
```
