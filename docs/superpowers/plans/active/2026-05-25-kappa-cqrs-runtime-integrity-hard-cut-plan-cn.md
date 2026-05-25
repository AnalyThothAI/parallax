# Kappa/CQRS Runtime Integrity Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-25
**Owning spec:** `docs/superpowers/specs/active/2026-05-25-kappa-cqrs-runtime-integrity-hard-cut-cn.md`
**Recommended worktree:** `.worktrees/kappa-cqrs-runtime-integrity-hard-cut`
**Recommended branch:** `codex/kappa-cqrs-runtime-integrity-hard-cut`

**Goal:** Make the runtime implementation match the documented Kappa/CQRS architecture: explicit transactions, append-only market facts, rebuildable current/read models, provider-free read paths, bounded WebSocket IO, and no compatibility fallback.

**Architecture:** This is a hard cut. Multi-table writes use explicit transaction boundaries; `market_tick_current` becomes a single-owner projection from `market_ticks`; Token Radar consumes durable dirty targets only; HTTP/WS read surfaces read persisted data only; old fallback fields and runtime scans are deleted rather than wrapped.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3, FastAPI/WebSocket, existing WorkerBase runtime, pytest architecture/unit/integration tests.

---

## Hard-Cut Verdict

- Root fix: explicit transaction APIs and failure-injection rollback tests.
- Root fix: `market_tick_current` has one owner and a rebuild command.
- Root fix: Token Radar dirty work is durable and queue-driven.
- Root fix: API/WS read paths cannot call providers.
- Root fix: old scoring fallback is deleted.
- Not root fix: keeping current upsert plus adding comments.
- Not root fix: increasing worker intervals.
- Not root fix: catching provider errors in API routes and returning partial data.
- Not root fix: leaving runtime broad scans as "safety catch-up".

## Pre-flight

- [ ] **Step 1: Confirm branch and dirty files**

Run:

```bash
git status --short
git branch --show-current
```

Expected:

- Any user-owned changes are noted and left untouched.
- Work starts from a clean branch or an isolated worktree.

- [ ] **Step 2: Create isolated worktree**

Run:

```bash
git worktree add .worktrees/kappa-cqrs-runtime-integrity-hard-cut -b codex/kappa-cqrs-runtime-integrity-hard-cut main
cd .worktrees/kappa-cqrs-runtime-integrity-hard-cut
git status --short
```

Expected:

- Branch is `codex/kappa-cqrs-runtime-integrity-hard-cut`.
- Status is clean.

- [ ] **Step 3: Capture active runtime config paths before live verification**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected:

- `config_path` and `workers_config_path` point to `~/.gmgn-twitter-intel/`.
- No secret values are printed.

## File Structure

### Create

- `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`  
  Own durable dirty targets for rebuilding/updating current market rows.
- `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_repository.py`  
  Own `market_tick_current` writes, rebuild, and changed-row detection.
- `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_current_projection_worker.py`  
  Single runtime writer for `market_tick_current`; enqueues Token Radar market dirty targets.
- `src/gmgn_twitter_intel/domains/asset_market/services/market_tick_persistence.py`  
  Atomic service for appending ticks and enqueueing current dirty targets.
- `src/gmgn_twitter_intel/domains/asset_market/services/market_tick_current_rebuild.py`  
  Deterministic rebuild service from append-only `market_ticks`.
- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_resolution_refresh_dirty_target_repository.py`  
  Own durable lookup-key refresh targets for `resolution_refresh`.
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260525_0095_kappa_cqrs_runtime_integrity.py`  
  Add `market_tick_current_dirty_targets`, `token_resolution_refresh_dirty_targets`, and any quote/candle snapshot columns/tables chosen below.
- `tests/integration/test_transaction_atomicity.py`  
  Failure-injection rollback tests for the critical chains.
- `tests/unit/test_market_tick_current_projection_worker.py`
- `tests/unit/test_market_tick_current_repository.py`
- `tests/unit/test_api_provider_free_read_paths.py`
- `tests/unit/test_websocket_backpressure.py`
- `tests/architecture/test_kappa_cqrs_runtime_integrity.py`

### Modify

- `src/gmgn_twitter_intel/platform/db/postgres_client.py`
- `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
- `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_poll_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/discovery_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py`
- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_resolution_refresh.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`
- `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_search.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
- `src/gmgn_twitter_intel/domains/asset_market/read_models/market_candles_service.py`
- `src/gmgn_twitter_intel/domains/token_intel/read_models/stocks_radar_service.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/architecture/test_event_anchor_capture_redesign_contracts.py`
- `tests/unit/domains/macro_intel/test_macro_asset_correlation.py`
- `tests/unit/test_cex_binance_hard_cut_cleanup.py`
- `tests/integration/test_pulse_desk_e2e.py`
- `docs/ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`

## Storage Design

Add a market-current dirty table:

```sql
CREATE TABLE IF NOT EXISTS market_tick_current_dirty_targets (
  target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
  target_id TEXT NOT NULL,
  dirty_reason TEXT NOT NULL,
  source_watermark_ms BIGINT NOT NULL DEFAULT 0,
  payload_hash TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  first_dirty_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_market_tick_current_dirty_due
  ON market_tick_current_dirty_targets(
    due_at_ms,
    leased_until_ms,
    priority,
    updated_at_ms,
    target_type,
    target_id
  );
```

The dirty target `payload_hash` must include the target key and latest source
watermark, but exclude lease/control fields.

Keep existing `market_tick_current` columns and primary key. The hard cut changes
writer ownership, not public read shape.

Add a lookup-key dirty table for resolution refresh:

```sql
CREATE TABLE IF NOT EXISTS token_resolution_refresh_dirty_targets (
  provider TEXT NOT NULL,
  lookup_key TEXT NOT NULL,
  lookup_type TEXT NOT NULL CHECK (lookup_type IN ('dex_symbol_lookup', 'address_lookup')),
  dirty_reason TEXT NOT NULL,
  source_watermark_ms BIGINT NOT NULL DEFAULT 0,
  payload_hash TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  first_dirty_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (provider, lookup_key)
);

CREATE INDEX IF NOT EXISTS idx_token_resolution_refresh_dirty_due
  ON token_resolution_refresh_dirty_targets(
    due_at_ms,
    leased_until_ms,
    priority,
    updated_at_ms,
    provider,
    lookup_key
  );
```

Normal `resolution_refresh` runtime claims this table only. Broad lookup-key
discovery from recent facts is ops repair only.

If persisted stock quotes are not already available at implementation time, add
a small read model table owned by a worker:

```sql
CREATE TABLE IF NOT EXISTS stock_quote_snapshots (
  symbol TEXT PRIMARY KEY,
  quote_json JSONB NOT NULL,
  source_provider TEXT NOT NULL,
  observed_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  payload_hash TEXT NOT NULL
);
```

This table is not a fact source for trading decisions; it is a provider-owned
presentation snapshot. If an existing macro/equity quote fact table is available
by then, use that instead and do not create this table.

## Task 1: Add Transaction Primitives And Guards

**Files:**

- Modify: `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/platform/db/postgres_client.py`
- Add tests in: `tests/integration/test_transaction_atomicity.py`

- [ ] **Step 1: Write failing tests for explicit worker transactions**

Add tests that prove `worker_transaction()` rolls back all statements:

```python
def test_worker_transaction_rolls_back_all_repository_writes(postgres_db):
    db = DBPoolBundle.create(postgres_db.settings)
    with pytest.raises(RuntimeError):
        with db.worker_transaction("test_atomicity") as repos:
            repos.conn.execute("CREATE TEMP TABLE IF NOT EXISTS atomicity_probe(id text primary key) ON COMMIT PRESERVE ROWS")
            repos.conn.execute("INSERT INTO atomicity_probe(id) VALUES ('committed-too-early')")
            raise RuntimeError("boom")

    with db.worker_session("test_atomicity") as repos:
        rows = repos.conn.execute("SELECT id FROM atomicity_probe").fetchall()
    assert rows == []
```

Expected: FAIL because `worker_transaction()` does not exist.

- [ ] **Step 2: Implement `worker_transaction()`**

Implementation shape:

```python
@contextmanager
def worker_transaction(self, name: str, statement_timeout_seconds: float | None = None):
    with self.worker_session(name, statement_timeout_seconds=statement_timeout_seconds) as repos:
        with repos.unit_of_work():
            yield repos
```

Also add `RepositorySession.transaction = unit_of_work` if that name reads better
at call sites.

- [ ] **Step 3: Add transaction-state guard helper**

Add a small helper in `postgres_client.py`:

```python
def require_transaction(conn: Any, *, operation: str) -> None:
    info = getattr(conn, "info", None)
    transaction_status = getattr(info, "transaction_status", None)
    if transaction_status is None:
        return
    if int(transaction_status) == 0:
        raise RuntimeError(f"{operation}_requires_explicit_transaction")
```

Use it only in newly created service methods that must never autocommit. Do not
retrofit every repository in this task.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/integration/test_transaction_atomicity.py -q
```

Expected: PASS.

## Task 2: Make Market Tick Persistence Atomic

**Files:**

- Create: `src/gmgn_twitter_intel/domains/asset_market/services/market_tick_persistence.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_poll_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Test: `tests/integration/test_transaction_atomicity.py`

- [ ] **Step 1: Write failing rollback test for tick plus dirty target**

Test shape:

```python
def test_market_tick_insert_and_current_dirty_enqueue_roll_back_together(postgres_repos, market_tick):
    service = MarketTickPersistenceService(repos=postgres_repos)
    with pytest.raises(RuntimeError):
        with postgres_repos.unit_of_work():
            service.insert_ticks_and_enqueue_current_dirty(
                [market_tick],
                reason="test_failure",
                now_ms=market_tick.received_at_ms,
                fail_after_ticks_for_test=True,
            )

    assert postgres_repos.market_ticks.latest_at_or_before(
        target_type=market_tick.target_type,
        target_id=market_tick.target_id,
        at_ms=market_tick.observed_at_ms,
        max_lag_ms=1,
    ) is None
    assert postgres_repos.market_tick_current_dirty_targets.get(
        market_tick.target_type,
        market_tick.target_id,
    ) is None
```

Expected: FAIL until the service and repository exist.

- [ ] **Step 2: Remove `market_tick_current` upsert from `MarketTickRepository`**

`MarketTickRepository` inserts only `market_ticks` and returns inserted tick ids.
Delete the `current_upsert` CTE. Do not leave a feature flag or fallback path.

- [ ] **Step 3: Add atomic persistence service**

The service:

- materializes tick list once
- inserts ticks
- dedupes changed `(target_type, target_id)`
- enqueues `market_tick_current_dirty_targets`
- requires an active transaction

- [ ] **Step 4: Update stream and poll workers**

Replace direct `repos.market_ticks.insert_ticks_returning_ids(...)` plus dirty
enqueue with:

```python
with self.db.worker_transaction(self.name) as repos:
    result = MarketTickPersistenceService(repos=repos).insert_ticks_and_enqueue_current_dirty(
        materialized,
        reason="market_tick_inserted",
        now_ms=int(self.clock()),
    )
```

Emit wake only after the transaction exits successfully.

- [ ] **Step 5: Update event-anchor backfill persistence**

Inside one `worker_transaction()`:

- insert ticks
- attach or terminalize `enriched_events`
- mark `event_anchor_backfill_jobs`
- enqueue current dirty targets for inserted/attached ticks

Only append `attached_ticks` when both capture attach and job mark succeed.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/integration/test_transaction_atomicity.py tests/unit/test_market_tick_stream_worker.py tests/unit/test_market_tick_poll_worker.py tests/unit/test_event_anchor_backfill_worker.py -q
```

Expected: PASS.

## Task 3: Add Market Tick Current Projection Owner

**Files:**

- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_repository.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_current_projection_worker.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/market_tick_current_rebuild.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- Modify: worker settings tests/config as needed
- Test: `tests/unit/test_market_tick_current_projection_worker.py`
- Test: `tests/unit/test_market_tick_current_repository.py`

- [ ] **Step 1: Write repository tests**

Cover:

- enqueue coalesces by target
- claim uses lease token
- mark_done cannot delete newer dirty work
- latest tick selection orders by `observed_at_ms DESC, received_at_ms DESC, tick_id DESC`
- upsert returns `changed=True` only when visible current row changes

- [ ] **Step 2: Implement repositories**

`MarketTickCurrentDirtyTargetRepository` owns enqueue/claim/mark_done/mark_error.

`MarketTickCurrentRepository` owns:

- `latest_tick_for_target(target_type, target_id)`
- `upsert_current_from_tick(tick_row, now_ms) -> bool`
- `truncate_current()`
- `rebuild_from_market_ticks(batch_size, dry_run)`

- [ ] **Step 3: Implement worker**

Worker run shape:

```text
claim due current-dirty targets
for each target:
  load latest market tick from market_ticks
  upsert market_tick_current if changed
  if changed: enqueue token_radar_dirty_targets
  mark current-dirty done
commit
emit token_radar_updated for changed targets
```

The worker is the only runtime writer for `market_tick_current`.

- [ ] **Step 4: Register worker**

Add worker key `market_tick_current_projection` to registry, worker settings, and
worker docs. Give it a single-writer advisory lock.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_market_tick_current_repository.py tests/unit/test_market_tick_current_projection_worker.py tests/unit/test_worker_settings.py -q
```

Expected: PASS.

## Task 4: Add Rebuild And Repair Ops Commands

**Files:**

- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Create or modify: tests for ops CLI closest to `tests/unit/test_token_radar_audit_cli.py`
- Modify: `docs/generated/cli-help.md`

- [ ] **Step 1: Add `rebuild-market-tick-current` command**

Command contract:

```bash
uv run gmgn-twitter-intel ops rebuild-market-tick-current --dry-run
uv run gmgn-twitter-intel ops rebuild-market-tick-current --execute
```

Dry-run reports counts by target type and estimated rows. Execute truncates and
rebuilds `market_tick_current` from `market_ticks`. It does not write Token Radar
rows directly.

- [ ] **Step 2: Add Token Radar dirty enqueue repair command**

Command contract:

```bash
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --source events --since-ms 0 --dry-run
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --source market-current --since-ms 0 --execute
```

It only enqueues `token_radar_dirty_targets`; it never writes read-model rows.

- [ ] **Step 3: Regenerate CLI help**

Run:

```bash
uv run gmgn-twitter-intel --help > /tmp/gmgn-cli-help.txt
```

Then update `docs/generated/cli-help.md` with the established project command if
one exists. Do not paste secrets or runtime config values.

## Task 5: Hard-Cut Token Radar Dirty Runtime

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Test: `tests/unit/test_token_radar_projection_worker.py`
- Test: `tests/unit/test_token_radar_dirty_target_repository.py`
- Test: `tests/integration/test_token_radar_repository.py`

- [ ] **Step 1: Write failing no-runtime-scan test**

Patch the dirty repository catch-up methods to raise and assert empty queue
returns `claimed=0` without scanning:

```python
def test_token_radar_projection_empty_queue_does_not_scan_facts(worker, repos):
    repos.token_radar_dirty_targets.raise_on_catchup = True
    result = asyncio.run(worker.run_once())
    assert result.processed == 0
    assert result.notes["claimed"] == 0
```

- [ ] **Step 2: Remove runtime catch-up scan calls**

Delete normal runtime calls to event/resolution broad catch-up methods. Keep
repair logic only in ops command code.

- [ ] **Step 3: Remove required-repository fallback**

Replace `getattr(repos, "token_radar_dirty_targets", None)` runtime skips with
direct required access. Missing repository should fail tests/startup.

- [ ] **Step 4: Wrap publish units in explicit transactions**

Projection writes must commit target features, rank rows, audit/history,
coverage, offset, and dirty mark-done consistently. If a large publish must be
split for lock duration, split by explicit `(window, scope)` unit with complete
state inside each unit.

- [ ] **Step 5: Batch source-row queries**

Add a batched query path for claimed targets grouped by `(window, scope)`. Keep
the old single-target query only for unit tests or delete it if no public caller
needs it.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_dirty_target_repository.py tests/integration/test_token_radar_repository.py -q
```

Expected: PASS.

## Task 6: Hard-Cut Resolution Refresh To Dirty Queue

**Files:**

- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/token_resolution_refresh_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/discovery_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_resolution_refresh.py`
- Test: `tests/unit/test_resolution_refresh_worker.py`
- Test: `tests/unit/test_discovery_repository.py`
- Test: `tests/integration/test_transaction_atomicity.py`

- [ ] **Step 1: Write failing empty-queue test**

Patch the old discovery scan to raise and assert runtime does not call it:

```python
def test_resolution_refresh_empty_dirty_queue_does_not_scan_recent_facts(worker, repos):
    repos.discovery.raise_on_due_lookup_keys = True

    result = asyncio.run(worker.run_once(now_ms=1_800_000))

    assert result.processed == 0
    assert result.notes["result"]["lookups_selected"] == 0
    assert result.notes["result"]["claimed"] == 0
```

Expected: FAIL because current worker calls `repos.discovery.due_lookup_keys(...)`.

- [ ] **Step 2: Implement lookup-key dirty repository**

Repository methods:

- `enqueue_lookup_keys(items, reason, now_ms, commit=False)`
- `claim_due(limit, now_ms, lease_ms, owner)`
- `mark_done(claim_token)`
- `mark_error(claim_token, error, retry_at_ms)`
- `queue_depth(now_ms)`

Claim tokens include provider, lookup key, payload hash, lease owner, and attempt
count so old claims cannot delete newer dirty work.

- [ ] **Step 3: Enqueue lookup dirty targets at source writes**

When token intent lookup keys are written for unresolved, `NIL`, or `AMBIGUOUS`
resolutions, enqueue `token_resolution_refresh_dirty_targets` in the same
transaction. The enqueue belongs with the fact write, not in the refresh worker's
runtime scanner.

- [ ] **Step 4: Rewrite `ResolutionRefreshWorker` claim loop**

Runtime shape:

```text
worker_session
  -> claim due lookup-key dirty targets
release connection
for each claim:
  worker_transaction -> start_lookup
  provider lookup outside DB connection
  worker_transaction
    -> finish_lookup
    -> persist registry/identity facts
    -> reprocess intents for claimed lookup key only
    -> enqueue Token Radar dirty targets
    -> mark refresh target done or retry
commit
notify resolution_updated after commit
```

Do not call `DiscoveryRepository.due_lookup_keys()` in normal runtime.

- [ ] **Step 5: Move broad lookup discovery to ops repair**

Add an ops command:

```bash
uv run gmgn-twitter-intel ops enqueue-resolution-refresh-targets --since-ms 0 --dry-run
uv run gmgn-twitter-intel ops enqueue-resolution-refresh-targets --since-ms 0 --execute
```

The command may use the old broad query to enqueue dirty targets. It must not
call providers, reprocess intents, or write Token Radar rows directly.

- [ ] **Step 6: Add architecture guard**

Fail if runtime worker code calls `due_lookup_keys` or scans
`token_intent_lookup_keys + token_intents + events + token_intent_resolutions`
for normal refresh discovery.

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_resolution_refresh_worker.py tests/unit/test_discovery_repository.py tests/integration/test_transaction_atomicity.py -q
```

Expected: PASS.

## Task 7: Remove Token Radar Legacy Confidence Fallback

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`
- Modify or add: `tests/unit/domains/token_intel/test_token_radar_feature_builder.py`
- Modify: `tests/architecture/test_no_factor_snapshot_fallback.py`

- [ ] **Step 1: Write failing scoring test**

```python
def test_confidence_ignores_legacy_numeric_fields_when_resolution_status_missing():
    row = {
        "resolution_status": None,
        "intent_confidence": 0.99,
        "confidence": 0.88,
    }
    assert _confidence(row) == 0.0
```

Expected: FAIL because current code falls back to numeric fields.

- [ ] **Step 2: Delete fallback**

Implementation:

```python
def _confidence(row: dict[str, Any]) -> float:
    return mention_confidence_from_status(row.get("resolution_status"))
```

If missing status should be observable, surface it in factor health elsewhere; do
not reuse legacy numeric fields.

- [ ] **Step 3: Add architecture guard**

Fail if runtime source contains `intent_confidence` or `row.get("confidence")`
inside Token Radar scoring paths, except migrations/tests explicitly allowlisted.

## Task 8: Hard-Cut Provider IO From API Read Paths

**Files:**

- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_search.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/read_models/market_candles_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/stocks_radar_service.py`
- Create or reuse: persisted candle/quote read model files
- Test: `tests/unit/test_api_provider_free_read_paths.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Add poison-provider tests**

Create providers whose methods raise `AssertionError("provider IO in read path")`.
Assert these endpoints still succeed without calling them:

- `/api/search/inspect`
- `/api/token-case`
- `/api/target-social-timeline`
- `/api/stocks-radar`

- [ ] **Step 2: Replace candle service dependency**

For Token Case/Search/Social Timeline, use persisted `market_ticks` bucketing or a
worker-owned candle snapshot. The response can return:

```json
{
  "price_series_type": "anchor_line",
  "candle_status": "unavailable",
  "candle_source": "persisted_market_ticks"
}
```

when there are not enough local facts. Do not call GMGN/Binance/OKX from API.

- [ ] **Step 3: Replace stocks quote provider dependency**

`StocksRadarService` reads persisted quote snapshots. If a symbol has no
snapshot, return explicit unavailable state from DB-derived data. Do not call
Yahoo/macrodata provider from the route.

- [ ] **Step 4: Add architecture guard**

Scan API routes and read models for provider access patterns:

- `runtime.providers`
- `stock_quote_provider`
- `.candles(`
- `.token_candles(`
- `.quote(`

Allow only worker/provider wiring modules and explicit tests.

## Task 9: Make WebSocket Replay And Broadcast Non-Blocking

**Files:**

- Modify: `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
- Add tests: `tests/unit/test_websocket_backpressure.py`
- Modify existing: `tests/integration/test_api_websocket.py`

- [ ] **Step 1: Write replay non-blocking test**

Use a heartbeat task that increments while a subscribe replay runs. The test
fails if synchronous DB replay blocks the event loop.

- [ ] **Step 2: Batch replay DB reads**

Replace per-event payload assembly with batch repository methods:

- entities by event ids
- alerts by event ids
- token intents by event ids
- token resolutions by event ids

Run the sync DB work in `asyncio.to_thread` until an async repository exists.

- [ ] **Step 3: Add per-client outbound queues**

Client state gains:

```python
queue: asyncio.Queue[str]
writer_task: asyncio.Task[None]
```

`publish()` enqueues messages and returns. Queue full policy:

- live market updates: drop oldest replaceable update for that client
- replay/event/notification: close slow client with a clear reason

- [ ] **Step 4: Run WebSocket tests**

Run:

```bash
uv run pytest tests/unit/test_websocket_backpressure.py tests/integration/test_api_websocket.py -q
```

Expected: PASS.

## Task 10: Fix Wake Listener Executor Contention

**Files:**

- Modify: `src/gmgn_twitter_intel/app/runtime/wake_waiter.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
- Test: `tests/unit/test_wake_waiter.py`
- Test: `tests/unit/test_db_pool_bundle.py`

- [ ] **Step 1: Add stress test**

Create many wake waiters and simultaneous `asyncio.to_thread` DB/provider tasks.
Assert wake waits do not consume the default executor enough to starve work.

- [ ] **Step 2: Implement dedicated wake execution**

Choose one:

- a dedicated `ThreadPoolExecutor` for wake waits, or
- one shared wake dispatcher thread that listens and sets local events.

Do not use the default executor for long LISTEN waits.

## Task 11: Clean Compatibility Residue And Architecture Scans

**Files:**

- Modify: `tests/unit/domains/macro_intel/test_macro_asset_correlation.py`
- Modify: `tests/unit/test_cex_binance_hard_cut_cleanup.py`
- Modify: `tests/integration/test_pulse_desk_e2e.py`
- Modify: `tests/architecture/test_event_anchor_capture_redesign_contracts.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Create/modify: `tests/architecture/test_kappa_cqrs_runtime_integrity.py`

- [ ] **Step 1: Rename non-runtime test helpers**

Rename `_price_observations` to `_asset_price_samples` or similar in tests.
Rename test strings containing old table names when they are not asserting
historical migrations.

- [ ] **Step 2: Rename `token_radar_rows` fixture names**

In tests where the fixture is not the old table, rename to `radar_rows` or
`current_rows`.

- [ ] **Step 3: Prune skipped dirs during architecture scan**

Replace `ROOT.rglob("*")` full traversal with an `os.walk` that mutates
`dirnames` to skip ignored directories before descent.

- [ ] **Step 4: Add new hard-cut guards**

Guard categories:

- `market_tick_current` writer allowlist
- no runtime provider IO in API/read models
- no Token Radar broad runtime catch-up scans
- no Resolution Refresh broad runtime lookup-key scans
- no `intent_confidence` / `confidence` scoring fallback
- no silent dirty repository missing skip in runtime workers
- no `MarketTickRepository` writes to `market_tick_current`

- [ ] **Step 5: Run architecture tests**

Run:

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_event_anchor_capture_redesign_contracts.py tests/architecture/test_no_factor_snapshot_fallback.py tests/architecture/test_kappa_cqrs_runtime_integrity.py -q
```

Expected: PASS.

## Task 12: Update Architecture Docs

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`

- [ ] **Step 1: Document transaction rule**

Add: multi-table writes use explicit use-case transactions; `commit=False` is not
an architecture boundary.

- [ ] **Step 2: Document market current owner**

State:

- `market_ticks` is append-only fact truth.
- `market_tick_current` is a rebuildable read model.
- `MarketTickCurrentProjectionWorker` is the only runtime writer.
- Rebuild command derives it from `market_ticks`.

- [ ] **Step 3: Document provider-free read paths**

State that API/WS/CLI read surfaces do not call market, quote, candle, OpenAI, or
external provider adapters.

- [ ] **Step 4: Document WebSocket backpressure policy**

Describe queue sizes, close/drop behavior, and what messages are replayable.

## Task 13: End-To-End Verification

**Files:** none unless verification doc is created.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest \
  tests/integration/test_transaction_atomicity.py \
  tests/unit/test_market_tick_current_repository.py \
  tests/unit/test_market_tick_current_projection_worker.py \
  tests/unit/test_api_provider_free_read_paths.py \
  tests/unit/test_websocket_backpressure.py \
  tests/architecture/test_worker_runtime_contracts.py \
  tests/architecture/test_event_anchor_capture_redesign_contracts.py \
  tests/architecture/test_no_factor_snapshot_fallback.py \
  tests/architecture/test_kappa_cqrs_runtime_integrity.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run broader checks**

Run:

```bash
uv run pytest tests/unit tests/integration tests/architecture -q
uv run ruff check .
```

Expected: PASS or documented unrelated baseline failures.

- [ ] **Step 3: Run live-safe ops dry runs**

Run:

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel ops rebuild-market-tick-current --dry-run
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --source market-current --since-ms 0 --dry-run
```

Expected:

- Config paths point to `~/.gmgn-twitter-intel/`.
- Dry-runs report counts only.
- No secrets are printed.

- [ ] **Step 4: Verify no request-time providers**

Run API poison-provider tests and manually inspect route construction:

```bash
rg -n "runtime\\.providers|stock_quote_provider|\\.candles\\(|\\.token_candles\\(|\\.quote\\(" src/gmgn_twitter_intel/app/surfaces/api src/gmgn_twitter_intel/domains/*/read_models
```

Expected: no runtime provider call sites in API/read-model code except allowlisted tests.

- [ ] **Step 5: Verify DB ownership**

Run:

```bash
rg -n "market_tick_current" src/gmgn_twitter_intel/domains src/gmgn_twitter_intel/app tests/architecture
```

Expected:

- Runtime writes occur only in `market_tick_current_repository.py` and
  `market_tick_current_projection_worker.py`.
- Reads remain in Token Radar/target read paths.
- Architecture tests encode the ownership.

## Rollout Notes

1. Deploy during a maintenance window because market current ownership changes.
2. Run `ops rebuild-market-tick-current --execute` after migration and before
   re-enabling Token Radar projection.
3. Run Token Radar dirty enqueue repair for market current and recent events.
4. Restart workers.
5. Confirm `/readyz` shows `market_tick_current_projection` and
   `token_radar_projection` draining queues.
6. Do not add compatibility flags or old fallback paths if any step fails.
