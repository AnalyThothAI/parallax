# Runtime DB Performance Hard Cut Verification

Date: 2026-05-27

## Code Verification

Focused suite:

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

Result:

```text
312 passed in 7.69s
```

Lint:

```bash
uv run ruff check .
```

Result:

```text
All checks passed!
```

Whitespace:

```bash
git diff --check
```

Result: passed with no output.

Runtime Macro no-compat scan:

```bash
rg -n "macro_observation_series_active_generation|macro_observation_series_generations|generation_id = rows.generation_id|_generation_id\(" \
  src/gmgn_twitter_intel/domains/macro_intel \
  src/gmgn_twitter_intel/app/runtime \
  docs/WORKERS.md \
  docs/ARCHITECTURE.md \
  docs/RELIABILITY.md \
  docs/references/POSTGRES_PERFORMANCE.md
```

Result: no runtime/docs matches.

## Migration Verification

Static migration/schema tests passed in the focused suite. Live `alembic upgrade head` was not run in this coding pass because `20260527_0114` is a hard cut that drops Macro active-generation runtime tables and should be applied only after pausing `macro_view_projection`.

## Rollout Checks Still Required

After applying migration `20260527_0114` with the Macro projection worker paused:

```sql
SELECT pg_size_pretty(pg_total_relation_size('macro_observation_series_rows'));

SELECT to_regclass('macro_observation_series_active_generation') AS active_generation_table,
       to_regclass('macro_observation_series_generations') AS generations_table;

SELECT latest_attempt_status, row_count, source_signature IS NOT NULL AS has_source_signature
FROM macro_observation_series_publication_state
WHERE projection_version = 'macro_regime_v4';
```

Expected: generation tables are absent, compact rows are bounded by `limit_per_series`, and the second steady Macro run reports `unchanged` with zero series-row writes.
