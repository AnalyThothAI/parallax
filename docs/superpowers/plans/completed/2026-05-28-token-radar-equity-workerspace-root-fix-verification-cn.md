# Token Radar / Equity Event / WorkerSpace Root Fix Verification

## Config Paths

- `uv run parallax config` returned `ok=true`.
- `config_path`: `/Users/qinghuan/.parallax/config.yaml`.
- `workers_config_path`: `/Users/qinghuan/.parallax/workers.yaml`.
- Secrets were not copied into this artifact.

## Migration

- Final `main` Alembic chain includes current `main` News
  migrations `20260528_0117` -> `20260528_0118` -> `20260528_0119` ->
  `20260528_0120`, and Token/Equity/WorkerSpace `20260528_0121` follows
  `20260528_0120`; `20260528_0122` reasserts Token Radar runtime NOT NULL
  guardrails without rehashing payloads.
- `uv run parallax db migrate`: passed.
- `uv run parallax db health`: passed with
  `migration_version=20260528_0122`, `expected_migration_version=20260528_0122`,
  `migration_status=ready`.
- Docker `migrate` service exited `0`.

## Unit And Architecture Tests

- Final-review regression pair:
  `uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py -q`
  -> `13 passed`.
- Focused root-fix suite:
  `uv run pytest tests/architecture/test_token_equity_workerspace_root_fix_contract.py tests/unit/test_token_radar_payload_hash.py tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py tests/unit/test_runtime_worker_context.py -q`
  -> `37 passed`.
- Migration/manifest guard:
  `uv run pytest tests/architecture/test_token_equity_workerspace_root_fix_contract.py tests/unit/test_postgres_schema.py::test_runtime_performance_hard_cut_revision_chain tests/unit/test_postgres_schema.py::test_alembic_revision_ids_are_unique tests/unit/test_postgres_schema.py::test_token_equity_workerspace_root_fix_migration_contract -q`
  -> `10 passed`.
- Final `main` focused + migration guard:
  `uv run pytest tests/architecture/test_token_equity_workerspace_root_fix_contract.py tests/unit/test_token_radar_payload_hash.py tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py tests/unit/test_runtime_worker_context.py tests/unit/test_postgres_schema.py::test_runtime_performance_hard_cut_revision_chain tests/unit/test_postgres_schema.py::test_alembic_revision_ids_are_unique tests/unit/test_postgres_schema.py::test_token_equity_workerspace_root_fix_migration_contract tests/unit/test_postgres_schema.py::test_token_radar_runtime_not_null_guardrails_do_not_rehash_payloads -q`
  -> `41 passed`.
- Wider related unit/schema suite:
  `uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py tests/unit/test_event_anchor_backfill_worker.py tests/unit/domains/token_intel/test_token_radar_rank_source_query.py tests/unit/test_postgres_schema.py -q`
  -> `110 passed` on final `main`.
- `uv run ruff format --check $(git diff --name-only main...HEAD | rg '\.py$')`
  -> passed for branch-touched Python files.
- Final `main` formatter check:
  `uv run ruff format --check src/parallax/platform/db/alembic/versions/20260528_0122_token_radar_runtime_not_null_guardrails.py tests/unit/test_postgres_schema.py`
  -> `2 files already formatted`.
- `git diff --check` -> passed.

## make check-all

- `make check-all` currently fails at `ruff format --check` before tests run.
- The remaining formatter failures are 23 pre-existing/non-branch files:
  Macro, News, narrative, older golden/integration/unit tests, and the Macro
  `20260528_0116` migration. Branch-touched Python files pass format check.
- Because `check-all` stops at formatting, integration/e2e/golden/coverage gates
  were not reached through this single Make target.

## Live PostgreSQL Before/After

- Docker services after rebuild:
  `postgres` healthy, `migrate` exited `0`, `app` healthy.
- `/readyz` after rebuilding app image from final `main`:
  `ok=true`, `reasons=[]`, DB `migration_version=20260528_0122`,
  `expected_migration_version=20260528_0122`, `migration_status=ready`.
- Schema smoke:
  `equity_event_process_jobs` exists; `token_radar_rank_source_events.source_payload_hash`,
  `token_radar_dirty_targets.market_dirty`, and
  `equity_event_evidence_artifacts.artifact_payload_hash` exist.
- Queue smoke:
  final Docker DB had `0` null `source_payload_hash` rows across `40321`
  rank-source rows; `0` null dirty-flag rows across `22` dirty targets;
  `equity_event_process_jobs` had `77 done` rows; evidence artifacts had
  `0` null `artifact_payload_hash` rows across `22022` rows.

## Coverage

- Not reached through `make check-all` because the Make gate fails first on
  unrelated formatter drift.

## Skipped Tests

- No focused tests were intentionally skipped.
- Full `check-all` downstream integration/e2e/golden/coverage phases were not
  reached because the formatter gate failed first.

## E2E Golden Path

- `curl -fsS http://127.0.0.1:8765/healthz` -> `ok`.
- `curl -fsS http://127.0.0.1:8765/readyz` -> `ok=true`.
- `/api/status` returned `401` without credentials, which is expected for the
  authenticated status surface.

## Other Commands Run

- `docker compose up -d --build app` rebuilt and restarted `app`/`migrate` from
  final `main`; `migrate` exited `0`, `postgres` and `app` became healthy.
- The dirty `main` worktree from another News thread was preserved in
  `stash@{0}` with message `pre-token-equity-main-merge-news-wip-20260528`
  before the merge. It was not reapplied because it contains a separate
  News `20260528_0121` migration and would make the Docker validation ambiguous.
- Final-review fixes added after the Docker readiness smoke:
  running Equity process jobs with a changed input hash are reset to `pending`
  so the old lease cannot mark stale output done; Token Radar source+market
  dirty claims now overlay latest market context before projection.
- Static retired-path scan:
  `rg -n "list_event_documents_for_processing|list_unprocessed_event_documents|replace_evidence_artifacts|WITH source_intents AS MATERIALIZED|TokenRadarTargetFeatureQuery|source_rows\(" ...`
  -> no production hits; only architecture-test assertions matched.
- WorkerSpace docs/API scan confirmed no stale `claim_scope`/`payload_scope`/
  `provider_scope`/`persist_scope` references remain in canonical docs.

## Remaining Risks

- Full `make check-all` remains blocked by unrelated formatter drift outside
  this branch's touched Python files.
- Live queues still contain historical terminal/backlog rows; this branch
  changes the root execution architecture but does not resolve every old
  terminal provider/business outcome.
- Startup logs still showed one WebSocket replay `statement timeout` on
  `events` and one GMGN WS broken pipe; no new errors appeared in the final
  30-second log window, and `/readyz` stayed `ok=true`.
- Postgres CPU dropped from a startup burst to about `63.80%` after the final
  wait window; no long-running active SQL was present, only a short
  `idle in transaction` worker claim observed at sub-second age.
- The hard reset SQL in the runbook is destructive maintenance. It includes
  Equity Event classifier fact outputs and must only be used with workers
  stopped and explicit re-enqueue/rebuild targets ready.
