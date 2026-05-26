# PostgreSQL Runtime Root Cause Hard Cut Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan.

**Goal:** remove the remaining PostgreSQL runtime bottlenecks by cutting the per-target Token Radar query path, moving Macro request-time dedupe into a projected read model, fixing queue terminal observability, and enforcing Kappa/CQRS runtime invariants with tests and live checks.

**Architecture:** PostgreSQL remains the business truth store. Runtime workers write material facts and derived read models with exactly one writer per read model. Request paths and hot worker loops must read bounded projected tables, not rebuild history or dedupe large fact streams on demand.

**Tech Stack:** Python, psycopg / SQLAlchemy, Alembic, PostgreSQL, Docker Compose, pytest, pg_stat_statements / PoWA / pgBadger.

**Owning Spec:** `docs/superpowers/specs/active/2026-05-26-postgres-runtime-root-cause-hard-cut-cn.md`

**Working Branch:** `codex/postgres-runtime-root-cause-hard-cut`

**Worktree:** `.worktrees/postgres-runtime-root-cause-hard-cut`

**Status:** Approved for implementation in this thread on 2026-05-26.

---

## Current Evidence Snapshot

This plan is based on the live runtime snapshot taken on 2026-05-26 after the previous Docker rebuild:

- `/readyz` is up, but worker health still reports blocked/degraded queues.
- `token_radar_dirty_targets` still has rebuild-gate errors after claims have already burned attempts.
- pg_stat_statements top query is the Token Radar single-target feature query:
  - SQL fingerprint: `WITH source_intents AS MATERIALIZED (...)`
  - 3,601 calls, 26.36s total, 228,404 shared blocks read.
- Macro read APIs still run request-time `row_number()` dedupe over `macro_observations`.
- One `pulse_agent_jobs` row was observed as `running` with `attempt_count=max_attempts` for more than 8 hours.
- Terminal evidence exists but lacks a normalized reason bucket for operator triage.
- Table stats for several hot tables are stale by two to three orders of magnitude.

The root cause is mixed:

- SQL shape problem: repeated single-target historical CTE scans and request-time dedupe.
- Architecture problem: runtime request paths still do read-model construction work.
- Kappa/CQRS violation: projected read models are not fully absorbing replay/dedupe/ranking work.
- Operational hygiene problem: queue health and stats are observable, but not yet operator-actionable enough.

---

## Non-Negotiable Constraints

- Do not add compatibility flags, fallback readers, dual write paths, or shadow old paths.
- Remove or rewrite old runtime paths directly.
- `NOTIFY` remains only a wake hint; every worker must re-read PostgreSQL and run bounded catch-up.
- Provider raw frames remain inputs, not business facts.
- Derived read models must have one runtime writer and be rebuildable from facts.
- Any migration touching large existing tables must include validity checks for indexes created concurrently.
- Real-data checks must use `uv run gmgn-twitter-intel config` and report only paths / booleans / counts, never secrets.

---

## Implementation Tasks

### Task 0: Create Isolated Worktree

Create the implementation branch and worktree before code changes.

```bash
git worktree add .worktrees/postgres-runtime-root-cause-hard-cut -b codex/postgres-runtime-root-cause-hard-cut
cd .worktrees/postgres-runtime-root-cause-hard-cut
```

Sanity checks:

```bash
git status --short
uv run gmgn-twitter-intel config
```

Expected config output:

- `config_path` points at `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path` points at `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`
- secrets are not printed

---

### Task 1: Add Failing Architecture Guards First

Add tests before implementation so the hard cuts cannot regress.

Files:

- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `tests/unit/test_postgres_schema.py`

Add guards for:

1. Token Radar runtime code may not import or instantiate `TokenRadarTargetFeatureQuery`.
2. Token Radar runtime code may not contain `WITH source_intents AS MATERIALIZED`.
3. Token Radar projection worker may not call a single-target `source_rows(...)` API.
4. Macro API and request repository methods may not run `row_number()` over `macro_observations`.
5. Worker terminal schema must include `final_reason_bucket`.
6. Alembic migrations that create concurrent indexes must include an invalid-index assertion.

Suggested architecture assertions:

```python
def test_token_radar_runtime_has_no_single_target_source_query() -> None:
    runtime_files = [
        ROOT / "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py",
        ROOT / "src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py",
    ]
    text = "\n".join(path.read_text() for path in runtime_files)
    assert "TokenRadarTargetFeatureQuery" not in text
    assert "source_rows(" not in text
    assert "WITH source_intents AS MATERIALIZED" not in text


def test_macro_request_path_has_no_observation_dedupe_window() -> None:
    request_files = [
        ROOT / "src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py",
        ROOT / "src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py",
    ]
    text = "\n".join(path.read_text() for path in request_files)
    forbidden = [
        "WITH deduped AS",
        "row_number() OVER",
        "PARTITION BY concept_key, observed_at",
    ]
    for token in forbidden:
        assert token not in text
```

Run and confirm these fail before implementation:

```bash
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_postgres_schema.py -q
```

Expected before implementation:

- architecture guards fail because old paths still exist
- no unrelated tests are changed in this task

---

### Task 2: Move Token Radar Rank Gate Before Dirty Target Claim

Current issue:

- `TokenRadarProjection.rebuild_dirty_targets()` claims dirty targets first.
- `_rank_and_hydrate_selected_rows()` discovers stale rank inputs later.
- Claimed dirty targets are marked with `token_radar_rank_inputs_require_full_rebuild`.
- Attempts are burned without productive work.

Files:

- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `tests/unit/test_token_radar_projection.py`

Add a repository readiness method:

```python
def rank_input_readiness_for_work_items(
    self,
    *,
    projection_version: str,
    work_items: Sequence[tuple[str, str]],
) -> TokenRadarRankInputReadiness:
    ...
```

Return shape:

```python
@dataclass(frozen=True)
class TokenRadarRankInputReadiness:
    ready: bool
    stale_count: int
    stale_by_work_item: dict[tuple[str, str], int]
```

Use one grouped SQL query over `token_radar_target_features`, not one query per work item:

```sql
WITH requested(window, scope) AS (
    SELECT *
    FROM unnest(%(windows)s::text[], %(scopes)s::text[])
),
stale AS (
    SELECT
        r.window,
        r.scope,
        count(*) AS stale_count
    FROM requested r
    JOIN token_radar_target_features f
      ON f.window = r.window
     AND f.scope = r.scope
    WHERE f.rank_input_projection_version IS DISTINCT FROM %(projection_version)s
    GROUP BY r.window, r.scope
)
SELECT window, scope, stale_count
FROM stale
```

Modify `rebuild_dirty_targets()` flow:

1. Resolve requested work items.
2. Check rank input readiness.
3. If blocked:
   - do not call `claim_due()`
   - do not increment dirty target attempts
   - return a structured result with `blocked_precondition=True`
   - surface `token_radar_rank_inputs_require_full_rebuild`
4. Only claim dirty targets when readiness is clean.

Test cases:

- When stale rank inputs exist, `claim_due()` is never called.
- The worker result exposes a blocked precondition and stale counts.
- Dirty target `attempt_count` does not change.
- When readiness is clean, existing claim behavior continues.

Run:

```bash
uv run pytest tests/unit/test_token_radar_projection.py -q
```

---

### Task 3: Replace Token Radar Single-Target Source Query With Batch Query

Current issue:

- `TokenRadarTargetFeatureQuery.source_rows(...)` scans historical facts once per target/window/scope.
- This creates the top pg_stat_statements fingerprint.
- Full rank rebuild also calls `score_target_window(...)` per key.

Files:

- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `tests/unit/test_token_radar_projection.py`
- `tests/unit/test_cex_binance_read_path_filters.py`

Hard cut:

- Delete the single-target runtime method `source_rows(...)`.
- Delete or rewrite `score_target_window(...)` so runtime code cannot call it.
- Replace with a batch request API that groups target/window/scope work into one bounded SQL call.

New request type:

```python
@dataclass(frozen=True)
class TokenRadarSourceRequest:
    request_key: str
    target_type_key: str
    identity_id: str
    window: str
    scope: str
    analysis_since_ms: int
    score_since_ms: int
    now_ms: int
```

New query API:

```python
class TokenRadarTargetFeatureBatchQuery:
    def source_rows_for_requests(
        self,
        requests: Sequence[TokenRadarSourceRequest],
    ) -> dict[str, list[dict[str, Any]]]:
        ...
```

SQL shape:

```sql
WITH request_targets AS (
    SELECT *
    FROM jsonb_to_recordset(%(requests_json)s::jsonb) AS r(
        request_key text,
        target_type_key text,
        identity_id text,
        window text,
        scope text,
        analysis_since_ms bigint,
        score_since_ms bigint,
        now_ms bigint
    )
),
resolved_intents AS (
    SELECT
        r.request_key,
        r.window,
        r.scope,
        r.score_since_ms,
        tir.event_id,
        tir.intent_id,
        tir.target_type_key,
        tir.identity_id
    FROM request_targets r
    JOIN token_intent_resolutions tir
      ON tir.target_type_key = r.target_type_key
     AND tir.identity_id = r.identity_id
),
source_events AS (
    SELECT
        ri.request_key,
        ri.window,
        ri.scope,
        ri.score_since_ms,
        e.*
    FROM resolved_intents ri
    JOIN events e
      ON e.id = ri.event_id
    JOIN request_targets r
      ON r.request_key = ri.request_key
    WHERE e.ingested_at_ms >= r.analysis_since_ms
      AND e.ingested_at_ms < r.now_ms
)
SELECT ...
FROM source_events se
LEFT JOIN ...
ORDER BY se.request_key, se.ingested_at_ms DESC
```

Important constraints:

- No `MATERIALIZED` CTE.
- The request set must be chunked by a fixed maximum size, for example 100 to 250 request rows, to avoid huge `jsonb_to_recordset` payloads.
- Existing `_project_group(...)` scoring logic can remain, but it should receive already-grouped source rows instead of querying the database itself.
- `rebuild_rank_inputs_full()` must use the same batch path for rebuild keys.

Projection flow:

```python
requests = self._build_source_requests(claims, work_items, now_ms=now_ms)
rows_by_request = self._source_query.source_rows_for_requests(requests)
for request in requests:
    source_rows = rows_by_request.get(request.request_key, [])
    group = self._project_group(...)
    self._persist_projected_group(...)
```

Tests:

- Batch query builds one SQL call per chunk.
- Requests include correct `analysis_since_ms` and `score_since_ms`.
- Empty source rows delete old feature payloads for the request.
- CEX/Binance read-path filter tests still prove excluded quote paths are filtered.
- Architecture guard proves runtime code has no single-target `source_rows(...)`.

Run:

```bash
uv run pytest \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_cex_binance_read_path_filters.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  -q
```

---

### Task 4: Add Macro Projected Observation Read Model

Current issue:

- Macro APIs call `latest_observations(...)`, `observations_for_concepts(...)`, and `concept_history_counts(...)`.
- Those methods run `row_number()` dedupe over `macro_observations` at request time.
- This is a request-path CQRS violation and causes temp block writes.

Files:

- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py`
- `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- `tests/unit/domains/macro_intel/test_macro_feature_engine.py`
- `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
- `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`
- `tests/unit/test_api_macro_contract.py`

Migration creates a new read model:

```sql
CREATE TABLE macro_observation_series_rows (
    projection_version text NOT NULL,
    concept_key text NOT NULL,
    observed_at timestamptz NOT NULL,
    series_rank integer NOT NULL,
    value_numeric double precision NOT NULL,
    source_name text NOT NULL,
    series_key text NOT NULL,
    source_priority integer NOT NULL,
    unit text,
    frequency text,
    data_quality text,
    source_ts timestamptz,
    raw_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingested_at_ms bigint NOT NULL,
    projected_at_ms bigint NOT NULL,
    PRIMARY KEY (projection_version, concept_key, observed_at)
);

CREATE INDEX idx_macro_observation_series_rows_lookup
    ON macro_observation_series_rows (
        projection_version,
        concept_key,
        series_rank
    );
```

Projection writer:

```python
def refresh_observation_series_rows(
    self,
    *,
    projection_version: str,
    now_ms: int,
    lookback_days: int,
    limit_per_series: int,
) -> int:
    ...
```

Allowed SQL shape inside the projection writer:

```sql
WITH source_ranked AS (
    SELECT
        concept_key,
        observed_at,
        value_numeric,
        source_name,
        series_key,
        source_priority,
        unit,
        frequency,
        data_quality,
        source_ts,
        raw_payload_json,
        ingested_at_ms,
        row_number() OVER (
            PARTITION BY concept_key, observed_at
            ORDER BY source_priority DESC, source_ts DESC NULLS LAST, ingested_at_ms DESC
        ) AS dedupe_rank
    FROM macro_observations
    WHERE observed_at >= %(min_observed_at)s
),
series_ranked AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY concept_key
            ORDER BY observed_at DESC
        ) AS series_rank
    FROM source_ranked
    WHERE dedupe_rank = 1
)
INSERT INTO macro_observation_series_rows (...)
SELECT ...
FROM series_ranked
WHERE series_rank <= %(limit_per_series)s
ON CONFLICT (...) DO UPDATE SET ...
```

Request-path methods become projected reads only:

```python
def latest_observations(...):
    SELECT ...
    FROM macro_observation_series_rows
    WHERE projection_version = %(projection_version)s
      AND series_rank = 1
    ORDER BY concept_key
```

```python
def observations_for_concepts(...):
    SELECT ...
    FROM macro_observation_series_rows
    WHERE projection_version = %(projection_version)s
      AND concept_key = ANY(%(concept_keys)s)
      AND series_rank <= %(limit_per_series)s
    ORDER BY concept_key, observed_at DESC
```

```python
def concept_history_counts(...):
    SELECT concept_key, count(*)
    FROM macro_observation_series_rows
    WHERE projection_version = %(projection_version)s
      AND concept_key = ANY(%(concept_keys)s)
    GROUP BY concept_key
```

Hard cuts:

- API routes must not query `macro_observations`.
- Existing repository method names can remain only if their SQL reads `macro_observation_series_rows`.
- No fallback from projected rows to raw observations.
- The macro projection worker must call `refresh_observation_series_rows(...)` before inserting `macro_view_snapshots`.

Tests:

- Projection worker refreshes projected rows before snapshot insert.
- API contract tests read from projected rows.
- Request repository methods contain no `row_number()` over `macro_observations`.
- History counts come from `macro_observation_series_rows`.

Run:

```bash
uv run pytest \
  tests/unit/domains/macro_intel/test_macro_feature_engine.py \
  tests/unit/domains/macro_intel/test_macro_migration_contract.py \
  tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
  tests/unit/test_api_macro_contract.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  -q
```

---

### Task 5: Normalize Queue Terminal Reasons and Stop Source-Table Terminal Scans

Current issue:

- `worker_queue_terminal_events` stores terminal evidence, but no normalized reason bucket.
- Queue health still mixes source-table terminal status scans with terminal projection counts.
- Operator triage sees the backlog but cannot group by retryable root cause quickly.

Files:

- `src/gmgn_twitter_intel/app/runtime/queue_terminal.py`
- `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/queue_ops.py`
- `tests/unit/test_queue_terminal.py`
- `tests/unit/test_queue_health.py`
- `tests/unit/test_cli_queue_ops.py`
- `tests/unit/test_postgres_schema.py`

Migration change:

```sql
ALTER TABLE worker_queue_terminal_events
    ADD COLUMN final_reason_bucket text NOT NULL DEFAULT 'other';

UPDATE worker_queue_terminal_events
SET final_reason_bucket = CASE
    WHEN final_reason ILIKE '%522%' THEN 'llm_provider_522'
    WHEN final_reason ILIKE '%retry_budget_exhausted%' THEN 'retry_budget_exhausted'
    WHEN final_reason ILIKE '%timeout%' THEN 'timeout'
    WHEN final_reason ILIKE '%provider_no_quote%' THEN 'provider_no_quote'
    WHEN final_reason ILIKE '%provider_error%' THEN 'provider_error'
    WHEN final_reason ILIKE '%no_market_data%' THEN 'no_market_data'
    WHEN final_reason ILIKE '%provider_unavailable%' THEN 'provider_unavailable'
    WHEN final_reason ILIKE '%stale%' THEN 'stale_window_ttl'
    WHEN final_reason ILIKE '%not_found%' THEN 'not_found'
    WHEN final_reason ILIKE '%semantic%' THEN 'semantic_unavailable'
    ELSE 'other'
END;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_reason_bucket_unresolved
    ON worker_queue_terminal_events (
        worker_name,
        source_table,
        final_reason_bucket,
        terminalized_at_ms DESC
    )
    WHERE operator_action IS NULL;
```

Runtime helper:

```python
def terminal_reason_bucket(final_reason: str | None, final_status: str | None) -> str:
    reason = (final_reason or "").lower()
    if "522" in reason:
        return "llm_provider_522"
    if "retry_budget_exhausted" in reason:
        return "retry_budget_exhausted"
    if "timeout" in reason:
        return "timeout"
    if "provider_no_quote" in reason:
        return "provider_no_quote"
    if "provider_error" in reason:
        return "provider_error"
    if "no_market_data" in reason:
        return "no_market_data"
    if "stale" in reason:
        return "stale_window_ttl"
    if "not_found" in reason:
        return "not_found"
    if "semantic" in reason:
        return "semantic_unavailable"
    return "other"
```

Queue health changes:

- `_terminal_projection_metrics()` returns unresolved terminal count and `reason_buckets`.
- `_status_counts()` and `_status_metrics()` count active / retryable / running statuses from source tables only.
- Source-table terminal statuses such as `done`, `dead`, `failed_exhausted`, or semantic terminal aliases are not scanned for backlog health.
- `_table_health()` uses terminal projection counts for terminal backlog.

CLI:

```bash
uv run gmgn-twitter-intel queue inspect --reason-bucket llm_provider_522
```

Tests:

- Terminal insert stores `final_reason_bucket`.
- Duplicate terminalization keeps a stable bucket unless final reason changes.
- Queue health exposes reason bucket counts.
- Queue health does not count terminal statuses from large source tables.
- CLI passes `--reason-bucket` to `inspect_terminal_events(...)`.

Run:

```bash
uv run pytest \
  tests/unit/test_queue_terminal.py \
  tests/unit/test_queue_health.py \
  tests/unit/test_cli_queue_ops.py \
  tests/unit/test_postgres_schema.py \
  -q
```

---

### Task 6: Terminalize Exhausted Stale Pulse Jobs

Current issue:

- A `pulse_agent_jobs` row can remain `running` after reaching `max_attempts`.
- Claim logic skips it because `attempt_count < max_attempts` is false.
- Queue health then reports a live running job that cannot make progress.

Files:

- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `tests/integration/test_pulse_lab_repository.py`
- `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`

Add repository method:

```python
def terminalize_exhausted_stale_running_jobs(
    self,
    *,
    now_ms: int,
    stale_after_ms: int,
    limit: int = 100,
) -> int:
    ...
```

SQL flow:

```sql
WITH candidates AS (
    SELECT id
    FROM pulse_agent_jobs
    WHERE status = 'running'
      AND attempt_count >= max_attempts
      AND updated_at_ms < %(stale_before_ms)s
    ORDER BY updated_at_ms ASC
    LIMIT %(limit)s
    FOR UPDATE SKIP LOCKED
)
UPDATE pulse_agent_jobs p
SET
    status = 'dead',
    last_error = 'stale_running_timeout',
    completed_at_ms = %(now_ms)s,
    updated_at_ms = %(now_ms)s
FROM candidates c
WHERE p.id = c.id
RETURNING p.*
```

For each returned row, write terminal evidence with:

- `worker_name='pulse_candidate'`
- `source_table='pulse_agent_jobs'`
- `final_status='dead'`
- `final_reason='stale_running_timeout'`
- `final_reason_bucket='stale_window_ttl'`

Worker integration:

- Call `terminalize_exhausted_stale_running_jobs(...)` once per pulse worker iteration before claiming new jobs.
- Do not reserve external agents for jobs that will be terminalized.
- Confirm no-start backpressure does not increment attempts.

Tests:

- Exhausted stale running job becomes `dead`.
- Terminal event is written with bucket `stale_window_ttl`.
- Non-exhausted stale running job remains eligible for normal reclaim.
- Fresh running job is untouched.
- No-start backpressure path leaves `attempt_count` unchanged.

Run:

```bash
uv run pytest \
  tests/integration/test_pulse_lab_repository.py \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py \
  tests/unit/test_queue_terminal.py \
  -q
```

---

### Task 7: Add Alembic Migration and Maintenance Checks

Add one hard-cut migration after current head `20260526_0100`.

Files:

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0101_postgres_runtime_root_cause_hard_cut.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0102_macro_observation_series_source_ts_text.py`

Migration contents:

1. Create `macro_observation_series_rows`.
2. Add `worker_queue_terminal_events.final_reason_bucket`.
3. Backfill terminal buckets.
4. Create unresolved terminal reason bucket index concurrently.
5. Add invalid-index assertion after concurrent index creation.
6. Analyze affected tables.
7. Keep `macro_observation_series_rows.source_ts` as text to match the source fact contract.

Invalid index assertion:

```sql
DO $$
DECLARE
    invalid_count integer;
BEGIN
    SELECT count(*)
    INTO invalid_count
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema()
      AND c.relname IN (
          'idx_worker_queue_terminal_reason_bucket_unresolved'
      )
      AND NOT i.indisvalid;

    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'invalid indexes detected after postgres runtime hard cut migration: %', invalid_count;
    END IF;
END $$;
```

Analyze:

```sql
ANALYZE macro_observation_series_rows;
ANALYZE worker_queue_terminal_events;
ANALYZE token_radar_target_features;
ANALYZE token_radar_dirty_targets;
ANALYZE pulse_agent_jobs;
```

Schema tests:

- migration has `down_revision = "20260526_0100"`
- terminal table includes `final_reason_bucket`
- macro read model table exists
- concurrent index migration includes invalid-index assertion

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py -q
```

---

### Task 8: Update Operational Documentation

Files:

- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/WORKER_FLOW.md`
- `docs/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`

Required doc updates:

- Token Radar section explains batch source requests and pre-claim rank readiness.
- Macro section identifies `macro_observation_series_rows` as the request read model.
- Queue section explains terminal reason buckets and active-only source health scans.
- Pulse worker section explains stale exhausted running terminalization.
- Keep `AGENTS.md` and `CLAUDE.md` links intact.

Doc verification:

```bash
rg -n "macro_observation_series_rows|final_reason_bucket|TokenRadarTargetFeatureBatchQuery|rank_input_readiness" docs src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md
```

---

## Full Verification Gates

### Static Hard-Cut Checks

```bash
rg -n "WITH source_intents AS MATERIALIZED|TokenRadarTargetFeatureQuery|source_rows\\(" \
  src/gmgn_twitter_intel/domains/token_intel
```

Expected:

- no runtime hits
- tests may mention old names only as forbidden tokens

```bash
rg -n "row_number\\(\\) OVER|WITH deduped AS|PARTITION BY concept_key, observed_at" \
  src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py \
  src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py
```

Expected:

- no request-path hits
- projection refresh SQL may contain window functions only in the method dedicated to writing `macro_observation_series_rows`

```bash
rg -n "compat|fallback|legacy_source_rows|dual_reader|shadow_reader" \
  src/gmgn_twitter_intel tests docs/superpowers/specs/active/2026-05-26-postgres-runtime-root-cause-hard-cut-cn.md
```

Expected:

- no new compatibility or fallback implementation

### Unit / Architecture / Integration Tests

```bash
uv run pytest \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  tests/unit/test_postgres_schema.py \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_cex_binance_read_path_filters.py \
  tests/unit/domains/macro_intel/test_macro_feature_engine.py \
  tests/unit/domains/macro_intel/test_macro_migration_contract.py \
  tests/unit/domains/macro_intel/test_macro_view_projection_worker.py \
  tests/unit/test_api_macro_contract.py \
  tests/unit/test_queue_terminal.py \
  tests/unit/test_queue_health.py \
  tests/unit/test_cli_queue_ops.py \
  tests/integration/test_pulse_lab_repository.py \
  tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py \
  -q
```

Then run the project gate:

```bash
make check-all
```

### Docker / Migration / Runtime Health

```bash
make docker-up
docker compose ps
curl -fsS http://127.0.0.1:8000/readyz | jq .
```

Expected:

- `postgres`, `migrate`, and `app` are healthy.
- Alembic reaches `20260526_0102`.
- `/readyz.ok == true`.
- Degraded queues, if any, report bounded active backlog and terminal reason buckets.

### PostgreSQL Live Checks

Run inside the live database container after Docker is healthy.

No invalid indexes:

```sql
SELECT
    n.nspname,
    c.relname
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT i.indisvalid;
```

Expected: zero rows.

Token Radar old fingerprint removed from new deltas:

```sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    query
FROM pg_stat_statements
WHERE query ILIKE '%WITH source_intents AS MATERIALIZED%'
ORDER BY total_exec_time DESC
LIMIT 5;
```

Expected after reset / post-deploy sampling: no new calls.

Macro request-time dedupe removed:

```sql
SELECT
    calls,
    total_exec_time,
    temp_blks_written,
    query
FROM pg_stat_statements
WHERE query ILIKE '%macro_observations%'
  AND query ILIKE '%row_number%'
ORDER BY total_exec_time DESC
LIMIT 5;
```

Expected after reset / post-deploy sampling: no request-path calls.

Token Radar rank gate no longer burns attempts:

```sql
SELECT
    last_error,
    count(*) AS rows,
    max(attempt_count) AS max_attempt_count
FROM token_radar_dirty_targets
WHERE last_error = 'token_radar_rank_inputs_require_full_rebuild'
GROUP BY last_error;
```

Expected:

- no growing count after worker cycles
- `attempt_count` does not increase when rank inputs are stale

Pulse stale running exhausted jobs are gone:

```sql
SELECT count(*)
FROM pulse_agent_jobs
WHERE status = 'running'
  AND attempt_count >= max_attempts
  AND updated_at_ms < (
      extract(epoch from now()) * 1000
  )::bigint - 900000;
```

Expected: `0`.

Terminal reason buckets are populated:

```sql
SELECT
    worker_name,
    source_table,
    final_reason_bucket,
    count(*) AS rows
FROM worker_queue_terminal_events
WHERE operator_action IS NULL
GROUP BY worker_name, source_table, final_reason_bucket
ORDER BY rows DESC
LIMIT 20;
```

Expected:

- buckets include concrete values such as `llm_provider_522`, `provider_no_quote`, `provider_unavailable`, `retry_budget_exhausted`, `semantic_unavailable`, `stale_window_ttl`, `timeout`, or `other`.

Statistics refreshed:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname IN (
    'token_intent_lookup_keys',
    'token_intent_resolutions',
    'event_anchor_backfill_jobs',
    'token_radar_target_features',
    'pulse_agent_runs',
    'worker_queue_terminal_events',
    'macro_observation_series_rows'
)
ORDER BY relname;
```

Expected:

- affected tables have recent `last_analyze` or `last_autoanalyze`
- row estimates are no longer wildly stale after normal workload sampling

### Observability Artifacts

Refresh reports after at least one worker cycle:

```bash
make postgres-observability
```

Expected artifacts:

- PoWA has fresh samples.
- pgBadger latest report is regenerated.
- `docs/generated/` or operator report paths include the latest snapshot.

Capture the comparison in the completion note:

- Token Radar old fingerprint calls before/after.
- Macro temp block writes before/after.
- Queue terminal bucket top 10.
- Pulse stale running exhausted count.
- Invalid index count.

---

## Completion Criteria

The implementation is complete only when all of these are true:

- Architecture guards pass.
- `make check-all` passes.
- Docker rebuild and migration succeed.
- `/readyz` is true.
- pg_stat_statements shows no new old Token Radar fingerprint after reset / sampling.
- Macro request endpoints read projected rows and do not run raw observation dedupe.
- Dirty target attempts no longer grow because of stale rank inputs.
- Exhausted stale running pulse jobs terminalize.
- Queue health reports normalized terminal reason buckets.
- PostgreSQL has no invalid indexes.
- Docs describe the new runtime invariant and operational checks.
