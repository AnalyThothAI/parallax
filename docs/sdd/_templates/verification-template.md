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
**Diff**: `git diff main...<branch>` — `<N>` files changed, `<+a>/-<b>` lines.

The plan and spec are the contract. This file is the evidence the contract was met. No `done`, `fixed`, or `passing` claim is allowed without the corresponding output captured below.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - WHEN ... THEN system SHALL ... | Pass | `make check-all` exited 0 and covered AC1. |
| AC2 - WHEN ... THEN system SHALL ... | Pass | `make check-all` exited 0 and covered AC2. |
| AC3 - WHEN ... THEN system SHALL ... | Fail | Blocking evidence or deviation. |

Deviations from spec (with reason and user-approved date if any):

- ...

Deviations from plan (with reason):

- ...

## Verification commands

The only command whose output may be pasted as evidence is `make check-all`.
Paste the FULL output below, including the exit code line.

```text
$ make check-all
<paste full stdout/stderr here>
exit code: 0
```

If `make check-all` exit code is non-zero, the work is not complete — do not
file this artefact until it is.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | 91% | >= 80% | Pass |
| branch | Not run | >= 70% | Fail |

If thresholds were temporarily relaxed in `pyproject.toml [tool.coverage.report]`,
state the relaxed value and the follow-up entry in `docs/TECH_DEBT.md`.

## Skipped tests

Number of skipped tests in the run above: 0

A run with any skipped tests cannot serve as completion evidence. Fix the lane
or leave the feature in `Review` / `Blocked` until the final run reports zero
skips.

## E2E golden path

Confirm each runtime signal required by the current feature spec was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

Runtime-lane dependencies must fail closed with actionable setup guidance; do
not satisfy this section with environment skip switches.

## Completion gate

After filling the sections above and completing every task as `[x]`, run the
single-feature completion gate and record its command plus final exit status
here. This command reruns `make check-all` before the feature verify gate; keep
the full `make check-all` transcript in `## Verification commands`, not here.

```text
$ make check-sdd-completion FEATURE=<slug>
verify gate passed: <slug>
exit code: 0
```

## Other commands run (manual UI smoke; only for areas not coverable by tests)

```text
$ <command>
<output>
```

## Diff summary

Files changed (grouped by package):

- `src/parallax/<area>/...`
- `tests/<area>/...`
- `docs/sdd/...`

Migrations applied:

- `<revision id>` — <one-line description>.

Schema or contract changes that consumers must be aware of:

- ...

## Risks observed

Issues seen during verification, even if they did not block completion. Each entry: what was seen, severity, follow-up action or owner.

- ...

## Follow-ups

Work that emerged during this change but was correctly out of scope. File these as new specs, not as inline TODOs in the code.

- ...
