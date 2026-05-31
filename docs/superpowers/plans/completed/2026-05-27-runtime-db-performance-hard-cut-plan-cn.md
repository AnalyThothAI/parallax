# Runtime DB Performance Hard Cut Implementation Plan

> 2026-05-27 hard-cut update: this plan has been superseded by the next
> lifecycle hard-cut for any residual storage cleanup. Do not preserve the
> temporary legacy table `macro_observation_series_rows_legacy_20260527_0114`
> after verification, do not reintroduce `macro_observation_series_active_generation`,
> and do not use generation/run/attempt/timestamp/UUID identities for current
> read-model serving keys.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 P0/P1/P2 一次性硬切实时链路剩余数据库性能问题：Token Radar current rows 必须窗口新鲜，Token Radar 私有缓存必须有生命周期，Macro projection 不能再用 timestamp/UUID generation 复制 100GB 级 read model。

**Architecture:** Token Radar 在 publication 边界做窗口 eligibility，缓存 TTL 只作用于 projection-private 表，current rows 仍只由 `publish_current_generation()` 替换。Macro projected series 改为 current-only/source-signature 模型：事实未变时不重写，事实变化时 stage 后事务性替换 compact current rows。全程不加兼容 reader、legacy fallback、旧 generation 分支。

**Tech Stack:** Python 3.13, psycopg 3, PostgreSQL 18, Alembic, pytest, ruff, Docker Compose.

---

## Owning Spec

- Spec: `docs/superpowers/specs/active/2026-05-27-runtime-db-performance-hard-cut-cn.md`
- Worktree: `.worktrees/macro-sync-worker-hard-cut/`
- Branch: `main`

## Pre-flight

- [ ] Spec is approved by Qinghuan.
- [ ] Confirm worktree:

  ```bash
  git -C /Users/qinghuan/Documents/code/parallax/.worktrees/macro-sync-worker-hard-cut branch --show-current
  git -C /Users/qinghuan/Documents/code/parallax/.worktrees/macro-sync-worker-hard-cut status --short
  ```

  Expected: branch is `main`; only the spec/plan docs are uncommitted before implementation.

- [ ] Confirm live runtime config paths without printing secrets:

  ```bash
  uv run parallax config
  ```

  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`.

- [ ] Record baseline targeted tests:

  ```bash
  uv run pytest \
    tests/unit/test_token_radar_repository.py \
    tests/unit/test_token_radar_projection.py \
    tests/unit/domains/token_intel/test_token_radar_rank_source_query.py \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    -q
  ```

- [ ] Record baseline lint:

  ```bash
  uv run ruff check .
  ```

- [ ] Record baseline DB evidence before migration/code rollout:

  ```sql
  SELECT relname,
         reltuples::bigint AS estimated_rows,
         pg_size_pretty(pg_relation_size(oid)) AS heap,
         pg_size_pretty(pg_indexes_size(oid)) AS indexes,
         pg_size_pretty(pg_total_relation_size(oid)) AS total
  FROM pg_class
  WHERE relname IN (
    'token_radar_target_features',
    'token_radar_rank_source_events',
    'token_radar_current_rows',
    'token_radar_publication_state',
    'macro_observation_series_rows',
    'macro_observation_series_generations',
    'macro_observation_series_active_generation'
  )
  ORDER BY pg_total_relation_size(oid) DESC;
  ```

## Review Corrections

这些修正来自三路只读 review，实施时视为本 plan 的硬约束：

- **Token Radar P0:** repository cutoff 是性能边界，service 层还要做一次同样 cutoff 的不变量过滤；这不是兼容逻辑，而是防止 fake repo、未来 repo 变体或查询回归把 stale rows 发布到 current rows。测试里的 fake repository 必须在返回前应用 cutoff，另外断言最终 publish rows 全部满足窗口新鲜。
- **Token Radar P0/P1:** 所有窗口计算使用 `WINDOW_MS[window]`，未知窗口必须 fail fast；不要使用 `WINDOW_MS.get(window, WINDOW_MS["1h"])`。
- **Token Radar P1:** `token_radar_target_features` 需要新增面向 retention delete 的 freshness index：`(projection_version, "window", scope, latest_event_received_at_ms DESC)`。现有 rank-score index 和 market freshness index 不覆盖这个删除路径。
- **Token Radar P1:** prune 是 projection-private cache cleanup。除非显式包进同一个 transaction，否则不要传 `commit=False`；当前 psycopg runtime connection 是 autocommit=false 但 `refresh_rank_set()` 的 publish transaction 晚于 rank input load，误传 `commit=False` 会把缓存清理和后续 publish 生命周期混在一起。
- **Macro P2:** 这次卡顿根因是 read-model lifecycle 设计/实现错误，不是 PostgreSQL 参数问题。Macro 虽然有单 writer，但用 timestamp/UUID physical generation 持续复制 current read model，并且 cleanup 批量上限追不上写入，active pointer 只隐藏了 serving 面积，没有控制物理表膨胀。
- **Macro P2:** compact table 必须保持现有 serving contract 类型：`observed_at TIMESTAMPTZ NOT NULL`、`value_numeric DOUBLE PRECISION NOT NULL`、`data_quality TEXT`。不要悄悄改成 `DATE` 或放宽 `value_numeric`。
- **Macro P2:** migration 不能在 legacy table 仍持有旧 primary-key/index 名称时创建同名 `macro_observation_series_rows_pkey`。compact 阶段使用临时约束/index 名，swap 后要么保留临时名到 legacy drop，要么先 drop/rename legacy constraint/index 再改最终名。
- **Macro P2:** source signature 只包含业务事实和 projection 参数，必须排除 `now_ms`、UUID、`projected_at_ms`、`ingested_at_ms`。`ingested_at_ms` 会在重导入同一业务事实时变化，纳入签名会导致 unchanged skip 失效。
- **Macro P2:** migration 不要求初始化 `macro_observation_series_publication_state.source_signature`；上线后第一次 worker run 可能重写一次 compact rows，这是可接受的冷启动成本，第二次必须 unchanged/0 writes。
- **Architecture guards:** `rg` 扫描只是辅助；必须有 AST/SQL contract tests 覆盖 no-cutoff rank input call、Macro active-generation reader、runtime generation writer、manifest writer contract。

## File-level Edits

### Token Radar P0/P1

- Modify `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
  - Change `list_rank_inputs_for_rank_set` so `min_latest_event_received_at_ms: int` is required.
  - Add `AND latest_event_received_at_ms >= %s` to the rank-input SQL.
  - Add `prune_target_features` scoped by `projection_version`, `window`, `scope`, and cutoff.
  - Do not add defaults that allow old no-cutoff call sites.

- Modify `src/parallax/domains/token_intel/services/token_radar_projection.py`
  - Pass `now_ms` into `_rank_current_rows`.
  - Compute P0 cutoff as `computed_at_ms - WINDOW_MS[window]`.
  - Compute P1 retention cutoff as `computed_at_ms - 3 * WINDOW_MS[window]`.
  - Prune private cache before rank inputs are loaded.
  - Keep current-row replacement inside `publish_current_generation()`.

- Modify `src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py`
  - Add `prune_edges` delegating to `TokenRadarRankSourceQuery`.

- Modify `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py`
  - Add scoped delete SQL for expired `token_radar_rank_source_events`.
  - Delete only rows matching projection/window/scope and `event_received_at_ms < cutoff`.
  - Do not touch material facts.

- Create Alembic migration:
  - `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py`
  - Add `idx_token_radar_target_features_window_freshness` on `(projection_version, "window", scope, latest_event_received_at_ms DESC)`.
  - Use PostgreSQL `CREATE INDEX CONCURRENTLY IF NOT EXISTS` in an autocommit block.

- Modify tests:
  - `tests/unit/test_token_radar_repository.py`
  - `tests/unit/test_token_radar_projection.py`
  - `tests/unit/domains/token_intel/test_token_radar_rank_source_query.py`
  - `tests/unit/test_postgres_schema.py`
  - `tests/architecture/test_token_radar_publication_state_hard_cut.py`

### Macro P2

- Create Alembic migration:
  - `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py`
  - `revision = "20260527_0114"`
  - `down_revision = "20260527_0113"`

- Modify `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
  - Replace timestamp/UUID physical generation writes with current-only refresh.
  - Add deterministic source signature calculation that does not include `now_ms` or UUIDs.
  - Add compact publication state upsert.
  - Update `latest_observations`, `observations_for_concepts`, and `concept_history_counts` to read current rows directly without active-generation joins.
  - Remove `_generation_id` use from runtime refresh.

- Modify `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
  - Accept a structured refresh result instead of an integer.
  - Report `series_status`, `projected_rows_written`, `source_signature`, and `source_rows_scanned` in worker notes.
  - Preserve snapshot build from current projected rows.

- Modify tests:
  - `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
  - `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
  - `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`
  - Add one integration-style repository test if existing fake DB coverage cannot prove row count does not double.

- Modify docs if implementation changes public ops semantics:
  - `docs/WORKERS.md`
  - `docs/references/POSTGRES_PERFORMANCE.md`
  - `src/parallax/domains/macro_intel/ARCHITECTURE.md`
  - `src/parallax/app/runtime/worker_manifest.py`
  - `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
  - `tests/architecture/test_worker_runtime_contracts.py`
  - `tests/unit/domains/macro_intel/test_macro_feature_engine.py`

---

## Task 1: P0 Token Radar Window Cutoff at Rank Input

**Files:**
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py:565`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py:296`
- Test: `tests/unit/test_token_radar_repository.py`
- Test: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 1: Write repository cutoff test**

  Add or replace `test_list_rank_inputs_for_rank_set_filters_by_latest_event_cutoff`.

  Assertions:

  ```python
  assert "latest_event_received_at_ms >= %s" in conn.sql
  assert conn.params[-1] == 1_777_800_000_000
  ```

  Run:

  ```bash
  uv run pytest tests/unit/test_token_radar_repository.py::test_list_rank_inputs_for_rank_set_filters_by_latest_event_cutoff -q
  ```

  Expected before implementation: fail because the repository method has no cutoff parameter or SQL predicate.

- [ ] **Step 2: Require cutoff in rank input repository**

  Change signature to:

  ```python
  def list_rank_inputs_for_rank_set(
      self,
      *,
      projection_version: str,
      window: str,
      scope: str,
      min_latest_event_received_at_ms: int,
  ) -> list[dict[str, Any]]:
  ```

  Add SQL predicate:

  ```sql
  AND latest_event_received_at_ms >= %s
  ```

  Pass parameters in this order:

  ```python
  (projection_version, window, scope, int(min_latest_event_received_at_ms))
  ```

- [ ] **Step 3: Write projection stale-feature exclusion test**

  Add `test_refresh_rank_set_excludes_expired_target_features_without_dirty_claims`.

  Test shape:
  - `now_ms = 1_777_800_300_000`
  - `window="5m"`
  - fake repo receives `min_latest_event_received_at_ms == now_ms - WINDOW_MS["5m"]`
  - fake repo starts with one row at `now_ms - WINDOW_MS["5m"] - 1` and one row at `now_ms - 1_000`
  - fake repo applies `min_latest_event_received_at_ms` before returning rows
  - publish rows contain only the fresh identity

  Run:

  ```bash
  uv run pytest tests/unit/test_token_radar_projection.py::test_refresh_rank_set_excludes_expired_target_features_without_dirty_claims -q
  ```

  Expected before implementation: fail because `_rank_current_rows()` does not receive or pass a cutoff.

- [ ] **Step 4: Pass cutoff through projection**

  Change `_rank_current_rows` signature to:

  ```python
  def _rank_current_rows(
      self,
      *,
      window: str,
      scope: str,
      limit: int,
      now_ms: int,
  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  ```

  Inside it, calculate the cutoff with fail-fast window lookup:

  ```python
  window_ms = WINDOW_MS[window]
  min_latest_event_received_at_ms = int(now_ms) - int(window_ms)
  raw_rank_inputs = self.repos.token_radar.list_rank_inputs_for_rank_set(
      projection_version=PROJECTION_VERSION,
      window=window,
      scope=scope,
      min_latest_event_received_at_ms=min_latest_event_received_at_ms,
  )
  rank_inputs = [
      row
      for row in raw_rank_inputs
      if int(row.get("latest_event_received_at_ms") or 0) >= min_latest_event_received_at_ms
  ]
  ```

  The repository predicate is the performance boundary. The service filter is a hard invariant guard, not compatibility behavior.

  Change `refresh_rank_set()` call site to:

  ```python
  rank_inputs, rows = self._rank_current_rows(
      window=window,
      scope=scope,
      limit=limit,
      now_ms=computed_at_ms,
  )
  ```

- [ ] **Step 5: Verify P0 targeted tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/test_token_radar_repository.py::test_list_rank_inputs_for_rank_set_filters_by_latest_event_cutoff \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_excludes_expired_target_features_without_dirty_claims \
    -q
  ```

  Expected: both pass.

---

## Task 2: P0 Empty Fresh Generation and Architecture Guard

**Files:**
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/architecture/test_token_radar_publication_state_hard_cut.py`

- [ ] **Step 1: Add empty-generation regression test**

  Add `test_refresh_rank_set_publishes_empty_ready_generation_when_no_features_are_window_fresh`.

  Assertions:

  ```python
  assert published["rows"] == []
  assert result["status"] in {"ready", "published", "unchanged"}
  assert result["source_rows"] == 0
  ```

  The fake `publish_current_generation()` must be called with an empty row list.

- [ ] **Step 2: Strengthen architecture guard**

  In `tests/architecture/test_token_radar_publication_state_hard_cut.py`, add AST/string guard that every `list_rank_inputs_for_rank_set` call includes `min_latest_event_received_at_ms`.

  Expected forbidden pattern:

  ```text
  a list_rank_inputs_for_rank_set call with projection_version, window, and scope but without min_latest_event_received_at_ms
  ```

- [ ] **Step 3: Verify Task 2 tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_publishes_empty_ready_generation_when_no_features_are_window_fresh \
    tests/architecture/test_token_radar_publication_state_hard_cut.py \
    -q
  ```

---

## Task 3: P1 Token Radar Private Cache Retention

**Files:**
- Create/Modify: `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Modify: `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Test: `tests/unit/test_token_radar_repository.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_rank_source_query.py`
- Test: `tests/unit/test_token_radar_projection.py`
- Test: `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Add target feature freshness index migration and schema test**

  Add migration DDL:

  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_window_freshness
    ON token_radar_target_features(projection_version, "window", scope, latest_event_received_at_ms DESC);
  ```

  Add or update schema test asserting the index exists and includes `latest_event_received_at_ms`.

  Run:

  ```bash
  uv run pytest tests/unit/test_postgres_schema.py -q
  ```

- [ ] **Step 2: Add target feature prune repository test**

  Add `test_prune_target_features_deletes_only_projection_window_scope_before_cutoff`.

  Assertions:

  ```python
  assert "DELETE FROM token_radar_target_features" in conn.sql
  assert 'projection_version = %s' in conn.sql
  assert '"window" = %s' in conn.sql
  assert "scope = %s" in conn.sql
  assert "latest_event_received_at_ms < %s" in conn.sql
  assert "token_radar_current_rows" not in conn.sql
  ```

- [ ] **Step 3: Implement `prune_target_features`**

  Add method:

  ```python
  def prune_target_features(
      self,
      *,
      projection_version: str,
      window: str,
      scope: str,
      latest_event_before_ms: int,
      commit: bool = True,
  ) -> int:
      cursor = self.conn.execute(
          """
          DELETE FROM token_radar_target_features
          WHERE projection_version = %s
            AND "window" = %s
            AND scope = %s
            AND latest_event_received_at_ms < %s
          """,
          (projection_version, window, scope, int(latest_event_before_ms)),
      )
      if commit:
          self.conn.commit()
      return int(getattr(cursor, "rowcount", 0) or 0)
  ```

- [ ] **Step 4: Add rank-source edge prune query test**

  Add `test_rank_source_query_prunes_edges_by_projection_window_scope_and_cutoff`.

  Assertions:

  ```python
  assert "DELETE FROM token_radar_rank_source_events" in conn.sql
  assert 'AND "window" = %s' in conn.sql
  assert "AND scope = %s" in conn.sql
  assert "AND event_received_at_ms < %s" in conn.sql
  assert "events " not in conn.sql
  assert "token_intents" not in conn.sql
  ```

- [ ] **Step 5: Implement rank-source prune**

  In `TokenRadarRankSourceQuery`, add:

  ```python
  def prune_edges(
      self,
      *,
      projection_version: str,
      window: str,
      scope: str,
      event_received_before_ms: int,
      commit: bool = True,
  ) -> int:
      cursor = self.conn.execute(
          """
          DELETE FROM token_radar_rank_source_events
          WHERE projection_version = %s
            AND "window" = %s
            AND scope = %s
            AND event_received_at_ms < %s
          """,
          (projection_version, window, scope, int(event_received_before_ms)),
      )
      if commit:
          self.conn.commit()
      return int(getattr(cursor, "rowcount", 0) or 0)
  ```

  In `TokenRadarRankSourceRepository`, delegate with the same signature.

- [ ] **Step 6: Call prune before rank input load**

  In `TokenRadarProjection.refresh_rank_set()` before `_rank_current_rows`:

  ```python
  retention_ms = 3 * int(WINDOW_MS[window])
  retention_cutoff_ms = computed_at_ms - retention_ms
  pruned_features = self.repos.token_radar.prune_target_features(
      projection_version=PROJECTION_VERSION,
      window=window,
      scope=scope,
      latest_event_before_ms=retention_cutoff_ms,
  )
  pruned_edges = self.repos.token_radar_rank_sources.prune_edges(
      projection_version=PROJECTION_VERSION,
      window=window,
      scope=scope,
      event_received_before_ms=retention_cutoff_ms,
  )
  ```

  Include `pruned_features` and `pruned_rank_source_edges` in the returned result map.
  These deletes intentionally commit independently as private-cache cleanup unless the implementation explicitly opens one transaction covering prune, rank input load, and publish.

- [ ] **Step 7: Add service ordering test**

  Add `test_refresh_rank_set_prunes_private_cache_before_loading_rank_inputs`.

  Assertions:

  ```python
  assert recorder.calls[:3] == [
      "prune_target_features",
      "prune_rank_source_edges",
      "list_rank_inputs_for_rank_set",
  ]
  assert recorder.prune_cutoff == now_ms - 3 * WINDOW_MS["5m"]
  ```

- [ ] **Step 8: Verify P1 targeted tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/test_token_radar_repository.py::test_prune_target_features_deletes_only_projection_window_scope_before_cutoff \
    tests/unit/domains/token_intel/test_token_radar_rank_source_query.py::test_rank_source_query_prunes_edges_by_projection_window_scope_and_cutoff \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_prunes_private_cache_before_loading_rank_inputs \
    -q
  ```

---

## Task 4: P2 Macro Current-only Migration

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
- Modify: `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
- Modify: `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Rewrite migration contract tests for hard cut**

  Replace generation expectations with `test_macro_observation_series_contract_is_current_only_after_hard_cut`.

  Required assertions:

  ```python
  assert "generation_id" not in create_or_refresh_sql
  assert "macro_observation_series_active_generation" not in create_or_refresh_sql
  assert "macro_observation_series_generations" not in create_or_refresh_sql
  assert "PRIMARY KEY (projection_version, concept_key, observed_at)" in migration_sql
  ```

- [ ] **Step 2: Create migration with compact replacement**

  Migration requirements:

  ```python
  revision = "20260527_0114"
  down_revision = "20260527_0113"
  ```

  Upgrade shape:

  ```sql
  CREATE TABLE macro_observation_series_rows_compact (
    projection_version TEXT NOT NULL,
    concept_key TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    series_rank INTEGER NOT NULL,
    value_numeric DOUBLE PRECISION NOT NULL,
    source_name TEXT NOT NULL,
    series_key TEXT NOT NULL,
    source_priority INTEGER NOT NULL,
    unit TEXT,
    frequency TEXT,
    data_quality TEXT,
    source_ts TEXT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at_ms BIGINT NOT NULL,
    projected_at_ms BIGINT NOT NULL
  );
  INSERT INTO macro_observation_series_rows_compact (
    projection_version, concept_key, observed_at, series_rank, value_numeric,
    source_name, series_key, source_priority, unit, frequency, data_quality,
    source_ts, raw_payload_json, ingested_at_ms, projected_at_ms
  )
  SELECT rows.projection_version, rows.concept_key, rows.observed_at, rows.series_rank, rows.value_numeric,
         rows.source_name, rows.series_key, rows.source_priority, rows.unit, rows.frequency, rows.data_quality,
         rows.source_ts, rows.raw_payload_json, rows.ingested_at_ms, rows.projected_at_ms
  FROM macro_observation_series_rows AS rows
  JOIN macro_observation_series_active_generation AS active
    ON active.projection_version = rows.projection_version
   AND active.concept_key = rows.concept_key
   AND active.generation_id = rows.generation_id;

  CREATE TABLE macro_observation_series_publication_state (
    projection_version TEXT PRIMARY KEY,
    source_signature TEXT,
    row_count BIGINT NOT NULL DEFAULT 0,
    latest_attempt_status TEXT NOT NULL DEFAULT 'pending',
    latest_attempt_started_at_ms BIGINT,
    latest_attempt_finished_at_ms BIGINT,
    latest_attempt_error TEXT,
    updated_at_ms BIGINT NOT NULL
  );
  ```

  Swap shape inside one short transaction:

  ```sql
  ALTER TABLE macro_observation_series_rows_compact
    ADD CONSTRAINT macro_observation_series_rows_compact_pkey
    PRIMARY KEY (projection_version, concept_key, observed_at);

  CREATE INDEX idx_macro_observation_series_rows_compact_lookup
    ON macro_observation_series_rows_compact(projection_version, concept_key, series_rank, observed_at DESC);

  ALTER TABLE macro_observation_series_rows RENAME TO macro_observation_series_rows_legacy_20260527_0114;
  ALTER TABLE macro_observation_series_rows_compact RENAME TO macro_observation_series_rows;
  DROP TABLE IF EXISTS macro_observation_series_active_generation;
  DROP TABLE IF EXISTS macro_observation_series_generations;
  ```

  Do not create `macro_observation_series_rows_pkey` while the renamed legacy table still owns the old constraint/index name. Either keep compact names until the legacy table is dropped, or explicitly drop/rename the legacy constraint/index before renaming the compact constraint.

  Keep the renamed legacy table only until verification in local/dev. Production rollout may drop it immediately after explicit operator approval to reclaim disk.
  `macro_observation_series_publication_state.source_signature` may be null after migration; the first post-deploy worker run may rewrite the compact rows once, and the second unchanged run must write zero rows.

- [ ] **Step 3: Add migration safety notes**

  In the migration module docstring or comments, state:

  ```text
  Stop macro_view_projection before applying this migration.
  This migration is a hard cut and does not support runtime reads from legacy generations.
  Drop macro_observation_series_rows_legacy_20260527_0114 after verification to reclaim disk.
  ```

- [ ] **Step 4: Verify migration contract tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    -q
  ```

---

## Task 5: P2 Macro Repository Source Signature and Unchanged Skip

**Files:**
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Test: `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
- Test: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

- [ ] **Step 1: Add refresh result type**

  Add near repository imports:

  ```python
  from typing import TypedDict

  class MacroSeriesRefreshResult(TypedDict):
      status: str
      rows_written: int
      source_rows: int
      source_signature: str
  ```

- [ ] **Step 2: Add stable signature helper tests**

  Add `test_macro_series_source_signature_ignores_now_ms`, `test_macro_series_source_signature_ignores_ingested_at_ms`, and `test_macro_series_source_signature_changes_when_value_changes`.

  Assertions:

  ```python
  assert signature_at_t1 == signature_at_t2
  assert signature_with_old_ingest == signature_with_new_ingest
  assert signature_before != signature_after_value_change
  ```

- [ ] **Step 3: Implement deterministic signature helper**

  Add helper:

  ```python
  def _series_source_signature(*, projection_version: str, lookback_days: int, limit_per_series: int, rows: Sequence[Mapping[str, Any]]) -> str:
      stable_rows = [
          {
              "concept_key": str(row.get("concept_key") or ""),
              "observed_at": str(row.get("observed_at") or ""),
              "value_numeric": str(row.get("value_numeric") or ""),
              "source_name": str(row.get("source_name") or ""),
              "series_key": str(row.get("series_key") or ""),
              "source_priority": int(row.get("source_priority") or 0),
              "unit": row.get("unit"),
              "frequency": row.get("frequency"),
              "data_quality": str(row.get("data_quality") or ""),
              "source_ts": str(row.get("source_ts") or ""),
          }
          for row in rows
      ]
      stable_rows.sort(key=lambda item: (item["concept_key"], item["observed_at"], item["source_name"], item["series_key"]))
      payload = {
          "projection_version": projection_version,
          "lookback_days": int(lookback_days),
          "limit_per_series": int(limit_per_series),
          "rows": stable_rows,
      }
      return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
  ```

  Add `import json` if missing.
  Do not include `now_ms`, UUIDs, `projected_at_ms`, or `ingested_at_ms` in the signature payload.

- [ ] **Step 4: Replace generation refresh with current-only refresh**

  Change `refresh_observation_series_rows` to return `MacroSeriesRefreshResult`.

  Query selected rows with the existing `source_ranked` and `series_ranked`
  logic, but stage them as rows to insert into current table without
  `generation_id`.

  Required control flow:

  ```python
  selected_rows = self._select_observation_series_rows(
      projection_version=projection_version,
      lookback_days=bounded_lookback_days,
      limit_per_series=bounded_limit_per_series,
  )
  source_signature = _series_source_signature(
      projection_version=projection_version,
      lookback_days=bounded_lookback_days,
      limit_per_series=bounded_limit_per_series,
      rows=selected_rows,
  )
  current_state = self._macro_series_publication_state(projection_version)
  if current_state and current_state.get("source_signature") == source_signature:
      self._upsert_macro_series_publication_state(
          projection_version=projection_version,
          status="unchanged",
          source_signature=source_signature,
          row_count=len(selected_rows),
          started_at_ms=int(now_ms),
          finished_at_ms=int(now_ms),
          latest_attempt_error=None,
      )
      return {"status": "unchanged", "rows_written": 0, "source_rows": len(selected_rows), "source_signature": source_signature}
  if not selected_rows:
      self._upsert_macro_series_publication_state(
          projection_version=projection_version,
          status="failed",
          source_signature=source_signature,
          row_count=0,
          started_at_ms=int(now_ms),
          finished_at_ms=int(now_ms),
          latest_attempt_error="macro_observation_series_empty",
      )
      raise RuntimeError("macro_observation_series_empty")
  with _transaction_context(self.conn):
      DELETE current rows for projection_version
      INSERT selected rows
      upsert publication state status="published"
  ```

  Do not call `_generation_id`.
  Do not write `macro_observation_series_generations`.
  Do not write `macro_observation_series_active_generation`.

- [ ] **Step 5: Add unchanged no-write repository test**

  Add `test_refresh_observation_series_rows_skips_writes_when_source_signature_unchanged`.

  Assertions:

  ```python
  assert result["status"] == "unchanged"
  assert result["rows_written"] == 0
  assert "INSERT INTO macro_observation_series_rows" not in second_run_queries
  assert "DELETE FROM macro_observation_series_rows" not in second_run_queries
  ```

- [ ] **Step 6: Add changed replacement test**

  Add `test_refresh_observation_series_rows_replaces_current_rows_when_signature_changes`.

  Assertions:

  ```python
  assert "DELETE FROM macro_observation_series_rows" in queries
  assert "INSERT INTO macro_observation_series_rows" in queries
  assert "generation_id" not in queries
  assert result["status"] == "published"
  ```

- [ ] **Step 7: Verify Task 5 tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    -q
  ```

---

## Task 6: P2 Macro Current Read Paths and Worker Notes

**Files:**
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Modify: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Modify: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- Test: `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`
- Test: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
- Test: `tests/unit/domains/macro_intel/test_macro_feature_engine.py`
- Test: `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- Test: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Remove active-generation joins from current readers**

  Update:

  ```text
  latest_observations
  observations_for_concepts
  concept_history_counts
  ```

  Each query reads:

  ```sql
  FROM macro_observation_series_rows AS rows
  WHERE rows.projection_version = %s
  ```

  No query may contain:

  ```text
  macro_observation_series_active_generation
  active.generation_id = rows.generation_id
  rows.generation_id
  ```

- [ ] **Step 2: Update reader contract tests**

  Replace tests that require active-generation joins with tests that reject them:

  ```python
  assert "macro_observation_series_active_generation" not in query
  assert "generation_id" not in query
  assert "FROM macro_observation_series_rows AS rows" in query
  ```

- [ ] **Step 3: Update worker refresh result handling**

  In `MacroViewProjectionWorker.run_once_sync()`:

  ```python
  refresh_result = repos.macro_intel.refresh_observation_series_rows(
      projection_version=MACRO_VIEW_PROJECTION_VERSION,
      now_ms=now,
      lookback_days=self._lookback_days(),
      limit_per_series=self._limit_per_series(),
  )
  projected_rows_written = int(refresh_result.get("rows_written") or 0)
  series_status = str(refresh_result.get("status") or "")
  source_signature = str(refresh_result.get("source_signature") or "")
  ```

  Worker notes include:

  ```python
  "series_status": series_status,
  "source_signature": source_signature,
  "projected_rows_written": projected_rows_written,
  ```

- [ ] **Step 4: Update worker test**

  Update `test_macro_view_projection_worker_writes_latest_snapshot()` so fake repo returns:

  ```python
  {
      "status": "published",
      "rows_written": 3,
      "source_rows": 3,
      "source_signature": "sig-a",
  }
  ```

  Assertions:

  ```python
  assert result.notes["series_status"] == "published"
  assert result.notes["projected_rows_written"] == 3
  assert result.notes["source_signature"] == "sig-a"
  ```

- [ ] **Step 5: Update manifest, feature tests, and domain architecture**

  Update `worker_manifest.py` so `macro_view_projection` no longer declares writes to `macro_observation_series_active_generation` or `macro_observation_series_generations`, and no input contract depends on active generation. Update domain architecture docs to say Macro projected series is current-only/source-signature based.

  Replace any Macro feature-engine test assertion that requires active-generation joins with a direct current-row contract.

- [ ] **Step 6: Verify Task 6 tests**

  Run:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    tests/unit/domains/macro_intel/test_macro_feature_engine.py \
    tests/architecture/test_runtime_performance_architecture_hard_cut.py \
    tests/architecture/test_worker_runtime_contracts.py \
    -q
  ```

---

## Task 7: Docs, Guards, and No-compatibility Scans

**Files:**
- Modify: `docs/WORKERS.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- Modify: `tests/architecture/test_token_radar_publication_state_hard_cut.py`

- [ ] **Step 1: Update docs**

  Document:

  ```text
  Token Radar current publication requires window-eligible rank inputs.
  Token Radar private caches are pruned by the projection owner.
  Macro observation series rows are current-only; unchanged source signatures skip rewrites.
  Old macro physical generations are not a runtime contract.
  ```

- [ ] **Step 2: Add no-compatibility AST guards and supplemental scan**

  Add architecture tests that parse Python AST for:

  ```text
  list_rank_inputs_for_rank_set calls without min_latest_event_received_at_ms
  runtime Macro calls to _generation_id
  runtime Macro reader SQL referencing macro_observation_series_active_generation
  worker_manifest declaring Macro active-generation tables as read-model outputs
  ```

  The `rg` scan is supplemental and must also pass:

  ```bash
  rg -n "macro_observation_series_active_generation|macro_observation_series_generations|generation_id = rows.generation_id|_generation_id\\(|list_rank_inputs_for_rank_set\\([^)]*scope=scope\\s*\\)" \
    src/parallax/domains src/parallax/app tests
  ```

  Expected after implementation: no runtime matches for old Macro generation tables or no-cutoff rank input calls. Migration files may mention old Macro table names only for hard-cut table swap/drop.

- [ ] **Step 3: Verify docs and guards**

  Run:

  ```bash
  uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py -q
  uv run ruff check .
  ```

---

## Root-cause Position

Macro 严重卡顿的根因是本地 read-model 设计和实现偏离规范，不是 PostgreSQL 调参问题，也不是 Kappa/CQRS 模式本身的问题。

- `macro_view_projection` 每轮刷新都会生成新的 timestamp/UUID generation，并全量插入 `macro_observation_series_rows`。
- API 只通过 active pointer 读取最新 generation，因此 serving 面看起来很小，但物理表、索引、vacuum、temp IO 随 worker run count 膨胀。
- cleanup 只删有限批次 superseded generation rows，无法追上持续全量复制。
- 这违反了项目规范里的 compact/current/rebuildable read-model 生命周期：derived read model 可以重建，但不能无界保存每次投影副本。
- 规范没有被遵循的原因不是缺少单 writer，而是把“generation swap”当成了长期 runtime storage contract；`src/parallax/domains/macro_intel/ARCHITECTURE.md` 和 worker manifest 还把旧 active-generation contract 固化进文档/测试，导致实现回归没有被 guard 住。

本方案的 P2 因此必须删除 runtime physical generation 模型，而不是只加 retention 或调大 cleanup batch。

## Cross-worker Review Findings

这些发现不应静默塞进本 plan 的实现范围，但需要记录为后续 hard-cut 候选：

| Priority | Area | Finding | Recommended follow-up |
| --- | --- | --- | --- |
| P1 | `event_anchor_backfill` | `list_due` 后直接 provider IO，没有 claim/lease 或 advisory lock；多进程会重复外部 IO 和 attach attempts。 | 单独做 worker claim/lease hard cut，provider IO 前必须持有 bounded claim。 |
| P1 | `cex_oi_radar_board` | 每轮新 `run_id` 全量写 board rows，reader 只读 latest run，当前没有 retention/active lifecycle 控制，存在 Macro 同类 bloat 风险。 | 单独做 CEX board current-only 或 bounded-retention spec。 |
| P2 | Token case/search | API 在 DB `latest_market_tick` 缺失时 fallback 到 `LivePriceGateway` 进程内 `_cache`，绕过 durable current model。 | 单独删除 in-memory serving fallback，统一读 `market_tick_current`/durable tick。 |
| P2 | `news_page_projection` | 已有 `payload_hash`/`source_watermark` columns，但 replace path 仍 delete+unconditional upsert，hash guard 未使用。 | 单独补 source signature/unchanged skip，降低 repeated dirty target 写放大。 |
| P3 | News source status API | `/news/sources/status` 有 private `_registry` fallback。 | 清理私有属性 fallback，改成显式 public provider status contract。 |
| P3 | Worker manifest | `raw_frames` 被标为 facts，但项目规范说 provider raw frames 是 inputs, not facts。 | 调整 manifest terminology，避免后续把 raw frames 当业务真相。 |

当前 plan 保持 scope：Token Radar P0/P1 + Macro P2。上表问题进入后续 specs，避免本轮同时改太多 worker surface。

---

## PR Breakdown

1. **PR 1 - Token Radar window correctness**
   - Owns Tasks 1-2.
   - Mergeable independently.
   - Proves AC1, AC2, AC3, and part of AC9.

2. **PR 2 - Token Radar private cache retention**
   - Owns Task 3.
   - Depends on PR 1 because prune happens before cutoff-filtered rank input.
   - Proves AC4 and AC5 for Token Radar cache.

3. **PR 3 - Macro current-only projection**
   - Owns Tasks 4-7.
   - Can be developed in the same branch but should be reviewed as the largest risk slice.
   - Proves AC6, AC7, AC8, and remaining AC9.

## Rollout Order

1. Deploy PR 1 and restart Token Radar worker.
2. Verify zero stale current rows:

   ```sql
   WITH win(win_window, window_ms) AS (
     VALUES ('5m',300000::bigint),('1h',3600000),('4h',14400000),('24h',86400000)
   ),
   s AS (
     SELECT state.*, win.window_ms
     FROM token_radar_publication_state state
     JOIN win ON win.win_window = state."window"
   )
   SELECT s."window", s.scope, COUNT(r.*) AS rows,
          COUNT(*) FILTER (
            WHERE r.source_max_received_at_ms < s.current_published_at_ms - s.window_ms
          ) AS stale_rows
   FROM s
   LEFT JOIN token_radar_current_rows r
     ON r.projection_version=s.projection_version
    AND r."window"=s."window"
    AND r.scope=s.scope
    AND r.generation_id=s.current_generation_id
   GROUP BY s."window", s.scope
   ORDER BY s."window", s.scope;
   ```

   Expected: `stale_rows = 0` for every row.

3. Deploy PR 2 and run one full Token Radar window cycle.
4. Verify private cache retention:

   ```sql
   WITH now_ms AS (SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint AS value),
   window_ms(wname, ms) AS (
     VALUES ('5m',300000::bigint),('1h',3600000),('4h',14400000),('24h',86400000)
   )
   SELECT f."window", f.scope, count(*) AS rows,
          count(*) FILTER (WHERE f.latest_event_received_at_ms < n.value - 3*w.ms) AS older_than_retention
   FROM token_radar_target_features f
   JOIN window_ms w ON w.wname = f."window"
   CROSS JOIN now_ms n
   GROUP BY f."window", f.scope
   ORDER BY f."window", f.scope;
   ```

   Expected: old rows trend to zero after each window/scope refreshes.

5. Stop or pause `macro_view_projection`.
6. Apply migration `20260527_0114`.
7. Deploy Macro code.
8. Restart `macro_view_projection`.
9. Verify Macro compactness and unchanged skip:

   ```sql
   SELECT pg_size_pretty(pg_total_relation_size('macro_observation_series_rows'));

   SELECT count(*) AS rows,
          count(DISTINCT concept_key) AS concepts
   FROM macro_observation_series_rows
   WHERE projection_version = 'macro_regime_v4';

   SELECT concept_key, count(*) AS rows
   FROM macro_observation_series_rows
   WHERE projection_version = 'macro_regime_v4'
   GROUP BY concept_key
   HAVING count(*) > 250;

   SELECT to_regclass('macro_observation_series_active_generation') AS active_generation_table,
          to_regclass('macro_observation_series_generations') AS generations_table;

   SELECT column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_name = 'macro_observation_series_rows'
     AND column_name IN ('observed_at', 'value_numeric', 'data_quality')
   ORDER BY column_name;

   SELECT latest_attempt_status, row_count, source_signature IS NOT NULL AS has_source_signature
   FROM macro_observation_series_publication_state
   WHERE projection_version = 'macro_regime_v4';
   ```

   Expected: no concept has more than `limit_per_series` rows; generation tables are absent; `observed_at` remains `timestamp with time zone`; publication state exists after the first run.

10. After API verification, drop legacy Macro table if migration kept it:

    ```sql
    DROP TABLE IF EXISTS macro_observation_series_rows_legacy_20260527_0114;
    VACUUM (ANALYZE) macro_observation_series_rows;
    ```

## Rollback

- **PR 1 rollback:** Revert code if rank input cutoff causes a severe product issue. This may reintroduce stale current rows, so rollback requires a visible incident note and a follow-up fix. No schema rollback needed.
- **PR 2 rollback:** Revert prune calls and repository prune methods. Cache rows already pruned are rebuildable through Token Radar projection; no facts are lost.
- **PR 3 rollback before dropping legacy table:** Stop Macro worker, rename `macro_observation_series_rows_legacy_20260527_0114` back to `macro_observation_series_rows`, restore active-generation/generation tables only if they were kept by the migration rollback path, and redeploy previous Macro code.
- **PR 3 rollback after dropping legacy table:** Do not attempt to restore physical generations. Rebuild compact `macro_observation_series_rows` from `macro_observations` and keep current-only code. This is a hard-cut irreversible storage cleanup.

## Acceptance Test Commands

- AC1-AC3:

  ```bash
  uv run pytest \
    tests/unit/test_token_radar_repository.py::test_list_rank_inputs_for_rank_set_filters_by_latest_event_cutoff \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_excludes_expired_target_features_without_dirty_claims \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_publishes_empty_ready_generation_when_no_features_are_window_fresh \
    -q
  ```

- AC4-AC5:

  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/test_token_radar_repository.py::test_prune_target_features_deletes_only_projection_window_scope_before_cutoff \
    tests/unit/domains/token_intel/test_token_radar_rank_source_query.py::test_rank_source_query_prunes_edges_by_projection_window_scope_and_cutoff \
    tests/unit/test_token_radar_projection.py::test_refresh_rank_set_prunes_private_cache_before_loading_rank_inputs \
    -q
  ```

- AC6-AC8:

  ```bash
  uv run pytest \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_feature_engine.py \
    tests/architecture/test_runtime_performance_architecture_hard_cut.py \
    tests/architecture/test_worker_runtime_contracts.py \
    -q
  ```

- AC9 and lint:

  ```bash
  uv run ruff check .
  rg -n "macro_observation_series_active_generation|macro_observation_series_generations|_generation_id\\(|legacy fallback|compat" \
    src/parallax/app src/parallax/domains tests
  ```

  Expected: no runtime compatibility matches. Migration files may mention dropped old tables only for hard-cut migration.

- Full focused suite:

  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/test_token_radar_repository.py \
    tests/unit/test_token_radar_projection.py \
    tests/unit/test_token_radar_projection_worker.py \
    tests/unit/domains/token_intel/test_token_radar_rank_source_query.py \
    tests/architecture/test_token_radar_publication_state_hard_cut.py \
    tests/unit/domains/macro_intel/test_macro_generation_swap.py \
    tests/unit/domains/macro_intel/test_macro_migration_contract.py \
    tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
    tests/unit/domains/macro_intel/test_macro_feature_engine.py \
    tests/architecture/test_runtime_performance_architecture_hard_cut.py \
    tests/architecture/test_worker_runtime_contracts.py \
    -q
  ```

## Verification Artefact

Before declaring implementation complete, create:

- `docs/superpowers/plans/active/2026-05-27-runtime-db-performance-hard-cut-verification-cn.md`

It must include:

- full command output for focused pytest and `uv run ruff check .`;
- migration output for `uv run alembic upgrade head`;
- Token Radar stale-current-row SQL results;
- Token Radar cache retention SQL results;
- Macro compactness SQL results;
- `pg_stat_statements` sample proving unchanged Macro steady runs no longer execute the old multi-second generation insert pattern;
- remaining risks and any operator action still pending, especially dropping the legacy Macro table if retained for rollback.
