# PostgreSQL Projection Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the PG-only audit and projection operations closure without changing business scoring, extraction, attribution, or API payload semantics.

**Architecture:** PostgreSQL facts remain the source of truth. Projection tables are versioned, replayable read models with offset, run, dirty-range, status, and validation commands. The first slice adds schema and ops visibility only; workers and API cutover happen after shadow comparison.

**Tech Stack:** Python 3.13, PostgreSQL, psycopg 3, Alembic, pytest, FastAPI CLI wiring.

---

## File Structure

- `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0004_projection_operations.py` adds projection metadata and read model tables.
- `src/gmgn_twitter_intel/storage/projection_repository.py` owns projection offsets, runs, dirty ranges, and status summaries.
- `src/gmgn_twitter_intel/storage/postgres_audit.py` owns DB audit, hot query explain audit, and projection validation output.
- `src/gmgn_twitter_intel/cli.py` wires `db audit`, `db query-audit`, `ops projection-status`, and `ops validate-projections`.
- `tests/test_postgres_schema.py` checks migration text and PG-only projection schema.
- `tests/test_postgres_schema_runtime.py` checks migrated tables and Alembic head.
- `tests/test_projection_repository.py` checks offset/run/dirty-range behavior.
- `tests/test_postgres_audit.py` checks audit outputs.
- `tests/test_cli.py` checks command wiring.
- `docs/superpowers/specs/2026-05-06-materialized-read-models-production-cn.md` is the current PG-only projection spec.

## Task 1: Projection Schema

- [x] **Step 1: Write schema tests**

Add static migration assertions for:

```python
assert "CREATE TABLE IF NOT EXISTS projection_offsets" in text
assert "CREATE TABLE IF NOT EXISTS projection_runs" in text
assert "CREATE TABLE IF NOT EXISTS projection_dirty_ranges" in text
assert "CREATE TABLE IF NOT EXISTS token_social_buckets" in text
assert "CREATE TABLE IF NOT EXISTS token_social_bucket_authors" in text
assert "CREATE TABLE IF NOT EXISTS token_flow_window_snapshots" in text
```

- [x] **Step 2: Verify tests fail before implementation**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q
```

Expected before code: failure because migration `20260506_0004_projection_operations.py` does not exist.

- [x] **Step 3: Add Alembic migration**

Create `20260506_0004_projection_operations.py` with:

- `projection_offsets`
- `projection_runs`
- `projection_dirty_ranges`
- `token_social_buckets`
- `token_social_bucket_authors`
- `token_flow_window_snapshots`

- [x] **Step 4: Verify schema tests**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q
```

Expected: static tests pass; runtime tests pass where a local PostgreSQL test database is available.

## Task 2: Projection Repository

- [x] **Step 1: Write repository tests**

Cover:

- run start and finish
- offset advance
- dirty-range enqueue
- dirty-range idempotency
- dirty-range claim with row locking

- [x] **Step 2: Verify tests fail before implementation**

Run:

```bash
uv run pytest tests/test_projection_repository.py -q
```

Expected before code: import failure for `gmgn_twitter_intel.storage.projection_repository`.

- [x] **Step 3: Implement repository**

Create `ProjectionRepository` with:

- `get_offset`
- `list_offsets`
- `advance_offset`
- `start_run`
- `finish_run`
- `run_by_id`
- `list_runs`
- `enqueue_dirty_range`
- `claim_dirty_ranges`
- `list_dirty_ranges`
- `status_summary`

- [x] **Step 4: Verify repository tests**

Run:

```bash
uv run pytest tests/test_projection_repository.py -q
```

Expected: pass where a local PostgreSQL test database is available.

## Task 3: Audit Commands

- [x] **Step 1: Write audit tests**

Cover:

- operational audit returns engine, migration version, counts, projection schema presence, and FK orphan counts
- query audit returns plans for hot read paths without running analysis by default

- [x] **Step 2: Verify tests fail before implementation**

Run:

```bash
uv run pytest tests/test_postgres_audit.py -q
```

Expected before code: import failure for `gmgn_twitter_intel.storage.postgres_audit`.

- [x] **Step 3: Implement audit module**

Create:

- `PostgresOperationalAudit`
- `PostgresQueryAudit`
- `ProjectionValidationAudit`

- [x] **Step 4: Wire CLI commands**

Add:

```bash
gmgn-twitter-intel db audit
gmgn-twitter-intel db query-audit
gmgn-twitter-intel db query-audit --analyze
gmgn-twitter-intel ops projection-status
gmgn-twitter-intel ops validate-projections --sample 100
```

- [x] **Step 5: Verify command tests**

Run:

```bash
uv run pytest tests/test_cli.py::CliTests::test_db_audit_query_audit_and_projection_ops_use_postgres_only -q
```

Expected: pass where a local PostgreSQL test database is available.

## Task 4: Documentation Closure

- [x] **Step 1: Replace current projection spec**

Ensure `docs/superpowers/specs/2026-05-06-materialized-read-models-production-cn.md` describes only PG-only projection operations.

- [x] **Step 2: Add document guard**

Add `test_current_projection_docs_are_postgres_only` to keep current projection docs free of old runtime instructions.

- [x] **Step 3: Verify document guard**

Run:

```bash
uv run pytest tests/test_project_structure.py::test_current_projection_docs_are_postgres_only -q
```

Expected: pass.

## Final Verification

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py tests/test_projection_repository.py tests/test_postgres_audit.py tests/test_cli.py::CliTests::test_db_audit_query_audit_and_projection_ops_use_postgres_only tests/test_project_structure.py::test_current_projection_docs_are_postgres_only -q
uv run ruff check src/gmgn_twitter_intel/storage/projection_repository.py src/gmgn_twitter_intel/storage/postgres_audit.py src/gmgn_twitter_intel/cli.py tests/test_projection_repository.py tests/test_postgres_audit.py
uv run python -m compileall src tests
```

Expected:

- tests pass or PostgreSQL integration tests skip only when the local test database is unavailable;
- ruff reports no issues;
- compileall exits 0.

## Next Implementation Slice

After this closure lands:

1. Implement token social bucket worker behind projection offsets.
2. Shadow compare bucket output against raw rolling aggregation.
3. Implement token-flow window snapshot worker.
4. Shadow compare `/api/token-flow` raw output against snapshots.
5. Cut API to projection read model with explicit stale/missing responses.
