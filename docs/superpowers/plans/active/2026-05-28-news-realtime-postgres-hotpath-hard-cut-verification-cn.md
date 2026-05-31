# News Realtime Postgres Hotpath Hard Cut Verification

Date: 2026-05-28

Branch: `codex/news-realtime-postgres-hotpath-hard-cut`

## Result

PASS for the News hard cut and live runtime checks.

Residual project gate: `make check-all` is blocked before tests by unrelated repository-wide `ruff format --check .` drift in 24 non-News files.

## Evidence

- Focused News target suite after source-status fix:
  - `529 passed in 326.43s`.
- Post-format focused verification:
  - `101 passed in 1.44s`.
  - `190 passed in 9.17s`.
- Source-status regression tests:
  - `5 passed in 9.72s`.
- Integration spot run with isolated test DB:
  - `4 passed in 17.61s`.
- Lint/format for branch Python changes:
  - `ruff check`: pass.
  - `ruff format --check`: pass for branch Python changes.
- Docker/live:
  - `docker compose ps`: app healthy, postgres healthy.
  - `parallax db health`: `migration_version=20260528_0119`, `expected_migration_version=20260528_0119`, `migration_status=ready`.
  - New indexes present: `ix_news_item_observation_edges_source_item`, `ix_news_fetch_runs_source_started_run`.
  - OpenNews provider-signal `brief_input` dirty targets: 0.
  - No-start backpressure agent runs: 0.
  - OpenNews latest fetch runs: REST `http_status=200` for `opennews-news` and `opennews-listing`, no handshake errors.
  - `/api/news/sources/status`: 200; timings after warmup: 138ms and 130ms.
  - `/api/news?limit=5`: 200, returned 5 items.
  - `/ws`: auth ready received; replay smoke received 1 message.
  - Claim query plan uses `ix_news_items_unprocessed_claim`; execution time below 1ms on live DB.

## Make Check-All

`make check-all` fails in the `check` subtarget at repository-wide `ruff format --check .`.

After formatting only this branch's changed Python files, the remaining 24 files needing reformat are unrelated to this News work: macro, token radar, equity event, narrative, golden, and general test files. They were not changed to avoid unrelated churn.
