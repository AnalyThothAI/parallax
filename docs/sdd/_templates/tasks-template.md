# Tasks — `<feature title>`

**Status**: Draft | Approved | In Progress | Review | Blocked | Verified | Superseded
**Owning plan**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/plan.md`
**Worktree**: `.worktrees/<branch-slug>/`
**Branch**: `<branch>`
**Approved by**: <user / delegated goal / pending>
**Approved at**: <YYYY-MM-DD / pending>

Use this file when a plan spans multiple PRs or when a parallel sub-agent will execute pieces. Skip it for single-PR work.

Tasks are TDD-ordered: write the failing test first, then the implementation, then run verification. Mark a task `[P]` when it can run in parallel with the previous task without sharing state. When a task is delegated, fill the subagent fields before dispatch.

## Conventions

- Each task names exactly one file or repository concern. Multi-file work is multiple tasks.
- Status uses `[ ] pending`, `[~] in progress`, `[x] complete`, `[!] blocked`.
- A task is complete only when its verification command produced the expected output.
- Use `docs/agent-playbook/subagent-handoff-template.md` for delegated work.
- The **Touch set** is what the assignee may edit. The **Conflict set** is what they must avoid or coordinate with the parent agent.

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below are TDD ordered. |
| Verify | `verification.md` captures command output. |

## Tasks

### Task 1 — `<one-line title>`

- **File(s)**: `tests/<area>/test_<file>.py`, `src/<area>/<file>.py`
- **Owner**: `<parent | subagent nickname | person>`
- **Depends on**: `<none | Task N | external approval>`
- **Touch set**: `<paths this task may edit>`
- **Conflict set**: `<paths/concerns this task must not edit without coordination>`
- **Failing test first**: `tests/<area>/test_<file>.py::<test_name>` — asserts `<observable behaviour>`.
- **Subagent handoff**: `<not delegated | prompt/link to filled handoff template>`
- **Implementation**: <one-paragraph description of the code change>.
- **Verification**: `uv run pytest tests/<area>/test_<file>.py::<test_name> -x`
- **Review owner**: `<parent agent | person>`
- **Factory lane**: `<Spec/plan | Domain implementation | Harness/tests | Docs/contracts | Risk radar | Final integration>`
- **Deterministic constraints**: `<scripts/tests/docs gates that must always apply>`
- **On-demand context**: `<docs/code/context packet this task should load only when needed>`
- **Kill/defer criteria**: `<conditions that stop or defer this task>`
- **Eval/repair signal**: `<review defect, harness failure, token cost, or repair-loop metric this task records>`
- **Status**: [ ]

### Task 2 — `<title>` `[P]`

- **File(s)**:
- **Owner**:
- **Depends on**:
- **Touch set**:
- **Conflict set**:
- **Failing test first**:
- **Subagent handoff**:
- **Implementation**:
- **Verification**:
- **Review owner**:
- **Factory lane**:
- **Deterministic constraints**:
- **On-demand context**:
- **Kill/defer criteria**:
- **Eval/repair signal**:
- **Status**: [ ]

### Task 3 — `<title>`

- **File(s)**:
- **Owner**:
- **Depends on**:
- **Touch set**:
- **Conflict set**:
- **Failing test first**:
- **Subagent handoff**:
- **Implementation**:
- **Verification**:
- **Review owner**:
- **Factory lane**:
- **Deterministic constraints**:
- **On-demand context**:
- **Kill/defer criteria**:
- **Eval/repair signal**:
- **Status**: [ ]

## Final verification

After all tasks are `[x] complete`:

- [ ] `make check-all`
- [ ] All acceptance criteria from the spec produce expected output (paste evidence into `verification.md`).
