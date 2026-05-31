# Verification - Macro Workbench Hard Cut

**Date**: 2026-05-24
**Owning spec**: `docs/superpowers/specs/active/2026-05-24-macro-workbench-hard-cut-root-fix-cn.md`
**Owning plan**: `docs/superpowers/plans/active/2026-05-24-macro-workbench-hard-cut-root-fix-plan-cn.md`
**Branch**: `codex/macro-workbench-hard-cut`
**Worktree**: `/Users/qinghuan/Documents/code/parallax/.worktrees/macro-workbench-hard-cut`

## Summary

The hard-cut implementation now uses `macro_regime_v4` and
`macro_module_view_v2` through backend projections, API contracts, generated
types, frontend models, fixtures, route shells, and macro module pages. The
frontend no longer depends on legacy `chart_id` / `table_id`,
`current_read`, `charts`, or `signals` fields. Macro page visible text renders
semantic labels, localized gaps, source-quality rows, and evidence
descriptions instead of raw concept keys, raw provider ids, or JSON.

## Acceptance Evidence

| Area | Status | Evidence |
|------|--------|----------|
| Backend v4 readiness and module v2 contract | Pass | `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_feature_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 62 passed |
| Backend lint | Pass | `uv run ruff check src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py src/parallax/domains/macro_intel tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py` -> all checks passed |
| Touched Python formatting | Pass | `uv run ruff format --check <20 touched macro/API/CLI/test files>` -> 20 files already formatted |
| Backend type check | Pass | `uv run mypy src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py` -> success, 18 source files |
| Frontend macro tests | Pass | `cd web && npm test -- --run ...macro tests...` -> 9 files, 45 tests passed |
| Frontend lint and architecture | Pass | `cd web && npm run lint` -> ESLint passed, architecture 10 files / 59 tests passed |
| Frontend type check | Pass | `cd web && npm run typecheck` -> passed |
| Frontend production build | Pass | `cd web && npm run build` -> Vite build succeeded |
| Mobile golden path | Pass | `cd web && npx playwright test mobile-route-cold-load.spec.ts --project=mobile-390` -> 11 passed |
| Tablet macro smoke | Pass | Browser resize to 834px with mocked v2 macro payload: no banned raw terms and `documentElement.scrollWidth == innerWidth == 834` |
| Raw-term smoke | Pass | Browser check against mocked `/macro`: no `asset:spx`, `rates:dgs10`, `insufficient_history_60d`, `provider_not_configured`, `macro_module_view_v1`, `macro_regime_v3`, `current_read`, `signals`, or `{` visible |
| Diff whitespace | Pass | `git diff --check` -> passed |

## Project Gate

`make check-all` was run after formatting this change's touched Python files.
It still exits 2 during the repository-wide format gate:

```text
$ make check-all
All checks passed!
Would reformat: scripts/regen_pulse_agent_desk_decisions.py
Would reformat: src/parallax/app/runtime/ops_diagnostics.py
...
Would reformat: src/parallax/domains/macro_intel/services/macro_asset_correlation.py
...
Would reformat: tests/unit/test_token_image_mirror_worker.py
66 files would be reformatted, 838 files already formatted
make[1]: *** [check] Error 1
make: *** [check-all] Error 2
exit code: 2
```

The remaining format failures are pre-existing or out-of-scope files across
ops, narrative, news, pulse, token, integrations, migrations, and one
unmodified macro file (`macro_asset_correlation.py`). They were not reformatted
in this branch to avoid unrelated churn.

## Real-Data Diagnostics

Commands were run with redaction discipline. Secret values were not copied.

```text
$ uv run parallax config
ok=true
config_path=/Users/qinghuan/.parallax/config.yaml
workers_config_path=/Users/qinghuan/.parallax/workers.yaml
ws_token_configured=true
providers: gmgn=true, okx=true, binance=true
workers: macro_view_projection enabled=true, cex_oi_radar_board enabled=false
```

```text
$ uv run parallax db health
ok=true
probe=postgres_liveness
migration_version=20260524_0093
expected_migration_version=20260524_0093
migration_status=ready
```

```text
$ uv run parallax macro status
ok=true
migration_ready=true
observations_count=36
concept_count=36
history_ready=false
history_coverage.required_points=126
history_coverage.required_concept_count=36
history_coverage.ready_concept_count=0
history_coverage.coverage_ratio=0.0
latest_import_run.status=ok
latest_import_run.bundle_name=macro-core
latest_snapshot=null before manual projection
```

```text
$ uv run parallax macro project-once
ok=true
projection_version=macro_regime_v4
status=stale
regime=term_premium_pressure
```

After manual projection, `macro status` reports a latest
`macro_regime_v4` snapshot with `status=stale`,
`latest_coverage_ratio=1.0`, and `history_coverage_ratio=0.0`. This is the
expected honest degradation for the current live store: every required concept
has a latest fact, but each concept has only one historical point, and the
broad dollar observation is stale.

Real-data page readiness cannot be asserted until macro history has been
backfilled to at least the required 126 points per required concept and the
projection is regenerated.

## Browser Smoke

Local frontend server: `http://127.0.0.1:5173/macro`.

Mocked v2 API payloads were used because the local API/DB was unavailable. The
route rendered:

- module question and status strip
- current read with headline, regime, confidence, crypto read, and token impact
- KPI strip with human labels and observed dates
- localized insufficient-history chart state
- typed support table
- four evidence groups with descriptions
- source-quality provenance rows
- localized data gaps

Screenshots captured by Playwright MCP:

- `macro-hard-cut-desktop.png`
- `macro-hard-cut-tablet-834.png`

## Residual Risks

- Repository-wide `make check-all` is blocked by unrelated formatting debt. The
  macro/API/frontend gates listed above are green.
- Real-data DB smoke now connects and produces a v4 snapshot, but live macro
  readiness remains degraded because the operator store currently has 36
  concepts with one point each and `history_coverage_ratio=0.0`.
- Final subagent re-review could not run because the subagent quota was
  exhausted. Earlier subagent findings were fixed and then covered by targeted
  tests, grep scans, type checks, build, and browser smoke.

## Follow-Ups

- Decide separately whether to run repository-wide `ruff format` across the 66
  unrelated files so `make check-all` can reach later gates.
- After PostgreSQL is reachable, run the documented history backfill and verify
  `/macro`, `/macro/assets`, `/macro/rates`, `/macro/fed`, `/macro/liquidity`,
  `/macro/volatility`, `/macro/credit`, and
  `/macro/assets/crypto-derivatives` against live data.
