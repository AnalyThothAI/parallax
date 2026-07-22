# Verification — News fetch retention foreign-key index

**Status**: In Progress
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/active/2026-07-22-news-fetch-retention-index/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-22-news-fetch-retention-index/plan.md`
**Branch**: `codex/news-fetch-retention-index`
**Worktree**: `.worktrees/news-fetch-retention-index/`
**Approved by**: delegated Docker startup and backend optimization goal
**Approved at**: 2026-07-22
**Diff**: pending

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - canonical schema | Pass | Unit schema contract: 9 passed. |
| AC2 - nonempty upgrade | Pass | PostgreSQL migration integration: 4 passed. |
| AC3 - live startup | In Progress | Baseline migration was safely stopped and rolled back to 0184. |

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

- [ ] `/readyz` returned 200
- [ ] migration reached current head
- [ ] canonical FK lookup uses an index

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
```

## Diff summary

- New reversible revision 0187 owns the canonical child FK index.
- Unit and PostgreSQL integration tests cover graph identity, index validity/readiness, and `ON DELETE SET NULL` behaviour.

Migrations applied:

- None yet.

Schema or contract changes:

- One canonical index on `news_provider_items(fetch_run_id)`; no public contract change.

## Risks observed

- PostgreSQL table statistics substantially underestimated news row counts, so catalog estimates alone were insufficient; exact bounded counts and query plans exposed the issue.

## Follow-ups

- Audit other retention-parent foreign keys for missing child indexes as a separate read-only review.
