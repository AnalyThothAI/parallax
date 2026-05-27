# Token Radar KISS Publication State Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Token Radar 在线服务收敛为 `token_radar_current_rows` + `token_radar_publication_state`，删除 hydration retry、audit/history hot path、fallback reader 和 dirty payload-hash claim 编码。

**Architecture:** Kappa/CQRS：material facts 是唯一业务真相；Token Radar projection 只发布可重建 read model。每个 `(projection_version, window, scope)` 构建一个 in-memory generation，并在单事务内 replace current rows + 写 publication state ready；失败只更新 publication state 的 latest attempt，不修改上一版 current rows。

**Tech Stack:** Python 3.13, psycopg 3, PostgreSQL 18, Alembic, FastAPI, pytest, ruff.

---

## Owning Spec

- Spec: `docs/superpowers/specs/active/2026-05-27-token-radar-kiss-current-row-hard-cut-cn.md`

## First-Principles Simplification

The previous plan still carried extra coordination:

- `side_effect_status` inside coverage mixed freshness with audit/downstream failures.
- `rank_history` and `snapshot_audit` stayed in the publish path even though online serving does not need them.
- `row_set_hash` added diagnostics but not correctness.
- current publish still needed to reason about downstream dirty enqueue rollback.

This plan removes those layers:

- `token_radar_current_rows` answers: “what rows can be served?”
- `token_radar_publication_state` answers: “is the served generation fresh, stale, failed, or pending?”
- `token_radar_rank_source_events` is projection input and lazy evidence only.
- `token_radar_target_features` is projection-private cache only.
- `rank_history` and `snapshot_audit` are removed from runtime hot path.

## Systemic Cleanup Test Targets

The hard cut is not complete until these scans and tests pass:

- No runtime source in `src/gmgn_twitter_intel/app` or
  `src/gmgn_twitter_intel/domains` contains:
  `token_radar_projection_coverage`, `token_radar_rank_history`,
  `token_radar_snapshot_audit`, `payload_hash changed during selected-row hydration`,
  `_rank_and_hydrate_selected_rows`, `_hydrate_ranked_rows`,
  `load_target_feature_payloads_for_ranked_keys`, `rebuild_rank_inputs_full`,
  `list_rank_input_rebuild_keys`, `stale_rank_input_count`,
  `rank_input_readiness_for_work_items`, `latest_snapshot_audit_rows`,
  `side_effect_status`, or `:claimed:`.
- Schema tests prove `token_radar_publication_state` exists and
  `token_radar_projection_coverage`, `token_radar_rank_history`, and
  `token_radar_snapshot_audit` do not exist at runtime.
- Unit tests prove build failure and publish failure both mark publication state
  `failed` while preserving the last successful current generation.
- API/read-model tests prove failed publication state is never surfaced as
  `fresh`.
- Consumer tests prove Pulse, notifications, narrative admission, asset registry,
  and runtime repair only act on ready publication generations.
- Factor evaluation tests prove no runtime path reads `token_radar_snapshot_audit`.
- Dirty queue tests prove source fingerprints are stable and lease/claim state is
  not encoded into payload hashes.

## Target Data Flow

```text
material facts
  -> rank source edges / private target feature cache
  -> build one publication generation in memory
  -> transaction:
       delete old current rows for window/scope
       insert new current rows with one generation_id
       upsert publication_state ready
  -> commit
  -> wake hint only
```

Failure path:

```text
build/publish error
  -> leave current rows unchanged
  -> upsert publication_state failed with latest_attempt_error
  -> API exposes stale or failed
```

## File Structure

### Schema

- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py`
  - Drop `token_radar_projection_coverage` and create `token_radar_publication_state`.
  - Add generation columns to `token_radar_current_rows`.
  - Drop `token_radar_rank_history` and `token_radar_snapshot_audit`.
  - Clear rebuildable current/state rows for hard cut.

### Repository / Projection

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
  - Add `publish_current_generation(...)`.
  - Add `mark_publication_failed(...)`.
  - Add `latest_publication_state(...)`.
  - Delete `publish_rows(...)`, `latest_snapshot_audit_rows(...)`, hydration-by-payload methods, stale rank input rebuild helpers.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
  - Replace rank-then-hydrate with one generation builder.
  - Publish due work items even when no dirty target was claimed.
  - Do not write rank history or snapshot audit.

- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
  - Treat failed/missing/stale publication state as due work.
  - Wake after successful current publish only.

### Read Paths

- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
  - Read publication state, not coverage.
  - Return `fresh` only for matching ready generation.
  - Return `stale` or `failed` for latest failed attempts.

- Modify consumers:
  - `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - `src/gmgn_twitter_intel/domains/pulse_lab/queries/pulse_policy_evaluator.py`
  - `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
  - `src/gmgn_twitter_intel/app/runtime/runtime_worker_dirty_targets.py`
  - `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
  - `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
  - `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`

### Dirty Queue / Evidence / Docs

- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
  - Remove `:claimed:` payload hash mutation.

- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`
  - Remove the same `:claimed:` payload hash mutation pattern so the repo-wide
    guard is honest.

- Modify:
  - `src/gmgn_twitter_intel/app/runtime/token_radar_postgres_hard_reset.py`
  - `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
  - Remove old coverage/history/audit reset and ownership entries.

- Modify:
  - `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
  - `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
  - Add bounded lazy evidence query.

- Modify docs:
  - `docs/CONTRACTS.md`
  - `docs/WORKERS.md`
  - `docs/RELIABILITY.md`
  - `docs/references/POSTGRES_PERFORMANCE.md`
  - `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

---

## Task 0: Legacy Surface Inventory Lock

**Files:**
- No production file edits in this task.
- Use the inventory below to drive Tasks 1-8.

- [ ] **Step 1: Run the legacy surface scan**

Run:

```bash
rg -n "payload_hash changed during selected-row hydration|_rank_and_hydrate_selected_rows|_hydrate_ranked_rows|_patch_hydrated_rank_row|load_target_feature_payloads_for_ranked_keys|rebuild_rank_inputs_full|list_rank_input_rebuild_keys|stale_rank_input_count|rank_input_readiness_for_work_items|latest_snapshot_audit_rows|token_radar_projection_coverage|token_radar_rank_history|token_radar_snapshot_audit|:claimed:" src/gmgn_twitter_intel/app src/gmgn_twitter_intel/domains tests
```

Expected before implementation: matches exist in the current codebase. They are
the cleanup scope, not acceptable leftovers.

- [ ] **Step 2: Classify every match into one removal bucket**

Use this exact bucket list:

```text
projection-hydration-retry:
  src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py
  tests/unit/test_token_radar_projection.py
  tests/unit/test_token_radar_repository.py

legacy-rank-input-rebuild:
  src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py
  src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py
  src/gmgn_twitter_intel/app/surfaces/cli/parser.py
  tests/unit/test_token_radar_projection.py
  tests/unit/test_token_radar_repository.py
  tests/integration/test_cli.py

coverage-to-publication-state:
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py
  src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py
  src/gmgn_twitter_intel/domains/pulse_lab/queries/pulse_policy_evaluator.py
  src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py
  src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py
  src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py
  src/gmgn_twitter_intel/app/runtime/runtime_worker_dirty_targets.py
  src/gmgn_twitter_intel/app/runtime/token_radar_postgres_hard_reset.py
  src/gmgn_twitter_intel/app/runtime/worker_manifest.py
  tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py
  tests/unit/test_asset_flow_service.py
  tests/unit/test_token_capture_tier_worker.py
  tests/integration/test_worker_missed_wake_recovery.py
  tests/integration/test_narrative_repository.py
  tests/integration/test_narrative_admission_dirty_targets.py
  tests/integration/test_pulse_candidate_dirty_triggers.py

audit-history-drop:
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py
  src/gmgn_twitter_intel/app/runtime/token_radar_postgres_hard_reset.py
  src/gmgn_twitter_intel/app/runtime/worker_manifest.py
  src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md
  tests/unit/test_token_factor_evaluation.py
  tests/unit/domains/token_intel/test_token_radar_postgres_hard_reset.py
  tests/integration/test_postgres_schema_runtime.py
  tests/integration/test_token_radar_repository.py
  tests/unit/test_postgres_schema.py
  tests/unit/test_token_radar_repository.py

dirty-claim-hash:
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py
  src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py
  tests/unit/test_token_radar_dirty_target_repository.py
  tests/unit/test_ingest_service_token_radar_dirty_targets.py
```

- [ ] **Step 3: Use this pass/fail rule for every implementation task**

After each task, rerun the scan from Step 1. A task is complete only when every
remaining match is either:

```text
1. in a historical Alembic migration under src/gmgn_twitter_intel/platform/db/alembic/versions,
2. in the active spec or plan docs,
3. in a test that is intentionally asserting the string is absent,
4. in a later bucket that has not started yet.
```

Do not add allowlists for runtime fallback paths.

- [ ] **Step 4: Final target**

By Task 8, this command must return no matches in runtime code:

```bash
rg -n "payload_hash changed during selected-row hydration|_rank_and_hydrate_selected_rows|_hydrate_ranked_rows|_patch_hydrated_rank_row|load_target_feature_payloads_for_ranked_keys|rebuild_rank_inputs_full|list_rank_input_rebuild_keys|stale_rank_input_count|rank_input_readiness_for_work_items|latest_snapshot_audit_rows|token_radar_projection_coverage|token_radar_rank_history|token_radar_snapshot_audit|side_effect_status|:claimed:" src/gmgn_twitter_intel/app src/gmgn_twitter_intel/domains
```

Expected after implementation: no output.

This inventory task has no commit; it is an execution gate for the hard cut.

## Task 1: Schema Hard Cut To Publication State

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1: Write failing schema unit test**

Add to `tests/unit/test_postgres_schema.py`:

```python
def test_token_radar_publication_state_hard_cut_migration_contract() -> None:
    text = _read_migration("20260527_0111_token_radar_publication_state.py")

    assert "token_radar_publication_state" in text
    assert "DROP TABLE IF EXISTS token_radar_projection_coverage" in text
    assert "DROP TABLE IF EXISTS token_radar_rank_history" in text
    assert "DROP TABLE IF EXISTS token_radar_snapshot_audit" in text
    assert "DELETE FROM token_radar_current_rows" in text
    assert "generation_id TEXT" in text
    assert "published_at_ms BIGINT" in text
    assert "source_frontier_ms BIGINT" in text
    assert "current_generation_id TEXT" in text
    assert "latest_attempt_status TEXT" in text
    assert "side_effect_status" not in text
    assert "row_set_hash" not in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_token_radar_publication_state_hard_cut_migration_contract -q
```

Expected: FAIL because the migration does not exist.

- [ ] **Step 3: Create hard-cut migration**

Create `src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py`:

```python
"""Token Radar publication state hard cut."""

from __future__ import annotations

from alembic import op

revision = "20260527_0111"
down_revision = "20260526_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM token_radar_current_rows")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_history CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_snapshot_audit CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_publication_state CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_projection_coverage CASCADE")
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
          ADD COLUMN IF NOT EXISTS generation_id TEXT,
          ADD COLUMN IF NOT EXISTS published_at_ms BIGINT,
          ADD COLUMN IF NOT EXISTS source_frontier_ms BIGINT
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
          ALTER COLUMN generation_id SET NOT NULL,
          ALTER COLUMN published_at_ms SET NOT NULL,
          ALTER COLUMN source_frontier_ms SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE token_radar_publication_state (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          current_generation_id TEXT,
          current_published_at_ms BIGINT,
          current_source_frontier_ms BIGINT,
          current_row_count BIGINT NOT NULL DEFAULT 0,
          current_source_rows BIGINT NOT NULL DEFAULT 0,
          latest_attempt_generation_id TEXT,
          latest_attempt_status TEXT NOT NULL CHECK (latest_attempt_status IN ('ready', 'failed')),
          latest_attempt_started_at_ms BIGINT,
          latest_attempt_finished_at_ms BIGINT,
          latest_attempt_error TEXT,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope),
          CHECK (
            latest_attempt_status = 'failed'
            OR current_generation_id = latest_attempt_generation_id
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_generation
          ON token_radar_current_rows(projection_version, "window", scope, generation_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_publication_state_current
          ON token_radar_publication_state(projection_version, "window", scope, current_generation_id)
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260527_0111 token-radar publication-state hard cut is not safely reversible; "
        "restore a pre-migration backup if rollback is required."
    )
```

- [ ] **Step 4: Add runtime schema integration test**

Add to `tests/integration/test_postgres_schema_runtime.py`:

```python
def test_token_radar_publication_state_schema(postgres_conn) -> None:
    columns = _columns_by_table(postgres_conn)

    assert "generation_id" in columns["token_radar_current_rows"]
    assert "published_at_ms" in columns["token_radar_current_rows"]
    assert "source_frontier_ms" in columns["token_radar_current_rows"]
    assert "token_radar_publication_state" in columns
    assert "current_generation_id" in columns["token_radar_publication_state"]
    assert "latest_attempt_status" in columns["token_radar_publication_state"]
    assert "latest_attempt_error" in columns["token_radar_publication_state"]
    assert "token_radar_projection_coverage" not in columns
    assert "token_radar_rank_history" not in columns
    assert "token_radar_snapshot_audit" not in columns
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_token_radar_publication_state_hard_cut_migration_contract tests/integration/test_postgres_schema_runtime.py::test_token_radar_publication_state_schema -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py
git commit -m "schema: hard cut token radar publication state"
```

## Task 2: Repository Publish State API

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 1: Write failing unit test for atomic publish**

Add to `tests/unit/test_token_radar_repository.py`:

```python
def test_publish_current_generation_replaces_rows_and_marks_state_ready() -> None:
    conn = FakePublishConn()
    row = _valid_factor_row()

    published = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        generation_id="gen-1",
        computed_at_ms=1_778_000_000_000,
        source_frontier_ms=1_777_999_990_000,
        rows=[row],
        commit=False,
    )

    sql = "\n".join(conn.sqls)
    assert published is True
    assert "DELETE FROM token_radar_current_rows" in sql
    assert "INSERT INTO token_radar_current_rows" in sql
    assert "INSERT INTO token_radar_publication_state" in sql
    assert "token_radar_rank_history" not in sql
    assert "token_radar_snapshot_audit" not in sql
    assert conn.state_params["latest_attempt_status"] == "ready"
    assert conn.state_params["current_generation_id"] == "gen-1"
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py::test_publish_current_generation_replaces_rows_and_marks_state_ready -q
```

Expected: FAIL because `publish_current_generation` does not exist.

- [ ] **Step 3: Replace `publish_rows` with `publish_current_generation`**

In `TokenRadarRepository`, delete `publish_rows(...)` and add:

```python
def publish_current_generation(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    generation_id: str,
    computed_at_ms: int,
    source_frontier_ms: int,
    rows: list[dict[str, Any]],
    commit: bool = True,
) -> bool:
    self.conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
        (projection_version, f"{window}:{scope}"),
    )
    latest = self.conn.execute(
        """
        SELECT current_published_at_ms
        FROM token_radar_publication_state
        WHERE projection_version = %s AND "window" = %s AND scope = %s
        """,
        (projection_version, window, scope),
    ).fetchone()
    latest_ms = int(latest["current_published_at_ms"]) if latest and latest.get("current_published_at_ms") else None
    if latest_ms is not None and latest_ms > int(computed_at_ms):
        if commit:
            self.conn.commit()
        return False

    for row in rows:
        _validate_factor_contract(row)
    listed_at_by_key = self.first_seen_by_identity(
        projection_version=projection_version,
        window=window,
        scope=scope,
        rows=rows,
    )
    runtime_rows = [
        {
            **_runtime_row_payload(
                row,
                projection_version=projection_version,
                window=window,
                scope=scope,
                computed_at_ms=int(computed_at_ms),
                listed_at_ms=listed_at_by_key.get(_identity_key(row), int(computed_at_ms)),
            ),
            "generation_id": str(generation_id),
            "published_at_ms": int(computed_at_ms),
            "source_frontier_ms": int(source_frontier_ms),
        }
        for row in rows
    ]

    self.conn.execute(
        """
        DELETE FROM token_radar_current_rows
        WHERE projection_version = %s AND "window" = %s AND scope = %s
        """,
        (projection_version, window, scope),
    )
    for row in runtime_rows:
        self.conn.execute(
            f"""
            INSERT INTO token_radar_current_rows(
              {RADAR_ROW_INSERT_COLUMNS_SQL}, generation_id, published_at_ms, source_frontier_ms
            )
            VALUES ({RADAR_ROW_INSERT_VALUES_SQL}, %(generation_id)s, %(published_at_ms)s, %(source_frontier_ms)s)
            """,
            _json_payload(row),
        )
    self.upsert_first_seen_batch(
        projection_version=projection_version,
        window=window,
        scope=scope,
        rows=runtime_rows,
        computed_at_ms=int(computed_at_ms),
        commit=False,
    )
    self.conn.execute(
        """
        INSERT INTO token_radar_publication_state(
          projection_version, "window", scope,
          current_generation_id, current_published_at_ms, current_source_frontier_ms,
          current_row_count, current_source_rows,
          latest_attempt_generation_id, latest_attempt_status,
          latest_attempt_started_at_ms, latest_attempt_finished_at_ms,
          latest_attempt_error, updated_at_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ready', %s, %s, NULL, %s)
        ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
          current_generation_id = excluded.current_generation_id,
          current_published_at_ms = excluded.current_published_at_ms,
          current_source_frontier_ms = excluded.current_source_frontier_ms,
          current_row_count = excluded.current_row_count,
          current_source_rows = excluded.current_source_rows,
          latest_attempt_generation_id = excluded.latest_attempt_generation_id,
          latest_attempt_status = excluded.latest_attempt_status,
          latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
          latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
          latest_attempt_error = NULL,
          updated_at_ms = excluded.updated_at_ms
        """,
        (
            projection_version,
            window,
            scope,
            str(generation_id),
            int(computed_at_ms),
            int(source_frontier_ms),
            len(runtime_rows),
            len(runtime_rows),
            str(generation_id),
            int(computed_at_ms),
            int(computed_at_ms),
            _now_ms(),
        ),
    )
    if commit:
        self.conn.commit()
    return True
```

Extend `RADAR_ROW_INSERT_COLUMNS_SQL` / JSON payload handling to include the new columns only in this insert call, not in old shared column constants if the helper is used by migration tests.

- [ ] **Step 4: Add failed attempt writer**

Add:

```python
def mark_publication_failed(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    generation_id: str,
    started_at_ms: int,
    finished_at_ms: int,
    error: str,
    commit: bool = True,
) -> None:
    bounded_error = str(error)[:2_000]
    self.conn.execute(
        """
        INSERT INTO token_radar_publication_state(
          projection_version, "window", scope,
          current_generation_id, current_published_at_ms, current_source_frontier_ms,
          current_row_count, current_source_rows,
          latest_attempt_generation_id, latest_attempt_status,
          latest_attempt_started_at_ms, latest_attempt_finished_at_ms,
          latest_attempt_error, updated_at_ms
        )
        VALUES (%s, %s, %s, NULL, NULL, NULL, 0, 0, %s, 'failed', %s, %s, %s, %s)
        ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
          latest_attempt_generation_id = excluded.latest_attempt_generation_id,
          latest_attempt_status = 'failed',
          latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
          latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
          latest_attempt_error = excluded.latest_attempt_error,
          updated_at_ms = excluded.updated_at_ms
        """,
        (
            projection_version,
            window,
            scope,
            str(generation_id),
            int(started_at_ms),
            int(finished_at_ms),
            bounded_error,
            _now_ms(),
        ),
    )
    if commit:
        self.conn.commit()
```

- [ ] **Step 5: Replace coverage reader with publication state reader**

Delete `latest_coverage(...)` and add:

```python
def latest_publication_state(
    self,
    *,
    projection_version: str,
    windows: tuple[str, ...],
    scopes: tuple[str, ...],
) -> dict[tuple[str, str], dict[str, Any]]:
    requested = [(window, scope) for window in windows for scope in scopes]
    if not requested:
        return {}
    values_sql = ",".join(["(%s, %s)"] * len(requested))
    params: list[Any] = []
    for window, scope in requested:
        params.extend([window, scope])
    rows = self.conn.execute(
        f"""
        WITH requested("window", scope) AS (VALUES {values_sql})
        SELECT state.*
        FROM requested
        JOIN token_radar_publication_state state
          ON state."window" = requested."window"
         AND state.scope = requested.scope
        WHERE state.projection_version = %s
        """,
        [*params, projection_version],
    ).fetchall()
    return {
        (str(row["window"]), str(row["scope"])): {
            "latest_attempt_status": str(row["latest_attempt_status"]),
            "latest_attempt_generation_id": row.get("latest_attempt_generation_id"),
            "latest_attempt_error": row.get("latest_attempt_error"),
            "latest_attempt_finished_at_ms": (
                int(row["latest_attempt_finished_at_ms"])
                if row.get("latest_attempt_finished_at_ms") is not None
                else None
            ),
            "current_generation_id": row.get("current_generation_id"),
            "current_published_at_ms": (
                int(row["current_published_at_ms"])
                if row.get("current_published_at_ms") is not None
                else None
            ),
            "current_source_frontier_ms": int(row.get("current_source_frontier_ms") or 0),
            "current_row_count": int(row.get("current_row_count") or 0),
            "current_source_rows": int(row.get("current_source_rows") or 0),
        }
        for row in rows
    }
```

- [ ] **Step 6: Delete hot-path audit/history methods**

Remove methods and call sites:

```text
latest_snapshot_audit_rows
_write_rank_exit_audits
_write_rank_history
_write_snapshot_audit
ensure_storage_partitions usage for rank_history/snapshot_audit
```

Keep `ensure_storage_partitions` only if another retained table still needs it; otherwise delete it.

- [ ] **Step 7: Add integration test for failed attempt preserving current rows**

Add to `tests/integration/test_token_radar_repository.py`:

```python
def test_failed_publication_attempt_preserves_current_generation(postgres_conn) -> None:
    repo = TokenRadarRepository(postgres_conn)
    row = _valid_factor_row()
    repo.publish_current_generation(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        window="1h",
        scope="all",
        generation_id="gen-ready",
        computed_at_ms=1_778_000_000_000,
        source_frontier_ms=1_777_999_999_000,
        rows=[row],
    )
    repo.mark_publication_failed(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        window="1h",
        scope="all",
        generation_id="gen-failed",
        started_at_ms=1_778_000_060_000,
        finished_at_ms=1_778_000_061_000,
        error="forced failure",
    )

    state = repo.latest_publication_state(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        windows=("1h",),
        scopes=("all",),
    )[("1h", "all")]
    rows = repo.latest_current_rows(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        window="1h",
        scope="all",
        limit=10,
    )

    assert state["latest_attempt_status"] == "failed"
    assert state["current_generation_id"] == "gen-ready"
    assert state["latest_attempt_generation_id"] == "gen-failed"
    assert state["latest_attempt_error"] == "forced failure"
    assert {row["generation_id"] for row in rows} == {"gen-ready"}
```

- [ ] **Step 8: Run repository tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py
git commit -m "feat: publish token radar current rows with publication state"
```

## Task 3: Projection Builds One Generation And Deletes Hydration Retry

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_projection_worker.py`

- [ ] **Step 1: Write failing no-hydration test**

Add to `tests/unit/test_token_radar_projection.py`:

```python
def test_projection_builds_generation_without_payload_hash_hydration_retry(monkeypatch):
    now_ms = 1_778_000_000_000
    feature_row = _project_group(
        [source_row("event-1", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="1h",
        scope="all",
    )
    token_radar = FakeTokenRadar(target_features=[feature_row])
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    result = TokenRadarProjection(repos=repos).refresh_rank_set(
        window="1h",
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert token_radar.published_generation_id
    assert token_radar.load_payload_calls == 0
```

Update the fake repository in that file:

```python
def list_target_features_for_generation(self, *, projection_version, window, scope):
    return list(self.target_features)

def load_target_feature_payloads_for_ranked_keys(self, **kwargs):
    self.load_payload_calls += 1
    raise AssertionError("old hydration path must not be called")
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py::test_projection_builds_generation_without_payload_hash_hydration_retry -q
```

Expected: FAIL because production code still calls hydration-by-payload.

- [ ] **Step 3: Write failing build-failure state test**

Add to `tests/unit/test_token_radar_projection.py`:

```python
def test_projection_marks_publication_failed_when_generation_build_fails():
    now_ms = 1_778_000_000_000
    token_radar = FakeTokenRadar(target_features_error=RuntimeError("feature cache unavailable"))
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    with pytest.raises(RuntimeError, match="feature cache unavailable"):
        TokenRadarProjection(repos=repos).refresh_rank_set(
            window="1h",
            scope="all",
            now_ms=now_ms,
            limit=20,
        )

    assert token_radar.failed_publications == [
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "window": "1h",
            "scope": "all",
            "generation_id": f"{TOKEN_RADAR_PROJECTION_VERSION}:1h:all:{now_ms}",
            "started_at_ms": now_ms,
            "error": "feature cache unavailable",
        }
    ]
    assert token_radar.published_generation_id is None
```

Update `FakeTokenRadar.list_target_features_for_generation(...)` to raise
`self.target_features_error` when set, and update
`FakeTokenRadar.mark_publication_failed(...)` to append a compact dict to
`failed_publications`.

- [ ] **Step 4: Verify the build-failure test fails**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py::test_projection_marks_publication_failed_when_generation_build_fails -q
```

Expected: FAIL because the old flow does not mark build failures in publication state.

- [ ] **Step 5: Add one-read target feature repository method**

In `TokenRadarRepository`, add:

```python
def list_target_features_for_generation(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
) -> list[dict[str, Any]]:
    rows = self.conn.execute(
        """
        SELECT *
        FROM token_radar_target_features
        WHERE projection_version = %s
          AND "window" = %s
          AND scope = %s
          AND rank_input_version = %s
        ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
        """,
        (projection_version, window, scope, TOKEN_RADAR_RANK_INPUT_VERSION),
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 6: Replace rank-then-hydrate with generation builder**

Delete:

```text
_rank_and_hydrate_selected_rows
_hydrate_ranked_rows
_patch_hydrated_rank_row
load_target_feature_payloads_for_ranked_keys
payload_hash changed during selected-row hydration
```

Add in `TokenRadarProjection`:

```python
def _publication_generation_id(self, *, window: str, scope: str, computed_at_ms: int) -> str:
    return f"{PROJECTION_VERSION}:{window}:{scope}:{int(computed_at_ms)}"


def _build_publication_generation(
    self,
    *,
    window: str,
    scope: str,
    limit: int,
    computed_at_ms: int,
) -> dict[str, Any]:
    feature_rows = self.repos.token_radar.list_target_features_for_generation(
        projection_version=PROJECTION_VERSION,
        window=window,
        scope=scope,
    )
    compact_inputs = [_compact_rank_input_from_target_feature(row) for row in feature_rows]
    ranked = self.rank_compact_inputs(compact_inputs)
    selected = _select_top_ranked_by_lane(ranked, limit=limit)
    features_by_key = {_rank_payload_key(row): row for row in feature_rows}
    current_rows: list[dict[str, Any]] = []
    for ranked_row in selected:
        feature_row = features_by_key.get(_rank_payload_key(ranked_row))
        if feature_row is None:
            continue
        current_rows.append(_patch_ranked_current_row(_row_from_target_feature(feature_row), ranked_row))
    return {
        "generation_id": self._publication_generation_id(
            window=window,
            scope=scope,
            computed_at_ms=computed_at_ms,
        ),
        "rows": current_rows,
        "source_frontier_ms": max(
            (int(row.get("source_max_received_at_ms") or 0) for row in current_rows),
            default=0,
        ),
    }
```

Move `_row_from_target_feature(...)` from
`src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
to `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
unchanged, then rename `_patch_hydrated_rank_row(...)` to
`_patch_ranked_current_row(...)` in the same service module. Do not introduce a
second DB read by payload hash.

- [ ] **Step 7: Update refresh flow**

In `refresh_rank_set(...)`, compute the attempted generation id before build and
wrap both build and publish:

```python
started_at_ms = int(now_ms)
attempted_generation_id = self._publication_generation_id(
    window=window,
    scope=scope,
    computed_at_ms=started_at_ms,
)
try:
    generation = self._build_publication_generation(
        window=window,
        scope=scope,
        limit=limit,
        computed_at_ms=started_at_ms,
    )
    published = self.repos.token_radar.publish_current_generation(
        projection_version=PROJECTION_VERSION,
        window=window,
        scope=scope,
        generation_id=generation["generation_id"],
        computed_at_ms=started_at_ms,
        source_frontier_ms=generation["source_frontier_ms"],
        rows=generation["rows"],
        commit=True,
    )
except Exception as exc:
    self.repos.token_radar.mark_publication_failed(
        projection_version=PROJECTION_VERSION,
        window=window,
        scope=scope,
        generation_id=attempted_generation_id,
        started_at_ms=started_at_ms,
        finished_at_ms=_now_ms(),
        error=str(exc),
        commit=True,
    )
    raise
return {
    "status": "ready" if published else "stale_skipped",
    "generation_id": generation["generation_id"],
    "row_count": len(generation["rows"]),
}
```

- [ ] **Step 8: Publish due work even without dirty claims**

In `rebuild_dirty_targets(...)`, build `publish_items` from both successful target projections and requested work items:

```python
publish_items = set(touched_window_scopes)
publish_items.update((str(window), str(scope)) for window, scope in work_items)
for window, scope in sorted(publish_items):
    result["windows"][f"{window}:{scope}"] = self.refresh_rank_set(
        window=window,
        scope=scope,
        now_ms=now_ms,
        limit=limit,
    )
```

Mark target dirty claims done after target feature projection succeeds. Publish failure must not mark already-projected target claims as target errors.

- [ ] **Step 9: Update worker due-state logic**

In `token_radar_projection_worker.py`, replace coverage reads with publication state reads:

```python
state = self.repos.token_radar.latest_publication_state(
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
    windows=tuple(self.windows),
    scopes=tuple(self.scopes),
)
```

A work item is due when:

```python
item_state is None
or item_state["latest_attempt_status"] == "failed"
or item_state["current_published_at_ms"] is None
or now_ms - int(item_state["current_published_at_ms"]) >= interval_ms
```

- [ ] **Step 10: Run projection tests and source scan**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py -q
rg -n "payload_hash changed during selected-row hydration|load_target_feature_payloads_for_ranked_keys|_hydrate_ranked_rows|_rank_and_hydrate_selected_rows" src/gmgn_twitter_intel/app src/gmgn_twitter_intel/domains
```

Expected: pytest PASS and `rg` returns no runtime matches.

- [ ] **Step 11: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py
git commit -m "refactor: build token radar publication generations directly"
```

## Task 4: API And Consumer Freshness Gates

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/queries/pulse_policy_evaluator.py`
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/runtime_worker_dirty_targets.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify tests under `tests/unit/test_asset_flow_service.py`, `tests/unit/test_token_radar_repository.py`, `tests/unit/test_pulse_candidate_worker.py`, `tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py`, `tests/unit/test_notification_rules.py`, `tests/unit/test_token_capture_tier_worker.py`, `tests/integration/test_narrative_repository.py`

- [ ] **Step 1: Write failing AssetFlow stale test**

Add to `tests/unit/test_asset_flow_service.py`:

```python
def test_asset_flow_failed_attempt_with_previous_rows_is_stale_not_fresh():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol="BTC",
                target_type="CexToken",
                target_id="cex_token:BTC",
                generation_id="gen-ready",
            )
        ],
        publication_state={
            ("1h", "all"): {
                "latest_attempt_status": "failed",
                "latest_attempt_generation_id": "gen-failed",
                "latest_attempt_error": "publish failed",
                "current_generation_id": "gen-ready",
                "current_published_at_ms": 1_778_000_000_000,
                "current_row_count": 1,
                "current_source_rows": 1,
            }
        },
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_778_000_060_000)

    assert result["targets"][0]["target"]["symbol"] == "BTC"
    assert result["projection"]["status"] == "stale"
    assert result["projection"]["latest_attempt_status"] == "failed"
    assert result["projection"]["error"] == "publish failed"
```

- [ ] **Step 2: Update AssetFlow freshness mapping**

Replace coverage logic with publication state:

```python
state = self.token_radar.latest_publication_state(
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
    windows=(window,),
    scopes=(scope,),
).get((window, scope))
rows = self.token_radar.latest_current_rows(
    window=window,
    scope=scope,
    limit=max(0, int(limit)) * 2,
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
)
row_generations = {str(row.get("generation_id") or "") for row in rows if row.get("generation_id")}
current_generation = str((state or {}).get("current_generation_id") or "")
latest_status = str((state or {}).get("latest_attempt_status") or "")
matches_current = bool(current_generation) and row_generations <= {current_generation}

if latest_status == "ready" and matches_current:
    projection_status = "fresh"
elif rows:
    projection_status = "stale"
elif latest_status == "failed":
    projection_status = "failed"
else:
    return _pending_projection_payload(state)
```

Return metadata:

```python
"status": projection_status,
"latest_attempt_status": latest_status or "missing",
"generation_id": current_generation or None,
"row_generation_ids": sorted(row_generations),
"error": (state or {}).get("latest_attempt_error"),
"computed_at_ms": (state or {}).get("current_published_at_ms") or row_computed_at_ms,
```

- [ ] **Step 3: Gate target detail reads on ready state**

Change `current_row_for_target(...)` SQL to join publication state:

```sql
SELECT current_rows.*
FROM token_radar_current_rows current_rows
JOIN token_radar_publication_state state
  ON state.projection_version = current_rows.projection_version
 AND state."window" = current_rows."window"
 AND state.scope = current_rows.scope
 AND state.current_generation_id = current_rows.generation_id
WHERE state.latest_attempt_status = 'ready'
  AND current_rows.projection_version = %s
  AND current_rows."window" = %s
  AND current_rows.scope = %s
  AND current_rows.target_type = %s
  AND current_rows.target_id = %s
ORDER BY current_rows.lane DESC, current_rows.rank ASC
LIMIT 1
```

- [ ] **Step 4: Update downstream consumers**

For Pulse, notifications, and runtime dirty repair:

- use `current_row_for_target(...)` for single-target decisions;
- use current rows only when joined to `token_radar_publication_state` with `latest_attempt_status = 'ready'`;
- never enqueue jobs from stale rows.
- update narrative admission and asset registry live-market target queries to join
  `token_radar_publication_state` instead of `token_radar_projection_coverage`.

Add assertion tests:

```python
assert "token_radar_publication_state" in conn.sql
assert "latest_attempt_status = 'ready'" in conn.sql
assert repos.pulse_jobs.inserted == []
```

Add explicit stale suppression tests:

```python
def test_narrative_admission_ignores_stale_token_radar_generation():
    conn = FakeNarrativeConn(publication_status="failed", current_rows=[_current_row(generation_id="gen-ready")])

    result = NarrativeRepository(conn).load_radar_admission_target(
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        schema_version=NARRATIVE_SCHEMA_VERSION,
    )

    assert result["radar_row"] is None
    assert "token_radar_publication_state" in conn.sql
    assert "latest_attempt_status = 'ready'" in conn.sql


def test_ranked_live_market_targets_uses_ready_publication_state():
    conn = FakeRegistryConn(publication_status="failed", current_rows=[_current_row(generation_id="gen-ready")])

    result = RegistryRepository(conn).ranked_live_market_targets(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        since_ms=1_778_000_000_000,
        limit=20,
    )

    assert result == []
    assert "token_radar_publication_state" in conn.sql
    assert "token_radar_projection_coverage" not in conn.sql
```

- [ ] **Step 5: Run read-path tests**

Run:

```bash
uv run pytest tests/unit/test_asset_flow_service.py tests/unit/test_token_radar_repository.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py tests/unit/test_notification_rules.py tests/unit/test_token_capture_tier_worker.py tests/integration/test_narrative_repository.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py src/gmgn_twitter_intel/domains/pulse_lab/queries/pulse_policy_evaluator.py src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py src/gmgn_twitter_intel/app/runtime/runtime_worker_dirty_targets.py src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py tests/unit/test_asset_flow_service.py tests/unit/test_token_radar_repository.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py tests/unit/test_notification_rules.py tests/unit/test_token_capture_tier_worker.py tests/integration/test_narrative_repository.py
git commit -m "fix: gate token radar consumers on publication state"
```

## Task 5: Dirty Target Hash Simplification

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`
- Modify: `tests/unit/test_token_radar_dirty_target_repository.py`
- Modify: `tests/unit/test_ingest_service_token_radar_dirty_targets.py`
- Modify: `tests/unit/test_market_tick_current_repository.py`

- [ ] **Step 1: Write failing tests for claim-free payload hash**

Add to `tests/unit/test_token_radar_dirty_target_repository.py`:

```python
def test_market_enqueue_does_not_encode_claimed_state_in_payload_hash() -> None:
    conn = FakeConn()

    TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
        [("chain_token", "solana:abc")],
        reason="market_current_changed",
        now_ms=1_778_000_000_000,
        commit=False,
    )

    sql = "\n".join(conn.sqls)
    assert ":claimed:" not in sql
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
```

Add to `tests/unit/test_ingest_service_token_radar_dirty_targets.py`:

```python
def test_dirty_payload_hash_is_stable_for_same_source_events_at_different_times() -> None:
    first = _dirty_records(
        [{"target_type_key": "Asset", "identity_id": "asset-1", "source_event_ids": ["event-1"]}],
        reason="token_intent_written",
        now_ms=1_778_000_000_000,
        due_at_ms=None,
    )[0]
    second = _dirty_records(
        [{"target_type_key": "Asset", "identity_id": "asset-1", "source_event_ids": ["event-1"]}],
        reason="token_intent_written",
        now_ms=1_778_000_060_000,
        due_at_ms=None,
    )[0]

    assert first["payload_hash"] == second["payload_hash"]
```

Add to `tests/unit/test_market_tick_current_repository.py`:

```python
def test_market_tick_current_dirty_enqueue_does_not_encode_claimed_state_in_payload_hash() -> None:
    conn = _ScriptedConnection([])

    MarketTickCurrentDirtyTargetRepository(conn).enqueue_targets(
        [("chain_token", "solana:abc")],
        reason="market_tick_written",
        now_ms=1_778_000_000_000,
        commit=False,
    )

    sql = "\n".join(conn.sql)
    assert ":claimed:" not in sql
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_market_enqueue_does_not_encode_claimed_state_in_payload_hash tests/unit/test_ingest_service_token_radar_dirty_targets.py::test_dirty_payload_hash_is_stable_for_same_source_events_at_different_times -q
```

Expected: FAIL until the old hash semantics are removed. Also run:

```bash
uv run pytest tests/unit/test_market_tick_current_repository.py::test_market_tick_current_dirty_enqueue_does_not_encode_claimed_state_in_payload_hash -q
```

Expected: FAIL until the same claim-hash pattern is removed from the market tick dirty target repository.

- [ ] **Step 3: Remove `:claimed:` mutation**

In both dirty target repositories, update conflict clauses so re-dirty while
leased clears the lease. Use the owning table name in each repository
(`token_radar_dirty_targets` or `market_tick_current_dirty_targets`):

```sql
payload_hash = EXCLUDED.payload_hash,
dirty_reason = EXCLUDED.dirty_reason,
due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
leased_until_ms = NULL,
lease_owner = NULL,
last_error = NULL,
updated_at_ms = EXCLUDED.updated_at_ms
```

Keep `mark_done` / `mark_error` guarded by `(target_type_key, identity_id, payload_hash, lease_owner, attempt_count)` so old claims cannot delete newer fingerprints.

- [ ] **Step 4: Make dirty record hashes stable**

Change dirty record creation to hash stable source identity:

```python
payload_hash = _payload_hash(
    {
        "target_type_key": target_type_key,
        "identity_id": identity_id,
        "dirty_reason": str(reason),
        "source_event_ids": sorted(str(event_id) for event_id in source_event_ids),
    }
)
```

Do not include `now_ms`, `due_at_ms`, `lease_owner`, or `attempt_count`.

- [ ] **Step 5: Run dirty tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_dirty_target_repository.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/unit/test_market_tick_current_repository.py -q
```

Expected: PASS, and the source scan must not find `:claimed:` in
`src/gmgn_twitter_intel/domains`.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/unit/test_market_tick_current_repository.py
git commit -m "fix: keep token radar dirty hashes as source fingerprints"
```

## Task 6: Lazy Evidence Only

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Modify: `tests/unit/domains/token_intel/test_token_radar_rank_source_query.py`

- [ ] **Step 1: Write failing bounded evidence test**

Add:

```python
def test_top_edges_for_current_row_is_bounded_lazy_evidence_query() -> None:
    conn = FakeConn(rows=[{"event_id": "event-1", "rank_source_score": 12.0}])

    rows = TokenRadarRankSourceQuery(conn).top_edges_for_current_row(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        target_type_key="Asset",
        identity_id="asset-1",
        limit=5,
    )

    assert rows == [{"event_id": "event-1", "rank_source_score": 12.0}]
    assert "FROM token_radar_rank_source_events" in conn.sql
    assert "LIMIT %s" in conn.sql
    assert "raw_payload_json" not in conn.sql
```

- [ ] **Step 2: Implement query**

Add method:

```python
def top_edges_for_current_row(
    self,
    *,
    projection_version: str,
    window: str,
    scope: str,
    target_type_key: str,
    identity_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = self.conn.execute(
        """
        SELECT
          intent_id,
          event_id,
          target_type_key,
          identity_id,
          display_symbol,
          display_name,
          author_handle,
          is_watched,
          event_received_at_ms,
          rank_source_score,
          reason_codes_json
        FROM token_radar_rank_source_events
        WHERE projection_version = %s
          AND "window" = %s
          AND scope = %s
          AND target_type_key = %s
          AND identity_id = %s
        ORDER BY rank_source_score DESC NULLS LAST, event_received_at_ms DESC, event_id ASC
        LIMIT %s
        """,
        (projection_version, window, scope, target_type_key, identity_id, max(0, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]
```

Add a repository wrapper with the same signature.

- [ ] **Step 3: Run evidence tests**

Run:

```bash
uv run pytest tests/unit/domains/token_intel/test_token_radar_rank_source_query.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py tests/unit/domains/token_intel/test_token_radar_rank_source_query.py
git commit -m "feat: expose bounded token radar evidence edges"
```

## Task 7: Delete Legacy CLI, Coverage, Audit, And Runtime Paths

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/token_radar_postgres_hard_reset.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Modify tests under `tests/unit/test_token_radar_projection.py`, `tests/unit/test_token_radar_repository.py`, `tests/unit/test_token_factor_evaluation.py`, `tests/unit/domains/token_intel/test_token_radar_postgres_hard_reset.py`, `tests/integration/test_cli.py`, `tests/integration/test_postgres_schema_runtime.py`

- [ ] **Step 1: Delete legacy methods and commands**

Remove:

```text
TokenRadarProjection.rebuild_rank_inputs_full
TokenRadarRepository.list_rank_input_rebuild_keys
TokenRadarRepository.stale_rank_input_count
TokenRadarRepository.rank_input_readiness_for_work_items
ops rebuild-token-radar-rank-inputs
```

Keep `ops rebuild-token-radar` only if it calls the new publication generation path.

- [ ] **Step 2: Delete coverage/hard-reset/manifest remnants**

Remove all runtime references to:

```text
token_radar_projection_coverage
token_radar_rank_history
token_radar_snapshot_audit
```

Concrete changes:

- `token_radar_postgres_hard_reset.py` resets only rebuildable retained Token
  Radar tables: `token_radar_current_rows`, `token_radar_publication_state`,
  `token_radar_target_features`, `token_radar_dirty_targets`, and
  `token_radar_rank_source_events`.
- `worker_manifest.py` lists `token_radar_publication_state` and no longer lists
  `token_radar_projection_coverage`, `token_radar_rank_history`, or
  `token_radar_snapshot_audit`.
- `token_factor_evaluation_repository.py` no longer reads
  `token_radar_snapshot_audit`; this repository must use retained material facts
  or return an explicit unsupported/no-snapshot result for this hard cut.

- [ ] **Step 3: Write factor-evaluation no-audit test**

Replace the old test that asserted `FROM token_radar_snapshot_audit` with:

```python
def test_token_factor_evaluation_does_not_read_token_radar_snapshot_audit():
    conn = FakeConn()

    rows = TokenFactorEvaluationRepository(conn).historical_radar_rows(
        factor_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        horizon_ms=60 * 60 * 1000,
        generated_at_ms=1_778_000_000_000,
        limit=10,
    )

    assert rows == []
    assert "token_radar_snapshot_audit" not in "\n".join(conn.sqls)
```

Update the existing `tests/unit/test_token_factor_evaluation.py` test that
currently asserts the old snapshot audit query. The assertion must be exactly
that no SQL references `token_radar_snapshot_audit`.

- [ ] **Step 4: Update tests**

Delete tests whose only purpose is old compatibility:

```text
legacy_needs_rebuild recovery
payload_hash changed during selected-row hydration retry
latest_snapshot_audit_rows fallback
rank input rebuild CLI
```

Replace with assertions that the new rebuild command calls `refresh_rank_set` and writes publication state.

- [ ] **Step 5: Run CLI/projection/factor/reset tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_repository.py tests/unit/test_token_factor_evaluation.py tests/unit/domains/token_intel/test_token_radar_postgres_hard_reset.py tests/integration/test_cli.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Run legacy surface scan**

Run:

```bash
rg -n "token_radar_projection_coverage|token_radar_rank_history|token_radar_snapshot_audit|rebuild_rank_inputs_full|list_rank_input_rebuild_keys|stale_rank_input_count|rank_input_readiness_for_work_items|latest_snapshot_audit_rows" src/gmgn_twitter_intel/app src/gmgn_twitter_intel/domains
```

Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py src/gmgn_twitter_intel/app/surfaces/cli/parser.py src/gmgn_twitter_intel/app/runtime/token_radar_postgres_hard_reset.py src/gmgn_twitter_intel/app/runtime/worker_manifest.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_repository.py tests/unit/test_token_factor_evaluation.py tests/unit/domains/token_intel/test_token_radar_postgres_hard_reset.py tests/integration/test_cli.py tests/integration/test_postgres_schema_runtime.py
git commit -m "refactor: remove token radar legacy runtime paths"
```

## Task 8: Architecture Guards And Docs

**Files:**
- Create: `tests/architecture/test_token_radar_publication_state_hard_cut.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

- [ ] **Step 1: Add no-compat architecture guard**

Create `tests/architecture/test_token_radar_publication_state_hard_cut.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"

BANNED_RUNTIME_TOKENS = (
    "payload_hash changed during selected-row hydration",
    "_rank_and_hydrate_selected_rows",
    "_hydrate_ranked_rows",
    "_patch_hydrated_rank_row",
    "load_target_feature_payloads_for_ranked_keys",
    "rebuild_rank_inputs_full",
    "list_rank_input_rebuild_keys",
    "stale_rank_input_count",
    "rank_input_readiness_for_work_items",
    "latest_snapshot_audit_rows",
    "token_radar_projection_coverage",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "side_effect_status",
    ":claimed:",
)

ONLINE_PATHS = (
    SRC / "app/surfaces/api/routes_radar.py",
    SRC / "domains/token_intel/read_models/asset_flow_service.py",
    SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py",
    SRC / "domains/pulse_lab/queries/pulse_policy_evaluator.py",
    SRC / "domains/notifications/services/notification_rules.py",
    SRC / "domains/narrative_intel/repositories/narrative_repository.py",
    SRC / "domains/asset_market/repositories/registry_repository.py",
    SRC / "app/runtime/runtime_worker_dirty_targets.py",
)

FORBIDDEN_ONLINE_TABLES = (
    "token_radar_target_features",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_rank_source_events",
)


def _runtime_files() -> list[Path]:
    roots = (SRC / "app", SRC / "domains")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def test_legacy_token_radar_publication_paths_are_removed() -> None:
    violations: list[str] = []
    for path in _runtime_files():
        text = path.read_text(encoding="utf-8")
        for token in BANNED_RUNTIME_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} contains {token}")
    assert violations == []


def test_online_token_radar_paths_do_not_read_private_or_cold_tables() -> None:
    violations: list[str] = []
    for path in ONLINE_PATHS:
        text = path.read_text(encoding="utf-8")
        for table in FORBIDDEN_ONLINE_TABLES:
            if table in text:
                violations.append(f"{path.relative_to(ROOT)} reads {table}")
    assert violations == []
```

- [ ] **Step 2: Update worker contract guard**

In `tests/architecture/test_worker_runtime_contracts.py`, replace Token Radar coverage ownership expectations with `token_radar_publication_state`. Assert only Token Radar projection/repository writes it.

- [ ] **Step 3: Update docs**

Use this wording in docs:

```markdown
Token Radar online serving is `token_radar_current_rows` plus
`token_radar_publication_state`. `fresh` is allowed only when publication state
is `ready` and served rows match `current_generation_id`. Failed latest attempts
serve previous rows as `stale` or no rows as `failed`.
```

Update `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md` to state that
`rank_history` and `snapshot_audit` are not part of the runtime hot path.

- [ ] **Step 4: Run architecture/docs tests**

Run:

```bash
uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py docs/CONTRACTS.md docs/WORKERS.md docs/RELIABILITY.md docs/references/POSTGRES_PERFORMANCE.md src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md
git commit -m "docs: define token radar publication state contract"
```

## Task 9: Focused Verification And Live Checks

**Files:**
- Modify only files required by failures.

- [ ] **Step 1: Run core local gates**

Run:

```bash
uv run ruff check .
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_repository.py tests/unit/test_asset_flow_service.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/test_market_tick_current_repository.py tests/unit/test_token_factor_evaluation.py -q
uv run pytest tests/integration/test_token_radar_repository.py tests/integration/test_cli.py -q
uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run full backend gate**

Run:

```bash
make check
```

Expected: PASS.

- [ ] **Step 3: Confirm runtime config paths**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected paths:

```text
config_path: /Users/qinghuan/.gmgn-twitter-intel/config.yaml
workers_config_path: /Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

Report only paths and redacted booleans.

- [ ] **Step 4: Apply migration and rebuild controlled windows**

Run after local tests pass:

```bash
uv run alembic upgrade head
uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all --limit 100
uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope matched --limit 100
uv run gmgn-twitter-intel ops rebuild-token-radar --window 24h --scope all --limit 100
uv run gmgn-twitter-intel ops rebuild-token-radar --window 24h --scope matched --limit 100
```

Expected: each command reports ready publication state and a generation id.

- [ ] **Step 5: Run live SQL verification**

```sql
SELECT "window", scope, latest_attempt_status, current_generation_id,
       latest_attempt_generation_id, current_row_count, current_source_rows,
       to_timestamp(current_published_at_ms / 1000.0) AS current_published_at,
       latest_attempt_error
FROM token_radar_publication_state
WHERE projection_version = 'token-radar-v13-social-attention'
  AND "window" IN ('1h', '24h')
ORDER BY "window", scope;
```

```sql
SELECT "window", scope,
       count(*) AS rows,
       count(DISTINCT generation_id) AS generations,
       min(published_at_ms) AS min_published_at_ms,
       max(published_at_ms) AS max_published_at_ms
FROM token_radar_current_rows
WHERE projection_version = 'token-radar-v13-social-attention'
  AND "window" IN ('1h', '24h')
GROUP BY "window", scope
ORDER BY "window", scope;
```

```sql
SELECT last_error, count(*) AS count
FROM token_radar_dirty_targets
WHERE last_error IS NOT NULL
GROUP BY last_error
ORDER BY count DESC;
```

Expected:

```text
latest_attempt_status = ready for 1h/24h all/matched
each current row set has generations = 1
min/max published_at_ms match within each set
no dirty last_error contains selected-row hydration
```

- [ ] **Step 6: Run source scan**

Run:

```bash
rg -n "payload_hash changed during selected-row hydration|latest_snapshot_audit_rows|load_target_feature_payloads_for_ranked_keys|rebuild_rank_inputs_full|list_rank_input_rebuild_keys|stale_rank_input_count|rank_input_readiness_for_work_items|_patch_hydrated_rank_row|token_radar_projection_coverage|token_radar_rank_history|token_radar_snapshot_audit|side_effect_status|:claimed:" src/gmgn_twitter_intel/app src/gmgn_twitter_intel/domains
```

Expected: no matches.

- [ ] **Step 7: Run completion gate**

Run:

```bash
make check-all
```

Expected: PASS.

- [ ] **Step 8: Commit verification fixes if any**

If verification exposed a bug in an earlier task, return to that task's commit
step and commit the owned files with that task's message. Do not create an empty
commit.

---

## Final Acceptance Checklist

- [ ] `token_radar_current_rows` is the only online Token Radar serving table.
- [ ] `token_radar_publication_state` is the only online freshness/last-failure table.
- [ ] Current rows and ready publication state commit in the same transaction.
- [ ] Failed latest attempts preserve current rows but surface `stale` or `failed`.
- [ ] Runtime hot path does not read or write `token_radar_rank_history` or `token_radar_snapshot_audit`.
- [ ] Runtime contains no payload-hash hydration retry path.
- [ ] Dirty target `payload_hash` is not used as claim state.
- [ ] Architecture tests prevent private/cold tables from becoming online fallback readers.
