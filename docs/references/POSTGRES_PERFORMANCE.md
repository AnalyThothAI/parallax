# PostgreSQL Performance And Queue Diagnostics

> **Scope.** This is the living performance playbook for the local Docker
> PostgreSQL production runtime. It covers query diagnosis, live migration
> safety, worker queue pressure, and PoWA/pgBadger usage. Dated runtime findings
> belong in timestamped reviews, not in this living playbook.

## Why This Exists

Parallax is PostgreSQL-first Kappa/CQRS. The database is not just
storage; it is the durable execution plane for facts, read models, dirty
targets, run ledgers, and queue state. Performance work must therefore preserve
these invariants:

- Material facts remain the only business truth.
- Each rebuildable read model has exactly one runtime writer.
- Dirty target tables are control plane, not business facts.
- Runtime workers claim durable dirty work on bounded intervals and pass due
  gates without a message-delivery dependency.
- Runtime fixes must be observable through PostgreSQL evidence, not intuition.

The durable pattern is: first make pressure visible, then remove the exact hot
SQL or retry loop. Do not hide backlog by weakening `/readyz`, reducing worker
count, or deleting facts.

## Hot/Cold Lifecycle Contract

PostgreSQL tables are grouped by runtime temperature before any performance or
maintenance change. Hot paths stay compact and indexed by claimed work keys;
cold paths are retained by partition lifecycle, not by worker-loop deletes.

| Retention class | Tables | Lifecycle rule |
| --- | --- | --- |
| Hot online serving path | `token_radar_current_rows`, `token_radar_publication_state`, `macro_observations`, `macro_research_publications` | Online Token Radar reads only current rows plus publication state. Macro research reads one immutable session-keyed publication; live Macro evidence performs a bounded concept/date fact query with capped rows per source series and never assembles research. Retired CEX OI/detail tables are not performance templates. |
| Projection-private/detail path | `token_radar_target_features`, `token_radar_rank_source_events` | Used by the Token Radar projection and bounded evidence/detail lookups only. `token_radar_target_features` is not an API, CLI, notification, or repair read path. `token_radar_rank_source_events` is lazy evidence/detail, not online leaderboard service. |
| Selected-row hydrate | `events`, `enriched_events` | Access only after ranking or explicit evidence selection has chosen stable row ids or payload hashes. Do not join these wide payload tables into rank/discovery scans. |
| Cold audit/history | `raw_frames` and immutable Macro publication history | Partition or product-defined immutable lifecycle only. Runtime workers must not issue loop deletes against audit, history, publication, or provider raw-frame tables. |
| Control/execution plane | Dirty targets, fetch runs, `macro_research_runs`, `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` | Leased and bounded. Queue state transitions preserve attempts and lease ownership. LangGraph checkpoint rows use a stable scope-derived `thread_id`; they are not business facts or an API read path. |

2026-05-27 Macro lesson: a retired generated-series design had one runtime
writer and correct active-generation readers, but every run produced a new
physical generation. The active pointer made the API look current while the
underlying row set kept growing with worker runs, increasing index size,
planner/autovacuum work, and request latency. For current read models,
"latest generation" is not a lifecycle policy. Current read model primary keys
must be stable product/window keys, not `generation_id`, `run_id`,
`attempt_id`, timestamp-derived ids, or UUIDs. Use compact current rows,
bounded retention, or explicit cold history; prove the bound with relation-size
and row-cardinality checks, not only by checking the API response. Unchanged
current projections must use `payload_hash` or `IS DISTINCT FROM` gates and be
observable as zero serving-row writes.

## Source Material

- SDD workflow: `docs/sdd/`
- Operational invariants: `docs/OPERATIONS.md`
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
uv run parallax config
curl -sS http://127.0.0.1:8765/readyz \
  | jq '{ok,reasons,db,composition}'
docker compose ps --all
```

For Docker, the container paths are under `/root/.parallax/`, mounted
from the host `~/.parallax/`. Report only paths, booleans, redacted
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
- Fixed: Token Radar runtime projection does not run a broad recent
  resolved-target/fact-window catch-up scan. Operators repair missed work with
  explicit bounded dirty-target enqueue commands.
- Fixed in the follow-up hard cut: Token Radar source hydration now builds
  bounded `TokenRadarSourceRequest` batches and uses
  `TokenRadarTargetFeatureBatchQuery.source_rows_for_requests(...)`. Runtime
  code no longer calls the single-target `source_rows(...)` path or the old
  `WITH source_intents AS MATERIALIZED` query.
- Fixed in the 2026-05-28 Token/WorkerSpace hard cut: Token Radar
  market-only dirty targets reuse stable `token_radar_rank_source_events`
  source packets and overlay latest market context instead of rewriting source
  edges. Source-edge writes use payload hashes to avoid unchanged TOAST
  rewrites.

### Match Indexes To Real Predicates

Partial indexes work only when the query predicate implies the partial predicate.
If runtime says `status <> 'done'`, an index on `status = 'pending'` will not
prove the path. Change the runtime predicate or create the exact partial index.

Good examples from the hard cut:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_lookup_keys_intent_lookup
  ON token_intent_lookup_keys(intent_id, lookup_key);

CREATE INDEX IF NOT EXISTS idx_token_radar_dirty_targets_claim
  ON token_radar_dirty_targets(
    due_at_ms ASC,
    updated_at_ms ASC,
    target_type_key,
    identity_id
  );
```

### Keep Runtime Idle Paths Bounded

A worker loop with no due work must not scan broad facts or read models to prove
nothing happened. Normal runtime work must be proportional to claimed dirty
targets or leased jobs.

`macro_research` performs one narrow scheduling-state read, claims at most one
completed-session row, and then closes the transaction before model or evidence
tool I/O. There is no generic model-capacity/gateway queue. Timeout, tool, model,
or publication failures transition that exact run through its bounded retry
state; they do not trigger a broad fact scan or create a second execution
ledger.

Broad discovery belongs in dry-run-first ops commands that enqueue bounded work:

```bash
uv run parallax ops enqueue-token-radar-dirty-targets --dry-run
```

### Hard Reset Token Rows

Use this only after the Token Radar / WorkerSpace hard cut migration and code
are deployed, all affected workers are stopped or in a maintenance window, and
the operator has a bounded repair target list ready.
This is a destructive maintenance reset, not routine cleanup and not a fact
retention policy. The Token Radar tables in this recipe are rebuildable
projection/control rows. It must not be run while workers are concurrently
claiming the same queues.

After the reset, enqueue explicit bounded repair targets through the owning ops
paths. Do not rely on runtime workers to scan facts and rediscover everything.

```sql
TRUNCATE token_radar_dirty_targets;
TRUNCATE token_radar_rank_source_events;
TRUNCATE token_radar_target_features;
TRUNCATE token_radar_current_rows;
DELETE FROM token_radar_publication_state
WHERE projection_version = 'token-radar-v13-social-attention';
```

Recommended post-reset checks:

```sql
ANALYZE token_radar_dirty_targets;
ANALYZE token_radar_rank_source_events;
ANALYZE token_radar_target_features;
ANALYZE token_radar_current_rows;
ANALYZE token_radar_publication_state;
```

### Treat Queue Terminal States As Evidence

Active queue tables should represent claimable, retryable, or running work.
Terminal outcomes must be explicit evidence with an operator action path:

```bash
uv run parallax ops queue-inspect --status terminal --limit 50
uv run parallax ops queue-resolve \
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

The Macro request path must remain a session-key lookup on
`macro_research_publications`, optionally joined to its single
`macro_research_runs` row for persisted status. Do not restore request-time
dedupe or research assembly over `macro_observations`, and do not expose
LangGraph checkpoint payloads through the API.

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

## Dated Evidence Is Not Current State

Live row counts, queue depth, worker inventory, relation sizes, query timings,
and readiness results belong in timestamped review or incident artifacts. They
must not be copied into this living playbook as current truth.

Before using an older snapshot, reopen the cited artifact and verify it against
the operator-owned runtime with the Safe Baseline above. If live PostgreSQL is
unavailable, label the physical state unknown and limit conclusions to static
schema, query-shape, migration, and test evidence.
## Completion Checklist For Future Performance PRs

- `uv run parallax config` confirms operator-owned runtime paths.
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
