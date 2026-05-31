# Next Runtime Lifecycle Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 worker 审计中发现的 P0/P1/P2 生命周期问题做下一轮 hard cut：Macro current snapshot 不再按 run 增长，旧 164GB generation 数据和旧 snapshot 数据彻底删除，CEX/News/Agent/current-row churn 也补上 bounded lifecycle 和 no-compat guard。

**Architecture:** 所有 serving read model 必须是 stable-key current row 或明确有 retention 的 audit/control ledger；任何 latest-run/latest-timestamp serving pattern 都要删除或改成 bounded publication state。Macro 改成 dirty-target 驱动，未 claim 到 durable dirty target 时不扫 `macro_observations`，已 claim 后才重建 current rows/snapshot。迁移直接 drop retired physical data，不保留 runtime legacy reader、fallback path、兼容 table。

**Tech Stack:** Python 3.13, psycopg 3, PostgreSQL 18, Alembic, pytest, ruff, Docker Compose.

---

## Owning Input

- Audit summary: all-worker Kappa/CQRS audit on `main@2c5eee4f`.
- Worktree: `/Users/qinghuan/Documents/code/parallax/.worktrees/macro-sync-worker-hard-cut`
- Branch: `main`
- New migration revision: `20260527_0115`
- Previous head: `20260527_0114`

## Non-Negotiable Hard-Cut Rules

- No compatibility reader for old Macro active generation, old Macro snapshots, or CEX latest-run rows.
- No table rename-to-legacy for this round. Retired physical data is dropped in the migration.
- No serving read model primary key may include `generation_id`, `run_id`, `attempt_id`, timestamp-derived snapshot id, or UUID unless the table is explicitly classified as audit/control and has retention.
- Unchanged projection must be observable as zero serving-row writes.
- Provider no-start/backpressure must not consume business queue attempts.
- Control-plane queue/run state must not be exposed as product truth.

## Pre-Flight

- [ ] **Step 1: Confirm clean worktree**

  Run:

  ```bash
  git -C /Users/qinghuan/Documents/code/parallax/.worktrees/macro-sync-worker-hard-cut branch --show-current
  git -C /Users/qinghuan/Documents/code/parallax/.worktrees/macro-sync-worker-hard-cut status --short
  ```

  Expected:

  ```text
  main
  ```

  `status --short` should show only this plan before implementation.

- [ ] **Step 2: Confirm live config paths without secrets**

  Run:

  ```bash
  uv run parallax config
  ```

  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`.

- [ ] **Step 3: Record live baseline**

  Run:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT relname,
         pg_size_pretty(pg_total_relation_size(relid)) AS total,
         n_live_tup,
         n_tup_ins,
         n_tup_upd,
         n_tup_del
  FROM pg_stat_user_tables
  WHERE relname IN (
    'macro_view_snapshots',
    'macro_observation_series_rows',
    'macro_observation_series_rows_legacy_20260527_0114',
    'macro_projection_dirty_targets',
    'cex_oi_radar_runs',
    'cex_oi_radar_rows',
    'news_page_rows',
    'token_capture_tier',
    'token_profile_current',
    'news_source_quality_rows'
  )
  ORDER BY pg_total_relation_size(relid) DESC;"
  ```

  Expected before this plan: legacy Macro table may be present and large; after this plan it must be absent.

---

## File-Level Change Map

### Migrations

- Create `src/parallax/platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py`
  - Drop `macro_observation_series_rows_legacy_20260527_0114`.
  - Collapse `macro_view_snapshots` to one stable current row per `projection_version`.
  - Add `payload_hash` to `macro_view_snapshots`.
  - Create `macro_projection_dirty_targets`.
  - Seed one due `macro_projection_dirty_targets` row for `macro_view`.
  - Add history-order index on `macro_observation_series_rows(projection_version, concept_key, observed_at DESC, series_rank)`.
  - Drop superseded Macro lookup index if redundant.
  - Rebuild CEX OI board tables as current-only rows plus publication state; drop `cex_oi_radar_runs`.
  - Add `payload_hash` columns for page/source/profile rows where missing.

### Macro

- Modify `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
  - Stable snapshot id: `macro-view:{projection_version}:current`.
  - Do not encode `computed_at_ms` into row identity.

- Modify `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
  - Claim `macro_projection_dirty_targets` first.
  - If no claim, return `processed=0`, `rows_written=0`, and do not read `macro_observations`.
  - If series refresh is `unchanged`, mark dirty target done and skip `insert_snapshot`.
  - If changed, insert/update the single current snapshot row.

- Modify `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
  - Add dirty-target claim/mark/enqueue methods or a focused repository class if existing style prefers queue repositories.
  - Change `insert_snapshot` to stable current upsert with payload hash and `WHERE payload_hash IS DISTINCT FROM EXCLUDED.payload_hash`.
  - Change `latest_snapshot` to read by `projection_version` without latest-order scan.
  - Keep `refresh_observation_series_rows` current-only; do not reintroduce generation tables.

- Modify `src/parallax/domains/macro_intel/services/macro_sync_service.py`
  - Enqueue `macro_projection_dirty_targets` only when a sync/import writes or changes macro observations.

### CEX OI Radar

- Modify `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`
  - Remove `start_run`, `finish_run`, and `oi_radar_run_id`.
  - Replace with `publish_board(rows, computed_at_ms, status, notes)`.
  - `cex_oi_radar_rows.row_id` must be stable by provider/exchange/period/target_id, not by run id.
  - `latest_board` reads current rows and `cex_oi_radar_publication_state`.

- Modify `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py`
  - Do not generate run ids.
  - Publish current board in one transaction.
  - Preserve `cex_detail_snapshots` because its snapshot id is market-stable.

### News/Current-Row Churn

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`
  - `replace_page_rows_for_items` must delete only obsolete scoped rows.
  - Upsert page rows with payload hash and `WHERE payload_hash IS DISTINCT FROM EXCLUDED.payload_hash`.
  - `replace_source_quality_rows` must use payload hash and unchanged skip.

- Modify `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py`
  - Add `WHERE` gate to `ON CONFLICT` so identical tier/reason/score does not update `updated_at_ms`.

- Modify `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`
  - Add payload hash or explicit `IS DISTINCT FROM` gate; return `bool changed`.

### Agent/LLM Backpressure and Ledger

- Modify:
  - `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
  - `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - `src/parallax/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
  - related repositories under `domains/narrative_intel`, `domains/news_intel`, `domains/equity_event_intel`

  Required behavior:

  - Reserve agent capacity before durable queue claim.
  - If capacity/circuit/RPM rejects before provider start, do not increment business attempt.
  - If provider starts, every validation/publication failure writes a model-run ledger row with `execution_started=true`.

### Contracts and Docs

- Modify `src/parallax/app/runtime/worker_manifest.py`
  - Fix collector writes and live_price_gateway contract.
  - Classify notification delivery as side-effect/control ledger, not product fact.
  - Add lifecycle class for read models: `current`, `private_cache`, `control_ledger`, `audit_fact`.

- Modify `docs/ARCHITECTURE.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/references/POSTGRES_PERFORMANCE.md`.

- Modify both routers:
  - `AGENTS.md`
  - `CLAUDE.md`

  Add hard rule: current read models cannot use run/timestamp/generation identity and unchanged projections must write zero serving rows.

- Clean active docs:
  - Remove or supersede active-generation implementation text from active plans/specs that still instruct future agents to write `macro_observation_series_active_generation`.

---

## Task 1: Migration Hard Cleanup and Lifecycle Schema

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

- [ ] **Step 1: Write migration contract tests first**

  Add helpers if the target test file does not already have them:

  ```python
  def _migration_text(filename: str) -> str:
      path = ROOT / "src/parallax/platform/db/alembic/versions" / filename
      return path.read_text()


  def _create_table_block(text: str, table_name: str) -> str:
      marker = f"CREATE TABLE IF NOT EXISTS {table_name}"
      if marker not in text:
          marker = f"CREATE TABLE {table_name}"
      start = text.index(marker)
      end = text.find('"""', start)
      return text[start:end]
  ```

  Add assertions:

  ```python
  def test_0115_drops_retired_macro_generation_legacy_table() -> None:
      text = _migration_text("20260527_0115_next_runtime_lifecycle_hard_cut.py")
      assert "DROP TABLE IF EXISTS macro_observation_series_rows_legacy_20260527_0114" in text
      assert "RENAME TO macro_observation_series_rows_legacy" not in text


  def test_0115_rebuilds_macro_view_snapshots_as_current_rows() -> None:
      text = _migration_text("20260527_0115_next_runtime_lifecycle_hard_cut.py")
      assert "macro_view_snapshots_compact" in text
      assert "payload_hash TEXT NOT NULL" in text
      assert "macro-view:' || projection_version || ':current" in text
      assert "DROP TABLE macro_view_snapshots" in text
      assert "ORDER BY computed_at_ms DESC" in text


  def test_0115_removes_cex_latest_run_serving_tables() -> None:
      text = _migration_text("20260527_0115_next_runtime_lifecycle_hard_cut.py")
      assert "DROP TABLE IF EXISTS cex_oi_radar_runs" in text
      assert "cex_oi_radar_publication_state" in text
      assert "run_id" not in _create_table_block(text, "cex_oi_radar_rows")
  ```

- [ ] **Step 2: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    -q
  ```

  Expected: FAIL because the `0115` migration does not exist.

- [ ] **Step 3: Create migration**

  Migration SQL must include these constants:

  ```python
  revision = "20260527_0115"
  down_revision = "20260527_0114"

  _CREATE_MACRO_PROJECTION_DIRTY_TARGETS_SQL = """
  CREATE TABLE IF NOT EXISTS macro_projection_dirty_targets (
    projection_name TEXT NOT NULL,
    projection_version TEXT NOT NULL,
    target_kind TEXT NOT NULL DEFAULT 'macro_view',
    target_id TEXT NOT NULL DEFAULT 'macro_view',
    due_at_ms BIGINT NOT NULL,
    lease_owner TEXT,
    lease_expires_at_ms BIGINT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    PRIMARY KEY (projection_name, projection_version, target_kind, target_id)
  )
  """

  _CREATE_MACRO_VIEW_SNAPSHOTS_COMPACT_SQL = """
  CREATE TABLE macro_view_snapshots_compact (
    snapshot_id TEXT PRIMARY KEY,
    projection_version TEXT NOT NULL UNIQUE,
    asof_date DATE NOT NULL,
    status TEXT NOT NULL,
    regime TEXT NOT NULL,
    overall_score DOUBLE PRECISION,
    panels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    chain_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    scenario_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    scorecard_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash TEXT NOT NULL,
    computed_at_ms BIGINT NOT NULL
  )
  """
  ```

  Upgrade sequence:

  ```python
  op.execute("SET LOCAL lock_timeout = '5s'")
  op.execute("SET LOCAL statement_timeout = '30min'")
  op.execute("DROP TABLE IF EXISTS macro_observation_series_rows_legacy_20260527_0114")
  op.execute(_CREATE_MACRO_PROJECTION_DIRTY_TARGETS_SQL)
  op.execute(_CREATE_MACRO_VIEW_SNAPSHOTS_COMPACT_SQL)
  op.execute(_COPY_LATEST_MACRO_VIEW_SNAPSHOT_AS_CURRENT_SQL)
  op.execute("DROP TABLE macro_view_snapshots")
  op.execute("ALTER TABLE macro_view_snapshots_compact RENAME TO macro_view_snapshots")
  op.execute(_CREATE_CEX_PUBLICATION_STATE_SQL)
  op.execute("DROP TABLE IF EXISTS cex_oi_radar_rows")
  op.execute("DROP TABLE IF EXISTS cex_oi_radar_runs")
  op.execute(_CREATE_CEX_CURRENT_ROWS_SQL)
  op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS payload_hash TEXT")
  op.execute("ALTER TABLE news_source_quality_rows ADD COLUMN IF NOT EXISTS payload_hash TEXT")
  op.execute("ALTER TABLE token_profile_current ADD COLUMN IF NOT EXISTS payload_hash TEXT")
  op.execute("""
  UPDATE news_page_rows
     SET payload_hash = md5(row_to_json(news_page_rows)::text)
   WHERE payload_hash IS NULL
  """)
  op.execute("""
  UPDATE news_source_quality_rows
     SET payload_hash = md5(row_to_json(news_source_quality_rows)::text)
   WHERE payload_hash IS NULL
  """)
  op.execute("""
  UPDATE token_profile_current
     SET payload_hash = md5(row_to_json(token_profile_current)::text)
   WHERE payload_hash IS NULL
  """)
  op.execute("ALTER TABLE news_page_rows ALTER COLUMN payload_hash SET NOT NULL")
  op.execute("ALTER TABLE news_source_quality_rows ALTER COLUMN payload_hash SET NOT NULL")
  op.execute("ALTER TABLE token_profile_current ALTER COLUMN payload_hash SET NOT NULL")
  op.execute("ANALYZE macro_view_snapshots")
  op.execute("ANALYZE macro_observation_series_rows")
  ```

  Concurrent index block:

  ```python
  with op.get_context().autocommit_block():
      op.execute("SET lock_timeout = '5s'")
      op.execute("SET statement_timeout = '30min'")
      op.execute("""
      CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_macro_observation_series_rows_history_order
        ON macro_observation_series_rows(projection_version, concept_key, observed_at DESC, series_rank)
      """)
      op.execute("""
      DROP INDEX CONCURRENTLY IF EXISTS idx_macro_observation_series_rows_compact_lookup
      """)
      op.execute("RESET lock_timeout")
      op.execute("RESET statement_timeout")
  ```

- [ ] **Step 4: Run migration tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit migration**

  ```bash
  git add src/parallax/platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py \
    tests/unit/test_postgres_schema.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py
  git commit -m "fix: hard cut retired runtime lifecycle storage"
  ```

---

## Task 2: P0 Macro Current Snapshot Lifecycle

**Files:**
- Modify: `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Modify: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Test: `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`
- Test: `tests/unit/domains/macro_intel/test_macro_generation_swap.py`

- [ ] **Step 1: Write failing tests for stable snapshot identity**

  Add:

  ```python
  def test_macro_snapshot_id_is_stable_current_identity() -> None:
      snapshot = build_macro_view_snapshot([], computed_at_ms=1_777_000_000_000)
      assert snapshot["snapshot_id"] == "macro-view:macro_regime_v4:current"


  def test_macro_projection_skips_snapshot_when_series_unchanged(fake_repos) -> None:
      fake_repos.macro_intel.refresh_result = {
          "status": "unchanged",
          "rows_written": 0,
          "source_rows": 22743,
          "source_signature": "sig-1",
      }
      result = MacroViewProjectionWorker(...).run_once_sync(now_ms=1_777_000_000_000)
      assert result.notes["series_status"] == "unchanged"
      assert result.notes["rows_written"] == 0
      assert fake_repos.macro_intel.insert_snapshot_calls == 0
  ```

- [ ] **Step 2: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest tests/unit/domains/macro_intel/test_macro_view_projection_worker.py -q
  ```

  Expected: FAIL because snapshot id includes `computed_at_ms` and worker inserts on unchanged.

- [ ] **Step 3: Implement stable snapshot id and insert skip**

  Change `build_macro_view_snapshot`:

  ```python
  "snapshot_id": f"macro-view:{MACRO_VIEW_PROJECTION_VERSION}:current",
  ```

  Change `MacroViewProjectionWorker.run_once_sync`:

  ```python
  if series_status == "unchanged":
      repos.macro_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)
      return WorkerResult(
          processed=0,
          notes={
              "claimed": len(claimed),
              "queue_depth": 0,
              "source_rows_scanned": int(refresh_result.get("source_rows") or 0),
              "targets_loaded": len(MACRO_CORE_CONCEPTS),
              "rows_written": 0,
              "projected_rows_written": 0,
              "snapshot_status": "unchanged",
              "series_status": "unchanged",
              "source_signature": source_signature,
              "projection_version": MACRO_VIEW_PROJECTION_VERSION,
          },
      )
  ```

  Change `insert_snapshot` to compute a content hash excluding `computed_at_ms` and gate updates:

  ```sql
  ON CONFLICT(snapshot_id) DO UPDATE SET
    status = excluded.status,
    regime = excluded.regime,
    overall_score = excluded.overall_score,
    panels_json = excluded.panels_json,
    indicators_json = excluded.indicators_json,
    triggers_json = excluded.triggers_json,
    data_gaps_json = excluded.data_gaps_json,
    source_coverage_json = excluded.source_coverage_json,
    features_json = excluded.features_json,
    chain_json = excluded.chain_json,
    scenario_json = excluded.scenario_json,
    scorecard_json = excluded.scorecard_json,
    payload_hash = excluded.payload_hash,
    computed_at_ms = excluded.computed_at_ms
  WHERE macro_view_snapshots.payload_hash IS DISTINCT FROM excluded.payload_hash
  RETURNING true AS changed
  ```

  Make `insert_snapshot` return `bool changed`.

- [ ] **Step 4: Run Macro snapshot tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit Macro snapshot hard cut**

  ```bash
  git add src/parallax/domains/macro_intel/services/macro_regime_engine.py \
    src/parallax/domains/macro_intel/repositories/macro_intel_repository.py \
    src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py
  git commit -m "fix: hard cut macro snapshot current lifecycle"
  ```

---

## Task 3: P1 Macro Dirty Target Driver

**Files:**
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Modify: `src/parallax/domains/macro_intel/services/macro_sync_service.py`
- Modify: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Test: `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`
- Test: `tests/unit/domains/macro_intel/test_macro_sync_service.py`
- Test: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Write failing idle-path test**

  Add:

  ```python
  def test_macro_view_projection_without_dirty_target_does_not_scan_observations(fake_repos) -> None:
      fake_repos.macro_projection_dirty_targets.claimed = []
      result = MacroViewProjectionWorker(...).run_once_sync(now_ms=1_777_000_000_000)
      assert result.processed == 0
      assert result.notes["claimed"] == 0
      assert result.notes["source_rows_scanned"] == 0
      assert fake_repos.macro_intel.refresh_observation_series_rows_calls == 0
      assert fake_repos.macro_intel.observations_for_concepts_calls == 0
  ```

- [ ] **Step 2: Write failing enqueue test**

  Add:

  ```python
  def test_macro_sync_enqueues_projection_dirty_target_when_observations_change(fake_repos) -> None:
      service = MacroSyncService(...)
      fake_repos.macro_intel.upsert_observations_result = {"inserted": 3, "updated": 2, "unchanged": 10}
      service.run_window(...)
      assert fake_repos.macro_projection_dirty_targets.enqueued == [
          {
              "projection_name": "macro_view",
              "projection_version": "macro_regime_v4",
              "target_kind": "macro_view",
              "target_id": "macro_view",
          }
      ]
  ```

- [ ] **Step 3: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_sync_service.py \
    -q
  ```

  Expected: FAIL because Macro projection is interval-scan driven.

- [ ] **Step 4: Implement dirty target methods**

  Add repository methods:

  ```python
  def enqueue_macro_projection_dirty_target(
      self,
      *,
      projection_name: str,
      projection_version: str,
      now_ms: int,
      due_at_ms: int | None = None,
      reason: str,
      commit: bool = True,
  ) -> int:
      cursor = self.conn.execute(
          """
          INSERT INTO macro_projection_dirty_targets(
            projection_name, projection_version, target_kind, target_id,
            due_at_ms, created_at_ms, updated_at_ms, last_error
          )
          VALUES (%s, %s, 'macro_view', 'macro_view', %s, %s, %s, NULL)
          ON CONFLICT(projection_name, projection_version, target_kind, target_id) DO UPDATE SET
            due_at_ms = LEAST(macro_projection_dirty_targets.due_at_ms, excluded.due_at_ms),
            lease_owner = NULL,
            lease_expires_at_ms = NULL,
            last_error = NULL,
            updated_at_ms = excluded.updated_at_ms
          """,
          (projection_name, projection_version, int(due_at_ms or now_ms), int(now_ms), int(now_ms)),
      )
      if commit:
          self.conn.commit()
      return int(cursor.rowcount or 0)
  ```

  Claim SQL must use `FOR UPDATE SKIP LOCKED` and lease fields.

- [ ] **Step 5: Gate worker on claim**

  Worker shape:

  ```python
  claimed = repos.macro_projection_dirty_targets.claim_due(
      projection_name="macro_view",
      projection_version=MACRO_VIEW_PROJECTION_VERSION,
      limit=1,
      lease_ms=self._lease_ms(),
      lease_owner=self.name,
      now_ms=now,
      commit=False,
  )
  if not claimed:
      return WorkerResult(processed=0, notes={"claimed": 0, "source_rows_scanned": 0, "rows_written": 0})
  ```

- [ ] **Step 6: Enqueue from Macro sync only when facts changed**

  In `MacroSyncService`, after observation upsert/import result:

  ```python
  changed_count = int(result.get("inserted") or 0) + int(result.get("updated") or 0)
  if changed_count > 0:
      repos.macro_intel.enqueue_macro_projection_dirty_target(
          projection_name="macro_view",
          projection_version=MACRO_VIEW_PROJECTION_VERSION,
          now_ms=finished_at_ms,
          reason="macro_observations_changed",
          commit=False,
      )
  ```

- [ ] **Step 7: Run Macro dirty target tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_sync_service.py \
    tests/architecture/test_worker_runtime_contracts.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 8: Commit Macro dirty target driver**

  ```bash
  git add src/parallax/domains/macro_intel \
    src/parallax/app/runtime/worker_manifest.py \
    tests/unit/domains/macro_intel \
    tests/architecture/test_worker_runtime_contracts.py
  git commit -m "fix: drive macro projection from dirty targets"
  ```

---

## Task 4: P1 CEX OI Radar Current-Only Board

**Files:**
- Modify: `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`
- Modify: `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py`
- Modify: `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Write failing repository tests**

  Add:

  ```python
  def test_cex_oi_board_rows_are_stable_current_rows(repo) -> None:
      first = [{"target_id": "cex_symbol:binance:BTCUSDT", "rank": 1, "native_market_id": "BTCUSDT", "base_symbol": "BTC", "quote_symbol": "USDT", "score": 99}]
      second = [{**first[0], "score": 98}]
      repo.publish_board(rows=first, computed_at_ms=1000, period="5m", status="success", notes={})
      repo.publish_board(rows=second, computed_at_ms=2000, period="5m", status="success", notes={})
      rows = repo.latest_board(limit=10)["rows"]
      assert len(rows) == 1
      assert rows[0]["row_id"] == "cex-oi-radar-row:binance:USDT:PERPETUAL:5m:cex_symbol:binance:BTCUSDT"
      assert rows[0]["score"] == 98
  ```

  Add architecture guard:

  ```python
  def test_cex_oi_radar_runtime_has_no_latest_run_serving_pattern() -> None:
      source = (SRC / "domains/cex_market_intel/repositories/cex_oi_radar_repository.py").read_text()
      assert "run_id" not in source
      assert "ORDER BY finished_at_ms DESC" not in source
      assert "cex_oi_radar_runs" not in source
  ```

- [ ] **Step 2: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py \
    tests/architecture/test_worker_runtime_contracts.py \
    -q
  ```

  Expected: FAIL because repository uses `run_id`.

- [ ] **Step 3: Implement current-only repository**

  Replace run methods with:

  ```python
  def publish_board(
      self,
      *,
      rows: list[dict[str, Any]],
      computed_at_ms: int,
      period: str,
      status: str,
      notes: dict[str, Any],
  ) -> int:
      board_key = f"binance:USDT:PERPETUAL:{period}"
      self.conn.execute(
          """
          INSERT INTO cex_oi_radar_publication_state(
            board_key, provider, exchange, quote_symbol, contract_type, period,
            status, row_count, computed_at_ms, notes_json, updated_at_ms
          )
          VALUES (
            %s, 'binance', 'binance', 'USDT',
            'PERPETUAL', %s, %s, %s, %s, %s, %s
          )
          ON CONFLICT(board_key) DO UPDATE SET
            status = excluded.status,
            row_count = excluded.row_count,
            computed_at_ms = excluded.computed_at_ms,
            notes_json = excluded.notes_json,
            updated_at_ms = excluded.updated_at_ms
          """,
          (board_key, period, status, len(rows), Jsonb(notes), int(computed_at_ms), int(computed_at_ms)),
      )
      self.conn.execute("DELETE FROM cex_oi_radar_rows WHERE period = %s", (period,))
      return self.insert_current_rows(period=period, rows=rows, computed_at_ms=computed_at_ms)
  ```

  Use stable `row_id`:

  ```python
  def _row_id(period: str, target_id: str) -> str:
      return f"cex-oi-radar-row:binance:USDT:PERPETUAL:{period}:{target_id}"
  ```

- [ ] **Step 4: Update worker to remove run id**

  Worker notes must not include `run_id`. Failure path calls `publish_board(rows=[], status="failed", notes={"reason": type(exc).__name__})`.

- [ ] **Step 5: Run CEX tests**

  Run:

  ```bash
  uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py -q
  ```

  Expected: PASS.

- [ ] **Step 6: Commit CEX hard cut**

  ```bash
  git add src/parallax/domains/cex_market_intel \
    tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py \
    tests/architecture/test_worker_runtime_contracts.py
  git commit -m "fix: hard cut cex oi board current lifecycle"
  ```

---

## Task 5: P1/P2 Current-Row Unchanged Write Gates

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py`
- Modify: `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`
- Test: `tests/unit/domains/asset_market/test_token_capture_tier_repository.py`
- Test: `tests/unit/domains/asset_market/test_token_profile_current_repository.py`

- [ ] **Step 1: Write failing news page unchanged test**

  Add:

  ```python
  def test_replace_page_rows_for_items_keeps_unchanged_row_without_delete_reinsert(repo) -> None:
      row = _news_page_row(news_item_id="news-1", computed_at_ms=1000)
      first = repo.replace_page_rows_for_items(news_item_ids=["news-1"], rows=[row], commit=True)
      second = repo.replace_page_rows_for_items(news_item_ids=["news-1"], rows=[row], commit=True)
      assert first == {"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 0}
      assert second == {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0}
  ```

- [ ] **Step 2: Write failing token current tests**

  Add:

  ```python
  def test_token_capture_tier_upsert_returns_false_when_payload_unchanged(repo) -> None:
      assert repo.upsert_tier(target_type="chain_token", target_id="sol:abc", tier=1, reason="ranked", score=Decimal("1"), updated_at_ms=1000) is True
      assert repo.upsert_tier(target_type="chain_token", target_id="sol:abc", tier=1, reason="ranked", score=Decimal("1"), updated_at_ms=2000) is False


  def test_token_profile_current_upsert_returns_false_when_payload_unchanged(repo) -> None:
      row = _profile_row(target_id="sol:abc", computed_at_ms=1000)
      assert repo.upsert_current(row, commit=True) is True
      assert repo.upsert_current({**row, "computed_at_ms": 2000, "updated_at_ms": 2000}, commit=True) is False
  ```

- [ ] **Step 3: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/unit/domains/asset_market/test_token_capture_tier_repository.py \
    tests/unit/domains/asset_market/test_token_profile_current_repository.py \
    -q
  ```

  Expected: FAIL because current repositories update unconditionally.

- [ ] **Step 4: Implement page/source/profile payload hashes**

  Hash helper:

  ```python
  def _stable_payload_hash(payload: Mapping[str, Any], *, exclude: set[str]) -> str:
      normalized = {key: value for key, value in payload.items() if key not in exclude}
      encoded = json.dumps(postgres_safe_json(normalized), sort_keys=True, separators=(",", ":"))
      return hashlib.sha256(encoded.encode()).hexdigest()
  ```

  Exclude timestamps that are publication metadata: `computed_at_ms`, `updated_at_ms`, `projected_at_ms`.

  Use SQL gate:

  ```sql
  ON CONFLICT(row_id) DO UPDATE SET
    ...
    payload_hash = EXCLUDED.payload_hash,
    computed_at_ms = EXCLUDED.computed_at_ms
  WHERE news_page_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
  RETURNING (xmax = 0) AS inserted
  ```

- [ ] **Step 5: Implement token capture/profile gates**

  Token capture conflict update:

  ```sql
  ON CONFLICT(target_type, target_id) DO UPDATE SET
    tier = EXCLUDED.tier,
    reason = EXCLUDED.reason,
    score = EXCLUDED.score,
    updated_at_ms = EXCLUDED.updated_at_ms
  WHERE token_capture_tier.tier IS DISTINCT FROM EXCLUDED.tier
     OR token_capture_tier.reason IS DISTINCT FROM EXCLUDED.reason
     OR token_capture_tier.score IS DISTINCT FROM EXCLUDED.score
  RETURNING true AS changed
  ```

  Token profile uses `payload_hash` excluding `computed_at_ms` and `updated_at_ms`.

- [ ] **Step 6: Run current-row tests**

  Run:

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/unit/domains/asset_market/test_token_capture_tier_repository.py \
    tests/unit/domains/asset_market/test_token_profile_current_repository.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 7: Commit unchanged gates**

  ```bash
  git add src/parallax/domains/news_intel/repositories/news_repository.py \
    src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py \
    src/parallax/domains/asset_market/repositories/token_profile_current_repository.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/unit/domains/asset_market/test_token_capture_tier_repository.py \
    tests/unit/domains/asset_market/test_token_profile_current_repository.py
  git commit -m "fix: skip unchanged current row writes"
  ```

---

## Task 6: P1 Agent Queue Capacity and Run Ledger

**Files:**
- Modify: `src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
- Modify related repository tests under `tests/unit/domains/*`

- [ ] **Step 1: Write claim-before-capacity guard tests**

  For each worker, add a test with a fake capacity gate returning `rejected`:

  ```python
  def test_worker_does_not_claim_queue_when_agent_capacity_rejects(fake_repos, fake_agent_gate) -> None:
      fake_agent_gate.reserve_result = AgentReservation.rejected(reason="rpm_limit")
      result = Worker(...).run_once_sync(now_ms=1_777_000_000_000)
      assert result.skipped == 1
      assert fake_repos.dirty_targets.claim_due_calls == 0
      assert fake_repos.model_runs.inserted == []
  ```

- [ ] **Step 2: Write provider-started validation ledger tests**

  For `mention_semantics` and `token_discussion_digest`, add:

  ```python
  def test_provider_started_validation_error_writes_model_run_and_releases_claim(fake_repos, fake_provider) -> None:
      fake_provider.result = {"invalid": "schema"}
      result = Worker(...).run_once_sync(now_ms=1_777_000_000_000)
      assert result.failed == 1
      assert fake_repos.model_runs.last()["execution_started"] is True
      assert fake_repos.model_runs.last()["status"] == "failed"
      assert fake_repos.dirty_targets.mark_error_calls == 1
  ```

- [ ] **Step 3: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/narrative_intel \
    tests/unit/domains/news_intel \
    tests/unit/domains/equity_event_intel \
    -q
  ```

  Expected: FAIL on current claim-before-reserve behavior.

- [ ] **Step 4: Move capacity reservation before claim**

  Worker order must be:

  ```python
  reservation = agent_capacity.reserve(lane=lane_name, now_ms=now)
  if not reservation.accepted:
      return WorkerResult(skipped=1, notes={"reason": reservation.reason, "claimed": 0})

  claimed = dirty_repo.claim_due(...)
  if not claimed:
      reservation.release()
      return WorkerResult(processed=0, notes={"claimed": 0})
  ```

  Do not mark queue error for no-start capacity rejection.

- [ ] **Step 5: Wrap provider-started validation/publication**

  Shape:

  ```python
  execution_started = False
  try:
      execution_started = True
      raw_result = provider.generate(...)
      validated = validate_batch_result(raw_result)
      publish(validated)
      model_runs.mark_success(...)
  except Exception as exc:
      if execution_started:
          model_runs.mark_failed(..., error=str(exc), execution_started=True)
      dirty_repo.mark_error(claimed, error=str(exc), retry_ms=retry_ms, now_ms=now)
      return WorkerResult(failed=len(claimed), notes={"claimed": len(claimed)})
  ```

- [ ] **Step 6: Run agent tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/narrative_intel \
    tests/unit/domains/news_intel \
    tests/unit/domains/equity_event_intel \
    -q
  ```

  Expected: PASS.

- [ ] **Step 7: Commit agent queue hard cut**

  ```bash
  git add src/parallax/domains/narrative_intel \
    src/parallax/domains/news_intel/runtime/news_item_brief_worker.py \
    src/parallax/domains/equity_event_intel/runtime/equity_event_brief_worker.py \
    tests/unit/domains/narrative_intel \
    tests/unit/domains/news_intel \
    tests/unit/domains/equity_event_intel
  git commit -m "fix: reserve agent capacity before queue claim"
  ```

---

## Task 7: Remove Runtime Compatibility Fallbacks and Product/Control Drift

**Files:**
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/parallax/app/surfaces/api/routes_macro.py`
- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_case_service.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`
- Test: `tests/unit/app/surfaces/api/test_routes_macro.py`
- Test: `tests/architecture/test_worker_runtime_contracts.py`
- Test: `tests/architecture/test_runtime_lifecycle_hard_cut.py`

- [ ] **Step 1: Write fallback-removal architecture test**

  Add:

  ```python
  def test_no_runtime_compatibility_fallbacks_for_agent_contracts() -> None:
      source = (SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py").read_text()
      assert "DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT" not in source
      assert "client.model" not in source
      assert "fallback" not in source.lower()
  ```

- [ ] **Step 2: Write Macro API product-truth test**

  Add:

  ```python
  def test_macro_api_currentness_does_not_read_sync_runs() -> None:
      source = (SRC / "app/surfaces/api/routes_macro.py").read_text()
      assert "latest_macro_sync_run" not in source
      assert "latest_import_run" not in source
      assert "latest_sync_run" not in source
      assert "latest_snapshot" in source
  ```

- [ ] **Step 3: Run tests and verify failure**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py \
    tests/unit/app/surfaces/api/test_routes_macro.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_lifecycle_hard_cut.py \
    -q
  ```

  Expected: FAIL until fallbacks and control-plane reads are removed.

- [ ] **Step 4: Remove Pulse runtime fallback**

  Replace fallback behavior with fail-fast config error:

  ```python
  if set(runtime_contract.stage_names) != set(configured_stage_names):
      raise RuntimeError("pulse_agent_runtime_contract_mismatch")

  if lane_model is None:
      raise RuntimeError(f"pulse_agent_lane_model_missing:{lane_name}")
  ```

- [ ] **Step 5: Remove Macro control-plane from product payload**

  `/api/macro` currentness must use:

  ```python
  snapshot = repos.macro_intel.latest_snapshot()
  publication_state = repos.macro_intel.macro_series_publication_state(MACRO_VIEW_PROJECTION_VERSION)
  ```

  Do not include `macro_sync_runs`, `macro_import_runs`, or `macro_sync_windows` in public product payload. If ops needs them, keep them behind an ops diagnostics route.

- [ ] **Step 6: Remove Token dossier process-local cache fallback**

  Token dossier market data must read durable `market_tick_current` or latest persisted `market_ticks`; if missing, return `status="missing"`. Do not call `LivePriceGateway.snapshot()` from product read models.

- [ ] **Step 7: Fix manifest drift**

  Required manifest changes:

  ```python
  live_price_gateway = WorkerManifest(
      writes_facts=(),
      writes_read_models=(),
      writes_control_plane=(),
      wakes_out=(),
      input_contract=("token_capture_tier", "market_ticks"),
  )

  notification_delivery = WorkerManifest(
      writes_control_plane=("notification_deliveries",),
      writes_facts=(),
  )
  ```

  Collector manifest must list every table it writes or move derived writes to the owning worker; do not leave stale partial contracts.

- [ ] **Step 8: Run contract tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py \
    tests/unit/app/surfaces/api/test_routes_macro.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_lifecycle_hard_cut.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 9: Commit fallback/control cleanup**

  ```bash
  git add src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py \
    src/parallax/app/surfaces/api/routes_macro.py \
    src/parallax/app/runtime/worker_manifest.py \
    src/parallax/domains/token_intel/read_models/token_case_service.py \
    tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py \
    tests/unit/app/surfaces/api/test_routes_macro.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_lifecycle_hard_cut.py
  git commit -m "fix: remove runtime compatibility fallbacks"
  ```

---

## Task 8: Global Lifecycle Guard Tests and Docs

**Files:**
- Create: `tests/architecture/test_runtime_lifecycle_hard_cut.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify or move obsolete active docs under `docs/superpowers/{specs,plans}/active`

- [ ] **Step 1: Add global schema/source guard**

  Test:

  ```python
  FORBIDDEN_CURRENT_IDENTITY_TOKENS = (
      "generation_id",
      "run_id",
      "attempt_id",
  )


  CURRENT_READ_MODEL_TABLES = (
      "macro_view_snapshots",
      "macro_observation_series_rows",
      "token_radar_current_rows",
      "market_tick_current",
      "token_profile_current",
      "news_page_rows",
      "news_source_quality_rows",
      "cex_oi_radar_rows",
  )


  def test_current_read_models_do_not_use_run_generation_identity() -> None:
      migrations = "\n".join(path.read_text() for path in MIGRATIONS.glob("*.py"))
      for table in CURRENT_READ_MODEL_TABLES:
          block = _latest_create_or_alter_block(migrations, table)
          for token in FORBIDDEN_CURRENT_IDENTITY_TOKENS:
              assert token not in block, f"{table} must not use {token}"
  ```

- [ ] **Step 2: Add retired Macro docs drift guard**

  Test:

  ```python
  def test_active_docs_do_not_instruct_macro_active_generation_runtime() -> None:
      active_docs = list((ROOT / "docs/superpowers/specs/active").glob("*.md"))
      active_docs += list((ROOT / "docs/superpowers/plans/active").glob("*.md"))
      offenders = []
      for path in active_docs:
          text = path.read_text()
          if "macro_observation_series_active_generation" in text and "retired" not in text.lower():
              offenders.append(str(path))
          if "Macro 使用 generation stage/swap" in text:
              offenders.append(str(path))
      assert offenders == []
  ```

- [ ] **Step 3: Update router docs**

  Add to both `AGENTS.md` and `CLAUDE.md`:

  ```markdown
  ## Current read model lifecycle

  Current/serving read models must be bounded by product identity, not by worker
  run identity. Do not put `generation_id`, `run_id`, timestamp-derived
  snapshot ids, or UUID ids into serving current-row primary keys. If a read
  model needs history, create a separate audit/history table with explicit
  retention and keep public readers off that table. Unchanged projection runs
  must write zero serving rows and expose `unchanged` in worker notes.
  ```

- [ ] **Step 4: Update architecture docs**

  Add rules:

  - `NOTIFY` remains wake hint; dirty target or bounded interval catch-up is required.
  - Control ledgers are not product truth.
  - Current read models must publish by stable key and payload hash.
  - Migration deleting retired physical data is preferred over retaining legacy tables after hard cut.

- [ ] **Step 5: Clean active spec/plan residuals**

  For active docs that still contain executable instructions to create or read `macro_observation_series_active_generation`, either:

  - move completed/superseded documents to `docs/superpowers/{specs,plans}/completed`, or
  - replace implementation instructions with a short superseded banner:

  ```markdown
  > Superseded by 2026-05-27 runtime lifecycle hard cut. Macro active-generation
  > runtime is retired and must not be reimplemented.
  ```

  Do not leave active checklist items telling future agents to implement generation stage/swap.

- [ ] **Step 6: Run docs/architecture tests**

  Run:

  ```bash
  uv run pytest tests/architecture/test_runtime_lifecycle_hard_cut.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: PASS.

- [ ] **Step 7: Commit guard/docs**

  ```bash
  git add tests/architecture/test_runtime_lifecycle_hard_cut.py \
    docs/ARCHITECTURE.md docs/RELIABILITY.md docs/WORKERS.md docs/references/POSTGRES_PERFORMANCE.md \
    AGENTS.md CLAUDE.md docs/superpowers/specs docs/superpowers/plans
  git commit -m "docs: codify current read model lifecycle rules"
  ```

---

## Task 9: Verification, Docker Rebuild, Live Cleanup Proof

**Files:**
- Create or update: `docs/superpowers/plans/active/2026-05-27-next-runtime-lifecycle-hard-cut-verification-cn.md`

- [ ] **Step 1: Run focused unit/integration suite**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel \
    tests/unit/domains/cex_market_intel \
    tests/unit/domains/asset_market \
    tests/unit/domains/narrative_intel \
    tests/unit/domains/news_intel \
    tests/unit/domains/equity_event_intel \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/architecture/test_runtime_lifecycle_hard_cut.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/unit/test_postgres_schema.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 2: Run lint**

  Run:

  ```bash
  uv run ruff check .
  ```

  Expected: PASS.

- [ ] **Step 3: Run full check gate if time permits**

  Run:

  ```bash
  make check-all
  ```

  Expected: PASS. If this is too slow, record the focused suite plus reason in verification and run full gate before merge.

- [ ] **Step 4: Build and migrate Docker**

  Run:

  ```bash
  docker compose build app
  docker compose up -d postgres migrate app
  ```

  Expected: app healthy and Alembic at `20260527_0115`.

- [ ] **Step 5: Prove old data is gone**

  Run:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT
    to_regclass('macro_observation_series_rows_legacy_20260527_0114') AS macro_legacy,
    to_regclass('macro_observation_series_active_generation') AS macro_active_generation,
    to_regclass('macro_observation_series_generations') AS macro_generations,
    to_regclass('cex_oi_radar_runs') AS cex_runs;"
  ```

  Expected:

  ```text
  macro_legacy | macro_active_generation | macro_generations | cex_runs
  -------------+-------------------------+-------------------+---------
               |                         |                   |
  ```

- [ ] **Step 6: Prove serving row cardinality is bounded**

  Run:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT relname,
         pg_size_pretty(pg_total_relation_size(relid)) AS total,
         n_live_tup
  FROM pg_stat_user_tables
  WHERE relname IN (
    'macro_view_snapshots',
    'macro_observation_series_rows',
    'macro_projection_dirty_targets',
    'cex_oi_radar_rows',
    'cex_oi_radar_publication_state'
  )
  ORDER BY relname;"
  ```

  Expected:

  - `macro_view_snapshots`: one row per projection version.
  - `macro_observation_series_rows`: proportional to concepts x limit, not run count.
  - `cex_oi_radar_rows`: zero if worker disabled; otherwise bounded by universe limit.

- [ ] **Step 7: Prove idle Macro projection does not scan facts**

  Run two consecutive Macro worker cycles or wait through two app intervals, then query logs/pg_stat:

  ```bash
  docker compose logs --since=10m app | rg "macro_view_projection|series_status|source_rows_scanned"
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT calls, round(total_exec_time::numeric,2) AS total_ms, round(mean_exec_time::numeric,2) AS mean_ms,
         temp_blks_written,
         left(regexp_replace(query, '\\s+', ' ', 'g'), 180) AS query
  FROM pg_stat_statements
  WHERE query ILIKE '%WITH source_ranked%'
    AND query ILIKE '%macro_observations%'
  ORDER BY calls DESC
  LIMIT 5;"
  ```

  Expected: no repeated source-ranked calls when no dirty target is due; worker notes show `claimed=0` or `series_status=unchanged` with `rows_written=0`.

- [ ] **Step 8: Prove no runtime compatibility strings remain**

  Run:

  ```bash
  rg -n "macro_observation_series_active_generation|macro_observation_series_generations|generation stage/swap|cex_oi_radar_runs|oi_radar_run_id|DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT|client.model|legacy fallback|compat" \
    src tests docs AGENTS.md CLAUDE.md
  ```

  Expected: no runtime source matches. Migration historical references are allowed only in old migration files and tests that assert retirement.

- [ ] **Step 9: Record verification artifact**

  Create `docs/superpowers/plans/active/2026-05-27-next-runtime-lifecycle-hard-cut-verification-cn.md` with:

  - Commit list.
  - Test outputs.
  - Docker migration status.
  - Live table-size proof.
  - Logs showing Macro idle no-scan.
  - Remaining risks. Expected remaining risks should be empty except external provider 522/notification delivery failures.

- [ ] **Step 10: Final commit**

  ```bash
  git add docs/superpowers/plans/active/2026-05-27-next-runtime-lifecycle-hard-cut-verification-cn.md
  git commit -m "docs: verify runtime lifecycle hard cut"
  ```

---

## Completion Gate

This plan is complete only when all of these are true:

- `macro_observation_series_rows_legacy_20260527_0114` is dropped from live DB.
- `macro_view_snapshots` is current-only and no longer grows by worker run count.
- `macro_view_projection` has a no-dirty-target idle path that does not scan `macro_observations`.
- `cex_oi_radar_runs` is gone and CEX board rows are current-only.
- Agent workers reserve capacity before queue claim.
- Runtime compatibility fallbacks are removed.
- Active docs no longer instruct agents to recreate Macro active generation.
- Focused tests, architecture tests, ruff, Docker build, Alembic migrate, and live log checks are recorded.
