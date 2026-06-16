# Verification — Macro Decision Console

**Status**: Draft
**Superseded by**: Not superseded
**Date**: 2026-06-16
**Owning spec**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
**Branch**: `codex/macro-decision-console`
**Worktree**: `.worktrees/macro-decision-console`
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16
**Diff**: Planning artifacts only; implementation not started.

## Discovery Evidence

Recorded during planning on 2026-06-16:

- `uv run parallax config` exited 0. Redacted summary: config path `/Users/qinghuan/.parallax/config.yaml`; workers config path `/Users/qinghuan/.parallax/workers.yaml`; macrodata enabled; FRED configured through env name `FINANCE_FRED_API_KEY`; no secret values printed.
- `uv run parallax macro status` exited 0. Summary: migration ready, macrodata package version `0.1.8`, required series count 128, missing required series count 0, observations count 63,407, concept count 128, latest snapshot status `partial`, history coverage ratio 0.8425, projection lag 0 days, 20 concepts below minimum history.
- `uv run macrodata doctor` in `/Users/qinghuan/Documents/code/macrodata-cli` exited 0. Summary: standalone checkout version `0.1.8`, `fred_api_key_configured=false`.
- `uv run macrodata bundle macro-core --asof 2026-06-16` in `/Users/qinghuan/Documents/code/macrodata-cli` exited 0 with `data_quality=partial`, requested 128 series, available 67 series, source chain `nyfed`, `treasury_fiscal`, `fred`, `yahoo`, `cftc`, and FRED public fallback errors dominated by `provider_timeout`.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - WHEN a user hard-loads `/macro` THEN the system SHALL show the decision console. | in progress | Implementation not started. |
| AC2 - WHEN a user opens macro navigation THEN the system SHALL show only source-backed primary routes. | in progress | Implementation not started. |
| AC3 - WHEN a deleted macro route is opened directly THEN the system SHALL use ordinary not-found behavior. | in progress | Implementation not started. |
| AC4 - WHEN FRED public CSV is unavailable or timed out THEN macrodata-cli SHALL return clear diagnostics. | in progress | Implementation not started. |
| AC5 - WHEN Parallax runtime has FRED configured THEN macro status SHALL report redacted configured state. | in progress | Discovery confirms current redacted reporting. |
| AC6 - WHEN implementation is verified THEN all listed gates SHALL pass or list a baseline blocker. | in progress | Implementation not started. |

Deviations from spec:

- None recorded.

Deviations from plan:

- None recorded.

## Verification commands

Final completion evidence has not been run because implementation has not started.

```text
$ make check-all
not run
exit code: not run
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not run | >= 80% | not applicable |
| branch | Not run | >= 70% | not applicable |

## Skipped tests

Number of skipped tests in the run above: Not run

## E2E golden path

- [ ] /macro decision console renders at desktop width.
- [ ] /macro decision console renders at mobile width without overlap.
- [ ] Retained primary child routes remain reachable.
- [ ] Deleted macro routes are absent from navigation and route registry.
- [ ] No failing `/api/macro*` requests in browser session.

## Completion Gate

```text
$ make check-sdd-completion FEATURE=2026-06-16-macro-decision-console
not run
exit code: not run
```

## Other Commands Run

```text
$ uv run parallax config
exit code: 0

$ uv run parallax macro status
exit code: 0

$ uv run macrodata doctor
exit code: 0

$ uv run macrodata bundle macro-core --asof 2026-06-16
exit code: 0
```

## Diff Summary

Files changed during planning:

- `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- None implemented yet.

## Risks Observed

- Standalone macrodata-cli without `FRED_API_KEY` is too dependent on FRED public CSV and produced many timeout errors in the planning run.
- Parallax live macro data is current but still `partial` because required history coverage is below readiness threshold.
- Existing macro route inventory advertises several proxy-only or gap-only pages as supported direct routes.

## Follow-Ups

- Implement the hard-deletion tasks in `tasks.md`.
- Split any paid-data-source work into a separate SDD record after operator approval.
