# Verification — `<feature title>`

**Date**: YYYY-MM-DD
**Owning spec**: `docs/superpowers/specs/YYYY-MM-DD-<slug>.md`
**Owning plan**: `docs/superpowers/plans/YYYY-MM-DD-<slug>.md`
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

```text
$ uv run ruff check .
<paste tail of output>

$ uv run pytest
<paste summary line: N passed, M failed, ... in <duration>>

$ uv run python -m compileall src tests
<paste tail of output>
```

Other commands run (manual UI / live-WebSocket / docker compose smoke):

```text
$ <command>
<output>
```

## Diff summary

Files changed (grouped by package):

- `src/gmgn_twitter_intel/<area>/...`
- `tests/<area>/...`
- `docs/superpowers/...`

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
