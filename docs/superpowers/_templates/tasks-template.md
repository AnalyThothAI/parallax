# Tasks — `<feature title>`

**Owning plan**: `docs/superpowers/plans/YYYY-MM-DD-<slug>.md`
**Worktree**: `.worktrees/<branch-slug>/`

Use this file when a plan spans multiple PRs or when a parallel sub-agent will execute pieces. Skip it for single-PR work.

Tasks are TDD-ordered: write the failing test first, then the implementation, then run verification. Mark a task `[P]` when it can run in parallel with the previous task without sharing state.

## Conventions

- Each task names exactly one file or repository concern. Multi-file work is multiple tasks.
- Status uses `[ ] pending`, `[~] in progress`, `[x] complete`, `[!] blocked`.
- A task is complete only when its verification command produced the expected output.

## Tasks

### Task 1 — `<one-line title>`

- **File(s)**: `tests/<area>/test_<file>.py`, `src/<area>/<file>.py`
- **Failing test first**: `tests/<area>/test_<file>.py::<test_name>` — asserts `<observable behaviour>`.
- **Implementation**: <one-paragraph description of the code change>.
- **Verification**: `uv run pytest tests/<area>/test_<file>.py::<test_name> -x`
- **Status**: [ ]

### Task 2 — `<title>` `[P]`

- **File(s)**:
- **Failing test first**:
- **Implementation**:
- **Verification**:
- **Status**: [ ]

### Task 3 — `<title>`

- **File(s)**:
- **Failing test first**:
- **Implementation**:
- **Verification**:
- **Status**: [ ]

## Final verification

After all tasks are `[x] complete`:

- [ ] `uv run ruff check .`
- [ ] `uv run pytest`
- [ ] `uv run python -m compileall src tests`
- [ ] All acceptance criteria from the spec produce expected output (paste evidence into `verification.md`).
