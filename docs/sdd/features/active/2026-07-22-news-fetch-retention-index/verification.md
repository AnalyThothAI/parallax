# Verification — News fetch retention foreign-key index

**Status**: Review
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/active/2026-07-22-news-fetch-retention-index/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-22-news-fetch-retention-index/plan.md`
**Branch**: `codex/news-fetch-retention-index`
**Worktree**: `.worktrees/news-fetch-retention-index/`
**Approved by**: delegated Docker startup and backend optimization goal
**Approved at**: 2026-07-22
**Diff**: commit `0c4a4c59` — 8 files changed, 411 insertions, 3 deletions.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - canonical schema | Pass | Unit schema contract: 9 passed. |
| AC2 - nonempty upgrade | Pass | PostgreSQL migration integration: 4 passed. |
| AC3 - live startup | Pass | Migration reached 0187; app/PostgreSQL are healthy and readiness reports no reasons. |

Deviations from spec:

- None.

Deviations from plan:

- None.

## Verification commands

Repository-wide `make check-all` is not claimed for this bounded repair.

```text
$ make check-all
not run
exit code: not run
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not run | repository gate | In Progress |
| branch | Not run | repository gate | In Progress |

## Skipped tests

Not measured by a repository-wide completion run.

## E2E golden path

- [x] `/readyz` returned 200
- [x] migration reached current head
- [x] canonical FK lookup uses an index

No broad E2E is in scope.

## Completion gate

Not claimed; the feature remains active/Review without the full no-skip gate.

## Other commands run

- Baseline live migration: stopped after more than seven minutes of CPU-bound FK scans; transaction rolled back to 0184.
- Baseline plan: sequential scan on `news_provider_items` for `fetch_run_id` lookup.

```text
$ uv run pytest tests/unit/test_postgres_schema.py -x
9 passed
exit code: 0

$ uv run pytest tests/integration/test_postgres_schema_runtime.py -x
4 passed
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_retention.py -q
2 passed
exit code: 0

$ make docker-up
final app and migrate images built; migration completed; app started
exit code: 0

$ make docker-status
app and PostgreSQL healthy; migration 20260722_0187 ready
exit code: 0

$ curl --fail --silent http://127.0.0.1:8765/healthz
ok
exit code: 0

$ curl --fail --silent http://127.0.0.1:8765/readyz
ok=true; reasons=[]; migration_status=ready
exit code: 0
```

## Diff summary

- New reversible revision 0187 owns the canonical child FK index.
- Unit and PostgreSQL integration tests cover graph identity, index validity/readiness, and `ON DELETE SET NULL` behaviour.

Migrations applied:

- `20260721_0185` — backend KISS hard cut.
- `20260722_0186` — runtime projection hard cut.
- `20260722_0187` — canonical news provider-item fetch-run FK index.

Schema or contract changes:

- One canonical index on `news_provider_items(fetch_run_id)`; no public contract change.

## Risks observed

- PostgreSQL table statistics substantially underestimated news row counts, so catalog estimates alone were insufficient; exact bounded counts and query plans exposed the issue.
- The final Docker layer reinstalls Playwright OS/browser assets after any Python source change; this is a separate build-cache optimization candidate.

## Follow-ups

- Audit other retention-parent foreign keys for missing child indexes as a separate read-only review.
