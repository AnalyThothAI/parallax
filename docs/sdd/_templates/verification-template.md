# Verification — `<feature title>`

**Status**: Draft | Approved | In Progress | Review | Blocked | Verified | Superseded
**Superseded by**: `<required existing repo path when Status is Superseded>`
**Date**: YYYY-MM-DD
**Owning spec**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/spec.md`
**Owning plan**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/plan.md`
**Branch**: `<branch>`
**Worktree**: `.worktrees/<branch-slug>/`
**Approved by**: <user / delegated goal / pending>
**Approved at**: <YYYY-MM-DD / pending>
**Diff**: `git diff main...<branch>` — `<N>` files changed.

The plan selects verification commands proportional to the changed seam and
risk. Record relevant output and exit status for every cited command.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - WHEN ... THEN system SHALL ... | Pass | `uv run pytest tests/<path> -q` exited 0. |
| AC2 - WHEN ... THEN system SHALL ... | Pass | `npm run test -- <path>` exited 0. |
| AC3 - WHEN ... THEN system SHALL ... | In Progress | Missing evidence or deviation. |

Deviations from spec:

- None.

Deviations from plan:

- None.

## Verification commands

```text
$ uv run pytest tests/<path> -q
<relevant output>
exit code: 0

$ <another command selected by the plan>
<relevant output>
exit code: 0
```

## Diff summary

- `<area>`: <what changed>.

## Risks observed

- <Omitted lane, unresolved risk, or none.>

## Follow-ups

- <Out-of-scope work or none.>
