# Token Radar PostgreSQL Hard Cut Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性根治 Token Radar / Token Case 运行态卡顿、派生表膨胀、token image 终态重试、wake listener 连接池不足，以及 `market_ticks` 长期增长风险。

**Architecture:** 采用生产 PostgreSQL 的 CQRS/Kappa 写法：事实表按时间分区、热读只读小 current 表、后台投影改成 dirty-target incremental，rank/history/audit 分离且只按变化写入。此次是 clean-reset hard cut：不迁移旧派生数据，不保留旧 runtime fallback，不用兼容旧 `token_radar_rows` 或旧全量窗口扫描路径。

**Tech Stack:** Python 3.13, FastAPI, psycopg 3, PostgreSQL 18, Alembic, pytest, ruff, Docker Compose.

---

## Non-Negotiable Decisions

- 本计划一次性落地，不拆成两期。
- 允许删除所有 rebuildable read models 和旧派生数据；facts 只保留新的事实语义。
- 不保留 `token_radar_rows`、旧 `replace_rows`、旧 full-window source query fallback、旧 retention-by-DELETE CLI。
- Token Case / Token Radar API 只读 current/read-model 表，不在请求路径调用 provider。
- 大表增长靠 PostgreSQL 分区 drop / compact current upsert / sampled audit 控制，不靠事后小批量 DELETE。
- `NOTIFY` 仍然只是 wake hint；worker 必须能靠 DB dirty queue catch up。

## Production PostgreSQL Rules Applied

- **Partition high-ingest facts by time.** `market_ticks` 按 `observed_at_ms` RANGE 分区，唯一约束包含分区键。
- **Avoid global uniqueness assumptions on partitioned tables.** `market_ticks` 主键改为 `(observed_at_ms, tick_id)`；引用方保存 `tick_observed_at_ms`。
- **Use small current tables for user reads.** 页面读取 `market_tick_current`, `token_radar_current_rows`, `token_profile_current`。
- **Use upsert-with-hash for hot read models.** current rows 用稳定 key 和 `payload_hash`，只有内容变化才 UPDATE。
- **Keep large JSON out of hot paths.** 完整 factor snapshot 只进 sampled/on-change audit，不在每轮 projection 全量写。
- **Drop partitions for retention.** history/audit/market tick 过期清理由 drop partition 完成。
- **Tune churn tables explicitly.** current/queue 表设置 lower fillfactor 和 aggressive autovacuum reloptions。
- **Design indexes from access paths.** API/current 使用 btree；时间 retention 使用 partition boundary；宽 JSON 不建默认 GIN。

## Current Root Cause Snapshot

- `TokenRadarSourceQuery.source_rows()` 使用 `WITH source_intents AS MATERIALIZED` 扫窗口事实，并对每行做 `market_ticks` latest/first lateral lookup。
- `TokenRadarRepository.publish_rows()` 当前对 current rows 是 delete+insert，对 rank/history/audit 每轮完整写入，导致 TOAST 和 dead tuples 快速增长。
- clean-reset 后数据不大，但运行态已出现 `token_radar_snapshot_audit_202605 ~352MB`, `token_radar_rank_history_202605 ~70MB`, `token_radar_current_rows ~32MB`。
- `token_image_assets` 已有 `unsupported` 状态，但 source query 仍会重复选出 ready/unsupported source，造成无意义 upsert churn。
- `wake_pool` 已改成动态大小，但缺少架构测试保证所有 `wakes_on` worker 容量被覆盖。

---

## Target Data Model

### Facts

- `market_ticks`
  - partitioned by `observed_at_ms`.
  - primary key `(observed_at_ms, tick_id)`.
  - unique dedupe `(observed_at_ms, target_type, target_id, source_provider)`.
  - local index `(target_type, target_id, observed_at_ms DESC, tick_id DESC)` on each partition.

- `enriched_events`
  - stores `tick_observed_at_ms` plus `tick_id`.
  - composite FK `(tick_observed_at_ms, tick_id)` to `market_ticks`.

### Hot Read Models

- `market_tick_current`
  - one row per `(target_type, target_id)`.
  - written only by `MarketTickRepository` when ticks are inserted.
  - Token Case and live gateway read this table directly for latest-market state; missing current rows return explicit `missing`.

- `token_radar_target_features`
  - one row per `(projection_version, window, scope, lane, target_type_key, identity_id)`.
  - stores compact factor feature columns, `factor_snapshot_json`, source ids, `payload_hash`, and `last_scored_at_ms`.
  - updated only for dirty targets.

- `token_radar_current_rows`
  - one row per current ranked target key.
  - stable `row_id` derived from `(projection_version, window, scope, lane, target_type_key, identity_id)`.
  - no delete+insert per cycle; use `ON CONFLICT DO UPDATE ... WHERE payload_hash IS DISTINCT FROM excluded.payload_hash`.

### Control Plane

- `token_radar_dirty_targets`
  - one row per dirty `(target_type_key, identity_id)`.
  - producers: ingest/resolution refresh/market tick insert/profile updates.
  - worker claims with `FOR UPDATE SKIP LOCKED`.

- `token_radar_maintenance_runs`
  - records hard reset, partition creation, partition drop, analyze/vacuum diagnostics.

### Bounded History/Audit

- `token_radar_rank_history`
  - stores rank changes only.
  - no full factor snapshot JSON.
  - partitioned by `recorded_at_ms`.

- `token_radar_snapshot_audit`
  - stores full snapshot only for `rank_enter`, `rank_exit`, `decision_change`, `manual_sample`, `debug_error`.
  - partitioned by `recorded_at_ms`.
  - no per-cycle full snapshot writes.

---

## File Structure

### Schema And DB Contracts

- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py`
  - Drops/recreates Token Radar derived tables.
  - Recreates `market_ticks` and `enriched_events` with partition-safe keys.
  - Creates `market_tick_current`.
  - Creates current/history/audit/dirty queue indexes and reloptions.

- Modify: `tests/unit/test_postgres_schema.py`
  - Assert revision chain includes `20260523_0090`.
  - Assert no legacy `token_radar_rows` table is created.
  - Assert partitioned tables and composite FK SQL are present.

- Modify: `tests/integration/test_postgres_schema_runtime.py`
  - Assert runtime schema has partitioned `market_ticks`, `token_radar_rank_history`, and `token_radar_snapshot_audit`.
  - Assert `market_ticks` update remains rejected.
  - Assert `market_tick_current` exists and has the expected primary key.

### Market Tick Write/Read Path

- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
  - Insert into partitioned `market_ticks`.
  - Upsert `market_tick_current` in the same transaction.
  - Return `(observed_at_ms, tick_id)` for enriched-event references.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/enriched_event_repository.py`
  - Join market ticks by `(tick_observed_at_ms, tick_id)`.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
  - Store `tick_observed_at_ms` when attaching anchor ticks.

- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
  - Persist enriched event tick references using the composite key.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_target_repository.py`
  - Read latest market from `market_tick_current` for Token Case.

- Modify tests:
  - `tests/unit/test_market_tick_repository.py`
  - `tests/unit/test_enriched_event_repository.py`
  - `tests/unit/test_token_target_posts_service.py`
  - `tests/integration/test_ingest_enriched_events.py`

### Token Radar Incremental Projection

- Create: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
  - `enqueue_targets(rows, reason, now_ms)`
  - `claim_due(limit, lease_ms, now_ms)`
  - `mark_done(keys, now_ms)`
  - `mark_error(keys, error, retry_ms, now_ms)`

- Create: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`
  - Replaces full-window `TokenRadarSourceQuery` runtime use.
  - Reads rows for one target across one window/scope.
  - Uses indexed `token_intent_resolutions(target_type, target_id, is_current, resolver_policy_version)` and `events(received_at_ms)`.
  - Reads latest market from `market_tick_current`.
  - Reads event-time market from `enriched_events` composite tick reference.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
  - Replace full rebuild API with target-window scoring:
    - `rebuild_dirty_targets(now_ms, limit)`
    - `score_target_window(target, window, scope, now_ms)`
    - `refresh_rank_set(window, scope, now_ms)`
  - Build factor snapshots only for dirty targets.
  - Recompute cross-section rank from `token_radar_target_features`, not from raw facts.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
  - Replace `publish_rows()` with:
    - `upsert_target_features(...)`
    - `publish_rank_set(...)`
    - `insert_rank_changes(...)`
    - `insert_snapshot_audit_events(...)`
  - Remove per-cycle insert into snapshot audit.
  - Remove current table delete+insert.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
  - Claim dirty targets first.
  - If no dirty targets, run bounded stale-scan that only enqueues candidates, not full projection.
  - Hot wake events coalesce into dirty queue rows.

- Remove runtime dependency:
  - `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`
  - Delete the file or move any remaining historical SQL assertion into tests; runtime and service code must have no import path to it.

- Modify tests:
  - `tests/unit/test_token_radar_projection.py`
  - `tests/unit/test_token_radar_projection_worker.py`
  - `tests/unit/test_token_radar_repository.py`
  - `tests/integration/test_token_radar_repository.py`
  - `tests/integration/test_token_radar_idempotency.py`
  - `tests/integration/test_worker_missed_wake_recovery.py`

### Dirty Target Producers

- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
  - Enqueue dirty target after a token intent/resolution is written.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py`
  - Enqueue dirty targets for affected lookup keys after successful reprocess.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
  - When `market_tick_current` changes materially, enqueue the linked Token Radar identity.

- Modify: `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
  - Wire dirty target repository into runtime repository session.

- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
  - Add `token_radar_dirty_targets`.

### Token Image Churn Fix

- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_image_source_query.py`
  - Left join `token_image_assets` by source hash.
  - Exclude `ready` and `unsupported`.
  - Keep only missing/pending/error candidates.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/token_image_asset_repository.py`
  - Keep `unsupported` terminal.
  - Ensure `upsert_pending_sources()` does not update terminal `ready` or `unsupported` rows.

- Modify tests:
  - `tests/unit/test_token_image_mirror.py`
  - `tests/unit/test_token_image_mirror_worker.py`
  - `tests/integration/test_token_image_asset_repository.py`

### Wake Pool And Worker Budget Guardrails

- Modify: `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
  - Keep dynamic wake pool sizing.
  - Add telemetry field for computed wake pool slots.

- Modify: `tests/unit/test_db_pool_bundle.py`
  - Assert `wake_pool.max_size >= enabled_wake_listener_concurrency + 2`.

- Modify: `tests/architecture/test_worker_runtime_contracts.py`
  - Assert all `wakes_on` worker settings are covered by wake pool sizing logic.
  - Assert no worker directly imports the deleted full-window Token Radar source query.

### Ops Hard Reset And Maintenance

- Create: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_postgres_hard_reset.py`
  - Drops all derived Token Radar tables.
  - Truncates dirty queue/current/history/audit/features.
  - Recreates current month and next month partitions.
  - Does not touch provider secrets or config files.

- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
  - Replace old `prune-token-radar` / old storage reset with:
    - `ops reset-token-radar-postgres-hard-cut --dry-run`
    - `ops reset-token-radar-postgres-hard-cut --execute`
    - `ops ensure-postgres-partitions --execute`
    - `ops drop-expired-postgres-partitions --execute`

- Modify tests:
  - `tests/unit/domains/token_intel/test_token_radar_storage_reset.py`
  - `tests/integration/test_cli.py`

### Documentation

- Modify: `docs/ARCHITECTURE.md`
  - Token Radar projection is dirty-target incremental, not full-window rebuild.

- Modify: `docs/RELIABILITY.md`
  - Add partition retention and hard-reset runbook.

- Modify: `docs/WORKERS.md`
  - Update worker inventory: Token Radar worker consumes dirty queue and writes feature/current/history/audit read models.

- Modify: `docs/TECH_DEBT.md`
  - Close the old Token Radar storage bloat debt.

---

## Implementation Tasks

### Task 1: Schema Hard Cut Migration

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1: Add failing schema tests**

Add unit assertions for:

```python
def test_token_radar_postgres_hard_cut_migration_partitions_hot_tables() -> None:
    text = _migration_text("20260523_0090_token_radar_postgres_hard_cut.py")
    assert "DROP TABLE IF EXISTS token_radar_rows CASCADE" in text
    assert "CREATE TABLE IF NOT EXISTS market_ticks" in text
    assert "PARTITION BY RANGE (observed_at_ms)" in text
    assert "PRIMARY KEY (observed_at_ms, tick_id)" in text
    assert "CREATE TABLE IF NOT EXISTS market_tick_current" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_dirty_targets" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_target_features" in text
    assert "payload_hash TEXT NOT NULL" in text
    assert "PARTITION BY RANGE (recorded_at_ms)" in text
```

- [ ] **Step 2: Run failing schema tests**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_token_radar_postgres_hard_cut_migration_partitions_hot_tables -q
```

Expected: fail because migration does not exist yet.

- [ ] **Step 3: Create migration**

Create revision `20260523_0090` with `down_revision = "20260523_0089"`. Migration must:

- Drop old derived Token Radar storage.
- Drop and recreate `market_ticks`, `enriched_events`, and dependent read models because this is a clean-reset hard cut.
- Create default and current-month partitions for partitioned tables.
- Set reloptions:

```sql
ALTER TABLE token_radar_current_rows SET (
  fillfactor = 80,
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.02
);
ALTER TABLE token_radar_dirty_targets SET (
  fillfactor = 80,
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.02
);
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected: pass.

### Task 2: Market Tick Current And Composite Tick References

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/enriched_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_target_repository.py`
- Modify: related unit/integration tests listed above.

- [ ] **Step 1: Add failing repository tests**

Add assertions that inserting a newer tick upserts `market_tick_current`, inserting an older tick does not replace current, and enriched-event reads join by `(tick_observed_at_ms, tick_id)`.

- [ ] **Step 2: Implement market current upsert**

Use SQL shape:

```sql
INSERT INTO market_tick_current(...)
VALUES (...)
ON CONFLICT(target_type, target_id) DO UPDATE SET ...
WHERE market_tick_current.observed_at_ms <= excluded.observed_at_ms
```

- [ ] **Step 3: Update Token Case latest market read**

`TokenTargetRepository.latest_market_tick()` should read `market_tick_current` first. It must not scan `market_ticks` for the normal latest-price path.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/unit/test_market_tick_repository.py tests/unit/test_enriched_event_repository.py tests/unit/test_token_target_posts_service.py tests/integration/test_ingest_enriched_events.py -q
```

Expected: pass.

### Task 3: Dirty Target Queue And Producers

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`

- [ ] **Step 1: Add failing dirty queue tests**

Test coalescing:

```python
def test_dirty_target_enqueue_coalesces_by_identity():
    repo.enqueue_targets([row], reason="event_written", now_ms=1000)
    repo.enqueue_targets([row], reason="market_tick_written", now_ms=2000)
    queued = repo.claim_due(limit=10, lease_ms=60000, now_ms=3000)
    assert len(queued) == 1
    assert queued[0]["dirty_reasons_json"] == ["event_written", "market_tick_written"]
```

- [ ] **Step 2: Implement repository**

Use `ON CONFLICT(projection_version, target_type_key, identity_id)` and merge reason arrays with a deterministic JSONB set expression.

- [ ] **Step 3: Wire producers**

Ingest/resolution refresh/market current updates enqueue dirty targets after facts commit. `NOTIFY` remains wake hint only.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/unit/test_market_tick_repository.py tests/unit/test_resolution_refresh_worker.py tests/integration/test_worker_missed_wake_recovery.py -q
```

Expected: pass.

### Task 4: Replace Full-Window Token Radar Projection

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Remove runtime use of: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`

- [ ] **Step 1: Add failing architecture test**

Assert no runtime/service module imports `TokenRadarSourceQuery`.

- [ ] **Step 2: Add target feature query tests**

Assert generated SQL:

- filters one `target_type/target_id`.
- uses `events.received_at_ms >= %s`.
- reads latest market from `market_tick_current`.
- does not contain `WITH source_intents AS MATERIALIZED`.

- [ ] **Step 3: Implement target-window scoring**

`TokenRadarProjection` should score one dirty target across configured windows/scopes, write `token_radar_target_features`, then refresh affected rank sets from feature rows.

- [ ] **Step 4: Implement stable current-row publish**

`publish_rank_set()` must:

- upsert by stable target key.
- update only when `payload_hash` changes.
- mark disappeared rows inactive or delete them in one bounded statement for that window/scope.
- insert rank history only when rank or decision changed.
- insert snapshot audit only for audit reasons.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py tests/integration/test_token_radar_idempotency.py -q
```

Expected: pass.

### Task 5: Token Image Source Churn Hard Cut

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_image_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/token_image_asset_repository.py`
- Modify: token image tests.

- [ ] **Step 1: Add failing tests**

Assert ready and unsupported image source URLs are not selected again and `upsert_pending_sources()` does not mutate terminal rows.

- [ ] **Step 2: Implement SQL exclusion**

Candidate query should exclude:

```sql
WHERE existing_image.image_id IS NULL
   OR existing_image.status IN ('pending', 'error')
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/unit/test_token_image_mirror.py tests/unit/test_token_image_mirror_worker.py tests/integration/test_token_image_asset_repository.py -q
```

Expected: pass.

### Task 6: Ops Commands And No-Compatibility Cleanup

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_postgres_hard_reset.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `tests/integration/test_cli.py`
- Modify: `tests/unit/domains/token_intel/test_token_radar_storage_reset.py`

- [ ] **Step 1: Replace old ops surface**

Remove old prune/reset commands that imply compatibility with legacy storage. Add hard-cut commands only.

- [ ] **Step 2: Add dry-run output tests**

Dry-run must list affected derived tables and partitions, and explicitly say facts are preserved only when the command is not full schema reset.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/integration/test_cli.py tests/unit/domains/token_intel/test_token_radar_storage_reset.py -q
```

Expected: pass.

### Task 7: Runtime And Load Verification

**Files:**
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_okx_dex_ws_client.py tests/unit/test_market_tick_stream_worker.py tests/unit/test_market_tick_poll_worker.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_repository.py -q
```

Expected: pass.

- [ ] **Step 2: Run integration suite for changed storage**

Run:

```bash
uv run pytest tests/integration/test_postgres_schema_runtime.py tests/integration/test_ingest_enriched_events.py tests/integration/test_token_radar_repository.py tests/integration/test_token_radar_idempotency.py tests/integration/test_api_http.py -q
```

Expected: pass.

- [ ] **Step 3: Rebuild and clean-reset runtime**

Run:

```bash
docker compose build app
docker compose stop app
docker compose run --rm migrate
docker compose up -d app
```

For this hard cut, use the approved empty-DB path before migration:

```bash
docker compose stop app
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO gmgn_app;"
docker compose run --rm migrate
docker compose up -d app
```

- [ ] **Step 4: Runtime acceptance checks**

Run:

```bash
uv run gmgn-twitter-intel config
curl -sS http://localhost:8765/readyz
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -At -c "SELECT relname, n_live_tup, n_dead_tup, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_stat_user_tables WHERE relname IN ('market_ticks','market_tick_current','token_radar_current_rows','token_radar_target_features','token_radar_rank_history','token_radar_snapshot_audit','token_image_assets') ORDER BY relname"
```

Expected:

- `/readyz` returns `ok=true`.
- `market_tick_current` remains small.
- `token_radar_current_rows` has low dead tuples after repeated runs.
- snapshot audit grows only on change/sample events.
- no active query contains `WITH source_intents AS MATERIALIZED`.

---

## Acceptance Criteria

- Runtime source has no active import or call path to old full-window `TokenRadarSourceQuery`.
- `token_radar_rows` does not exist in fresh runtime schema.
- `market_ticks` is partitioned by time and latest market reads use `market_tick_current`.
- Token Radar current writes do not use per-cycle delete+insert.
- Rank history and snapshot audit do not write full rows every projection cycle.
- Token image worker does not keep touching ready/unsupported sources.
- Wake pool sizing is tested against configured `wakes_on` listeners.
- Token Case page remains fast while workers are running.
- PostgreSQL table sizes remain proportional to live current rows plus bounded partitions after 30 minutes of live sync.

## Rollback Boundary

Because this is a no-compatibility hard cut, rollback is operational, not in-code compatibility:

1. Stop app.
2. Restore database from pre-hard-cut backup, or drop schema and migrate previous main.
3. Deploy previous image.
4. Restart sync from provider facts if no backup is desired.

No runtime compatibility branch should be kept in the codebase.
