# Verification — `<feature title>`

**Date**: YYYY-MM-DD
**Owning spec**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/spec.md`
**Owning plan**: `docs/sdd/features/active/YYYY-MM-DD-<slug>/plan.md`
**Branch**: `<branch>`
**Diff**: `git diff main...<branch>` — `<N>` files changed, `<+a>/-<b>` lines.

The plan and spec are the contract. This file is the evidence the contract was met. No `done`, `fixed`, or `passing` claim is allowed without the corresponding output captured below.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — WHEN ... THEN system SHALL ... | ✅ / ❌ | command + expected output |
| AC2 — WHEN ... THEN system SHALL ... | ✅ / ❌ | ... |
| AC3 — WHEN ... THEN system SHALL ... | ✅ / ❌ | ... |

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
| line   | X.X%  | ≥ 80%     | ✅/❌  |
| branch | X.X%  | ≥ 70%     | ✅/❌  |

If thresholds were temporarily relaxed in `pyproject.toml [tool.coverage.report]`,
state the relaxed value and the follow-up entry in `docs/TECH_DEBT.md`.

## Skipped tests

Number of skipped tests in the run above: <N>

If N > 0, list categories and explain why each is acceptable:

| count | reason | acceptable? |
|-------|--------|-------------|
|       |        |             |

A run with unexplained skips cannot serve as completion evidence.

## E2E golden path

Confirm each runtime signal from the spec §6.4 was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

If `SKIP_E2E=1` was set, this run cannot serve as completion evidence.

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
