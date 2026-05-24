# Projection Dirty Target Hard Cut Verification

Date: 2026-05-24

## Code Verification

- `uv run ruff check .`
  - Result: passed.
- `uv run ruff format --check $(git diff --name-only -- '*.py') $(git ls-files --others --exclude-standard -- '*.py')`
  - Result: passed for touched Python files.
- `git diff --check`
  - Result: passed.
- `uv run mypy src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_projection_dirty_target_repository.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_page_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_story_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_source_quality_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_brief_worker.py src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py src/gmgn_twitter_intel/app/ops/projection_dirty_targets.py`
  - Result: passed.
- `uv run mypy src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_story_projection_worker.py`
  - Result: passed.
- `uv run pytest tests/unit/domains/equity_event_intel tests/unit/domains/news_intel tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_projection_worker_idle_cost_contract.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q`
  - Result: `307 passed, 11 skipped`.
- `uv run pytest tests/integration/domains/news_intel tests/integration/test_equity_event_workers.py -q`
  - Result before deleting the obsolete broad candidate progression test: `66 passed`.
  - Result after hard-deleting broad repository discovery methods: `65 passed`.
- `uv run pytest tests/unit/domains/equity_event_intel/test_equity_story_projection_dirty_targets.py -q`
  - Result: `9 passed`.
- `uv run pytest tests/integration/test_equity_event_workers.py -q`
  - Result: `25 passed`.
- `uv run pytest tests/architecture/test_projection_worker_idle_cost_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  - Result: `91 passed`.

## Full Gate Residual

- `make check-all`
  - Result: failed at `ruff format --check .` before mypy/web/tests.
  - Cause: 64 pre-existing unrelated files would be reformatted.
  - Touched Python files are formatted and checked separately.

## Real Config

- `uv run gmgn-twitter-intel config`
  - `config_path`: `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
  - `workers_config_path`: `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`
- Real `workers.yaml` was updated so `news_page_projection.wakes_on` includes `news_page_dirty`.
- `news_source_quality_projection.windows`: `["24h", "7d"]`.

## Migration And Repair

- `uv run gmgn-twitter-intel db migrate`
  - Result: upgraded `20260524_0093 -> 20260524_0094`.
- `uv run gmgn-twitter-intel db health`
  - Result: migration status `ready`, expected/current `20260524_0094`.
- `uv run gmgn-twitter-intel ops enqueue-projection-dirty-targets --domain all --dry-run`
  - Equity: 16,923 company events, 67,692 company-event projection targets.
  - News: 1,076 news items, 2,152 news item projection targets, 20 source-quality targets.
- `uv run gmgn-twitter-intel ops enqueue-projection-dirty-targets --domain all --execute`
  - Enqueued all listed targets.

## Docker And Live Runtime

- `docker compose up -d --build app`
  - Result: built `gmgn-twitter-intel-app` and `gmgn-twitter-intel-migrate`; app started healthy.
  - The Docker build ran the frontend production build (`npm run build`) and emitted new `web/dist` asset hashes during the first rebuild.
- `/healthz`
  - Result: `ok`.
- `/readyz`
  - Result: `ok`, DB ready at migration `20260524_0094`.
- Provider state after rebuild:
  - GMGN direct WS: `streaming`.
  - OKX DEX WS: `streaming`, desired subscriptions 9, acked subscriptions 9, reconnect count 0, data frames and ticks increasing.

## Runtime Queue And Performance Evidence

- After manual repair replay:
  - `equity_event_projection_dirty_targets`: no remaining rows.
  - `news_projection_dirty_targets`: 20 `source_quality` rows remain, all `due_now=0`, all `error_rows=0`; these are future durable timers.
- Projection worker idle state:
  - `news_page_projection`: `claimed=0`, `projected=0`, `marked_error=0`.
  - `equity_event_page_projection`: `claimed=0`, `page_rows=0`, `timeline_rows=0`, `deleted=0`, `marked_error=0`.
  - `news_source_quality_projection`: `claimed=0`, `projected=0`, `rescheduled=0`, `marked_error=0`.
- `pg_stat_activity` after queues drained:
  - No long-running business query.
  - Only the inspection query was active in the final idle snapshot.
- CPU samples after queues drained:
  - App ranged roughly 11-69% during active agent/provider work.
  - Postgres ranged roughly 13-132% in short samples, with non-idle activity attributable to short-cycle workers such as queue claims, source-quality due checks, news item processing, token/market jobs, and the inspection query.
  - The old failure mode was not observed: no repeating broad `equity_event_page_projection` scan over all equity events while queues were empty.

## Live Issue Found And Fixed

- During repair replay, `equity_event_story_projection` found an idempotency bug:
  - Existing `equity_event_story_members.company_event_id` rows were reprocessed and could be assigned to a different story, violating the unique index on `company_event_id`.
  - Symptom: batches marked error with duplicate key on `idx_equity_event_story_members_event`.
- Fix:
  - `load_events_for_story_projection` now loads current story membership for each claimed event.
  - `EquityEventStoryProjectionWorker` refreshes existing membership instead of regrouping it.
  - Unit and integration tests verify this path.
- Post-fix runtime:
  - story dirty queue cleared.
  - story error rows returned to zero.

## Merge Note

The main worktree at `/Users/qinghuan/Documents/code/gmgn-twitter-intel` has unrelated dirty changes and conflicting untracked spec/plan files, so this branch was not merged into `main` from the dirty main worktree.
