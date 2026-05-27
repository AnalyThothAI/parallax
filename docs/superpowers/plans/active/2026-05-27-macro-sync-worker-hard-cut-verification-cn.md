# Macro Sync Worker Hard Cut Verification

**Date:** 2026-05-27
**Branch/worktree:** `codex/macro-sync-worker-hard-cut` / `.worktrees/macro-sync-worker-hard-cut`

## Automated Checks

```bash
uv run pytest tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_postgres_schema.py tests/architecture/test_api_read_paths_provider_free.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_project_structure.py -q
```

Result: `425 passed`.

```bash
uv run ruff check src/gmgn_twitter_intel/domains/macro_intel/services/macro_sync_service.py src/gmgn_twitter_intel/domains/macro_intel/services/macro_sync_scheduler.py src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_sync_worker.py src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py src/gmgn_twitter_intel/integrations/macrodata/runner.py src/gmgn_twitter_intel/platform/config/settings.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_scheduler.py tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_currentness_payloads.py tests/unit/test_cli_macro_commands.py tests/unit/test_worker_settings.py tests/architecture/test_api_read_paths_provider_free.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_project_structure.py
```

Result: `All checks passed!`.

## Docker Smoke

Not run in this pass. Required live smoke before merge/deploy:

```bash
docker compose exec app /app/.venv/bin/macrodata --help
docker compose exec app /app/.venv/bin/gmgn-twitter-intel macro status
```

Expected status evidence: `latest_sync_run`, `facts_max_observed_at`, and `projection_behind_facts` are present, and no secret values are printed.
