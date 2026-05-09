# Tech Debt

> **Scope.** Append-only log of tracked technical debt. Verification artefacts that surface follow-up items append rows here rather than burying them in per-feature `verification.md` files.

## Schema

| Field | Meaning |
|-------|---------|
| Description | One-line summary of the debt. |
| Introduced | Commit SHA or spec slug that introduced it. |
| Area | One of `collector`, `pipeline`, `storage`, `retrieval`, `api`, `web`, `harness`, `infra`. |
| Severity | `low`, `medium`, `high`. |
| Impact | One sentence on what it costs us to leave this. |
| Owner | Name or `unowned`. |

Order rows by severity (high first) then by date introduced (oldest first).

## Open

| Description | Introduced | Area | Severity | Impact | Owner |
|-------------|------------|------|----------|--------|-------|

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
