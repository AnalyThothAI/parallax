# Plan — News fetch retention foreign-key index

**Status**: Verified
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/completed/2026-07-22-news-fetch-retention-index/spec.md`
**Worktree**: `.worktrees/news-fetch-retention-index/`
**Branch**: `codex/news-fetch-retention-index`
**Approved by**: delegated Docker startup and backend optimization goal
**Approved at**: 2026-07-22

## Pre-flight

- [x] Spec is approved.
- [x] Worktree exists on `codex/news-fetch-retention-index`.
- [x] Prior repository verification at base commit is green.
- [x] Live reproduction confirms the FK lookup is a sequential scan and migration remains at 0184 after rollback.

Known-failing baseline tests:

- New graph/schema assertions fail because revision 0187 and `idx_news_provider_items_fetch_run_id` do not exist.

## File-level edits

### Migration

- `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`: add one reversible canonical index after published head 0186; do not edit 0185/0186.

### Tests

- `tests/unit/test_postgres_schema.py`: assert a single current head and exact 0187 index contract.
- `tests/integration/test_postgres_schema_runtime.py`: assert the upgraded schema contains a valid/ready index and preserves child rows with the FK nulled.

### Storage / migrations

```sql
CREATE INDEX idx_news_provider_items_fetch_run_id
  ON news_provider_items(fetch_run_id);
```

No table, column, payload, or retention-window change.

## PR breakdown

1. **PR 1 — retention FK index**: failing schema tests, migration declaration, live restart evidence.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: one missing FK index, one migration owner, two assertions. |
| Plan preserves canonical architecture boundaries. | Pass: PostgreSQL remains the only truth and schema owner. |
| Compatibility code or old files are not retained. | Pass: one unconditional canonical index; no runtime fallback. |
| Parallel touch/conflict sets are explicit. | Pass: parent owns migration/tests; audit agents are read-only. |

## Rollout order

1. Add failing graph/schema assertions.
2. Add reversible revision 0187 and run unit/integration checks.
3. Create a temporary concurrent preflight index on the stopped operator stack.
4. Merge/build the corrected image; the temporary index accelerates 0185 and 0187 creates the canonical index.
5. Remove the temporary index and verify the canonical lookup plan and readiness.

## Rollback

Code rollback reverts the atomic commit. Before migration completion, the preflight index can be dropped concurrently. After migration completion, retain the canonical FK index because removing it reintroduces the observed performance defect.

## Acceptance test commands

- AC1: `uv run pytest tests/unit/test_postgres_schema.py -x`
- AC2: `uv run pytest tests/integration/test_postgres_schema_runtime.py -x`
- AC3: `make docker-up && make docker-status && curl --fail http://localhost:8765/healthz && curl --fail http://localhost:8765/readyz`

## Verification

Evidence lives in `docs/sdd/features/completed/2026-07-22-news-fetch-retention-index/verification.md`. The bounded migration repair is verified from its schema, non-empty upgrade, and live startup receipts.
