# Token Radar Root-Cause Stable Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 彻底修复 `token_radar_current_rows` 写入风暴、物理膨胀、API 分数列分裂和榜单可信度语义混淆。

**Architecture:** Kappa/CQRS hard cut：`NOTIFY` 只做 wake hint，worker 必须经过 durable dirty/due gate；current rows 是唯一在线 read model，但发布必须是内容稳定 generation，未变化不写表。API 把 publication freshness 和 business quality 分开表达，`high_alert` 必须满足硬质量门禁。

**Tech Stack:** Python 3.13, psycopg 3, PostgreSQL 18, Alembic, FastAPI, pytest, ruff, Docker Compose live diagnostics.

---

## Owning Context

- Spec: `docs/superpowers/specs/active/2026-05-27-token-radar-kiss-current-row-hard-cut-cn.md`
- Existing plan already cleaned many old compatibility paths: `docs/superpowers/plans/active/2026-05-27-token-radar-kiss-current-row-hard-cut-plan-cn.md`
- This plan is the next root-cause pass. It must not reintroduce coverage fallback, audit-as-current, rank history, hydration retry, payload-hash claim encoding, feature flags, or dual readers.

## Live Evidence

Sampled on 2026-05-27 after the publication-state hard cut:

```text
token_radar_projection.interval_seconds = 10
token_radar_projection.wakes_on = market_tick_current_updated, resolution_updated

projection_runs last 10m:
  runs_10m = 9523
  rows_written_10m = 97901
  rows_read_10m = 956057
  avg_duration_ms = 17.8

token_radar_current_rows:
  live rows = 128
  dead tuples = 5320
  total size = 73 MB
  avg factor_snapshot_json = 3856 bytes
  rank_score null rows = 128
  score_json = {} rows = 128

publication_state:
  8/8 sets ready

business quality sample:
  multiple high_alert rows have market_health = missing or partial
```

Conclusion: Postgres query latency is not the root cause. The root cause is wake storm plus full-set rewrite plus wide row payload plus unclear quality semantics.

## First-Principles Target

- Wake is a hint, not a publish request.
- Dirty targets and due windows are the only reasons to enter projection work.
- A due window can rebuild for time-window expiry, but an unchanged generation must not touch current rows.
- Generation id is content-addressed, not timestamp-addressed.
- `token_radar_current_rows.rank_score` is authoritative for SQL/monitoring and must match `factor_snapshot_json.composite.rank_score`.
- `score_json` and other empty legacy JSON blocks are not runtime contracts.
- `projection.status=fresh` means publication generation is fresh only.
- `projection.quality_status=ready|degraded|insufficient|failed` describes business credibility.
- `high_alert` requires market quality good enough for high-confidence surfacing. Degraded rows may be `watch`, not `high_alert`.

## Non-Negotiables

- No feature flag to keep old behavior.
- No fallback reader from target features, rank source events, audit, history, or old rows.
- No runtime catch-up scan over recent resolved facts inside `TokenRadarProjectionWorker`.
- No `payload_hash` retry or selected-row hydration.
- No current-row write when stable row set is unchanged.
- No `fresh` API projection without explicit quality status.
- No `high_alert` when row quality is market-missing or market-stale.
- No new detail/evidence table in this pass unless a task below explicitly creates it. KISS choice: keep `factor_snapshot_json` in current rows for the existing API contract, but stop unnecessary rewrites and remove empty legacy JSON columns.

## File Structure

### Runtime Wake And Scheduling

- Modify: `src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py`
  - Wake Token Radar only when Token Radar dirty targets were actually enqueued.
  - Emit at most one `market_tick_current_updated` wake per worker run.

- Modify: `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
  - Gate hot and cold work items by publication state timestamps.
  - Return idle without calling projection when no work item is due.

- Keep unchanged: `src/parallax/app/runtime/worker_base.py`
  - Do not add generic worker throttling. The bug is domain scheduling, not the base loop.

### Projection And Repository

- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
  - Remove runtime `enqueue_recent_resolved_targets()` catch-up scan.
  - Publish due rank sets only from due work items or actual changed target features.
  - Return `ready`, `idle`, `unchanged`, `failed`, or `stale_skipped` explicitly per window.
  - Set `rank_score`, `quality_status`, and `degraded_reasons_json` on current rows.

- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
  - Generate/accept content-stable generation ids.
  - Compare stable current row set before writing.
  - Return a structured publication result instead of `bool`.
  - Fill `rank_score` and remove runtime use of `score_json`.

### Schema

- Create: `src/parallax/platform/db/alembic/versions/20260527_0113_token_radar_stable_publication.py`
  - Hard reset rebuildable `token_radar_current_rows`.
  - Add `quality_status TEXT NOT NULL`.
  - Add `degraded_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb`.
  - Make `rank_score DOUBLE PRECISION NOT NULL`.
  - Drop empty legacy current-row columns: `asset_json`, `primary_venue_json`, `target_json`, `attention_json`, `market_json`, `price_json`, `score_json`.
  - Preserve `factor_snapshot_json`, `intent_json`, `resolution_json`, `data_health_json`, and `source_event_ids_json` for current API/list contracts.

### API And Scoring

- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
  - Keep `projection.status` for publication freshness.
  - Add `projection.quality_status`, `projection.degraded_reasons`, and row-level `quality`.
  - Read row `rank_score` as the SQL score scalar and cross-check snapshot score in tests.

- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
  - Cap `high_alert` when market anchor/latest/floors are not ready.
  - Preserve `watch` for useful but degraded radar rows.

- Review and modify if tests require: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Pulse trigger should not promote degraded Token Radar rows into trade-candidate paths.

### Tests And Docs

- Modify:
  - `tests/unit/test_market_tick_current_projection_worker.py`
  - `tests/unit/test_token_radar_projection_worker.py`
  - `tests/unit/test_token_radar_projection.py`
  - `tests/unit/test_token_radar_repository.py`
  - `tests/integration/test_token_radar_repository.py`
  - `tests/integration/test_token_radar_idempotency.py`
  - `tests/unit/test_asset_flow_service.py`
  - `tests/unit/test_factor_snapshot.py`
  - `tests/architecture/test_token_radar_publication_state_hard_cut.py`
  - `tests/integration/test_postgres_schema_runtime.py`
  - `tests/unit/test_postgres_schema.py`

- Modify docs:
  - `docs/ARCHITECTURE.md`
  - `docs/RELIABILITY.md`
  - `src/parallax/domains/token_intel/ARCHITECTURE.md`
  - `docs/references/POSTGRES_PERFORMANCE.md`

---

## Task 0: Red Tests For The Real Failure Modes

**Files:**
- Modify: `tests/unit/test_market_tick_current_projection_worker.py`
- Modify: `tests/unit/test_token_radar_projection_worker.py`
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/unit/test_asset_flow_service.py`
- Modify: `tests/unit/test_factor_snapshot.py`

- [ ] **Step 0.1: Add wake coalescing tests**

Add tests that prove:

```python
def test_market_tick_current_wakes_token_radar_only_when_dirty_target_enqueued():
    assert fake_token_radar_dirty_targets.enqueue_return == 0
    assert wake.token_radar_notifications == []


def test_market_tick_current_batches_token_radar_wake_once_per_run():
    assert fake_token_radar_dirty_targets.enqueue_return == 3
    assert wake.token_radar_notifications == [{"target_type": "batch", "target_id": "market_tick_current"}]
```

Expected before implementation: FAIL because `_emit_token_radar_wakes()` currently emits per changed target and ignores whether `enqueue_market_targets()` inserted anything.

- [ ] **Step 0.2: Add due-gate tests for Token Radar worker**

Add tests that prove:

```python
def test_token_radar_wake_does_not_bypass_hot_interval_gate():
    worker = _worker_with_ready_state_published_1_second_ago()
    assert projection_calls == []


def test_token_radar_worker_runs_due_hot_items_after_interval():
    worker = _worker_with_ready_state_published_11_seconds_ago()
    assert projection_calls[0]["work_items"] == (("5m", "all"), ("5m", "matched"))


def test_token_radar_worker_returns_idle_when_no_work_item_due():
    result = worker.rebuild_once(now_ms=1_777_800_001_000)
    assert result["status"] == "idle"
```

Expected before implementation: FAIL because `_hot_work_items()` always returns hot windows.

- [ ] **Step 0.3: Add projection service no-scan/no-noop-publish tests**

Add tests that prove:

```python
def test_rebuild_dirty_targets_does_not_runtime_scan_recent_resolved_targets_when_idle():
    result = projection.rebuild_dirty_targets(work_items=(), now_ms=1_777_800_000_000)
    assert dirty_repo.enqueue_recent_resolved_targets_calls == []
    assert projection.refresh_rank_set_calls == []
    assert result["status"] == "idle"


def test_unchanged_target_feature_claim_marks_done_without_rank_publish():
    assert token_radar.upsert_target_feature_return == 0
    assert projection.refresh_rank_set_calls == []
    assert dirty_repo.done_count == 1
```

Expected before implementation: FAIL where current code performs runtime catch-up scan or publishes all due items without distinguishing feature changes.

- [ ] **Step 0.4: Add stable publish repository tests**

Add tests that prove:

```python
def test_stable_generation_id_is_content_addressed_not_time_addressed():
    first_generation_id = stable_generation_id(projection_version="v", window="5m", scope="all", rows=[row])
    second_generation_id = stable_generation_id(projection_version="v", window="5m", scope="all", rows=[row])
    assert first_generation_id == second_generation_id


def test_publish_current_generation_unchanged_does_not_delete_or_insert_rows():
    assert result.status == "unchanged"
    assert "DELETE FROM token_radar_current_rows" not in conn.sqls_after_compare
    assert "INSERT INTO token_radar_current_rows" not in conn.sqls_after_compare


def test_publish_current_generation_persists_rank_score_scalar():
    result = repo.publish_current_generation(rows=[{**row, "rank_score": 88}])
    assert conn.current_insert_params["rank_score"] == 88
```

Expected before implementation: FAIL because generation id is timestamp-derived, publish returns `bool`, and `rank_score` is not inserted.

- [ ] **Step 0.5: Add API quality tests**

Add tests that prove:

```python
def test_asset_flow_fresh_projection_can_be_quality_degraded():
    result = service.asset_flow(window="1h", scope="all", limit=20)
    assert result["projection"]["status"] == "fresh"
    assert result["projection"]["quality_status"] == "degraded"
    assert "market_anchor_missing" in result["projection"]["degraded_reasons"]


def test_asset_flow_ready_market_returns_quality_ready():
    result = service.asset_flow(window="1h", scope="all", limit=20)
    assert result["projection"]["quality_status"] == "ready"
```

Expected before implementation: FAIL because API currently exposes only `anchor_coverage` diagnostics.

- [ ] **Step 0.6: Add high-alert hard-gate tests**

Add tests that prove:

```python
def test_factor_snapshot_caps_high_alert_when_market_anchor_missing():
    snapshot = build_token_factor_snapshot(
        target=resolved_cex_target,
        attention=strong_attention,
        social_quality=strong_social_quality,
        social_semantics=strong_social_semantics,
        market=market_without_anchor,
        timing={},
        source_event_ids=["event-1"],
        computed_at_ms=1_777_800_000_000,
    )
    assert snapshot["composite"]["recommended_decision"] != "high_alert"
    assert "market_anchor_missing" in snapshot["gates"]["blocked_reasons"]


def test_factor_snapshot_caps_high_alert_when_latest_market_stale():
    snapshot = build_token_factor_snapshot(
        target=resolved_cex_target,
        attention=strong_attention,
        social_quality=strong_social_quality,
        social_semantics=strong_social_semantics,
        market=market_with_stale_latest,
        timing={},
        source_event_ids=["event-1"],
        computed_at_ms=1_777_800_000_000,
    )
    assert snapshot["composite"]["recommended_decision"] != "high_alert"
    assert "market_latest_stale" in snapshot["gates"]["blocked_reasons"]
```

Expected before implementation: FAIL for CEX or anchor-missing rows that can still surface as high alert.

- [ ] **Step 0.7: Run red test set**

Run:

```bash
uv run pytest \
  tests/unit/test_market_tick_current_projection_worker.py \
  tests/unit/test_token_radar_projection_worker.py \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_token_radar_repository.py \
  tests/unit/test_asset_flow_service.py \
  tests/unit/test_factor_snapshot.py -q
```

Expected: the new tests fail for the reasons listed above. Existing unrelated tests should keep their previous status.

---

## Task 1: Coalesce Upstream Token Radar Wakes

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py`
- Modify: `tests/unit/test_market_tick_current_projection_worker.py`

- [ ] **Step 1.1: Make `_process_claim()` return Token Radar enqueue count**

Change `_process_claim()` from returning only `(changed, target)` to returning:

```python
{
    "market_current_changed": bool,
    "token_radar_dirty_enqueued": int,
    "target": (target_type, target_id) | None,
}
```

The value of `token_radar_dirty_enqueued` must be the rowcount returned by `repos.token_radar_dirty_targets.enqueue_market_targets`.

- [ ] **Step 1.2: Emit one downstream wake per run**

Change `_run_once_sync()` so it collects `token_radar_dirty_enqueued_total`. Call `_emit_token_radar_wake()` once only when the total is greater than zero.

Use the existing wake channel; payload is not business truth. A single payload is enough:

```python
notify_market_tick_current_updated(target_type="batch", target_id="market_tick_current")
```

- [ ] **Step 1.3: Remove per-target wake behavior**

Delete the loop that calls `notify_market_tick_current_updated` for every target. Keep no fallback to `notify_token_radar_updated`.

- [ ] **Step 1.4: Verify**

Run:

```bash
uv run pytest tests/unit/test_market_tick_current_projection_worker.py tests/integration/test_market_tick_wake_idempotency.py -q
```

Expected: PASS. Tests must prove duplicate or coalesced dirty target enqueues do not emit redundant Token Radar wakes.

---

## Task 2: Make Token Radar Worker Wake-Bounded, Not Wake-Driven

**Files:**
- Modify: `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `tests/unit/test_token_radar_projection_worker.py`

- [ ] **Step 2.1: Add interval-derived due gates**

Add properties:

```python
hot_interval_ms = int(self.interval_seconds * 1000)
cold_interval_ms = int(self.cold_interval_seconds)
```

`hot_interval_ms` applies to hot windows. `cold_interval_ms` applies to non-hot windows and failed retry backoff.

- [ ] **Step 2.2: Replace `_hot_work_items()` with due-aware logic**

Implement:

```python
def _hot_work_items(self, *, publication_state, computed_at_ms):
    due = []
    for window in self.hot_windows:
        for scope in self.scopes:
            if _publication_due(
                publication_state.get((window, scope)),
                computed_at_ms=computed_at_ms,
                interval_ms=int(self.interval_seconds * 1000),
                failed_retry_ms=self.cold_interval_ms,
            ):
                due.append((window, scope))
    return due
```

Rules:

- Missing state is due.
- Latest failed state is due only after `hot_interval_ms` when there is no current generation, or after `cold_interval_ms` when there is a previous generation.
- Ready state is due only when `computed_at_ms - current_published_at_ms >= hot_interval_ms`.
- A wake never bypasses these gates.

- [ ] **Step 2.3: Allow no-work idle**

Change `_next_work_items()` so it can return an empty tuple. Change `_rebuild_once()` so empty work items return:

```python
{
    "computed_at_ms": computed_at_ms,
    "rows_written": 0,
    "source_rows": 0,
    "status": "idle",
    "claimed": 0,
    "catch_up_enqueued": 0,
    "windows": {},
}
```

Do not call `TokenRadarProjection.rebuild_dirty_targets()` when no work item is due.

- [ ] **Step 2.4: Verify**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection_worker.py -q
```

Expected: PASS. Existing tests that asserted hot items always run must be updated to assert hot items run when due.

---

## Task 3: Remove Runtime Catch-Up Scan And Publish Only From Due Or Changed Inputs

**Files:**
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/integration/test_token_radar_idempotency.py`

- [ ] **Step 3.1: Delete runtime `enqueue_recent_resolved_targets()` call**

Remove the block in `rebuild_dirty_targets()` that scans recent resolved targets when no claims exist. Missed enqueue recovery belongs to explicit ops repair, not runtime.

Architecture invariant after this step:

```text
TokenRadarProjectionWorker -> claim token_radar_dirty_targets or run due rank-set refresh
ops repair -> may scan facts and enqueue token_radar_dirty_targets
```

- [ ] **Step 3.2: Track changed target features**

`_project_source_request()` already returns `rows_written` from `upsert_target_feature()`. Use that value:

- `rows_written > 0`: add `(window, scope)` to `touched`.
- `rows_written == 0`: mark claim done, but do not publish because of that claim.
- deleted target feature rows count as touched because rank set may change.

- [ ] **Step 3.3: Keep due rank-set refresh**

Do not remove due rank-set refresh. Time-window expiry is a valid reason to rebuild a rank set. The difference is that due work items now come from Task 2 gates, not every wake.

Set:

```python
publish_items = touched | set(resolved_work_items)
```

only after Task 2 guarantees `resolved_work_items` are due.

- [ ] **Step 3.4: Return unchanged windows distinctly**

When `refresh_rank_set()` returns unchanged, record the window result as:

```python
{"status": "unchanged", "rows_written": 0, "source_rows": 10}
```

Overall worker status is `ready` if at least one due window was checked successfully, even if all were unchanged.

- [ ] **Step 3.5: Verify**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py tests/integration/test_token_radar_idempotency.py -q
```

Expected: PASS. Repeated unchanged runs must not enqueue catch-up, must not publish current rows, and must keep semantic rows stable.

---

## Task 4: Content-Stable Generation And Unchanged Publish Skip

**Files:**
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 4.1: Add publication result value**

Create a small local dataclass or typed dict in `token_radar_repository.py`:

```python
class PublicationResult(TypedDict):
    status: str  # "published" | "unchanged" | "stale_skipped"
    generation_id: str
    rows_written: int
```

Keep it local to the repository module unless another module truly needs the type.

- [ ] **Step 4.2: Compute stable generation id after rows are ranked**

Add a function:

```python
def stable_generation_id(*, projection_version: str, window: str, scope: str, rows: list[dict[str, Any]]) -> str:
    stable_rows = [
        {
            "lane": row["lane"],
            "rank": int(row["rank"]),
            "target_type_key": row.get("target_type_key") or row.get("target_type") or "",
            "identity_id": row.get("identity_id") or row.get("target_id") or row.get("intent_id") or "",
            "decision": row.get("decision"),
            "rank_score": row.get("rank_score"),
            "source_max_received_at_ms": row.get("source_max_received_at_ms"),
            "payload_hash": row.get("payload_hash"),
        }
        for row in rows
    ]
    stable_rows.sort(key=lambda item: (item["lane"], item["rank"], item["target_type_key"], item["identity_id"]))
    payload = {
        "projection_version": projection_version,
        "window": window,
        "scope": scope,
        "rows": stable_rows,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

Sort by `(lane, rank, target_type_key, identity_id)` and hash the JSON payload with `projection_version`, `window`, and `scope`.

- [ ] **Step 4.3: Stop timestamp-derived generation ids**

Replace timestamp-derived generation usage in `refresh_rank_set()` with `stable_generation_id` after rows are built and patched.

Attempt failures before row build can use an attempt id such as:

```python
attempt_id = f"attempt:{PROJECTION_VERSION}:{window}:{scope}:{computed_at_ms}"
```

Do not store attempt ids as successful generation ids.

- [ ] **Step 4.4: Compare existing current row set before DML**

In `publish_current_generation()`:

1. Take advisory transaction lock.
2. Load existing rows for the projection set.
3. Build stable signatures for existing and incoming rows.
4. If signatures match:
   - Upsert `token_radar_publication_state` to clear a prior `failed` latest attempt and confirm `ready`.
   - Do not delete current rows.
   - Do not insert current rows.
   - Do not call `on_current_changes`.
   - Return `{"status": "unchanged", "rows_written": 0, "generation_id": existing_generation_id}`.

- [ ] **Step 4.5: Publish changed sets atomically**

For changed sets, keep the existing transaction shape:

```text
advisory xact lock
delete current rows for projection/window/scope
insert all incoming rows for one generation
upsert publication_state ready
enqueue downstream dirty targets from actual current changes
commit by outer transaction
```

The result must be:

```python
{"status": "published", "rows_written": len(rows_to_insert), "generation_id": generation_id}
```

- [ ] **Step 4.6: Verify**

Run:

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_token_radar_repository.py -q
```

Expected: PASS. Tests must prove unchanged publish emits no current-row DML and changed publish still atomically swaps rows and state.

---

## Task 5: Make Current Row Score And Schema Honest

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260527_0113_token_radar_stable_publication.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`
- Modify: `tests/unit/test_token_radar_repository.py`
- Modify: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 5.1: Hard reset rebuildable current rows**

Migration must start with:

```sql
DELETE FROM token_radar_current_rows;
```

This is acceptable because current rows are rebuildable read model rows.

- [ ] **Step 5.2: Drop legacy empty current-row JSON columns**

Drop these columns from `token_radar_current_rows`:

```text
asset_json
primary_venue_json
target_json
attention_json
market_json
price_json
score_json
```

Do not keep compatibility aliases.

- [ ] **Step 5.3: Add/require honest scalar score and quality columns**

Migration:

```sql
ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS rank_score DOUBLE PRECISION;
ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS quality_status TEXT;
ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS degraded_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_radar_current_rows ALTER COLUMN rank_score SET NOT NULL;
ALTER TABLE token_radar_current_rows ALTER COLUMN quality_status SET NOT NULL;
```

Allowed `quality_status` values:

```text
ready
degraded
insufficient
failed
```

- [ ] **Step 5.4: Update repository insert contract**

Update `RADAR_ROW_COLUMNS`, `RADAR_ROW_INSERT_COLUMNS_SQL`, and `_json_payload()`:

- Include `rank_score`, `quality_status`, `degraded_reasons_json`.
- Remove dropped legacy JSON columns.
- Keep `factor_snapshot_json`, `intent_json`, `resolution_json`, `data_health_json`, and `source_event_ids_json`.

- [ ] **Step 5.5: Populate rank score from patched snapshot**

In `_patch_ranked_current_row()` set:

```python
patched["rank_score"] = ranked.get("rank_score")
```

In `_project_group()` and `_row_from_target_feature()`, do not set `score_json`.

- [ ] **Step 5.6: Verify**

Run:

```bash
uv run pytest \
  tests/unit/test_postgres_schema.py \
  tests/integration/test_postgres_schema_runtime.py \
  tests/unit/test_token_radar_repository.py \
  tests/integration/test_token_radar_repository.py -q
```

Expected: PASS. Schema tests must fail if `score_json` or other dropped legacy JSON current-row columns return.

---

## Task 6: Add Explicit Row And Projection Quality Semantics

**Files:**
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `tests/unit/test_asset_flow_service.py`
- Modify: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 6.1: Add row-quality helper**

Add a private helper in `token_radar_projection.py`:

```python
def _quality_from_factor_snapshot(snapshot: dict[str, Any]) -> tuple[str, list[str]]:
    data_health = _dict(snapshot.get("data_health"))
    market = _dict(snapshot.get("market"))
    readiness = _dict(market.get("readiness"))
    normalization = _dict(snapshot.get("normalization"))
    reasons: list[str] = []
    status = "ready"
    if data_health.get("identity") == "missing":
        reasons.append("identity_missing")
        status = "insufficient"
    if data_health.get("alpha") == "missing":
        reasons.append("alpha_missing")
        status = "insufficient"
    if readiness.get("anchor_status") != "ready":
        reasons.append("market_anchor_missing")
        status = "degraded" if status == "ready" else status
    if readiness.get("latest_status") in {"missing", "stale"}:
        reasons.append(f"market_latest_{readiness.get('latest_status')}")
        status = "degraded" if status == "ready" else status
    if readiness.get("dex_floor_status") in {"missing_fields", "below_floor"}:
        reasons.append("dex_floor_missing" if readiness.get("dex_floor_status") == "missing_fields" else "dex_floor_below")
        status = "degraded" if status == "ready" else status
    if normalization.get("cohort_status") in {"insufficient", "all_tied"}:
        reasons.append("cohort_not_rankable")
        status = "degraded" if status == "ready" else status
    return status, _dedupe_strings(reasons)
```

Rules:

- `identity` missing -> `insufficient`, reason `identity_missing`.
- `alpha` missing -> `insufficient`, reason `alpha_missing`.
- market readiness `anchor_status != ready` -> `degraded`, reason `market_anchor_missing`.
- market readiness `latest_status in {"missing", "stale"}` -> `degraded`, reason `market_latest_missing` or `market_latest_stale`.
- DEX `dex_floor_status != ready` -> `degraded`, reason `dex_floor_missing` or `dex_floor_below`.
- normalization `cohort_status in {"insufficient", "all_tied"}` -> `degraded`, reason `cohort_not_rankable`.
- no reasons -> `ready`.

- [ ] **Step 6.2: Persist row quality**

When building current rows, set:

```python
row["quality_status"] = quality_status
row["degraded_reasons_json"] = degraded_reasons
```

- [ ] **Step 6.3: Expose row quality in API**

In `_public_row()` add:

```python
"quality": {
    "status": row.get("quality_status"),
    "degraded_reasons": row.get("degraded_reasons_json") or [],
}
```

- [ ] **Step 6.4: Expose projection-level quality**

In `asset_flow()` aggregate returned rows:

```text
failed if projection.status failed
insufficient if all returned rows are insufficient
degraded if any returned row is degraded/insufficient or unresolved diagnostics are nonzero
ready otherwise
```

Add `projection.quality_status` and `projection.degraded_reasons`.

- [ ] **Step 6.5: Verify**

Run:

```bash
uv run pytest tests/unit/test_asset_flow_service.py tests/unit/test_token_radar_projection.py -q
```

Expected: PASS. `fresh` and `quality_status=degraded` must be able to appear together.

---

## Task 7: Make High Alert Quality-Gated

**Files:**
- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `tests/unit/test_factor_snapshot.py`
- Review: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify Pulse tests only if the review shows degraded rows can still enter trade-candidate paths.

- [ ] **Step 7.1: Add market high-alert block reasons**

In `_gates()` add high-alert block reasons for:

```text
market_anchor_missing
market_latest_missing
market_latest_stale
dex_floor_missing
dex_floor_below
```

These reasons must cap `max_decision` to `watch`, not necessarily `discard`, unless identity/social/alpha hard blockers already require discard.

- [ ] **Step 7.2: Keep discovery radar useful**

Do not discard useful social signals solely because market quality is degraded. The intended behavior is:

```text
ready market + strong social => high_alert allowed
degraded market + strong social => watch
identity/alpha/social hard missing => discard
```

- [ ] **Step 7.3: Verify Pulse does not over-promote degraded rows**

Review the Pulse trigger path. If it can still turn degraded rows into trade candidates only because `decision == "watch"` or `rank_score` is high, add a deterministic gate using row quality or factor snapshot gates.

- [ ] **Step 7.4: Verify**

Run:

```bash
uv run pytest tests/unit/test_factor_snapshot.py tests/unit/domains/pulse_lab -q
```

Expected: PASS. Tests must prove market-degraded rows cannot be `high_alert`.

---

## Task 8: Architecture And Regression Guards

**Files:**
- Modify: `tests/architecture/test_token_radar_publication_state_hard_cut.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `src/parallax/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`

- [ ] **Step 8.1: Ban runtime catch-up scan from Token Radar projection**

Architecture test must fail if `TokenRadarProjection.rebuild_dirty_targets()` calls:

```text
enqueue_recent_resolved_targets
```

The method may remain in the dirty-target repository only for explicit bounded ops repair.

- [ ] **Step 8.2: Ban legacy current-row score columns**

Schema tests must assert:

```text
token_radar_current_rows.score_json does not exist
token_radar_current_rows.rank_score exists and is NOT NULL
token_radar_current_rows.quality_status exists and is NOT NULL
```

- [ ] **Step 8.3: Ban timestamp generation helper**

Architecture test must fail if runtime code contains:

```text
_generation_id(*, window
published_at_ms
```

Successful generation ids must come from stable row-set content.

- [ ] **Step 8.4: Update docs**

Document:

- Wake hints do not bypass per-window due gates.
- Current rows unchanged publish does not write current rows.
- Publication freshness and business quality are distinct.
- `rank_score` is the SQL scalar contract; `factor_snapshot_json.composite` is the explanation contract.

- [ ] **Step 8.5: Verify**

Run:

```bash
uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py \
  tests/unit/test_postgres_schema.py \
  tests/integration/test_postgres_schema_runtime.py -q
```

Expected: PASS.

---

## Task 9: Focused Full Verification

**Files:**
- No implementation edits in this task.

- [ ] **Step 9.1: Run focused backend suite**

Run:

```bash
uv run pytest \
  tests/unit/test_market_tick_current_projection_worker.py \
  tests/integration/test_market_tick_wake_idempotency.py \
  tests/unit/test_token_radar_projection_worker.py \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_token_radar_repository.py \
  tests/integration/test_token_radar_repository.py \
  tests/integration/test_token_radar_idempotency.py \
  tests/unit/test_asset_flow_service.py \
  tests/unit/test_factor_snapshot.py \
  tests/architecture/test_token_radar_publication_state_hard_cut.py \
  tests/unit/test_postgres_schema.py \
  tests/integration/test_postgres_schema_runtime.py -q
```

Expected: PASS.

- [ ] **Step 9.2: Run lint**

Run:

```bash
uv run ruff check src/parallax tests
```

Expected: PASS.

- [ ] **Step 9.3: Run old-string guard**

Run:

```bash
rg -n "payload_hash changed during selected-row hydration|_rank_and_hydrate_selected_rows|_hydrate_ranked_rows|_patch_hydrated_rank_row|load_target_feature_payloads_for_ranked_keys|rebuild_rank_inputs_full|list_rank_input_rebuild_keys|stale_rank_input_count|rank_input_readiness_for_work_items|latest_snapshot_audit_rows|token_radar_projection_coverage|token_radar_rank_history|token_radar_snapshot_audit|side_effect_status|:claimed:|score_json" src/parallax/app src/parallax/domains
```

Expected: no output, except `score_json` may appear in non-Token-Radar domains only if an existing unrelated table still owns that exact contract. Token Radar runtime must have zero `score_json` references.

---

## Task 10: Docker Live Verification

**Files:**
- No implementation edits in this task.

- [ ] **Step 10.1: Rebuild and start runtime**

Run only after implementation is complete and no other thread is controlling Docker:

```bash
docker compose up -d --build
```

Expected: app and postgres healthy.

- [ ] **Step 10.2: Confirm runtime config**

Run:

```bash
uv run parallax config
```

Expected:

```text
config_path = /Users/qinghuan/.parallax/config.yaml
workers_config_path = /Users/qinghuan/.parallax/workers.yaml
token_radar_projection.interval_seconds = 10
```

Do not print secrets.

- [ ] **Step 10.3: Watch projection run rate**

Run after 10 minutes of live runtime:

```bash
docker compose exec -T postgres psql -U parallax_app -d parallax -v ON_ERROR_STOP=1 -c "
SELECT
  count(*) AS runs_10m,
  sum(rows_written) AS rows_written_10m,
  sum(rows_read) AS rows_read_10m,
  round(avg(finished_at_ms-started_at_ms)::numeric, 1) AS avg_duration_ms,
  max(finished_at_ms-started_at_ms) AS max_duration_ms
FROM projection_runs
WHERE projection_name='token-radar'
  AND started_at_ms >= (extract(epoch from now())*1000)::bigint - 600000;
"
```

Expected:

```text
runs_10m <= 240
rows_written_10m is not linear with wake count
```

Rationale: 5m all/matched can run about once per 10 seconds, and cold windows about once per 60 seconds.

- [ ] **Step 10.4: Check current rows bloat stops increasing linearly**

Run:

```bash
docker compose exec -T postgres psql -U parallax_app -d parallax -v ON_ERROR_STOP=1 -c "
SELECT
  n_live_tup,
  n_dead_tup,
  pg_size_pretty(pg_relation_size(relid)) AS heap,
  pg_size_pretty(pg_indexes_size(relid)) AS indexes,
  pg_size_pretty(pg_total_relation_size(relid)) AS total
FROM pg_stat_user_tables
WHERE relname='token_radar_current_rows';
"
```

Expected:

```text
n_dead_tup does not grow by thousands over a 10 minute stable sample
total size does not grow every sample while live row count stays near 100-200
```

- [ ] **Step 10.5: Check score and quality integrity**

Run:

```bash
docker compose exec -T postgres psql -U parallax_app -d parallax -v ON_ERROR_STOP=1 -c "
SELECT
  count(*) AS rows,
  count(*) FILTER (WHERE rank_score IS NULL) AS null_rank_score,
  count(*) FILTER (
    WHERE rank_score IS DISTINCT FROM NULLIF(factor_snapshot_json #>> '{composite,rank_score}', '')::double precision
  ) AS rank_score_mismatch,
  count(*) FILTER (WHERE quality_status = 'degraded') AS degraded_rows,
  count(*) FILTER (WHERE decision = 'high_alert' AND quality_status <> 'ready') AS degraded_high_alert
FROM token_radar_current_rows;
"
```

Expected:

```text
null_rank_score = 0
rank_score_mismatch = 0
degraded_high_alert = 0
```

- [ ] **Step 10.6: Check API semantics**

Run:

```bash
uv run parallax asset-flow --window 5m --scope all --limit 20
uv run parallax asset-flow --window 1h --scope all --limit 20
```

Expected:

```text
projection.status is fresh/stale/failed/pending publication state
projection.quality_status is ready/degraded/insufficient/failed
fresh does not imply quality ready
high_alert rows are quality ready
```

## Completion Bar

This work is complete only when all of the following are true:

- 10-minute live `projection_runs` falls from thousands to a bounded schedule-driven range.
- Repeated wakes do not cause current-row DML when generation is unchanged.
- `token_radar_current_rows.rank_score` is non-null and matches factor snapshot composite score.
- Token Radar runtime no longer references `score_json`.
- API exposes `projection.status` and `projection.quality_status` separately.
- Degraded market rows cannot be `high_alert`.
- No compatibility reader, fallback path, history/audit current path, or runtime catch-up scan is present.
