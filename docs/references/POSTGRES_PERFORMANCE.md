# PostgreSQL Performance And Queue Diagnostics

> **Scope.** This is the living performance playbook for the local Docker
> PostgreSQL production runtime. It covers query diagnosis, live migration
> safety, worker queue pressure, PoWA/pgBadger usage, and the current
> 2026-05-26 follow-up backlog.

## Why This Exists

`gmgn-twitter-intel` is PostgreSQL-first Kappa/CQRS. The database is not just
storage; it is the durable execution plane for facts, read models, dirty
targets, run ledgers, and queue state. Performance work must therefore preserve
these invariants:

- Material facts remain the only business truth.
- Each rebuildable read model has exactly one runtime writer.
- Dirty target tables are control plane, not business facts.
- `NOTIFY` is only a wake hint; every listener still performs bounded catch-up.
- Runtime fixes must be observable through PostgreSQL evidence, not intuition.

The 2026-05-26 hard cut proved the pattern: first make the pressure visible,
then remove the exact hot SQL or retry loop. Do not hide backlog by weakening
`/readyz`, reducing worker count, or deleting facts.

## Hot/Cold Lifecycle Contract

PostgreSQL tables are grouped by runtime temperature before any performance or
maintenance change. Hot paths stay compact and indexed by claimed work keys;
cold paths are retained by partition lifecycle, not by worker-loop deletes.

| Retention class | Tables | Lifecycle rule |
| --- | --- | --- |
| Hot compact rank/read path | `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `macro_observation_series_rows` active generation | No wide JSON/text scans. Online Token Radar reads only current rows plus publication state; `fresh` requires `ready` and matching `current_generation_id`. |
| Selected-row hydrate | `events`, `enriched_events`, `equity_event_evidence_artifacts` | Access only after ranking, document selection, or explicit evidence selection has chosen stable row ids or payload hashes. Do not join these wide payload tables into rank/discovery scans. |
| Cold audit/history | `raw_frames` and future explicit cold projections | Partition lifecycle only. Runtime workers must not issue loop deletes against audit, history, or provider raw-frame tables. |
| Control plane | Dirty targets, jobs, fetch runs | Leased, bounded, and terminal-evidence based. Queue state transitions must preserve attempts, lease ownership, payload hash/idempotency keys, and explicit terminal reasons. |

## Source Material

- Spec: `docs/superpowers/specs/active/2026-05-26-postgres-performance-queue-hard-cut-cn.md`
- Plan: `docs/superpowers/plans/active/2026-05-26-postgres-performance-queue-hard-cut-plan-cn.md`
- Baseline analysis: `docs/generated/postgres-observability/postgres-production-performance-analysis-2026-05-26-cn.md`
- Worker audit: `docs/generated/postgres-observability/worker-architecture-audit-2026-05-26.md`
- Worker contract review: `docs/generated/postgres-observability/worker-contract-spec-review-2026-05-26-cn.md`
- Operational invariants: `docs/RELIABILITY.md`
- Setup commands: `docs/SETUP.md`

External primary references:

- PostgreSQL `EXPLAIN`: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL `pg_stat_statements`: https://www.postgresql.org/docs/current/pgstatstatements.html
- PostgreSQL `CREATE INDEX CONCURRENTLY`: https://www.postgresql.org/docs/current/sql-createindex.html
- PostgreSQL `WITH` query materialization: https://www.postgresql.org/docs/current/queries-with.html
- PostgreSQL partial indexes: https://www.postgresql.org/docs/current/indexes-partial.html
- PostgreSQL `VACUUM`: https://www.postgresql.org/docs/current/sql-vacuum.html
- PostgreSQL partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- PoWA: https://powa.readthedocs.io/
- pgBadger: https://github.com/darold/pgbadger

## Observability Stack

The Docker PostgreSQL service loads:

- `pg_stat_statements`: normalized query cost, calls, rows, buffers.
- `pg_stat_kcache`: CPU and kernel I/O attribution by query.
- `pg_qualstats`: predicate and missing-index clues.
- `pg_wait_sampling`: sampled wait events.
- PoWA: time-series view over PostgreSQL statistics.
- pgBadger: log-driven report for slow statements, lock waits, deadlocks,
  checkpoints, autovacuum, and temp-file events.

Use each tool for its natural job:

| Tool | Best For | Not For |
| --- | --- | --- |
| `pg_stat_activity` | live blockers, idle transactions, long active queries | historical ranking |
| `pg_stat_statements` | cumulative Top SQL and before/after deltas | exact source row payloads |
| `EXPLAIN (ANALYZE, BUFFERS)` | proving the plan, buffers, row estimates | mutating SQL outside `BEGIN ... ROLLBACK` |
| `pg_stat_kcache` | CPU-heavy query attribution | business correctness |
| `pg_qualstats` | repeated predicates and index candidates | automatic index creation |
| PoWA | trend analysis across snapshots | immediate error logs |
| pgBadger | slow logs, temp files, lock waits, deadlocks, checkpoints | current queue state |

## Safe Baseline

Start every production diagnosis with redacted config and readiness context:

```bash
uv run gmgn-twitter-intel config
curl -sS http://127.0.0.1:8765/readyz \
  | jq '{ok,reasons,worker_count:(.workers|length), worker_lanes:.worker_lanes}'
docker compose ps --all
```

For Docker, the container paths are under `/root/.gmgn-twitter-intel/`, mounted
from the host `~/.gmgn-twitter-intel/`. Report only paths, booleans, redacted
DSNs, and diagnostic counts. Do not print config secrets.

Then capture PostgreSQL:

```sql
SELECT pid, application_name, state, wait_event_type, wait_event,
       now() - xact_start AS xact_age,
       left(query, 160) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_age DESC NULLS LAST;

SELECT blocked.pid AS blocked_pid,
       blocked.application_name AS blocked_app,
       blocking.pid AS blocking_pid,
       blocking.application_name AS blocking_app,
       left(blocked.query, 120) AS blocked_query
FROM pg_stat_activity blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocker_pid ON true
JOIN pg_stat_activity blocking ON blocking.pid = blocker_pid;

SELECT calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 3) AS mean_ms,
       rows,
       shared_blks_read,
       temp_blks_written,
       left(regexp_replace(query, '\s+', ' ', 'g'), 220) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
```

For mutating `EXPLAIN`, always wrap it:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
DELETE FROM some_table WHERE id = 'sample-id';
ROLLBACK;
```

PostgreSQL actually executes a statement under `EXPLAIN ANALYZE`; the rollback
is not optional for `INSERT`, `UPDATE`, `DELETE`, and `MERGE`.

## Runtime Performance Root Fix Hard Cut

Use `scripts/runtime_performance_root_fix_check.sh` after the runtime
performance architecture hard cut is deployed. The script is intentionally
read-only: it checks `/readyz`, Alembic head, `pg_stat_statements`, and worker
state, but it does not reset statistics, enqueue jobs, mutate rows, or change
database settings. It exits non-zero when a hard gate is over its configured
threshold.

Hard gates enforced by the check:

- Old Token Radar `WITH request_targets AS (` calls must not increase during
  the validation window when `OLD_TOKEN_RADAR_CALLS_BEFORE` is supplied.
- `token_radar_rank_source_events` query mean-time proxy must stay below
  `TOKEN_RADAR_RANK_SOURCE_MAX_MS` (default `100`), with temp block writes at
  or below `TOKEN_RADAR_TEMP_BLOCKS_MAX` (default `0`).
- The largest Token Radar SQL fingerprint must stay below 10% of total
  `pg_stat_statements.total_exec_time` for the window by default, configurable
  with `TOKEN_RADAR_TOP_SQL_SHARE_MAX`.
- Stale `equity_event_fetch_runs.status = 'running'` rows older than 15 minutes
  must be at or below `STALE_EQUITY_FETCH_RUNS_MAX` (default `0`).

The script also prints the current Alembic head. Runtime results are not
accepted unless that head corresponds to the deployed runtime performance hard
cut migration set.

The script prints a read-only lifecycle report with this CSV header:

```text
table_name,total_bytes,live_rows,dead_rows,last_analyze,retention_class,recommended_action
```

The report is advisory only. It reads `pg_stat_user_tables` and
`pg_total_relation_size(relid)` for the hot/cold lifecycle tables, then labels
each row with the retention class above. It recommends follow-up review but does
not run partition changes, heap maintenance, queue updates, or worker actions.

## Query Design Rules

### Avoid Hot-Path Wide Reads

Do not use `SELECT *` on hot tables that carry JSONB explanations, audit
payloads, or source arrays. Rank, filter, and claim from narrow scalar columns,
then hydrate only selected rows by stable key and `payload_hash`.

Current example:

- Fixed: the old Token Radar rank-set `SELECT * FROM token_radar_target_features
  ... ORDER BY lane DESC, rank_score DESC ...` path is removed from runtime.
- Fixed in the follow-up hard cut: Token Radar source hydration now builds
  bounded `TokenRadarSourceRequest` batches and uses
  `TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)`. Runtime
  code no longer calls the single-target `source_rows(...)` path or the old
  `WITH source_intents AS MATERIALIZED` query.

### Match Indexes To Real Predicates

Partial indexes work only when the query predicate implies the partial predicate.
If runtime says `status <> 'done'`, an index on `status = 'pending'` will not
prove the path. Change the runtime predicate or create the exact partial index.

Good examples from the hard cut:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_lookup_keys_intent_lookup
  ON token_intent_lookup_keys(intent_id, lookup_key);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projection_runs_running_stale
  ON projection_runs(projection_name, projection_version, started_at_ms ASC)
  WHERE status = 'running';
```

### Keep Runtime Idle Paths Bounded

A worker loop with no due work must not scan broad facts or read models to prove
nothing happened. Normal runtime work must be proportional to claimed dirty
targets or leased jobs.

Broad discovery belongs in dry-run-first ops commands that enqueue bounded work:

```bash
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --dry-run
```

### Treat Queue Terminal States As Evidence

Active queue tables should represent claimable, retryable, or running work.
Terminal outcomes must be explicit evidence with an operator action path:

```bash
uv run gmgn-twitter-intel ops queue-inspect --status terminal --limit 50
uv run gmgn-twitter-intel ops queue-resolve \
  --terminal-id <terminal-id> \
  --action retry \
  --reason "operator-reviewed provider recovery" \
  --execute
```

Do not repair terminal rows by ad hoc SQL. Retry must go through the owning
repository transition so leases, attempt counts, payload hashes, and idempotency
keys stay coherent.

### Prefer Read Models Over Request-Time Dedupe

Window functions such as `row_number() OVER (...)` are fine in offline rebuilds
or bounded projections. They are suspect in HTTP request paths when they scan
wide fact windows or write temp blocks.

The macro observation path is the current example. It should be projected into
deduped latest rows before reads, not recomputed per request.

### Batch Writes Without Losing Idempotency

High-frequency per-row upserts are acceptable during early correctness work,
but they create CPU, WAL, index, and autovacuum pressure. Convert them to
set-based writes only when the idempotency key remains the same.

Do not replace domain-specific unique constraints with a global
`worker_idempotency` table. That creates a second truth.

## Live Migration Rules

For live tables:

1. Assign a new Alembic revision. Never edit a landed migration on `main`.
2. Set `lock_timeout` and `statement_timeout`.
3. Use `op.get_context().autocommit_block()` for `CREATE INDEX CONCURRENTLY`
   and `DROP INDEX CONCURRENTLY`.
4. Backfill in bounded chunks when the table is large.
5. `ANALYZE` changed hot tables after DDL/backfill.
6. Check invalid indexes before claiming success:

```sql
SELECT indexrelid::regclass AS index_name
FROM pg_index
WHERE NOT indisvalid;
```

`CREATE INDEX CONCURRENTLY` keeps writes available, but it costs extra scans and
can leave invalid indexes if it fails. That is expected production machinery,
not a reason to build indexes the blocking way.

## Vacuum And Bloat Rules

Frequently updated queue/control tables need more aggressive attention than
append-only fact tables. Watch:

```sql
SELECT relname,
       n_live_tup,
       n_dead_tup,
       round(100.0*n_dead_tup/GREATEST(n_live_tup+n_dead_tup,1),2) AS dead_pct,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       last_autovacuum,
       last_autoanalyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 0
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Use plain `VACUUM (ANALYZE)` for routine cleanup. `VACUUM FULL` rewrites the
table and takes stronger locks; reserve it for deliberate maintenance windows.

Partitioned audit/history tables need retention policy first, index cleanup
second. Do not drop `idx_scan=0` indexes from a single short observation window.
Confirm stats reset time, rare query paths, constraints, and operator class use.

## Current Snapshot, 2026-05-26 17:40 Asia/Shanghai

Fresh local Docker evidence after the `main` merge:

- `docker compose ps`: `app` healthy, `postgres` healthy, `migrate` exited 0,
  `powa-web` running.
- `/readyz`: `ok=true`, 34 workers, 6 lanes.
- No current blockers and no `idle in transaction` sessions.
- PoWA: `powa_statements_history_current=1484`,
  `powa_statements_history=7104`.
- pgBadger latest report:
  `~/.gmgn-twitter-intel/reports/pgbadger/pgbadger-latest.html`, about 3.4 MB.
- New hot-path indexes have no invalid entries. `idx_token_intent_lookup_keys_intent_lookup`
  already has non-zero scans.

### What Improved

1. **The old wide Token Radar rank-set query is gone from runtime code.**
   `pg_stat_statements` now shows only compact/hydration/upsert/delete shapes
   against `token_radar_target_features`, not the former wide `SELECT *` rank
   refresh.

2. **The lookup-key delete index is working.**
   `idx_token_intent_lookup_keys_intent_lookup` had 842 scans in the fresh
   snapshot, which means the low-risk missing-index fix is no longer theoretical.

3. **Terminal queue evidence exists and is queryable.**
   `worker_queue_terminal_events` now exposes historical dead/failed rows and
   live `resolution_refresh` poison-key terminalization. Operators have one
   inspect/resolve surface instead of scattered SQL.

4. **Readiness semantics are cleaner.**
   Ordinary backlog no longer makes the process unready; queue table
   unavailability, adapter failure, or manifest mismatch does.

## Root Cause Update, 2026-05-26 18:15 Asia/Shanghai

Subagent and live PostgreSQL checks agree on the current shape: this is not a
single bad SQL statement and not a general PostgreSQL outage. It is a layered
problem where rollout ordering and projection architecture create unnecessary
work, and a few query shapes and maintenance gaps amplify it.

### Root Cause Split

| Area | Severity | Diagnosis |
| --- | --- | --- |
| Token Radar rebuild gate | P0 | Compact rank-input rebuild was incomplete. Dirty-target work now checks rank-input readiness before claim, so stale rank inputs block without burning attempts. |
| Token Radar source hydration | P0 | The old `TokenRadarTargetFeatureQuery.source_rows()` single-target family caused the Top SQL fingerprint. Runtime now uses batched source requests without the materialized CTE. |
| Worker terminal backlog | P0/P1 | Most unresolved terminal rows are real provider/business outcomes, not DB lock symptoms. LLM `522`, no quote, no market data, stale TTL, and retry-budget exhaustion dominate. |
| Worker state-machine contracts | P1 | `pulse_candidate` had a stale-running edge case. Exhausted stale running jobs now terminalize as `dead` with `stale_running_timeout` before new claims. |
| PostgreSQL maintenance hygiene | P1 | No invalid indexes exist, but several hot tables have stale statistics and high churn. The follow-up migration validates its concurrent index and analyzes affected hot tables. |
| Kappa/CQRS boundary | P1 | Macro request-time dedupe moved into `macro_observation_series_rows`, written by `MacroViewProjectionWorker`; request paths read the projected table only. |

### Fresh Evidence

Runtime config is using operator-owned files:

```text
config_path: /Users/qinghuan/.gmgn-twitter-intel/config.yaml
workers_config_path: /Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

Readiness is green, but queue health exposes pressure:

```text
/readyz ok=true
identity_market_fact: blocked, queue_depth=28, unresolved_terminal=3174
projection: degraded, queue_depth=696, failed=686, max_attempt=60
agent: blocked, queue_depth=29, running=1, unresolved_terminal=2038
```

Token Radar rebuild gate:

```text
token_radar_target_features:
  legacy_needs_rebuild:      16,292
  token-radar-rank-input-v1:    951

token_radar_dirty_targets:
  resolution_refresh:          402 total, 312 due, max_attempt=59
  market_tick_current_changed: 188 total, 171 due, max_attempt=59
  ingest_resolution:           106 total,  93 due, max_attempt=60
  sample error: token_radar_rank_inputs_require_full_rebuild
```

Top SQL confirms the hotspot moved, not disappeared:

```text
WITH source_intents AS MATERIALIZED (...)
calls: 3,601
total_exec_time: 26,361 ms
mean_exec_time: 7.321 ms
shared_blks_read: 228,404
temp_blks_written: 2,155
```

The request-time macro dedupe is still visible:

```text
WITH deduped AS (SELECT *, row_number() OVER (...))
calls: 12
mean_exec_time: 181.629 ms
rows: 47,857
temp_blks_written: 7,729
```

Terminal evidence by normalized reason:

| Worker | Reason | Unresolved |
| --- | --- | ---: |
| `resolution_refresh` | `not_found_retry_budget_exhausted` | 1,536 |
| `event_anchor_backfill` | `provider_no_quote` | 1,109 |
| `mention_semantics` | `llm_provider_522` | 976 |
| `pulse_candidate` | `stale_window_ttl` | 584 |
| `enrichment` | `llm_provider_522` | 276 |
| `event_anchor_backfill` | `no_market_data` | 262 |
| `event_anchor_backfill` | `provider_error` | 229 |
| `enrichment` | `timeout` | 127 |
| `pulse_candidate` | `provider_unavailable` | 68 |

Pulse has one stale running job:

```text
status=running, attempt_count=3, max_attempts=3, window=1h, scope=all, age=511 minutes
```

Statistics are stale enough to influence planner choices. Actual counts are
far above `pg_stat_user_tables.n_live_tup` estimates until analyze runs:

| Table | Actual Rows | Total Size | `n_live_tup` Estimate | Dead Pct Estimate |
| --- | ---: | ---: | ---: | ---: |
| `token_intent_lookup_keys` | 157,616 | 91 MB | 318 | 87.97% |
| `token_intent_resolutions` | 147,522 | 185 MB | 825 | 46.29% |
| `event_anchor_backfill_jobs` | 33,606 | 22 MB | 84 | 50.00% |
| `token_radar_target_features` | 17,252 | 109 MB | 90 | 78.26% |
| `pulse_agent_runs` | 9,512 | 255 MB | 57 | 45.19% |

There are no invalid indexes in the current database.

## Still-Open Problems

### P0: Token Radar Rank Inputs Still Need A Full Rebuild

Evidence:

```text
token_radar_target_features:
  legacy_needs_rebuild:      16,731 rows
  token-radar-rank-input-v1:    381 rows

token_radar_dirty_targets:
  241 active rows in the observed sample
  max_attempt up to 31
  sample last_error: token_radar_rank_inputs_require_full_rebuild
```

Diagnosis:

The migration correctly refused to mark pre-existing rows as
`token-radar-rank-input-v1` because not every compact rank scalar can be safely
recovered from old JSON. That protects ranking correctness, but the mandatory
owner-path rebuild has not been fully drained yet. Until it is, Token Radar
dirty targets can repeatedly fail with `token_radar_rank_inputs_require_full_rebuild`.

Next move:

```bash
uv run gmgn-twitter-intel ops rebuild-token-radar-rank-inputs \
  --execute \
  --reason "post-migration compact rank input rebuild" \
  --limit 5000
```

Then verify:

```sql
SELECT rank_input_version, count(*)
FROM token_radar_target_features
GROUP BY rank_input_version;

SELECT dirty_reason, count(*), max(attempt_count), max(last_error)
FROM token_radar_dirty_targets
GROUP BY dirty_reason;
```

Do this in an operator window. It rewrites target features through the Token
Radar owner path, which is exactly what the hard cut requires.

### P0: Token Radar Source Hydration Was The Next Top Query

Pre-fix `pg_stat_statements` Top 1:

```text
WITH source_intents AS MATERIALIZED (...)
calls: 2,339
total_exec_time: 29,644 ms
mean_exec_time: 12.674 ms
shared_blks_read: 268,585
```

Code path:

```text
src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py
TokenRadarTargetFeatureQuery.source_rows()
```

Diagnosis:

After removing the wide rank-set read, the next expensive shape was per-target
source hydration. It joined current resolutions, intents, events, account
profiles, semantic extraction, asset identity, price feeds, enriched event
capture, market tick facts, and current market rows once per target/window/scope.

Hard cut:

- `TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)` accepts a
  bounded request set and hydrates source rows once per chunk.
- `rebuild_dirty_targets()` and `rebuild_rank_inputs_full()` both use the batch
  path.
- The runtime source SQL no longer contains `WITH source_intents AS MATERIALIZED`.
- Rank-input readiness runs before dirty-target claim; stale rank inputs return
  `blocked_precondition=true` without incrementing `attempt_count`.

Verification:

```bash
rg -n "WITH source_intents AS MATERIALIZED|TokenRadarTargetFeatureQuery|source_rows\\(" \
  src/gmgn_twitter_intel/domains/token_intel
```

Expected runtime result: no hits.

### P0: Queue Backlog Is Now Visible, Not Solved

Fresh unresolved terminal evidence:

| Worker | Source | Status | Count | Main Reason |
| --- | --- | ---: | ---: | --- |
| `event_anchor_backfill` | `event_anchor_backfill_jobs` | `failed` | 1,586 | `provider_no_quote`, `no_market_data`, provider errors |
| `mention_semantics` | `token_mention_semantics` | `semantic_unavailable` | 967 | LLM provider `522` |
| `pulse_candidate` | `pulse_agent_jobs` | `dead` | 642 | mostly `stale_window_ttl` |
| `resolution_refresh` | `token_discovery_dirty_lookup_keys` | `not_found` | 622 | retry budget exhausted |
| `enrichment` | `enrichment_jobs` | `dead` | 400 | LLM provider `522`, 120s timeout |
| `resolution_refresh` | `token_discovery_dirty_lookup_keys` | `error` | 14 | provider error retry budget |
| `event_anchor_backfill` | `event_anchor_backfill_jobs` | `expired` | 10 | `backfill_expired` |

Diagnosis by domain:

- `event_anchor_backfill` is mostly a market data/provider coverage issue, not
  a PostgreSQL lock issue. `provider_no_quote` and `no_market_data` need market
  target/quote availability diagnosis.
- `mention_semantics` and `enrichment` are dominated by external LLM provider
  `522` and provider timeouts. Treat this as provider/circuit/backpressure
  behavior, not as database failure.
- `pulse_candidate` dead rows are mostly stale-window TTL. The agent lane is
  admitting or retaining work that cannot finish before the product window
  expires.
- `resolution_refresh` is actively terminalizing poison lookup keys, but active
  backlog still exists.

Fresh active `token_discovery_dirty_lookup_keys`:

```text
total: 1,231
due: 1,221
running: 0
max_attempt: 554
oldest_due: 2026-05-25 04:15 UTC
```

The high active attempt counts are legacy rows being drained under the new
budget. The worker has `max_attempts=3`, but terminalization happens when a row
is claimed. With `concurrency=1` and `batch_size=50`, old rows will disappear
gradually, not instantly.

Next moves:

- Let the new terminalizer drain, then re-check active max attempts.
- Resolve obvious terminal rows by operator action, not table updates.
- Add reason-level dashboards: provider outage, no quote, no market data,
  stale TTL, retry budget exhausted.
- For `pulse_candidate`, tune enqueue volume versus TTL and agent capacity.

### P1: Macro Request-Time Dedupe Still Writes Temp Blocks

Fresh `pg_stat_statements`:

```text
WITH deduped AS (
  SELECT *, row_number() OVER (...)
  FROM macro_observations
)
calls: 13
mean_exec_time: 181.172 ms
rows: 47,833
temp_blks_written: 7,729
```

Diagnosis:

The macro read path still computes deduped latest observations during requests.
That is a CQRS smell. Reads should hit a projected read model.

Next move:

- Implement the plan's Phase 6 in a separate migration after `20260526_0100`.
- Add `macro_observation_latest_rows` or extend `macro_view_snapshots`.
- Delete request-time `row_number() OVER` from HTTP repository paths.
- Verify temp blocks disappear from the Top mean-time report.

### P1: Large Audit/Fact Tables Need Retention And Partition Discipline

Fresh largest relations:

| Relation | Total Size |
| --- | ---: |
| `market_ticks_default` | 2.1 GB |
| `events` | 1.9 GB |
| `raw_frames` | 835 MB |

Diagnosis:

This is expected for an append-heavy Kappa system, but it cannot be ignored.
Token Radar audit/history and market tick facts need explicit retention,
partition drop cadence, and index review.

Next move:

```bash
uv run gmgn-twitter-intel ops ensure-postgres-partitions --dry-run
uv run gmgn-twitter-intel ops drop-expired-postgres-partitions --dry-run
```

Only execute after confirming retention policy and expected product lookback.

### P1: Control Tables Show High Dead Tuple Percentages

Fresh examples:

| Table | Dead Pct | Total Size |
| --- | ---: | ---: |
| `token_radar_target_features` | 93.77% | 108 MB |
| `token_intent_lookup_keys` | 87.85% | 91 MB |
| `token_intent_resolutions` | 46.35% | 183 MB |
| `event_anchor_backfill_jobs` | 50.00% | 21 MB |
| `pulse_agent_runs` | 39.01% | 248 MB |

Diagnosis:

This is the cost of recent hard-cut backfills and high-churn queue updates. It
does not mean the database is broken, but it does mean planner stats and heap
visibility may lag during active churn.

Next move:

```sql
VACUUM (ANALYZE) token_radar_target_features;
VACUUM (ANALYZE) token_intent_lookup_keys;
VACUUM (ANALYZE) token_intent_resolutions;
VACUUM (ANALYZE) event_anchor_backfill_jobs;
VACUUM (ANALYZE) pulse_agent_runs;
```

Run after the current drain/rebuild wave, not while the same tables are being
heavily rewritten.

### P2: Equity Provider Document Churn Is Still Noisy

Fresh Top SQL includes high-call equity document select/upsert paths:

```text
SELECT * FROM equity_provider_documents WHERE source_id = ... AND provider_document_key = ...
calls: 25,836

equity_event_documents upsert
calls: 25,836
```

Diagnosis:

Single-call latency is low, but this pattern creates continuous CPU, WAL, index,
and autovacuum pressure. It is not the first bottleneck, but it will matter as
source volume grows.

Next move:

- Preserve provider natural-key idempotency.
- Convert fetch/process batches to set-based `INSERT ... SELECT FROM unnest`
  where the repository can keep the same conflict policy.
- Measure WAL and dead tuples before/after.

## Priority Order

1. Finish Token Radar rank-input rebuild and verify `legacy_needs_rebuild=0`
   for active publishable rows; dirty target workers should block before claim
   while that rebuild is incomplete.
2. Verify post-deploy pg_stat deltas show no new
   `WITH source_intents AS MATERIALIZED` calls.
3. Drain and classify terminal queue evidence by `final_reason_bucket`; do not leave 4k+
   unresolved terminal rows as background noise.
4. Verify Macro API deltas show no request-time `row_number()` over
   `macro_observations`; request paths should read `macro_observation_series_rows`.
5. Schedule retention/partition review for Token Radar audit/history and
   market ticks.
6. Vacuum/analyze high-churn control tables after the current live drain.
7. Reduce equity provider document write churn with set-based idempotent writes.

## Completion Checklist For Future Performance PRs

- `uv run gmgn-twitter-intel config` confirms operator-owned runtime paths.
- `/readyz` is green or failures are contract failures, not hidden backlog.
- `docker compose ps --all` has app/postgres healthy and migrations complete.
- `pg_stat_activity` shows no unexpected blockers or idle-in-transaction leaks.
- Top `pg_stat_statements` before/after snapshots are recorded.
- Mutating `EXPLAIN ANALYZE` evidence is wrapped in `BEGIN ... ROLLBACK`.
- New live-table indexes are concurrent and validated.
- Changed hot tables are analyzed.
- Queue health and terminal evidence are inspected.
- pgBadger report exists for log-driven symptoms.
- PoWA current and history tables contain rows.
- No feature flags, compatibility SQL paths, or dual writers were introduced to
  make the numbers look better.
