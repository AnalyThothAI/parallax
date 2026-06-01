# Rates Workbench Clarity Redesign Verification

**Date:** 2026-06-01  
**Branch:** `codex/rates-workbench-clarity-redesign`  
**Worktree:** `.worktrees/rates-workbench-clarity-redesign/`  
**Plan:** `docs/superpowers/plans/active/2026-06-01-rates-workbench-clarity-redesign.md`

## Summary

The rates routes now render through a rates-specific workbench instead of the generic macro leaf renderer. The primary reading order is:

1. `利率页导航`
2. `市场解读`
3. `关键事实`
4. `主要图表`
5. `决策支持`
6. `利率明细`
7. `利率数据诊断`

Diagnostics and provenance remain inspectable, but raw projection ids, concept keys, gap codes, and JSON-like blobs are kept out of the primary reading area.

## Spec Coverage

| AC | Result | Evidence |
|----|--------|----------|
| AC1 | Covered | Rates route branch and shell header verified by component tests and E2E. |
| AC2 | Covered | Fed funds, auctions, real rates, expectations fixtures render readable market read/fact sections. |
| AC3 | Covered | Fed funds corridor model and SVG chart covered by unit/component tests. |
| AC4 | Covered | Yield curve uses inline `points` when `latest` is absent. |
| AC5 | Covered | Proxy copy for auctions and expectations is human-readable. |
| AC6 | Covered | Official auction table precedence tested. |
| AC7 | Covered | Real rates fixture displays facts/read before diagnostics. |
| AC8 | Covered | Raw keys/gap codes are blocked in primary UI by model/component/E2E assertions. |
| AC9 | Covered | Official expectations table precedence tested. |
| AC10 | Covered | Responsive route audit covers all rates child routes. |
| AC11 | Covered | Diagnostics remain after primary visual and include diagnostic tables. |
| AC12 | Covered | `macroRatesWorkbench.css` is owned by macro responsive architecture harness. |
| AC13 | Covered | E2E asserts no body overflow / table overflow / metric fragmentation. |
| AC14 | Covered with smoke notes | Browser smoke recorded below for all five rates child routes. |

## Coverage

- Model tests: rates workbench view model, rates corridor chart model, yield-curve inline-point fallback.
- Component tests: rates workbench hierarchy, proxy readability, diagnostic table placement, yield-curve chart inline-point rendering, non-rates macro module regression.
- Architecture tests: macro CSS owner discovery, allowed breakpoints, no destructive wrapping, no retired selectors.
- E2E: macro responsive audit over rates product routes and hidden-supported auction route.

## Commands

### Passed

```text
cd web && npm run lint
Result: exit 0
Test Files: 11 passed (11)
Tests: 64 passed (64)
```

```text
cd web && npm run typecheck
Result: exit 0
```

```text
cd web && npm run build
Result: exit 0
Note: Vite emitted the existing large chunk warning for index-C6DvGm9S.js (651.61 kB).
```

```text
cd web && npm test -- --run tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesChartModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx
Result: exit 0
Test Files: 6 passed (6)
Tests: 49 passed (49)
```

```text
cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts
Result: exit 0
1 passed, 4 skipped
```

### Failed Existing Gates

```text
cd web && npm test -- --run
Result: exit 1
Test Files: 2 failed | 96 passed (98)
Tests: 2 failed | 418 passed (420)
Failures:
- tests/unit/features/signal-lab/useSignalPulseQueries.test.tsx expects /api/social-events/by-ids but code calls /api/events/by-ids.
- tests/component/features/watchlist/ui/WatchlistPage.test.tsx times out at 5000ms in "renders the full source navigator and keeps timeline scope when switching handles".
```

Both failing tests were reproduced from the main checkout before being recorded as branch risk, so they are not introduced by the rates workbench files.

## Full `make check-all` Output

```text
All checks passed!
Would reformat: src/parallax/app/runtime/job_queue.py
Would reformat: src/parallax/app/surfaces/api/routes_radar.py
Would reformat: src/parallax/app/surfaces/cli/commands/macro.py
Would reformat: src/parallax/domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py
Would reformat: src/parallax/domains/asset_market/repositories/token_profile_current_repository.py
Would reformat: src/parallax/domains/macro_intel/repositories/macro_intel_repository.py
Would reformat: src/parallax/domains/news_intel/runtime/news_item_brief_worker.py
Would reformat: src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py
Would reformat: src/parallax/domains/token_intel/read_models/stocks_radar_service.py
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
37 files would be reformatted, 931 files already formatted
make[1]: *** [check] Error 1
make: *** [check-all] Error 2
```

This is the same harness class already tracked in `docs/TECH_DEBT.md` as a pre-existing `make check-all` baseline debt.

## Real-Data Smoke

Commands:

```text
uv run parallax config
uv run parallax db health
uv run parallax macro status
```

Redacted config result:

```json
{
  "config_path": "/Users/qinghuan/.parallax/config.yaml",
  "workers_config_path": "/Users/qinghuan/.parallax/workers.yaml",
  "macrodata_enabled": true,
  "fred_api_key_configured": false
}
```

Database health:

```text
Result: exit 1
ok=false
probe=postgres_liveness
migration_version=20260601_0141
expected_migration_version=20260601_0140
migration_status=stale
```

Macro status:

```text
Result: exit 0
migration_ready=true
fred_api_key_configured=false
observations_count=27049
concept_count=36
history_ready=false
history_ready_concepts=33 / 115
history_coverage_ratio=0.286957
facts_max_observed_at=2026-06-01
latest_snapshot_status=partial
rates_panel_regime=neutral
rates_panel_data_gap_count=0
```

## Browser Smoke

Browser smoke was run with Playwright against `http://127.0.0.1:5174` using the local Vite server.

| Route | Backing | Result |
|-------|---------|--------|
| `/macro/rates/fed-funds` | Fact-backed, partial | Workbench visible; facts show target corridor/EFFR/IORB/SOFR; diagnostics after chart; no horizontal overflow. |
| `/macro/rates/yield-curve` | Fact-backed, partial | Workbench visible; available tenors draw; missing tenor notes are readable; diagnostics after chart; no horizontal overflow. |
| `/macro/rates/auctions` | Proxy-backed | Shows `当前为拍卖代理页面`; proxy chart/table not empty; diagnostics after chart; no horizontal overflow. |
| `/macro/rates/real-rates` | Fact-backed, ready | Workbench visible; real-rate facts before diagnostics; diagnostics after chart; no horizontal overflow. |
| `/macro/rates/expectations` | Proxy-backed | Shows `当前为政策路径代理页面`; proxy chart/table not empty; diagnostics after chart; no horizontal overflow. |

Mobile/tablet smoke:

```text
mobile-390: all five rates routes doc/body overflow=false
tablet-834: all five rates routes doc/body overflow=false
```

## E2E Golden Path

`macro-responsive-audit.spec.ts` now:

- returns rates-specific fixtures from `mockApi`;
- waits for `图表序列加载中` to disappear before scanning primary text;
- asserts rates nav/market/primary/diagnostics regions exist;
- asserts the rates regions appear in the intended DOM order;
- blocks raw `macro_module_view_v3`, `source_snapshot_id`, rates/fed/liquidity/inflation concept keys, `_missing` gap codes, and JSON braces above diagnostics;
- ignores only the known mock-mode `/ws` handshake console error, because `installMockApi` mocks HTTP API traffic but not WebSocket traffic.

Skipped tests:

```text
macro-responsive-audit.spec.ts: 4 skipped
Reason: the spec intentionally runs its viewport matrix inside the desktop-1366 Playwright project.
```

## Diff Review

`git diff --stat main...HEAD`:

```text
27 files changed, 4895 insertions(+), 5 deletions(-)
```

Touched areas match the plan:

- `docs/superpowers/specs/active`
- `docs/superpowers/plans/active`
- `web/src/features/macro`
- `web/tests`

## Code Review

- Task 4 review approved after diagnostic tables were restored.
- Task 5 review found two E2E audit risks: raw-text scan before chart hydration and too-narrow raw-id regex.
- Both Task 5 findings were fixed in `79084d47 test: harden rates workbench audit checks`.

## Remaining Risks And Follow-Ups

- Repository completion gate remains blocked by pre-existing `make check-all` Python formatting debt already tracked in `docs/TECH_DEBT.md`.
- Full frontend Vitest gate remains blocked by two pre-existing non-rates failures; a new TECH_DEBT row records this.
- Real-data DB smoke currently reports migration status `stale`; this is an operator/runtime state issue, not a rates frontend regression.
- Macro real-data readiness is partial because `FINANCE_FRED_API_KEY` is not configured and history coverage is 33 / 115 concepts.
