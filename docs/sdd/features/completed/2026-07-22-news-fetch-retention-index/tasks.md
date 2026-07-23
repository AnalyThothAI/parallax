# Tasks — News fetch retention foreign-key index

**Status**: Verified
**Owning plan**: `docs/sdd/features/completed/2026-07-22-news-fetch-retention-index/plan.md`
**Worktree**: `.worktrees/news-fetch-retention-index/`
**Branch**: `codex/news-fetch-retention-index`
**Approved by**: delegated Docker startup and backend optimization goal
**Approved at**: 2026-07-22

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tests precede migration implementation. |
| Verify | `verification.md` records bounded commands and live plan evidence. |

## Tasks

### Task 1 — Encode and implement the FK index invariant

- **File(s)**: `tests/unit/test_postgres_schema.py`, `tests/integration/test_postgres_schema_runtime.py`, `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `tests/unit/test_postgres_schema.py`, `tests/integration/test_postgres_schema_runtime.py`, `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`
- **Conflict set**: `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0186_runtime_projection_hard_cut.py`; coordinate with 2026-07-22-backend-kiss-deep-audit for tests/unit/test_postgres_schema.py and tests/integration/test_postgres_schema_runtime.py; coordinate with 2026-07-23-macro-evidence-ai-hard-cut for tests/unit/test_postgres_schema.py and tests/integration/test_postgres_schema_runtime.py
- **Failing test first**: `tests/unit/test_postgres_schema.py::test_news_fetch_run_fk_index_is_canonical_and_reversible` — requires revision 0187 and its exact index contract.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add exactly one reversible migration after 0186 with a btree index on the child FK; preserve published revisions byte-for-byte.
- **Verification**: `uv run pytest tests/unit/test_postgres_schema.py -x`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: no historical migration edit, table, worker, compatibility clause, or retention change.
- **On-demand context**: migration 0185, PostgreSQL schema integration tests, performance reference.
- **Kill/defer criteria**: stop if the FK or deletion semantics differ from the observed schema.
- **Eval/repair signal**: unit/integration failures and PostgreSQL query plan.
- **Status**: [x]

### Task 2 — Rebuild and verify the live stack

- **File(s)**: `docs/sdd/features/completed/2026-07-22-news-fetch-retention-index/verification.md`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/sdd/features/completed/2026-07-22-news-fetch-retention-index/verification.md`
- **Conflict set**: `src/parallax/`; `web/`
- **Failing test first**: `tests/integration/test_postgres_schema_runtime.py::test_backend_kiss_hard_cut_migrates_nonempty_0184_state` — proves nonempty upgrade and index presence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Use one temporary concurrent preflight index for the already-stopped 0184 database, deploy the corrected migration image, remove the temporary duplicate, and inspect readiness/plan.
- **Verification**: `make docker-status`
- **Review owner**: parent agent
- **Factory lane**: Final integration
- **Deterministic constraints**: never reveal credentials; no E2E; preserve database data.
- **On-demand context**: `docs/SETUP.md`, `docs/SECURITY.md`, live catalog/plan output.
- **Kill/defer criteria**: stop on rollback failure, migration error, or readiness failure.
- **Eval/repair signal**: migration duration, index plan, container health.
- **Status**: [x]
