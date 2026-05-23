# Token Radar Storage Root Fix And Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Token Radar 从一个高频追加、携带完整 JSONB 快照的巨型 read model，拆成小而快的当前读模型、可控保留的历史索引、按分区淘汰的审计快照，并一次性删除旧 Token Radar 派生数据，从空的新 read models 重新开始。

**Architecture:** 当前页面和 API 只读 `token_radar_current_rows`，它保存最新 window/scope/lane/rank 的完整展示 payload，规模固定在几千行内。历史 rank 进入轻量 `token_radar_rank_history`，完整 factor snapshot 只进入按 `computed_at_ms` range partition 的 `token_radar_snapshot_audit`，由显式 ops 维护分区和保留期。旧 `token_radar_rows`、旧 retention runs、旧 Token Radar coverage/offset/run 派生状态全部作为 rebuildable read-model data 删除；运行时代码不保留旧表兼容路径。

**Tech Stack:** Python, FastAPI sync handlers, psycopg/PostgreSQL, Alembic migrations, pytest, Docker Compose, existing Kappa/CQRS worker runtime.

---

## Root Cause Summary

Measured on the live local Docker database:

- `token_radar_rows` total size: `120GB`.
- Heap: `28GB`.
- Indexes: `22GB`.
- TOAST / aux storage: `70GB`.
- Main relation estimated rows: about `17M`.
- TOAST relation estimated rows: about `39.6M`.
- Current live rows reported by `pg_stat_user_tables`: about `1.18M`.
- `vacuum_count`, `autovacuum_count`, `analyze_count`, `autoanalyze_count` for the main table were `0`.
- `token_radar_retention_runs` had only three rows; only one `execute` run deleted `10,000` rows.

Code root cause:

- `TokenRadarProjectionWorker` runs hot windows frequently and background windows on a cold interval.
- `TokenRadarProjection.rebuild()` creates ranked rows with full `factor_snapshot_json`.
- `TokenRadarRepository.replace_rows()` deletes only rows for the exact same `(projection_version, window, scope, computed_at_ms)`, then inserts a full new batch.
- The table therefore stores many copies of mostly repeated current read-model snapshots.

The design issue is not "the database is too small" or "one index is missing." The issue is that one table is serving three incompatible purposes:

1. current Token Radar read model,
2. historical rank/settlement evidence,
3. full audit/replay blob storage.

The root fix is to split those purposes.

## Official PostgreSQL Practice Constraints

The implementation should follow these PostgreSQL practices:

- Routine vacuum keeps tables healthy, but it is not a primary design for deleting huge time-series history. Use it continuously, not as the only cleanup mechanism. Reference: [PostgreSQL Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
- `VACUUM FULL` rewrites the table and requires an exclusive lock. It is a one-time maintenance-window tool for reclaiming severe legacy bloat, not normal runtime cleanup. Reference: [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html).
- Time-bounded data should be partitioned so old data can be removed by dropping/detaching partitions instead of massive deletes. Reference: [PostgreSQL Declarative Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html).
- Large JSONB values are stored using PostgreSQL TOAST, so a design that appends large JSONB snapshots at high frequency will create large auxiliary storage. Reference: [PostgreSQL TOAST](https://www.postgresql.org/docs/current/storage-toast.html).
- When rebuilding large indexes on live systems, prefer concurrent index rebuild patterns where available. Reference: [PostgreSQL REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html).

## Target Data Model

### `token_radar_current_rows`

Purpose: serving `/api/token-radar`, CLI `asset-flow`, and current factor diagnostics.

Properties:

- one runtime writer: `TokenRadarProjectionWorker`,
- latest only,
- full current display payload allowed,
- no historical accumulation,
- small enough for fast API reads and fast vacuum/analyze.

Suggested shape:

```sql
CREATE TABLE IF NOT EXISTS token_radar_current_rows (
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  lane TEXT NOT NULL,
  rank BIGINT NOT NULL,
  row_id TEXT NOT NULL,
  computed_at_ms BIGINT NOT NULL,
  source_max_received_at_ms BIGINT NOT NULL,
  intent_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  pricefeed_id TEXT,
  intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  primary_venue_json JSONB,
  target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_version TEXT NOT NULL,
  decision TEXT NOT NULL,
  data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  listed_at_ms BIGINT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (projection_version, "window", scope, lane, rank)
);

CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_lookup
  ON token_radar_current_rows(projection_version, "window", scope, lane, rank);

CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_target
  ON token_radar_current_rows(projection_version, "window", scope, target_type, target_id);
```

### `token_radar_rank_history`

Purpose: lightweight historical rank/decision tracking, without TOAST-heavy payloads.

Properties:

- append-only,
- no full factor snapshot,
- can retain longer than audit snapshots,
- partitioned by `computed_at_ms`.

Suggested shape:

```sql
CREATE TABLE IF NOT EXISTS token_radar_rank_history (
  history_id TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  lane TEXT NOT NULL,
  rank BIGINT NOT NULL,
  computed_at_ms BIGINT NOT NULL,
  source_max_received_at_ms BIGINT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  intent_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  factor_version TEXT NOT NULL,
  rank_score INTEGER,
  raw_alpha_score DOUBLE PRECISION,
  decision TEXT NOT NULL,
  listed_at_ms BIGINT,
  source_event_count INTEGER NOT NULL DEFAULT 0,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY (history_id, computed_at_ms)
) PARTITION BY RANGE (computed_at_ms);
```

### `token_radar_snapshot_audit`

Purpose: bounded replay/settlement/debug snapshots. This is the only new table that stores full `factor_snapshot_json` history.

Properties:

- partitioned by `computed_at_ms`,
- written at a controlled interval,
- stores only rows selected for settlement/audit,
- retention default 7 days,
- old data removed by dropping partitions.

Suggested shape:

```sql
CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit (
  snapshot_id TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  lane TEXT NOT NULL,
  rank BIGINT NOT NULL,
  row_id TEXT NOT NULL,
  computed_at_ms BIGINT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  intent_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  factor_version TEXT NOT NULL,
  factor_snapshot_json JSONB NOT NULL,
  target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY (snapshot_id, computed_at_ms)
) PARTITION BY RANGE (computed_at_ms);
```

### `token_radar_storage_maintenance_runs`

Purpose: audit every destructive or storage-maintenance operation.

```sql
CREATE TABLE IF NOT EXISTS token_radar_storage_maintenance_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  operation TEXT NOT NULL,
  status TEXT NOT NULL,
  dry_run BOOLEAN NOT NULL,
  details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  rows_planned BIGINT NOT NULL DEFAULT 0,
  rows_changed BIGINT NOT NULL DEFAULT 0,
  bytes_before BIGINT,
  bytes_after BIGINT,
  started_at_ms BIGINT NOT NULL,
  finished_at_ms BIGINT,
  error TEXT,
  created_at_ms BIGINT NOT NULL
);
```

## Rollout Guardrails

- This is a clean-slate hard reset. Token Radar-dependent product surfaces may temporarily degrade, read empty, or return errors during the cutover.
- The non-negotiable success criterion is that new facts continue to enter PostgreSQL and the new Token Radar write path persists rows into `token_radar_current_rows`, `token_radar_rank_history`, and `token_radar_snapshot_audit`.
- Do not modify or clean these material fact tables in this plan: `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, and `enriched_events`.
- Do not run `DROP`, `TRUNCATE`, `VACUUM FULL`, or `REINDEX` automatically from normal workers.
- All destructive cleanup must require `--execute`; default is `--dry-run`.
- Confirm `uv run gmgn-twitter-intel config` reports operator-owned runtime paths before running real-data cleanup.
- Never print secrets from config; report only paths, booleans, counts, sizes, and status.
- Do not preserve old Token Radar derived state. `token_radar_target_first_seen`, Token Radar projection coverage, Token Radar projection offsets, and Token Radar projection runs are reset so the system starts clean.
- Keep one runtime writer for each read model.
- Do not touch unresolved merge-conflict files until the worktree is clean or a dedicated worktree is created.

## Hard-Cut Success Criteria

During this migration, business continuity is secondary. These checks define success:

- Collector still writes new `events`.
- Token intent / resolution workers still write or update `token_intents` and `token_intent_resolutions`.
- Market capture still writes `market_ticks`.
- Token Radar projection writes current rows into `token_radar_current_rows`.
- Token Radar projection writes bounded lightweight history into `token_radar_rank_history`.
- Token Radar projection writes bounded audit snapshots into `token_radar_snapshot_audit`.
- Runtime source code has no remaining non-migration references to `token_radar_rows`.
- Old Token Radar derived data is gone. New rows start at the first successful post-reset projection cycle.

These checks define failure:

- Fact ingestion stops.
- New Token Radar projection cycles cannot commit.
- Database startup or migration fails.
- `token_radar_rows` remains in runtime code after the clean-slate reset. The migration is not complete until `rg -n "token_radar_rows" src/gmgn_twitter_intel` only finds historical migrations or explicit cleanup documentation.

---

## Task 1: Add Schema For Split Read Models

**Files:**

- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0083_token_radar_storage_root_fix.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1.1: Write schema test first**

Add a new test near `test_runtime_schema_contains_token_radar_retention_and_watchlist_signal_stats`:

```python
def test_runtime_schema_contains_token_radar_storage_root_fix_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row["table_name"]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
        }
        columns = {
            (row["table_name"], row["column_name"]): row["data_type"]
            for row in conn.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'token_radar_current_rows',
                    'token_radar_rank_history',
                    'token_radar_snapshot_audit',
                    'token_radar_storage_maintenance_runs'
                  )
                """
            ).fetchall()
        }
        indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'token_radar_current_rows',
                    'token_radar_rank_history',
                    'token_radar_snapshot_audit',
                    'token_radar_storage_maintenance_runs'
                  )
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "token_radar_current_rows",
        "token_radar_rank_history",
        "token_radar_snapshot_audit",
        "token_radar_storage_maintenance_runs",
    }.issubset(tables)
    assert columns[("token_radar_current_rows", "factor_snapshot_json")] == "jsonb"
    assert columns[("token_radar_rank_history", "rank_score")] in {"integer", "bigint"}
    assert columns[("token_radar_snapshot_audit", "factor_snapshot_json")] == "jsonb"
    assert {
        "idx_token_radar_current_rows_lookup",
        "idx_token_radar_current_rows_target",
        "idx_token_radar_rank_history_lookup",
        "idx_token_radar_snapshot_audit_lookup",
    }.issubset(indexes)
```

- [ ] **Step 1.2: Run schema test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_postgres_schema_runtime.py::test_runtime_schema_contains_token_radar_storage_root_fix_tables -q
```

Expected:

```text
FAILED because the new tables do not exist
```

- [ ] **Step 1.3: Add Alembic migration**

Create `20260523_0083_token_radar_storage_root_fix.py` with:

```python
"""Split Token Radar current, history, and audit storage."""

from __future__ import annotations

from alembic import op

revision = "20260523_0083"
down_revision = "20260522_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_current_rows (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          row_id TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL,
          intent_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          primary_venue_json JSONB,
          target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          factor_version TEXT NOT NULL,
          decision TEXT NOT NULL,
          data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          listed_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_version, "window", scope, lane, rank)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_lookup
          ON token_radar_current_rows(projection_version, "window", scope, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_target
          ON token_radar_current_rows(projection_version, "window", scope, target_type, target_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_history (
          history_id TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          intent_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          factor_version TEXT NOT NULL,
          rank_score INTEGER,
          raw_alpha_score DOUBLE PRECISION,
          decision TEXT NOT NULL,
          listed_at_ms BIGINT,
          source_event_count INTEGER NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (history_id, computed_at_ms)
        ) PARTITION BY RANGE (computed_at_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_history_lookup
          ON token_radar_rank_history(projection_version, "window", scope, computed_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit (
          snapshot_id TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          row_id TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          intent_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          factor_version TEXT NOT NULL,
          factor_snapshot_json JSONB NOT NULL,
          target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (snapshot_id, computed_at_ms)
        ) PARTITION BY RANGE (computed_at_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_snapshot_audit_lookup
          ON token_radar_snapshot_audit(projection_version, "window", scope, computed_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_storage_maintenance_runs (
          run_id TEXT PRIMARY KEY,
          mode TEXT NOT NULL,
          operation TEXT NOT NULL,
          status TEXT NOT NULL,
          dry_run BOOLEAN NOT NULL,
          details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          rows_planned BIGINT NOT NULL DEFAULT 0,
          rows_changed BIGINT NOT NULL DEFAULT 0,
          bytes_before BIGINT,
          bytes_after BIGINT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT,
          error TEXT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_radar_storage_maintenance_runs")
    op.execute("DROP TABLE IF EXISTS token_radar_snapshot_audit CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_history CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_current_rows")
```

- [ ] **Step 1.4: Run migration tests**

Run:

```bash
uv run pytest tests/integration/test_postgres_schema_runtime.py::test_runtime_schema_contains_token_radar_storage_root_fix_tables -q
```

Expected:

```text
1 passed
```

## Task 2: Add Partition Maintenance Service

**Files:**

- Create: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_storage_maintenance.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Test: `tests/unit/test_token_radar_storage_maintenance.py`

- [ ] **Step 2.1: Write tests for partition names and ranges**

Create `tests/unit/test_token_radar_storage_maintenance.py`:

```python
from gmgn_twitter_intel.domains.token_intel.services.token_radar_storage_maintenance import (
    DAY_MS,
    partition_name,
    partition_range_for_day,
)


def test_partition_name_is_stable_and_table_specific():
    assert partition_name("token_radar_snapshot_audit", 1_779_494_400_000) == (
        "token_radar_snapshot_audit_20260523"
    )


def test_partition_range_for_day_uses_utc_day_boundaries():
    start_ms, end_ms = partition_range_for_day(1_779_494_400_000)

    assert end_ms - start_ms == DAY_MS
    assert start_ms == 1_779_465_600_000
```

- [ ] **Step 2.2: Implement partition helper functions**

Create:

```python
from __future__ import annotations

import datetime as dt
import re
import time
import uuid
from typing import Any

from psycopg.types.json import Jsonb

DAY_MS = 24 * 60 * 60 * 1000
PARTITIONED_TABLES = ("token_radar_rank_history", "token_radar_snapshot_audit")
_PARTITION_RE = re.compile(r"^[a-z_][a-z0-9_]*_\\d{8}$")


def partition_range_for_day(ms: int) -> tuple[int, int]:
    instant = dt.datetime.fromtimestamp(int(ms) / 1000, tz=dt.UTC)
    day_start = dt.datetime(instant.year, instant.month, instant.day, tzinfo=dt.UTC)
    start_ms = int(day_start.timestamp() * 1000)
    return start_ms, start_ms + DAY_MS


def partition_name(table: str, ms: int) -> str:
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"unsupported_partitioned_table:{table}")
    start_ms, _ = partition_range_for_day(ms)
    day = dt.datetime.fromtimestamp(start_ms / 1000, tz=dt.UTC).strftime("%Y%m%d")
    name = f"{table}_{day}"
    if not _PARTITION_RE.fullmatch(name):
        raise ValueError(f"invalid_partition_name:{name}")
    return name
```

- [ ] **Step 2.3: Add repository methods for maintenance audit**

In `TokenRadarRepository`, add:

```python
def insert_storage_maintenance_run(self, payload: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
    row = self.conn.execute(
        """
        INSERT INTO token_radar_storage_maintenance_runs(
          run_id, mode, operation, status, dry_run, details_json,
          rows_planned, rows_changed, bytes_before, bytes_after,
          started_at_ms, finished_at_ms, error, created_at_ms
        )
        VALUES (
          %(run_id)s, %(mode)s, %(operation)s, %(status)s, %(dry_run)s, %(details_json)s,
          %(rows_planned)s, %(rows_changed)s, %(bytes_before)s, %(bytes_after)s,
          %(started_at_ms)s, %(finished_at_ms)s, %(error)s, %(created_at_ms)s
        )
        RETURNING *
        """,
        {**payload, "details_json": Jsonb(payload.get("details_json") or {})},
    ).fetchone()
    if commit:
        self.conn.commit()
    return dict(row) if row else dict(payload)
```

- [ ] **Step 2.4: Add service methods**

Add `TokenRadarStorageMaintenanceService`:

```python
class TokenRadarStorageMaintenanceService:
    def __init__(self, *, token_radar: Any) -> None:
        self.token_radar = token_radar
        self.conn = token_radar.conn

    def ensure_daily_partitions(self, *, now_ms: int | None = None, days_ahead: int = 2) -> dict[str, Any]:
        resolved_now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        created: list[str] = []
        for table in PARTITIONED_TABLES:
            for offset in range(0, max(1, int(days_ahead)) + 1):
                day_ms = resolved_now_ms + offset * DAY_MS
                name = partition_name(table, day_ms)
                start_ms, end_ms = partition_range_for_day(day_ms)
                self.conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {name}
                    PARTITION OF {table}
                    FOR VALUES FROM ({start_ms}) TO ({end_ms})
                    """
                )
                created.append(name)
        self.conn.commit()
        return {"created_or_existing": created, "days_ahead": int(days_ahead)}
```

- [ ] **Step 2.5: Run service tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_storage_maintenance.py -q
```

Expected:

```text
All tests pass.
```

## Task 3: Write Current Rows And Bounded History From Projection

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Test: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 3.1: Add repository test fake**

In `tests/unit/test_token_radar_projection.py`, add a fake repository object for write capture:

```python
class RecordingTokenRadarRepository:
    def __init__(self):
        self.current_calls = []
        self.history_calls = []
        self.audit_calls = []
        self.coverage_calls = []

    def mark_coverage(self, **kwargs):
        self.coverage_calls.append(kwargs)

    def replace_rows(self, **kwargs):
        raise AssertionError("projection must not write legacy token_radar_rows")

    def replace_current_rows(self, **kwargs):
        self.current_calls.append(kwargs)
        return True

    def append_rank_history(self, **kwargs):
        self.history_calls.append(kwargs)

    def append_snapshot_audit(self, **kwargs):
        self.audit_calls.append(kwargs)

    def first_seen_by_identity(self, **kwargs):
        return {}

    def upsert_first_seen_batch(self, **kwargs):
        return None
```

- [ ] **Step 3.2: Add failing projection write test**

Add:

```python
def test_projection_writes_current_rows_and_lightweight_history(monkeypatch):
    token_radar = RecordingTokenRadarRepository()
    repos = type("Repos", (), {"token_radar": token_radar, "conn": object()})()

    source = source_row("event-1", received_at_ms=1_777_800_000_000)
    source["target_type"] = "Asset"
    source["target_id"] = "asset:eip155:8453:erc20:0xabc"
    source["asset_symbol"] = "ABC"
    source["asset_chain_id"] = "eip155:8453"
    source["asset_address"] = "0xabc"

    projection = TokenRadarProjection(repos=repos)
    monkeypatch.setattr(projection, "_source_rows", lambda **_: [source])

    result = projection.rebuild(window="5m", scope="all", now_ms=1_777_800_060_000, limit=10)

    assert result["status"] == "ready"
    assert token_radar.current_calls
    assert token_radar.history_calls
    assert token_radar.audit_calls
    assert token_radar.current_calls[0]["rows"][0]["factor_snapshot_json"]
    assert "factor_snapshot_json" not in token_radar.history_calls[0]["rows"][0]
```

- [ ] **Step 3.3: Add `replace_current_rows()`**

Implement in `TokenRadarRepository`:

```python
def replace_current_rows(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    computed_at_ms: int,
    rows: list[dict[str, Any]],
    commit: bool = True,
) -> bool:
    for row in rows:
        _validate_factor_contract(row)
    listed_at_by_key = self.first_seen_by_identity(
        projection_version=projection_version,
        window=window,
        scope=scope,
        rows=rows,
    )
    self.conn.execute(
        """
        DELETE FROM token_radar_current_rows
        WHERE projection_version = %s AND "window" = %s AND scope = %s
        """,
        (projection_version, window, scope),
    )
    now_ms = _now_ms()
    for row in rows:
        payload = _json_payload(
            {
                **row,
                "projection_version": projection_version,
                "window": window,
                "scope": scope,
                "computed_at_ms": computed_at_ms,
                "listed_at_ms": listed_at_by_key.get(_identity_key(row), int(computed_at_ms)),
                "updated_at_ms": now_ms,
            }
        )
        self.conn.execute(
            """
            INSERT INTO token_radar_current_rows(
              row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
              lane, rank, intent_id, event_id, target_type, target_id, pricefeed_id, intent_json,
              asset_json, primary_venue_json, target_json, factor_snapshot_json, factor_version,
              decision, data_health_json, source_event_ids_json, listed_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
              %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
              %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(intent_json)s, %(asset_json)s,
              %(primary_venue_json)s, %(target_json)s, %(factor_snapshot_json)s, %(factor_version)s,
              %(decision)s, %(data_health_json)s, %(source_event_ids_json)s, %(listed_at_ms)s,
              %(created_at_ms)s, %(updated_at_ms)s
            )
            """,
            payload,
        )
    self.upsert_first_seen_batch(
        projection_version=projection_version,
        window=window,
        scope=scope,
        rows=rows,
        computed_at_ms=int(computed_at_ms),
        commit=False,
    )
    if commit:
        self.conn.commit()
    return True
```

- [ ] **Step 3.4: Add `append_rank_history()`**

Implement:

```python
def append_rank_history(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    computed_at_ms: int,
    rows: list[dict[str, Any]],
    commit: bool = True,
) -> int:
    inserted = 0
    for row in rows:
        snapshot = require_token_factor_snapshot(row.get("factor_snapshot_json"), field_name="factor_snapshot_json")
        composite = snapshot.get("composite") or {}
        payload = {
            "history_id": _stable_id(
                "token-radar-rank-history",
                projection_version,
                window,
                scope,
                str(computed_at_ms),
                str(row.get("lane") or ""),
                str(row.get("rank") or ""),
                str(row.get("target_id") or row.get("intent_id") or ""),
            ),
            "projection_version": projection_version,
            "window": window,
            "scope": scope,
            "lane": row.get("lane"),
            "rank": row.get("rank"),
            "computed_at_ms": computed_at_ms,
            "source_max_received_at_ms": row.get("source_max_received_at_ms"),
            "target_type": row.get("target_type"),
            "target_id": row.get("target_id"),
            "intent_id": row.get("intent_id"),
            "event_id": row.get("event_id"),
            "factor_version": row.get("factor_version"),
            "rank_score": composite.get("rank_score"),
            "raw_alpha_score": composite.get("raw_alpha_score"),
            "decision": row.get("decision"),
            "listed_at_ms": row.get("listed_at_ms"),
            "source_event_count": len(row.get("source_event_ids_json") or []),
            "created_at_ms": row.get("created_at_ms"),
        }
        self.conn.execute(
            """
            INSERT INTO token_radar_rank_history(
              history_id, projection_version, "window", scope, lane, rank, computed_at_ms,
              source_max_received_at_ms, target_type, target_id, intent_id, event_id, factor_version,
              rank_score, raw_alpha_score, decision, listed_at_ms, source_event_count, created_at_ms
            )
            VALUES (
              %(history_id)s, %(projection_version)s, %(window)s, %(scope)s, %(lane)s, %(rank)s,
              %(computed_at_ms)s, %(source_max_received_at_ms)s, %(target_type)s, %(target_id)s,
              %(intent_id)s, %(event_id)s, %(factor_version)s, %(rank_score)s, %(raw_alpha_score)s,
              %(decision)s, %(listed_at_ms)s, %(source_event_count)s, %(created_at_ms)s
            )
            ON CONFLICT DO NOTHING
            """,
            payload,
        )
        inserted += 1
    if commit:
        self.conn.commit()
    return inserted
```

- [ ] **Step 3.5: Add `append_snapshot_audit()`**

Implement:

```python
def append_snapshot_audit(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    computed_at_ms: int,
    rows: list[dict[str, Any]],
    commit: bool = True,
) -> int:
    inserted = 0
    for row in rows:
        _validate_factor_contract(row)
        payload = _json_payload(
            {
                **row,
                "snapshot_id": _stable_id(
                    "token-radar-snapshot-audit",
                    projection_version,
                    window,
                    scope,
                    str(computed_at_ms),
                    str(row.get("lane") or ""),
                    str(row.get("rank") or ""),
                    str(row.get("target_id") or row.get("intent_id") or ""),
                ),
                "projection_version": projection_version,
                "window": window,
                "scope": scope,
                "computed_at_ms": computed_at_ms,
            }
        )
        self.conn.execute(
            """
            INSERT INTO token_radar_snapshot_audit(
              snapshot_id, projection_version, "window", scope, lane, rank, row_id, computed_at_ms,
              target_type, target_id, intent_id, event_id, factor_version, factor_snapshot_json,
              target_json, data_health_json, source_event_ids_json, created_at_ms
            )
            VALUES (
              %(snapshot_id)s, %(projection_version)s, %(window)s, %(scope)s, %(lane)s, %(rank)s,
              %(row_id)s, %(computed_at_ms)s, %(target_type)s, %(target_id)s, %(intent_id)s,
              %(event_id)s, %(factor_version)s, %(factor_snapshot_json)s, %(target_json)s,
              %(data_health_json)s, %(source_event_ids_json)s, %(created_at_ms)s
            )
            ON CONFLICT DO NOTHING
            """,
            payload,
        )
        inserted += 1
    if commit:
        self.conn.commit()
    return inserted
```

- [ ] **Step 3.6: Wire projection writes**

In `TokenRadarProjection.rebuild()`, replace legacy `replace_rows(...)` with:

```python
rows_replaced = self.repos.token_radar.replace_current_rows(
    projection_version=PROJECTION_VERSION,
    window=window,
    scope=scope,
    computed_at_ms=computed_at_ms,
    rows=rows,
    commit=False,
)
self.repos.token_radar.append_rank_history(
    projection_version=PROJECTION_VERSION,
    window=window,
    scope=scope,
    computed_at_ms=computed_at_ms,
    rows=rows,
    commit=False,
)
self.repos.token_radar.append_snapshot_audit(
    projection_version=PROJECTION_VERSION,
    window=window,
    scope=scope,
    computed_at_ms=computed_at_ms,
    rows=_snapshot_audit_rows(rows=rows, window=window, scope=scope),
    commit=False,
)
```

Add helper:

```python
def _snapshot_audit_rows(*, rows: list[dict[str, Any]], window: str, scope: str) -> list[dict[str, Any]]:
    if window == "5m":
        return [row for row in rows if int(row.get("rank") or 0) <= 20]
    if scope == "matched":
        return rows[:50]
    return rows[:100]
```

- [ ] **Step 3.7: Run projection tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py -q
```

Expected:

```text
All tests pass.
```

## Task 4: Replace Legacy Current Reads With New Current Table

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 4.1: Add `latest_current_rows()`**

Implement:

```python
def latest_current_rows(
    self,
    *,
    window: str,
    scope: str,
    limit: int,
    projection_version: str,
) -> list[dict[str, Any]]:
    rows = self.conn.execute(
        """
        WITH ranked AS (
          SELECT
            token_radar_current_rows.*,
            row_number() OVER (PARTITION BY lane ORDER BY rank ASC) AS lane_rank
          FROM token_radar_current_rows
          WHERE projection_version = %s
            AND "window" = %s
            AND scope = %s
        )
        SELECT *
        FROM ranked
        WHERE lane_rank <= %s
        ORDER BY lane DESC, rank ASC
        LIMIT %s
        """,
        (
            projection_version,
            window,
            scope,
            max(0, int(limit)),
            max(0, int(limit)) * 2,
        ),
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 4.2: Remove `latest_rows()` compatibility**

Delete the legacy `latest_rows()` method body that reads `token_radar_rows`. Do not keep fallback or compatibility code. Callers must use one of these explicit methods:

```python
latest_current_rows(...)
latest_rank_history(...)
latest_snapshot_audit_rows(...)
```

If a caller has no new-table equivalent yet, make that caller fail loudly in tests rather than silently reading legacy data.

- [ ] **Step 4.3: Update `AssetFlowService` explicitly**

Change:

```python
rows = self.token_radar.latest_rows(...)
```

to:

```python
rows = self.token_radar.latest_current_rows(
    window=window,
    scope=scope,
    limit=row_limit,
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
)
```

- [ ] **Step 4.4: Update factor diagnostics CLI test**

Change `test_cli_ops_factor_diagnostics_reads_latest_token_radar_rows` so the fake repository implements `latest_current_rows()` and the assertion expects that method to be called.

- [ ] **Step 4.5: Run read path tests**

Run:

```bash
uv run pytest tests/integration/test_cli.py -k "factor_diagnostics or asset_flow" -q
uv run pytest tests/unit -k "token_radar or asset_flow" -q
```

Expected:

```text
All selected tests pass.
```

## Task 5: Remove All Runtime References To Legacy `token_radar_rows`

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_profile_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_image_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`
- Modify: `src/gmgn_twitter_intel/platform/db/postgres_audit.py`
- Test: affected unit/integration tests

- [ ] **Step 5.1: Convert current consumers**

Replace current-list joins against `token_radar_rows` with `token_radar_current_rows`. Current consumers include:

```text
src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py
src/gmgn_twitter_intel/domains/asset_market/queries/token_profile_source_query.py
src/gmgn_twitter_intel/domains/asset_market/queries/token_image_source_query.py
src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py
src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py
src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py
src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py
```

Use `token_radar_current_rows` for latest/current behavior.

- [ ] **Step 5.2: Convert historical consumers**

Replace historical factor evaluation reads with `token_radar_snapshot_audit`:

```text
src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py
src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py
```

Historical queries that need full `factor_snapshot_json` must read from `token_radar_snapshot_audit`. Queries that need only rank/decision/target metadata should read from `token_radar_rank_history`.

- [ ] **Step 5.3: Convert audits**

Replace `token_radar_rows` checks in `src/gmgn_twitter_intel/platform/db/postgres_audit.py` with checks for:

```text
token_radar_current_rows
token_radar_rank_history
token_radar_snapshot_audit
```

Do not keep an audit requirement that legacy `token_radar_rows` exists.

- [ ] **Step 5.4: Remove legacy repository methods**

Delete or rename methods whose only purpose is legacy table access:

```text
replace_rows()
latest_rows()
plan_prunable_rows()
delete_prunable_rows_batch()
protected_batch_counts()
insert_retention_run()
finish_retention_run()
```

Keep first-seen helpers only if they read `token_radar_target_first_seen` or new current/history/audit tables.

- [ ] **Step 5.5: Prove runtime code no longer references legacy table**

Run:

```bash
rg -n "token_radar_rows|latest_rows\\(|replace_rows\\(|prune-token-radar|backfill-token-radar-current" src/gmgn_twitter_intel
```

Expected:

```text
Only historical Alembic migration files and the explicit clean-reset command mention token_radar_rows. No runtime module uses latest_rows(), replace_rows(), prune-token-radar, or backfill-token-radar-current.
```

- [ ] **Step 5.6: Run focused tests**

Run:

```bash
uv run pytest tests/unit tests/integration -k "token_radar or factor_diagnostics or pulse_candidate or narrative or token_profile or token_image" -q
```

Expected:

```text
All selected tests pass.
```

## Task 6: Add New Storage Report And Partition Maintenance Commands

**Files:**

- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_storage_maintenance.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 6.1: Add storage report command**

Parser:

```python
ops_subcommands.add_parser(
    "token-radar-storage-report",
    help="print Token Radar current/history/audit storage and partition status",
)
```

Handler:

```python
if args.ops_command == "token-radar-storage-report":
    data = TokenRadarStorageMaintenanceService(token_radar=repos.token_radar).storage_report()
    return 0, {"ok": True, "data": data}
```

Service method:

```python
def storage_report(self) -> dict[str, Any]:
    rows = self.conn.execute(
        """
        SELECT
          relname,
          pg_total_relation_size(relid) AS total_bytes,
          pg_relation_size(relid) AS heap_bytes,
          pg_indexes_size(relid) AS index_bytes,
          n_live_tup,
          n_dead_tup,
          last_vacuum,
          last_autovacuum,
          last_analyze,
          last_autoanalyze
        FROM pg_stat_user_tables
        WHERE relname IN (
          'token_radar_current_rows',
          'token_radar_rank_history',
          'token_radar_snapshot_audit'
        )
        ORDER BY relname
        """
    ).fetchall()
    return {"tables": [dict(row) for row in rows]}
```

- [ ] **Step 6.2: Add partition prune command**

Parser:

```python
prune_storage = ops_subcommands.add_parser(
    "prune-token-radar-storage",
    help="drop old Token Radar history/audit partitions",
)
prune_storage.add_argument("--history-retention-days", type=int, default=30)
prune_storage.add_argument("--snapshot-retention-days", type=int, default=7)
prune_storage.add_argument("--dry-run", action="store_true")
prune_storage.add_argument("--execute", action="store_true")
```

Handler:

```python
if args.ops_command == "prune-token-radar-storage":
    if bool(args.dry_run) == bool(args.execute):
        return 2, {"ok": False, "error": "choose exactly one of --dry-run or --execute"}
    data = TokenRadarStorageMaintenanceService(token_radar=repos.token_radar).prune_storage(
        history_retention_days=args.history_retention_days,
        snapshot_retention_days=args.snapshot_retention_days,
        dry_run=bool(args.dry_run),
        execute=bool(args.execute),
    )
    return 0, {"ok": True, "data": data}
```

- [ ] **Step 6.3: Implement partition drop planner**

Add:

```python
def prune_storage(
    self,
    *,
    history_retention_days: int,
    snapshot_retention_days: int,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute is required")
    now_ms = int(time.time() * 1000)
    planned_partitions = self._old_partitions(
        table_retention_days={
            "token_radar_rank_history": int(history_retention_days),
            "token_radar_snapshot_audit": int(snapshot_retention_days),
        },
        now_ms=now_ms,
    )
    run_id = f"token-radar-storage:{uuid.uuid4().hex}"
    self.token_radar.insert_storage_maintenance_run(
        {
            "run_id": run_id,
            "mode": "execute" if execute else "dry_run",
            "operation": "prune-token-radar-storage",
            "status": "running" if execute else "dry_run",
            "dry_run": bool(dry_run),
            "details_json": {"planned_partitions": planned_partitions},
            "rows_planned": len(planned_partitions),
            "rows_changed": 0,
            "bytes_before": None,
            "bytes_after": None,
            "started_at_ms": now_ms,
            "finished_at_ms": now_ms if dry_run else None,
            "error": None,
            "created_at_ms": now_ms,
        }
    )
    dropped = []
    if execute:
        for item in planned_partitions:
            name = item["partition_name"]
            if not _PARTITION_RE.fullmatch(name):
                raise ValueError(f"invalid_partition_name:{name}")
            self.conn.execute(f"DROP TABLE IF EXISTS {name}")
            dropped.append(name)
        self.conn.commit()
    return {"run_id": run_id, "planned_partitions": planned_partitions, "dropped_partitions": dropped}
```

- [ ] **Step 6.4: Keep clean reset separate**

Do not include legacy `DROP TABLE` in `prune-token-radar-storage`. Clean reset is Task 8 and requires an explicit maintenance-window command.

- [ ] **Step 6.5: Run CLI tests**

Run:

```bash
uv run pytest tests/integration/test_cli.py -k "token_radar_storage" -q
```

Expected:

```text
All selected tests pass.
```

## Task 7: Clean-Slate Cutover And Verify New Data Ingestion

**Files:**

- Modify: `docs/RELIABILITY.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 7.1: Confirm runtime config paths**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected:

```text
config_path and workers_config_path point at ~/.gmgn-twitter-intel/
```

Do not print secrets.

- [ ] **Step 7.2: Apply migrations**

Run:

```bash
docker compose exec app gmgn-twitter-intel db migrate
```

Expected:

```text
Migration exits 0.
```

- [ ] **Step 7.3: Create upcoming partitions**

Run:

```bash
docker compose exec app gmgn-twitter-intel ops prune-token-radar-storage --dry-run
```

Expected:

```text
Command returns ok=true and does not drop partitions.
```

Run the partition ensure path once from a small Python wrapper or add a CLI subcommand `ensure-token-radar-partitions` in Task 6 before rollout.

- [ ] **Step 7.4: Execute clean reset of old Token Radar derived state**

Stop the app so no old worker writes race with cleanup:

```bash
docker compose stop app
```

Run dry-run:

```bash
docker compose run --rm app gmgn-twitter-intel ops clean-reset-token-radar-storage --dry-run
```

Expected:

```text
Reports that legacy token_radar_rows, retention runs, first-seen rows, coverage rows, projection runs, and projection offsets will be removed.
```

Run execute:

```bash
docker compose run --rm app gmgn-twitter-intel ops clean-reset-token-radar-storage \
  --confirm-delete-legacy-token-radar \
  --execute
```

Expected:

```text
Command exits 0. Old Token Radar derived storage is gone or empty. Material fact tables are untouched.
```

Restart the app:

```bash
docker compose up -d app
```

- [ ] **Step 7.5: Rebuild Token Radar once into new tables**

Run:

```bash
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 100
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all --limit 100
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 4h --scope all --limit 100
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 24h --scope all --limit 100
```

Expected:

```text
Each command exits 0 and writes current/history/audit rows into the new tables.
```

- [ ] **Step 7.6: Verify fact ingestion still works**

Run before and after the cutover:

```bash
docker compose exec postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT 'events' AS table_name, count(*) AS rows, max(received_at_ms) AS max_ms FROM events
UNION ALL
SELECT 'token_intents', count(*), max(updated_at_ms) FROM token_intents
UNION ALL
SELECT 'token_intent_resolutions', count(*), max(decision_time_ms) FROM token_intent_resolutions
UNION ALL
SELECT 'market_ticks', count(*), max(observed_at_ms) FROM market_ticks
UNION ALL
SELECT 'enriched_events', count(*), max(created_at_ms) FROM enriched_events;"
```

Expected:

```text
Counts are non-zero where the pipeline is enabled, and max_ms advances after the service runs.
```

- [ ] **Step 7.7: Verify new Token Radar writes**

Run:

```bash
docker compose exec postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT 'token_radar_current_rows' AS table_name, count(*) AS rows, max(computed_at_ms) AS max_ms FROM token_radar_current_rows
UNION ALL
SELECT 'token_radar_rank_history', count(*), max(computed_at_ms) FROM token_radar_rank_history
UNION ALL
SELECT 'token_radar_snapshot_audit', count(*), max(computed_at_ms) FROM token_radar_snapshot_audit;"
```

Expected:

```text
`token_radar_current_rows` has rows for active windows/scopes. History and audit tables have rows if their partitions exist and projection cycles completed.
```

- [ ] **Step 7.8: Optional business read smoke test**

Run:

```bash
curl -s http://localhost:8765/api/bootstrap >/tmp/gmgn-bootstrap.json
python - <<'PY'
import json, urllib.request
boot = json.load(open('/tmp/gmgn-bootstrap.json'))
token = boot['data']['ws_token']
req = urllib.request.Request(
    'http://localhost:8765/api/token-radar?window=5m&scope=all',
    headers={'Authorization': f'Bearer {token}'},
)
body = json.loads(urllib.request.urlopen(req, timeout=5).read())
print(body['ok'], len(body['data']['targets']), len(body['data']['attention']))
PY
```

Expected:

```text
The endpoint may pass, read empty, or temporarily fail during clean-slate cutover. Do not block cleanup on this check if fact ingestion and new Token Radar writes are healthy.
```

- [ ] **Step 7.9: Update docs**

In `docs/RELIABILITY.md`, replace the current Token Radar maintenance section with:

```markdown
Token Radar storage is split by purpose. Current API reads use
`token_radar_current_rows`; historical rank tracking uses partitioned
`token_radar_rank_history`; full replay snapshots use partitioned
`token_radar_snapshot_audit`. The legacy `token_radar_rows` table is removed
as part of the clean-slate hard reset and must not be used by runtime code.
```

In `docs/CONTRACTS.md`, update the Token Radar operational commands list with:

```markdown
- `gmgn-twitter-intel ops token-radar-storage-report` reports current,
  history, and audit Token Radar storage health.
- `gmgn-twitter-intel ops prune-token-radar-storage` drops old history
  and audit partitions using dry-run/execute safety.
- `gmgn-twitter-intel ops clean-reset-token-radar-storage` deletes old
  Token Radar derived state so the new read models start from empty tables.
```

In `docs/TECH_DEBT.md`, do not leave a compatibility follow-up for `token_radar_rows`. Runtime code must have no legacy references in this plan.

## Task 8: Clean-Reset Existing Token Radar Derived Storage

**Files:**

- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_storage_maintenance.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 8.1: Add explicit clean-reset command**

Parser:

```python
clean_reset = ops_subcommands.add_parser(
    "clean-reset-token-radar-storage",
    help="delete legacy Token Radar derived storage and reset new Token Radar read models",
)
clean_reset.add_argument("--confirm-delete-legacy-token-radar", action="store_true")
clean_reset.add_argument("--dry-run", action="store_true")
clean_reset.add_argument("--execute", action="store_true")
```

- [ ] **Step 8.2: Implement reset planner**

The command must default to dry-run. It must not inspect business consumer readiness. It must only protect material facts by planning destructive work against Token Radar derived tables.

```python
def clean_reset_plan(self) -> dict[str, Any]:
    relation_rows = self.conn.execute(
        """
        SELECT
          c.relname,
          pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname IN (
            'token_radar_rows',
            'token_radar_retention_runs',
            'token_radar_current_rows',
            'token_radar_rank_history',
            'token_radar_snapshot_audit',
            'token_radar_target_first_seen'
          )
        ORDER BY c.relname
        """
    ).fetchall()
    return {
        "relations": [dict(row) for row in relation_rows],
        "will_drop": ["token_radar_rows", "token_radar_retention_runs"],
        "will_truncate": [
            "token_radar_current_rows",
            "token_radar_rank_history",
            "token_radar_snapshot_audit",
            "token_radar_target_first_seen",
        ],
        "will_delete": [
            "token_radar_projection_coverage rows for Token Radar",
            "projection_runs rows for token-radar",
            "projection_offsets rows for token-radar",
        ],
    }
```

- [ ] **Step 8.3: Implement dry-run**

Dry-run returns:

```json
{
  "operation": "clean-reset-token-radar-storage",
  "will_drop": ["token_radar_rows", "token_radar_retention_runs"],
  "will_truncate": ["token_radar_current_rows", "token_radar_rank_history", "token_radar_snapshot_audit", "token_radar_target_first_seen"],
  "requires_execute": true
}
```

- [ ] **Step 8.4: Implement execute with maintenance-window warning**

When `--execute --confirm-delete-legacy-token-radar` is set, run in one maintenance transaction where supported:

```sql
DROP TABLE IF EXISTS token_radar_rows CASCADE;
DROP TABLE IF EXISTS token_radar_retention_runs;
TRUNCATE TABLE token_radar_current_rows;
TRUNCATE TABLE token_radar_rank_history;
TRUNCATE TABLE token_radar_snapshot_audit;
TRUNCATE TABLE token_radar_target_first_seen;
DELETE FROM token_radar_projection_coverage
WHERE projection_version LIKE 'token-radar-%';
DELETE FROM projection_runs
WHERE projection_name = 'token-radar';
DELETE FROM projection_offsets
WHERE projection_name = 'token-radar';
VACUUM (ANALYZE) token_radar_current_rows;
VACUUM (ANALYZE) token_radar_rank_history;
VACUUM (ANALYZE) token_radar_snapshot_audit;
```

Do not delete `events`, `token_intents`, `token_intent_resolutions`, `market_ticks`, `enriched_events`, or identity fact tables.

- [ ] **Step 8.5: Prove no runtime legacy references remain**

Run:

```bash
rg -n "token_radar_rows|latest_rows\\(|replace_rows\\(|prune-token-radar|backfill-token-radar-current|cleanup-legacy-token-radar-rows" src/gmgn_twitter_intel
```

Expected:

```text
Only historical Alembic migration files and the clean-reset command mention token_radar_rows. No runtime read/write path references the legacy table.
```

- [ ] **Step 8.6: Run clean reset in local Docker maintenance window**

Stop app worker writes:

```bash
docker compose stop app
```

Start a one-off app command for cleanup:

```bash
docker compose run --rm app gmgn-twitter-intel ops clean-reset-token-radar-storage \
  --confirm-delete-legacy-token-radar \
  --execute
```

Restart:

```bash
docker compose up -d app
```

Expected:

```text
Command exits 0, app restarts, fact ingestion continues, and new Token Radar tables receive rows from fresh projection cycles. Old Token Radar derived history is intentionally gone.
```

- [ ] **Step 8.7: Verify disk is reclaimed**

Run:

```bash
docker compose exec postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       n_live_tup
FROM pg_stat_user_tables
WHERE relname LIKE 'token_radar%'
ORDER BY pg_total_relation_size(relid) DESC;"
```

Expected:

```text
token_radar_rows is absent. New Token Radar tables are small or empty until fresh projection cycles write them.
```

## Task 9: Add Worker-Level Partition Ensuring

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_storage_maintenance.py`
- Test: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 9.1: Ensure partitions before writes**

Before each projection rebuild writes history/audit rows, call:

```python
TokenRadarStorageMaintenanceService(token_radar=self.repos.token_radar).ensure_daily_partitions(
    now_ms=computed_at_ms,
    days_ahead=2,
)
```

Keep this call outside long transactions when possible. If called inside projection, make it idempotent and fast.

- [ ] **Step 9.2: Add test that missing partitions are created**

Use fake maintenance service or fake repository to verify `ensure_daily_partitions()` is called before `append_rank_history()` and `append_snapshot_audit()`.

- [ ] **Step 9.3: Run worker tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_storage_maintenance.py -q
```

Expected:

```text
All selected tests pass.
```

## Task 10: Verification And Rollback

**Files:**

- Create: `docs/superpowers/plans/active/2026-05-23-token-radar-storage-root-fix-cleanup-verification-cn.md`

- [ ] **Step 10.1: Run targeted backend tests**

Run:

```bash
uv run pytest \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_token_radar_storage_maintenance.py \
  tests/integration/test_postgres_schema_runtime.py \
  tests/integration/test_cli.py \
  -k "token_radar or factor_diagnostics or asset_flow" \
  -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 10.2: Run full gate**

Run:

```bash
make check-all
```

Expected:

```text
Command exits 0.
```

- [ ] **Step 10.3: Capture storage before/after**

Run:

```bash
docker compose exec postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       n_live_tup,
       n_dead_tup,
       last_vacuum,
       last_autovacuum
FROM pg_stat_user_tables
WHERE relname LIKE 'token_radar%'
ORDER BY pg_total_relation_size(relid) DESC;"
```

Expected:

```text
token_radar_current_rows is small; legacy token_radar_rows is empty or absent after cleanup.
```

- [ ] **Step 10.4: Verify API latency**

Measure:

```bash
python - <<'PY'
import json
import time
import urllib.request

base = "http://localhost:8765"
boot = json.loads(urllib.request.urlopen(base + "/api/bootstrap", timeout=5).read())
token = boot["data"]["ws_token"]
for path in [
    "/api/token-radar?window=5m&scope=all",
    "/api/token-radar?window=1h&scope=all",
]:
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        urllib.request.urlopen(req, timeout=10).read()
        timings.append(round((time.perf_counter() - started) * 1000))
    print(path, timings)
PY
```

Expected:

```text
Most local requests are comfortably below 250ms under normal worker load.
```

- [ ] **Step 10.5: Rollback plan**

Rollback before clean reset executes:

```text
Revert the code branch and leave old token_radar_rows intact.
```

Rollback after clean reset executes:

```text
Do not attempt logical rollback from old token_radar_rows. Rebuild current rows from facts using ops rebuild-token-radar for each window/scope. Full historical snapshots before cleanup are intentionally discarded unless an operator has taken a database backup.
```

## Execution Order

1. Implement Tasks 1-4 in a dedicated worktree.
2. Run targeted tests.
3. Implement Tasks 5-6.
4. Run local migration against Docker.
5. Verify fact ingestion and new Token Radar writes.
6. Implement Task 8 cleanup command.
7. Execute clean reset in a maintenance window; delete old Token Radar derived storage.
8. Record verification.

## Residual Risks

- `DROP TABLE token_radar_rows CASCADE` is intentional in this clean-slate plan. It is only allowed after Task 5 proves no runtime code references the table.
- `VACUUM FULL` should not be needed after dropping legacy storage. Use it only for unrelated remaining bloat during a separate maintenance window.
- Current rows still contain JSONB snapshots, but bounded cardinality keeps TOAST small.
- Audit snapshots still contain JSONB, but partition TTL and sampling prevent unlimited growth.
- Token Radar, Pulse, Narrative, Profile, Image, and diagnostics surfaces must not depend on legacy `token_radar_rows` after this plan. They may still show empty data until fresh post-reset projection cycles populate the new tables.
- Existing worktree conflict files must be resolved or isolated in a dedicated worktree before code implementation.

## Self-Review

- Spec coverage: the plan covers data-model split, current read migration, bounded partitioned history, snapshot audit retention, old data cleanup, docs, tests, and rollback.
- Placeholder scan: no task relies on deferred implementation language or unspecified commands.
- Type consistency: table names, service names, and repository method names are stable across tasks.
