# Tasks — `<feature title>`

**Owning plan**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/plan.md`
**Worktree**: `.worktrees/<branch-slug>/`

Use this file when a plan spans multiple PRs or when a parallel sub-agent will execute pieces. Skip it for single-PR work.

Tasks are TDD-ordered: write the failing test first, then the implementation, then run verification. Mark a task `[P]` when it can run in parallel with the previous task without sharing state. When a task is delegated, fill the subagent fields before dispatch.

## Conventions

- Each task names exactly one file or repository concern. Multi-file work is multiple tasks.
- Status uses `[ ] pending`, `[~] in progress`, `[x] complete`, `[!] blocked`.
- A task is complete only when its verification command produced the expected output.
- Use `docs/agent-playbook/subagent-handoff-template.md` for delegated work.
- The **Touch set** is what the assignee may edit. The **Conflict set** is what they must avoid or coordinate with the parent agent.

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
- **Status**: [ ]

## Final verification

After all tasks are `[x] complete`:

- [ ] `make check-all`
- [ ] All acceptance criteria from the spec produce expected output (paste evidence into `verification.md`).
