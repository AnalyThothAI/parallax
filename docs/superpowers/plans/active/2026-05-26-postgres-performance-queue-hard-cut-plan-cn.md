# Plan — PostgreSQL Performance And Queue Backlog Hard Cut

> For implementation agents: this is a hard cut. Do not add compatibility
> flags, old SQL fallbacks, legacy config defaults, or dual worker paths.

**Status**: Draft
**Date**: 2026-05-26
**Owning spec**: `docs/superpowers/specs/active/2026-05-26-postgres-performance-queue-hard-cut-cn.md`
**Worktree**: `.worktrees/postgres-performance-queue-hard-cut/`
**Branch**: `codex/postgres-performance-queue-hard-cut`

## Review Gate

Subagent review found the first draft was directionally correct but not
implementation-ready. This revision treats the following as hard blockers:

- no migration revision may be modified after it lands on `main`;
- no phase may depend on a migration that is marked optional or assigned to a
  later PR;
- no broad production `EXPLAIN (ANALYZE)` may mutate rows outside an explicit
  `BEGIN ... ROLLBACK`;
- Token Radar compact rank inputs must include every current `_rank_key`
  tie-breaker and must hydrate by matching `payload_hash`;
- terminal queue evidence must be idempotent when payload hashes are absent and
  must keep a full source row snapshot for owner-repository retry;
- active queue state and terminal operator state must have one declared owner
  per table.

## Pre-flight

- [ ] Spec is approved.
- [ ] Worktree exists at `.worktrees/postgres-performance-queue-hard-cut/`.
- [ ] `git branch --show-current` returns `codex/postgres-performance-queue-hard-cut`.
- [ ] Migration sequence is assigned before coding:
  - `20260526_0099`: PostgreSQL hot-path storage/index changes.
  - `20260526_0100`: queue terminal evidence and queue-health contract changes.
  - `20260526_0101`: macro latest-row materialization, only if Phase 6 lands in
    this same branch.
- [ ] Baseline `uv run ruff check .` is recorded.
- [ ] Baseline targeted tests are recorded.
- [ ] Baseline `/readyz`, `pg_stat_statements`, `pg_stat_kcache`, queue
  health, pgBadger, and PoWA current/history counts are recorded.

Known baseline risks:

- The current main worktree already contains observability and queue-health
  edits. Create the implementation worktree only after deciding whether to base
  it on local `main` or after committing the current docs/runtime work.
- Live PostgreSQL is production. Do not reset statistics, drop indexes, or
  archive terminal queue rows without explicit operator approval.
- Do not keep runtime fallback branches or old SQL paths. Migration DDL may use
  `IF NOT EXISTS` only for re-entrant live migration safety after a failed
  partial production attempt; concurrent index creation still intentionally does
  not use `IF NOT EXISTS`, and invalid indexes fail loudly.

## Phase 0 — Baseline Evidence

Record these outputs before code changes:

```bash
uv run gmgn-twitter-intel config
curl -sS http://127.0.0.1:8765/readyz | jq '{ok,reasons,worker_lanes}'
docker compose ps --all
./scripts/pgbadger_report.sh
```

PostgreSQL baseline:

```sql
SELECT calls, total_exec_time, mean_exec_time, rows,
       shared_blks_hit, shared_blks_read, temp_blks_written,
       left(regexp_replace(query, '\s+', ' ', 'g'), 220) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

SELECT round((exec_user_time + exec_system_time)::numeric, 2) AS exec_cpu_s,
       exec_reads_blks, exec_writes_blks,
       left(regexp_replace(query, '\s+', ' ', 'g'), 220) AS query
FROM pg_stat_kcache_detail
WHERE datname = 'gmgn_twitter_intel'
ORDER BY (exec_user_time + exec_system_time) DESC
LIMIT 20;
```

Queue baseline:

```sql
SELECT status, count(*), max(attempt_count)
FROM event_anchor_backfill_jobs
GROUP BY status
ORDER BY count DESC;

SELECT status, count(*), max(attempt_count)
FROM pulse_agent_jobs
GROUP BY status
ORDER BY count DESC;

SELECT status, count(*), max(attempt_count)
FROM enrichment_jobs
GROUP BY status
ORDER BY count DESC;

SELECT status, count(*), max(attempt_count)
FROM token_mention_semantics
GROUP BY status
ORDER BY count DESC;

SELECT count(*) AS total,
       count(*) FILTER (
         WHERE due_at_ms <= (extract(epoch from now())*1000)::bigint
           AND (leased_until_ms IS NULL OR leased_until_ms <= (extract(epoch from now())*1000)::bigint)
       ) AS due,
       count(*) FILTER (WHERE leased_until_ms > (extract(epoch from now())*1000)::bigint) AS running,
       count(*) FILTER (WHERE last_error IS NOT NULL AND last_error <> '') AS with_error,
       max(attempt_count) AS max_attempt
FROM token_discovery_dirty_lookup_keys;
```

## Phase 0.5 — Production Migration Safety Gates

Before applying any live migration, record:

```sql
SELECT relname,
       reltuples::bigint AS estimated_rows,
       pg_size_pretty(pg_total_relation_size(oid)) AS total_size
FROM pg_class
WHERE relname IN (
  'token_radar_target_features',
  'token_intent_lookup_keys',
  'event_anchor_backfill_jobs',
  'enriched_events',
  'projection_runs'
)
ORDER BY pg_total_relation_size(oid) DESC;

SELECT pid, application_name, state, wait_event_type, wait_event,
       now() - xact_start AS xact_age,
       left(query, 160) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_age DESC NULLS LAST;
```

Migration implementation rules:

- Set local `lock_timeout` and `statement_timeout` inside the migration before
  live-table DDL/backfill. Fail fast on lock contention.
- Use `op.get_context().autocommit_block()` for every `CREATE INDEX
  CONCURRENTLY` and `DROP INDEX CONCURRENTLY`.
- If `token_radar_target_features` is above the approved row/size gate,
  backfill recoverable scalar columns in bounded chunks by primary key. Do not
  run a single unbounded update on the live table.
- Run `ANALYZE` on changed hot tables after DDL/backfill.
- Check for invalid indexes after concurrent index work:

  ```sql
  SELECT indexrelid::regclass AS index_name
  FROM pg_index
  WHERE NOT indisvalid
    AND indexrelid::regclass::text LIKE ANY (ARRAY[
      'idx_token_intent_lookup_keys_intent_lookup%',
      'idx_token_radar_target_features_rank_v2%',
      'idx_event_anchor_backfill_jobs_pending_created%',
      'idx_enriched_events_ready_anchor%',
      'idx_projection_runs_running_stale%'
    ]);
  ```

- Live lock monitoring is part of rollout. If a migration waits on a lock,
  stop and diagnose with `pg_blocking_pids`, not by raising timeouts.

## Phase 1 — Storage Hard Cut Migration

Create:

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py`

Revision metadata:

```python
revision = "20260526_0099"
down_revision = "20260525_0098"
```

Add Token Radar scalar rank input columns to `token_radar_target_features`.
They are derived columns owned by the Token Radar projection writer, not a
second source of truth.

```sql
ALTER TABLE token_radar_target_features
  ADD COLUMN social_heat_raw_score double precision,
  ADD COLUMN social_heat_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN social_propagation_raw_score double precision,
  ADD COLUMN social_propagation_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN semantic_catalyst_raw_score double precision,
  ADD COLUMN semantic_catalyst_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN timing_risk_raw_score double precision,
  ADD COLUMN timing_risk_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN cohort_high_confidence_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN cohort_kol_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN cohort_public_followup_authors integer NOT NULL DEFAULT 0,
  ADD COLUMN cohort_first_seen_global_24h boolean NOT NULL DEFAULT false,
  ADD COLUMN cohort_symbol text NOT NULL DEFAULT '',
  ADD COLUMN social_heat_watched_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN social_heat_mentions_1h integer NOT NULL DEFAULT 0,
  ADD COLUMN social_propagation_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN social_heat_latest_seen_ms bigint,
  ADD COLUMN raw_composite_score double precision,
  ADD COLUMN recommended_decision text NOT NULL DEFAULT 'discard',
  ADD COLUMN gates_max_decision text NOT NULL DEFAULT 'discard',
  ADD COLUMN rank_input_version text NOT NULL DEFAULT 'legacy_needs_rebuild';
```

Backfill only scalar fields that are recoverable from persisted
`factor_snapshot_json`. Existing rows do not persist all cohort inputs required
by the new compact rank-input path, so the migration must leave
`rank_input_version='legacy_needs_rebuild'` for pre-existing rows. The compact
rank query will not read those rows until the mandatory post-migration rebuild
rewrites them through `upsert_target_feature(...)`.

```sql
UPDATE token_radar_target_features
SET
  social_heat_raw_score = COALESCE(
    NULLIF(factor_snapshot_json #>> '{families,social_heat,raw_score}', '')::double precision,
    NULLIF(factor_snapshot_json #>> '{families,social_heat,score}', '')::double precision
  ),
  social_heat_weight = COALESCE(NULLIF(factor_snapshot_json #>> '{families,social_heat,weight}', '')::double precision, 0),
  social_propagation_raw_score = COALESCE(
    NULLIF(factor_snapshot_json #>> '{families,social_propagation,raw_score}', '')::double precision,
    NULLIF(factor_snapshot_json #>> '{families,social_propagation,score}', '')::double precision
  ),
  social_propagation_weight = COALESCE(NULLIF(factor_snapshot_json #>> '{families,social_propagation,weight}', '')::double precision, 0),
  semantic_catalyst_raw_score = COALESCE(
    NULLIF(factor_snapshot_json #>> '{families,semantic_catalyst,raw_score}', '')::double precision,
    NULLIF(factor_snapshot_json #>> '{families,semantic_catalyst,score}', '')::double precision
  ),
  semantic_catalyst_weight = COALESCE(NULLIF(factor_snapshot_json #>> '{families,semantic_catalyst,weight}', '')::double precision, 0),
  timing_risk_raw_score = COALESCE(
    NULLIF(factor_snapshot_json #>> '{families,timing_risk,raw_score}', '')::double precision,
    NULLIF(factor_snapshot_json #>> '{families,timing_risk,score}', '')::double precision
  ),
  timing_risk_weight = COALESCE(NULLIF(factor_snapshot_json #>> '{families,timing_risk,weight}', '')::double precision, 0),
  raw_composite_score = COALESCE(
    NULLIF(factor_snapshot_json #>> '{composite,rank_score}', '')::double precision,
    NULLIF(factor_snapshot_json #>> '{composite,raw_alpha_score}', '')::double precision
  ),
  recommended_decision = COALESCE(NULLIF(factor_snapshot_json #>> '{composite,recommended_decision}', ''), 'discard'),
  gates_max_decision = COALESCE(NULLIF(factor_snapshot_json #>> '{gates,max_decision}', ''), 'discard'),
  cohort_symbol = upper(COALESCE(NULLIF(factor_snapshot_json #>> '{subject,symbol}', ''), '')),
  social_heat_watched_mentions = COALESCE(NULLIF(factor_snapshot_json #>> '{families,social_heat,facts,watched_mentions}', '')::integer, 0),
  social_heat_mentions_1h = COALESCE(NULLIF(factor_snapshot_json #>> '{families,social_heat,facts,mentions_1h}', '')::integer, 0),
  social_propagation_mentions = COALESCE(NULLIF(factor_snapshot_json #>> '{families,social_propagation,facts,mentions}', '')::integer, 0),
  social_heat_latest_seen_ms = NULLIF(factor_snapshot_json #>> '{families,social_heat,facts,latest_seen_ms}', '')::bigint;
```

Mandatory rebuild:

- Add an ops command:
  `gmgn-twitter-intel ops rebuild-token-radar-rank-inputs --execute --reason <text>`.
- The command enqueues or recomputes every currently publishable Token Radar
  target through the owner projection path so all scalar rank columns, cohort
  counters, tie-breakers, and `rank_input_version` are written by the same code
  that writes `factor_snapshot_json`.
- Rollout cannot claim AC1 until this command has completed and a compact rank
  parity check has passed.

Use `op.get_context().autocommit_block()` for concurrent index work:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_lookup_keys_intent_lookup
  ON token_intent_lookup_keys(intent_id, lookup_key);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_rank_v2
  ON token_radar_target_features(
    projection_version,
    "window",
    scope,
    lane DESC,
    rank_score DESC,
    latest_event_received_at_ms DESC,
    identity_id ASC
  )
  WHERE rank_input_version = 'token-radar-rank-input-v1';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_anchor_backfill_jobs_pending_created
  ON event_anchor_backfill_jobs(created_at_ms ASC, event_id ASC, intent_id ASC)
  WHERE status = 'pending';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enriched_events_ready_anchor
  ON enriched_events(event_id ASC, intent_id ASC)
  WHERE capture_method <> 'unavailable'
    AND tick_id IS NOT NULL
    AND tick_lag_ms IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projection_runs_running_stale
  ON projection_runs(projection_name, projection_version, started_at_ms ASC)
  WHERE status = 'running';
```

Do not drop suspected unused indexes in this migration. Drop only an index that
the same PR fully supersedes and verifies. If the Token Radar rank path no
longer uses `idx_token_radar_target_features_rank`, drop it in the same
revision after the new v2 index exists:

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_rank;
```

Tests:

- `tests/unit/test_postgres_schema.py::test_postgres_performance_queue_hard_cut_indexes`
  asserts the new columns, concurrent indexes, and downgrade drops.
- Architecture tests assert no migration creates non-concurrent indexes on the
  listed live tables.

## Phase 2 — Token Radar Narrow Rank Path

Modify:

- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `tests/unit/test_token_radar_repository.py`
- `tests/unit/test_token_radar_projection.py`

Repository changes:

- Replace `list_target_features_for_rank_set(...)` with
  `list_rank_inputs_for_rank_set(...)`.
- Delete the old wide-rank method and its tests. No compatibility alias.
- `list_rank_inputs_for_rank_set(...)` selects only scalar columns:

```sql
SELECT
  projection_version,
  "window",
  scope,
  lane,
  target_type_key,
  identity_id,
  target_type,
  target_id,
  pricefeed_id,
  latest_event_received_at_ms,
  latest_market_observed_at_ms,
  social_heat_raw_score,
  social_heat_weight,
  social_propagation_raw_score,
  social_propagation_weight,
  semantic_catalyst_raw_score,
  semantic_catalyst_weight,
  timing_risk_raw_score,
  timing_risk_weight,
  cohort_high_confidence_mentions,
  cohort_kol_mentions,
  cohort_public_followup_authors,
  cohort_first_seen_global_24h,
  cohort_symbol,
  social_heat_watched_mentions,
  social_heat_mentions_1h,
  social_propagation_mentions,
  social_heat_latest_seen_ms,
  raw_composite_score,
  recommended_decision,
  gates_max_decision,
  rank_input_version,
  payload_hash,
  last_scored_at_ms
FROM token_radar_target_features
WHERE projection_version = %s
  AND "window" = %s
  AND scope = %s
  AND rank_input_version = %s
ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
```

- Add `load_target_feature_payloads_for_ranked_keys(...)` that loads
  `factor_snapshot_json`, `source_event_ids_json`, `source_intent_ids_json`,
  and `source_resolution_ids_json` only for the final selected rows.
- Hydration must match `(projection_version, window, scope, lane,
  target_type_key, identity_id, payload_hash)`. If any selected key's
  `payload_hash` no longer matches, abort that refresh and re-run compact
  ranking rather than publishing rows ranked from one source snapshot and
  explained by another.
- Update `_target_feature_payload(...)` so every feature upsert writes the new
  scalar columns in the same statement as `factor_snapshot_json`.
- The upsert writes `rank_input_version='token-radar-rank-input-v1'` only after
  all scalar fields, cohort counters, tie-breaker fields, and payload JSON are
  generated from the same in-memory projected row.

Service changes:

- Remove the old full-payload cross-section runtime path and use only the
  compact-input ranker: `rank_compact_inputs(rank_inputs)`.
- The compact ranker must reproduce current `_rank_key(...)` exactly:
  `recommended_decision`, normalized `rank_score`,
  `social_heat_watched_mentions`, `social_heat_mentions_1h` falling back to
  `social_propagation_mentions`, and `social_heat_latest_seen_ms`.
- Select top `limit` rows per lane from compact rank outputs.
- Hydrate only selected rows through
  `load_target_feature_payloads_for_ranked_keys(...)`.
- Patch normalization fields into the selected rows' factor snapshots before
  `publish_rows(...)`.
- Preserve the selected-row public runtime contract currently provided by
  `_row_from_target_feature(...)`: hydrated rows must include `intent_json`,
  `target_json`, `resolution_json`, `data_health_json`, source id arrays,
  `factor_version`, `decision`, and `rank_score` in the same shape consumed by
  `publish_rows(...)`, current rows, rank history, and snapshot audit.
- Keep business ranking semantics identical: same factor families, same cohort
  definition, same decision gates, same current/history/audit output shape.

Tests:

- Red test first: the rank-set repository test fails if SQL contains
  `SELECT * FROM token_radar_target_features`.
- Parity test: given fixture factor snapshots, old expected rank order and new
  compact rank order are identical, including `_rank_key(...)` tie-breakers.
- Migration parity test: seeded pre-existing target feature rows that cannot
  recover cohort scalars are excluded until the rebuild command rewrites them
  with `rank_input_version='token-radar-rank-input-v1'`.
- Hydration test: repository loads JSON payloads only for selected ranked keys,
  not for every rank input, and refuses to publish when `payload_hash` changed
  between compact rank and hydration.
- Contract test: `rg "list_target_features_for_rank_set|SELECT \\*\\s+FROM token_radar_target_features" src/gmgn_twitter_intel/domains/token_intel` does not find the old rank-set path.

## Phase 3 — Lookup-Key And Projection Cleanup

Modify:

- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_intent_lookup_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/projection_repository.py`
- `tests/unit/test_token_intent_lookup_repository.py`
- `tests/integration/test_projection_repository.py`

Lookup-key changes:

- Keep `replace_lookup_keys(...)` semantics.
- Do not add a compatibility write path.
- Verify `keys_for_intent(...)` and delete-by-intent both use
  `idx_token_intent_lookup_keys_intent_lookup`.

Projection stale cleanup:

- Add `ProjectionRepository.mark_stale_running_runs(...)` tests asserting the
  SQL still filters `status = 'running'`.
- Add an integration `EXPLAIN` assertion that the plan uses
  `idx_projection_runs_running_stale`.
- Add a local throttle inside `TokenRadarProjection.refresh_rank_set`
  so stale cleanup runs once per projection/window/scope cadence, not once per
  every rank refresh. This is a code rule, not config.

Acceptance evidence:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM token_intent_lookup_keys
WHERE intent_id = '<sample-existing-intent-id>';
ROLLBACK;

BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE projection_runs
SET status = 'abandoned', finished_at_ms = 0, error = 'stale_running_timeout'
WHERE projection_name = 'token-radar'
  AND projection_version = 'token-radar-v13-social-attention'
  AND status = 'running'
  AND started_at_ms < 0;
ROLLBACK;
```

## Phase 4 — Event Anchor Runtime Cleanup Hard Cut

Modify:

- `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- `tests/unit/test_event_anchor_backfill_worker.py`

Hard cut:

- Delete `EventAnchorBackfillWorker._mark_ready_jobs_done(...)`.
- Delete `EventAnchorBackfillJobRepository.mark_ready_jobs_done(...)`.
- Remove `ready_jobs_reconciled` from normal run notes.
- Keep direct `mark_done(...)` only in the attach transaction where the worker
  successfully attaches a tick. That path already exists in
  `event_anchor_backfill_worker.py:350`.

Mandatory one-time reconciliation:

- Add an ops command for existing historical rows:
  `gmgn-twitter-intel ops reconcile-event-anchor-jobs --limit N --execute`.
- The command is not used by normal runtime.
- The command either marks ready historical rows done or writes terminal
  evidence, then exits. It requires `--execute`.
- Before deleting runtime reconciliation, record a dry-run count of
  ready-but-not-done rows and an `EXPLAIN` for the command.
- During rollout, run the command in dry-run mode first, then execute it if the
  dry run reports pending rows. After execution, assert no ready-pending rows
  remain.

Tests:

- Architecture test fails if `mark_ready_jobs_done` appears in runtime code.
- Unit test asserts `run_once()` with no due rows does not query
  `enriched_events`.
- Static guard checks `event_anchor_backfill_worker.py` and
  `event_anchor_backfill_job_repository.py` method names directly; it must not
  use a broad `rg "mark_ready_jobs_done" src tests` that catches the guard test
  itself.
- Integration `EXPLAIN` for the historical reconcile command proves it uses
  `idx_event_anchor_backfill_jobs_pending_created` and
  `idx_enriched_events_ready_anchor`.

## Phase 5 — Queue Terminal Evidence And Operator Actions

Create:

- `src/gmgn_twitter_intel/app/runtime/queue_terminal.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/queue_ops.py`
- `tests/unit/test_queue_terminal.py`
- `tests/unit/test_cli_queue_ops.py`

Create migration:

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0100_worker_queue_terminal_events.py`

Revision metadata:

```python
revision = "20260526_0100"
down_revision = "20260526_0099"
```

```sql
CREATE TABLE IF NOT EXISTS worker_queue_terminal_events(
  terminal_id text PRIMARY KEY,
  worker_name text NOT NULL,
  source_table text NOT NULL,
  target_key text NOT NULL,
  source_row_json jsonb NOT NULL,
  source_row_hash text NOT NULL,
  final_status text NOT NULL,
  final_reason text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  payload_hash text NOT NULL DEFAULT '',
  first_seen_at_ms bigint,
  last_attempted_at_ms bigint,
  terminalized_at_ms bigint NOT NULL,
  terminal_generation integer NOT NULL DEFAULT 1,
  operator_action text,
  operator_reason text,
  operator_action_at_ms bigint
);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_source_snapshot
  ON worker_queue_terminal_events(worker_name, source_table, target_key, source_row_hash, terminal_generation);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_one_unresolved
  ON worker_queue_terminal_events(worker_name, source_table, target_key)
  WHERE operator_action IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_unresolved
  ON worker_queue_terminal_events(worker_name, source_table, terminalized_at_ms DESC)
  WHERE operator_action IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_source
  ON worker_queue_terminal_events(source_table, worker_name);
```

Source-of-truth rules:

- Active queue tables express only claimable, retryable, or running work.
- `worker_queue_terminal_events` is the operator action surface for terminal
  queue evidence.
- Existing source-table terminal statuses (`dead`, `expired`,
  `semantic_unavailable`) remain domain control history, but queue health must
  count them as terminal evidence, not active depth. Ops writes go through
  terminal evidence plus owner-specific retry transitions, not ad hoc updates.
- Every terminal event stores `source_row_json` and `source_row_hash`. Retry
  uses that snapshot to call the owner repository transition exactly; it never
  reconstructs active work from a loose target key.

Runtime changes:

- `resolution_refresh` enforces a fixed max attempt budget for
  `token_discovery_dirty_lookup_keys`.
- The budget applies to every path that would reschedule the row, including
  provider failures and repeated `not_found` outcomes. No mark-error or
  mark-not-found path may reschedule once the claimed row is exhausted.
- Exhausted lookup keys write `worker_queue_terminal_events`, then delete from
  active `token_discovery_dirty_lookup_keys`.
- Event anchor, Pulse, enrichment, and mention semantics terminal rows are
  surfaced through the same terminal-event repository. Do not mutate their
  business facts.
- For every queue type, implement an explicit retry transition:
  - dirty lookup key: reinsert from `source_row_json` through the discovery
    repository with reset lease and bounded attempt state;
  - event anchor: transition the existing `(event_id, intent_id)` job from
    terminal control state back to pending through the event-anchor repository;
  - enrichment: transition the existing job through the enrichment repository
    instead of relying on `ON CONFLICT DO NOTHING`;
  - mention semantics: transition the existing row through the narrative
    repository instead of relying on `ON CONFLICT DO NOTHING`;
  - Pulse: transition the existing job through the Pulse jobs repository.

CLI changes:

Extend `src/gmgn_twitter_intel/app/surfaces/cli/parser.py` and wire execution
through `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py::handle_ops`.
Do not create parser-only commands.

```text
gmgn-twitter-intel ops queue-inspect [--worker <name>] [--source-table <table>] [--status terminal|active] [--limit N]
gmgn-twitter-intel ops queue-resolve --terminal-id <id> --action retry|quarantine|archive --reason <text> --execute
```

Rules:

- `queue-inspect` is read-only.
- `queue-resolve` requires `--execute`.
- `retry` resolves the current terminal event with `operator_action='retry'`
  and then recreates active work only through the owner-specific retry
  transition listed above.
- `archive` marks terminal evidence resolved and does not recreate active work.
- `quarantine` keeps terminal evidence unresolved but suppresses active retry.
- No command prints payload secrets.

Queue health changes:

- Add `terminal_count` and `unresolved_terminal_count`.
- `queue_depth` means active non-done work.
- `blocked_count` means active blocked work plus unresolved terminal evidence.
- Keep per-lane aggregation in `worker_status.py`.
- Add a queue adapter registry that declares each manifest queue table as either
  `status_queue`, `dirty_target`, or `terminal_projection`. Do not infer dirty
  target shape by fallback.
- Architecture tests must assert every manifest queue table has exactly one
  adapter spec and every adapter spec is used by at least one manifest.

Readiness contract changes:

- Modify `app.runtime.queue_health` so queue-table/query failures are returned
  as explicit adapter errors. Do not silently swallow adapter failures.
- Modify `fill_worker_queue_healths(...)` so each worker/lane can distinguish:
  active backlog, unresolved terminal evidence, table unavailable, manifest
  queue mismatch, and adapter query failure.
- Modify `app.runtime.app._readiness_payload(...)` so it computes worker
  status once, passes that status into `_unhealthy_reasons(...)`, and marks
  readiness unhealthy only for queue-health contract failures:
  unavailable queue table, manifest queue mismatch, or queue-health adapter
  query failure.
- Do not mark readiness unhealthy for ordinary active backlog, due backlog, dead
  rows, or unresolved terminal evidence. Those are operational problems exposed
  in `worker_lanes`, not service boot/readiness failures.
- Update `tests/integration/test_api_health.py::test_healthz_readyz_and_metrics_return_status`
  to cover the new readiness contract.
- Add unit tests in `tests/unit/test_queue_health.py` for adapter error
  propagation and manifest/table mismatch reporting. Cover missing connection,
  connection context-enter failure, and outer-loop adapter failure.

Tests:

- Queue terminal repository idempotency test.
- Queue terminal repository test proving NULL/empty payload hash cannot create
  duplicate terminal events.
- Runtime test proving an exhausted `resolution_refresh` dirty lookup row
  writes terminal evidence with `source_row_json` and deletes the active row.
- CLI dry-run/execute tests through `gmgn_twitter_intel.app.surfaces.cli.main`.
- Queue health test with active due rows, running leases, and terminal evidence.
- Readiness test proving queue adapter failure makes `/readyz` unhealthy while
  ordinary backlog keeps `/readyz` healthy.
- Architecture test ensures ops queue code writes only control/terminal tables,
  not business fact tables.

## Phase 6 — Macro Read Path Follow-up

This is P1. If it lands in the same branch, it uses its own migration revision.
If it lands later, it must be a separate PR with a new revision after the then
current head. Never modify `20260526_0099` or `20260526_0100` after they land.

Modify:

- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/domains/macro_intel/runtime/*`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0101_macro_latest_rows.py`

Hard cut:

- Add `macro_observation_latest_rows` or extend `macro_view_snapshots` so HTTP
  reads no longer run request-time `row_number()` dedupe over
  `macro_observations`.
- The macro projection/import path writes the deduped latest rows.
- Delete request-time dedupe query from `latest_observations(...)` and
  `observations_for_concepts(...)` where applicable.

Tests:

- Unit test fails if macro HTTP repository SQL contains
  `row_number() OVER`.
- Integration test validates macro payload equality before/after against a
  seeded dataset.
- `pg_stat_statements` after live observation no longer shows macro dedupe temp
  writes in Top mean-time queries.

## Phase 7 — PoWA Long-Term History

Modify:

- `compose.yaml`
- `scripts/powa_configure.sh`
- `docs/SETUP.md`
- `docs/RELIABILITY.md`

Hard cut:

- Keep PoWA repository in the `powa` database.
- Configure the local server in the mode actually used by this compose stack:
  verify server id `0`, installed PoWA modules, snapshot frequency, coalesce,
  and bounded retention.
- Do not rely only on current snapshot tables.
- History verification must wait for enough snapshots to pass the configured
  coalesce threshold, or temporarily lower coalesce for the verification window
  and then restore the production value.

Script:

```bash
#!/usr/bin/env bash
set -euo pipefail
docker compose exec -T postgres psql -U gmgn_app -d powa -v ON_ERROR_STOP=1 <<'SQL'
SELECT id, hostname, port, username, dbname, frequency, powa_coalesce, retention
FROM powa_servers
WHERE id = 0;

UPDATE powa_servers
SET frequency = 300,
    powa_coalesce = 5,
    retention = interval '7 days'
WHERE id = 0;

SELECT powa_take_snapshot(0);
SELECT powa_take_snapshot(0);
SELECT powa_take_snapshot(0);
SELECT powa_take_snapshot(0);
SELECT powa_take_snapshot(0);
SQL
```

Verification SQL:

```sql
SELECT count(*) FROM powa_statements_history_current;
SELECT count(*) FROM powa_statements_history;
```

Tests:

- `tests/unit/test_ops_diagnostics.py` or a shell-script harness test asserts
  the script updates frequency/retention without printing passwords.
- Verification must show both current rows and coalesced history rows are
  non-zero. If coalesce was lowered for verification, restore the production
  value and record that in the verification artefact.

## Phase 8 — Documentation

Update:

- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/CONTRACTS.md`
- `docs/generated/cli-help.md`
- `docs/generated/postgres-observability/postgres-production-performance-analysis-2026-05-26-cn.md`

Required doc changes:

- Document active vs terminal queue semantics.
- Document that `/readyz` does not fail on ordinary backlog.
- Document PostgreSQL observation commands and pgBadger/PoWA use.
- Document no compatibility flags for performance hard cuts.
- Regenerate CLI help after adding queue ops commands.
- Add final before/after query metrics.

## PR Breakdown

Preferred landing shape: one implementation branch and one PR for Phases 1 to
5 plus Phase 7 and docs. That keeps the hard cut atomic and avoids half-migrated
main.

If review size forces multiple PRs, split only at migration boundaries:

1. **PR 1 — storage and rank hot path**:
   `20260526_0099`, Token Radar scalar rank columns, mandatory rank-input
   rebuild command, narrow rank path, lookup/projection/event-anchor indexes,
   tests, and `EXPLAIN` evidence.
2. **PR 2 — queue terminalization and readiness**:
   `20260526_0100`, event-anchor runtime scan deletion, mandatory
   reconciliation command, terminal evidence table, queue ops CLI, queue health
   adapter registry, readiness contract, and tests.
3. **PR 3 — PoWA and docs**:
   PoWA configuration script, generated CLI help, docs, pgBadger/PoWA
   verification.
4. **PR 4 — macro materialization**:
   `20260526_0101`, only if macro materialization is not included earlier.

No PR may modify a migration revision that has already landed on `main`.

## Rollout Order

1. Create implementation worktree from the approved base.
2. Run baseline commands from Phase 0.
3. Apply migration locally and run targeted tests.
4. Rebuild Docker:

   ```bash
   docker compose up -d --build app
   ```

5. Confirm `migrate` exits 0 and app/postgres are healthy.
6. Run the mandatory Token Radar rank-input rebuild command and verify compact
   rank parity before judging Token Radar freshness.
7. Run mandatory event-anchor reconciliation dry run and execute only when the
   dry run reports ready-but-not-done rows.
8. Run PoWA configure script.
9. Run targeted transaction-wrapped `EXPLAIN (ANALYZE, BUFFERS)` checks.
10. Observe one live interval:
   `/readyz`, `pg_stat_statements`, `pg_stat_kcache`, pgBadger report, PoWA
   current/history counts.
11. Run queue terminal inspect in dry-run mode.
12. Only after reviewing terminal rows, run queue resolve commands with
    explicit `--execute` and reasons.

## Rollback

Code rollback:

- Revert the PR and rebuild app.
- Do not re-enable old SQL fallback code. A rollback means reverting the hard
  cut commit, not toggling runtime behavior.

Migration rollback:

- Downgrade drops new indexes concurrently and removes new scalar columns only
  after code rollback.
- Do not drop `worker_queue_terminal_events` until terminal evidence has been
  exported or confirmed unnecessary by the operator.

Queue actions:

- `archive` and `quarantine` are operator decisions. They are not automatically
  reversed.
- `retry` creates new active work through the owner repository and can be
  re-terminalized by the retry budget.

PoWA rollback:

- Reset frequency to disabled only if the operator accepts losing trend
  collection.
- Do not delete PoWA history as part of app rollback.

## Acceptance Test Commands

AC1:

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/unit/test_token_radar_projection.py -q
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -P pager=off -c "
SELECT calls, total_exec_time, left(regexp_replace(query, '\\s+', ' ', 'g'), 220) AS query
FROM pg_stat_statements
WHERE query ILIKE '%SELECT *%token_radar_target_features%'
  AND query ILIKE '%ORDER BY lane DESC, rank_score DESC%'
ORDER BY calls DESC;"
```

Expected: no old wide rank-set query is present after a controlled compact rank
refresh. Absence from Top 10 is not enough; the old normalized query must have
zero calls or be absent.

AC2:

```bash
uv run pytest tests/unit/test_token_intent_lookup_repository.py tests/unit/test_postgres_schema.py -q
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -P pager=off -c "
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM token_intent_lookup_keys
WHERE intent_id = '<sample-existing-intent-id>';
ROLLBACK;"
```

Expected: index plan using `idx_token_intent_lookup_keys_intent_lookup`.

AC3:

```bash
uv run pytest tests/unit/test_event_anchor_backfill_worker.py -q
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected: no runtime method or broad-scan repository method remains; the static
guard is method-scoped and does not fail on its own assertion text.

AC4:

```bash
uv run pytest tests/integration/test_projection_repository.py -q
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -P pager=off -c "
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE projection_runs
SET status = 'abandoned', finished_at_ms = 0, error = 'stale_running_timeout'
WHERE projection_name = 'token-radar'
  AND projection_version = 'token-radar-v13-social-attention'
  AND status = 'running'
  AND started_at_ms < 0;
ROLLBACK;"
```

Expected: partial index plan using `idx_projection_runs_running_stale`.

AC5 and AC6:

```bash
uv run pytest tests/unit/test_queue_health.py tests/unit/test_queue_terminal.py tests/unit/test_cli_queue_ops.py -q
curl -sS http://127.0.0.1:8765/readyz | jq '.worker_lanes'
uv run gmgn-twitter-intel ops queue-inspect --worker resolution_refresh --limit 20
```

Expected: active vs terminal queue counts are visible, readiness stays true for
ordinary backlog, terminal evidence is inspectable, duplicate terminalization
with empty payload hash is idempotent, and queue-resolve uses `--terminal-id`.

AC7 and AC8:

```bash
./scripts/pgbadger_report.sh
scripts/powa_configure.sh
docker compose exec -T postgres psql -U gmgn_app -d powa -P pager=off -c "
SELECT count(*) AS current_rows FROM powa_statements_history_current;
SELECT count(*) AS history_rows FROM powa_statements_history;"
```

Expected: pgBadger report exists and PoWA current/history counts are non-zero
after the configured interval.

Full changed-area verification:

```bash
uv run pytest \
  tests/unit/test_postgres_schema.py \
  tests/unit/test_token_radar_repository.py \
  tests/unit/test_token_radar_projection.py \
  tests/unit/test_token_intent_lookup_repository.py \
  tests/unit/test_event_anchor_backfill_worker.py \
  tests/unit/test_queue_health.py \
  tests/unit/test_queue_terminal.py \
  tests/unit/test_cli_queue_ops.py \
  tests/integration/test_projection_repository.py \
  tests/integration/test_api_health.py::test_healthz_readyz_and_metrics_return_status \
  tests/architecture/test_worker_runtime_contracts.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  -q

uv run ruff check src/gmgn_twitter_intel tests
make check-all
git diff --check
```

## Verification

Create a verification artefact after implementation:

- `docs/superpowers/plans/active/2026-05-26-postgres-performance-queue-hard-cut-verification-cn.md`

The verification must paste:

- targeted test output;
- Docker rebuild output summary;
- `/readyz` output summary;
- before/after Top SQL rows;
- before/after queue health rows;
- pgBadger report path and key counts;
- PoWA current/history counts;
- any queue terminal operator actions performed, with reasons.
