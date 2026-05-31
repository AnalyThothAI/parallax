# Token / Pulse / Equity CPU Hot Path Hard Cut Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan.

**Goal:** remove the remaining CPU hot paths in Token Radar, Pulse, and Equity timelines without touching News. The hard cut must stop target-wide runtime scans, stop unchanged read-model churn, and keep business facts unchanged.

**Architecture:** PostgreSQL material facts remain the source of truth. Runtime workers claim durable work first, read only bounded inputs, write exactly one owned read model, and write zero serving rows when the projection payload is unchanged. Rebuild is allowed because the touched tables are derived read models or control-plane queues.

**Tech Stack:** Python, psycopg, Alembic, PostgreSQL, Docker Compose, pytest, pg_stat_statements, PoWA, pgBadger.

**Owning References:**

- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/superpowers/specs/active/2026-05-27-runtime-db-performance-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-27-token-radar-kiss-current-row-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-28-token-radar-equity-workerspace-root-fix-cn.md`

**Status:** Ready for implementation. News duplicate-key and News projection work are explicitly out of scope.

---

## Current Evidence Snapshot

Live runtime checks on 2026-05-29 showed the root cause is still present, but narrowed:

- Token Radar old `WITH request_targets AS` and `WITH source_intents AS MATERIALIZED` paths are gone. The remaining cost is the new source-edge hydrate query in `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py`, which still starts from target/window/scope and re-reads the whole source window for each source-dirty target.
- `token_radar_dirty_targets.source_event_ids_json` already captures exact dirty events, but `TokenRadarProjection.rebuild_dirty_targets()` does not pass that event set into rank-source population.
- Pulse is triggered from `token_radar_current_rows`, which already has `source_event_ids_json`, but `PulseCandidateWorker._asset_context()` still calls `repos.token_targets.timeline_rows(... watched_only=False, limit=200)` and filters `matched` in Python.
- Equity `replace_company_timeline_rows()` always executes a `DELETE` before upsert, and that delete uses `(company_id = ANY(...) OR company_event_id = ANY(...))`. On live stats, this was a high-frequency sequential scan on `equity_company_timeline_rows`.
- CPU above 100% is expected when multiple PostgreSQL workers or containers consume more than one logical core. The problem is not the percentage itself; the problem is avoidable CPU from repeated scans and unchanged read-model churn.

## Non-Negotiable Constraints

- Do not implement compatibility flags, fallback readers, dual writers, shadow old SQL, or legacy runtime branches.
- Do not change material facts: `events`, `token_intents`, `token_intent_resolutions`, `registry_assets`, `market_ticks`, `equity_company_events`, `equity_event_documents`, and accepted fact tables stay intact.
- Do not do News work in this plan.
- Runtime Token Radar source-dirty work must be event-id bounded. A source-dirty claim without event ids is a contract error, not permission to run the old target-wide hydrate.
- Pulse must use the evidence set carried by the Token Radar current row. It must not reconstruct a full 24h target timeline in the hot path.
- Equity timeline replacement must determine unchanged/stale state before deleting. Identical payloads must produce zero serving-row writes.
- Rebuild must run only with workers stopped or paused, after migrations and code are deployed.
- Real-data diagnostics must first run `uv run parallax config` and report only paths, booleans, and counts, never secrets.

## Target Data Flow

Token/Pulse after the hard cut:

```text
token_radar_dirty_targets.source_event_ids_json
        |
        v
TokenRadarProjection source-dirty claim
        |
        v
populate_edges_for_event_ids(event ids only)
        |
        v
token_radar_rank_source_events
        |
        v
token_radar_current_rows.source_event_ids_json
        |
        v
PulseCandidateWorker
        |
        v
timeline_rows_for_event_ids(event ids only, watched_only for matched)
```

Equity timeline after the hard cut:

```text
incoming timeline payloads
        |
        v
load existing state by row_id / company_id / company_event_id
        |
        +--> identical and no stale scoped rows -> zero writes
        |
        v
delete stale rows by indexed company_id and company_event_id statements
        |
        v
upsert only missing or payload-changed rows
```

---

## Implementation Tasks

### Task 0: Baseline and Scope Lock

Run before code changes:

```bash
git status --short
uv run parallax config
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_projection_worker_idle_cost_contract.py -q
```

Capture live evidence without resetting stats:

```bash
docker stats --no-stream
uv run parallax ops worker-status
uv run parallax ops queue-inspect --status active --limit 20
```

Expected config evidence:

- `config_path` is `/Users/qinghuan/.parallax/config.yaml`
- `workers_config_path` is `/Users/qinghuan/.parallax/workers.yaml`
- no secret values are printed

### Task 1: Add Hard-Cut Architecture Guards First

Add `tests/architecture/test_token_pulse_equity_cpu_hard_cut_contract.py`.

Required guards:

1. `TokenRadarRankSourceQuery` must not contain the target-wide source hydrate shape:
   - `JOIN token_intent_resolutions` directly from `requested.target_type_key`
   - the old `_POPULATE_RANK_SOURCE_EDGES_SQL` constant
   - stale delete over the full analysis window without requested event ids
2. `TokenRadarProjection.rebuild_dirty_targets()` must pass claimed `source_event_ids_json` into rank-source population for source-dirty work.
3. Runtime Token Radar source population must expose only the event-id bounded method, for example `populate_edges_for_event_ids(...)`.
4. `PulseCandidateWorker._asset_context()` must not call `timeline_rows(... watched_only=False ...)` for all scopes.
5. Pulse runtime must call an event-id bounded evidence loader and pass `watched_only=True` for `scope == "matched"`.
6. `replace_company_timeline_rows()` must not contain a delete predicate with ` OR company_event_id`.
7. `replace_company_timeline_rows()` must have a pre-delete existing-state/no-op gate.
8. No file under `src/parallax/domains/news_intel` is modified by this implementation.

Run this test alone and confirm it fails before implementation:

```bash
uv run pytest tests/architecture/test_token_pulse_equity_cpu_hard_cut_contract.py -q
```

### Task 2: Add Targeted Database Support

Create Alembic migration `src/parallax/platform/db/alembic/versions/20260529_0124_token_pulse_equity_cpu_hard_cut.py` with `down_revision = "20260529_0123"`.

Add indexes for the new bounded paths. Use `with op.get_context().autocommit_block():` for every `CREATE INDEX CONCURRENTLY`; do not execute concurrent indexes inside Alembic's normal transaction block.

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intents_event_intent
  ON token_intents(event_id, intent_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_resolutions_current_event_target
  ON token_intent_resolutions(
    event_id,
    target_type,
    target_id,
    resolver_policy_version,
    resolution_status,
    confidence DESC,
    decision_time_ms DESC,
    resolution_id DESC
  )
  WHERE is_current = true
    AND target_type IN ('Asset', 'CexToken')
    AND target_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_feeds_cex_canonical_updated
  ON price_feeds(subject_id, updated_at_ms DESC, native_market_id ASC)
  WHERE subject_type = 'CexToken'
    AND provider = 'binance'
    AND feed_type = 'cex_swap'
    AND quote_symbol = 'USDT'
    AND status = 'canonical';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_timeline_rows_company_row
  ON equity_company_timeline_rows(company_id, row_id)
  INCLUDE (company_event_id, payload_hash, projection_version, source_watermark_ms);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_timeline_rows_event_row
  ON equity_company_timeline_rows(company_event_id, row_id)
  INCLUDE (company_id, payload_hash, projection_version, source_watermark_ms);
```

After migration, validate invalid concurrent indexes are not present:

```sql
SELECT relname
FROM pg_class
JOIN pg_index ON pg_index.indexrelid = pg_class.oid
WHERE relname IN (
  'idx_token_intents_event_intent',
  'idx_token_intent_resolutions_current_event_target',
  'idx_price_feeds_cex_canonical_updated',
  'idx_equity_company_timeline_rows_company_row',
  'idx_equity_company_timeline_rows_event_row'
)
AND NOT indisvalid;
```

Expected result: zero rows.

### Task 3: Hard Cut Token Radar Source Population to Event IDs

Files:

- `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py`
- `src/parallax/domains/token_intel/services/token_radar_projection.py`
- `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- `tests/unit/test_token_radar_projection.py`
- `tests/integration/test_token_radar_idempotency.py`
- `tests/integration/test_token_radar_repository.py`

Implementation:

1. Extend `TokenRadarSourceRequest` with `source_event_ids: tuple[str, ...]`.
2. Change `_request_payload()` to include `source_event_ids_json`.
3. Change `_source_requests_for_targets()` so source-dirty claims copy `claim["source_event_ids_json"]` into every generated request.
4. For source-dirty claims with empty `source_event_ids_json`, mark the claim error with `token_radar_source_event_ids_required` and do not call rank-source population.
5. Replace `populate_edges_for_requests(...)` with `populate_edges_for_event_ids(...)`.
6. Remove the old target-wide `_POPULATE_RANK_SOURCE_EDGES_SQL` instead of keeping it as a fallback.
7. The new SQL must start from `jsonb_array_elements_text(source_event_ids_json)` and then join by exact `event_id`.
8. The new stale-edge delete may delete only rows whose `source_id` is in the requested event-id set. It must not delete all rows in `analysis_since_ms..now_ms`.
9. Market-only dirty work must keep using existing rank-source rows plus `latest_market_context_for_targets(...)`; it must not populate source edges.
10. Ops repair must materialize event ids into dirty payloads. Do not add a broad repair branch to the worker.

The new SQL shape should follow this outline:

```sql
WITH raw_requested AS (
  SELECT *
  FROM jsonb_to_recordset(%s::jsonb) AS r(
    request_key text,
    target_type_key text,
    identity_id text,
    "window" text,
    scope text,
    analysis_since_ms bigint,
    score_since_ms bigint,
    now_ms bigint,
    source_event_ids_json jsonb
  )
),
requested_events AS (
  SELECT DISTINCT
    raw_requested.*,
    event_ids.event_id
  FROM raw_requested
  CROSS JOIN LATERAL jsonb_array_elements_text(raw_requested.source_event_ids_json) AS event_ids(event_id)
),
source_intents AS (
  SELECT ...
  FROM requested_events
  JOIN events ON events.event_id = requested_events.event_id
  JOIN token_intents ON token_intents.event_id = events.event_id
  JOIN token_intent_resolutions
    ON token_intent_resolutions.intent_id = token_intents.intent_id
   AND token_intent_resolutions.event_id = events.event_id
   AND token_intent_resolutions.target_type = requested_events.target_type_key
   AND token_intent_resolutions.target_id = requested_events.identity_id
   AND token_intent_resolutions.is_current = true
   AND token_intent_resolutions.resolver_policy_version = %s
  WHERE events.received_at_ms >= requested_events.analysis_since_ms
    AND events.received_at_ms <= requested_events.now_ms
    AND CASE WHEN requested_events.scope = 'matched' THEN events.is_watched = true ELSE true END
)
```

Test cases:

- A source-dirty claim with two event ids upserts only those two source edges.
- A second identical run returns zero changed rank-source rows.
- A changed resolution for one requested event deletes only that event edge for the old target.
- Existing older rank-source rows for the same target/window/scope remain available to `load_rows_for_requests(...)`.
- A source-dirty claim with no event ids is marked `token_radar_source_event_ids_required`.
- Market-only dirty work does not call `populate_edges_for_event_ids(...)`.

### Task 4: Hard Cut Pulse Timeline Loading to Token Radar Evidence IDs

Files:

- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/parallax/domains/pulse_lab/services/pulse_timeline_context.py`
- `src/parallax/domains/token_intel/repositories/token_target_repository.py`
- `tests/unit/test_pulse_candidate_worker.py`
- `tests/unit/test_pulse_timeline_context.py`
- `tests/unit/test_cex_binance_read_path_filters.py`

Implementation:

1. Add `TokenTargetRepository.timeline_rows_for_event_ids(...)`.
2. The new method accepts `target_type`, `target_id`, `event_ids`, `watched_only`, and `limit`.
3. The SQL must start from `unnest(%(event_ids)s::text[]) WITH ORDINALITY`, then join exact `events.event_id`, current `token_intent_resolutions`, identity, and market context.
4. Keep the existing `timeline_rows(...)` method for API/search surfaces, but remove it from Pulse runtime.
5. In `PulseCandidateWorker._asset_context()`, compute `source_event_ids = _source_event_ids(row)` before loading timeline context.
6. If `source_event_ids` is empty, return `None` and record a compact worker note or gate reason; do not fall back to target-wide timeline loading.
7. For matched scope, call the evidence loader with `watched_only=True`.
8. Move cheap trigger/gate checks before timeline hydration. If the factor gate fails, skip timeline loading entirely.
9. If existing edge state proves the candidate is unchanged and not due, skip timeline loading.
10. Build `timeline_payload` only from the event-id bounded rows.

The hot path should become:

```python
source_event_ids = _source_event_ids(row)
if not source_event_ids:
    return None

gate = self.gate_func(factor_snapshot=factor_snapshot, thresholds=self.gate_thresholds)
if not gate.passed:
    return None

if self._unchanged_edge_state_can_skip(repos, candidate_id, trigger_signature, now_ms=now_ms):
    return None

rows = repos.token_targets.timeline_rows_for_event_ids(
    target_type=target_type,
    target_id=target_id,
    event_ids=source_event_ids,
    watched_only=scope == "matched",
    limit=200,
)
```

Test cases:

- Pulse all-scope trigger calls `timeline_rows_for_event_ids(...)` with current-row `source_event_ids_json`.
- Pulse matched-scope trigger passes `watched_only=True`.
- Pulse never calls `timeline_rows(...)` in worker runtime.
- Missing `source_event_ids_json` does not load timeline rows and does not enqueue an agent job.
- Gate failure does not load timeline rows.
- Reordered source ids produce stable `timeline_signature`.

### Task 5: Hard Cut Equity Timeline Replacement No-Op and Delete Shape

Files:

- `src/parallax/domains/equity_event_intel/repositories/equity_event_repository.py`
- `src/parallax/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py`
- `tests/integration/test_equity_event_repository.py`
- `tests/architecture/test_projection_worker_idle_cost_contract.py`

Implementation:

1. Add an internal helper that loads existing timeline state with separate indexed reads. Do not use an `OR` predicate.
2. Existing-state lookup must cover:
   - incoming `row_id`s
   - scoped `company_id`s
   - scoped `company_event_id`s
3. Compare incoming row ids, payload hashes, projection versions, and stale rows before any delete.
4. If incoming payloads are identical and there are no stale scoped rows, return without deleting or upserting.
5. Split stale deletion into separate indexed statements:

```sql
DELETE FROM equity_company_timeline_rows
 WHERE company_id = ANY(%(company_ids)s::text[])
   AND NOT (row_id = ANY(%(row_ids)s::text[]));

DELETE FROM equity_company_timeline_rows
 WHERE company_event_id = ANY(%(company_event_ids)s::text[])
   AND NOT (row_id = ANY(%(row_ids)s::text[]));
```

6. Upsert only rows that are missing or whose `payload_hash` or `projection_version` changed.
7. Do not update a serving row only because `computed_at_ms` or `source_watermark_ms` advanced with an identical payload. If a downstream path truly needs pure watermark freshness, move that metadata outside the serving row in a separate follow-up.
8. Return counts from `replace_company_timeline_rows()` for observability:
   - `inserted`
   - `updated`
   - `deleted`
   - `unchanged`

Test cases:

- Existing identical row keeps the same `xmin` and `computed_at_ms`.
- Existing identical scoped event with an advanced watermark does not update the row.
- Stale rows for a scoped `company_event_id` are deleted.
- Stale rows for a scoped `company_id` are deleted.
- Rows outside the scoped company/event are not deleted.
- Repository text does not contain `company_id = ANY` and `OR company_event_id` in one delete.

### Task 6: Tighten Runtime Performance Verification Script

Files:

- `scripts/runtime_performance_root_fix_check.sh`
- `tests/unit/test_postgres_observability_scripts.py`

Implementation:

1. Keep the script focused on runtime worker SQL fingerprints.
2. Exclude one-off diagnostics from Token Radar rank-source mean checks, especially statements that only count null `source_payload_hash`.
3. Add explicit checks for:
   - event-id bounded Token Radar population query exists in pg_stat_statements after runtime work
   - old target-wide Token Radar source population query has zero calls
   - Pulse timeline target-wide query has zero runtime calls from `pulse_candidate`
   - Equity timeline delete no longer appears with an `OR` predicate
4. Keep broad pg_stat/PgBadger summary output for operator context, but fail only on runtime fingerprints.

### Task 7: Controlled Rebuild After Code and Migration

Run only after Tasks 1-6 are implemented and focused tests pass.

Preconditions:

- App workers are stopped or paused.
- Code and Alembic migration are deployed.
- `uv run parallax config` reports operator-owned config paths.
- A recent database backup exists.

Stop runtime workers in the active deployment shape. For Docker Compose:

```bash
docker compose stop app
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Clear only rebuildable Token/Equity derived state and Pulse scheduling state. Do not truncate material facts. Do not truncate Pulse agent/candidate ledgers in the default rebuild; Token Radar republication will enqueue fresh Pulse triggers, and Pulse will update candidates through the new bounded evidence path.

```sql
BEGIN;

TRUNCATE TABLE
  token_radar_rank_source_events,
  token_radar_target_features,
  token_radar_current_rows,
  token_radar_publication_state,
  token_radar_dirty_targets
RESTART IDENTITY;

TRUNCATE TABLE
  pulse_trigger_dirty_targets,
  pulse_candidate_edge_state
RESTART IDENTITY;

TRUNCATE TABLE
  equity_company_timeline_rows;

COMMIT;
```

If the operator explicitly wants a full Pulse public-surface reset, write a separate FK-aware maintenance run that includes `pulse_agent_run_steps`, `pulse_agent_runs`, `pulse_agent_jobs`, candidate edge/event tables, and `pulse_candidates` in dependency order. Do not fold that destructive reset into the default CPU hard-cut rebuild.

Re-enqueue Token Radar from event facts. Use an epoch-millis value for the lookback start; for an 8h rebuild this is `now_ms - 8 * 60 * 60 * 1000`.

```bash
uv run parallax ops enqueue-token-radar-dirty-targets --source events --since-ms "$SINCE_MS" --limit 200000 --execute
```

Re-enqueue Equity timeline only, leaving News out:

```bash
uv run parallax ops enqueue-projection-dirty-targets --domain equity --projection timeline --since-hours 72 --execute
```

Restart workers:

```bash
docker compose up -d app
```

Drain the bounded workers with the current worker config. If a one-shot CLI run is needed, run each Token Radar window/scope explicitly:

```bash
uv run parallax ops rebuild-token-radar --window 5m --scope all --limit 5000
uv run parallax ops rebuild-token-radar --window 5m --scope matched --limit 5000
uv run parallax ops rebuild-token-radar --window 1h --scope all --limit 5000
uv run parallax ops rebuild-token-radar --window 1h --scope matched --limit 5000
uv run parallax ops rebuild-token-radar --window 4h --scope all --limit 5000
uv run parallax ops rebuild-token-radar --window 4h --scope matched --limit 5000
uv run parallax ops rebuild-token-radar --window 24h --scope all --limit 5000
uv run parallax ops rebuild-token-radar --window 24h --scope matched --limit 5000
```

### Task 8: Verification Gates

Focused tests:

```bash
uv run pytest \
  tests/architecture/test_token_pulse_equity_cpu_hard_cut_contract.py \
  tests/architecture/test_worker_runtime_contracts.py \
  tests/architecture/test_projection_worker_idle_cost_contract.py \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_pulse_candidate_worker.py \
  tests/unit/test_pulse_timeline_context.py \
  tests/integration/test_token_radar_idempotency.py \
  tests/integration/test_token_radar_repository.py \
  tests/integration/test_equity_event_repository.py \
  -q
```

Schema and observability tests:

```bash
uv run pytest tests/unit/test_postgres_schema.py tests/unit/test_postgres_observability_scripts.py -q
```

Runtime checks after rebuild:

```bash
uv run parallax ops worker-status
uv run parallax ops queue-inspect --status active --limit 50
scripts/runtime_performance_root_fix_check.sh
```

Database checks:

```sql
SELECT query, calls, mean_exec_time, total_exec_time, temp_blks_written
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%'
   OR query ILIKE '%equity_company_timeline_rows%'
   OR query ILIKE '%WITH matched AS%'
ORDER BY total_exec_time DESC
LIMIT 20;
```

Acceptance targets:

- Token Radar source population no longer has the old target-wide fingerprint.
- Token Radar source population mean execution time is below 30ms after warm-up for normal dirty batches, with no multi-second p99 in the 8h window.
- Pulse candidate runtime no longer contributes material temp blocks from target-wide timeline loading.
- Equity timeline delete no longer appears as an `OR` predicate and no longer drives sequential scans on `equity_company_timeline_rows`.
- Re-running the same Token/Pulse/Equity inputs writes zero serving rows.
- `/readyz` remains healthy and worker status has no new hard-cut contract errors.

---

## Deep Review

### Why Previous Optimizations Did Not Fully Remove CPU

Token Radar moved to compact rank-source edges and added `source_payload_hash`, but the expensive part still happens before that hash gate. The runtime still rehydrates the target/window/scope source set, sorts/dedupes it, and then discovers whether anything changed. The dirty target already carries exact event ids, so the hard cut is to use that existing bounded input and delete only touched event edges.

Pulse still reconstructs broad social context after Token Radar has already selected the current evidence set. This doubles work and creates temp blocks because the query joins `events`, `token_intent_resolutions`, identity tables, market captures, and text/reference payloads before the Python scope filter. Pulse should explain the current Token Radar trigger, so the bounded evidence ids are the correct contract.

Equity already has a payload hash gate on upsert, but the delete runs before the gate. Identical timeline projections can therefore scan and delete-check on every claim. Splitting delete predicates and moving no-op detection ahead of deletes fixes the root without changing the timeline row semantics.

### Business Logic Review

Facts remain untouched. The implementation changes how derived rows are refreshed, not what facts mean.

Token Radar ranking still uses the same source-edge payload and scoring code. The only change is the source of refreshed edges: exact dirty events instead of target-wide rescans. Rebuild uses explicit ops enqueue to materialize the bounded event set.

Pulse still receives selected posts, clusters, risk flags, and timeline signatures. The selected rows come from Token Radar current evidence ids rather than a fresh 24h target scan. This keeps the agent tied to the scoring evidence and removes unrelated chatter from the hot path.

Equity timeline rows still contain the same payload fields. Identical payloads stop updating `computed_at_ms` and `source_watermark_ms` in the serving row. If a reader depends on pure watermark movement, that dependency is a metadata concern and should move out of the serving row rather than forcing churn.

### Rebuild Review

The rebuild touches only rebuildable/control tables:

- Token derived/control: `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_dirty_targets`
- Pulse scheduling state: `pulse_trigger_dirty_targets`, `pulse_candidate_edge_state`
- Equity derived: `equity_company_timeline_rows`

The default rebuild must not truncate token facts, event facts, market facts, equity company events, documents, story groups, fact candidates, provider observations, Pulse agent runs, Pulse agent jobs, or Pulse candidates.

### Rollback Review

This is a hard cut. There is no compatibility rollback path in runtime code.

If a release must be backed out:

1. Stop workers.
2. Restore the previous application image and database backup, or deploy a follow-up migration that restores the old SQL intentionally.
3. Rebuild Token Radar and Equity derived rows from material facts.

Do not reintroduce old target-wide runtime fallback SQL as an emergency branch.

### Out-of-Scope Follow-Ups

- News duplicate key and News projection hot-path cleanup.
- Narrative admission/mention semantics deadlock cleanup.
- Agent provider backlog and circuit-open remediation.
- Full macro/news PostgreSQL tuning.
