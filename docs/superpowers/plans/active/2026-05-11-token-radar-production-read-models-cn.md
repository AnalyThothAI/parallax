# Plan — Token Radar Production Read Models

**Status**: Completed
**Date**: 2026-05-11
**Owning spec**: `docs/superpowers/specs/active/2026-05-11-token-radar-production-read-models-cn.md`
**Worktree**: `.worktrees/token-radar-production-read-models/`
**Branch**: `codex/token-radar-production-read-models`

## Pre-flight

- [x] Worktree exists at `.worktrees/token-radar-production-read-models/`.
- [x] Branch is `codex/token-radar-production-read-models`.
- [x] User explicitly approved writing spec + plan and landing implementation in one pass on 2026-05-11.
- [x] Baseline `uv run ruff check src tests` recorded.
- [x] Baseline focused tests recorded.

Known process deviation:

- Project SOP normally asks for explicit approval between spec and plan lanes. User instruction for this turn was to write both and land the fix, so this plan treats the lane boundary as approved and records the deviation here.

## File-level edits

### `src/parallax/platform/db/alembic/versions/20260511_0025_token_radar_production_read_models.py`

- Add Alembic revision `20260511_0025`, down revision `20260511_0024`.
- Create `token_radar_publications`.
- Create `current_market_field_facts`.
- Create `token_market_price_baselines`.
- Add concurrent indexes:
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_publication_read
    ON token_radar_rows(projection_version, "window", scope, computed_at_ms, lane, rank);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_current_market_field_facts_latest
    ON current_market_field_facts(subject_type, subject_id, field_key, observed_at_ms DESC, source_observation_id DESC);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_market_price_baselines_resolution
    ON token_market_price_baselines(resolution_id);
  ```

### `src/parallax/domains/token_intel/repositories/token_radar_repository.py`

- Replace public coverage methods with publication methods:
  - `mark_refresh_status(...) -> None`
  - `publish_rows(...) -> None`
  - `latest_publications(...) -> dict[tuple[str, str], dict[str, Any]]`
- Change `latest_rows(...)` to join `token_radar_publications.published_computed_at_ms`.
- Keep `replace_rows(...)` as row writer, but stale-writer guard checks publication/row max and publish only happens after successful replace.
- Remove public reads from `token_radar_projection_coverage`; no compatibility fallback.

### `src/parallax/domains/token_intel/services/token_radar_projection.py`

- At start, call `mark_refresh_status(refresh_status="running", ...)`.
- On success:
  1. start/finish projection run in transaction;
  2. `replace_rows(..., commit=False)`;
  3. `publish_rows(..., refresh_status="ready", commit=True)`.
- On failure, call `mark_refresh_status(refresh_status="failed", ...)` without moving published pointer.
- Keep provider-free projection.

### `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`

- Replace `latest_coverage(...)` and `mark_coverage(...)` calls with publication methods.
- Missing-work logic treats a window/scope as ready only when it has `published_computed_at_ms`; refresh failure/running does not erase publication.

### `src/parallax/domains/token_intel/read_models/asset_flow_service.py`

- Constructor becomes `AssetFlowService(token_radar, current_market)`.
- Use `latest_publications(...)`.
- If no publication exists, return pending.
- If publication exists, return rows even when `refresh_status` is `running` or `failed`.
- Hydrate `current_market` from injected current-market repository for returned target rows.
- Delete factor-snapshot current-market reconstruction helpers.

### `src/parallax/app/surfaces/api/http.py`

- Construct `AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market)`.

### `src/parallax/app/surfaces/cli/main.py`

- Construct `AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market)`.
- Add ops command:
  ```text
  parallax ops backfill-token-price-baselines --limit N
  ```

### `src/parallax/app/runtime/app.py`

- Notification rule engine receives `AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market)`.

### `src/parallax/domains/asset_market/repositories/price_observation_repository.py`

- After inserting/upserting `price_observations`, write capable non-null fields into `current_market_field_facts`.
- If `source_resolution_id`, `source_event_id`, and `event_received_at_ms` are present, upsert `token_market_price_baselines`.
- Add repository helper for backfilling baselines in batches.

### `src/parallax/domains/asset_market/repositories/current_market_repository.py`

- Replace `price_observations` lateral reads with a single query over `current_market_field_facts`.
- Build the same field-aware snapshot shape as the current public contract.

### `src/parallax/domains/token_intel/queries/token_radar_source_query.py`

- Join `token_market_price_baselines` by `resolution_id`.
- Select first/event/before fields from the baseline table.
- Assert source query still does not reference `price_observations`.

### Docs

- Update `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, and `src/parallax/domains/token_intel/ARCHITECTURE.md` to describe:
  - publication pointer;
  - current-market field facts;
  - token market price baselines.

## Tests

- `tests/unit/test_token_radar_repository.py::test_latest_rows_reads_last_published_rows_while_refresh_running`
- `tests/unit/test_token_radar_repository.py::test_failed_refresh_preserves_published_computed_at`
- `tests/unit/test_asset_flow_service.py::test_asset_flow_serves_published_rows_when_refresh_running`
- `tests/unit/test_asset_flow_service.py::test_asset_flow_requires_current_market_repository_for_public_rows`
- `tests/test_current_market_repository.py::test_current_market_sql_reads_field_facts_not_price_observations`
- `tests/integration/test_price_observation_repository.py::test_insert_observation_writes_current_market_field_facts`
- `tests/integration/test_price_observation_repository.py::test_insert_message_observation_writes_token_price_baseline`
- `tests/unit/test_token_radar_projection.py::test_source_rows_reads_price_baselines_without_price_observations`
- `tests/unit/test_postgres_schema.py::test_token_radar_production_read_models_migration`
- API/CLI/runtime construction tests if existing tests fail after constructor hard cut.

## PR breakdown

Single PR:

1. Storage + repositories + projection publication.
2. Current-market read model maintenance.
3. Price baseline read model and source query join.
4. API/CLI/runtime injection and docs.

This is intentionally one PR because partial rollout would either publish without the new pointer or read a table that is not maintained.

## Rollout order

1. Apply migration: `uv run parallax db migrate`.
2. Backfill field facts from existing `price_observations`: `uv run parallax ops backfill-current-market-field-facts --limit <N>`.
3. Backfill token price baselines: `uv run parallax ops backfill-token-price-baselines --limit <N>`.
4. Run `uv run parallax ops rebuild-token-radar --window 24h --scope all`.
5. Verify `/api/token-radar?window=24h&scope=all` returns published rows while refresh metadata is observable.

## Rollback

- Code rollback is safe while new tables remain; old code ignores new tables.
- Do not drop new tables during emergency rollback; they are append/read-model state and can be rebuilt.
- If publication pointer is corrupt, set `published_computed_at_ms` to the last known good `token_radar_rows.computed_at_ms` for the same version/window/scope, then rebuild.
- Dropping indexes/tables is not part of operational rollback unless approved separately.

## Acceptance test commands

- AC1/AC2: `uv run pytest tests/unit/test_token_radar_repository.py tests/unit/test_asset_flow_service.py -q`
- AC3/AC4: `uv run pytest tests/test_current_market_repository.py tests/integration/test_price_observation_repository.py -q`
- AC5/AC6: `uv run pytest tests/unit/test_token_radar_projection.py::test_source_rows_reads_price_baselines_without_price_observations -q`
- AC7: `uv run pytest tests/unit/test_asset_flow_service.py tests/integration/test_api_http.py tests/integration/test_cli.py -q`
- Full gate: `make check-all`

## Verification

Verification passed with:

- `make check-all`
- `626 passed, 19 skipped`
- Coverage `82.14%`
