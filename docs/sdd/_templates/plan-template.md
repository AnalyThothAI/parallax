# Plan — `<feature title>`

**Status**: Draft | Approved | In Progress | Review | Blocked | Verified | Superseded
**Superseded by**: `<required existing repo path when Status is Superseded>`
**Date**: YYYY-MM-DD
**Owning spec**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/spec.md`
**Worktree**: `.worktrees/<branch-slug>/`
**Branch**: `<branch>`
**Approved by**: <user / delegated goal / pending>
**Approved at**: <YYYY-MM-DD / pending>

## Pre-flight

- [ ] Spec is approved.
- [ ] Worktree exists at `.worktrees/<branch-slug>/` and `git branch --show-current` matches `<branch>`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes (or known-failing tests are explicitly listed below).

Known-failing baseline tests (none expected):

- ...

## File-level edits

Group by package. Each entry: file path, range, what changes. Function signatures and SQL go inline so a reviewer can audit without opening the editor.

### `src/parallax/<area>/<file>.py`

- Lines `<a>–<b>`: <change description>.
  - New signature: `def name(arg: Type) -> ReturnType: ...`
- Lines `<c>–<d>`: ...

### Storage / migrations

- New / modified table:
  ```sql
  -- Alembic revision: <revision id>
  ALTER TABLE ... ADD COLUMN ...;
  CREATE INDEX ...;
  ```
- Backfill SQL:
  ```sql
  ...
  ```

### Tests

- `tests/<area>/test_<file>.py::<test_name>` — describe what it asserts.
- `tests/<area>/test_<file>.py::<test_name>` — ...

## PR breakdown

One PR per logical, independently-reviewable slice. Each PR lists which file edits and tests it owns.

1. **PR 1 — <name>**: edits <files>, adds <tests>. Mergeable on its own.
2. **PR 2 — <name>**: depends on PR 1. ...
3. **PR 3 — <name>**: ...

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: <evidence> |
| Plan preserves canonical architecture boundaries. | Pass: <evidence> |
| Compatibility code or old files are not retained. | Pass: <evidence> |
| Parallel touch/conflict sets are explicit. | Pass: <evidence> |

## Rollout order

1. Migration applied (`uv run alembic upgrade head`).
2. Backfill executed (`uv run parallax ops <command>`).
3. Code merged.
4. Verification commands executed.
5. Operational notes (alert thresholds, dashboards) updated.

## Rollback

For each step above, the reverse procedure. State which steps are not safely reversible and what compensating action protects production.

## Acceptance test commands

Map to the spec's acceptance criteria. Each command must produce evidence (stdout / log line / API response) that proves the criterion.

- AC1: `uv run pytest tests/<path>::<test>`
- AC2: `uv run parallax <subcommand> ...` (expected output: ...)
- AC3: `curl -s ... | jq ...` (expected JSON shape: ...)

## Verification

Verification evidence lives in `docs/sdd/features/active/YYYY-MM-DD-<slug>/verification.md`. The verification artefact must exist before the feature directory moves to `completed/`.
