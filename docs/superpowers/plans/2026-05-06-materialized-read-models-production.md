# Materialized Read Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build production-grade materialized read models for token flow, token timeline summaries, and account quality without turning the system into an inconsistent cache layer.

**Architecture:** Keep SQLite source facts as the authoritative event store and add replayable projection tables with offsets, runs, dirty ranges, and explicit lag. Projection workers update read models outside the request path; APIs read read models after cutover and expose projection freshness.

**Tech Stack:** Python 3.13, FastAPI, SQLite WAL, existing repository pattern, `uv run pytest`, `ruff`, `compileall`.

---

## File Structure

- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
  - Add projection metadata tables, token social bucket tables, and indexes.
- Create: `src/gmgn_twitter_intel/storage/projection_repository.py`
  - Own projection offsets, runs, dirty ranges, and status reads.
- Create: `src/gmgn_twitter_intel/storage/token_social_projection_repository.py`
  - Own bucket and author-bucket upserts/reads.
- Create: `src/gmgn_twitter_intel/pipeline/projection_worker.py`
  - Batch new source facts into projection dirty ranges and bucket tables.
- Create: `src/gmgn_twitter_intel/pipeline/token_flow_snapshot_worker.py`
  - Build current window snapshots from bucket projections.
- Create: `src/gmgn_twitter_intel/retrieval/token_flow_read_model_service.py`
  - Read `token_flow_window_snapshots` for `/api/token-flow`.
- Modify: `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
  - Keep raw aggregation logic for tests, rebuild validation, and shadow compare only.
- Modify: `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
  - Read summary/buckets/authors from projection tables; keep post pagination from source facts.
- Modify: `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
  - Remove request-path backfill assumptions; expose projection status.
- Create: `src/gmgn_twitter_intel/pipeline/account_quality_projection_worker.py`
  - Incrementally maintain account call stats and quality snapshots.
- Modify: `src/gmgn_twitter_intel/api/app.py`
  - Start/stop projection workers and include projection health in readiness payload.
- Modify: `src/gmgn_twitter_intel/api/http.py`
  - Return projection lag/status blocks from affected endpoints.
- Modify: `src/gmgn_twitter_intel/cli.py`
  - Add projection status, rebuild, validate, and run-once commands.
- Create tests listed per task below.

## Task 1: Projection Metadata Schema

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Create: `tests/test_projection_schema.py`

- [ ] **Step 1: Write failing schema tests**

Add tests asserting these tables and indexes exist after `migrate(conn)`:

```python
def test_projection_metadata_tables_exist(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()

    assert "projection_offsets" in names
    assert "projection_runs" in names
    assert "projection_dirty_ranges" in names
    assert "token_social_buckets" in names
    assert "token_social_bucket_authors" in names
    assert "token_flow_window_snapshots" in names
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_projection_schema.py -v
```

Expected: fails because projection tables do not exist.

- [ ] **Step 3: Add schema**

Add schema version increment and these table definitions:

```sql
CREATE TABLE IF NOT EXISTS projection_offsets (
  projection_name TEXT PRIMARY KEY,
  projection_version TEXT NOT NULL,
  source_table TEXT NOT NULL,
  source_max_received_at_ms INTEGER NOT NULL,
  source_max_id TEXT NOT NULL,
  last_run_id TEXT,
  status TEXT NOT NULL,
  lag_ms INTEGER NOT NULL,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS projection_runs (
  run_id TEXT PRIMARY KEY,
  projection_name TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  source_start_ms INTEGER,
  source_end_ms INTEGER,
  rows_read INTEGER NOT NULL,
  rows_written INTEGER NOT NULL,
  dirty_ranges_written INTEGER NOT NULL,
  started_at_ms INTEGER NOT NULL,
  finished_at_ms INTEGER,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_projection_runs_name_started
  ON projection_runs(projection_name, started_at_ms DESC);

CREATE TABLE IF NOT EXISTS projection_dirty_ranges (
  dirty_id TEXT PRIMARY KEY,
  projection_name TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  window TEXT,
  scope TEXT,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projection_dirty_ranges_claim
  ON projection_dirty_ranges(projection_name, projection_version, status, updated_at_ms);
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/test_projection_schema.py tests/test_sqlite_schema.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/storage/sqlite_schema.py tests/test_projection_schema.py
git commit -m "feat: add projection metadata schema"
```

## Task 2: Token Social Bucket Schema

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Modify: `tests/test_projection_schema.py`

- [ ] **Step 1: Add failing tests for token social tables**

Assert unique keys and read indexes exist:

```python
def test_token_social_projection_indexes_exist(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        indexes = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
    finally:
        conn.close()

    assert "ux_token_social_buckets_key" in indexes
    assert "idx_token_social_buckets_window" in indexes
    assert "ux_token_social_bucket_authors_key" in indexes
    assert "idx_token_flow_window_snapshots_lookup" in indexes
```

- [ ] **Step 2: Add schema**

Add:

```sql
CREATE TABLE IF NOT EXISTS token_social_buckets (
  bucket_id TEXT PRIMARY KEY,
  projection_version TEXT NOT NULL,
  scope TEXT NOT NULL,
  bucket_size_ms INTEGER NOT NULL,
  bucket_start_ms INTEGER NOT NULL,
  token_id TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  symbol TEXT NOT NULL,
  post_count INTEGER NOT NULL,
  direct_mention_count INTEGER NOT NULL,
  selected_symbol_mention_count INTEGER NOT NULL,
  weighted_mention_count REAL NOT NULL,
  attribution_confidence_sum REAL NOT NULL,
  watched_post_count INTEGER NOT NULL,
  unique_author_count INTEGER NOT NULL,
  watched_author_count INTEGER NOT NULL,
  weighted_reach REAL NOT NULL,
  first_seen_ms INTEGER,
  latest_seen_ms INTEGER,
  top_event_ids_json TEXT NOT NULL,
  top_authors_json TEXT NOT NULL,
  source_event_ids_json TEXT NOT NULL,
  source_attribution_ids_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_token_social_buckets_key
  ON token_social_buckets(projection_version, scope, bucket_size_ms, bucket_start_ms, token_id);
CREATE INDEX IF NOT EXISTS idx_token_social_buckets_window
  ON token_social_buckets(projection_version, scope, bucket_size_ms, bucket_start_ms);
CREATE INDEX IF NOT EXISTS idx_token_social_buckets_token_window
  ON token_social_buckets(projection_version, scope, token_id, bucket_start_ms);

CREATE TABLE IF NOT EXISTS token_social_bucket_authors (
  author_bucket_id TEXT PRIMARY KEY,
  projection_version TEXT NOT NULL,
  scope TEXT NOT NULL,
  bucket_size_ms INTEGER NOT NULL,
  bucket_start_ms INTEGER NOT NULL,
  token_id TEXT NOT NULL,
  author_handle TEXT NOT NULL,
  post_count INTEGER NOT NULL,
  watched_post_count INTEGER NOT NULL,
  followers_max INTEGER NOT NULL,
  first_seen_ms INTEGER NOT NULL,
  latest_seen_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_token_social_bucket_authors_key
  ON token_social_bucket_authors(projection_version, scope, bucket_size_ms, bucket_start_ms, token_id, author_handle);

CREATE TABLE IF NOT EXISTS token_flow_window_snapshots (
  window_snapshot_id TEXT PRIMARY KEY,
  projection_version TEXT NOT NULL,
  window TEXT NOT NULL,
  scope TEXT NOT NULL,
  decision_time_ms INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  token_id TEXT NOT NULL,
  identity_json TEXT NOT NULL,
  flow_json TEXT NOT NULL,
  timeline_json TEXT NOT NULL,
  market_json TEXT NOT NULL,
  score_versions_json TEXT NOT NULL,
  component_payload_json TEXT NOT NULL,
  data_health_json TEXT NOT NULL,
  source_bucket_range_json TEXT NOT NULL,
  source_max_received_at_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_token_flow_window_snapshots_lookup
  ON token_flow_window_snapshots(projection_version, window, scope, decision_time_ms, rank);
```

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_projection_schema.py tests/test_sqlite_schema.py
git add src/gmgn_twitter_intel/storage/sqlite_schema.py tests/test_projection_schema.py
git commit -m "feat: add token social read model schema"
```

## Task 3: Projection Repository

**Files:**
- Create: `src/gmgn_twitter_intel/storage/projection_repository.py`
- Test: `tests/test_projection_repository.py`

- [ ] **Step 1: Write repository tests**

Cover:

- `start_run()` inserts running run row.
- `finish_run()` records status and counts.
- `get_offset()` returns default missing offset.
- `advance_offset()` is idempotent.
- `enqueue_dirty_range()` dedupes same projection/entity/range/reason.

- [ ] **Step 2: Implement repository**

Expose methods:

```python
class ProjectionRepository:
    def __init__(self, conn: sqlite3.Connection): ...
    def get_offset(self, projection_name: str) -> dict[str, Any] | None: ...
    def start_run(self, *, projection_name: str, projection_version: str, mode: str, source_start_ms: int | None, source_end_ms: int | None) -> dict[str, Any]: ...
    def finish_run(self, *, run_id: str, status: str, rows_read: int, rows_written: int, dirty_ranges_written: int, error: str | None = None, commit: bool = True) -> None: ...
    def advance_offset(self, *, projection_name: str, projection_version: str, source_table: str, source_max_received_at_ms: int, source_max_id: str, last_run_id: str, lag_ms: int, status: str = "ready", commit: bool = True) -> None: ...
    def enqueue_dirty_range(self, *, projection_name: str, projection_version: str, entity_type: str, entity_key: str, window: str | None, scope: str | None, start_ms: int, end_ms: int, reason: str, commit: bool = True) -> str: ...
    def claim_dirty_ranges(self, *, projection_name: str, projection_version: str, limit: int, commit: bool = True) -> list[dict[str, Any]]: ...
```

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_projection_repository.py
git add src/gmgn_twitter_intel/storage/projection_repository.py tests/test_projection_repository.py
git commit -m "feat: add projection repository"
```

## Task 4: Token Social Projection Repository

**Files:**
- Create: `src/gmgn_twitter_intel/storage/token_social_projection_repository.py`
- Test: `tests/test_token_social_projection_repository.py`

- [ ] **Step 1: Write tests**

Use small fixture rows and assert:

- upsert bucket replaces same bucket key instead of duplicating.
- upsert author bucket preserves exact author identity.
- reading buckets for a token/window returns ordered bucket rows.
- reading authors across multiple buckets dedupes by `author_handle`.

- [ ] **Step 2: Implement repository**

Methods:

```python
class TokenSocialProjectionRepository:
    def upsert_bucket(self, *, bucket: dict[str, Any], commit: bool = True) -> None: ...
    def replace_bucket_authors(self, *, projection_version: str, scope: str, bucket_size_ms: int, bucket_start_ms: int, token_id: str, authors: list[dict[str, Any]], commit: bool = True) -> int: ...
    def buckets_for_window(self, *, projection_version: str, scope: str, bucket_size_ms: int, start_ms: int, end_ms: int, token_id: str | None = None) -> list[dict[str, Any]]: ...
    def authors_for_window(self, *, projection_version: str, scope: str, bucket_size_ms: int, start_ms: int, end_ms: int, token_id: str) -> list[dict[str, Any]]: ...
```

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_token_social_projection_repository.py
git add src/gmgn_twitter_intel/storage/token_social_projection_repository.py tests/test_token_social_projection_repository.py
git commit -m "feat: add token social projection repository"
```

## Task 5: Token Social Projection Worker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/projection_worker.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Test: `tests/test_projection_worker.py`

- [ ] **Step 1: Write failing worker tests**

Create fixture events and attributions. Assert:

- worker processes only rows after offset.
- all/matched scopes are computed separately.
- 30s bucket assignment is deterministic.
- `projection_offsets` advances only after bucket writes succeed.
- worker writes dirty ranges for affected token/window/scope.

- [ ] **Step 2: Implement worker with bounded batches**

Rules:

- `projection_name="token-social-buckets"`.
- `projection_version="token-social-buckets-v1"`.
- batch limit default `2000`.
- use source cursor `(received_at_ms, attribution_id)`.
- do not run inside API request handlers.
- use existing `write_lock`.

- [ ] **Step 3: Wire runtime task**

In `api/app.py`, add optional worker task controlled by settings:

- `projections.enabled`
- `projections.poll_interval_seconds`
- `projections.batch_limit`

Default enabled for Docker/local serve after tests cover it.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_projection_worker.py tests/test_api_health.py
git add src/gmgn_twitter_intel/pipeline/projection_worker.py src/gmgn_twitter_intel/api/app.py tests/test_projection_worker.py
git commit -m "feat: maintain token social bucket projections"
```

## Task 6: Token Flow Window Snapshot Worker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/token_flow_snapshot_worker.py`
- Create: `src/gmgn_twitter_intel/storage/token_flow_snapshot_repository.py`
- Test: `tests/test_token_flow_snapshot_worker.py`

- [ ] **Step 1: Write tests**

Assert:

- dirty range for a token causes 5m/all snapshot rebuild.
- no-lookahead market block uses snapshots at-or-before decision time.
- score payload matches existing `TokenFlowService` for fixture data.
- stale projection status is set when rebuild fails.

- [ ] **Step 2: Implement snapshot repository**

Methods:

```python
class TokenFlowSnapshotRepository:
    def replace_window_snapshot(self, *, projection_version: str, window: str, scope: str, decision_time_ms: int, items: list[dict[str, Any]], source_max_received_at_ms: int, commit: bool = True) -> int: ...
    def latest_window_snapshot(self, *, projection_version: str, window: str, scope: str, limit: int) -> dict[str, Any]: ...
```

- [ ] **Step 3: Implement snapshot worker**

Build top-N from `token_social_buckets` and `token_social_bucket_authors`, then reuse existing scoring functions from:

- `baseline_scoring.py`
- `timeline_features.py`
- `social_heat_scoring.py`
- `discussion_quality_scoring.py`
- `propagation_scoring.py`
- `tradeability_scoring.py`
- `timing_scoring.py`
- `opportunity_scoring.py`

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_token_flow_snapshot_worker.py tests/test_token_flow_no_lookahead.py
git add src/gmgn_twitter_intel/pipeline/token_flow_snapshot_worker.py src/gmgn_twitter_intel/storage/token_flow_snapshot_repository.py tests/test_token_flow_snapshot_worker.py
git commit -m "feat: build token flow window snapshots"
```

## Task 7: Token Flow API Cutover

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/token_flow_read_model_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Test: `tests/test_api_http.py`, `tests/test_token_flow_read_model_service.py`

- [ ] **Step 1: Write read model service tests**

Assert:

- service returns latest snapshot rows by window/scope.
- payload includes projection status.
- stale projection returns explicit error object.
- no raw aggregation fallback is called.

- [ ] **Step 2: Implement read model service**

Return shape:

```python
{
    "items": [...],
    "projection": {
        "projection_name": "token-flow-window-snapshots",
        "projection_version": "token-flow-window-snapshots-v1",
        "source_max_received_at_ms": 1778024085340,
        "updated_at_ms": 1778024090000,
        "lag_ms": 4660,
        "status": "ready",
    },
}
```

- [ ] **Step 3: Cut API to read model**

In `api/http.py`, `/api/token-flow` should use `TokenFlowReadModelService`. Keep raw `TokenFlowService` import only for ops validation and tests.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_token_flow_read_model_service.py tests/test_api_http.py tests/test_token_flow_social_heat_contract.py
git add src/gmgn_twitter_intel/retrieval/token_flow_read_model_service.py src/gmgn_twitter_intel/api/http.py tests/test_token_flow_read_model_service.py tests/test_api_http.py
git commit -m "feat: serve token flow from read model"
```

## Task 8: Timeline Summary Cutover

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- Test: `tests/test_token_social_timeline_service.py`

- [ ] **Step 1: Write tests**

Assert:

- summary and buckets are read from projection tables.
- posts still come from `event_token_attributions JOIN events`.
- unique authors across multiple buckets are exact.
- price uses at-or-before snapshot and does not look ahead.

- [ ] **Step 2: Implement projection-backed summary**

Change `timeline()`:

- load bucket rows from `TokenSocialProjectionRepository`;
- load authors from `token_social_bucket_authors`;
- build summary from projected bucket rows;
- keep `_post_rows()` for evidence pagination.

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_token_social_timeline_service.py tests/test_token_flow_no_lookahead.py
git add src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py tests/test_token_social_timeline_service.py
git commit -m "feat: serve timeline summaries from projections"
```

## Task 9: Account Quality Incremental Projection

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/account_quality_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
- Test: `tests/test_account_quality_projection_worker.py`, `tests/test_account_quality_service.py`

- [ ] **Step 1: Write tests**

Assert:

- worker updates `account_profiles` and `account_token_call_stats` from new attributions.
- outcome fields remain `insufficient_market_history` until horizon snapshots exist.
- settlement updates outcome fields after market snapshots arrive.
- API does not run backfill on request.

- [ ] **Step 2: Implement worker**

Use `projection_offsets` with:

- `projection_name="account-quality"`
- `projection_version="account-quality-v1"`
- source table `event_token_attributions`

Maintain existing tables:

- `account_profiles`
- `account_token_call_stats`
- `account_quality_snapshots`

- [ ] **Step 3: Modify API semantics**

`/api/account-quality` should return:

```python
{
    "query": {"handles": ["toly"]},
    "projection": {"status": "ready", "lag_ms": 1200, "projection_version": "account-quality-v1"},
    "accounts": [...]
}
```

If missing projection, return `projection_missing` with HTTP 503 for production endpoint.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_account_quality_projection_worker.py tests/test_account_quality_service.py tests/test_api_http.py
git add src/gmgn_twitter_intel/pipeline/account_quality_projection_worker.py src/gmgn_twitter_intel/retrieval/account_quality_service.py tests/test_account_quality_projection_worker.py tests/test_account_quality_service.py
git commit -m "feat: project account quality incrementally"
```

## Task 10: Ops Commands

**Files:**
- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add CLI tests**

Commands:

```bash
uv run gmgn-twitter-intel ops projection-status
uv run gmgn-twitter-intel ops run-projections --once --limit 2000
uv run gmgn-twitter-intel ops rebuild-projections --projection token-social-buckets --from-ms 0 --to-ms 9999999999999
uv run gmgn-twitter-intel ops validate-projections --sample 100
```

Expected JSON:

- `projection-status` returns offsets/runs/lag.
- `run-projections --once` returns rows read/written.
- `rebuild-projections` writes run row with mode `rebuild`.
- `validate-projections` returns sampled mismatch count.

- [ ] **Step 2: Implement commands**

Wire commands to repositories/workers. Do not start API server. Use the same SQLite path from settings.

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest tests/test_cli.py
git add src/gmgn_twitter_intel/cli.py tests/test_cli.py
git commit -m "feat: add projection ops commands"
```

## Task 11: Validation and Benchmark

**Files:**
- Create: `tests/test_projection_reconciliation.py`
- Create: `tests/test_projection_performance_contract.py`
- Modify: `docs/superpowers/specs/2026-05-06-materialized-read-models-production-cn.md`

- [ ] **Step 1: Add reconciliation tests**

For seeded fixtures:

- raw token-flow aggregation equals projection token-flow for 5m/1h.
- raw timeline bucket summary equals projection summary.
- account quality raw backfill result equals incremental projection result.

- [ ] **Step 2: Add performance contract tests**

Use deterministic medium fixture, not live DB:

- token-flow read model returns top 50 without scanning `event_token_attributions`.
- timeline summary reads bucket tables.
- account-quality API reads account tables only.

- [ ] **Step 3: Document live validation runbook**

Add commands:

```bash
uv run gmgn-twitter-intel ops projection-status
uv run gmgn-twitter-intel ops validate-projections --sample 100
curl -sS http://127.0.0.1:8765/readyz
```

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/test_projection_reconciliation.py tests/test_projection_performance_contract.py
git add tests/test_projection_reconciliation.py tests/test_projection_performance_contract.py docs/superpowers/specs/2026-05-06-materialized-read-models-production-cn.md
git commit -m "test: add projection reconciliation contracts"
```

## Task 12: Production Cutover

**Files:**
- Modify: `compose.yaml`
- Modify: `src/gmgn_twitter_intel/settings.py`
- Modify: `README.md`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Add settings tests**

Settings:

- `projections.enabled`
- `projections.poll_interval_seconds`
- `projections.batch_limit`
- `projections.max_allowed_lag_seconds`

- [ ] **Step 2: Enable projections in runtime config**

Default:

```yaml
projections:
  enabled: true
  poll_interval_seconds: 2
  batch_limit: 2000
  max_allowed_lag_seconds: 30
```

- [ ] **Step 3: Update README**

Document:

- read model semantics;
- eventual consistency;
- projection ops commands;
- no raw fallback after cutover;
- rebuild procedure.

- [ ] **Step 4: Run full validation**

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
docker compose up -d --build app
docker ps --format 'table {{.Names}}\t{{.Status}}' | rg 'gmgn-twitter-intel|NAMES'
curl -sS --max-time 5 http://127.0.0.1:8765/readyz
```

Expected:

- tests pass;
- container healthy;
- `/readyz` reports projection status and no stale projection;
- token-flow API reads read model.

- [ ] **Step 5: Commit**

```bash
git add compose.yaml src/gmgn_twitter_intel/settings.py README.md tests/test_settings.py
git commit -m "docs: document projection runtime operations"
```

## Rollback

Rollback is a code rollback, not a hidden runtime fallback:

1. Stop app.
2. Revert cutover commit.
3. Keep projection tables; they are derived data and can remain unused.
4. Restart app.
5. Run `uv run pytest tests/test_api_health.py tests/test_api_http.py`.

## Final Verification

Before merging the projection branch:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
docker compose up -d --build app
curl -sS --max-time 5 http://127.0.0.1:8765/readyz
uv run gmgn-twitter-intel ops projection-status
uv run gmgn-twitter-intel ops validate-projections --sample 100
```

Expected:

- all tests pass;
- container healthy;
- projection lag under configured SLA;
- validation mismatch count is 0 for sampled windows;
- API endpoints do not perform raw aggregation for token-flow/account-quality request paths.
