# Token Profile Image Mirror Root Fix Verification

Date: 2026-05-31
Worktree: `/Users/qinghuan/Documents/code/parallax/.worktrees/token-profile-image-mirror-root-fix`
Branch: `codex/token-profile-image-mirror-root-fix`

## Summary

- Root-fix targeted tests pass.
- Live repair proved the missing durable admission path: `repair-token-profile-images` admitted 208 image source dirty targets from existing stuck profile rows.
- `token_image_mirror` consumed admitted work and wrote local image assets: 19 mirrored, 89 unsupported, 0 error.
- `asset-flow` now shows same-origin `/api/token-images/{image_id}` for a live BTC profile row.
- Full `make check-all` is not green because the repository currently has unrelated `ruff format --check` drift in 36 pre-existing files outside this change set. I did not mass-format unrelated files.

## Runtime Config

Command:

```bash
uv run parallax config
```

Result:

- `config_path=/Users/qinghuan/.parallax/config.yaml`
- `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`
- PostgreSQL DSN output was redacted by the CLI.
- `gmgn_configured=true`, `okx.dex_configured=true`, `binance.enabled=true`
- `token_image_mirror.enabled=true`
- `token_profile_current.enabled=true`

The command emitted optional LiteLLM `botocore` preload warnings only.

## Full Gate

Command:

```bash
make check-all
```

Result: failed at `ruff format --check` before unit/integration/e2e/golden/coverage gates.

Full final output:

```text
All checks passed!
Would reformat: src/parallax/app/runtime/job_queue.py
Would reformat: src/parallax/app/surfaces/api/routes_radar.py
Would reformat: src/parallax/app/surfaces/cli/commands/macro.py
Would reformat: src/parallax/domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py
Would reformat: src/parallax/domains/asset_market/repositories/token_profile_current_repository.py
Would reformat: src/parallax/domains/macro_intel/repositories/macro_intel_repository.py
Would reformat: src/parallax/domains/notifications/services/notification_rules.py
Would reformat: src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py
Would reformat: src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py
Would reformat: src/parallax/platform/db/alembic/versions/20260528_0116_macro_workerspace_root_fix.py
Would reformat: tests/architecture/test_agent_input_identity_contracts.py
Would reformat: tests/architecture/test_event_anchor_capture_redesign_contracts.py
Would reformat: tests/architecture/test_macro_no_compatibility_contract.py
Would reformat: tests/architecture/test_notifications_hard_cut.py
Would reformat: tests/architecture/test_project_structure.py
Would reformat: tests/architecture/test_src_domain_architecture.py
Would reformat: tests/architecture/test_token_radar_publication_state_hard_cut.py
Would reformat: tests/architecture/test_token_radar_source_width_contract.py
Would reformat: tests/architecture/test_token_radar_venue_leaderboard_contract.py
Would reformat: tests/golden/test_token_radar_corpus.py
Would reformat: tests/integration/test_narrative_repository.py
Would reformat: tests/unit/domains/macro_intel/test_macro_migration_contract.py
Would reformat: tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py
Would reformat: tests/unit/domains/macro_intel/test_macro_sync_service.py
Would reformat: tests/unit/domains/narrative_intel/test_narrative_workers.py
Would reformat: tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py
Would reformat: tests/unit/domains/token_intel/test_token_radar_venue.py
Would reformat: tests/unit/test_market_tick_current_projection_worker.py
Would reformat: tests/unit/test_notification_rules.py
Would reformat: tests/unit/test_postgres_observability_scripts.py
Would reformat: tests/unit/test_postgres_schema.py
Would reformat: tests/unit/test_settings.py
Would reformat: tests/unit/test_token_radar_projection.py
Would reformat: tests/unit/test_token_radar_projection_worker.py
Would reformat: tests/unit/test_token_radar_repository.py
Would reformat: tests/unit/watchlist/test_watchlist_intel_api.py
36 files would be reformatted, 925 files already formatted
make[1]: *** [check] Error 1
make: *** [check-all] Error 2
```

Coverage, integration, e2e, and golden sub-gates were not reached by `make check-all` because format check failed first.

## Targeted Verification

Command:

```bash
uv run pytest tests/unit/test_token_image_source_admission.py tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_current_worker.py tests/unit/test_token_image_mirror_worker.py tests/integration/test_token_image_asset_repository.py tests/integration/test_token_image_source_dirty_target_repository.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_worker_runtime_contracts.py tests/integration/test_cli.py tests/unit/test_cli.py tests/unit/test_ops_backfill_commands.py -q
```

Result:

```text
230 passed, 1 skipped, 2 subtests passed in 62.30s (0:01:02)
```

Skipped:

```text
tests/architecture/test_worker_runtime_contracts.py:774: got empty parameter set for (table_name)
```

Commands:

```bash
uv run ruff check <changed python files>
uv run ruff format --check <changed python files>
```

Results:

```text
All checks passed!
19 files already formatted
```

## Provider URL Fallback Check

Command:

```bash
rg -n "/api/token-image\?url|logo_url.*https?://" web/src src/parallax/app/surfaces/api src/parallax/domains/token_intel
```

Result: no matches.

Broader grep for provider image source strings found only source ingestion/provenance code and tests, not frontend/API public rendering fallback.

## Live Before

Command:

```bash
uv run parallax ops worker-status
```

Relevant queue summary before repair:

```json
{
  "token_profile_current": {"queue_depth": 18, "due_count": 18, "reason": "fresh_work"},
  "token_image_mirror": {"queue_depth": 0, "due_count": 0, "reason": "no_active_work"},
  "asset_profile_refresh": {"queue_depth": 0, "due_count": 0, "reason": "no_active_work"}
}
```

Command:

```bash
uv run parallax asset-flow --window 1h --scope all --limit 20
```

Relevant summary before repair:

```json
{
  "target_count": 20,
  "with_logo": 0,
  "missing_logo": 20
}
```

## Live Repair

Command:

```bash
uv run parallax ops repair-token-profile-images --limit 500
```

Result summary:

```json
{
  "selected_targets": 239,
  "profile_targets_enqueued": 239,
  "profile_rebuild": {
    "selected": 264,
    "claimed": 264,
    "targets_loaded": 264,
    "rows_written": 264,
    "ready": 243,
    "missing": 19,
    "unsupported": 2,
    "error": 0,
    "with_logo": 0,
    "image_candidates": 208,
    "image_sources_admitted": 208,
    "image_ready_existing": 0,
    "image_pending_existing": 0,
    "image_error_existing": 0,
    "image_unsupported_existing": 0,
    "image_dirty_existing": 0
  }
}
```

This is the root-cause proof: existing stuck profile rows produced image candidates and durable `token_image_source_dirty_targets`.

## Live Mirror

Command:

```bash
uv run parallax ops mirror-token-images --limit 200
```

Result summary:

```json
{
  "selected": 108,
  "pending_upserted": 108,
  "claimed": 108,
  "rows_written": 108,
  "mirrored": 19,
  "unsupported": 89,
  "error": 0
}
```

Follow-up command:

```bash
uv run parallax ops mirror-token-images --limit 50
```

Result summary:

```json
{
  "claimed": 0,
  "reason": "no_due_token_image_source_targets"
}
```

## Live Rebuild And Read Verification

Command:

```bash
uv run parallax ops rebuild-token-profiles --limit 500
```

Result summary:

```json
{
  "selected": 37,
  "claimed": 37,
  "rows_written": 37,
  "ready": 23,
  "missing": 13,
  "unsupported": 1,
  "error": 0,
  "with_logo": 7,
  "image_candidates": 21,
  "image_sources_admitted": 1,
  "image_ready_existing": 7,
  "image_unsupported_existing": 13
}
```

Follow-up command:

```bash
uv run parallax ops rebuild-token-profiles --limit 100
```

Result summary:

```json
{
  "selected": 21,
  "claimed": 21,
  "rows_written": 21,
  "ready": 9,
  "missing": 12,
  "unsupported": 0,
  "error": 0,
  "with_logo": 3,
  "image_candidates": 7,
  "image_sources_admitted": 0,
  "image_ready_existing": 3,
  "image_unsupported_existing": 4
}
```

Final worker queue summary:

```json
{
  "token_image_mirror": {"queue_depth": 0, "due_count": 0, "reason": "no_active_work"},
  "token_profile_current": {"queue_depth": 36, "due_count": 36, "reason": "fresh_work"}
}
```

Final read summary:

```json
{
  "target_count": 20,
  "with_logo": 1,
  "missing_logo": 19,
  "sample_with_logo": [
    {
      "symbol": "BTC",
      "target_id": "cex_token:BTC",
      "logo_url": "/api/token-images/428fd960582e22a71610af19327691afd5b68fbb0d056e9195510fccde34b63b",
      "quality_flags": null
    }
  ]
}
```

## Remaining Risks

- Full completion gate remains blocked by unrelated repository-wide formatting drift. I did not mass-format unrelated files.
- Many live image candidates were unsupported by mirror validation or bytes/media checks. This is expected for non-image/default/blocked provider URLs; they remain no-logo rows without provider URL fallback.
- `token_profile_current_dirty_targets` continued to receive live work during verification; final profile queue depth was 36. `token_image_source_dirty_targets` drained to 0, which is the critical icon mirror queue.
