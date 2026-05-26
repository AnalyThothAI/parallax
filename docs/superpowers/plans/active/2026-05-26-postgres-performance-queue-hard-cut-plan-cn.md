# Plan — PostgreSQL Performance And Queue Backlog Hard Cut

> For implementation agents: this is a hard cut. Do not add compatibility
> flags, old SQL fallbacks, legacy config defaults, or dual worker paths.

**Status**: Draft
**Date**: 2026-05-26
**Owning spec**: `docs/superpowers/specs/active/2026-05-26-postgres-performance-queue-hard-cut-cn.md`
**Worktree**: `.worktrees/postgres-performance-queue-hard-cut/`
**Branch**: `codex/postgres-performance-queue-hard-cut`

## Pre-flight

- [ ] Spec is approved.
- [ ] Worktree exists at `.worktrees/postgres-performance-queue-hard-cut/`.
- [ ] `git branch --show-current` returns `codex/postgres-performance-queue-hard-cut`.
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
  ADD COLUMN IF NOT EXISTS social_heat_raw_score double precision,
  ADD COLUMN IF NOT EXISTS social_heat_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS social_propagation_raw_score double precision,
  ADD COLUMN IF NOT EXISTS social_propagation_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS semantic_catalyst_raw_score double precision,
  ADD COLUMN IF NOT EXISTS semantic_catalyst_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS timing_risk_raw_score double precision,
  ADD COLUMN IF NOT EXISTS timing_risk_weight double precision NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_high_confidence_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_kol_mentions integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_public_followup_authors integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_first_seen_global_24h boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS cohort_symbol text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS raw_composite_score double precision,
  ADD COLUMN IF NOT EXISTS gates_max_decision text NOT NULL DEFAULT 'discard';
```

Backfill existing feature rows once in the migration. The table is currently
small enough that a single update is acceptable, but keep the SQL pure and
deterministic:

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
  gates_max_decision = COALESCE(NULLIF(factor_snapshot_json #>> '{gates,max_decision}', ''), 'discard'),
  cohort_symbol = upper(COALESCE(NULLIF(factor_snapshot_json #>> '{subject,symbol}', ''), ''));
```

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
  );

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_anchor_backfill_jobs_unfinished_created
  ON event_anchor_backfill_jobs(created_at_ms ASC, event_id ASC, intent_id ASC)
  WHERE status <> 'done';

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
  raw_composite_score,
  gates_max_decision,
  payload_hash,
  last_scored_at_ms
FROM token_radar_target_features
WHERE projection_version = %s
  AND "window" = %s
  AND scope = %s
ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
```

- Add `load_target_feature_payloads_for_ranked_keys(...)` that loads
  `factor_snapshot_json`, `source_event_ids_json`, `source_intent_ids_json`,
  and `source_resolution_ids_json` only for the final selected rows.
- Update `_target_feature_payload(...)` so every feature upsert writes the new
  scalar columns in the same statement as `factor_snapshot_json`.

Service changes:

- Replace `_apply_cross_section(feature_rows)` with a compact-input ranker:
  `rank_compact_inputs(rank_inputs)`.
- Select top `limit` rows per lane from compact rank outputs.
- Hydrate only selected rows through
  `load_target_feature_payloads_for_ranked_keys(...)`.
- Patch normalization fields into the selected rows' factor snapshots before
  `publish_rows(...)`.
- Keep business ranking semantics identical: same factor families, same cohort
  definition, same decision gates, same current/history/audit output shape.

Tests:

- Red test first: the rank-set repository test fails if SQL contains
  `SELECT * FROM token_radar_target_features`.
- Parity test: given fixture factor snapshots, old expected rank order and new
  compact rank order are identical.
- Hydration test: repository loads JSON payloads only for selected ranked keys,
  not for every rank input.
- Contract test: `rg "list_target_features_for_rank_set|SELECT \\*" src/gmgn_twitter_intel/domains/token_intel` does not find the old rank-set path.

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
- Optionally add a local throttle inside `TokenRadarProjection.refresh_rank_set`
  so stale cleanup runs once per projection/window/scope cadence, not once per
  every rank refresh. If added, make it a code rule, not config.

Acceptance evidence:

```sql
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM token_intent_lookup_keys
WHERE intent_id = '<existing-intent-id-in-test-db>';

EXPLAIN (ANALYZE, BUFFERS)
UPDATE projection_runs
SET status = 'abandoned', finished_at_ms = 0, error = 'stale_running_timeout'
WHERE projection_name = 'token-radar'
  AND projection_version = 'token-radar-v13-social-attention'
  AND status = 'running'
  AND started_at_ms < 0;
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

One-time reconciliation:

- Add an ops command only if needed for existing historical rows:
  `gmgn-twitter-intel ops reconcile-event-anchor-jobs --limit N --execute`.
- The command is not used by normal runtime.
- The command either marks ready historical rows done or writes terminal
  evidence, then exits. It requires `--execute`.

Tests:

- Architecture test fails if `mark_ready_jobs_done` appears in runtime code.
- Unit test asserts `run_once()` with no due rows does not query
  `enriched_events`.
- Integration `EXPLAIN` for the historical reconcile command proves it uses
  `idx_event_anchor_backfill_jobs_unfinished_created` and
  `idx_enriched_events_ready_anchor`.

## Phase 5 — Queue Terminal Evidence And Operator Actions

Create:

- `src/gmgn_twitter_intel/app/runtime/queue_terminal.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/queue_ops.py`
- `tests/unit/test_queue_terminal.py`
- `tests/unit/test_cli_queue_ops.py`

Migration additions in `20260526_0099`:

```sql
CREATE TABLE IF NOT EXISTS worker_queue_terminal_events(
  terminal_id text PRIMARY KEY,
  worker_name text NOT NULL,
  source_table text NOT NULL,
  target_key text NOT NULL,
  final_status text NOT NULL,
  final_reason text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  payload_hash text,
  first_seen_at_ms bigint,
  last_attempted_at_ms bigint,
  terminalized_at_ms bigint NOT NULL,
  operator_action text,
  operator_reason text,
  operator_action_at_ms bigint
);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_target
  ON worker_queue_terminal_events(worker_name, source_table, target_key, payload_hash);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_unresolved
  ON worker_queue_terminal_events(worker_name, source_table, terminalized_at_ms DESC)
  WHERE operator_action IS NULL;
```

Runtime changes:

- `resolution_refresh` enforces a fixed max attempt budget for
  `token_discovery_dirty_lookup_keys`.
- Exhausted lookup keys write `worker_queue_terminal_events`, then delete from
  active `token_discovery_dirty_lookup_keys`.
- Event anchor, Pulse, enrichment, and mention semantics terminal rows are
  surfaced through the same terminal-event repository. Do not mutate their
  business facts.

CLI changes:

Extend `src/gmgn_twitter_intel/app/surfaces/cli/parser.py` with:

```text
gmgn-twitter-intel ops queue-inspect --worker <name> [--status terminal|active] [--limit N]
gmgn-twitter-intel ops queue-resolve --worker <name> --target-key <key> --action retry|quarantine|archive --reason <text> --execute
```

Rules:

- `queue-inspect` is read-only.
- `queue-resolve` requires `--execute`.
- `retry` re-enqueues only through the owning repository method.
- `archive` marks terminal evidence resolved and does not recreate active work.
- `quarantine` keeps terminal evidence unresolved but suppresses active retry.
- No command prints payload secrets.

Queue health changes:

- Add `terminal_count` and `unresolved_terminal_count`.
- `queue_depth` means active non-done work.
- `blocked_count` means active blocked work plus unresolved terminal evidence.
- Keep per-lane aggregation in `worker_status.py`.

Readiness contract changes:

- Modify `app.runtime.queue_health` so queue-table/query failures are returned
  as explicit adapter errors. Do not silently swallow adapter failures.
- Modify `fill_worker_queue_healths(...)` so each worker/lane can distinguish:
  active backlog, unresolved terminal evidence, table unavailable, manifest
  queue mismatch, and adapter query failure.
- Modify `app.surfaces.api.app.readiness_payload(...)` so it computes worker
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
  propagation and manifest/table mismatch reporting.

Tests:

- Queue terminal repository idempotency test.
- CLI dry-run/execute tests.
- Queue health test with active due rows, running leases, and terminal evidence.
- Readiness test proving queue adapter failure makes `/readyz` unhealthy while
  ordinary backlog keeps `/readyz` healthy.
- Architecture test ensures ops queue code writes only control/terminal tables,
  not business fact tables.

## Phase 6 — Macro Read Path Follow-up

This is P1 and may be a second PR if Phase 2 to Phase 5 are already large.

Modify:

- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/domains/macro_intel/runtime/*`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py`

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
- Configure the local server with a non-disabled frequency and bounded
  retention.
- Do not rely only on current snapshot tables.

Script:

```bash
#!/usr/bin/env bash
set -euo pipefail
docker compose exec -T postgres psql -U gmgn_app -d powa -v ON_ERROR_STOP=1 <<'SQL'
UPDATE powa_servers
SET frequency = 300,
    powa_coalesce = 100,
    retention = interval '7 days'
WHERE id = 0;
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

## Phase 8 — Documentation

Update:

- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/CONTRACTS.md`
- `docs/generated/postgres-observability/postgres-production-performance-analysis-2026-05-26-cn.md`

Required doc changes:

- Document active vs terminal queue semantics.
- Document that `/readyz` does not fail on ordinary backlog.
- Document PostgreSQL observation commands and pgBadger/PoWA use.
- Document no compatibility flags for performance hard cuts.
- Add final before/after query metrics.

## PR Breakdown

1. **PR 1 — storage and rank hot path**:
   migration, Token Radar scalar rank columns, narrow rank path, tests,
   `EXPLAIN` evidence.
2. **PR 2 — cleanup scans and queue terminalization**:
   event-anchor runtime scan deletion, projection/lookup verification,
   terminal evidence table, queue ops CLI, queue health semantics.
3. **PR 3 — PoWA and docs**:
   PoWA configuration script, docs, pgBadger/PoWA verification.
4. **PR 4 — macro materialization**:
   only if not included in PR 1 to PR 3; it is separable and should not block
   the P0 Token Radar/lookup-key fixes.

## Rollout Order

1. Create implementation worktree from the approved base.
2. Run baseline commands from Phase 0.
3. Apply migration locally and run targeted tests.
4. Rebuild Docker:

   ```bash
   docker compose up -d --build app
   ```

5. Confirm `migrate` exits 0 and app/postgres are healthy.
6. Run PoWA configure script.
7. Run targeted `EXPLAIN (ANALYZE, BUFFERS)` checks.
8. Observe one live interval:
   `/readyz`, `pg_stat_statements`, `pg_stat_kcache`, pgBadger report, PoWA
   current/history counts.
9. Run queue terminal inspect in dry-run mode.
10. Only after reviewing terminal rows, run queue resolve commands with
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
ORDER BY total_exec_time DESC
LIMIT 20;"
```

Expected: no old wide `SELECT * FROM token_radar_target_features` rank-set query
in Top 10 after one observation window.

AC2:

```bash
uv run pytest tests/unit/test_token_intent_lookup_repository.py tests/unit/test_postgres_schema.py -q
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -P pager=off -c "
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM token_intent_lookup_keys
WHERE intent_id = 'nonexistent-verification-intent';"
```

Expected: index plan using `idx_token_intent_lookup_keys_intent_lookup`.

AC3:

```bash
uv run pytest tests/unit/test_event_anchor_backfill_worker.py -q
rg "mark_ready_jobs_done" src/gmgn_twitter_intel tests
```

Expected: no runtime method or broad-scan repository method remains.

AC4:

```bash
uv run pytest tests/integration/test_projection_repository.py -q
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -P pager=off -c "
EXPLAIN (ANALYZE, BUFFERS)
UPDATE projection_runs
SET status = 'abandoned', finished_at_ms = 0, error = 'stale_running_timeout'
WHERE projection_name = 'token-radar'
  AND projection_version = 'token-radar-v13-social-attention'
  AND status = 'running'
  AND started_at_ms < 0;"
```

Expected: partial index plan using `idx_projection_runs_running_stale`.

AC5 and AC6:

```bash
uv run pytest tests/unit/test_queue_health.py tests/unit/test_queue_terminal.py tests/unit/test_cli_queue_ops.py -q
curl -sS http://127.0.0.1:8765/readyz | jq '.worker_lanes'
uv run gmgn-twitter-intel ops queue-inspect --worker resolution_refresh --limit 20
```

Expected: active vs terminal queue counts are visible, readiness stays true for
ordinary backlog, and terminal evidence is inspectable.

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
