# Tasks — `<feature title>`

**Status**: Draft | Approved | In Progress | Review | Blocked | Verified | Superseded
**Superseded by**: `<required existing repo path when Status is Superseded>`
**Owning plan**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/plan.md`
**Worktree**: `.worktrees/<branch-slug>/`
**Branch**: `<branch>`
**Approved by**: <user / delegated goal / pending>
**Approved at**: <YYYY-MM-DD / pending>

Use this file for every non-trivial SDD feature. Keep active boards at or below
40 tasks and split work that exceeds that bound.

Tasks are ordered by dependency. Write the failing contract first when behavior
can be tested, implement the change, then run the named verification command.
Native agent collaboration does not create repository handoff or report files.

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below are ordered by dependency. |
| Verify | `verification.md` captures command output. |

## Tasks

### Task 1 — `<one-line title>`

- **File(s)**: `tests/<area>/test_<file>.py`, `src/<area>/<file>.py`
- **Owner**: `<agent or person>`
- **Depends on**: `<none | Task N | external approval>`
- **Touch set**: `<paths this task may edit>`
- **Removed file(s)**: `<optional deleted paths, omitted when none>`
- **Conflict set**: `<paths/concerns this task must not edit without coordination>`
- **Failing test first**: `tests/<area>/test_<file>.py::<test_name>` — asserts `<observable behaviour>`.
- **Implementation**: <one-paragraph description of the change>.
- **Verification**: `uv run pytest tests/<area>/test_<file>.py::<test_name> -x`
- **Status**: [ ]

### Task 2 — `<title>`

- **File(s)**:
- **Owner**:
- **Depends on**:
- **Touch set**:
- **Conflict set**:
- **Failing test first**:
- **Implementation**:
- **Verification**:
- **Status**: [ ]
